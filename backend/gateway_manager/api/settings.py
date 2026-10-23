from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, ValidationError

from ..auth import AuthError
from ..deps import AppContext, client_ip, current_session, get_ctx, validation_detail, write_session
from ..models import Project, Settings
from ..store import State

router = APIRouter(tags=["settings"])


class UserBody(BaseModel):
    username: str
    password: str


@router.get("/settings")
def get_settings(ctx: AppContext = Depends(get_ctx), session=Depends(current_session)):
    return ctx.store.load().settings.model_dump(mode="json")


@router.put("/settings")
def put_settings(request: Request, body: dict = Body(...), ctx: AppContext = Depends(get_ctx),
                 session=Depends(write_session)):
    try:
        settings = Settings.model_validate(body)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=validation_detail(e, "the settings are not valid"))

    def mutate(state: State):
        old = state.settings
        state.settings = settings
        changed = [k for k in Settings.model_fields if getattr(old, k) != getattr(settings, k)]
        return "changed: " + (", ".join(changed) or "nothing")

    return ctx.service.update(mutate, user=session.username, ip=client_ip(request), action="settings")


@router.get("/users")
def list_users(ctx: AppContext = Depends(get_ctx), session=Depends(current_session)):
    return {"users": ctx.users.list()}


@router.post("/users")
def add_user(body: UserBody, request: Request, ctx: AppContext = Depends(get_ctx), session=Depends(write_session)):
    try:
        if ctx.users.exists(body.username):
            raise AuthError("that user already exists")
        ctx.users.set_password(body.username, body.password, create=True)
    except AuthError as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})
    ctx.audit.log(session.username, client_ip(request), "user-add", body.username.strip().lower())
    return {"users": ctx.users.list()}


@router.delete("/users/{username}")
def remove_user(username: str, request: Request, ctx: AppContext = Depends(get_ctx), session=Depends(write_session)):
    try:
        ctx.users.remove(username)
    except AuthError as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})
    ctx.audit.log(session.username, client_ip(request), "user-remove", username)
    return {"users": ctx.users.list()}


@router.get("/export")
def export(ctx: AppContext = Depends(get_ctx), session=Depends(current_session)):
    state = ctx.store.load()
    return {"settings": state.settings.model_dump(mode="json"),
            "projects": [p.model_dump(mode="json") for p in state.projects]}


@router.post("/import")
def import_projects(request: Request, body: dict = Body(...), ctx: AppContext = Depends(get_ctx),
                    session=Depends(write_session)):
    """{"projects": [...], "settings": {...}?, "mode": "merge" | "replace"}"""
    try:
        projects = [Project.model_validate(p) for p in body.get("projects", [])]
        settings = Settings.model_validate(body["settings"]) if body.get("settings") else None
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=validation_detail(e, "the import file is not valid"))
    mode = body.get("mode", "merge")
    if mode not in ("merge", "replace"):
        raise HTTPException(status_code=400, detail={"message": "mode must be merge or replace"})

    def mutate(state: State):
        if settings:
            state.settings = settings
        if mode == "replace":
            state.projects = projects
        else:
            by_id = {p.id: p for p in state.projects}
            by_id.update({p.id: p for p in projects})
            state.projects = list(by_id.values())
        return f"{mode}: {len(projects)} project(s)"

    return ctx.service.update(mutate, user=session.username, ip=client_ip(request), action="import")
