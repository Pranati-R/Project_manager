"""Connectivity tests, listener inspection, the base-path doctor and Tailscale discovery."""
from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

import httpx

from .models import AppKind, Exposure, PathMode, Project, Runtime, Settings
from .nginx_helper import parse_proc_net

PROC_NET = Path("/proc/net")
REF_RE = re.compile(r"""(?:\bsrc|\bhref)\s*=\s*["']([^"']+)["']""", re.I)
IMPORT_RE = re.compile(r"""\bimport\s*(?:[^'"]*?\bfrom\s*)?["'](/[^"']+)["']""")


def listeners(proc_net: Path = PROC_NET) -> dict[int, list[str]]:
    """Listening TCP ports -> the addresses they are bound to."""
    out: dict[int, list[str]] = {}
    for name, v6 in (("tcp", False), ("tcp6", True)):
        try:
            text = (proc_net / name).read_text()
        except OSError:
            continue
        for addr, port in parse_proc_net(text, v6):
            if addr not in out.setdefault(port, []):
                out[port].append(addr)
    return out


def _check(cid: str, label: str, status: str, detail: str = "", hint: str = "") -> dict:
    return {"id": cid, "label": label, "status": status, "detail": detail, "hint": hint}


async def tcp_check(host: str, port: int, timeout: float = 2.0) -> tuple[bool, str]:
    start = time.monotonic()
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass
        return True, f"{(time.monotonic() - start) * 1000:.0f} ms"
    except (OSError, asyncio.TimeoutError) as e:
        return False, "connection refused" if isinstance(e, ConnectionRefusedError) else (str(e) or "timed out")


def bind_hint(project: Project) -> str:
    if project.runtime == Runtime.docker:
        return "Publish the port on loopback only: docker run -p 127.0.0.1:%d:<container port> ... (Docker-published ports bypass ufw)." % project.frontend.port
    if project.app_kind in (AppKind.vite_dev, AppKind.vite_preview):
        return "Start Vite with --host 127.0.0.1 so only the gateway can reach it."
    return "Bind the app to 127.0.0.1 so it is only reachable through the gateway."


def exposure_checks(project: Project, ports: dict[int, list[str]]) -> list[dict]:
    checks = []
    parts = [("frontend", project.frontend)] + ([("backend", project.backend)] if project.backend else [])
    for part, up in parts:
        addrs = ports.get(up.port, [])
        if not addrs:
            continue
        if "0.0.0.0" in addrs or "::" in addrs:
            checks.append(_check(f"{part}_exposure", f"{part.capitalize()} port {up.port} binding", "warn",
                                 "listening on all interfaces, so it can be reached without the gateway",
                                 bind_hint(project)))
        elif up.host == "127.0.0.1" and addrs == ["::1"]:
            checks.append(_check(f"{part}_exposure", f"{part.capitalize()} port {up.port} binding", "error",
                                 "listening on ::1 (IPv6 localhost) only, but the gateway connects to 127.0.0.1",
                                 "Set the upstream host to ::1 or start the app with --host 127.0.0.1 "
                                 "(Node 17+ resolves 'localhost' to ::1)."))
        else:
            checks.append(_check(f"{part}_exposure", f"{part.capitalize()} port {up.port} binding", "ok",
                                 "listening on " + ", ".join(addrs)))
    return checks


def analyze_html(html: str, prefix: str) -> dict:
    """Root-absolute URLs in a page, split into inside/outside the project prefix."""
    refs = REF_RE.findall(html) + IMPORT_RE.findall(html)
    inside, outside = [], []
    for ref in refs:
        if not ref.startswith("/") or ref.startswith("//"):
            continue
        if prefix in ("", "/") or ref == prefix or ref.startswith(prefix + "/"):
            inside.append(ref)
        else:
            outside.append(ref)
    return {
        "inside": list(dict.fromkeys(inside)),
        "outside": list(dict.fromkeys(outside)),
        "vite_dev": "/@vite/client" in html,
        "host_blocked": "Blocked request. This host" in html,
    }


def gateway_base(settings: Settings, project: Project) -> str:
    port = project.dedicated_port if project.exposure == Exposure.port else settings.gateway_port
    addr = settings.listen_addresses[0]
    if addr in ("0.0.0.0", "::") or "127.0.0.1" in settings.listen_addresses:
        addr = "127.0.0.1"
    host = f"[{addr}]" if ":" in addr else addr
    return f"http://{host}:{port}"


async def test_project(project: Project, settings: Settings, *, proc_net: Path = PROC_NET) -> dict:
    checks: list[dict] = []
    fe = project.frontend
    ok, detail = await tcp_check(fe.host, fe.port)
    checks.append(_check("frontend_tcp", f"Frontend {fe.hostport}", "ok" if ok else "error", detail,
                         "" if ok else "The app is not running or listens on another port/address."))
    if project.backend:
        be = project.backend
        bok, bdetail = await tcp_check(be.host, be.port)
        checks.append(_check("backend_tcp", f"Backend {be.hostport}", "ok" if bok else "error", bdetail,
                             "" if bok else "The API server is not running or listens elsewhere."))
    checks += exposure_checks(project, listeners(proc_net))

    if not project.enabled:
        checks.append(_check("gateway", "Through the gateway", "skip", "the project is disabled"))
        return _summary(checks)

    base = gateway_base(settings, project)
    prefix = project.route_prefix
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
        url = f"{base}{prefix}/"
        try:
            r = await client.get(url, headers={"Accept": "text/html,*/*"})
        except httpx.HTTPError as e:
            checks.append(_check("gateway", f"GET {prefix}/ through the gateway", "error", str(e) or type(e).__name__,
                                 "Is nginx running and the config applied? See the Config tab."))
            return _summary(checks)
        checks.append(_gateway_status_check(r, f"GET {prefix}/ through the gateway"))
        if "text/html" in r.headers.get("content-type", "") and r.status_code < 500:
            checks += await _doctor(client, base, project, r.text)
        if project.backend:
            api_url = f"{base}{prefix}{project.backend.api_path}{project.health_path or '/'}"
            try:
                ar = await client.get(api_url)
                c = _gateway_status_check(ar, f"GET {prefix}{project.backend.api_path}{project.health_path or '/'}")
                if c["status"] == "warn" and ar.status_code == 404 and not project.health_path:
                    c = _check(c["id"], c["label"], "ok", "the API answered (404 for /, which is normal)",
                               "Set a health path (e.g. /health) for a stronger check.")
                checks.append(c)
            except httpx.HTTPError as e:
                checks.append(_check("api", "API through the gateway", "error", str(e) or type(e).__name__))
    return _summary(checks)


def _gateway_status_check(r: httpx.Response, label: str) -> dict:
    code = r.status_code
    if code in (502, 504):
        return _check("gateway", label, "error", f"HTTP {code}: nginx could not reach the app",
                      "Start the app, or fix the host/port in the project settings.")
    if code == 403 and "Blocked request" in r.text:
        return _check("gateway", label, "error", "HTTP 403 from Vite: the host name is not allowed",
                      "Turn off 'Pass the original Host header' (the Vite preset does this) or add the "
                      "name to server.allowedHosts in vite.config.")
    if code == 403:
        return _check("gateway", label, "error", "HTTP 403 from nginx",
                      "127.0.0.1 must be in 'Allowed networks' for these tests to work.")
    if code >= 500:
        return _check("gateway", label, "warn", f"HTTP {code} from the app")
    if code == 404:
        return _check("gateway", label, "warn", "HTTP 404 from the app", "The app does not serve this path.")
    return _check("gateway", label, "ok", f"HTTP {code}")


async def _doctor(client: httpx.AsyncClient, base: str, project: Project, html: str) -> list[dict]:
    prefix = project.route_prefix
    info = analyze_html(html, prefix)
    checks = []
    if info["host_blocked"]:
        checks.append(_check("base_path", "Base path", "error", "Vite blocked the request's host name",
                             "Turn off 'Pass the original Host header' for this project."))
        return checks
    if info["outside"]:
        sample = ", ".join(info["outside"][:3])
        kind = "the Vite dev server" if info["vite_dev"] else "the page"
        checks.append(_check(
            "base_path", "Base path", "error",
            f"{kind} references {sample} outside {prefix}/, so the browser will miss those files",
            f"Start/build the app with --base {prefix}/ (see the Setup guide), or give it its own port."
            if project.frontend.path_mode != PathMode.rewrite else
            "Rewrite mode could not fix these references; this app needs --base or its own port."))
    elif prefix:
        checks.append(_check("base_path", "Base path", "ok",
                             f"all {len(info['inside'])} root-absolute references stay inside {prefix}/"
                             if info["inside"] else "no root-absolute references in the page"))
    for ref in [r for r in info["inside"] if not r.endswith("/")][:3]:
        try:
            ar = await client.get(base + ref)
            status = "ok" if ar.status_code < 400 else "error"
            checks.append(_check("asset", f"Asset {ref}", status, f"HTTP {ar.status_code}",
                                 "" if status == "ok" else "The page links a file the app does not serve here."))
        except httpx.HTTPError as e:
            checks.append(_check("asset", f"Asset {ref}", "error", str(e) or type(e).__name__))
    return checks


def _summary(checks: list[dict]) -> dict:
    statuses = {c["status"] for c in checks}
    overall = "error" if "error" in statuses else "warn" if "warn" in statuses else "ok"
    return {"status": overall, "checks": checks}


async def quick_status(projects: list[Project]) -> dict[str, dict]:
    """TCP reachability of every project's upstreams, for the list view."""
    async def one(p: Project):
        fe_ok, _ = await tcp_check(p.frontend.host, p.frontend.port, 1.0)
        be_ok = None
        if p.backend:
            be_ok, _ = await tcp_check(p.backend.host, p.backend.port, 1.0)
        return p.id, {"frontend": fe_ok, "backend": be_ok}
    results = await asyncio.gather(*(one(p) for p in projects))
    return dict(results)


_ts_cache: dict = {"at": 0.0, "value": None}


def tailscale_info() -> dict:
    if _ts_cache["value"] is not None and time.time() - _ts_cache["at"] < 60:
        return _ts_cache["value"]
    info = {"ipv4": [], "ipv6": [], "dns_name": None}
    try:
        r = subprocess.run(["tailscale", "status", "--json", "--self", "--peers=false"],
                           capture_output=True, text=True, timeout=4)
        if r.returncode == 0:
            data = json.loads(r.stdout)
            me = data.get("Self", {})
            for ip in me.get("TailscaleIPs", []):
                (info["ipv6"] if ":" in ip else info["ipv4"]).append(ip)
            info["dns_name"] = (me.get("DNSName") or "").rstrip(".") or None
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    if not info["ipv4"]:
        info["ipv4"] = _cgnat_addresses()
    _ts_cache.update(at=time.time(), value=info)
    return info


def _cgnat_addresses() -> list[str]:
    """Addresses in Tailscale's 100.64.0.0/10 range, found without the tailscale CLI."""
    try:
        r = subprocess.run(["ip", "-j", "-4", "addr", "show"], capture_output=True, text=True, timeout=3)
        data = json.loads(r.stdout or "[]")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return []
    net = ipaddress.ip_network("100.64.0.0/10")
    found = []
    for iface in data:
        for a in iface.get("addr_info", []):
            try:
                if ipaddress.ip_address(a.get("local", "")) in net:
                    found.append(a["local"])
            except ValueError:
                pass
    return found


def gateway_urls(settings: Settings, ts: Optional[dict] = None) -> dict:
    ts = ts if ts is not None else tailscale_info()
    hosts = ([ts["dns_name"]] if ts.get("dns_name") else []) + ts.get("ipv4", [])
    if not hosts:
        hosts = ["<server-ip>"]
    urls = {"gateway": [f"http://{h}:{settings.gateway_port}/" for h in hosts]}
    if settings.admin_mode == "dedicated_port":
        urls["admin"] = [f"http://{h}:{settings.admin_port}/" for h in hosts]
    return urls
