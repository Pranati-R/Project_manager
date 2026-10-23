"""How the manager reaches the privileged helper.

Production: `sudo -n /usr/sbin/nginx-gateway-helper <command>`, with the config handed over
through the staging file. Development: the same operations run in-process against a
sandbox nginx owned by the current user. Every call returns the helper's JSON result
(a dict with "ok"); nothing raises for an nginx-level failure.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from . import nginx_helper
from .config import Config


def write_staged(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".gateway.", suffix=".tmp", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, 0o640)
    os.replace(tmp, path)


class SudoHelper:
    mode = "sudo"
    STATUS_TTL = 20  # seconds; the dashboard polls, and every sudo call is a line in auth.log

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.cmd = ["sudo", "-n", cfg.helper_path]
        self._status = (0.0, None)

    def _changing(self, *args: str) -> dict:
        self._status = (0.0, None)
        return self._call(*args)

    def _call(self, *args: str, timeout: int = 200) -> dict:
        try:
            r = subprocess.run(self.cmd + list(args), capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError:
            return {"ok": False, "stage": "helper", "message": "sudo is not installed"}
        except subprocess.TimeoutExpired:
            return {"ok": False, "stage": "helper", "message": f"the helper did not answer within {timeout}s"}
        try:
            return json.loads(r.stdout.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError):
            message = (r.stderr or r.stdout).strip() or f"exit code {r.returncode}"
            if "password is required" in message or "not allowed" in message:
                message = ("the sudo rule for nginx-gw is missing (/etc/sudoers.d/nginx-gateway); "
                           "reinstall the package: " + message)
            return {"ok": False, "stage": "helper", "message": message}

    def apply(self, text: str) -> dict:
        write_staged(self.cfg.staging_file, text)
        return self._changing("apply")

    def test_full(self, text: str) -> dict:
        write_staged(self.cfg.staging_file, text)
        return self._call("test-full")

    def scan(self, text: str) -> dict:
        write_staged(self.cfg.staging_file, text)
        return self._call("scan")

    def restore(self, backup_id: str) -> dict:
        return self._changing("restore", backup_id)

    def backups(self) -> dict:
        return self._call("backups")

    def status(self) -> dict:
        at, cached = self._status
        if cached is not None and time.monotonic() - at < self.STATUS_TTL:
            return cached
        result = self._call("status", timeout=30)
        self._status = (time.monotonic(), result)
        return result

    def start(self) -> dict:
        return self._changing("start")

    def logs(self, source: str, name: str = "", lines: int = 200) -> dict:
        return self._call("logs", source, "--name", name, "--lines", str(int(lines)), timeout=30)

    def restart(self, target: str) -> dict:
        return self._call("restart", target)


class SandboxHelper:
    """Development stand-in: a private nginx on the configured ports, run as you."""

    mode = "sandbox"

    def __init__(self, cfg: Config, extra_http: str = ""):
        from .sandbox import NginxSandbox, SandboxEnv

        self.cfg = cfg
        nginx_bin = cfg.resolved_nginx_bin()
        if not nginx_bin:
            raise RuntimeError("sandbox mode needs an nginx binary (set GWM_NGINX_BIN)")
        self.sandbox = NginxSandbox(cfg.sandbox_dir, nginx_bin, extra_http).prepare()
        self.env = SandboxEnv(self.sandbox, cfg.staging_file.parent, str(cfg.restart_targets))

    @property
    def log_dir(self) -> str:
        return str(self.sandbox.logs)

    def _guard(self, fn, *args) -> dict:
        try:
            return fn(*args)
        except nginx_helper.HelperFailure as e:
            return e.result

    def apply(self, text: str) -> dict:
        write_staged(self.cfg.staging_file, text)
        with nginx_helper.Lock(self.env.lock_file):
            result = self._guard(nginx_helper.apply_config, self.env, nginx_helper.read_staged(self.env))
        if result.get("ok") and result.get("nginx_active") is False:
            ok, out = self.sandbox.start()  # development convenience: run the sandbox nginx
            result.update(reloaded=ok, nginx_active=ok,
                          message="applied; sandbox nginx started" if ok else f"sandbox nginx failed: {out}")
        return result

    def test_full(self, text: str) -> dict:
        write_staged(self.cfg.staging_file, text)
        return self._guard(nginx_helper.test_full, self.env, nginx_helper.read_staged(self.env))

    def scan(self, text: str) -> dict:
        errors = nginx_helper.lint(text, self.env.log_dir)
        return {"ok": not errors, "lint": errors, "conflicts": [] if errors else nginx_helper.conflicts(self.env, text)}

    def restore(self, backup_id: str) -> dict:
        return self._guard(lambda: nginx_helper.apply_config(
            self.env, nginx_helper.read_backup(self.env, backup_id), f"backup {backup_id}"))

    def backups(self) -> dict:
        return {"ok": True, "backups": nginx_helper.list_backups(self.env)}

    def status(self) -> dict:
        return nginx_helper.status(self.env)

    def start(self) -> dict:
        return self._guard(nginx_helper.start_nginx, self.env)

    def logs(self, source: str, name: str = "", lines: int = 200) -> dict:
        return self._guard(nginx_helper.logs, self.env, source, name, lines)

    def restart(self, target: str) -> dict:
        return self._guard(nginx_helper.restart_target, self.env, target)

    def stop(self) -> None:
        self.sandbox.stop()


def make_helper(cfg: Config):
    return SandboxHelper(cfg) if cfg.helper_mode == "sandbox" else SudoHelper(cfg)
