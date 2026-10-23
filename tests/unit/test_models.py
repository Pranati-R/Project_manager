import pytest
from pydantic import ValidationError

from gateway_manager.models import Project, Settings, check_state


def project(**kw):
    base = {"id": "prajna", "name": "Prajna", "prefix": "/prajna", "frontend": {"port": 8200}}
    base.update(kw)
    return Project(**base)


def test_valid_project_defaults():
    p = project(backend={"port": 8201})
    assert p.frontend.host == "127.0.0.1"
    assert p.frontend.path_mode.value == "subpath"
    assert p.backend.api_path == "/api" and p.backend.api_mode.value == "strip_prefix"
    assert p.route_prefix == "/prajna"


@pytest.mark.parametrize("prefix", ["/x;}", "/x y", "/x$host", "/X", "/../etc", "/x\nlisten 80", "/ünï", "x//y",
                                    "/a/b/c/d/e", "/-x", "/x'"])
def test_prefix_rejects_injection_and_junk(prefix):
    with pytest.raises(ValidationError):
        project(prefix=prefix)


def test_prefix_is_normalized():
    assert project(prefix="/prajna/").prefix == "/prajna"
    assert project(prefix=" /a/b ").prefix == "/a/b"


@pytest.mark.parametrize("pid", ["Prajna", "pr ajna", "-x", "x-", "a" * 41, "x;", "", "prajna\n"])
def test_id_rules(pid):
    with pytest.raises(ValidationError):
        project(id=pid)


@pytest.mark.parametrize("host", ["localhost", "example.com", "127.0.0.1;", "1.2.3.4 5", "$host"])
def test_upstream_host_must_be_an_ip(host):
    with pytest.raises(ValidationError):
        project(frontend={"host": host, "port": 8200})


def test_ipv6_upstream_is_bracketed():
    p = project(frontend={"host": "::1", "port": 8200})
    assert p.frontend.hostport == "[::1]:8200"


def test_reserved_prefix():
    with pytest.raises(ValidationError):
        project(prefix="/gateway-health")


def test_dedicated_port_exposure():
    p = project(exposure="port", dedicated_port=8282, prefix="/ignored")
    assert p.prefix is None and p.is_root and p.route_prefix == ""
    with pytest.raises(ValidationError):
        project(exposure="port")
    with pytest.raises(ValidationError):
        project(exposure="port", dedicated_port=80)


def test_root_project_forces_subpath():
    p = project(prefix="/", frontend={"port": 8200, "path_mode": "strip"})
    assert p.frontend.path_mode.value == "subpath"


def test_name_and_size_rules():
    with pytest.raises(ValidationError):
        project(name="<script>")
    with pytest.raises(ValidationError):
        project(max_body_size="10 m")
    assert project(max_body_size="10M").max_body_size == "10m"


def test_settings_validation():
    s = Settings(listen_addresses=["0.0.0.0", "0.0.0.0", "::"], allowed_cidrs=["100.64.0.1/10"])
    assert s.listen_addresses == ["0.0.0.0", "::"]
    assert s.allowed_cidrs == ["100.64.0.0/10"]
    for bad in ({"gateway_port": 80}, {"gateway_port": 443}, {"gateway_port": 1023},
                {"gateway_port": 8281, "admin_port": 8281}, {"listen_addresses": ["eth0"]},
                {"allowed_cidrs": ["tailnet"]}):
        with pytest.raises(ValidationError):
            Settings(**bad)


def test_cross_project_checks():
    s = Settings()
    a = project()
    errors, _ = check_state(s, [a, project(id="other", name="Other")], 8790)
    assert any("already used" in e.message for e in errors)

    errors, _ = check_state(s, [project(frontend={"port": 8280})], 8790)
    assert any("proxy to itself" in e.message for e in errors)

    errors, _ = check_state(s, [project(frontend={"port": 8790})], 8790)
    assert any("manager" in e.message for e in errors)

    roots = [project(id="r1", name="R1", prefix="/"), project(id="r2", name="R2", prefix="/", frontend={"port": 9000})]
    errors, _ = check_state(s, roots, 8790)
    assert any("only one project" in e.message for e in errors)

    ded = [project(id="d1", name="D1", exposure="port", dedicated_port=8281)]
    errors, _ = check_state(s, ded, 8790)
    assert any("admin port" in e.message for e in errors)

    errors, warnings = check_state(s, [a, project(id="sub", name="Sub", prefix="/prajna/sub", frontend={"port": 8200})], 8790)
    assert not errors
    assert any("nested" in w.message for w in warnings)
    assert any("also used" in w.message for w in warnings)
