"""Network repairs are available in the TUI and stay inside its guarded console."""

import unittest
from unittest.mock import patch

from bc250cc.application.system import web_access
from frontends.tui.content import Choice, Panel
from frontends.tui.i18n import set_language
from frontends.tui.layout import Glyphs, build_layout
from frontends.tui.pages.remote import RemoteAccessPage
from tests.tui.fakes import FakeUI, make_context
from tests.tui.test_pages import text_of


class RemoteNetworkTests(unittest.TestCase):
    def setUp(self):
        set_language("en")
        self.ctx, self.ui, self.page = make_context(), FakeUI(), RemoteAccessPage()
        self.web = {
            "lan": True,
            "running": True,
            "port": 8250,
            "firewall": {
                "state": "blocked",
                "backend": "ufw",
                "repairable": True,
                "verified": False,
                "networks": ["192.168.0.0/24"],
            },
            "name_health": {"status": "resolver_failed", "repairable": True},
        }

    def blocks(self, tab="network"):
        return self.page.build(self.ctx, {"web": self.web}, tab, self.ui)

    def flattened(self, blocks=None):
        for block in self.blocks() if blocks is None else blocks:
            if isinstance(block, Panel):
                yield from self.flattened(block.blocks)
            else:
                yield block

    def choice(self, label, blocks=None):
        return next(block for block in self.flattened(blocks)
                    if isinstance(block, Choice) and block.label == label)

    def text(self):
        return text_of(build_layout(self.blocks(), 100, Glyphs.for_terminal(unicode_ok=True)))

    def test_network_tab_has_no_duplicate_web_shortcut(self):
        self.assertIn(("network", "Network diagnostics"), self.page.tabs(self.ctx))
        self.assertFalse(any(isinstance(block, Choice) and block.label == "Network diagnostics"
                             for block in self.flattened(self.blocks("web"))))

    def test_each_section_says_its_state_in_its_heading(self):
        self.assertEqual([(block.title, block.badge) for block in self.blocks()],
                         [("Network and connection", ""), ("Firewall", "Blocked"), ("Local address", "Not available")])
        self.assertEqual([block.label for block in self.flattened() if isinstance(block, Choice)],
                         ["Prepare the connection", "Configure LAN firewall", "Repair local address"])

    def test_network_diagnosis_fits_narrow_terminals_in_english_and_spanish(self):
        from frontends.tui.content import cell_width
        from frontends.tui.layout import Glyphs, build_layout

        try:
            for language in ("en", "es"):
                set_language(language)
                for width in (32, 50, 80):
                    layout = build_layout(
                        self.blocks(), width, Glyphs.for_terminal(unicode_ok=True)
                    )
                    for row in layout.rows:
                        self.assertLessEqual(
                            sum(cell_width(text) for text, _ in row.spans), width
                        )
            self.assertIn(("network", "Diagnóstico de red"), self.page.tabs(self.ctx))
        finally:
            set_language("en")

    def test_cachyos_configuration_diagnosis(self):
        text = self.text()
        for value in (
            "8250",
            "192.168.0.0/24",
            "UFW",
            "saved UFW",
            "firewall may block",
        ):
            self.assertIn(value, text)
        self.choice("Configure LAN firewall")
        self.choice("Repair local address")

    def test_firewall_repair_confirmation_and_console(self):
        inside = []
        original = self.ui.run

        def run(label, work):
            inside.append(True)
            try:
                return original(label, work)
            finally:
                inside.pop()

        self.ui.run = run

        def repair():
            self.assertTrue(inside)
            return {"state": "ready"}

        with patch.object(web_access, "repair_firewall", side_effect=repair) as call:
            self.choice("Configure LAN firewall").handler(self.ui)
        call.assert_called_once_with()
        self.assertEqual(self.ui.ran, ["Configure LAN firewall"])
        message, danger = self.ui.confirmations[0]
        self.assertTrue(danger)
        self.assertIn("8250", message)
        self.assertIn("192.168.0.0/24", message)
        self.assertEqual(self.ui.refreshed, 1)

    def test_local_name_repair_uses_existing_helper(self):
        with patch.object(
            web_access, "repair_local_name", return_value={"status": "ready"}
        ) as call:
            self.choice("Repair local address").handler(self.ui)
        call.assert_called_once_with()
        self.assertIn("Avahi", self.ui.confirmations[0][0])
        self.assertEqual(self.ui.ran, ["Repair local address"])

    def test_a_cancelled_repair_changes_nothing(self):
        with patch.object(web_access, "repair_firewall") as call:
            self.ui.confirm_answer = False
            self.choice("Configure LAN firewall").handler(self.ui)
            self.assertEqual(self.ui.ran, [])
            call.assert_not_called()

    def test_no_lan_or_unsupported_manager_offers_no_firewall_repair(self):
        self.web["lan"] = False
        self.assertFalse(
            any(
                isinstance(block, Choice) and block.label == "Configure LAN firewall"
                for block in self.flattened()
            )
        )
        self.web["lan"] = True
        for state in ("unsupported", "ready", "no_network", "update_helper"):
            self.web["firewall"] = {"state": state, "repairable": False}
            self.assertFalse(
                any(
                    isinstance(block, Choice)
                    and block.label == "Configure LAN firewall"
                    for block in self.flattened()
                )
            )

    def test_failures_are_reported_and_status_is_refreshed(self):
        with patch.object(
            web_access, "repair_firewall", side_effect=RuntimeError("repair failed")
        ):
            self.choice("Configure LAN firewall").handler(self.ui)
        self.assertEqual(self.ui.refreshed, 1)
        self.assertTrue(any(tone == "bad" for _, tone in self.ui.notes))

    def test_firewalld_and_changed_port_networks_are_not_hardcoded(self):
        self.web["port"] = 9321
        self.web["firewall"].update(
            backend="firewalld", verified=True, networks=["10.42.0.0/24"]
        )
        self.assertIn("firewalld", self.text())
        self.assertNotIn("saved UFW", self.text())
        with patch.object(web_access, "repair_firewall", return_value={}):
            self.choice("Configure LAN firewall").handler(self.ui)
        self.assertIn("9321", self.ui.confirmations[0][0])
        self.assertIn("10.42.0.0/24", self.ui.confirmations[0][0])


if __name__ == "__main__":
    unittest.main()


def test_a_single_repair_fits_beside_the_other_reading():
    from frontends.tui.content import cell_width
    from frontends.tui.layout import build_page

    page, ctx, ui = RemoteAccessPage(), make_context(), FakeUI()
    for firewall_repair in (True, False):
        web = {'lan': True, 'running': True,
               'firewall': {'state': 'blocked', 'repairable': firewall_repair},
               'name_health': {'status': 'resolver_failed', 'repairable': not firewall_repair}}
        layout = build_page(page.build(ctx, {'web': web}, 'network', ui), 142,
                            Glyphs.for_terminal(unicode_ok=True))
        assert 'Blocked' in text_of(layout).splitlines()[0]
        assert len(layout.choices) == 1
        assert all(sum(cell_width(text) for text, _tone in row.spans) <= 142 for row in layout.rows)
