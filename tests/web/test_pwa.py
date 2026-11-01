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
    assert {192, 512} <= set(sizes)
    html = (DIST / "index.html").read_text()
    assert 'rel="manifest" href="/manifest.webmanifest"' in html
    assert 'rel="apple-touch-icon"' in html


def test_worker_never_masks_online_navigation_or_handles_api_traffic():
    import shutil
    import subprocess

    import pytest

    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed for the service-worker behaviour check")
    script = r'''
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
const handlers = {};
const self = { location: { origin: "https://bc250cc.local:8250" }, navigator: { onLine: true },
  addEventListener: (name, handler) => { handlers[name] = handler; } };
vm.runInNewContext(readFileSync(process.argv[1], "utf8"), { self, URL, Response, Promise,
  fetch: () => { throw Error("The worker must not fetch online navigation or API requests"); } });
function dispatch(method, mode, path) {
  let result;
  handlers.fetch({ request: { method, mode, url: self.location.origin + path },
    respondWith: (response) => { result = response; } });
  return result;
}
assert.equal(dispatch("GET", "navigate", "/"), undefined);
self.navigator.onLine = false;
assert.equal(dispatch("GET", "cors", "/api/live"), undefined);
assert.equal(dispatch("GET", "navigate", "/api/session"), undefined);
assert.equal(dispatch("POST", "navigate", "/api/action"), undefined);
const response = await dispatch("GET", "navigate", "/");
assert.equal(response.status, 503);
assert.equal(response.headers.get("Cache-Control"), "no-store");
assert.match(await response.text(), /BC250 · Offline/);
'''
    subprocess.run([node, "--input-type=module", "-e", script, str(DIST / "sw.js")], check=True, capture_output=True, text=True)
