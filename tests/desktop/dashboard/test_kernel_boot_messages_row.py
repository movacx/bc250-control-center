"""Hiding the kernel's boot messages (the RDSEED warning): one more kernel boot option.

``loglevel=0`` is the only level that hides the level 0 warning the BC-250's
CPU makes the kernel print, and it silences every other boot message too. The
row is offered wherever the boot loader is managed, and drawn plainly: it risks
nothing for the board, which its confirmation says in words.
"""

from frontends.desktop.pages.additional_settings import AdditionalSettingsPage

OPTION = "loglevel=0"


def _tools(*, item=None, allowed=None):
    off = {"managed": False, "configured": False, "active": False, "external": False}
    arguments = {
        "mitigations=off": dict(off), "nosmt": dict(off), "amdgpu.bc250_cc_write_mode=3": dict(off),
        OPTION: item or dict(off),
    }
    state = {"available": True, "arguments": arguments, "cu_unlock": {"supported": False, "mode": ""}}
    if allowed is not None:
        state["allowed"] = allowed
    return {"system_setup": {"helper_available": True, "kernel_options": state}}


def _panel(qtbot):
    page = AdditionalSettingsPage()
    qtbot.addWidget(page)
    page.resize(1200, 900)
    page.show()
    page.panel._page = page
    return page.panel


def test_the_row_is_offered_and_not_drawn_as_a_warning(qtbot):
    panel = _panel(qtbot)
    panel._update_kernel_options_control(_tools())
    name, _pill, button = panel.kernel_option_controls[OPTION]
    assert not name.isHidden() and not button.isHidden()
    assert button.text() == "Hide boot messages"
    assert button.property("dangerAction") is False
    assert "RDSEED" in name.text()


def test_a_boot_menu_that_does_not_take_it_does_not_show_the_row(qtbot):
    panel = _panel(qtbot)
    panel._update_kernel_options_control(_tools(allowed=["mitigations=off", "nosmt"]))
    name, _pill, button = panel.kernel_option_controls[OPTION]
    assert name.isHidden() and button.isHidden()


def test_a_staged_change_is_taken_back_with_the_same_button(qtbot):
    panel = _panel(qtbot)
    panel._update_kernel_options_control(
        _tools(item={"managed": True, "configured": True, "active": False, "external": False})
    )
    _name, _pill, button = panel.kernel_option_controls[OPTION]
    assert button.text() == "Show boot messages"
    requests = []
    panel.dependency_action_requested.connect(requests.append)
    button.click()
    assert requests[-1]["action"] == "kernel_options_set"
    assert requests[-1]["kernel_options"] == []
    assert requests[-1]["kernel_option_changed"] == OPTION


def test_a_loglevel_set_outside_control_center_is_left_alone(qtbot):
    panel = _panel(qtbot)
    panel._update_kernel_options_control(
        _tools(item={"managed": False, "configured": True, "active": True, "external": True})
    )
    _name, _pill, button = panel.kernel_option_controls[OPTION]
    assert not button.isEnabled()
