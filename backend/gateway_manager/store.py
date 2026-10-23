"""Persistent state: settings, projects and what was last applied, in one JSON file.

Writes are atomic (temp file, fsync, rename) and the previous version of the file is
kept in history/ (last 20), so a bad edit can always be recovered.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .models import Project, Settings

KEEP_HISTORY = 20


class AppliedInfo(BaseModel):
    sha256: str
    at: float
    by: str
    settings: Settings
    projects: list[Project]


class ApplyOutcome(BaseModel):
    ok: bool
    at: float
    by: str
    message: str = ""
    stage: Optional[str] = None
    output: Optional[str] = None
    errors: list[str] = Field(default_factory=list)


class State(BaseModel):
    schema_version: int = 1
    settings: Settings = Field(default_factory=Settings)
    projects: list[Project] = Field(default_factory=list)
    applied: Optional[AppliedInfo] = None
    last_apply: Optional[ApplyOutcome] = None

    def project(self, project_id: str) -> Optional[Project]:
        return next((p for p in self.projects if p.id == project_id), None)


def write_atomic(path: Path, data: str, mode: int = 0o640) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


class Store:
    def __init__(self, path: Path, history_dir: Path):
        self.path = Path(path)
        self.history_dir = Path(history_dir)
        self.lock = threading.RLock()

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> State:
        with self.lock:
            if not self.path.exists():
                return State()
            return State.model_validate_json(self.path.read_text(encoding="utf-8"))

    def save(self, state: State, snapshot: bool = True) -> None:
        with self.lock:
            if snapshot and self.path.exists():
                self.history_dir.mkdir(parents=True, exist_ok=True)
                stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime()) + f"{time.time() % 1:.3f}"[1:]
                write_atomic(self.history_dir / f"state-{stamp}.json", self.path.read_text(encoding="utf-8"))
                old = sorted(self.history_dir.glob("state-*.json"))
                for f in old[:-KEEP_HISTORY]:
                    f.unlink(missing_ok=True)
            write_atomic(self.path, state.model_dump_json(indent=2))

    def seed(self, seed_file: Optional[Path], **settings_overrides) -> State:
        """Create the first state: optional example projects plus port overrides."""
        state = State()
        if seed_file and Path(seed_file).is_file():
            data = json.loads(Path(seed_file).read_text(encoding="utf-8"))
            state = State(settings=Settings(**data.get("settings", {})),
                          projects=[Project(**p) for p in data.get("projects", [])])
        if settings_overrides:
            state.settings = Settings(**{**state.settings.model_dump(), **settings_overrides})
        self.save(state, snapshot=False)
        return state
