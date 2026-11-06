"""QR pairing: one-time tokens, trusted permanent devices, and approval on the desktop."""
import json

from bc250cc.infrastructure import web_devices, web_pairing


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(web_devices, "app_config_dir", lambda: tmp_path)
    monkeypatch.setattr(web_pairing, "app_config_dir", lambda: tmp_path)


def test_pairing_token_works_once_and_is_stored_hashed(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    token = web_pairing.issue()
    path = tmp_path / "web-pairing.json"
    assert path.stat().st_mode & 0o777 == 0o600
    assert token not in path.read_text()
    assert web_pairing.valid(token)
    assert web_pairing.consume(token) is True
    assert web_pairing.consume(token) is False
    assert not web_pairing.valid(token)
    assert web_pairing.consume("") is False and web_pairing.consume("guess") is False


def test_pairing_token_expires(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    now = [1000.0]
    monkeypatch.setattr(web_pairing.time, "time", lambda: now[0])
    token = web_pairing.issue()
    now[0] += web_pairing.TTL_SECONDS + 1
    assert web_pairing.consume(token) is False
    assert json.loads((tmp_path / "web-pairing.json").read_text()) == {}


def test_outstanding_tokens_are_capped(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    now = [1000.0]
    monkeypatch.setattr(web_pairing.time, "time", lambda: now[0])
    tokens = []
    for _ in range(web_pairing.MAX_OUTSTANDING + 2):
        tokens.append(web_pairing.issue())
        now[0] += 1
    assert not web_pairing.valid(tokens[0]) and not web_pairing.valid(tokens[1])
    assert all(web_pairing.valid(token) for token in tokens[2:])


def test_a_trusted_device_has_control_and_never_expires(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    now = [100000.0]
    monkeypatch.setattr(web_devices.time, "time", lambda: now[0])
    web_devices.register("paired", "192.168.0.25", "Phone", 8 * 3600, trusted=True)
    web_devices.register("typed", "192.168.0.26", "Phone", 8 * 3600)
    assert web_devices.session("paired")["control"]
    assert not web_devices.session("typed")["control"]
    now[0] += 5 * 365 * 24 * 3600
    paired = web_devices.session("paired")
    assert paired and web_devices.is_permanent(paired)
    assert not web_devices.session("typed")


def test_approving_a_device_grants_control_and_removes_every_limit(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    now = [100000.0]
    monkeypatch.setattr(web_devices.time, "time", lambda: now[0])
    device = web_devices.register("typed", "192.168.0.26", "Phone", 8 * 3600)
    web_devices.approve(device)
    now[0] += web_devices.IDLE_SECONDS * 10 + 10 * 24 * 3600
    entry = web_devices.session("typed")
    assert entry["control"] and web_devices.is_permanent(entry)
    assert entry["idle_seconds"] is None
