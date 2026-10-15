"""TV control: the remote it opens on, the settings behind its gear, and what reaches the terminal."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt

from frontends.desktop.pages.tv_control import (
    REMOTE_PAGE,
    SETTINGS_PAGE,
    TvControlDialog,
)


class Controller:
    def __init__(self, status=None, automation=None, answers=None):
        self.sent = []
        self._status = status if status is not None else {
            "adapter": "cec0", "daemon": True, "tv": "standby", "receiver": "on", "address": "1.0.0.0",
        }
        self._automation = automation if automation is not None else {"wake": "absent", "poweroff": "absent"}
        self._answers = answers or {}

    def tv_control_status(self):
        return self._status

    def tv_control_automation(self):
        return self._automation

    def tv_control_action(self, action):
        self.sent.append(action)
        return self._answers.get(action, {"ok": True, "code": "sent", "detail": ""})


def _open(qtbot, controller=None):
    controller = controller or Controller()
    dialog = TvControlDialog(controller)
    qtbot.addWidget(dialog)
    # The first check came back: only then is the settings button of the footer free again.
    qtbot.waitUntil(dialog.check_button.isEnabled, timeout=5000)
    return dialog


def test_it_opens_on_the_remote_and_shows_what_the_tv_and_the_receiver_are_doing(qtbot):
    dialog = _open(qtbot)
    assert dialog.stack.currentIndex() == REMOTE_PAGE
    assert dialog.display["tv"].text() == "Standby" and dialog.display["receiver"].text() == "Powered on"
    assert all(button.isEnabled() for button in dialog.buttons.values())


def test_the_remote_has_every_button_there_is(qtbot):
    from bc250cc.infrastructure.accessories import hdmi_cec_control

    assert set(_open(qtbot).buttons) == set(hdmi_cec_control.ACTIONS)


def test_a_gear_opens_the_settings_and_an_arrow_comes_back(qtbot):
    dialog = _open(qtbot)
    assert not dialog.gear_button.isHidden() and dialog.back_button.isHidden()
    assert dialog.title.text() == "TV control"
    dialog.gear_button.click()
    assert dialog.stack.currentIndex() == SETTINGS_PAGE
    assert dialog.gear_button.isHidden() and not dialog.back_button.isHidden()
    assert dialog.title.text() == "Settings"
    dialog.back_button.click()
    assert dialog.stack.currentIndex() == REMOTE_PAGE and dialog.title.text() == "TV control"


def test_the_settings_show_the_readings_the_address_and_what_it_talks_to(qtbot):
    dialog = _open(qtbot)
    assert dialog.readings["tv"].text() == "Standby" and dialog.readings["receiver"].text() == "Powered on"
    assert dialog.readings["address"].text() == "1.0.0.0"
    assert "cec0" in dialog.subtitle.text()


@pytest.mark.parametrize("status, words", [
    ({"adapter": "", "daemon": False}, "adapter"),
    ({"adapter": "cec0", "daemon": False}, "cecd is not running"),
])
def test_without_an_adapter_or_a_daemon_the_remote_is_dead_and_says_why(qtbot, status, words):
    dialog = _open(qtbot, Controller(status=status))
    assert words in dialog.result.text() and words in dialog.subtitle.text()
    assert not any(button.isEnabled() for button in dialog.buttons.values())
    assert dialog.display["tv"].text() == "--"


def test_a_button_sends_its_action_and_shows_the_answer(qtbot):
    controller = Controller()
    dialog = _open(qtbot, controller)
    dialog.buttons["volume-up"].click()
    qtbot.waitUntil(lambda: dialog.result.text() == "Sent.", timeout=5000)
    assert controller.sent == ["volume-up"]


def test_a_refused_command_and_a_receiver_that_woke_are_told_apart(qtbot):
    controller = Controller(answers={
        "tv-off": {"ok": False, "code": "failed", "detail": ""},
        "amp-on": {"ok": True, "code": "amp-awake", "detail": "on"},
    })
    dialog = _open(qtbot, controller)
    dialog.buttons["tv-off"].click()
    qtbot.waitUntil(lambda: "not accepted" in dialog.result.text(), timeout=5000)
    qtbot.waitUntil(dialog.check_button.isEnabled, timeout=5000)
    dialog.buttons["amp-on"].click()
    qtbot.waitUntil(lambda: "awake" in dialog.result.text(), timeout=5000)
    assert "on" in dialog.result.text()


def test_every_symbol_names_itself_for_the_mouse_and_for_a_screen_reader(qtbot):
    dialog = _open(qtbot)
    for name, button in {**dialog.buttons, "gear": dialog.gear_button, "back": dialog.back_button}.items():
        assert button.toolTip() and button.accessibleName() == button.toolTip(), name
        assert button.focusPolicy() == Qt.FocusPolicy.StrongFocus


def test_every_message_has_text():
    from frontends.desktop.pages import tv_control

    assert set(tv_control.MESSAGES) >= {"sent", "failed", "no-daemon", "no-adapter", "no-address", "amp-awake"}


def test_an_automation_installs_or_removes_in_the_terminal_and_closes_the_window(qtbot):
    dialog = _open(qtbot, Controller(automation={"wake": "installed", "poweroff": "absent"}))
    assert dialog.automation_buttons["wake"].text() == "Remove"
    assert dialog.automation_buttons["poweroff"].text() == "Install"
    requested = []
    dialog.automation_requested.connect(requested.append)
    dialog.automation_buttons["wake"].click()
    assert requested == ["wake-remove"] and not dialog.isVisible()
    dialog.automation_buttons["poweroff"].click()
    assert requested == ["wake-remove", "poweroff-install"]


def test_what_another_toolkit_installed_is_not_touched(qtbot):
    dialog = _open(qtbot, Controller(automation={"wake": "foreign", "poweroff": "absent"}))
    assert not dialog.automation_buttons["wake"].isEnabled()
    assert "Another toolkit" in dialog.automation_buttons["wake"].toolTip()
    assert dialog.automation_buttons["poweroff"].isEnabled()


def test_the_check_button_belongs_to_the_settings_only(qtbot):
    dialog = _open(qtbot)
    assert dialog.check_button.isHidden()
    dialog.gear_button.click()
    assert not dialog.check_button.isHidden()


def test_it_paints_in_both_themes_and_on_both_pages(qtbot):
    from frontends.desktop import theme

    dialog = _open(qtbot)
    dialog.show()
    for mode in ("light", "dark"):
        theme.application_stylesheet(mode)
        for page in (REMOTE_PAGE, SETTINGS_PAGE):
            dialog.stack.setCurrentIndex(page)
            pixmap = dialog.grab()
            assert not pixmap.isNull() and pixmap.width() > 200


def test_the_whole_remote_fits_in_the_window_without_scrolling(qtbot):
    from PyQt6.QtWidgets import QScrollArea

    dialog = _open(qtbot)
    dialog.show()
    qtbot.waitExposed(dialog)
    scroll = dialog.stack.widget(REMOTE_PAGE).findChild(QScrollArea)
    assert not scroll.verticalScrollBar().isVisible(), "the remote had to be scrolled"
