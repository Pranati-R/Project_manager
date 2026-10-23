"""A private nginx instance (own prefix, pid, logs and temp dirs) run as the current user.

Used to validate a candidate config without privileges, by development mode
(GWM_HELPER_MODE=sandbox) and by the end-to-end tests. It never touches the system
nginx: everything lives under its own directory and it listens only on the ports the
gateway config names.
"""
from __future__ import annotations

import functools
import os
import re
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable

from . import nginx_helper

TEMP_DIRS = ("client", "proxy", "fastcgi", "uwsgi", "scgi")


@functools.lru_cache(maxsize=8)
def nginx_version(nginx_bin: str) -> tuple:
    r = subprocess.run([nginx_bin, "-v"], capture_output=True, text=True, timeout=10)
    m = re.search(r"nginx/(\d+)\.(\d+)\.(\d+)", r.stderr + r.stdout)
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


class NginxSandbox:
    def __init__(self, root: Path, nginx_bin: str, extra_http: str = ""):
        self.root = Path(root)
        self.nginx_bin = nginx_bin
        self.extra_http = extra_http

    conf = property(lambda self: self.root / "nginx.conf")
    conf_d = property(lambda self: self.root / "conf.d")
    logs = property(lambda self: self.root / "logs")
    pid_file = property(lambda self: self.root / "nginx.pid")

    def prepare(self) -> "NginxSandbox":
        for d in [self.conf_d, self.logs] + [self.root / "tmp" / t for t in TEMP_DIRS]:
            d.mkdir(parents=True, exist_ok=True)
        r = self.root
        temp_paths = "\n".join(f"    {t}_temp_path {r}/tmp/{t};" if t != "client" else
                               f"    client_body_temp_path {r}/tmp/client;" for t in TEMP_DIRS)
        self.conf.write_text(
            "# private nginx run by the gateway manager (sandbox); not the system nginx\n"
            "worker_processes 1;\n"
            f"pid {r}/nginx.pid;\n"
            f"error_log {r}/logs/error.log warn;\n"
            "events { worker_connections 512; }\n"
            "http {\n"
            f"{temp_paths}\n"
            f"    access_log {r}/logs/access.log;\n"
            "    default_type application/octet-stream;\n"
            "    types { text/html html; text/css css; application/javascript js; }\n"
            f"{self.extra_http}\n"
            f"    include {r}/conf.d/*.conf;\n"
            "}\n",
            encoding="utf-8",
        )
        return self

    def _cmd(self, *extra: str) -> list:
        cmd = [self.nginx_bin, "-p", str(self.root), "-c", str(self.conf)]
        if nginx_version(self.nginx_bin) >= (1, 19, 5):
            cmd += ["-e", str(self.logs / "error.log")]
        return cmd + list(extra)

    def _run(self, *extra: str, timeout: int = 30):
        r = subprocess.run(self._cmd(*extra), capture_output=True, text=True, timeout=timeout)
        # nginx < 1.19.5 always tries its compiled-in error log first; that alert is harmless here
        output = "\n".join(line for line in (r.stdout + r.stderr).splitlines()
                           if "could not open error log file" not in line)
        return r.returncode == 0, output.strip()

    def test(self):
        return self._run("-t")

    def dump(self):
        r = subprocess.run(self._cmd("-T"), capture_output=True, text=True, timeout=30)
        return r.returncode == 0, r.stdout, r.stderr

    def pid(self):
        try:
            pid = int(self.pid_file.read_text().strip())
            os.kill(pid, 0)
            return pid
        except (OSError, ValueError):
            return None

    def is_running(self) -> bool:
        return self.pid() is not None

    def start(self):
        ok, out = self._run()
        if ok:
            for _ in range(50):
                if self.is_running():
                    break
                time.sleep(0.05)
        return ok, out

    def reload(self):
        pid = self.pid()
        if pid is None:
            return False, "sandbox nginx is not running"
        os.kill(pid, signal.SIGHUP)
        time.sleep(0.3)  # let the new workers take over
        return True, ""

    def stop(self) -> None:
        pid = self.pid()
        if pid is None:
            return
        os.kill(pid, signal.SIGQUIT)
        for _ in range(100):
            if self.pid() is None:
                return
            time.sleep(0.05)
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass


class SandboxEnv(nginx_helper.Env):
    """nginx_helper's operations pointed at a sandbox instead of the system nginx."""

    bind_wait_seconds = 3.0

    def __init__(self, sandbox: NginxSandbox, staged_dir: Path, restart_targets: str = "/nonexistent"):
        self.sb = sandbox
        self.staged_dir = str(staged_dir)
        self.live_dir = str(sandbox.conf_d)
        self.stub = None
        self.backups = str(sandbox.root / "backups")
        self.lock_file = str(sandbox.root / "helper.lock")
        self.log_dir = str(sandbox.logs)
        self.restart_targets = restart_targets
        self.nginx = sandbox.nginx_bin

    def nginx_test(self):
        return self.sb.test()

    def nginx_dump(self):
        return self.sb.dump()

    def is_active(self) -> bool:
        return self.sb.is_running()

    def reload(self):
        return self.sb.reload()

    def start(self):
        return self.sb.start()

    def journal(self, unit: str, lines: int) -> list:
        return [f"(sandbox mode: no journal for {unit})"]


def validate(nginx_bin: str | None, render: Callable[[str], str]) -> tuple[bool | None, str]:
    """`nginx -t` for a config rendered with log paths inside a throwaway sandbox.

    Returns (None, reason) when no nginx binary is available to test with.
    """
    if not nginx_bin:
        return None, "nginx is not installed here, so the config was not tested with nginx -t"
    with tempfile.TemporaryDirectory(prefix="gwm-validate-") as d:
        sb = NginxSandbox(Path(d), nginx_bin).prepare()
        (sb.conf_d / "gateway.conf").write_text(render(str(sb.logs)), encoding="utf-8")
        return sb.test()
