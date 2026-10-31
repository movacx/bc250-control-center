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
    assert ("DNS", "bc250.local") in names
    assert ("IP Address", "192.168.0.15") in names
    assert cert.read_bytes() == web_tls.certificate()[0].read_bytes()
    monkeypatch.setattr(web_tls, "local_hostname", lambda: "renamed.local")
    web_tls.certificate()
    assert original != cert.read_bytes()
    assert web_tls.fingerprint(authority) == fingerprint
    subprocess.run(["openssl", "verify", "-CAfile", str(authority), "-verify_hostname", "renamed.local", str(cert)], check=True, capture_output=True)
