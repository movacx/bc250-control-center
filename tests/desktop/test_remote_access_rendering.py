"""Startup and navigation regressions for the redacted privacy backdrop."""
import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtWidgets import QApplication  # noqa: E402

from frontends.desktop import theme  # noqa: E402
from frontends.desktop.pages.remote_access import RemoteAccessPage  # noqa: E402


class RemoteRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.page = RemoteAccessPage()
        self.page.resize(1200, 850)
        self.addCleanup(self.page.close)

    def events(self):
        for _ in range(3):
            self.app.processEvents()

    def assert_silhouettes(self):
        image = self.page._privacy_cover._context.toImage()
        self.assertFalse(image.isNull())
        self.assertGreater(image.height(), 60)
        levels = [image.pixelColor(x, y).red() for y in range(image.height()) for x in range(image.width())]
        self.assertGreater(max(levels) - min(levels), 10)
        self.assertFalse(self.page.web_pin_box.isVisible())
        self.assertFalse(self.page.web_qr_image.isVisible())

    def test_firewall_offer_and_pending_state(self):
        self.page._privacy_hidden = False
        self.page._apply_web({"running": True, "lan": True, "port": 8250,
                              "firewall": {"state": "blocked", "repairable": True,
                                           "networks": ["192.168.0.0/24"]}})
        self.assertFalse(self.page.web_firewall_repair.isHidden())
        self.assertIn("192.168.0.0/24", self.page.web_firewall_status.text())
        self.page._firewall_repair_pending = True
        self.page._apply_web({"running": True, "lan": True, "firewall": {"state": "ready"}})
        self.assertFalse(self.page.web_firewall_repair.isHidden())
        self.assertFalse(self.page.web_firewall_repair.isEnabled())
        self.page._firewall_repair_pending = False
        self.page._render_web()
        self.assertTrue(self.page.web_firewall_repair.isHidden())

    def test_lock_before_first_show_recovers_context(self):
        self.page._conceal_information()
        self.assertTrue(self.page._privacy_cover._context.isNull())
        self.page.show()
        self.events()
        self.assert_silhouettes()

    def test_hidden_navigation_and_resize_keep_context(self):
        self.page.show()
        self.events()
        self.page.hide()
        self.page.resize(1050, 750)
        self.page.show()
        self.events()
        self.assert_silhouettes()

    def test_changing_theme_while_locked_rebuilds_context(self):
        previous = theme.ACTIVE_THEME
        self.addCleanup(theme.configure_theme, previous)
        self.page.show()
        self.events()
        for mode in ('midnight', 'dark', 'light'):
            theme.configure_theme(mode)
            self.page.apply_appearance()
            self.events()
            self.assert_silhouettes()

    def test_reveal_cancels_pending_context_capture(self):
        self.page.show()
        self.page._reveal_information()
        self.events()
        self.assertTrue(self.page._privacy_cover._context.isNull())
        self.assertFalse(self.page._privacy_hidden)

    def test_failed_alias_selects_ip_even_after_explicit_alias_selection(self):
        self.page._apply_web({'running': True, 'lan': True, 'urls': [
            'https://bc250cc.local:8250', 'https://192.168.0.8:8250']})
        self.page._web_address_chosen = True
        self.page._apply_web({'running': True, 'lan': True, 'urls': ['https://192.168.0.8:8250'],
                              'name_health': {'status': 'resolver_failed', 'repairable': True}})
        self.assertEqual(self.page.web_address.currentText(), 'https://192.168.0.8:8250')
        self.assertTrue(self.page.web_copy_url_button.isEnabled())

    def test_repair_action_survives_transient_status_changes(self):
        def apply(status, repairable=False):
            self.page._apply_web({'running': True, 'lan': True,
                                  'name_health': {'status': status, 'repairable': repairable}})
        apply('resolver_failed', True)
        self.assertFalse(self.page.web_name_repair.isHidden())
        message = self.page.web_name_status.text()
        apply('ready')
        self.assertFalse(self.page.web_name_repair.isHidden())
        self.assertEqual(self.page.web_name_status.text(), message)
        apply('unavailable')
        self.assertFalse(self.page.web_name_repair.isHidden())
        apply('ready')
        apply('ready')
        self.assertTrue(self.page.web_name_repair.isHidden())

    def test_repair_dialog_and_operation_keep_action_disabled_and_visible(self):
        self.page._apply_web({'lan': True, 'name_health': {'status': 'resolver_failed', 'repairable': True}})
        self.page._name_repair_pending = True
        for status in ('ready', 'disabled', 'unavailable'):
            self.page._apply_web({'lan': True, 'name_health': {'status': status, 'repairable': False}})
            self.assertFalse(self.page.web_name_repair.isHidden())
            self.assertFalse(self.page.web_name_repair.isEnabled())
