"""Per-project setup guide, in plain language: what to change in the app so it works under its gateway path.

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
        "help": "Start Vite with --base /your-path/. That is the only change. Hot reload keeps working.",
    },
    AppKind.vite_preview: {
        "label": "Vite preview (vite build + vite preview)",
        "path_mode": PathMode.subpath, "pass_host_header": False,
        "help": "Build and preview with --base /your-path/.",
    },
    AppKind.static_dist: {
        "label": "Built files from a static server (Docker nginx, serve, Caddy)",
        "path_mode": PathMode.strip, "pass_host_header": True,
        "help": "Build with --base /your-path/. The server keeps serving the files as usual; "
                "the gateway removes /your-path before the request reaches it.",
    },
    AppKind.backend_served: {
        "label": "Built files served by the app's own backend",
        "path_mode": PathMode.strip, "pass_host_header": True,
        "help": "Build with --base /your-path/. The backend keeps serving the files as usual; "
                "the gateway removes /your-path before the request reaches it.",
    },
    AppKind.nextjs: {
        "label": "Next.js (next start / next dev)",
        "path_mode": PathMode.subpath, "pass_host_header": True,
        "help": "Set basePath in next.config and rebuild. Your own fetch('/api/...') calls need the path added. "
                "Too many to edit? Give the app its own gateway port instead (no code change).",
    },
    AppKind.prebuilt: {
        "label": "Prebuilt app that cannot be rebuilt",
        "exposure": Exposure.port, "path_mode": PathMode.subpath, "pass_host_header": True,
        "help": "The app cannot be changed, so it gets its own gateway port and stays at /. "
                "Nothing in the app changes.",
    },
    AppKind.other: {
        "label": "Something else",
        "help": "Pick the path mode yourself: 'subpath' if the app knows its base path, 'strip' if it expects /. "
                "A plain backend needs no change: use 'strip'.",
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
        warnings.append(f"The app type '{preset['label']}' expects path mode '{preset['path_mode'].value}', "
                        f"but this project uses '{p.frontend.path_mode.value}'. Change one of them unless you did this on purpose.")
    if p.app_kind in (AppKind.vite_dev, AppKind.vite_preview) and p.pass_host_header:
        warnings.append("Vite blocks unknown host names, so you may see 'Blocked request'. Fix: in Advanced, turn off "
                        "'Pass the original Host header'.")

    sections.append(_sec("Where it will be", f"Open {url} from any device on your network."))

    if p.is_root:
        sections.append(_sec(
            "No base-path changes needed",
            "This app lives at the site root"
            + (f" of its own gateway port {p.dedicated_port}" if p.exposure == Exposure.port else "")
            + ", which is what it expects. Nothing in the app needs to change. "
              "Make it listen on 127.0.0.1 so only the gateway can reach it."))
    else:
        sections += _vite_sections(p, base, port, app_dir)

    if p.backend and not p.is_root:
        sections.append(_api_section(p, prefix))

    sections.append(_runtime_section(p, base, port, app_dir))
    sections.append(_sec(
        "Check it",
        "Press Test in the dashboard. It opens the page through the gateway and checks that its files "
        "load from the right path. To check your project folder for problems before you start, run:",
        f"nginx-gateway-ctl vite-check {app_dir} --prefix {base}"))
    return {"url": url, "warnings": warnings, "sections": sections}


def _vite_sections(p: Project, base: str, port: int, app_dir: str) -> list[dict]:
    kind = p.app_kind
    out = []
    if kind == AppKind.prebuilt:
        out.append(_sec(
            "This app needs its own port",
            "A prebuilt app expects to live at /, and it cannot be moved under a path without rebuilding it. "
            "Set Exposure to 'Its own gateway port'. The app itself stays exactly as it is."))
        return out
    if kind == AppKind.nextjs:
        out.append(_sec(
            "1. Set basePath and rebuild",
            "Add basePath to next.config. Reading it from an environment variable means the app still works "
            "at / when you run it without the gateway. The value is saved at build time, so you must rebuild.",
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
            "2. Add the path to your fetch() calls",
            "Next.js adds basePath to links and pages by itself, but not to your own fetch('/api/...') calls. "
            "The check command below lists them. Too many to edit? Use Exposure 'Its own gateway port' (no code change).",
            "fetch(`${process.env.NEXT_PUBLIC_BASE_PATH}/api/chats`)", "tsx"))
        return out
    if kind == AppKind.vite_dev:
        out.append(_sec(
            "1. Start Vite with the base path",
            f"--base {base} tells Vite where the app lives. You do not need to edit vite.config. "
            "--host 127.0.0.1 keeps the app private, so only the gateway can reach it.",
            f"cd {app_dir}\nnpm run dev -- --base {base} --host 127.0.0.1 --port {port} --strictPort"))
    elif kind == AppKind.vite_preview:
        out.append(_sec(
            "1. Build and preview with the base path",
            f"--base {base} tells Vite where the app lives. You do not need to edit vite.config.",
            f"cd {app_dir}\nnpx vite build --base {base}\nnpx vite preview --base {base} --host 127.0.0.1 --port {port} --strictPort"))
    elif kind in (AppKind.static_dist, AppKind.backend_served):
        server = ("Your server keeps serving the files as usual, because the gateway removes the path first"
                  if p.frontend.path_mode == PathMode.strip else
                  "With path mode 'subpath' your server must serve the files under that path itself")
        out.append(_sec(
            "1. Build with the base path",
            f"Vite writes {base}assets/... into the page. {server}.",
            f"cd {app_dir}\nnpx vite build --base {base}"))
    else:
        out.append(_sec(
            "1. Make the app aware of its base path",
            f"Every frontend has one setting for its base path. For Vite it is --base {base}. Others: "
            "Next.js basePath, Angular --base-href, Create React App PUBLIC_URL. Rebuild after you set it.",
            f"npx vite build --base {base}"))

    out.append(_sec(
        "2. Only if your app has pages like /settings (a router)",
        "Tell the router the base path. BASE_URL comes from --base, and is just / without the gateway, "
        "so this code works in both places. A hash router (/#/settings) needs no change.",
        "// React Router\n"
        "<BrowserRouter basename={import.meta.env.BASE_URL}>\n"
        "// or: createBrowserRouter(routes, { basename: import.meta.env.BASE_URL })\n\n"
        "// Vue Router\n"
        "createRouter({ history: createWebHistory(import.meta.env.BASE_URL), routes })",
        "tsx"))
    out.append(_sec(
        "3. Only if your code writes URLs that start with /",
        "Calls like fetch('/api/items') or images like '/logo.svg' written in code skip the path, so add the base. "
        "Links in index.html and CSS are fixed by Vite automatically. If your app reads its API address from "
        "an environment variable, set that variable instead and change no code.",
        "const API = `${import.meta.env.BASE_URL}api`;   // instead of '/api'\n"
        "fetch(`${API}/items`);\n"
        "<img src={`${import.meta.env.BASE_URL}logo.svg`} />",
        "tsx"))
    out.append(_sec(
        "Optional: set the base in vite.config instead",
        "If you do not want to type --base every time, read it from an environment variable.",
        "// vite.config.ts\nexport default defineConfig({\n  base: process.env.VITE_BASE_PATH ?? '/',\n  // ...\n})",
        "ts"))
    return out


def _api_section(p: Project, prefix: str) -> dict:
    b = p.backend
    seen = {ApiMode.strip_prefix: f"{b.api_path}/...", ApiMode.strip_all: "/...",
            ApiMode.preserve: f"{prefix}{b.api_path}/..."}[b.api_mode]
    return _sec(
        "Backend: no change needed",
        f"A request to {prefix}{b.api_path}/... reaches your backend ({b.hostport}) as {seen}. "
        "Your backend never sees the path, so you change nothing in it. WebSockets and streaming work too. "
        f"Only your frontend must call the API with the path in front (for example {prefix}{b.api_path}/items). "
        f"A FastAPI /docs page also needs root_path=\"{prefix}\".")


def _runtime_section(p: Project, base: str, port: int, app_dir: str) -> dict:
    env_line = "" if p.is_root else f"VITE_BASE_PATH={base} "
    if p.runtime == Runtime.systemd:
        return _sec(
            "Restart (systemd)",
            "Save the base path in the service so every restart uses it, then restart. To get a Restart "
            "button in the dashboard, add the service to /etc/nginx-gateway/restart-targets.conf.",
            "sudo systemctl edit <your-unit>.service\n"
            f"#   [Service]\n#   Environment=VITE_BASE_PATH={base}\n"
            "sudo systemctl restart <your-unit>.service\n"
            f"echo '{p.id} systemd <your-unit>.service' | sudo tee -a /etc/nginx-gateway/restart-targets.conf")
    if p.runtime == Runtime.docker:
        return _sec(
            "Rebuild and run (Docker)",
            "In Docker the base path is saved when the image is built, so changing .env is not enough: "
            "pass it as a build argument and rebuild. Publish the port on 127.0.0.1 only, because Docker "
            "ports skip the firewall.",
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
            "Stop the old process (Ctrl-C in its tmux window) and start it again, or start it in a new session:",
            f"tmux new -d -s {p.id} 'cd {app_dir} && {cmd}'")
    return _sec("Restart", "Restart the app the way you normally do, using the base path from above.")
