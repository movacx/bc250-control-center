"""Only verified local names may replace the LAN IP in pairing URLs."""
import ssl
import subprocess
from types import SimpleNamespace

import pytest

from bc250cc.infrastructure import web_network, web_tls


@pytest.mark.parametrize("resolved,expected", [
    ("bc250.local\t192.168.0.15\n", "bc250.local"),
    ("bc250.local\t192.168.0.99\n", ""),
    ("other.local\t192.168.0.15\n", ""),
    ("malformed", ""),
])
def test_mdns_must_resolve_to_this_machine(monkeypatch, resolved, expected):
    monkeypatch.setattr(web_network.socket, "gethostname", lambda: "bc250")
    monkeypatch.setattr(web_network.shutil, "which", lambda _: "/usr/bin/avahi-resolve-host-name")
    monkeypatch.setattr(web_network, "addresses", lambda: ["192.168.0.15"])
    monkeypatch.setattr(web_network.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=resolved))
    assert web_network.local_hostname() == expected


def test_missing_mdns_or_invalid_name_keeps_ip_fallback(monkeypatch):
    monkeypatch.setattr(web_network.socket, "gethostname", lambda: "bc250")
    monkeypatch.setattr(web_network.shutil, "which", lambda _: None)
    assert not web_network.local_hostname()
    monkeypatch.setattr(web_network.socket, "gethostname", lambda: "bad,name.example")
    assert not web_network.local_hostname()


def test_certificate_renews_for_local_name_without_replacing_authority(tmp_path, monkeypatch):
    monkeypatch.setattr(web_tls, "app_config_dir", lambda: tmp_path)
    monkeypatch.setattr(web_tls, "addresses", lambda: ["192.168.0.15"])
    monkeypatch.setattr(web_tls, "local_hostname", lambda: "bc250.local")
    cert, _key = web_tls.certificate()
    authority = web_tls.trust_certificate()
    fingerprint = web_tls.fingerprint(authority)
    original = cert.read_bytes()
    subprocess.run(["openssl", "verify", "-CAfile", str(authority), "-verify_hostname", "bc250.local", str(cert)], check=True, capture_output=True)
    names = ssl._ssl._test_decode_cert(str(cert))["subjectAltName"]
    assert ("DNS", "bc250cc.local") in names
    assert ("DNS", "bc250.local") in names
    assert ("IP Address", "192.168.0.15") in names
    assert cert.read_bytes() == web_tls.certificate()[0].read_bytes()
    monkeypatch.setattr(web_tls, "local_hostname", lambda: "renamed.local")
    web_tls.certificate()
    assert original != cert.read_bytes()
    assert web_tls.fingerprint(authority) == fingerprint
    subprocess.run(["openssl", "verify", "-CAfile", str(authority), "-verify_hostname", "renamed.local", str(cert)], check=True, capture_output=True)


@pytest.mark.parametrize("alias_address,expected", [("192.168.0.15", "bc250cc.local"), ("192.168.0.99", "machine.local")])
def test_application_alias_is_preferred_only_when_owned(monkeypatch, alias_address, expected):
    monkeypatch.setattr(web_network.socket, "gethostname", lambda: "machine")
    monkeypatch.setattr(web_network.shutil, "which", lambda _: "/usr/bin/avahi-resolve-host-name")
    monkeypatch.setattr(web_network, "addresses", lambda: ["192.168.0.15"])
    def resolve(argv, **_kwargs):
        name = argv[-1]
        address = alias_address if name == "bc250cc.local" else "192.168.0.15"
        return SimpleNamespace(stdout=f"{name}\t{address}\n")
    monkeypatch.setattr(web_network.subprocess, "run", resolve)
    assert web_network.local_hostname() == expected


def test_alias_publisher_follows_lan_address_and_stops_with_server(monkeypatch):
    from bc250cc.infrastructure import web_mdns
    ips = []  # Login can precede DHCP; the watcher must remain alive.
    processes = []
    monkeypatch.setattr(web_mdns.shutil, "which", lambda _: "/usr/bin/avahi-publish-address")
    monkeypatch.setattr(web_mdns, "addresses", lambda: ips)
    monkeypatch.setattr(web_mdns.web_network, "home_networks", lambda: ["192.168.0.0/24"])
    monkeypatch.setattr(web_mdns.threading, "Thread", lambda **k: SimpleNamespace(start=lambda: None, join=lambda **k: None))
    class Process:
        def __init__(self, argv, **kwargs):
            self.argv, self.stopped = argv, False
            processes.append(self)
        def poll(self):
            return 0 if self.stopped else None
        def terminate(self):
            self.stopped = True
        def wait(self, **kwargs):
            return 0
    monkeypatch.setattr(web_mdns.subprocess, "Popen", Process)
    with web_mdns.LanAlias(True) as publisher:
        assert not processes
        ips[:] = ["192.168.0.15", "127.0.0.1", "203.0.113.2"]
        publisher._refresh()
        assert len(processes) == 1
        assert processes[0].argv[-2:] == ["bc250cc.local", "192.168.0.15"]
        ips[:] = ["192.168.0.16"]
        publisher._refresh()
        assert processes[0].stopped
        assert processes[1].argv[-1] == "192.168.0.16"
    assert all(process.stopped for process in processes)


def test_alias_is_optional_and_never_published_in_localhost_mode(monkeypatch):
    from bc250cc.infrastructure import web_mdns
    monkeypatch.setattr(web_mdns.shutil, "which", lambda _: None)
    monkeypatch.setattr(web_mdns.subprocess, "Popen", lambda *a, **k: pytest.fail("No mDNS publisher should start"))
    with web_mdns.LanAlias(True):
        pass
    with web_mdns.LanAlias(False):
        pass
