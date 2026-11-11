"""Regressions reproduced during the manual review of the Fans workspace."""
import json
from copy import deepcopy

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QDialog, QInputDialog

from bc250cc.domain.fan import engine
from bc250cc.domain.fan.profile_exchange import (
    channel_profiles_document,
    imported_profile_updates,
    parse_channel_profiles_document,
)
from frontends.desktop.pages import fans as module
from frontends.desktop.pages import fans_widgets
from tests.desktop.fans.test_fan_page import make_page, select

PROFILES = [
    {"key": "quiet", "name": "Quiet", "percent": 45},
    {"key": "balanced", "name": "Balanced", "percent": 60},
    {"key": "maximum", "name": "Maximum", "percent": 100},
]
CONFIG = {"fan_channels": {"2": {
    "mode": "curve", "source": "cpu", "points": [[40, 30], [60, 50], [80, 100]],
}}}


def input_name(monkeypatch, name):
    def execute(dialog):
        dialog.setTextValue(name)
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QInputDialog, "exec", execute)


def test_sync_does_not_announce_success_until_background_completion(qtbot, monkeypatch):
    page, controller, notices = make_page(qtbot, monkeypatch, config=CONFIG, service_on=True)
    pending = {}
    def start(name, operation, success=None, failure=None, finished=None):
        if name == "fan-system-sync":
            pending.update(operation=operation, success=success, failure=failure, finished=finished)
        return True
    monkeypatch.setattr(page._background, "start", start)
    select(page, 2, "fixed")
    page.editor.fixed_spin.setValue(99)
    page.editor.apply()
    assert not any(t[0] == "Saved" for t in notices["toasts"])
    pending["failure"]("QA rejected policy")
    assert not any(t[0] == "Saved" for t in notices["toasts"])
    assert page.editor.retry and page.editor.apply_button.isEnabled()
    page.editor.apply()
    pending["success"](pending["operation"]())
    assert [t[0] for t in notices["toasts"]].count("Saved") == 1
    assert not page.editor.retry


def test_legacy_helper_is_rejected_before_saving_mix(qtbot, monkeypatch):
    page, controller, notices = make_page(qtbot, monkeypatch, config=CONFIG, service_on=True)
    page._system_fan_control["policy_schemas"] = [1]
    select(page, 2, "mix")
    before = controller.read_local_config()
    page.editor.apply()
    assert controller.config == before and controller.policies == []
    assert page.editor.dirty
    assert notices["dialogs"][-1] == ("PWM control is not ready", "Update fan helper")


def test_failed_write_can_retry_same_value_without_another_edit(qtbot, monkeypatch):
    page, controller, notices = make_page(qtbot, monkeypatch, config=CONFIG)
    select(page, 2, "fixed")
    page.editor.fixed_spin.setValue(99)
    original = controller.aplicar_pwm_fan
    def deny(*_args):
        raise RuntimeError("QA denied")
    monkeypatch.setattr(controller, "aplicar_pwm_fan", deny)
    page.editor.apply()
    assert page.editor.retry and not page.editor.dirty
    assert page.editor.apply_button.isEnabled()
    assert page.model.rows[page.model.row_for(2)]["cells"][module.STATE] == "Pending"
    monkeypatch.setattr(controller, "aplicar_pwm_fan", original)
    page.editor.apply_button.click()
    assert controller.writes[-1] == (2, 252)
    assert not page.editor.retry and not page.editor.apply_button.isEnabled()
    assert page.model.rows[page.model.row_for(2)]["cells"][module.STATE] == "Applied"


def test_cancel_low_duty_confirmation_keeps_original_channel_and_draft(qtbot, monkeypatch):
    page, controller, _ = make_page(qtbot, monkeypatch, config=CONFIG)
    select(page, 2, "fixed")
    page.editor.fixed_spin.setValue(10)
    answers = iter((QDialog.DialogCode.Accepted, QDialog.DialogCode.Rejected))
    class Confirm:
        def __init__(self, *_args, **_kwargs): pass
        def exec(self): return next(answers)
    monkeypatch.setattr(module, "ConfirmDialog", Confirm)
    select(page, 1)
    assert page.editor.pwm == 2 and page.editor.dirty
    assert page.model.pwm_at(page.table.currentIndex().row()) == 2
    assert page.editor.fixed_spin.value() == 10
    assert controller.writes == [] and controller.config == CONFIG


def test_global_profile_requires_explicit_discard_of_visible_draft(qtbot, monkeypatch):
    page, controller, notices = make_page(qtbot, monkeypatch, config=CONFIG)
    select(page, 2, "curve")
    page.editor.points._rows[1][1].setValue(65)
    page.profile_combo.setCurrentIndex(page.profile_combo.findData("Balanced"))
    notices["answer"] = QDialog.DialogCode.Rejected
    page.profile_apply.click()
    assert controller.config == CONFIG and page.editor.dirty
    assert page.editor.points.points()[1] == [60, 65]
    notices["answer"] = QDialog.DialogCode.Accepted  # explicit Discard
    page.profile_apply.click()
    assert controller.config["fan_channels"]["2"]["source"] == "hottest"
    assert not page.editor.dirty


def test_save_as_captures_draft_without_applying_or_losing_it(qtbot, monkeypatch):
    page, controller, _ = make_page(qtbot, monkeypatch, config=CONFIG)
    select(page, 2, "curve")
    page.editor.points._rows[1][1].setValue(65)
    input_name(monkeypatch, "Night")
    page._save_profile()
    assert controller.config["fan_modes"][0]["channels"]["2"]["points"][1] == [60, 65]
    assert controller.config["fan_channels"] == CONFIG["fan_channels"]
    assert page.editor.dirty and controller.writes == controller.policies == []


@pytest.mark.parametrize("name", ["Balanced", "balanced", "Equilibrado"])
def test_save_as_refuses_builtin_names_and_current_translation(qtbot, monkeypatch, name):
    page, controller, _ = make_page(qtbot, monkeypatch, config=CONFIG)
    original = module.tr
    monkeypatch.setattr(module, "tr", lambda text: "Equilibrado" if text == "Balanced" else original(text))
    input_name(monkeypatch, name)
    page._save_profile()
    assert not controller.config.get("fan_modes")


def test_cancel_replacing_named_profile_preserves_it(qtbot, monkeypatch):
    config = deepcopy(CONFIG)
    config["fan_modes"] = [{"name": "Night", "channels": {"2": {"mode": "fixed", "percent": 90}}}]
    page, controller, notices = make_page(qtbot, monkeypatch, config=config)
    input_name(monkeypatch, "Night")
    notices["answer"] = QDialog.DialogCode.Rejected
    page._save_profile()
    assert controller.config == config


def test_override_offers_resume_without_modifying_a_point(qtbot, monkeypatch):
    page, controller, _ = make_page(qtbot, monkeypatch, config=CONFIG, service_on=True)
    page._system_fan_control.update(state="override", status={"pwm": 2})
    page._render()
    assert page.editor.resume and page.editor.apply_button.isEnabled()
    assert page.editor.apply_button.text() == "Resume"
    assert not page.sync_button.isHidden()
    page.editor.apply_button.click()
    qtbot.waitUntil(lambda: bool(controller.policies))


def test_every_channel_field_survives_file_round_trip_without_activation():
    channels = engine.validate_policy({"schema": 2, "channels": {
        "2": {"mode": "mix", "mix": [
            {"source": "gpu", "points": [[40, 30], [80, 100]]},
            {"source": "vrm", "points": [[50, 40], [90, 100]]},
        ], "min_percent": 25, "max_percent": 99, "deadband_percent": 4,
            "start_percent": 45, "response_delay_seconds": 2, "max_up_step_percent": 20},
        "3": {"mode": "fixed", "role": "pump", "percent": 90},
    }})["channels"]
    config = {"fan_channels": channels, "fan_channel_labels": {"2": "Intake"},
              "fan_modes": [{"name": "Gaming", "channels": channels}], "fan_active_mode": "Gaming"}
    bundle = parse_channel_profiles_document(json.loads(json.dumps(channel_profiles_document(PROFILES, config))))
    assert bundle["channels"] == channels and bundle["labels"] == {"2": "Intake"}
    updates = imported_profile_updates(CONFIG, bundle, snapshot_name="Imported configuration")
    assert updates["fan_modes"] == config["fan_modes"]
    assert "fan_channels" not in updates and "fan_active_mode" not in updates


def test_legacy_curve_is_imported_as_a_saved_mode_not_silently_ignored():
    from bc250cc.domain.fan.profile_exchange import fan_profiles_document
    legacy = fan_profiles_document(PROFILES, {"pwm": 2, "points": [
        {"temperature": t, "speed": p} for t, p in [[40, 30], [60, 50], [80, 100]]
    ]})
    bundle = parse_channel_profiles_document(legacy)
    updates = imported_profile_updates({}, bundle, snapshot_name="Imported configuration")
    assert updates["fan_modes"][0]["channels"]["2"]["points"] == [[40, 30], [60, 50], [80, 100]]
    assert "fan_channels" not in updates


@pytest.mark.parametrize("field,value", [("channels", {"2": {"mode": "broken"}}),
    ("modes", [{"name": "X", "channels": {}}]), ("labels", {"99": "Wrong"})])
def test_corrupt_bundle_is_refused_whole(field, value):
    document = channel_profiles_document(PROFILES, CONFIG)
    document[field] = value
    with pytest.raises(ValueError):
        parse_channel_profiles_document(document)


def test_import_updates_button_values_and_callbacks_without_restart(qtbot, monkeypatch, tmp_path):
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(fans_widgets, "application_settings", lambda: settings)
    page, controller, _ = make_page(qtbot, monkeypatch, config=CONFIG)
    profiles = deepcopy(PROFILES)
    profiles[0]["percent"], profiles[1]["percent"] = 46, 61
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps(channel_profiles_document(profiles, CONFIG)))
    page._import_profiles(path)
    select(page, 2, "fixed")
    for button, percent in zip(page.editor.preset_buttons, [46, 61, 100]):
        assert button.text() == f"{percent} %"
        button.click()
        assert page.editor.fixed_spin.value() == percent
    assert controller.config["fan_channels"] == CONFIG["fan_channels"]
    assert controller.writes == []


def test_custom_state_is_not_labelled_as_balanced(qtbot, monkeypatch):
    page, _, _ = make_page(qtbot, monkeypatch, config=CONFIG)
    assert page.profile_combo.currentText() == "Custom"
    assert not page.profile_apply.isEnabled()


def test_action_buttons_stay_outside_editor_scroll_and_chart_is_bounded(qtbot, monkeypatch):
    page, _, _ = make_page(qtbot, monkeypatch, config=CONFIG)
    page.resize(1440, 900)
    page.show()
    select(page, 2, "curve")
    qtbot.waitUntil(lambda: page.editor.apply_button.isVisible())
    page.editor_scroll.verticalScrollBar().setValue(page.editor_scroll.verticalScrollBar().maximum())
    assert page.editor.feedback.parentWidget() is page.splitter.widget(1)
    assert page.editor.plot.height() == 240
    assert page.editor.plot.scale.height() <= page.editor.plot.height()
    assert page.editor.apply_button.isVisible()
    assert page.editor.apply_button.mapTo(page, page.editor.apply_button.rect().center()).y() < page.height()


def test_reimporting_same_snapshot_is_idempotent():
    bundle = parse_channel_profiles_document(channel_profiles_document(PROFILES, CONFIG))
    once = imported_profile_updates({}, bundle, snapshot_name="Imported configuration")
    twice = imported_profile_updates(once, bundle, snapshot_name="Imported configuration")
    assert twice == once


def test_invalid_schema_type_is_not_treated_as_legacy_version_one():
    document = channel_profiles_document(PROFILES, CONFIG)
    document["schema"] = True
    with pytest.raises(ValueError):
        parse_channel_profiles_document(document)


def test_calibration_temperature_includes_hot_board_but_not_storage(tmp_path):
    for index, name, value in [(0, "k10temp", 45000), (1, "nct6686", 90000), (2, "nvme", 120000)]:
        hwmon = tmp_path / f"hwmon{index}"
        hwmon.mkdir()
        (hwmon / "name").write_text(name)
        (hwmon / "temp1_input").write_text(str(value))
    assert module._hottest_temperature(tmp_path) == 90
    (tmp_path / "hwmon0/temp1_input").unlink()
    assert module._hottest_temperature(tmp_path) is None


def test_helper_capabilities_are_read_without_authentication(tmp_path, monkeypatch):
    from bc250cc.infrastructure.fan_repository import FanRepository
    helper = tmp_path / "fan-helper"
    helper.write_text("POLICY_SCHEMA = 1\n")
    repo = FanRepository()
    monkeypatch.setattr(repo, "_fan_pwm_packaged_helper_path", lambda: helper)
    assert repo._installed_fan_policy_schemas() == [1]
    helper.write_text("POLICY_SCHEMA = 2\n# v2\n")
    assert repo._installed_fan_policy_schemas() == [1, 2]
    helper.write_text("# declaration unavailable\n")
    assert repo._installed_fan_policy_schemas() == []


def test_queued_sync_resubmits_latest_policy_only_after_executor_releases_key(qtbot, monkeypatch):
    page, controller, _ = make_page(qtbot, monkeypatch, config=CONFIG, service_on=True)
    captured, running = [], set()
    def start(name, operation, success=None, failure=None, finished=None):
        if name == "fan-system-sync":
            assert name not in running
            running.add(name)
            captured.append((operation, success, failure, finished))
        return True
    monkeypatch.setattr(page._background, "start", start)
    monkeypatch.setattr(page._background, "is_running", lambda name: name in running)
    page._sync_system_fan_policy(force=True)
    controller.config["fan_channels"]["2"] = {"mode": "fixed", "percent": 90}
    page._fan_root_config = controller.read_local_config()
    page._sync_system_fan_policy(force=True, notify="newest")
    assert len(captured) == 1
    op, success, failure, finished = captured[0]
    success(op())
    assert len(captured) == 1
    running.remove("fan-system-sync")
    finished()
    assert len(captured) == 2
    op, success, failure, finished = captured[1]
    success(op())
    running.remove("fan-system-sync")
    finished()
    assert controller.policies[-1]["channels"]["2"]["percent"] == 90


def test_save_dialog_has_readable_width_localized_buttons_and_bounded_name(qtbot, monkeypatch):
    from PyQt6.QtWidgets import QLayout, QLineEdit
    page, controller, _ = make_page(qtbot, monkeypatch, config=CONFIG)
    def execute(dialog):
        dialog.show()
        qtbot.waitUntil(lambda: dialog.width() >= 360)
        assert dialog.layout().sizeConstraint() == QLayout.SizeConstraint.SetMinimumSize
        assert dialog.okButtonText() == "Save" and dialog.cancelButtonText() == "Cancel"
        assert dialog.findChild(QLineEdit).maxLength() == 32
        dialog.setTextValue("  QA   Night  ")
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QInputDialog, "exec", execute)
    page._save_profile()
    assert controller.config["fan_modes"][-1]["name"] == "QA Night"
    assert page.profile_combo.currentData() == "QA Night"


def test_calibration_cannot_stop_saved_pump_even_with_unapplied_fan_role(qtbot, monkeypatch):
    config = {"fan_channels": {"2": {"mode": "fixed", "role": "pump", "percent": 90}}}
    page, controller, notices = make_page(qtbot, monkeypatch, config=config)
    select(page, 2, "curve")
    page.editor.role.setCurrentIndex(page.editor.role.findData("fan"))
    page._calibrate_channel(2)
    assert controller.writes == []
    assert notices["dialogs"][-1] == ("Calibration stopped", "pumps are not calibrated: stopping a pump is unsafe")
