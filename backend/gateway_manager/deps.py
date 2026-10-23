"""Shared request plumbing: the app context, client address, sessions and CSRF."""
from __future__ import annotations

import hmac
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from pydantic import ValidationError

from .audit import Audit
from .auth import LoginThrottle, Session, SessionManager, UserStore
from .config import Config
from .service import GatewayService
from .store import Store

COOKIE = "gwm_session"


@dataclass
class AppContext:
    cfg: Config
    store: Store
    users: UserStore
    sessions: SessionManager
    throttle: LoginThrottle
    audit: Audit
    service: GatewayService
    helper: object


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


def client_ip(request: Request) -> str:
    # uvicorn resolves X-Forwarded-For only for requests from nginx on 127.0.0.1
    return request.client.host if request.client else "unknown"


def current_session(request: Request, ctx: AppContext = Depends(get_ctx)) -> Session:
    session = ctx.sessions.get(request.cookies.get(COOKIE), client_ip(request))
    if session is None:
        raise HTTPException(status_code=401, detail={"message": "please log in"})
    return session


def write_session(request: Request, session: Session = Depends(current_session)) -> Session:
    """For every request that changes something: the session's CSRF token must come back."""
    token = request.headers.get("x-csrf-token", "")
    if not hmac.compare_digest(token.encode(), session.csrf.encode()):
        raise HTTPException(status_code=403, detail={"message": "missing or wrong CSRF token; reload the page"})
    return session


def validation_detail(exc: ValidationError, message: str) -> dict:
    """Pydantic errors in the same shape as the gateway's own checks."""
    errors = []
    for e in exc.errors():
        msg = e.get("msg", "invalid value")
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        field = ".".join(str(x) for x in e.get("loc", ()) if not isinstance(x, int)) or None
        if field is None and ": " in msg and msg.split(": ", 1)[0].replace("_", "").isalpha():
            field, msg = msg.split(": ", 1)
        errors.append({"field": field, "message": msg, "project_id": None})
    return {"message": message, "errors": errors, "warnings": []}
