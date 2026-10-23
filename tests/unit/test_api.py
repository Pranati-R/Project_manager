"""The dashboard API with a fake helper: auth, CSRF, the save pipeline and drift."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import FakeHelper
from gateway_manager.config import Config
from gateway_manager.main import create_app

PRAJNA = {"id": "prajna", "name": "Prajna", "prefix": "/prajna", "frontend": {"port": 8200}, "backend": {"port": 8201}}


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    # Unit tests do not run nginx -t (the e2e tests do)
    monkeypatch.setattr("gateway_manager.service.sandbox.validate", lambda nginx_bin, render: (None, "skipped"))
    helper = FakeHelper()
    cfg = Config(state_dir=tmp_path / "state", nginx_bin="/nonexistent/nginx", seed_file=Path("/nonexistent"),
                 frontend_dir=Path(__file__).resolve().parents[2] / "frontend", restart_targets=tmp_path / "rt.conf")
    app = create_app(cfg, helper=helper)
    return TestClient(app), helper, app


def login(client, username="a@g.com", password="123456"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf"]}


def test_health_is_public(ctx):
    client, _, _ = ctx
    assert client.get("/api/health").json()["ok"] is True


def test_everything_else_needs_login(ctx):
    client, _, _ = ctx
    for path in ("/api/projects", "/api/status", "/api/settings", "/api/logs", "/api/config/preview", "/api/meta"):
        assert client.get(path).status_code == 401, path
    assert client.post("/api/projects", json=PRAJNA).status_code == 401


def test_default_login_and_banner_flag(ctx):
    client, _, _ = ctx
    r = client.post("/api/auth/login", json={"username": "A@G.com", "password": "123456"})
    assert r.status_code == 200
    assert r.json()["password_is_default"] is True
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie


def test_wrong_password_and_throttle(ctx):
    client, _, _ = ctx
    for _ in range(5):
        assert client.post("/api/auth/login", json={"username": "a@g.com", "password": "nope"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": "a@g.com", "password": "123456"})
    assert r.status_code == 429 and "Retry-After" in r.headers


def test_csrf_required_for_changes(ctx):
    client, _, _ = ctx
    login(client)
    assert client.post("/api/projects", json=PRAJNA).status_code == 403
    assert client.post("/api/projects", json=PRAJNA, headers={"X-CSRF-Token": "wrong"}).status_code == 403


def test_add_project_saves_and_applies(ctx):
    client, helper, _ = ctx
    h = login(client)
    r = client.post("/api/projects", json=PRAJNA, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["apply"]["ok"] is True
    assert len(helper.applied) == 1 and "location /prajna/ {" in helper.applied[0]
    projects = client.get("/api/projects").json()["projects"]
    assert [p["id"] for p in projects] == ["prajna"]
    status = client.get("/api/status").json()
    assert status["last_apply"]["ok"] is True


def test_invalid_project_is_rejected_with_field_errors(ctx):
    client, helper, _ = ctx
    h = login(client)
    r = client.post("/api/projects", json={**PRAJNA, "prefix": "/x;}", "frontend": {"port": 70000}}, headers=h)
    assert r.status_code == 422
    fields = {e["field"] for e in r.json()["detail"]["errors"]}
    assert {"prefix", "frontend.port"} <= fields
    assert helper.applied == []


def test_cross_project_conflict_is_rejected(ctx):
    client, helper, _ = ctx
    h = login(client)
    client.post("/api/projects", json=PRAJNA, headers=h)
    r = client.post("/api/projects", json={**PRAJNA, "id": "copy", "name": "Copy"}, headers=h)
    assert r.status_code == 422
    assert "already used" in r.json()["detail"]["message"]
    assert len(helper.applied) == 1


def test_port_conflict_from_helper_scan_blocks_save(ctx):
    client, helper, _ = ctx
    h = login(client)
    helper.scan_result = {"ok": True, "lint": [], "conflicts": ["port 8280 is already used by another nginx site (x)"]}
    r = client.post("/api/projects", json=PRAJNA, headers=h)
    assert r.status_code == 422 and "another nginx site" in r.json()["detail"]["message"]
    assert client.get("/api/projects").json()["projects"] == []


def test_failed_apply_keeps_change_and_reports_drift(ctx):
    client, helper, _ = ctx
    h = login(client)
    helper.next_apply = {"ok": False, "stage": "nginx-test", "message": "nginx -t failed", "output": "boom"}
    r = client.post("/api/projects", json=PRAJNA, headers=h)
    assert r.status_code == 200 and r.json()["apply"]["ok"] is False
    status = client.get("/api/status").json()
    assert status["last_apply"]["ok"] is False and status["drift"]["in_sync"] is False
    helper.next_apply = {"ok": True, "message": "applied"}
    r = client.post("/api/config/apply", headers=h)
    assert r.json()["apply"]["ok"] is True


def test_revert_to_last_applied(ctx):
    client, helper, _ = ctx
    h = login(client)
    client.post("/api/projects", json=PRAJNA, headers=h)
    helper.next_apply = {"ok": False, "stage": "bind", "message": "port busy"}
    client.post("/api/projects", json={**PRAJNA, "id": "two", "name": "Two", "prefix": "/two",
                                       "frontend": {"port": 8300}, "backend": None}, headers=h)
    assert len(client.get("/api/projects").json()["projects"]) == 2
    helper.next_apply = {"ok": True, "message": "applied"}
    r = client.post("/api/config/revert", headers=h)
    assert r.status_code == 200
    assert [p["id"] for p in r.json()["state"]["projects"]] == ["prajna"]


def test_enable_disable_edit_delete(ctx):
    client, helper, _ = ctx
    h = login(client)
    client.post("/api/projects", json=PRAJNA, headers=h)
    assert client.post("/api/projects/prajna/disable", headers=h).status_code == 200
    assert "return 404" in helper.applied[-1]
    assert client.post("/api/projects/prajna/enable", headers=h).status_code == 200
    r = client.put("/api/projects/prajna", json={**PRAJNA, "frontend": {"port": 8250}}, headers=h)
    assert r.status_code == 200 and "127.0.0.1:8250" in helper.applied[-1]
    assert client.put("/api/projects/prajna", json={**PRAJNA, "id": "renamed"}, headers=h).status_code == 400
    assert client.delete("/api/projects/prajna", headers=h).status_code == 200
    assert client.delete("/api/projects/prajna", headers=h).status_code == 404


def test_auto_apply_off(ctx):
    client, helper, _ = ctx
    h = login(client)
    settings = client.get("/api/settings").json()
    client.put("/api/settings", json={**settings, "auto_apply": False}, headers=h)
    n = len(helper.applied)
    r = client.post("/api/projects", json=PRAJNA, headers=h)
    assert r.json()["apply"] is None and len(helper.applied) == n


def test_preview_does_not_save(ctx):
    client, helper, _ = ctx
    login(client)
    r = client.post("/api/projects/preview", json=PRAJNA)
    assert r.status_code == 200 and "location /prajna/" in r.json()["snippet"] and not r.json()["errors"]
    r = client.post("/api/projects/preview", json={**PRAJNA, "prefix": "bad prefix"})
    assert r.json()["errors"] and r.json()["snippet"] == ""
    assert client.get("/api/projects").json()["projects"] == []


def test_password_change_and_users(ctx):
    client, _, _ = ctx
    h = login(client)
    assert client.post("/api/auth/password", json={"current": "wrong", "new": "abcdef"}, headers=h).status_code == 400
    assert client.post("/api/auth/password", json={"current": "123456", "new": "abc"}, headers=h).status_code == 400
    assert client.post("/api/auth/password", json={"current": "123456", "new": "newpass1"}, headers=h).status_code == 200
    assert client.get("/api/auth/me").json()["password_is_default"] is False
    r = client.post("/api/users", json={"username": "ops@example.com", "password": "secret1"}, headers=h)
    assert [u["username"] for u in r.json()["users"]] == ["a@g.com", "ops@example.com"]
    assert client.delete("/api/users/ops@example.com", headers=h).status_code == 200
    assert client.delete("/api/users/a@g.com", headers=h).status_code == 400  # last user


def test_restart_needs_an_allowlisted_target(ctx):
    client, helper, _ = ctx
    h = login(client)
    client.post("/api/projects", json={**PRAJNA, "restart_target": "prajna-web"}, headers=h)
    assert client.post("/api/projects/prajna/restart", headers=h).json()["ok"] is True
    assert helper.restarted == ["prajna-web"]


def test_logs_and_guide_and_meta(ctx):
    client, _, _ = ctx
    h = login(client)
    client.post("/api/projects", json={**PRAJNA, "app_kind": "vite_dev"}, headers=h)
    assert client.get("/api/logs?source=access&filter=line 1").json()["lines"] == ["access 8280 line 1"]
    assert client.get("/api/logs?source=audit").json()["lines"]
    assert client.get("/api/logs?source=../../etc/passwd").status_code == 400
    g = client.get("/api/projects/prajna/guide").json()
    assert any("--base /prajna/" in (s["code"] or "") for s in g["sections"])
    meta = client.get("/api/meta").json()
    assert {p["value"] for p in meta["presets"]} >= {"vite_dev", "static_dist", "nextjs", "prebuilt"}


def test_security_headers_and_static_dashboard(ctx):
    client, _, _ = ctx
    r = client.get("/")
    assert r.status_code == 200 and "Gateway Manager" in r.text
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY"
    assert client.get("/api/health").headers["cache-control"] == "no-store"


def test_import_export(ctx):
    client, _, _ = ctx
    h = login(client)
    r = client.post("/api/import", json={"projects": [PRAJNA], "mode": "replace"}, headers=h)
    assert r.status_code == 200
    data = client.get("/api/export").json()
    assert data["projects"][0]["id"] == "prajna"
