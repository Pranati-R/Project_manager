import json
import time

from gateway_manager.auth import (DEFAULT_PASSWORD, DEFAULT_USER, LoginThrottle, SessionManager, UserStore,
                                  hash_password, verify_password)
from gateway_manager.models import Project
from gateway_manager.store import State, Store


def test_password_hashing():
    h = hash_password("123456")
    assert h.startswith("scrypt$") and "123456" not in h
    assert verify_password("123456", h)
    assert not verify_password("1234567", h)
    assert not verify_password("x", "garbage")


def test_default_user_created_once(tmp_path):
    users = UserStore(tmp_path / "users.json")
    assert users.ensure_default() is True
    assert users.verify(DEFAULT_USER, DEFAULT_PASSWORD)
    assert users.is_default_password(DEFAULT_USER)
    assert users.ensure_default() is False
    users.set_password(DEFAULT_USER, "changed1")
    assert not users.is_default_password(DEFAULT_USER)
    assert users.ensure_default() is False
    assert not users.verify(DEFAULT_USER, DEFAULT_PASSWORD)
    raw = (tmp_path / "users.json").read_text()
    assert "changed1" not in raw and json.loads(raw)["users"][DEFAULT_USER]["hash"].startswith("scrypt$")


def test_sessions_bound_to_ip_and_expire():
    sm = SessionManager(idle_seconds=60, max_seconds=120)
    token, session = sm.create("a@g.com", "100.64.0.5")
    assert sm.get(token, "100.64.0.5") is session
    assert sm.get(token, "100.64.0.9") is None          # another address: rejected and dropped
    assert sm.get(token, "100.64.0.5") is None
    token, session = sm.create("a@g.com", "1.1.1.1")
    session.last_seen -= 61
    assert sm.get(token, "1.1.1.1") is None
    t1, _ = sm.create("u", "ip")
    t2, _ = sm.create("u", "ip")
    sm.revoke_user("u", keep_token=t2)
    assert sm.get(t1, "ip") is None and sm.get(t2, "ip") is not None


def test_throttle():
    t = LoginThrottle(max_failures=3, window=60, lockout=30)
    for _ in range(3):
        assert t.retry_after("ip:x") == 0
        t.failure("ip:x")
    assert 0 < t.retry_after("ip:x") <= 30
    t.success("ip:x")
    assert t.retry_after("ip:x") == 0


def test_store_atomic_save_and_history(tmp_path):
    store = Store(tmp_path / "state.json", tmp_path / "history")
    assert store.load().projects == []
    for i in range(25):
        state = store.load()
        state.projects = [Project(id=f"p{i}", name=f"P{i}", prefix=f"/p{i}", frontend={"port": 9000 + i})]
        store.save(state)
        time.sleep(0.002)
    assert store.load().projects[0].id == "p24"
    assert len(list((tmp_path / "history").glob("state-*.json"))) == 20
    assert not list(tmp_path.glob(".state.json.*"))  # no temp files left behind


def test_seed(tmp_path):
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({"projects": [{"id": "prajna", "name": "Prajna", "prefix": "/prajna",
                                              "frontend": {"port": 8200}}]}))
    store = Store(tmp_path / "state.json", tmp_path / "history")
    state = store.seed(seed, gateway_port=9280)
    assert state.settings.gateway_port == 9280 and state.projects[0].id == "prajna"
    assert State.model_validate_json((tmp_path / "state.json").read_text()).settings.gateway_port == 9280
