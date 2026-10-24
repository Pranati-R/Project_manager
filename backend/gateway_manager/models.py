"""Projects and gateway settings, with the validation that keeps the nginx config safe.

Every value that reaches the generated nginx config is constrained here to a narrow
character set (slugs, paths, IP literals, integers). The generator re-checks each value
before rendering, and the root helper lints the result, so a value that slipped past one
layer is still stopped by the next.
"""
from __future__ import annotations

import ipaddress
import re
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")
PREFIX_RE = re.compile(r"^(?:/[a-z0-9][a-z0-9._-]{0,62}){1,4}$")
API_PATH_RE = re.compile(r"^(?:/[A-Za-z0-9][A-Za-z0-9._-]{0,62}){1,4}$")
HEALTH_PATH_RE = re.compile(r"^(?:/[A-Za-z0-9._~-]{0,62}){1,8}$")
NAME_RE = re.compile(r"^[A-Za-z0-9 ._()-]{1,60}$")
SIZE_RE = re.compile(r"^[0-9]{1,5}[kmg]?$")
APP_DIR_RE = re.compile(r"^/[A-Za-z0-9._/ -]{0,200}$")

RESERVED_PREFIXES = ("/gateway-health",)
FORBIDDEN_PORTS = (80, 443)
MIN_LISTEN_PORT = 1024


class PathMode(str, Enum):
    subpath = "subpath"  # upstream receives /prefix/... (app built/served with that base)
    strip = "strip"  # upstream receives /... (static server for a dist built with the base)
    rewrite = "rewrite"  # strip + best-effort sub_filter rewriting (simple non-SPA pages)


class ApiMode(str, Enum):
    strip_prefix = "strip_prefix"  # /prefix/api/x -> /api/x
    strip_all = "strip_all"  # /prefix/api/x -> /x
    preserve = "preserve"  # /prefix/api/x -> /prefix/api/x


class Exposure(str, Enum):
    path = "path"  # a URL prefix on the gateway port
    port = "port"  # the site root on its own gateway port (apps that need "/")


class AppKind(str, Enum):
    vite_dev = "vite_dev"
    vite_preview = "vite_preview"
    static_dist = "static_dist"
    backend_served = "backend_served"
    nextjs = "nextjs"
    prebuilt = "prebuilt"
    other = "other"


class Runtime(str, Enum):
    systemd = "systemd"
    docker = "docker"
    tmux = "tmux"
    other = "other"


def normalize_ip(value: str) -> str:
    value = value.strip().strip("[]")
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        raise ValueError("must be an IP address such as 127.0.0.1 or ::1 (host names are not allowed)")


class Upstream(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = "127.0.0.1"
    port: int = Field(ge=1, le=65535)

    @field_validator("host")
    @classmethod
    def _host(cls, v: str) -> str:
        return normalize_ip(v)

    @property
    def hostport(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{host}:{self.port}"


class Frontend(Upstream):
    path_mode: PathMode = PathMode.subpath


class Backend(Upstream):
    api_path: str = "/api"
    api_mode: ApiMode = ApiMode.strip_prefix
    buffering: bool = False  # off suits streaming responses (SSE, token streams)

    @field_validator("api_path")
    @classmethod
    def _api_path(cls, v: str) -> str:
        v = v.strip()
        if len(v) > 1:
            v = v.rstrip("/")
        if not API_PATH_RE.fullmatch(v):
            raise ValueError("must look like /api or /api/v1 (letters, digits, . _ -)")
        return v


class Project(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    enabled: bool = True
    exposure: Exposure = Exposure.path
    prefix: Optional[str] = None
    dedicated_port: Optional[int] = None
    frontend: Frontend
    backend: Optional[Backend] = None
    pass_host_header: bool = True
    read_timeout: int = Field(default=3600, ge=5, le=86400)
    max_body_size: Optional[str] = None
    health_path: Optional[str] = None
    app_kind: AppKind = AppKind.other
    runtime: Runtime = Runtime.other
    restart_target: Optional[str] = None
    app_dir: Optional[str] = None
    notes: str = Field(default="", max_length=500)

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not SLUG_RE.fullmatch(v):
            raise ValueError("lowercase letters, digits and dashes; 1-40 characters; no dash at the ends")
        return v

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = " ".join(v.split())
        if not NAME_RE.fullmatch(v):
            raise ValueError("1-60 characters: letters, digits, spaces and . _ ( ) -")
        return v

    @field_validator("prefix")
    @classmethod
    def _prefix(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if v == "":
            return None
        if v != "/":
            v = v.rstrip("/")
            if not PREFIX_RE.fullmatch(v):
                raise ValueError("must look like /my-app (lowercase letters, digits, . _ -; up to 4 segments) or /")
        return v

    @field_validator("max_body_size")
    @classmethod
    def _size(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None
        v = v.strip().lower()
        if not SIZE_RE.fullmatch(v):
            raise ValueError("a size such as 10m, 512k or 1g")
        return v

    @field_validator("health_path")
    @classmethod
    def _health(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None
        v = v.strip()
        if not HEALTH_PATH_RE.fullmatch(v):
            raise ValueError("a path such as /health (no query string)")
        return v

    @field_validator("restart_target")
    @classmethod
    def _target(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None
        if not SLUG_RE.fullmatch(v.strip()):
            raise ValueError("an id from /etc/nginx-gateway/restart-targets.conf")
        return v.strip()

    @field_validator("app_dir")
    @classmethod
    def _app_dir(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None
        v = v.strip()
        if not APP_DIR_RE.fullmatch(v) or "/../" in v + "/":
            raise ValueError("an absolute folder path such as /home/me/prajna")
        return v

    @model_validator(mode="after")
    def _exposure(self) -> "Project":
        if self.exposure == Exposure.path:
            if not self.prefix:
                raise ValueError("prefix: required when the project is served on a URL path")
            if self.prefix in RESERVED_PREFIXES or any(
                self.prefix.startswith(r + "/") for r in RESERVED_PREFIXES
            ):
                raise ValueError(f"prefix: {self.prefix} is reserved by the gateway")
            self.dedicated_port = None
        else:
            if self.dedicated_port is None:
                raise ValueError("dedicated_port: required when the project gets its own port")
            if not (MIN_LISTEN_PORT <= self.dedicated_port <= 65535):
                raise ValueError(f"dedicated_port: must be between {MIN_LISTEN_PORT} and 65535")
            self.prefix = None
        if self.is_root and self.frontend.path_mode != PathMode.subpath:
            # At the site root there is no prefix to strip or rewrite
            self.frontend.path_mode = PathMode.subpath
        return self

    @property
    def is_root(self) -> bool:
        """Served at "/" (the root project on the gateway port, or a dedicated port)."""
        return self.exposure == Exposure.port or self.prefix == "/"

    @property
    def route_prefix(self) -> str:
        """The prefix used to build locations: "" when served at the root."""
        return "" if self.is_root else (self.prefix or "")

    @property
    def app_owns_bare_prefix(self) -> bool:
        """Next.js with basePath answers "/x" itself and redirects "/x/" to "/x", so the gateway
        must forward "/x" instead of redirecting it to "/x/" (that would loop)."""
        return (bool(self.route_prefix) and self.app_kind == AppKind.nextjs
                and self.frontend.path_mode == PathMode.subpath)


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gateway_port: int = Field(default=8280, ge=MIN_LISTEN_PORT, le=65535)
    admin_mode: Literal["dedicated_port", "localhost_only"] = "dedicated_port"
    admin_port: int = Field(default=8281, ge=MIN_LISTEN_PORT, le=65535)
    listen_addresses: list[str] = Field(default_factory=lambda: ["0.0.0.0"], min_length=1, max_length=8)
    allowed_cidrs: list[str] = Field(
        default_factory=lambda: ["100.64.0.0/10", "fd7a:115c:a1e0::/48", "127.0.0.1/32", "::1/128"],
        min_length=1,
        max_length=64,
    )
    client_max_body_size: str = "100m"
    landing_page: bool = True
    auto_apply: bool = True

    @field_validator("listen_addresses")
    @classmethod
    def _listen(cls, v: list[str]) -> list[str]:
        out = []
        for item in v:
            ip = normalize_ip(item)
            if ip not in out:
                out.append(ip)
        return out

    @field_validator("allowed_cidrs")
    @classmethod
    def _cidrs(cls, v: list[str]) -> list[str]:
        out = []
        for item in v:
            try:
                net = str(ipaddress.ip_network(item.strip(), strict=False))
            except ValueError:
                raise ValueError(f"{item!r} is not an IP network such as 100.64.0.0/10")
            if net not in out:
                out.append(net)
        return out

    @field_validator("client_max_body_size")
    @classmethod
    def _size(cls, v: str) -> str:
        v = v.strip().lower()
        if not SIZE_RE.fullmatch(v):
            raise ValueError("a size such as 100m")
        return v

    @model_validator(mode="after")
    def _ports(self) -> "Settings":
        for name in ("gateway_port", "admin_port"):
            if getattr(self, name) in FORBIDDEN_PORTS:
                raise ValueError(f"{name}: ports 80 and 443 belong to Apache/other web servers")
        if self.admin_mode == "dedicated_port" and self.admin_port == self.gateway_port:
            raise ValueError("admin_port: must differ from gateway_port")
        return self


class Issue(BaseModel):
    message: str
    field: Optional[str] = None
    project_id: Optional[str] = None


def check_state(settings: Settings, projects: list[Project], manager_port: int) -> tuple[list[Issue], list[Issue]]:
    """Cross-project rules that a single model cannot see. Returns (errors, warnings)."""
    errors: list[Issue] = []
    warnings: list[Issue] = []

    listeners = {settings.gateway_port: "the gateway port"}
    if settings.admin_mode == "dedicated_port":
        listeners[settings.admin_port] = "the admin port"
    if manager_port in listeners:
        errors.append(Issue(message=f"port {manager_port} is used by the manager backend", field="gateway_port"))
    reserved = {**listeners, manager_port: "the manager backend", 80: "Apache (port 80)", 443: "port 443"}

    # Dedicated ports first: upstream checks below need the complete set
    dedicated: dict[int, str] = {}
    for p in projects:
        if p.exposure != Exposure.port:
            continue
        port = p.dedicated_port
        if port in reserved:
            errors.append(Issue(message=f"dedicated port {port} is {reserved[port]}",
                                field="dedicated_port", project_id=p.id))
        elif port in dedicated:
            errors.append(Issue(message=f"dedicated port {port} is already used by {dedicated[port]!r}",
                                field="dedicated_port", project_id=p.id))
        else:
            dedicated[port] = p.id

    seen_ids: set[str] = set()
    prefixes: dict[str, str] = {}
    upstream_ports: dict[int, str] = {}
    for p in projects:
        if p.id in seen_ids:
            errors.append(Issue(message=f"duplicate project id {p.id!r}", field="id", project_id=p.id))
        seen_ids.add(p.id)

        if p.exposure == Exposure.path:
            if p.prefix in prefixes:
                errors.append(Issue(message=f"prefix {p.prefix} is already used by {prefixes[p.prefix]!r}",
                                    field="prefix", project_id=p.id))
            else:
                prefixes[p.prefix] = p.id

        parts = [("frontend", p.frontend)] + ([("backend", p.backend)] if p.backend else [])
        for part, up in parts:
            local = up.host in ("127.0.0.1", "::1")
            if local and up.port in reserved:
                errors.append(Issue(
                    message=f"{part} port {up.port} is {reserved[up.port]}; the gateway would proxy to itself",
                    field=f"{part}.port", project_id=p.id))
            elif local and up.port in dedicated:
                errors.append(Issue(message=f"{part} port {up.port} is the gateway port of {dedicated[up.port]!r}",
                                    field=f"{part}.port", project_id=p.id))
            other = upstream_ports.setdefault(up.port, p.id)
            if other != p.id:
                warnings.append(Issue(message=f"{part} port {up.port} is also used by {other!r}",
                                      field=f"{part}.port", project_id=p.id))

    roots = [p.id for p in projects if p.exposure == Exposure.path and p.prefix == "/"]
    if len(roots) > 1:
        errors.append(Issue(message="only one project can use the prefix / (" + ", ".join(roots) + ")",
                            field="prefix", project_id=roots[1]))

    plist = sorted(x for x in prefixes if x != "/")
    for a in plist:
        for b in plist:
            if b.startswith(a + "/"):
                warnings.append(Issue(message=f"{b} is nested inside {a}; the longer prefix wins",
                                      field="prefix", project_id=prefixes[b]))
    for p in projects:
        if p.backend and p.exposure == Exposure.path and p.prefix not in (None, "/"):
            api = p.prefix + p.backend.api_path
            for other in plist:
                if other == api or other.startswith(api + "/"):
                    warnings.append(Issue(message=f"{other} overlaps the API path of {p.id!r}",
                                          field="prefix", project_id=prefixes[other]))
    return errors, warnings
