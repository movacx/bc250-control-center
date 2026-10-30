"""Installation metadata must point to live login, without pairing credentials."""
import json
import struct

from frontends.web.server import CSP, DIST


def test_manifest_has_a_standalone_same_origin_entry_and_real_icons():
    assert "manifest-src 'self'" in CSP
    assert "default-src 'none'" in CSP
    manifest = json.loads((DIST / "manifest.webmanifest").read_text())
    assert manifest["id"] == manifest["scope"] == "/"
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/#/dashboard"
    assert "pair=" not in json.dumps(manifest)
    assert "key=" not in json.dumps(manifest)
    sizes = []
    for icon in manifest["icons"]:
        data = (DIST / icon["src"]).read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        width, height = struct.unpack(">II", data[16:24])
        assert icon["sizes"] == f"{width}x{height}"
        assert width == height and width >= 192
        sizes.append(width)
    assert 512 in sizes
    html = (DIST / "index.html").read_text()
    assert 'rel="manifest" href="/manifest.webmanifest"' in html
    assert 'rel="apple-touch-icon"' in html
