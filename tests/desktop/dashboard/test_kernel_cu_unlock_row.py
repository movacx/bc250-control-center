"""The kernel's own CU unlock: one more kernel boot option, only where it exists.

linux-cachyos-bc250 unlocks all 40 compute units itself when amdgpu is given
``bc250_cc_write_mode=3``, which replaces umr and the live CU manager. The row
is offered only on a kernel that has that module parameter, and stays visible
when it was already staged or set by hand so that it can still be taken back.
"""

from frontends.desktop.pages.additional_settings import AdditionalSettingsPage

OPTION = "amdgpu.bc250_cc_write_mode=3"


def _tools(*, supported, item=None):
    arguments = {
        "mitigations=off": {"managed": False, "configured": False, "active": False},
        "nosmt": {"managed": False, "configured": False, "active": False},
        OPTION: item or {"managed": False, "configured": False, "active": False, "external": False},
    }
    return {"system_setup": {"helper_available": True, "kernel_options": {
        "available": True, "arguments": arguments, "cu_unlock": {"supported": supported, "mode": ""},
    }}}


def _panel(qtbot):
    page = AdditionalSettingsPage()
    qtbot.addWidget(page)
    page.resize(1200, 900)
    page.show()
    page.panel._page = page  # the page owns the panel: keep it alive with it
    return page.panel


def _visible(panel):
    name, pill, button = panel.kernel_option_controls[OPTION]
    return not name.isHidden(), not button.isHidden(), not panel.kernel_cu_note.isHidden()


def test_a_kernel_without_the_parameter_is_not_offered_the_row(qtbot):
    panel = _panel(qtbot)
    panel._update_kernel_options_control(_tools(supported=False))
    assert _visible(panel) == (False, False, False)
    # The two options that always existed are untouched.
    assert not panel.kernel_option_controls["nosmt"][2].isHidden()


def test_the_bc250_kernel_is_offered_the_row_and_says_what_it_replaces(qtbot):
    panel = _panel(qtbot)
    panel._update_kernel_options_control(_tools(supported=True))
    assert _visible(panel) == (True, True, True)
    _name, pill, button = panel.kernel_option_controls[OPTION]
    assert button.text() == "Unlock all 40 CUs"
    # Unlocking gives nothing up, so it is not drawn as a warning.
    assert button.property("dangerAction") is False
    assert "umr" in panel.kernel_cu_note.text()
    assert "amdgpu.disable_cu" in panel.kernel_cu_note.text()


def test_a_staged_unlock_can_be_restored_and_waits_for_the_reboot(qtbot):
    panel = _panel(qtbot)
    panel._update_kernel_options_control(_tools(supported=True, item={
        "managed": True, "configured": True, "active": False, "external": False,
    }))
    _name, pill, button = panel.kernel_option_controls[OPTION]
    assert button.text() == "Restore CU lock"
    assert not pill.isHidden() and pill.text() == "Reboot required"


def test_a_row_staged_on_a_kernel_that_lost_the_parameter_stays_so_it_can_be_removed(qtbot):
    panel = _panel(qtbot)
    panel._update_kernel_options_control(_tools(supported=False, item={
        "managed": True, "configured": True, "active": False, "external": False,
    }))
    assert _visible(panel) == (True, True, True)
    assert panel.kernel_option_controls[OPTION][2].text() == "Restore CU lock"


def test_an_unlock_set_by_hand_is_reported_and_cannot_be_edited_here(qtbot):
    panel = _panel(qtbot)
    panel._update_kernel_options_control(_tools(supported=True, item={
        "managed": False, "configured": True, "active": True, "external": True,
    }))
    _name, pill, button = panel.kernel_option_controls[OPTION]
    assert pill.text() == "Set outside Control Center" and not pill.isHidden()
    assert not button.isEnabled()


def test_pressing_the_button_asks_for_exactly_that_option(qtbot):
    panel = _panel(qtbot)
    panel._update_kernel_options_control(_tools(supported=True))
    seen = []
    panel.dependency_action_requested.connect(seen.append)
    panel.kernel_option_controls[OPTION][2].click()
    assert seen and seen[0]["action"] == "kernel_options_set"
    assert seen[0]["kernel_options"] == [OPTION]
    assert seen[0]["kernel_option_changed"] == OPTION
