"""Dashboard users, sessions, CSRF tokens and login throttling.

Passwords are hashed with scrypt (standard library). Sessions live in memory (a manager
restart means logging in again), are bound to the client address nginx reports, expire
after an hour idle or 12 hours in total, and each carries a CSRF token that every
state-changing request must send back in the X-CSRF-Token header.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .store import write_atomic

DEFAULT_USER = "a@g.com"
DEFAULT_PASSWORD = "123456"
USERNAME_RE = re.compile(r"^[a-z0-9._%+@-]{1,64}$")
MIN_PASSWORD = 6
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    b64 = lambda b: base64.b64encode(b).decode()
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${b64(salt)}${b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, digest = stored.split("$")
        if algo != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                                dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


class AuthError(ValueError):
    pass


def normalize_username(username: str) -> str:
    name = (username or "").strip().lower()
    if not USERNAME_RE.fullmatch(name):
        raise AuthError("use an email address or a name of letters, digits and . _ % + @ -")
    return name


def check_password_rules(password: str) -> None:
    if len(password or "") < MIN_PASSWORD:
        raise AuthError(f"the password needs at least {MIN_PASSWORD} characters")
    if len(password) > 128:
        raise AuthError("the password is too long")


class UserStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock = threading.RLock()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"users": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: dict) -> None:
        write_atomic(self.path, json.dumps(data, indent=2), mode=0o600)

    def list(self) -> list[dict]:
        with self.lock:
            return [{"username": u, "default_password": bool(v.get("default_password")),
                     "created": v.get("created")} for u, v in sorted(self._load()["users"].items())]

    def exists(self, username: str) -> bool:
        with self.lock:
            return normalize_username(username) in self._load()["users"]

    def verify(self, username: str, password: str) -> bool:
        try:
            name = normalize_username(username)
        except AuthError:
            return False
        with self.lock:
            entry = self._load()["users"].get(name)
        if entry is None:
            verify_password(password, hash_password("x"))  # same work for unknown users
            return False
        return verify_password(password, entry["hash"])

    def is_default_password(self, username: str) -> bool:
        with self.lock:
            entry = self._load()["users"].get(username, {})
        return bool(entry.get("default_password"))

    def set_password(self, username: str, password: str, *, create: bool = False, default: bool = False) -> None:
        name = normalize_username(username)
        check_password_rules(password)
        with self.lock:
            data = self._load()
            if name not in data["users"] and not create:
                raise AuthError(f"no user {name}")
            entry = data["users"].setdefault(name, {"created": int(time.time())})
            entry["hash"] = hash_password(password)
            entry["default_password"] = default
            self._save(data)

    def remove(self, username: str) -> None:
        name = normalize_username(username)
        with self.lock:
            data = self._load()
            if name not in data["users"]:
                raise AuthError(f"no user {name}")
            if len(data["users"]) == 1:
                raise AuthError("the last user cannot be removed")
            del data["users"][name]
            self._save(data)

    def ensure_default(self) -> bool:
        """Create the default login when there are no users yet. Returns True if created."""
        with self.lock:
            if self._load()["users"]:
                return False
            self.set_password(DEFAULT_USER, DEFAULT_PASSWORD, create=True, default=True)
            return True


@dataclass
class Session:
    username: str
    ip: str
    csrf: str
    created: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)


class SessionManager:
    def __init__(self, idle_seconds: int = 3600, max_seconds: int = 12 * 3600):
        self.idle, self.max = idle_seconds, max_seconds
        self._sessions: dict[str, Session] = {}
        self.lock = threading.Lock()

    @staticmethod
    def _key(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def create(self, username: str, ip: str) -> tuple[str, Session]:
        token = secrets.token_urlsafe(32)
        session = Session(username=username, ip=ip, csrf=secrets.token_urlsafe(24))
        with self.lock:
            self._prune()
            self._sessions[self._key(token)] = session
        return token, session

    def get(self, token: Optional[str], ip: str) -> Optional[Session]:
        if not token:
            return None
        now = time.time()
        with self.lock:
            session = self._sessions.get(self._key(token))
            if session is None:
                return None
            if now - session.last_seen > self.idle or now - session.created > self.max or session.ip != ip:
                self._sessions.pop(self._key(token), None)
                return None
            session.last_seen = now
            return session

    def revoke(self, token: Optional[str]) -> None:
        if token:
            with self.lock:
                self._sessions.pop(self._key(token), None)

    def revoke_user(self, username: str, keep_token: Optional[str] = None) -> None:
        keep = self._key(keep_token) if keep_token else None
        with self.lock:
            for key in [k for k, s in self._sessions.items() if s.username == username and k != keep]:
                del self._sessions[key]

    def _prune(self) -> None:
        now = time.time()
        for key in [k for k, s in self._sessions.items()
                    if now - s.last_seen > self.idle or now - s.created > self.max]:
            del self._sessions[key]


class LoginThrottle:
    """After 5 failures within 15 minutes a key (address or username) waits 5 minutes."""

    def __init__(self, max_failures: int = 5, window: int = 900, lockout: int = 300):
        self.max_failures, self.window, self.lockout = max_failures, window, lockout
        self._failures: dict[str, list[float]] = {}
        self.lock = threading.Lock()

    def retry_after(self, *keys: str) -> int:
        now = time.time()
        wait = 0
        with self.lock:
            for key in keys:
                recent = [t for t in self._failures.get(key, []) if now - t < self.window]
                self._failures[key] = recent
                if len(recent) >= self.max_failures:
                    wait = max(wait, int(recent[-1] + self.lockout - now))
        return max(wait, 0)

    def failure(self, *keys: str) -> None:
        with self.lock:
            for key in keys:
                self._failures.setdefault(key, []).append(time.time())

    def success(self, *keys: str) -> None:
        with self.lock:
            for key in keys:
                self._failures.pop(key, None)
