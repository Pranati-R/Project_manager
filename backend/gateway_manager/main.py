"""FastAPI application: the dashboard API under /api and the static dashboard at /.

Started by systemd as
    uvicorn gateway_manager.main:create_app --factory --host 127.0.0.1 --port 8790
and reached through nginx on the admin port (or an SSH tunnel to 127.0.0.1:8790).
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api import router as api_router
from .audit import Audit
from .auth import LoginThrottle, SessionManager, UserStore
from .config import Config, load_config
from .deps import AppContext
from .helper_client import make_helper
from .service import Conflict, GatewayService, NotFound, ValidationFailed
from .store import Store

CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


def create_app(cfg: Config | None = None, helper=None) -> FastAPI:
    cfg = cfg or load_config()
    helper = helper or make_helper(cfg)
    store = Store(cfg.state_file, cfg.history_dir)
    if not store.exists():
        store.seed(cfg.seed_file)
    users = UserStore(cfg.users_file)
    users.ensure_default()
    audit = Audit(cfg.audit_file)
    ctx = AppContext(
        cfg=cfg, store=store, users=users,
        sessions=SessionManager(cfg.session_idle_seconds, cfg.session_max_seconds),
        throttle=LoginThrottle(), audit=audit,
        service=GatewayService(cfg, store, helper, audit), helper=helper,
    )

    app = FastAPI(title="Nginx Gateway Manager", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.ctx = ctx

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        h = response.headers
        h["Content-Security-Policy"] = CSP
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "DENY"
        h["Referrer-Policy"] = "no-referrer"
        h["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
        return response

    @app.exception_handler(ValidationFailed)
    async def _validation(request: Request, exc: ValidationFailed):
        d = exc.check.as_dict()
        return JSONResponse(status_code=422, content={"detail": {
            "message": "the change was not saved: " + (exc.check.errors[0].message if exc.check.errors else "invalid"),
            **d}})

    @app.exception_handler(NotFound)
    async def _not_found(request: Request, exc: NotFound):
        return JSONResponse(status_code=404, content={"detail": {"message": str(exc)}})

    @app.exception_handler(Conflict)
    async def _conflict(request: Request, exc: Conflict):
        return JSONResponse(status_code=409, content={"detail": {"message": str(exc)}})

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": __version__}

    app.include_router(api_router, prefix="/api")
    app.mount("/", StaticFiles(directory=str(cfg.frontend_dir), html=True, check_dir=False), name="dashboard")
    return app
