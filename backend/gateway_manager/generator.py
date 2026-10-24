"""Render the nginx config for the gateway from the saved settings and projects."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from . import __version__
from .models import ApiMode, Exposure, PathMode, Project, Settings

TEMPLATES = Path(__file__).resolve().parent / "templates"
PRODUCTION_LOG_DIR = "/var/log/nginx"

# Everything interpolated into the config must match this: no whitespace, quotes,
# semicolons, braces, $ or # can be smuggled in through a project or setting.
SAFE_TOKEN = re.compile(r"^[A-Za-z0-9._:/\[\]~-]+$")
SAFE_LANDING = re.compile(r"^[^\"\\$\r\n]*$")


class UnsafeValue(ValueError):
    pass


def tok(value) -> str:
    text = str(value)
    if not SAFE_TOKEN.fullmatch(text):
        raise UnsafeValue(f"refusing to render unsafe value {text!r} into the nginx config")
    return text


def listen_addr(value) -> str:
    text = str(value)
    return f"[{tok(text)}]" if ":" in text else tok(text)


_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES)),
    undefined=StrictUndefined,
    autoescape=False,
    keep_trailing_newline=True,
)
_env.filters["tok"] = tok
_env.filters["listen_addr"] = listen_addr


def _api_ctx(p: Project, prefix: str) -> dict | None:
    b = p.backend
    if not b:
        return None
    base = f"http://{b.hostport}"
    if b.api_mode == ApiMode.strip_prefix or (prefix == "" and b.api_mode == ApiMode.preserve):
        pass_exact, pass_slash = base + b.api_path, base + b.api_path + "/"
    elif b.api_mode == ApiMode.strip_all:
        pass_exact, pass_slash = base + "/", base + "/"
    else:  # preserve: the backend sees the full /prefix/api/... path
        pass_exact, pass_slash = base, base
    return {
        "location": prefix + b.api_path,
        "pass_exact": pass_exact,
        "pass_slash": pass_slash,
        "hostport": b.hostport,
        "buffering": b.buffering,
        "host_header": "$http_host" if p.pass_host_header else b.hostport,
    }


def project_ctx(p: Project) -> dict:
    prefix = p.route_prefix  # "" when served at the site root
    fe = p.frontend
    mode = PathMode.subpath if p.is_root else fe.path_mode
    if p.is_root or mode == PathMode.subpath:
        fe_pass = f"http://{fe.hostport}"
    else:
        fe_pass = f"http://{fe.hostport}/"
    return {
        "id": p.id,
        "name": p.name,
        "enabled": p.enabled,
        "prefix": prefix or "/",
        "redirect_bare": bool(prefix) and not p.app_owns_bare_prefix,
        "proxy_bare": p.app_owns_bare_prefix,
        "dedicated_port": p.dedicated_port,
        "fe_location": prefix + "/",
        "fe_pass": fe_pass,
        "fe_mode": mode.value,
        "fe_hostport": fe.hostport,
        "fe_host_header": "$http_host" if p.pass_host_header else fe.hostport,
        "api": _api_ctx(p, prefix),
        "read_timeout": p.read_timeout,
        "max_body_size": p.max_body_size,
    }


def _landing_html(projects: list[Project]) -> str:
    links = []
    for p in sorted(projects, key=lambda x: x.name.lower()):
        if p.enabled and p.exposure == Exposure.path and p.prefix != "/":
            links.append(f"<a href='{p.prefix}/'>{p.name} <small>{p.prefix}/</small></a>")
    if not links:
        links.append("<p>No projects yet. Add one in the dashboard.</p>")
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'><title>Gateway</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:640px;margin:40px auto;padding:0 16px;"
        "color:#1f2933;background:#fff}h1{font-size:22px}a{display:flex;justify-content:space-between;"
        "padding:12px 14px;margin:8px 0;border:1px solid #d9e2ec;border-radius:8px;text-decoration:none;"
        "color:#102a43}a:hover{background:#f0f4f8}small{color:#627d98}"
        "@media (prefers-color-scheme:dark){body{background:#111827;color:#e5e7eb}"
        "a{color:#e5e7eb;border-color:#374151}a:hover{background:#1f2937}small{color:#9ca3af}}</style>"
        "</head><body><h1>Projects on this gateway</h1>" + "".join(links) + "</body></html>"
    )
    if not SAFE_LANDING.fullmatch(html):
        raise UnsafeValue("landing page contains characters that cannot go into an nginx string")
    return html


def render(settings: Settings, projects: list[Project], *, manager_port: int,
           log_dir: str = PRODUCTION_LOG_DIR) -> str:
    """The complete gateway.conf (included inside nginx's http {} block)."""
    path_projects, port_projects, root_project = [], [], None
    for p in projects:
        if p.exposure == Exposure.port:
            if p.enabled:
                port_projects.append(project_ctx(p))
        elif p.prefix == "/":
            if p.enabled:
                root_project = project_ctx(p)
        else:
            path_projects.append(project_ctx(p))
    path_projects.sort(key=lambda c: (-len(c["prefix"]), c["id"]))
    port_projects.sort(key=lambda c: c["dedicated_port"])

    landing = None
    if settings.landing_page and root_project is None:
        landing = _landing_html(projects)

    text = _env.get_template("gateway.conf.j2").render(
        settings=settings,
        path_projects=path_projects,
        port_projects=port_projects,
        root_project=root_project,
        landing_html=landing,
        manager_port=manager_port,
        log_dir=log_dir.rstrip("/"),
        version=__version__,
    )
    # Collapse the blank lines left behind by template control blocks
    text = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text)
    return text.strip("\n") + "\n"


def render_project_snippet(project: Project) -> str:
    """The nginx locations for one project, for the editor's live preview."""
    module = _env.get_template("gateway.conf.j2").make_module(vars={
        "settings": Settings(), "path_projects": [], "port_projects": [], "root_project": None,
        "landing_html": None, "manager_port": 8790, "log_dir": PRODUCTION_LOG_DIR, "version": __version__,
    })
    text = str(module.project_locations(project_ctx(project)))
    text = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text)
    return "\n".join(line[4:] if line.startswith("    ") else line for line in text.strip("\n").splitlines()) + "\n"


def config_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
