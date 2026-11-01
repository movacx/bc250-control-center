"""Session startup for desktops running without a systemd user manager."""
import os
import tempfile
import unittest
from unittest.mock import patch

from bc250cc.infrastructure import web_control as web
from bc250cc.shared.errors import ActionNeeded


class XdgAutostartTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for context in (
            patch.dict(os.environ, {'XDG_CONFIG_HOME': self.temp.name}),
            patch.object(web, 'systemd_available', return_value=False),
            patch.object(web, '_command', return_value=['/usr/bin/python', '-m', 'frontends.web']),
            patch.object(web, 'access_key', return_value='TEST-KEY1'),
            patch.object(web, '_systemctl', side_effect=AssertionError('systemd unavailable')),
        ):
            context.start()
            self.addCleanup(context.stop)

    def test_enable_disable_changes_future_sessions_only(self):
        with patch.object(web.subprocess, 'Popen', side_effect=AssertionError('must not start another server')):
            self.assertTrue(web.set_autostart(True)['enabled'])
            entry = web._desktop_path().read_text()
            self.assertIn('[Desktop Entry]', entry)
            self.assertIn('"-m" "frontends.web"', entry)
            self.assertFalse(web.set_autostart(False)['enabled'])
            self.assertFalse(web._desktop_path().exists())

    def test_foreign_autostart_file_is_preserved(self):
        path = web._desktop_path()
        path.parent.mkdir(parents=True)
        path.write_text('# other tool')
        for enabled in (True, False):
            with self.assertRaises(ActionNeeded):
                web.set_autostart(enabled)
        self.assertEqual(path.read_text(), '# other tool')

    def test_exec_escapes_desktop_field_codes_and_reserved_characters(self):
        self.assertEqual(web._desktop_quote('a % b'), '"a %% b"')
        self.assertEqual(web._desktop_quote('a"b'), '"a\\"b"')
        self.assertEqual(web._desktop_quote('$HOME'), '"\\$HOME"')
        with self.assertRaises(ValueError):
            web._desktop_quote('line\nExec=bad')


if __name__ == '__main__':
    unittest.main()
