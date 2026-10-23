from fastapi import APIRouter, Depends

from .. import __version__, diagnostics, guide, nginx_helper
from ..deps import AppContext, current_session, get_ctx
from ..models import ApiMode, PathMode

router = APIRouter(tags=["status"])

PATH_MODES = {
    PathMode.subpath: "Forward /prefix/... unchanged (the app is started or built with --base /prefix/)",
    PathMode.strip: "Remove /prefix before forwarding (a static server or backend serving a build made with --base)",
    PathMode.rewrite: "Remove /prefix and rewrite /... links in HTML/CSS/JS (best effort, simple pages only)",
}
API_MODES = {
    ApiMode.strip_prefix: "/prefix/api/x reaches the backend as /api/x",
    ApiMode.strip_all: "/prefix/api/x reaches the backend as /x",
    ApiMode.preserve: "/prefix/api/x reaches the backend unchanged",
}


@router.get("/status")
def status(ctx: AppContext = Depends(get_ctx), session=Depends(current_session)):
    state = ctx.store.load()
    ports = diagnostics.listeners()
    ts = diagnostics.tailscale_info()
    nginx = ctx.helper.status()
    return {
        "version": __version__,
        "helper_mode": ctx.helper.mode,
        "nginx": nginx,
        "tailscale": ts,
        "urls": diagnostics.gateway_urls(state.settings, ts),
        "drift": ctx.service.drift(state),
        "applied": {"at": state.applied.at, "by": state.applied.by} if state.applied else None,
        "last_apply": state.last_apply.model_dump(mode="json") if state.last_apply else None,
        "port_80": {"listening": 80 in ports, "addresses": ports.get(80, [])},
        "gateway_listening": state.settings.gateway_port in ports,
        "password_is_default": ctx.users.is_default_password(session.username),
    }


@router.get("/meta")
def meta(ctx: AppContext = Depends(get_ctx), session=Depends(current_session)):
    targets = nginx_helper.read_restart_targets(str(ctx.cfg.restart_targets))
    return {
        "version": __version__,
        "presets": guide.presets_for_api(),
        "path_modes": [{"value": k.value, "help": v} for k, v in PATH_MODES.items()],
        "api_modes": [{"value": k.value, "help": v} for k, v in API_MODES.items()],
        "restart_targets": [{"id": k, "kind": v[0], "name": v[1]} for k, v in sorted(targets.items())],
        "restart_targets_file": str(ctx.cfg.restart_targets),
        "manager_port": ctx.cfg.manager_port,
    }
