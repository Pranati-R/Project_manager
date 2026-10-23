"""Read-only check of a Vite project folder for subpath (gateway) readiness.

    nginx-gateway-ctl vite-check ~/prajna --prefix /prajna/

It only reads files: package.json, vite.config.* and the source tree. It reports what
would break under the prefix and prints the commands and one-line changes to fix it.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

SOURCE_EXT = {".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".mjs"}
SKIP_DIRS = {"node_modules", "dist", "build", ".git", ".next", "coverage", ".vite", ".turbo"}
MAX_FILES = 3000
MAX_BYTES = 512 * 1024
CONFIG_NAMES = [f"vite.config.{e}" for e in ("ts", "js", "mjs", "cjs", "mts")]

ROUTER_RE = re.compile(r"<BrowserRouter\b([^>]*)>|createBrowserRouter\s*\(|createWebHistory\s*\(\s*\)")
HASH_ROUTER_RE = re.compile(r"<HashRouter\b|createHashRouter\s*\(|createWebHashHistory\s*\(")
ABS_URL_RE = re.compile(
    r"""(?P<call>fetch|axios(?:\.\w+)?|new\s+EventSource|new\s+WebSocket|baseURL\s*:)\s*\(?\s*[`'"](?P<url>/(?!/)[^`'"\s]*)""")
API_ENV_RE = re.compile(r"import\.meta\.env\.(VITE_[A-Z0-9_]*(?:API|BACKEND|SERVER)[A-Z0-9_]*)")
API_DEFAULT_RE = re.compile(r"""(?:return|=|:|\?\?|\|\|)\s*[`'"](?P<url>/api(?:/[^`'"\s]*)?)[`'"]""")
LOCAL_URL_RE = re.compile(r"""[`'"](?P<url>https?://(?:127\.0\.0\.1|localhost|0\.0\.0\.0)(?::\d+)?)[^`'"]*[`'"]""")
ASSET_RE = re.compile(
    r"""(?:src|href)\s*=\s*\{?\s*["'](?P<url>/(?!/)[^"'\s]+\.(?:svg|png|jpe?g|gif|webp|ico|mp3|mp4|json|woff2?))["']""")
OPEN_HOST_RE = re.compile(r"""\bhost\s*:\s*(?:true\b|['"](?:0\.0\.0\.0|::)['"])|(?:\|\||\?\?)\s*['"](?:0\.0\.0\.0|::)['"]""")


@dataclass
class Finding:
    level: str  # ok | warn | error | info
    message: str
    where: str = ""
    fix: str = ""


@dataclass
class Report:
    project_dir: str
    prefix: str
    is_vite: bool = False
    base_in_config: str | None = None
    findings: list[Finding] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)


def _read(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _sources(root: Path):
    count = 0
    stack = [root]
    while stack and count < MAX_FILES:
        d = stack.pop()
        try:
            entries = sorted(d.iterdir())
        except OSError:
            continue
        for e in entries:
            if e.is_dir():
                if e.name not in SKIP_DIRS and not e.name.startswith("."):
                    stack.append(e)
            elif (e.suffix in SOURCE_EXT and not e.name.startswith(("vite.config", "next.config"))
                  and ".test." not in e.name):
                count += 1
                yield e


def _line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _check_config(rep: Report, cfg_path: Path, prefix: str) -> None:
    cfg = _read(cfg_path)
    name = cfg_path.name
    m = re.search(r"\bbase\s*:\s*([^,\n}]+)", cfg)
    if m:
        rep.base_in_config = m.group(1).strip()
        value = rep.base_in_config.strip("'\"`")
        if value == "./":
            rep.findings.append(Finding(
                "info", "base './' (relative): a production build works under any path when the app uses a hash "
                        f"router or a single page, but the dev server ignores it, so start dev with --base {prefix}", name))
        elif value in ("/", "") and prefix != "/":
            rep.findings.append(Finding(
                "warn", f"vite.config sets base to {rep.base_in_config}; --base on the command line overrides it, "
                        "or read it from the environment", name, "base: process.env.VITE_BASE_PATH ?? '/',"))
        elif "process.env" in value or "env." in value:
            rep.findings.append(Finding("ok", f"vite.config reads base from the environment ({rep.base_in_config})", name))
        elif value.rstrip("/") + "/" == prefix:
            rep.findings.append(Finding("ok", f"vite.config already uses base {prefix}", name))
    else:
        rep.findings.append(Finding("info", f"vite.config has no base setting: pass --base {prefix} when starting/"
                                            "building (no file change needed)", name))
    if re.search(r"\bhmr\s*:\s*\{[^}]*\bport\s*:", cfg, re.S):
        rep.findings.append(Finding("warn", "server.hmr.port is set: hot reload would bypass the gateway; remove it "
                                            "(or set hmr.clientPort to the gateway port)", name))
    if OPEN_HOST_RE.search(cfg):
        rep.findings.append(Finding("warn", "the dev/preview server listens on all interfaces (0.0.0.0 or ::) by "
                                            "default, so it is reachable without the gateway", name,
                                    "start it with --host 127.0.0.1"))
    if re.search(r"\bproxy\s*:\s*\{", cfg):
        rep.findings.append(Finding("info", "server.proxy is only used when you open the dev server directly; through "
                                            "the gateway, API calls under the prefix go straight to the backend", name))
    if "define" in cfg and LOCAL_URL_RE.search(cfg):
        url = LOCAL_URL_RE.search(cfg).group("url")
        rep.findings.append(Finding(
            "warn", f"vite.config can bake {url} into the app as the API address; a browser on another device would "
                    "call its own computer", name, "set the app's API base variable to a path under the prefix"))


def analyze(project_dir: str | Path, prefix: str = "/") -> Report:
    root = Path(project_dir).expanduser().resolve()
    prefix = "/" + prefix.strip("/") + "/" if prefix.strip("/") else "/"
    rep = Report(project_dir=str(root), prefix=prefix)
    if not root.is_dir():
        rep.findings.append(Finding("error", f"{root} is not a folder"))
        return rep

    pkg = {}
    pkg_text = _read(root / "package.json")
    if pkg_text:
        try:
            pkg = json.loads(pkg_text)
        except json.JSONDecodeError:
            rep.findings.append(Finding("warn", "package.json is not valid JSON", "package.json"))
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    cfg_path = next((root / n for n in CONFIG_NAMES if (root / n).exists()), None)
    rep.is_vite = "vite" in deps or cfg_path is not None
    if "next" in deps:
        rep.findings.append(Finding(
            "info", "this is a Next.js app: set basePath in next.config (e.g. basePath: process.env.NEXT_BASE_PATH) "
                    "and rebuild, or give it its own gateway port", "package.json"))
    elif not rep.is_vite:
        rep.findings.append(Finding("warn", "this does not look like a Vite project (no vite dependency or vite.config)"))
    if cfg_path:
        _check_config(rep, cfg_path, prefix)

    for name, script in pkg.get("scripts", {}).items():
        if re.search(r"\bvite\b", script) and re.search(r"--host(\s+(0\.0\.0\.0|::))?(\s|$)", script):
            rep.findings.append(Finding("warn", f"script '{name}' exposes Vite on all interfaces ({script})",
                                        "package.json", "use --host 127.0.0.1"))

    router_hits, url_hits, asset_hits, hash_router = [], [], [], []
    api_envs: dict[str, str] = {}
    api_defaults, local_urls = [], []
    for path in _sources(root):
        text = _read(path)
        rel = path.relative_to(root).as_posix()
        for m in ROUTER_RE.finditer(text):
            snippet = text[m.start():m.start() + 300]
            if m.group(0).startswith("<BrowserRouter"):
                if "basename" not in (m.group(1) or ""):
                    router_hits.append((rel, _line(text, m.start()), "<BrowserRouter> without basename"))
            elif m.group(0).startswith("createBrowserRouter"):
                if "basename" not in snippet:
                    router_hits.append((rel, _line(text, m.start()), "createBrowserRouter(...) without a basename option"))
            else:
                router_hits.append((rel, _line(text, m.start()), "createWebHistory() without import.meta.env.BASE_URL"))
        if HASH_ROUTER_RE.search(text):
            hash_router.append(rel)
        for env_name in API_ENV_RE.findall(text):
            api_envs.setdefault(env_name, rel)
        for m in ABS_URL_RE.finditer(text):
            url_hits.append((rel, _line(text, m.start()), f"{m.group('call').strip()} '{m.group('url')}'"))
        for m in API_DEFAULT_RE.finditer(text):
            api_defaults.append((rel, _line(text, m.start()), m.group("url")))
        for m in LOCAL_URL_RE.finditer(text):
            local_urls.append((rel, _line(text, m.start()), m.group("url")))
        for m in ASSET_RE.finditer(text):
            asset_hits.append((rel, _line(text, m.start()), m.group("url")))

    if hash_router:
        rep.findings.append(Finding("ok", "uses a hash router (#/...), which works under any path without a basename",
                                    hash_router[0]))
    env_name = sorted(api_envs)[0] if api_envs else None
    if env_name:
        rep.findings.append(Finding(
            "info", f"the API address comes from {', '.join(sorted(api_envs))}: set it to a path under the prefix "
                    f"when building/starting, e.g. {env_name}={prefix}api (no code change)", api_envs[env_name]))

    is_next = "next" in deps
    base_expr = "${process.env.NEXT_PUBLIC_BASE_PATH}" if is_next else "${import.meta.env.BASE_URL}"
    if prefix != "/":
        if len(url_hits) + len(api_defaults) > 10:
            rep.findings.append(Finding(
                "info", f"{len(url_hits) + len(api_defaults)} root-absolute API URLs: the zero-change option is to give "
                        "this app its own gateway port (Exposure: own port) instead of a path", ""))
        for rel, line, url in api_defaults:
            rep.findings.append(Finding(
                "warn" if env_name else "error", f"the API base defaults to '{url}', which skips the prefix",
                f"{rel}:{line}",
                f"check that it is built from {env_name}; otherwise use `{base_expr}{url.lstrip('/') if not is_next else url}`"
                if env_name else f"`{base_expr}{url.lstrip('/') if not is_next else url}`"))
        for rel, line, url in local_urls[:5]:
            rep.findings.append(Finding(
                "warn", f"{url} is a local address: a browser on another device would call its own computer",
                f"{rel}:{line}", "use a path under the prefix (routed to the backend in the project's API settings)"))
        for rel, line, what in router_hits:
            rep.findings.append(Finding("error", f"{what}: routes will not match under {prefix}", f"{rel}:{line}",
                                        "basename={import.meta.env.BASE_URL}  (Vue: createWebHistory(import.meta.env.BASE_URL))"))
        for rel, line, what in url_hits:
            rep.findings.append(Finding("error", f"root-absolute URL {what} skips the prefix", f"{rel}:{line}",
                                        f"build it from the base path, e.g. `{base_expr}{'/' if is_next else ''}api/...`"))
        for rel, line, url in asset_hits:
            rep.findings.append(Finding("warn", f"hard-coded public file {url} skips the prefix", f"{rel}:{line}",
                                        f"`${{import.meta.env.BASE_URL}}{url.lstrip('/')}`"))
        if not (router_hits or url_hits or asset_hits or api_defaults or local_urls):
            rep.findings.append(Finding("ok", "no router, API or public-file URLs that would skip the prefix"))

    if rep.is_vite:
        env = f"{env_name}={prefix}api " if env_name else ""
        rep.commands = [
            f"{env}npm run dev -- --base {prefix} --host 127.0.0.1 --port <port> --strictPort   # dev server",
            f"{env}npx vite build --base {prefix}                                  # production build",
        ]
    return rep


def format_report(rep: Report, limit: int = 8) -> str:
    icons = {"ok": "ok ", "warn": "!! ", "error": "XX ", "info": "-- "}
    lines = [f"Vite subpath check: {rep.project_dir}  (prefix {rep.prefix})", ""]
    seen: dict[str, int] = {}
    for f in rep.findings:
        kind = f.message.split(" skips")[0].split("'")[0]
        seen[kind] = seen.get(kind, 0) + 1
        if limit and seen[kind] == limit + 1:
            more = sum(1 for g in rep.findings if g.message.split(" skips")[0].split("'")[0] == kind) - limit
            lines.append(f"       ... and {more} more like this (--json lists all)")
        if limit and seen[kind] > limit:
            continue
        lines.append(f"  {icons.get(f.level, '   ')}{f.message}" + (f"  [{f.where}]" if f.where else ""))
        if f.fix:
            lines.append(f"       fix: {f.fix}")
    if rep.commands:
        lines += ["", "Start/build with the prefix:"] + [f"  {c}" for c in rep.commands]
    errors = sum(f.level == "error" for f in rep.findings)
    warns = sum(f.level == "warn" for f in rep.findings)
    lines += ["", f"{errors} problem(s), {warns} warning(s). This check only reads files; nothing was changed."]
    return "\n".join(lines)


def report_dict(rep: Report) -> dict:
    return {"project_dir": rep.project_dir, "prefix": rep.prefix, "is_vite": rep.is_vite,
            "base_in_config": rep.base_in_config, "commands": rep.commands,
            "findings": [f.__dict__ for f in rep.findings]}
