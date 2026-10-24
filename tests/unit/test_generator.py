import os
from pathlib import Path

import pytest

from gateway_manager import nginx_helper
from gateway_manager.generator import UnsafeValue, render, render_project_snippet, tok
from gateway_manager.models import Project, Settings

GOLDEN = Path(__file__).resolve().parent.parent / "golden" / "gateway.conf"


def sample():
    settings = Settings()
    projects = [
        Project(id="prajna", name="Prajna", prefix="/prajna", frontend={"port": 8200}, backend={"port": 8201},
                app_kind="vite_dev", pass_host_header=False),
        Project(id="meeting-transcriber", name="Meeting Transcriber", prefix="/meeting-transcriber",
                frontend={"port": 8300}, backend={"port": 8301, "api_path": "/backend", "api_mode": "strip_all"},
                read_timeout=7200, max_body_size="500m"),
        Project(id="static", name="Static", prefix="/static-site", frontend={"port": 8400, "path_mode": "strip"}),
        Project(id="legacy", name="Legacy", prefix="/legacy", frontend={"port": 8500, "path_mode": "rewrite"}),
        Project(id="off", name="Off", prefix="/off", frontend={"port": 8600}, enabled=False),
        Project(id="smart-finder", name="Smart Finder", exposure="port", dedicated_port=8282,
                frontend={"port": 3000}),
    ]
    return settings, projects


def test_render_matches_golden_file():
    settings, projects = sample()
    text = render(settings, projects, manager_port=8790)
    if os.environ.get("UPDATE_GOLDEN") or not GOLDEN.exists():
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(text, encoding="utf-8", newline="\n")
    assert text == GOLDEN.read_text(encoding="utf-8")


def test_rendered_config_passes_the_helper_linter():
    settings, projects = sample()
    assert nginx_helper.lint(render(settings, projects, manager_port=8790)) == []


def test_render_is_deterministic_and_ordered():
    settings, projects = sample()
    a = render(settings, projects, manager_port=8790)
    b = render(settings, list(reversed(projects)), manager_port=8790)
    assert a == b
    assert a.index("location /meeting-transcriber/") < a.index("location /prajna/")


def test_modes():
    settings, projects = sample()
    text = render(settings, projects, manager_port=8790)
    assert "location /prajna/ {\n        proxy_pass http://127.0.0.1:8200;" in text          # subpath
    assert "location /static-site/ {\n        proxy_pass http://127.0.0.1:8400/;" in text     # strip
    assert "proxy_pass http://127.0.0.1:8201/api/;" in text                                   # strip_prefix
    assert "location /meeting-transcriber/backend/ {\n        proxy_pass http://127.0.0.1:8301/;" in text  # strip_all
    assert "sub_filter '=\"/' '=\"/legacy/';" in text                                         # rewrite
    assert "proxy_set_header Host 127.0.0.1:8200;" in text                                    # vite: upstream host
    assert "proxy_read_timeout 7200s;" in text and "client_max_body_size 500m;" in text


def test_disabled_and_dedicated_and_admin():
    settings, projects = sample()
    text = render(settings, projects, manager_port=8790)
    assert "location /off/ {\n        return 404;" in text
    assert "listen 0.0.0.0:8282;" in text
    assert "listen 0.0.0.0:8281;" in text and "proxy_pass http://127.0.0.1:8790;" in text
    no_admin = render(Settings(admin_mode="localhost_only"), projects, manager_port=8790)
    assert "8281" not in no_admin


def test_landing_page_and_catch_all():
    settings, projects = sample()
    text = render(settings, projects, manager_port=8790)
    assert "location = / {" in text and "href='/prajna/'" in text
    assert "href='/off/'" not in text
    assert "location / {\n        return 404;" in text
    root = projects + [Project(id="home", name="Home", prefix="/", frontend={"port": 9000})]
    text = render(settings, root, manager_port=8790)
    assert "Projects on this gateway" not in text
    assert "location / {\n        proxy_pass http://127.0.0.1:9000;" in text


def test_nextjs_bare_prefix_is_forwarded_not_redirected():
    # Next.js basePath redirects "/x/" to "/x"; redirecting "/x" back to "/x/" would loop
    p = Project(id="sf", name="SF", prefix="/smartfinder", frontend={"port": 3001}, app_kind="nextjs")
    text = render(Settings(), [p], manager_port=8790)
    assert "location = /smartfinder {\n        proxy_pass http://127.0.0.1:3001;" in text
    assert "return 301 /smartfinder/" not in text
    assert nginx_helper.lint(text) == []
    vite = Project(id="v", name="V", prefix="/v", frontend={"port": 8200}, app_kind="vite_dev")
    assert "return 301 /v/$is_args$args;" in render(Settings(), [vite], manager_port=8790)


def test_ipv6_listen_and_upstream():
    settings = Settings(listen_addresses=["0.0.0.0", "::"])
    p = Project(id="v6", name="V6", prefix="/v6", frontend={"host": "::1", "port": 8200})
    text = render(settings, [p], manager_port=8790)
    assert "listen [::]:8280;" in text
    assert "proxy_pass http://[::1]:8200;" in text
    assert nginx_helper.lint(text) == []


def test_tok_refuses_unsafe_values():
    for bad in ("a;b", "a b", "$host", "a{", "#x", "'x'", "x\n"):
        with pytest.raises(UnsafeValue):
            tok(bad)


def test_snippet_for_editor_preview():
    _, projects = sample()
    snippet = render_project_snippet(projects[0])
    assert snippet.startswith("# ── prajna")
    assert "location /prajna/ {" in snippet and "\n    proxy_pass" in snippet


def test_sandbox_log_dir():
    settings, projects = sample()
    text = render(settings, projects, manager_port=8790, log_dir="/tmp/sb/logs")
    assert "access_log /tmp/sb/logs/gateway-8280.access.log gw_main;" in text
    assert nginx_helper.lint(text, "/tmp/sb/logs") == []
    assert nginx_helper.lint(text) != []  # production lint insists on /var/log/nginx
