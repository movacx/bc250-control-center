"""Selection and live telemetry must preserve unapplied channel drafts."""

from PyQt6.QtWidgets import QDialog

from frontends.desktop.pages import fans as fans_module
from tests.desktop.fans.test_fan_page import forum_config, make_page, select


def test_selection_reads_channel_without_saving_or_writing(qtbot, monkeypatch):
    page, controller, notices = make_page(qtbot, monkeypatch, config=forum_config())
    before = controller.read_local_config()
    for pwm in (2, 1, 3, 4, 5):
        select(page, pwm)
        assert page.editor.pwm == pwm
        assert page.editor.mode.currentData() == ("fixed" if pwm == 2 else "curve")
    assert controller.config == before
    assert controller.saved == controller.writes == controller.policies == []
    assert notices["confirms"] == []


def test_dirty_draft_survives_refresh_with_live_readings(qtbot, monkeypatch):
    page, controller, _ = make_page(qtbot, monkeypatch)
    select(page, 2, "fixed")
    page.editor.fixed_spin.setValue(57)
    assert page.editor.dirty
    page.current_state["sensores"]["fans"][1]["rpm"] = 2100
    page._apply_refresh_payload({"fans": page.current_state, "system": page._system_fan_control})
    assert page.editor.pwm == 2
    assert page.editor.mode.currentData() == "fixed"
    assert page.editor.fixed_spin.value() == 57
    assert page.editor.dirty
    assert "2100 RPM" in page.editor.live.text()
    assert controller.saved == controller.writes == []


def test_cancel_discard_keeps_selection_and_draft(qtbot, monkeypatch):
    page, controller, notices = make_page(qtbot, monkeypatch)
    select(page, 2, "fixed")
    page.editor.fixed_spin.setValue(57)
    notices["answer"] = QDialog.DialogCode.Rejected
    select(page, 3)
    assert page.model.pwm_at(page.table.currentIndex().row()) == 2
    assert page.editor.pwm == 2 and page.editor.fixed_spin.value() == 57
    assert notices["confirms"][-1][0] == "Unapplied changes"
    assert controller.saved == controller.writes == []


def test_accept_discard_loads_selected_channel(qtbot, monkeypatch):
    page, controller, notices = make_page(qtbot, monkeypatch)
    select(page, 2, "fixed")
    page.editor.fixed_spin.setValue(57)
    notices["answer"] = fans_module.DIALOG_SECONDARY  # Discard
    select(page, 3)
    assert page.editor.pwm == 3
    assert page.editor.mode.currentData() == "firmware"
    assert not page.editor.dirty
    assert notices["confirms"][-1][0] == "Unapplied changes"
    assert controller.saved == controller.writes == []


def test_revert_restores_saved_setting_without_hardware_write(qtbot, monkeypatch):
    page, controller, _ = make_page(qtbot, monkeypatch, config=forum_config())
    select(page, 2)
    page.editor.fixed_spin.setValue(70)
    page.editor.revert_button.click()
    assert page.editor.fixed_spin.value() == 90
    assert not page.editor.dirty
    assert controller.saved == controller.writes == []


def test_unused_header_cannot_dispatch_an_immediate_fixed_write(qtbot, monkeypatch):
    page, controller, _ = make_page(qtbot, monkeypatch)
    page.current_state["sensores"]["fans"] = []
    page._render()
    select(page, 3, "fixed")
    page.editor.fixed_spin.setValue(60)
    page.editor.apply_button.click()
    assert controller.saved == controller.writes == []


def test_read_only_channel_cannot_dispatch_an_immediate_fixed_write(qtbot, monkeypatch):
    page, controller, _ = make_page(qtbot, monkeypatch)
    for fan in page.current_state["sensores"]["fans"]:
        fan["pwm_root_writable"] = False
    page._render()
    select(page, 2, "fixed")
    page.editor.fixed_spin.setValue(60)
    page.editor.apply_button.click()
    assert controller.saved == controller.writes == []


def test_busy_write_does_not_accept_a_second_setting(qtbot, monkeypatch):
    page, controller, _ = make_page(qtbot, monkeypatch)
    select(page, 2, "fixed")
    page.editor.fixed_spin.setValue(60)
    page._busy = True
    page.editor.apply_button.click()
    assert controller.saved == controller.writes == []
    assert page.editor.dirty


def test_apply_from_the_switch_dialog_saves_the_draft_then_moves_on(qtbot, monkeypatch):
    """The dialog offers Apply too: the draft is saved for its own channel and
    the row the user clicked is the one that ends up selected."""
    page, controller, notices = make_page(qtbot, monkeypatch)
    select(page, 2, "fixed")
    page.editor.fixed_spin.setValue(57)
    notices["answer"] = QDialog.DialogCode.Accepted  # Apply
    select(page, 3)

    assert controller.config["fan_channels"]["2"]["percent"] == 57
    assert page.editor.pwm == 3 and not page.editor.dirty
    assert page.model.pwm_at(page.table.currentIndex().row()) == 3


def test_apply_from_the_switch_dialog_refuses_an_invalid_draft(qtbot, monkeypatch):
    page, controller, notices = make_page(qtbot, monkeypatch)
    select(page, 2, "fixed")
    page.editor.role.setCurrentIndex(page.editor.role.findData("pump"))
    page.editor.fixed_spin.setValue(10)  # a pump under 30 %: not valid
    notices["answer"] = QDialog.DialogCode.Accepted
    select(page, 3)

    assert page.editor.pwm == 2 and page.editor.dirty
    assert "fan_channels" not in controller.config
