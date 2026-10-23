"""End to end: several projects reachable through ONE gateway port of a real nginx.

A private nginx (its own prefix, ports and logs; never the system nginx) runs the config
produced by the real generator, installed by the real helper code, in front of small mock
apps. A pre-existing "foreign" site lives in the same nginx to prove the gateway leaves
other sites alone. Skipped when no nginx binary is found (set GW_NGINX_BIN).
"""
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from conftest import find_nginx, free_port
from gateway_manager import nginx_helper
from gateway_manager.generator import render
from gateway_manager.models import Project, Settings, check_state
from gateway_manager.sandbox import NginxSandbox, SandboxEnv

sys.path.insert(0, str(Path(__file__).parent))
from mock_upstream import LEGACY_HTML, ServerThread, make_app  # noqa: E402

NGINX = find_nginx()
pytestmark = [pytest.mark.e2e,
              pytest.mark.skipif(NGINX is None or sys.platform == "win32", reason="needs an nginx binary on Linux")]

MOCKS = {
    "prajna_fe": "prajna-frontend", "prajna_api": "prajna-api", "mt_fe": "transcriber-frontend",
    "mt_api": "transcriber-backend", "static": "smart-finder-static", "legacy": "legacy-app",
    "rootapp": "root-only-app", "manager": "manager", "slow": "foreign-upstream",
}


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    ports = {k: free_port() for k in list(MOCKS) + ["gateway", "admin", "dedicated", "foreign"]}
    apps = [ServerThread(make_app(name, LEGACY_HTML if key == "legacy" else None), ports[key]).start()
            for key, name in MOCKS.items()]
    root = tmp_path_factory.mktemp("gateway")
    logs = root / "sandbox" / "logs"
    foreign = f"""
    # ── a pre-existing site the gateway must not affect ──
    map $http_x_test $foreign_var {{ default "x"; }}
    log_format foreign_fmt '$remote_addr "$request" $status';
    server {{
        listen 127.0.0.1:{ports['foreign']};
        access_log {logs}/foreign.log foreign_fmt;
        location / {{ default_type text/plain; return 200 "foreign site\\n"; }}
        location /slow {{ proxy_pass http://127.0.0.1:{ports['slow']}; }}
    }}"""
    sb = NginxSandbox(root / "sandbox", NGINX, foreign).prepare()
    staging = root / "staging"
    staging.mkdir()
    env = SandboxEnv(sb, staging)
    ok, out = sb.start()
    assert ok, out

    settings = Settings(gateway_port=ports["gateway"], admin_port=ports["admin"], listen_addresses=["127.0.0.1"])
    projects = [
        Project(id="prajna", name="Prajna", prefix="/prajna", app_kind="vite_dev", pass_host_header=False,
                frontend={"port": ports["prajna_fe"]}, backend={"port": ports["prajna_api"]}),
        Project(id="meeting-transcriber", name="Meeting Transcriber", prefix="/meeting-transcriber",
                frontend={"port": ports["mt_fe"]},
                backend={"port": ports["mt_api"], "api_path": "/backend", "api_mode": "strip_all"}),
        Project(id="smart-finder", name="Smart Finder", prefix="/smart-finder",
                frontend={"port": ports["static"], "path_mode": "strip"}),
        Project(id="legacy", name="Legacy", prefix="/legacy", frontend={"port": ports["legacy"], "path_mode": "rewrite"}),
        Project(id="disabled", name="Disabled", prefix="/disabled", frontend={"port": ports["static"]}, enabled=False),
        Project(id="rootapp", name="Root app", exposure="port", dedicated_port=ports["dedicated"],
                frontend={"port": ports["rootapp"]}),
    ]
    errors, _ = check_state(settings, projects, ports["manager"])
    assert not errors, errors

    def build(s=settings, ps=projects):
        return render(s, ps, manager_port=ports["manager"], log_dir=str(sb.logs))

    text = build()
    assert nginx_helper.lint(text, str(sb.logs)) == []
    foreign_before = httpx.get(f"http://127.0.0.1:{ports['foreign']}/").text
    result = nginx_helper.apply_config(env, text)
    assert result["ok"] and result["reloaded"], result

    gw = httpx.Client(base_url=f"http://127.0.0.1:{ports['gateway']}", timeout=10, follow_redirects=False)
    yield SimpleNamespace(ports=ports, sb=sb, env=env, settings=settings, projects=projects, text=text,
                          build=build, gw=gw, foreign_before=foreign_before)
    gw.close()
    sb.stop()
    for a in apps:
        a.stop()


def test_every_project_answers_on_the_single_gateway_port(stack):
    seen = {}
    for prefix, app in [("/prajna/", "prajna-frontend"), ("/meeting-transcriber/", "transcriber-frontend"),
                        ("/smart-finder/", "smart-finder-static"), ("/prajna/api/ping", "prajna-api"),
                        ("/meeting-transcriber/backend/health", "transcriber-backend")]:
        r = stack.gw.get(prefix)
        assert r.status_code == 200, (prefix, r.status_code, r.text[:200])
        assert r.json()["app"] == app
        seen[prefix] = app
    assert len(set(seen.values())) == 5  # five different apps, one port
    assert stack.gw.get("/legacy/").status_code == 200


def test_path_modes(stack):
    assert stack.gw.get("/prajna/assets/app.js").json()["path"] == "/prajna/assets/app.js"       # subpath
    assert stack.gw.get("/smart-finder/assets/app.js").json()["path"] == "/assets/app.js"        # strip
    assert stack.gw.get("/prajna/api/items").json()["path"] == "/api/items"                      # strip_prefix
    assert stack.gw.get("/meeting-transcriber/backend/auth/login").json()["path"] == "/auth/login"  # strip_all
    assert stack.gw.get("/prajna/api").json()["path"] == "/api"


def test_query_strings_encoding_and_bodies(stack):
    r = stack.gw.get("/prajna/api/items?x=1&y=a%20b&tag=%E2%9C%93").json()
    assert r["query"] == "x=1&y=a%20b&tag=%E2%9C%93"
    assert stack.gw.get("/smart-finder/files/a%20b.txt").json()["raw_path"] == "/files/a%20b.txt"
    r = stack.gw.post("/prajna/api/items", json={"name": "x" * 5000}).json()
    assert r["method"] == "POST" and len(r["body"]) > 5000


def test_forwarded_headers_and_host(stack):
    p = stack.ports
    h = stack.gw.get("/prajna/api/whoami").json()["headers"]
    assert h["x-forwarded-prefix"] == "/prajna"
    assert h["x-forwarded-host"] == f"127.0.0.1:{p['gateway']}"
    assert h["x-real-ip"] == "127.0.0.1" and h["x-forwarded-proto"] == "http"
    assert h["host"] == f"127.0.0.1:{p['prajna_api']}"  # Vite preset: upstream Host, so Vite never blocks it
    h = stack.gw.get("/smart-finder/").json()["headers"]
    assert h["host"] == f"127.0.0.1:{p['gateway']}"    # default: the original Host


def test_websockets_through_the_gateway(stack):
    from websockets.sync.client import connect
    port = stack.ports["gateway"]
    with connect(f"ws://127.0.0.1:{port}/prajna/api/ws") as ws:
        ws.send("hello")
        assert ws.recv(timeout=5) == "prajna-api:/api/ws:hello"
    with connect(f"ws://127.0.0.1:{port}/prajna/") as ws:  # like Vite's HMR socket at the base path
        ws.send("hmr")
        assert ws.recv(timeout=5) == "prajna-frontend:/prajna/:hmr"


def test_dashboard_cookie_never_reaches_projects(stack):
    h = stack.gw.get("/prajna/api/c", headers={"Cookie": "a=1; gwm_session=SECRET; b=2"}).json()["headers"]
    assert "gwm_session" not in h.get("cookie", "") and "a=1" in h["cookie"] and "b=2" in h["cookie"]
    h = stack.gw.get("/prajna/api/c", headers={"Cookie": "gwm_session=SECRET"}).json()["headers"]
    assert "cookie" not in h
    h = stack.gw.get("/prajna/api/c", headers={"Cookie": "my_gwm_session=keep"}).json()["headers"]
    assert h["cookie"] == "my_gwm_session=keep"


def test_redirects_disabled_unknown_and_landing(stack):
    r = stack.gw.get("/prajna?x=1")
    assert r.status_code == 301 and r.headers["location"] == "/prajna/?x=1"
    assert stack.gw.get("/disabled/").status_code == 404
    assert stack.gw.get("/nothing-here/").status_code == 404
    assert stack.gw.get("/gateway-health").text == "ok\n"
    landing = stack.gw.get("/")
    assert landing.status_code == 200 and "/prajna/" in landing.text and "/disabled/" not in landing.text


def test_rewrite_mode_fixes_root_absolute_links(stack):
    html = stack.gw.get("/legacy/").text
    assert 'href="/legacy/style.css"' in html
    assert 'src="/legacy/assets/app.js"' in html
    assert 'src="//cdn.example.com/lib.js"' in html  # protocol-relative URLs untouched
    assert "url(/legacy/img/bg.png)" in html
    assert "href='/legacy/about'" in html
    assert "url(/legacy/img/x.png)" in stack.gw.get("/legacy/style.css").text


def test_dedicated_port_and_admin_port(stack):
    p = stack.ports
    r = httpx.get(f"http://127.0.0.1:{p['dedicated']}/some/page?q=1").json()
    assert r["app"] == "root-only-app" and r["path"] == "/some/page" and r["query"] == "q=1"
    r = httpx.get(f"http://127.0.0.1:{p['admin']}/api/health").json()
    assert r["app"] == "manager" and r["headers"]["x-forwarded-for"] == "127.0.0.1"


def test_foreign_site_is_untouched_even_during_reload(stack):
    p = stack.ports
    assert httpx.get(f"http://127.0.0.1:{p['foreign']}/").text == stack.foreign_before
    result = {}

    def slow():
        result["r"] = httpx.get(f"http://127.0.0.1:{p['foreign']}/slow", timeout=10)

    t = threading.Thread(target=slow)
    t.start()
    time.sleep(0.5)
    changed = stack.build(ps=stack.projects[:-1])  # drop a project: real config change + reload
    assert nginx_helper.apply_config(stack.env, changed)["reloaded"]
    t.join(10)
    assert result["r"].status_code == 200 and "slow done" in result["r"].text  # in-flight request survived
    assert httpx.get(f"http://127.0.0.1:{p['foreign']}/").text == stack.foreign_before
    assert nginx_helper.apply_config(stack.env, stack.text)["ok"]  # back to the full config


def test_port_collision_with_another_site_is_refused(stack):
    s = Settings(gateway_port=stack.ports["foreign"], admin_port=stack.ports["admin"], listen_addresses=["127.0.0.1"])
    with pytest.raises(nginx_helper.HelperFailure) as e:
        nginx_helper.apply_config(stack.env, stack.build(s=s))
    assert e.value.result["stage"] == "conflicts"
    assert f"port {stack.ports['foreign']} is already used by another nginx site" in " ".join(e.value.result["errors"])
    assert nginx_helper.read_live(stack.env) == stack.text
    assert stack.gw.get("/prajna/").status_code == 200


def test_rejected_config_leaves_the_gateway_running(stack):
    broken = stack.text.replace("    location = /gateway-health {",
                                "    location = /gateway-health {\n        return 404;\n    }\n    location = /gateway-health {", 1)
    assert nginx_helper.lint(broken, str(stack.sb.logs)) == []  # well-formed, but nginx refuses duplicates
    with pytest.raises(nginx_helper.HelperFailure) as e:
        nginx_helper.apply_config(stack.env, broken)
    assert e.value.result["stage"] == "nginx-test" and "duplicate location" in e.value.result["output"]
    assert nginx_helper.read_live(stack.env) == stack.text
    assert stack.gw.get("/prajna/").json()["app"] == "prajna-frontend"


def test_dashboard_diagnostics_see_the_gateway(stack):
    import asyncio

    from gateway_manager.diagnostics import test_project
    result = asyncio.run(test_project(stack.projects[0], stack.settings))
    by_id = {c["id"]: c for c in result["checks"]}
    assert by_id["frontend_tcp"]["status"] == "ok" and by_id["backend_tcp"]["status"] == "ok"
    assert by_id["gateway"]["status"] == "ok"


# ── a real Vite dev server behind the gateway (needs node + vite in tests/fixtures/vite-app) ──
VITE_APP = Path(os.environ.get("GW_VITE_APP") or Path(__file__).resolve().parents[1] / "fixtures" / "vite-app")
VITE_BIN = VITE_APP / "node_modules" / ".bin" / "vite"


@pytest.mark.skipif(not (shutil.which("node") and VITE_BIN.exists()),
                    reason="run `npm install` in tests/fixtures/vite-app (needs node) to include the Vite check")
def test_real_vite_dev_server_under_a_prefix(stack):
    import asyncio

    from websockets.sync.client import connect

    from gateway_manager.diagnostics import test_project
    port = free_port()
    proc = subprocess.Popen([str(VITE_BIN), "--base", "/viteapp/", "--host", "127.0.0.1", "--port", str(port),
                             "--strictPort"], cwd=VITE_APP, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            env={**os.environ, "BROWSER": "none"})
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                httpx.get(f"http://127.0.0.1:{port}/viteapp/", timeout=1)
                break
            except httpx.HTTPError:
                time.sleep(0.3)
        vite = Project(id="viteapp", name="Vite app", prefix="/viteapp", frontend={"port": port},
                       app_kind="vite_dev", pass_host_header=False)
        nginx_helper.apply_config(stack.env, stack.build(ps=stack.projects + [vite]))
        page = stack.gw.get("/viteapp/", headers={"Host": "box.tail1234.ts.net:8280"})
        assert page.status_code == 200, page.text[:300]
        assert "/viteapp/@vite/client" in page.text
        client = stack.gw.get("/viteapp/@vite/client")
        assert client.status_code == 200
        assert stack.gw.get("/viteapp/src/main.js").status_code == 200
        # Hot reload: the client opens a WebSocket at the base path (with a token since Vite 6.0.9)
        token = re.search(r'wsToken\s*=\s*"([^"]*)"', client.text)
        query = f"?token={token.group(1)}" if token else ""
        with connect(f"ws://127.0.0.1:{stack.ports['gateway']}/viteapp/{query}", subprotocols=["vite-hmr"],
                     additional_headers={"Origin": f"http://127.0.0.1:{stack.ports['gateway']}"}) as ws:
            assert "connected" in ws.recv(timeout=10)
        result = asyncio.run(test_project(vite, stack.settings))
        assert {c["id"]: c["status"] for c in result["checks"]}["base_path"] == "ok"
    finally:
        proc.terminate()
        proc.wait(10)
        nginx_helper.apply_config(stack.env, stack.text)
