"""The save -> validate -> apply pipeline behind every dashboard change.

A change is only saved if the resulting config passes the cross-project checks, the
linter and an unprivileged `nginx -t` in a sandbox. With auto-apply on (the default) it
is then installed through the helper, which re-checks it, runs `nginx -t` on the whole
nginx config, reloads and rolls back on failure. If that apply fails, the saved state
and the live config differ ("drift") until the change is retried or reverted.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from . import nginx_helper, sandbox
from .audit import Audit
from .config import Config
from .generator import PRODUCTION_LOG_DIR, UnsafeValue, config_hash, render
from .models import Issue, Project, Settings, check_state
from .store import AppliedInfo, ApplyOutcome, State, Store


class NotFound(LookupError):
    pass


class Conflict(ValueError):
    pass


@dataclass
class Check:
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    nginx_ok: Optional[bool] = None
    nginx_output: str = ""
    config: str = ""

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return {"ok": self.ok, "errors": [i.model_dump() for i in self.errors],
                "warnings": [i.model_dump() for i in self.warnings],
                "nginx_ok": self.nginx_ok, "nginx_output": self.nginx_output}


class ValidationFailed(Exception):
    def __init__(self, check: Check):
        super().__init__("validation failed")
        self.check = check


class GatewayService:
    def __init__(self, cfg: Config, store: Store, helper, audit: Audit):
        self.cfg, self.store, self.helper, self.audit = cfg, store, helper, audit
        self.log_dir = getattr(helper, "log_dir", PRODUCTION_LOG_DIR) if helper.mode == "sandbox" else PRODUCTION_LOG_DIR
        self.lock = threading.RLock()

    # ── rendering and checks ────────────────────────────────────────────────
    def render(self, settings: Settings, projects: list[Project], log_dir: Optional[str] = None) -> str:
        return render(settings, projects, manager_port=self.cfg.manager_port, log_dir=log_dir or self.log_dir)

    def check(self, settings: Settings, projects: list[Project], *, run_nginx: bool = True) -> Check:
        errors, warnings = check_state(settings, projects, self.cfg.manager_port)
        result = Check(errors=errors, warnings=warnings)
        if result.errors:
            return result
        try:
            result.config = self.render(settings, projects)
        except UnsafeValue as e:
            result.errors.append(Issue(message=str(e)))
            return result
        for problem in nginx_helper.lint(result.config, self.log_dir):
            result.errors.append(Issue(message=f"internal check: {problem}"))
        if result.errors or not run_nginx:
            return result
        ok, output = sandbox.validate(self.cfg.resolved_nginx_bin(),
                                      lambda log_dir: self.render(settings, projects, log_dir))
        result.nginx_ok, result.nginx_output = ok, output
        if ok is False:
            result.errors.append(Issue(message="nginx -t rejected the generated config: " + _first_error(output)))
        return result

    # ── changes ─────────────────────────────────────────────────────────────
    def update(self, mutate: Callable[[State], Optional[str]], *, user: str, ip: str, action: str,
               target: Optional[str] = None) -> dict:
        with self.lock:
            new = self.store.load().model_copy(deep=True)
            detail = mutate(new)
            # Re-validate everything the mutation touched (model_copy skips validation)
            new = State.model_validate(new.model_dump())
            check = self.check(new.settings, new.projects)
            if not check.ok:
                raise ValidationFailed(check)
            self._scan_new_ports(check)
            self.store.save(new)
            self.audit.log(user, ip, action, target, detail)
            apply = self.apply(user=user, ip=ip) if new.settings.auto_apply else None
            return {"check": check.as_dict(), "apply": apply, "state": self.public_state()}

    def _scan_new_ports(self, check: Check) -> None:
        """Before a change adds a listening port, ask the helper whether anything else owns it."""
        live = self.read_live()
        if not nginx_helper.listen_ports(check.config) - (nginx_helper.listen_ports(live) if live else set()):
            return
        scan = self.helper.scan(check.config)
        problems = list(scan.get("lint", [])) + list(scan.get("conflicts", []))
        if not scan.get("ok", False) and not problems:
            problems = [scan.get("message", "the port conflict check failed")]
        if problems:
            check.errors += [Issue(message=p, field="port") for p in problems]
            raise ValidationFailed(check)

    def apply(self, *, user: str, ip: str) -> dict:
        with self.lock:
            state = self.store.load()
            check = self.check(state.settings, state.projects, run_nginx=False)
            if not check.ok:
                result = {"ok": False, "stage": "validate", "message": "the saved projects do not pass validation",
                          "errors": [i.message for i in check.errors]}
            else:
                result = self.helper.apply(check.config)
            state.last_apply = ApplyOutcome(
                ok=bool(result.get("ok")), at=time.time(), by=user, message=result.get("message", ""),
                stage=result.get("stage"), output=result.get("output"), errors=list(result.get("errors", [])))
            if result.get("ok"):
                state.applied = AppliedInfo(sha256=config_hash(check.config), at=time.time(), by=user,
                                            settings=state.settings, projects=state.projects)
            self.store.save(state, snapshot=False)
            self.audit.log(user, ip, "apply", None, ("ok: " if result.get("ok") else "failed: ") + result.get("message", ""))
            return result

    def revert_to_applied(self, *, user: str, ip: str) -> dict:
        with self.lock:
            state = self.store.load()
            if not state.applied:
                raise Conflict("nothing has been applied yet, so there is nothing to revert to")
            state.settings = state.applied.settings
            state.projects = state.applied.projects
            self.store.save(state)
            self.audit.log(user, ip, "revert", None, "back to the last applied state")
        return self.apply(user=user, ip=ip)

    # ── reporting ───────────────────────────────────────────────────────────
    def read_live(self) -> Optional[str]:
        try:
            return self.cfg.live_config.read_text(encoding="utf-8")
        except (FileNotFoundError, PermissionError):
            return None

    def drift(self, state: Optional[State] = None) -> dict:
        state = state or self.store.load()
        try:
            generated = self.render(state.settings, state.projects)
        except UnsafeValue:
            generated = ""
        live = self.read_live()
        return {"in_sync": live is not None and live == generated, "live_present": live is not None,
                "generated_sha256": config_hash(generated), "live_sha256": config_hash(live) if live else None}

    def public_state(self) -> dict:
        state = self.store.load()
        return {
            "settings": state.settings.model_dump(mode="json"),
            "projects": [p.model_dump(mode="json") for p in state.projects],
            "applied": {"at": state.applied.at, "by": state.applied.by, "sha256": state.applied.sha256}
            if state.applied else None,
            "last_apply": state.last_apply.model_dump(mode="json") if state.last_apply else None,
            "drift": self.drift(state),
        }


def _first_error(output: str) -> str:
    for line in output.splitlines():
        if "[emerg]" in line or "[error]" in line:
            return line.split("]", 1)[-1].strip()
    return output.strip().splitlines()[-1] if output.strip() else "unknown error"
