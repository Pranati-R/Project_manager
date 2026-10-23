import os
import shutil
import socket
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def find_nginx():
    """GW_NGINX_BIN, else an nginx on PATH or in /usr/sbin; None skips the e2e tests."""
    for candidate in (os.environ.get("GW_NGINX_BIN"), shutil.which("nginx"), "/usr/sbin/nginx"):
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeHelper:
    """Stands in for the root helper in API tests; records what it was asked to do."""

    mode = "fake"

    def __init__(self):
        self.applied = []
        self.next_apply = {"ok": True, "applied": True, "reloaded": True, "message": "applied and nginx reloaded"}
        self.scan_result = {"ok": True, "lint": [], "conflicts": []}
        self.restarted = []

    def apply(self, text):
        self.applied.append(text)
        return dict(self.next_apply)

    def test_full(self, text):
        return {"ok": True, "output": "test is successful"}

    def scan(self, text):
        return dict(self.scan_result)

    def restore(self, backup_id):
        return {"ok": True, "message": f"restored {backup_id}"}

    def backups(self):
        return {"ok": True, "backups": []}

    def status(self):
        return {"ok": True, "nginx_installed": True, "nginx_active": True, "nginx_version": "1.18.0"}

    def start(self):
        return {"ok": True, "message": "nginx started"}

    def logs(self, source, name="", lines=200):
        return {"ok": True, "lines": [f"{source} {name} line {i}" for i in range(3)]}

    def restart(self, target):
        self.restarted.append(target)
        return {"ok": True, "message": f"restarted {target}"}
