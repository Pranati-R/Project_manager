from gateway_manager.diagnostics import analyze_html, exposure_checks, gateway_urls
from gateway_manager.guide import build_guide, presets_for_api
from gateway_manager.models import Project, Settings


def test_html_analysis_for_root_built_vite_app():
    html = """<script type="module" src="/@vite/client"></script>
              <script type="module" src="/src/main.tsx"></script><link href="/assets/x.css" rel="stylesheet">
              <a href="https://example.com/">x</a><img src="//cdn.example.com/a.png"><img src="logo.png">"""
    info = analyze_html(html, "/prajna")
    assert info["vite_dev"] is True
    assert info["outside"] == ["/@vite/client", "/src/main.tsx", "/assets/x.css"]
    assert info["inside"] == []


def test_html_analysis_for_correct_base():
    html = '<script type="module" src="/prajna/@vite/client"></script><link href="/prajna/assets/x.css">'
    info = analyze_html(html, "/prajna")
    assert info["outside"] == [] and len(info["inside"]) == 2
    assert analyze_html("Blocked request. This host (x.ts.net) is not allowed.", "/p")["host_blocked"]


def test_exposure_checks():
    p = Project(id="p", name="P", prefix="/p", frontend={"port": 8200}, backend={"port": 8201}, runtime="docker")
    checks = {c["id"]: c for c in exposure_checks(p, {8200: ["0.0.0.0"], 8201: ["127.0.0.1"]})}
    assert checks["frontend_exposure"]["status"] == "warn" and "127.0.0.1:8200" in checks["frontend_exposure"]["hint"]
    assert checks["backend_exposure"]["status"] == "ok"
    checks = exposure_checks(p, {8200: ["::1"]})
    assert checks[0]["status"] == "error" and "::1" in checks[0]["detail"]


def test_gateway_urls():
    s = Settings()
    urls = gateway_urls(s, {"ipv4": ["100.101.102.103"], "dns_name": "box.tail1234.ts.net"})
    assert urls["gateway"] == ["http://box.tail1234.ts.net:8280/", "http://100.101.102.103:8280/"]
    assert urls["admin"][1] == "http://100.101.102.103:8281/"
    assert "admin" not in gateway_urls(Settings(admin_mode="localhost_only"), {"ipv4": [], "dns_name": None})


def test_guides():
    vite = Project(id="prajna", name="Prajna", prefix="/prajna", frontend={"port": 8200}, backend={"port": 8201},
                   app_kind="vite_dev", runtime="tmux", pass_host_header=False)
    g = build_guide(vite, 8280, "box")
    text = "\n".join((s["code"] or "") + s["text"] for s in g["sections"])
    assert g["url"] == "http://box:8280/prajna/"
    assert "npm run dev -- --base /prajna/ --host 127.0.0.1 --port 8200 --strictPort" in text
    assert "basename={import.meta.env.BASE_URL}" in text
    assert not g["warnings"]

    docker = Project(id="sf", name="SF", prefix="/sf", frontend={"port": 8300, "path_mode": "subpath"},
                     app_kind="static_dist", runtime="docker")
    g = build_guide(docker, 8280)
    assert any("expects path mode 'strip'" in w for w in g["warnings"])
    assert any("-p 127.0.0.1:8300:80" in (s["code"] or "") for s in g["sections"])

    own = Project(id="sf", name="SF", exposure="port", dedicated_port=8282, frontend={"port": 3000}, app_kind="nextjs")
    g = build_guide(own, 8280, "box")
    assert g["url"] == "http://box:8282/"
    assert any("No base-path changes" in s["title"] for s in g["sections"])
    assert {p["value"] for p in presets_for_api()} >= {"vite_dev", "nextjs"}
