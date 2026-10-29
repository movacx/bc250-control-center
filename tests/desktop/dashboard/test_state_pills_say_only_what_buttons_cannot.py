"""Boot parameters on Additional settings: a state pill only says what the button cannot.

"Enabled" / "Disabled" / "Protected" repeated what the button beside it already
said ("Disable mitigations" means they are on). What the button cannot say is a
reboot that is still pending, so that is the only state left on screen.
"""

from frontends.desktop.pages.additional_settings import AdditionalSettingsPage


def _panel(qtbot):
    page = AdditionalSettingsPage()
    qtbot.addWidget(page)
    page.resize(1200, 900)
    page.show()
    page.panel._page = page
    return page.panel


def _state(**flags):
    return {"available": True, "active": False, "configured": False, "managed": False,
            "reboot_required": False, **flags}


def test_the_bazzite_mitigations_pill_shows_only_a_pending_reboot(qtbot):
    panel = _panel(qtbot)
    panel._update_mitigation_control({"bazzite_mitigations": _state()}, actionable=True)
    assert panel.mitigations_status.isHidden()
    panel._update_mitigation_control(
        {"bazzite_mitigations": _state(configured=True, managed=True, reboot_required=True)}, actionable=True
    )
    assert not panel.mitigations_status.isHidden()
    assert panel.mitigations_status.text() == "Reboot required"
    # Already disabled and booted: the button ("Restore mitigations") says so.
    panel._update_mitigation_control(
        {"bazzite_mitigations": _state(active=True, configured=True, managed=True)}, actionable=True
    )
    assert panel.mitigations_status.isHidden()


def test_the_boot_messages_pill_shows_only_a_pending_reboot(qtbot):
    panel = _panel(qtbot)
    panel._update_boot_messages_control({"bazzite_boot_messages": _state()}, actionable=True)
    assert panel.boot_messages_status.isHidden()
    panel._update_boot_messages_control(
        {"bazzite_boot_messages": _state(configured=True, managed=True, reboot_required=True)}, actionable=True
    )
    assert not panel.boot_messages_status.isHidden()
    assert panel.boot_messages_status.text() == "Reboot required"


def test_the_steamos_read_only_pill_is_gone_unless_the_state_is_unknown(qtbot):
    panel = _panel(qtbot)
    for mode in ("enabled", "disabled"):
        panel._update_steamos_readonly_control({"steamos_readonly": {"available": True, "state": mode}})
        assert panel.readonly_status.isHidden(), mode
    panel._update_steamos_readonly_control({"steamos_readonly": {"available": True, "state": "weird"}})
    assert not panel.readonly_status.isHidden()


def test_the_live_smt_pill_is_gone_because_its_button_says_it(qtbot):
    panel = _panel(qtbot)
    off = {"managed": False, "configured": False, "active": False, "external": False}
    tools = {"system_setup": {"helper_available": True, "kernel_options": {
        "available": True, "arguments": {"mitigations=off": off, "nosmt": off},
        "allowed": ["mitigations=off", "nosmt"], "smt": {"supported": True, "control": "on"},
    }}}
    panel._update_kernel_options_control(tools)
    assert not panel.smt_live_button.isHidden()
    assert panel.smt_live_button.text() == "Turn SMT off now"
    assert panel.smt_live_pill.isHidden()
