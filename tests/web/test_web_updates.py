"""Build discovery must describe the served page even during package replacement."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from frontends.web import server


class WebUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dist = Path(self.temp.name)
        self.version = 'a' * 16
        (self.dist / 'index.html').write_text(f'<meta name="bc250-build" content="{self.version}">')
        (self.dist / 'version.json').write_text(json.dumps({'version': 'b' * 16}))
        self.patch = patch.object(server, 'DIST', self.dist)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def request(self, path):
        handler = server.Handler(SimpleNamespace(allowed_networks=[], web=SimpleNamespace(language='en')),
                                 {'REMOTE_ADDR':'127.0.0.1', 'HTTP_HOST':'localhost:8250',
                                  'PATH_INFO':path, 'wsgi.input':io.BytesIO()})
        with patch.object(server, 'host_allowed', return_value=True):
            handler.route('GET')
        return handler.wfile.getvalue(), dict(handler.response_headers)

    def test_stale_sidecar_does_not_offer_a_false_update(self):
        body, headers = self.request('/api/version')
        self.assertEqual(json.loads(body), {'version':self.version})
        self.assertEqual(headers['Cache-Control'], 'no-store')

    def test_replaced_page_is_detected_without_server_restart(self):
        (self.dist / 'index.html').write_text('<meta name="bc250-build" content="' + 'c' * 16 + '">')
        self.assertEqual(json.loads(self.request('/api/version')[0])['version'], 'c' * 16)

    def test_missing_or_invalid_build_never_supplies_a_package_version(self):
        for html in ('<html></html>', '<meta name="bc250-build" content="1.21.4">'):
            (self.dist / 'index.html').write_text(html)
            self.assertEqual(json.loads(self.request('/api/version')[0])['version'], '')
        (self.dist / 'index.html').unlink()
        self.assertEqual(json.loads(self.request('/api/version')[0])['version'], '')

    def test_navigation_and_worker_are_not_stored(self):
        (self.dist / 'sw.js').write_text('// worker')
        for path in ('/', '/index.html', '/dashboard', '/sw.js'):
            self.assertEqual(self.request(path)[1]['Cache-Control'], 'no-store')
        (self.dist / 'app.js').write_text('// versioned bundle')
        self.assertEqual(self.request('/app.js')[1]['Cache-Control'], 'no-cache')


if __name__ == '__main__':
    unittest.main()
