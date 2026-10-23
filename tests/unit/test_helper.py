"""The root helper: linter, apply/rollback and the conflict scan, with fake nginx/systemctl."""
import os
import sys

import pytest

from gateway_manager import nginx_helper as nh
from gateway_manager.generator import render
from gateway_manager.models import Project, Settings

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the helper is Linux-only")


def config(port=8280, prefix="/prajna", **settings):
    s = Settings(gateway_port=port, **settings)
    p = Project(id="prajna", name="Prajna", prefix=prefix, frontend={"port": 8200}, backend={"port": 8201})
    return render(s, [p], manager_port=8790)


class FakeEnv(nh.Env):
    """Files in a temp dir; nginx -t, reload and the listening sockets are simulated."""

    bind_wait_seconds = 0.2

    def __init__(self, tmp):
        self.staged_dir = str(tmp / "staging")
        self.live_dir = str(tmp / "nginx" / "nginx-gateway")
        self.stub = str(tmp / "nginx" / "conf.d" / "nginx-gateway.conf")
        self.backups = str(tmp / "backups")
        self.lock_file = str(tmp / "helper.lock")
        self.restart_targets = str(tmp / "restart-targets.conf")
        os.makedirs(self.staged_dir)
        os.makedirs(os.path.dirname(self.stub))
        self.test_ok, self.active, self.binds = True, True, True
        self.reloads, self.dump, self.other_listeners = 0, "", set()
        self.loaded = None  # the config nginx is "running"

    def nginx_installed(self):
        return True

    def nginx_test(self):
        return self.test_ok, "nginx: configuration file /etc/nginx/nginx.conf test " + ("is successful" if self.test_ok else
                                                                                         "failed\nnginx: [emerg] x in /etc/nginx/sites-enabled/other:3")

    def nginx_dump(self):
        return True, self.dump, ""

    def is_active(self):
        return self.active

    def reload(self):
        self.reloads += 1
        self.loaded = nh.read_live(self)
        return True, ""

    def listening(self):
        ports = set(self.other_listeners)
        if self.binds and self.loaded:
            ports |= nh.listen_ports(self.loaded)
        return ports


@pytest.fixture
def env(tmp_path):
    return FakeEnv(tmp_path)


def test_lint_accepts_generated_and_rejects_everything_else():
    assert nh.lint(config()) == []
    bad = {
        "include /etc/shadow;": "not allowed at the top level",
        "server { listen 9000; include x; }": "not allowed here",
        "server { listen 9000; location / { alias /etc/; } }": "not allowed here",
        "server { listen 9000; location / { root /; } }": "not allowed here",
        "server { listen 80; }": "port 80",
        "server { listen 9000 default_server; }": "argument",
        "server { listen 9000; error_log /etc/passwd; }": "gateway-",
        "server { listen 9000; access_log /var/log/nginx/x.log combined; }": "gateway-",
        "server { listen 9000; location / { proxy_pass http://unix:/run/x.sock; } }": "target",
        "server { listen 9000; location / { proxy_pass http://example.com; } }": "target",
        "server { listen 9000; location ~ \\.php$ { return 404; } }": "plain prefix",
        "server { listen 9000; location / { proxy_set_header X-Secret $http_cookie; } }": "not allowed",
        "load_module modules/x.so;": "not allowed",
        "map $request_uri $evil { default 1; }": "gw_ maps",
        "server { listen 9000; server_name example.com; }": "server_name _",
        "server { listen 9000; location / { return 200 \"$http_cookie\"; } }": "variables",
        "server { listen 9000; location / { sub_filter a $http_cookie; } }": "variables",
        "server { listen 9000; ": "missing }",
        "server { listen 9000; location / { proxy_set_header Host \"a\nb\"; } }": "not allowed",
    }
    for text, expect in bad.items():
        errors = nh.lint(text)
        assert errors, text
        assert any(expect in e for e in errors), (text, errors)


def test_tokenizer_handles_quotes_and_comments():
    toks = nh.tokenize("a 'b c' \"d\\\"e\" # comment ;\n;")
    assert [t[1] for t in toks] == ["a", "b c", 'd"e', ";"]


def test_apply_installs_creates_stub_and_reloads(env):
    text = config()
    result = nh.apply_config(env, text)
    assert result["ok"] and result["reloaded"]
    assert nh.read_live(env) == text
    assert open(env.stub).read() == nh.STUB_TEXT
    assert env.reloads == 1
    assert result["backup"] is None
    # second change: previous version backed up
    text2 = config(prefix="/prajna2")
    result = nh.apply_config(env, text2)
    assert result["ok"] and result["backup"]
    assert nh.list_backups(env)[0]["id"] == result["backup"]
    assert nh.read_backup(env, result["backup"]) == text


def test_unchanged_config_is_a_no_op(env):
    nh.apply_config(env, config())
    result = nh.apply_config(env, config())
    assert result["ok"] and result["applied"] is False and env.reloads == 1


def test_failed_nginx_test_rolls_back(env):
    nh.apply_config(env, config())
    env.test_ok = False
    with pytest.raises(nh.HelperFailure) as e:
        nh.apply_config(env, config(prefix="/changed"))
    assert e.value.result["stage"] == "nginx-test"
    assert e.value.result["foreign_files"] == ["/etc/nginx/sites-enabled/other"]
    assert nh.read_live(env) == config()  # previous config kept
    assert env.reloads == 1


def test_first_apply_failure_removes_everything(env):
    env.test_ok = False
    with pytest.raises(nh.HelperFailure):
        nh.apply_config(env, config())
    assert nh.read_live(env) is None
    assert not os.path.exists(env.stub)


def test_bind_failure_rolls_back_and_reloads(env):
    nh.apply_config(env, config())
    env.binds = False
    with pytest.raises(nh.HelperFailure) as e:
        nh.apply_config(env, config(port=9280))
    assert e.value.result["stage"] == "bind"
    assert nh.read_live(env) == config()
    assert env.reloads == 3  # apply, failed apply, rollback


def test_stopped_nginx_is_not_started(env):
    env.active = False
    result = nh.apply_config(env, config())
    assert result["ok"] and result["nginx_active"] is False and env.reloads == 0
    assert nh.read_live(env) == config()


def test_conflicts_with_other_sites_and_programs(env):
    env.dump = ("# configuration file /etc/nginx/nginx.conf:\nhttp { }\n"
                "# configuration file /etc/nginx/sites-enabled/other:\nserver {\n    listen 8280;\n}\n"
                "# configuration file /etc/nginx/conf.d/maps.conf:\nmap $a $gw_connection_upgrade { default 1; }\n")
    with pytest.raises(nh.HelperFailure) as e:
        nh.apply_config(env, config())
    msgs = " ".join(e.value.result["errors"])
    assert "port 8280 is already used by another nginx site (/etc/nginx/sites-enabled/other)" in msgs
    assert "$gw_connection_upgrade is already defined" in msgs
    env.dump = ""
    env.other_listeners = {8281}
    with pytest.raises(nh.HelperFailure) as e:
        nh.apply_config(env, config())
    assert "port 8281 is already in use by another program" in " ".join(e.value.result["errors"])


def test_our_own_ports_are_not_conflicts(env):
    nh.apply_config(env, config())
    assert nh.conflicts(env, config(prefix="/other")) == []


def test_lint_failure_never_touches_nginx(env):
    with pytest.raises(nh.HelperFailure) as e:
        nh.apply_config(env, "include /etc/shadow;")
    assert e.value.result["stage"] == "lint"
    assert nh.read_live(env) is None and env.reloads == 0


def test_test_full_always_restores(env):
    nh.apply_config(env, config())
    result = nh.test_full(env, config(prefix="/candidate"))
    assert result["ok"]
    assert nh.read_live(env) == config()


def test_read_staged_refuses_symlinks(env, tmp_path):
    secret = tmp_path / "secret.conf"
    secret.write_text("server { listen 9; }")
    os.symlink(secret, os.path.join(env.staged_dir, env.staged_name))
    with pytest.raises(nh.HelperFailure):
        nh.read_staged(env)
    os.unlink(os.path.join(env.staged_dir, env.staged_name))
    os.rename(env.staged_dir, env.staged_dir + ".real")
    os.symlink(env.staged_dir + ".real", env.staged_dir)
    with pytest.raises(nh.HelperFailure):
        nh.read_staged(env)


def test_restart_targets_allowlist(env, tmp_path):
    with open(env.restart_targets, "w") as f:
        f.write("# comment\nweb systemd web.service\nbad systemd ../x\nsf docker smart-finder\nx docker a;b\n")
    targets = nh.read_restart_targets(env.restart_targets)
    assert targets == {"web": ("systemd", "web.service"), "sf": ("docker", "smart-finder")}
    with pytest.raises(nh.HelperFailure):
        nh.restart_target(env, "bad")


def test_backup_ids_are_validated(env):
    for bad in ("../../etc/shadow", "2026", "20261023T000000Z/../x"):
        with pytest.raises(nh.HelperFailure):
            nh.read_backup(env, bad)


def test_proc_net_parser():
    v4 = ("  sl  local_address rem_address   st\n"
          "   0: 0100007F:1F90 00000000:0000 0A 00000000:00000000\n"
          "   1: 00000000:0050 00000000:0000 0A 00000000:00000000\n"
          "   2: 0100007F:2058 0100007F:9C40 01 00000000:00000000\n")
    assert nh.parse_proc_net(v4) == [("127.0.0.1", 8080), ("0.0.0.0", 80)]
    v6 = ("  sl  local_address rem_address st\n"
          "   0: 00000000000000000000000001000000:1F90 00000000000000000000000000000000:0000 0A 0\n")
    assert nh.parse_proc_net(v6, ipv6=True) == [("::1", 8080)]


def test_main_refuses_without_root(capsys, monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    assert nh.main(["status"]) == 1
    assert "root" in capsys.readouterr().out
