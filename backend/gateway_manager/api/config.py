import difflib

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..deps import AppContext, client_ip, current_session, get_ctx, write_session

router = APIRouter(tags=["config"])


class ValidateBody(BaseModel):
    full: bool = False


@router.get("/config/preview")
def preview(ctx: AppContext = Depends(get_ctx), session=Depends(current_session)):
    state = ctx.store.load()
    check = ctx.service.check(state.settings, state.projects, run_nginx=False)
    generated = check.config
    live = ctx.service.read_live()
    diff = "".join(difflib.unified_diff((live or "").splitlines(keepends=True), generated.splitlines(keepends=True),
                                        fromfile="live (nginx)", tofile="generated (dashboard)"))
    return {"generated": generated, "live": live, "diff": diff, "in_sync": live == generated,
            "errors": [i.model_dump() for i in check.errors]}


@router.post("/config/validate")
def validate(body: ValidateBody, ctx: AppContext = Depends(get_ctx), session=Depends(write_session)):
    state = ctx.store.load()
    check = ctx.service.check(state.settings, state.projects)
    result = {"sandbox": check.as_dict(), "full": None}
    if body.full and check.ok:
        result["full"] = ctx.helper.test_full(check.config)
    return result


@router.post("/config/apply")
def apply(request: Request, ctx: AppContext = Depends(get_ctx), session=Depends(write_session)):
    result = ctx.service.apply(user=session.username, ip=client_ip(request))
    return {"apply": result, "state": ctx.service.public_state()}


@router.post("/config/revert")
def revert(request: Request, ctx: AppContext = Depends(get_ctx), session=Depends(write_session)):
    result = ctx.service.revert_to_applied(user=session.username, ip=client_ip(request))
    return {"apply": result, "state": ctx.service.public_state()}


@router.get("/config/backups")
def backups(ctx: AppContext = Depends(get_ctx), session=Depends(current_session)):
    return ctx.helper.backups()


@router.post("/config/restore/{backup_id}")
def restore(backup_id: str, request: Request, ctx: AppContext = Depends(get_ctx), session=Depends(write_session)):
    result = ctx.helper.restore(backup_id)
    ctx.audit.log(session.username, client_ip(request), "config-restore", backup_id, result.get("message"))
    return {"apply": result, "state": ctx.service.public_state()}


@router.post("/nginx/start")
def start_nginx(request: Request, ctx: AppContext = Depends(get_ctx), session=Depends(write_session)):
    result = ctx.helper.start()
    ctx.audit.log(session.username, client_ip(request), "nginx-start", None, result.get("message"))
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result)
    return result
