"""Per-project setup guide: what to change in the app so it works under its gateway path.

The guide is generated from the project's settings (prefix, ports, app kind, runtime)
and shown in the dashboard. Nothing here touches the project itself.
"""
from __future__ import annotations

from typing import Optional

from .models import ApiMode, AppKind, Exposure, PathMode, Project, Runtime

# What the dashboard's "How is the frontend served?" choice sets on the project
PRESETS = {
    AppKind.vite_dev: {
        "label": "Vite dev server (npm run dev)",
        "path_mode": PathMode.subpath, "pass_host_header": False,
        "help": "Start Vite with --base /prefix/. The gateway forwards /prefix/... unchanged and sends "
                "Host 127.0.0.1:port so Vite never blocks your Tailscale host name. Hot reload works through the gateway.",
    },
    AppKind.vite_preview: {
        "label": "Vite preview (vite build + vite preview)",
        "path_mode": PathMode.subpath, "pass_host_header": False,
        "help": "Build and preview with --base /prefix/. The gateway forwards /prefix/... unchanged.",
    },
    AppKind.static_dist: {
        "label": "Built files from a static server (Docker nginx, serve, Caddy)",
        "path_mode": PathMode.strip, "pass_host_header": True,
        "help": "Build with --base /prefix/; the server keeps serving dist/ at its root. The gateway removes "
                "/prefix before forwarding.",
    },
    AppKind.backend_served: {
        "label": "Built files served by the app's own backend",
        "path_mode": PathMode.strip, "pass_host_header": True,
        "help": "Build with --base /prefix/; the backend keeps serving the files at /. The gateway removes "
                "/prefix before forwarding.",
    },
    AppKind.nextjs: {
        "label": "Next.js (next start / next dev)",
        "path_mode": PathMode.subpath, "pass_host_header": True,
        "help": "Next.js needs basePath set at build time, and fetch('/api/...') calls must add it themselves. "
                "If the app has many such calls, give it its own gateway port instead (no code change).",
    },
    AppKind.prebuilt: {
        "label": "Prebuilt app that cannot be rebuilt",
        "exposure": Exposure.port, "path_mode": PathMode.subpath, "pass_host_header": True,
        "help": "Without a rebuild the app expects to live at /, so it gets its own gateway port "
                "(still through nginx and still Tailscale-only).",
    },
    AppKind.other: {
        "label": "Something else",
        "help": "Pick the path mode yourself: subpath if the app knows its prefix, strip if it expects /.",
    },
}


def presets_for_api() -> list[dict]:
    out = []
    for kind, p in PRESETS.items():
        sets = {k: (v.value if hasattr(v, "value") else v) for k, v in p.items() if k not in ("label", "help")}
        out.append({"value": kind.value, "label": p["label"], "help": p["help"], "sets": sets})
    return out


def _sec(title: str, text: str = "", code: Optional[str] = None, lang: str = "bash") -> dict:
    return {"title": title, "text": text, "code": code, "lang": lang}


def build_guide(p: Project, gateway_port: int, host: str = "<tailscale-ip>") -> dict:
    prefix = p.route_prefix
    base = f"{prefix}/" if prefix else "/"
    port = p.frontend.port
    app_dir = p.app_dir or f"~/{p.id}"
    public_port = p.dedicated_port if p.exposure == Exposure.port else gateway_port
    url = f"http://{host}:{public_port}{base}"
    sections: list[dict] = []
    warnings: list[str] = []

    preset = PRESETS.get(p.app_kind, {})
    if p.exposure == Exposure.path and "path_mode" in preset and preset["path_mode"] != p.frontend.path_mode and not p.is_root:
        warnings.append(f"The {preset['label']} preset expects path mode '{preset['path_mode'].value}', "
                        f"but this project uses '{p.frontend.path_mode.value}'.")
    if p.app_kind in (AppKind.vite_dev, AppKind.vite_preview) and p.pass_host_header:
        warnings.append("Vite blocks unknown host names (such as your MagicDNS name). Turn off "
                        "'Pass the original Host header' or add the name to server.allowedHosts.")

    sections.append(_sec("Where it will be", f"Open {url} from any device on your tailnet."))

    if p.is_root:
        sections.append(_sec(
            "No base-path changes needed",
            "This project is served at the site root"
            + (f" of its own gateway port {p.dedicated_port}" if p.exposure == Exposure.port else "")
            + ", exactly as it expects. Keep the app bound to 127.0.0.1 so only the gateway can reach it."))
    else:
        sections += _vite_sections(p, base, port, app_dir)

    if p.backend and not p.is_root:
        sections.append(_api_section(p, prefix))

    sections.append(_runtime_section(p, base, port, app_dir))
    sections.append(_sec(
        "Check it",
        "Use Test in the dashboard: it loads the page through the gateway and confirms that the page's files "
        "load under the prefix. For a static review of the project folder run:",
        f"nginx-gateway-ctl vite-check {app_dir} --prefix {base}"))
    return {"url": url, "warnings": warnings, "sections": sections}


def _vite_sections(p: Project, base: str, port: int, app_dir: str) -> list[dict]:
    kind = p.app_kind
    out = []
    if kind == AppKind.prebuilt:
        out.append(_sec(
            "This app needs its own port",
            "A prebuilt app references /assets/... and its own routes at the site root, and nginx cannot "
            "safely rewrite those. Switch Exposure to 'Own port'. Path mode 'rewrite' only helps simple "
            "multi-page sites."))
        return out
    if kind == AppKind.nextjs:
        out.append(_sec(
            "1. Set basePath and rebuild",
            "Next.js serves everything under basePath (path mode 'subpath'). Read it from the environment so the "
            "app still works at / without the gateway, then rebuild.",
            "// next.config.ts\n"
            "const nextConfig = {\n"
            "  basePath: process.env.NEXT_BASE_PATH || '',\n"
            "  env: { NEXT_PUBLIC_BASE_PATH: process.env.NEXT_BASE_PATH || '' },\n"
            "  // ...\n"
            "}\n\n"
            f"cd {app_dir}\n"
            f"NEXT_BASE_PATH={base.rstrip('/')} npm run build\n"
            f"NEXT_BASE_PATH={base.rstrip('/')} npx next start -H 127.0.0.1 -p {port}", "ts"))
        out.append(_sec(
            "2. Prefix fetch() calls",
            "Next.js adds basePath to <Link> and router pushes, but not to fetch('/api/...'). Run vite-check on the "
            "folder to list them; with many calls, Exposure 'Own port' is the zero-change alternative.",
            "fetch(`${process.env.NEXT_PUBLIC_BASE_PATH}/api/chats`)", "tsx"))
        return out
    if kind == AppKind.vite_dev:
        out.append(_sec(
            "1. Start Vite with the base path",
            "No vite.config change is needed: --base moves the assets, the dev client and hot reload under "
            f"{base}. --host 127.0.0.1 keeps the dev server private to the gateway.",
            f"cd {app_dir}\nnpm run dev -- --base {base} --host 127.0.0.1 --port {port} --strictPort"))
    elif kind == AppKind.vite_preview:
        out.append(_sec(
            "1. Build and preview with the base path",
            "",
            f"cd {app_dir}\nnpx vite build --base {base}\nnpx vite preview --base {base} --host 127.0.0.1 --port {port} --strictPort"))
    elif kind in (AppKind.static_dist, AppKind.backend_served):
        server = ("the server keeps serving dist/ at its root (the gateway removes the prefix)"
                  if p.frontend.path_mode == PathMode.strip else
                  "with path mode 'subpath' the server must serve the files under the prefix itself")
        out.append(_sec(
            "1. Build with the base path",
            f"Vite writes {base}assets/... into the page; {server}.",
            f"cd {app_dir}\nnpx vite build --base {base}"))
    else:
        out.append(_sec(
            "1. Make the app aware of its base path",
            f"If it is a Vite app, start or build it with --base {base}. Other frameworks have the same "
            "setting (Next.js basePath, Angular --base-href, CRA homepage).",
            f"npx vite build --base {base}"))

    out.append(_sec(
        "2. Only if the app uses client-side routing",
        "BASE_URL comes from --base and is / when the app runs without the gateway, so this works in both places.",
        "// React Router\n"
        "<BrowserRouter basename={import.meta.env.BASE_URL}>\n"
        "// or: createBrowserRouter(routes, { basename: import.meta.env.BASE_URL })\n\n"
        "// Vue Router\n"
        "createRouter({ history: createWebHistory(import.meta.env.BASE_URL), routes })",
        "tsx"))
    out.append(_sec(
        "3. Only if code uses root-absolute URLs",
        "Calls like fetch('/api/items') and files like '/logo.svg' referenced from code skip the prefix. "
        "References in index.html and CSS are rewritten by Vite automatically.",
        "const API = `${import.meta.env.BASE_URL}api`;   // instead of '/api'\n"
        "fetch(`${API}/items`);\n"
        "<img src={`${import.meta.env.BASE_URL}logo.svg`} />",
        "tsx"))
    out.append(_sec(
        "Optional: keep the base in vite.config",
        "Instead of passing --base every time, read it from the environment (unset means / as before).",
        "// vite.config.ts\nexport default defineConfig({\n  base: process.env.VITE_BASE_PATH ?? '/',\n  // ...\n})",
        "ts"))
    return out


def _api_section(p: Project, prefix: str) -> dict:
    b = p.backend
    seen = {ApiMode.strip_prefix: f"{b.api_path}/...", ApiMode.strip_all: "/...",
            ApiMode.preserve: f"{prefix}{b.api_path}/..."}[b.api_mode]
    return _sec(
        "Backend API",
        f"Requests to {prefix}{b.api_path}/... reach {b.hostport} as {seen}"
        + (", so the backend needs no change." if b.api_mode == ApiMode.strip_prefix else ".")
        + " WebSockets and streaming responses pass through. A FastAPI backend that shows its /docs page "
          f"behind the gateway can set root_path=\"{prefix}\".")


def _runtime_section(p: Project, base: str, port: int, app_dir: str) -> dict:
    env_line = "" if p.is_root else f"VITE_BASE_PATH={base} "
    if p.runtime == Runtime.systemd:
        return _sec(
            "Restart (systemd)",
            "Put the base path in the unit so every restart uses it, then restart. To restart from the "
            "dashboard, add the unit to /etc/nginx-gateway/restart-targets.conf.",
            "sudo systemctl edit <your-unit>.service\n"
            f"#   [Service]\n#   Environment=VITE_BASE_PATH={base}\n"
            "sudo systemctl restart <your-unit>.service\n"
            f"echo '{p.id} systemd <your-unit>.service' | sudo tee -a /etc/nginx-gateway/restart-targets.conf")
    if p.runtime == Runtime.docker:
        return _sec(
            "Rebuild and run (Docker)",
            "The base path is baked in at build time. Publish the port on 127.0.0.1 only: Docker-published "
            "ports bypass ufw.",
            "# Dockerfile (build stage)\n"
            "ARG VITE_BASE_PATH=/\n"
            "RUN npx vite build --base ${VITE_BASE_PATH}\n\n"
            f"docker build --build-arg VITE_BASE_PATH={base} -t {p.id} {app_dir}\n"
            f"docker rm -f {p.id} 2>/dev/null; docker run -d --name {p.id} --restart unless-stopped "
            f"-p 127.0.0.1:{port}:80 {p.id}\n"
            f"echo '{p.id} docker {p.id}' | sudo tee -a /etc/nginx-gateway/restart-targets.conf")
    if p.runtime == Runtime.tmux:
        cmd = ("npm run dev -- " + (f"--base {base} " if not p.is_root else "") + f"--host 127.0.0.1 --port {port} --strictPort"
               if p.app_kind == AppKind.vite_dev else f"{env_line}npm run build && {env_line}npm run preview")
        return _sec(
            "Restart (tmux)",
            "Stop the old process in its tmux window (Ctrl-C) and start it again, or run it in a new session:",
            f"tmux new -d -s {p.id} 'cd {app_dir} && {cmd}'")
    return _sec("Restart", "Restart the app the way you normally start it, with the base path above.")
