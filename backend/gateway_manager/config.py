"""Runtime paths and options, read from GWM_* environment variables.

The defaults are the production layout created by the .deb package; `nginx-gateway-ctl`
sets the same values explicitly. For local development point GWM_STATE_DIR somewhere
writable and set GWM_HELPER_MODE=sandbox (see README, "Developing").
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent.parent  # repo root / /opt/nginx-gateway/app


def _env(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


@dataclass(frozen=True)
class Config:
    state_dir: Path = Path("/var/lib/nginx-gateway")
    frontend_dir: Path = APP_ROOT / "frontend"
    seed_file: Path = APP_ROOT / "examples" / "seed-projects.json"
    manager_port: int = 8790
    # "sudo": the root helper through `sudo -n` (production)
    # "sandbox": a private nginx run as the current user (development, tests)
    helper_mode: str = "sudo"
    helper_path: str = "/usr/sbin/nginx-gateway-helper"
    nginx_bin: str = "/usr/sbin/nginx"
    live_config: Path = Path("/etc/nginx/nginx-gateway/gateway.conf")
    restart_targets: Path = Path("/etc/nginx-gateway/restart-targets.conf")
    sandbox_dir: Path = field(default=None)  # type: ignore[assignment]
    session_idle_seconds: int = 3600
    session_max_seconds: int = 12 * 3600

    def __post_init__(self):
        if self.sandbox_dir is None:
            object.__setattr__(self, "sandbox_dir", self.state_dir / "sandbox")
        if self.helper_mode == "sandbox":
            # The sandbox nginx keeps its "live" config inside the sandbox directory
            object.__setattr__(self, "live_config", self.sandbox_dir / "conf.d" / "gateway.conf")

    @property
    def state_file(self) -> Path:
        return self.state_dir / "state.json"

    @property
    def users_file(self) -> Path:
        return self.state_dir / "users.json"

    @property
    def audit_file(self) -> Path:
        return self.state_dir / "audit.log"

    @property
    def staging_file(self) -> Path:
        return self.state_dir / "staging" / "gateway.conf"

    @property
    def history_dir(self) -> Path:
        return self.state_dir / "history"

    def resolved_nginx_bin(self) -> str | None:
        """The nginx binary used for unprivileged validation, or None when there is none."""
        if os.path.isfile(self.nginx_bin) and os.access(self.nginx_bin, os.X_OK):
            return self.nginx_bin
        return shutil.which("nginx")


def load_config() -> Config:
    state_dir = Path(_env("GWM_STATE_DIR", "/var/lib/nginx-gateway"))
    sandbox = os.environ.get("GWM_SANDBOX_DIR", "").strip()
    return Config(
        state_dir=state_dir,
        frontend_dir=Path(_env("GWM_FRONTEND_DIR", str(APP_ROOT / "frontend"))),
        seed_file=Path(_env("GWM_SEED_FILE", str(APP_ROOT / "examples" / "seed-projects.json"))),
        manager_port=int(_env("GWM_MANAGER_PORT", "8790")),
        helper_mode=_env("GWM_HELPER_MODE", "sudo"),
        helper_path=_env("GWM_HELPER_PATH", "/usr/sbin/nginx-gateway-helper"),
        nginx_bin=_env("GWM_NGINX_BIN", "/usr/sbin/nginx"),
        live_config=Path(_env("GWM_LIVE_CONFIG", "/etc/nginx/nginx-gateway/gateway.conf")),
        restart_targets=Path(_env("GWM_RESTART_TARGETS", "/etc/nginx-gateway/restart-targets.conf")),
        sandbox_dir=Path(sandbox) if sandbox else state_dir / "sandbox",
    )
