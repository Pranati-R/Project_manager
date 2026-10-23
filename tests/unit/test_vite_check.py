import json

from gateway_manager.vite_check import analyze, format_report


def make_app(tmp_path, *, config, files):
    (tmp_path / "package.json").write_text(json.dumps({
        "scripts": {"dev": "vite --host", "build": "vite build"},
        "dependencies": {"react-router-dom": "^7"}, "devDependencies": {"vite": "^8"}}))
    (tmp_path / "vite.config.ts").write_text(config)
    for name, text in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return tmp_path


def levels(rep):
    return [(f.level, f.message) for f in rep.findings]


def test_finds_what_breaks_under_a_prefix(tmp_path):
    app = make_app(tmp_path, config="export default { server: { host: '0.0.0.0', hmr: { port: 24678 } } }", files={
        "src/App.tsx": "<BrowserRouter>\n<img src=\"/logo.svg\" />\n",
        "src/api.ts": "export const API = '/api';\nfetch('/api/items')\nnew WebSocket('/ws')\n",
        "node_modules/x/index.js": "fetch('/ignored')",
    })
    rep = analyze(app, "/prajna/")
    text = format_report(rep)
    msgs = " | ".join(m for _, m in levels(rep))
    assert "<BrowserRouter> without basename" in msgs
    assert "fetch '/api/items'" in msgs and "new WebSocket '/ws'" in msgs
    assert "the API base defaults to '/api'" in msgs
    assert "hard-coded public file /logo.svg" in msgs
    assert "hmr.port" in msgs and "all interfaces" in msgs
    assert "/ignored" not in msgs
    assert "--base /prajna/" in text and "nothing was changed" in text
    assert "script 'dev' exposes Vite" in msgs


def test_ready_app(tmp_path):
    app = make_app(tmp_path, config="export default defineConfig({ base: process.env.VITE_BASE_PATH ?? '/' })", files={
        "src/main.tsx": "<BrowserRouter basename={import.meta.env.BASE_URL}>\n"
                        "const API = import.meta.env.VITE_API_BASE || `${import.meta.env.BASE_URL}api`\n",
    })
    rep = analyze(app, "/prajna")
    assert not [f for f in rep.findings if f.level in ("error", "warn") and "script" not in f.message]
    assert any("reads base from the environment" in f.message for f in rep.findings)
    assert any("VITE_API_BASE" in f.message for f in rep.findings)


def test_hash_router_and_relative_base(tmp_path):
    app = make_app(tmp_path, config="export default { base: './' }", files={"src/App.tsx": "<HashRouter>"})
    msgs = " ".join(m for _, m in levels(analyze(app, "/mt/")))
    assert "hash router" in msgs and "base './'" in msgs


def test_never_writes(tmp_path):
    app = make_app(tmp_path, config="export default {}", files={"src/App.tsx": "<BrowserRouter>"})
    before = {p: p.stat().st_mtime_ns for p in app.rglob("*")}
    analyze(app, "/x/")
    assert before == {p: p.stat().st_mtime_ns for p in app.rglob("*")}
