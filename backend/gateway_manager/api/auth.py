from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from ..auth import AuthError, normalize_username
from ..deps import COOKIE, AppContext, client_ip, current_session, get_ctx, write_session

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str
    password: str


class PasswordBody(BaseModel):
    current: str
    new: str


def _me(ctx: AppContext, session) -> dict:
    return {"username": session.username, "csrf": session.csrf,
            "password_is_default": ctx.users.is_default_password(session.username)}


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response, ctx: AppContext = Depends(get_ctx)):
    ip = client_ip(request)
    try:
        user = normalize_username(body.username)
    except AuthError:
        user = "?"
    keys = (f"ip:{ip}", f"user:{user}")
    wait = ctx.throttle.retry_after(*keys)
    if wait:
        raise HTTPException(status_code=429, detail={"message": f"too many failed logins; try again in {wait} s"},
                            headers={"Retry-After": str(wait)})
    if not ctx.users.verify(user, body.password):
        ctx.throttle.failure(*keys)
        ctx.audit.log(user, ip, "login-failed")
        raise HTTPException(status_code=401, detail={"message": "wrong email or password"})
    ctx.throttle.success(*keys)
    token, session = ctx.sessions.create(user, ip)
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict", path="/",
                        secure=request.url.scheme == "https", max_age=ctx.cfg.session_max_seconds)
    ctx.audit.log(user, ip, "login")
    return _me(ctx, session)


@router.post("/logout")
def logout(request: Request, response: Response, ctx: AppContext = Depends(get_ctx),
           session=Depends(write_session)):
    ctx.sessions.revoke(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(ctx: AppContext = Depends(get_ctx), session=Depends(current_session)):
    return _me(ctx, session)


@router.post("/password")
def change_password(body: PasswordBody, request: Request, ctx: AppContext = Depends(get_ctx),
                    session=Depends(write_session)):
    if not ctx.users.verify(session.username, body.current):
        raise HTTPException(status_code=400, detail={"message": "the current password is wrong"})
    try:
        ctx.users.set_password(session.username, body.new)
    except AuthError as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})
    ctx.sessions.revoke_user(session.username, keep_token=request.cookies.get(COOKIE))
    ctx.audit.log(session.username, client_ip(request), "password-changed")
    return {"ok": True}
