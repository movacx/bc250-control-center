"""LAN boundaries, durable permission changes and authenticated local HTTPS."""
import json
import ssl
import threading
import urllib.request
from types import SimpleNamespace

import pytest

from bc250cc.infrastructure import web_devices, web_network, web_tls
from frontends.web import server


def test_lan_policy_accepts_only_connected_physical_home_subnets(monkeypatch):
    interfaces = [
        {"ifname": "wlan0", "addr_info": [{"local": "192.168.0.15", "prefixlen": 24}]},
        {"ifname": "docker0", "addr_info": [{"local": "172.17.0.1", "prefixlen": 16}]},
        {"ifname": "wg0", "addr_info": [{"local": "10.8.0.1", "prefixlen": 24}]},
        {"ifname": "eth1", "addr_info": [{"local": "8.8.8.8", "prefixlen": 24}]},
    ]
    monkeypatch.setattr(web_network.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=json.dumps(interfaces)))
    networks = web_network.home_networks()
    assert networks == ["192.168.0.0/24"]
    for address in ["127.0.0.1", "::1", "192.168.0.25"]:
        assert web_network.allows(address, networks)
    for address in ["192.168.1.25", "172.17.0.2", "10.8.0.2", "8.8.8.8", "invalid"]:
        assert not web_network.allows(address, networks)


def test_lan_discovery_failure_does_not_widen_access(monkeypatch):
    monkeypatch.setattr(web_network.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("no ip")))
    assert web_network.home_networks() == []
    assert not web_network.allows("192.168.0.25", web_network.home_networks())


def test_device_registry_is_private_and_never_contains_the_session_secret(tmp_path, monkeypatch):
    monkeypatch.setattr(web_devices, "app_config_dir", lambda: tmp_path)
    token = "a-secret-browser-cookie"
    device = web_devices.register(token, "192.168.0.25", "Phone", 8 * 3600)
    path = tmp_path / "web-devices.json"
    assert path.stat().st_mode & 0o777 == 0o600
    assert token not in path.read_text()
    assert not web_devices.session(token)["control"]
    web_devices.set_control(device, True)
    assert web_devices.session(token)["control"]
    web_devices.revoke(device)
    assert web_devices.session(token) == {}


def test_device_registry_has_idle_and_absolute_expiry(tmp_path, monkeypatch):
    monkeypatch.setattr(web_devices, "app_config_dir", lambda: tmp_path)
    now = [100000.0]
    monkeypatch.setattr(web_devices.time, "time", lambda: now[0])
    web_devices.register("idle", "192.168.0.25", "Phone", 8 * 3600)
    now[0] += web_devices.IDLE_SECONDS + 1
    assert not web_devices.session("idle")
    web_devices.register("absolute", "192.168.0.25", "Phone", 100)
    now[0] += 101
    assert not web_devices.session("absolute")
    assert json.loads((tmp_path / "web-devices.json").read_text()) == {}


def test_device_registry_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(web_devices, "app_config_dir", lambda: tmp_path)
    for i in range(web_devices.MAX_DEVICES):
        web_devices.register(str(i), "192.168.0.25", "Phone", 1000)
    with pytest.raises(PermissionError):
        web_devices.register("overflow", "192.168.0.25", "Phone", 1000)


def test_certificate_is_trusted_by_its_local_ca_and_serves_verified_https(tmp_path, monkeypatch):
    monkeypatch.setattr(web_tls, "app_config_dir", lambda: tmp_path)
    monkeypatch.setattr(web_tls, "addresses", lambda: ["192.168.0.15"])
    cert, key = web_tls.certificate()
    authority = web_tls.trust_certificate()
    assert key.stat().st_mode & 0o777 == 0o600
    assert (authority.parent / "authority.key").stat().st_mode & 0o777 == 0o600
    assert web_tls.fingerprint(authority) != web_tls.fingerprint(cert)
    assert web_tls.certificate() == (cert, key)
    original = cert.read_bytes()
    assert original == web_tls.certificate()[0].read_bytes()
    context = ssl.create_default_context(cafile=str(authority))
    httpd = server.Server(("127.0.0.1", 0), SimpleNamespace(language="en", ssh_sessions={}, local_sessions={}), certificate=(cert, key))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"https://127.0.0.1:{httpd.server_address[1]}/api/version", context=context, timeout=5) as response:
            assert response.status == 200
            assert "version" in json.loads(response.read())
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
    # A new LAN address renews only the leaf; the phone keeps trusting the CA.
    fingerprint = web_tls.fingerprint(authority)
    monkeypatch.setattr(web_tls, "addresses", lambda: ["192.168.0.16"])
    web_tls.certificate()
    assert cert.read_bytes() != original
    assert web_tls.fingerprint(authority) == fingerprint


def test_owner_selected_expiry_replaces_old_caps_for_only_one_device(tmp_path, monkeypatch):
    monkeypatch.setattr(web_devices, "app_config_dir", lambda: tmp_path)
    now = [100000.0]
    monkeypatch.setattr(web_devices.time, "time", lambda: now[0])
    phone = web_devices.register("phone", "192.168.0.2", "Phone", 8 * 3600)
    web_devices.register("other", "192.168.0.3", "Tablet", 8 * 3600)
    web_devices.set_control(phone, True)
    web_devices.set_lifetime(phone, 7 * 86400)
    assert web_devices.session("phone")["control"] is True
    assert web_devices.deadline(web_devices.session("phone")) == now[0] + 7 * 86400
    now[0] += 9 * 3600
    assert web_devices.session("phone")["duration_seconds"] == 7 * 86400
    assert not web_devices.session("other")
    web_devices.set_lifetime(phone, 60)
    deadline = web_devices.deadline(web_devices.session("phone"))
    now[0] += 61
    assert now[0] > deadline
    assert not web_devices.session("phone")


@pytest.mark.parametrize("seconds", [True, False, 0, -1, 59, "3600", 60.5, web_devices.MAX_SESSION_SECONDS + 1])
def test_invalid_owner_durations_do_not_change_a_session(tmp_path, monkeypatch, seconds):
    monkeypatch.setattr(web_devices, "app_config_dir", lambda: tmp_path)
    device = web_devices.register("phone", "192.168.0.2", "Phone", 1000)
    before = web_devices.session("phone")
    with pytest.raises(ValueError):
        web_devices.set_lifetime(device, seconds)
    assert web_devices.session("phone") == before
