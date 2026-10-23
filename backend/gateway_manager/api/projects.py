from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import ValidationError

from .. import diagnostics, guide
from ..deps import AppContext, client_ip, current_session, get_ctx, validation_detail, write_session
from ..generator import UnsafeValue, render_project_snippet
from ..models import Issue, Project, check_state
from ..service import Conflict, NotFound
from ..store import State

router = APIRouter(prefix="/projects", tags=["projects"])


def _parse(body: dict) -> Project:
    try:
        return Project.model_validate(body)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=validation_detail(e, "the project settings are not valid"))


def _get(state: State, project_id: str) -> Project:
    project = state.project(project_id)
    if project is None:
        raise NotFound(f"no project {project_id!r}")
    return project


@router.get("")
def list_projects(ctx: AppContext = Depends(get_ctx), session=Depends(current_session)):
    return ctx.service.public_state()


@router.get("/status")
async def projects_status(ctx: AppContext = Depends(get_ctx), session=Depends(current_session)):
    return await diagnostics.quick_status(ctx.store.load().projects)


@router.post("/preview")
def preview(body: dict = Body(...), ctx: AppContext = Depends(get_ctx), session=Depends(current_session)):
    """Validation and the nginx snippet for an unsaved project (the editor's live preview)."""
    try:
        project = Project.model_validate(body)
    except ValidationError as e:
        return {"snippet": "", **validation_detail(e, "not valid yet")}
    state = ctx.store.load()
    others = [p for p in state.projects if p.id != project.id]
    errors, warnings = check_state(state.settings, others + [project], ctx.cfg.manager_port)
    errors = [i for i in errors if i.project_id in (None, project.id)]
    warnings = [i for i in warnings if i.project_id in (None, project.id)]
    try:
        snippet = render_project_snippet(project)
    except UnsafeValue as e:
        snippet = ""
        errors.append(Issue(message=str(e)))
    return {"snippet": snippet, "message": "", "errors": [i.model_dump() for i in errors],
            "warnings": [i.model_dump() for i in warnings]}


@router.post("")
def create_project(request: Request, body: dict = Body(...), ctx: AppContext = Depends(get_ctx),
                   session=Depends(write_session)):
    project = _parse(body)

    def mutate(state: State):
        if state.project(project.id):
            raise Conflict(f"a project with id {project.id!r} already exists")
        state.projects.append(project)
        return f"{project.prefix or ':' + str(project.dedicated_port)} -> {project.frontend.hostport}"

    return ctx.service.update(mutate, user=session.username, ip=client_ip(request), action="project-add",
                              target=project.id)


@router.put("/{project_id}")
def update_project(project_id: str, request: Request, body: dict = Body(...), ctx: AppContext = Depends(get_ctx),
                   session=Depends(write_session)):
    project = _parse(body)
    if project.id != project_id:
        raise HTTPException(status_code=400, detail={"message": "the project id cannot be changed"})

    def mutate(state: State):
        old = _get(state, project_id)
        state.projects[state.projects.index(old)] = project
        changed = [k for k in Project.model_fields if getattr(old, k) != getattr(project, k)]
        return "changed: " + (", ".join(changed) or "nothing")

    return ctx.service.update(mutate, user=session.username, ip=client_ip(request), action="project-edit",
                              target=project_id)


@router.delete("/{project_id}")
def delete_project(project_id: str, request: Request, ctx: AppContext = Depends(get_ctx),
                   session=Depends(write_session)):
    def mutate(state: State):
        state.projects.remove(_get(state, project_id))

    return ctx.service.update(mutate, user=session.username, ip=client_ip(request), action="project-delete",
                              target=project_id)


@router.post("/{project_id}/{action}")
async def project_action(project_id: str, action: str, request: Request, ctx: AppContext = Depends(get_ctx),
                         session=Depends(write_session)):
    ip = client_ip(request)
    if action in ("enable", "disable"):
        def mutate(state: State):
            _get(state, project_id).enabled = action == "enable"
        return ctx.service.update(mutate, user=session.username, ip=ip, action=f"project-{action}", target=project_id)
    state = ctx.store.load()
    project = _get(state, project_id)
    if action == "test":
        return await diagnostics.test_project(project, state.settings)
    if action == "restart":
        if not project.restart_target:
            raise HTTPException(status_code=400, detail={"message": "set a restart target for this project first"})
        result = ctx.helper.restart(project.restart_target)
        ctx.audit.log(session.username, ip, "project-restart", project_id, result.get("message"))
        if not result.get("ok"):
            raise HTTPException(status_code=502, detail=result)
        return result
    raise HTTPException(status_code=404, detail={"message": f"unknown action {action}"})


@router.get("/{project_id}/guide")
def project_guide(project_id: str, ctx: AppContext = Depends(get_ctx), session=Depends(current_session)):
    state = ctx.store.load()
    project = _get(state, project_id)
    ts = diagnostics.tailscale_info()
    host = ts.get("dns_name") or (ts.get("ipv4") or ["<tailscale-ip>"])[0]
    return guide.build_guide(project, state.settings.gateway_port, host)
