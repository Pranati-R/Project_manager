"""Append-only record of who changed what (JSON lines, rotated at 5 MB)."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from .nginx_helper import tail_lines

MAX_BYTES = 5 * 1024 * 1024


class Audit:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock = threading.Lock()

    def log(self, user: str, ip: str, action: str, target: str | None = None, detail: str | None = None) -> None:
        entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "user": user, "ip": ip,
                 "action": action}
        if target:
            entry["target"] = target
        if detail:
            entry["detail"] = detail[:500]
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists() and self.path.stat().st_size > MAX_BYTES:
                os.replace(self.path, self.path.with_suffix(".log.1"))
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

    def tail(self, lines: int = 200) -> list[str]:
        try:
            return tail_lines(str(self.path), lines)
        except FileNotFoundError:
            return []
