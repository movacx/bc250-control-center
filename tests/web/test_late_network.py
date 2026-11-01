"""The user service can start before DHCP without requiring a manual toggle."""
import json
import socket
import ssl
import threading
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from bc250cc.infrastructure import web_network, web_tls
from frontends.web import network, server


def test_policy_tracks_late_network_disconnect_and_dhcp_change(monkeypatch):
    current = []
    endpoint = SimpleNamespace(allowed_networks=[], secure=False)
    monitor = network.LanMonitor(endpoint, enabled=True)
    monkeypatch.setattr(network.web_network, "home_networks", lambda: list(current))
    monitor.refresh()
    assert not endpoint.allowed_networks
    current[:] = ["192.168.0.0/24"]
    monitor.refresh()
    assert web_network.allows("192.168.0.20", endpoint.allowed_networks)
    current.clear()
    monitor.refresh()
    assert not web_network.allows("192.168.0.20", endpoint.allowed_networks)
    current[:] = ["192.168.1.0/24"]
    monitor.refresh()
    assert web_network.allows("192.168.1.20", endpoint.allowed_networks)
    assert not web_network.allows("192.168.0.20", endpoint.allowed_networks)


def test_discovery_failure_revokes_the_old_network_and_recovers(monkeypatch):
    endpoint = SimpleNamespace(allowed_networks=["192.168.0.0/24"], secure=False)
    monitor = network.LanMonitor(endpoint, enabled=True)
    monkeypatch.setattr(network.web_network, "home_networks", lambda: (_ for _ in ()).throw(OSError()))
    monitor._tick()
    assert not endpoint.allowed_networks
    monkeypatch.setattr(network.web_network, "home_networks", lambda: ["192.168.1.0/24"])
    monitor._tick()
    assert endpoint.allowed_networks == ["192.168.1.0/24"]


def test_background_watcher_updates_after_start_and_stops_cleanly(monkeypatch):
    ready = threading.Event()
    current = []
    class Endpoint:
        secure = False
        @property
        def allowed_networks(self):
            return self._networks
        @allowed_networks.setter
        def allowed_networks(self, value):
            self._networks = value
            if value:
                ready.set()
    endpoint = Endpoint()
    monkeypatch.setattr(network, "REFRESH_SECONDS", .01)
    monkeypatch.setattr(network.web_network, "home_networks", lambda: list(current))
    with network.LanMonitor(endpoint, enabled=True) as monitor:
        current[:] = ["192.168.0.0/24"]
        assert ready.wait(2)
        assert endpoint.allowed_networks == ["192.168.0.0/24"]
    assert not monitor._thread.is_alive()
    with network.LanMonitor(endpoint, enabled=False) as monitor:
        assert monitor._thread is None


def test_tls_refresh_retries_after_failure_without_replacing_the_working_adapter(monkeypatch):
    replacements = []
    endpoint = SimpleNamespace(allowed_networks=[], secure=True, update_certificate=replacements.append)
    monitor = network.LanMonitor(endpoint, enabled=True)
    monkeypatch.setattr(network.web_network, "home_networks", lambda: ["192.168.0.0/24"])
    monkeypatch.setattr(network.web_network, "addresses", lambda: ["192.168.0.15"])
    monkeypatch.setattr(network.web_access, "tls_certificate", lambda: (_ for _ in ()).throw(OSError()))
    monitor._tick()
    assert replacements == [] and monitor._addresses is None
    monkeypatch.setattr(network.web_access, "tls_certificate", lambda: ("cert", "key"))
    monitor._tick()
    monitor._tick()
    assert replacements == [("cert", "key")]


def test_tls_leaf_and_lan_access_follow_dhcp_on_a_running_server(tmp_path, monkeypatch):
    ips, networks = [], []
    monkeypatch.setattr(web_tls, "app_config_dir", lambda: tmp_path)
    monkeypatch.setattr(web_tls, "addresses", lambda: list(ips))
    monkeypatch.setattr(web_tls, "local_hostname", lambda: "")
    monkeypatch.setattr(network.web_network, "addresses", lambda: list(ips))
    monkeypatch.setattr(network.web_network, "home_networks", lambda: list(networks))
    monkeypatch.setattr(network.web_access, "tls_certificate", web_tls.certificate)
    original_allows = web_network.allows
    # Model a LAN client on the real loopback socket; never trust an HTTP header.
    monkeypatch.setattr(server.web_network, "allows", lambda address, allowed:
                        original_allows("192.168.0.20" if address == "127.0.0.1" else address, allowed))
    certificate = web_tls.certificate()
    authority = web_tls.trust_certificate()
    fingerprint = web_tls.fingerprint(authority)
    endpoint = server.Server(("127.0.0.1", 0), SimpleNamespace(language="en", ssh_sessions={}, local_sessions={}), certificate=certificate)
    monitor = network.LanMonitor(endpoint, enabled=True)
    thread = threading.Thread(target=endpoint.serve_forever, daemon=True)
    thread.start()
    context = ssl.create_default_context(cafile=str(authority))
    url = f"https://127.0.0.1:{endpoint.server_address[1]}/api/version"

    def response():
        with urllib.request.urlopen(url, context=context, timeout=5) as reply:
            return json.load(reply)

    try:
        monitor.refresh()
        with pytest.raises(urllib.error.HTTPError) as error:
            response()
        assert error.value.code == 403
        networks[:] = ["192.168.0.0/24"]
        for address in ("192.168.0.15", "192.168.0.16"):
            ips[:] = [address]
            monitor.refresh()
            assert response()["version"]
            with socket.create_connection(endpoint.server_address, timeout=5) as plain:
                with context.wrap_socket(plain, server_hostname="127.0.0.1") as tls:
                    assert ("IP Address", address) in tls.getpeercert()["subjectAltName"]
            assert web_tls.fingerprint(authority) == fingerprint
        networks.clear()
        monitor.refresh()
        with pytest.raises(urllib.error.HTTPError) as error:
            response()
        assert error.value.code == 403
    finally:
        endpoint.shutdown()
        endpoint.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("host,enabled", [("0.0.0.0", True), ("127.0.0.1", False)])
def test_main_keeps_lan_watchers_enabled_before_any_network_exists(monkeypatch, host, enabled):
    flags = []
    class Watcher:
        def __init__(self, *args, enabled):
            flags.append(enabled)
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            pass
    monkeypatch.setattr(server.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(server.web_access, "options", lambda: {"lan": enabled, "tls": True, "port": 8250})
    monkeypatch.setattr(server.web_access, "access_key", lambda: "TEST-KEY2")
    monkeypatch.setattr(server.web_access, "tls_certificate", lambda: ("cert", "key"))
    monkeypatch.setattr(server.web_access, "write_pid", lambda _: None)
    monkeypatch.setattr(server.web_network, "home_networks", lambda: [])
    monkeypatch.setattr(server, "Web", lambda: SimpleNamespace(language="en"))
    monkeypatch.setattr(server, "Server", lambda *a, **k: SimpleNamespace(secure=True, serve_forever=lambda: None, server_close=lambda: None))
    monkeypatch.setattr(server, "LanMonitor", Watcher)
    monkeypatch.setattr(server.web_mdns, "LanAlias", Watcher)
    monkeypatch.setattr(server.signal, "signal", lambda *a: None)
    assert server.main(["--host", host]) == 0
    assert flags == [enabled, enabled]
