"""SteamOS read-only panel: free space on /var and the button that clears its caches."""

from frontends.desktop.pages.additional_settings import AdditionalSettingsPage


def _panel(qtbot):
    page = AdditionalSettingsPage()
    qtbot.addWidget(page)
    page.resize(1200, 900)
    page.show()
    page.panel._page = page
    return page.panel


def test_the_panel_shows_free_space_and_asks_for_the_cleanup(qtbot):
    panel = _panel(qtbot)
    panel._update_steamos_readonly_control(
        {"steamos_readonly": {"available": True, "state": "enabled", "var_free_mb": 83}}
    )
    assert "83" in panel.var_space_note.text()
    assert not panel.var_space_note.isHidden()
    with qtbot.waitSignal(panel.dependency_action_requested) as signal:
        panel.var_space_button.click()
    assert signal.args[0]["action"] == "steamos_readonly_free-var"


def test_unreadable_free_space_shows_no_number(qtbot):
    panel = _panel(qtbot)
    panel._update_steamos_readonly_control(
        {"steamos_readonly": {"available": True, "state": "enabled", "var_free_mb": None}}
    )
    assert panel.var_space_note.isHidden()
