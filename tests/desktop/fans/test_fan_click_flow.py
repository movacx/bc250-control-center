"""Fixed/Firmware changes use one verified write and no result dialog."""

import json
from dataclasses import replace

import pytest
from PyQt6.QtWidgets import QDialog

from frontends.desktop.pages import fans as fans_module
from frontends.desktop.pages.fans import FansPage
from tests.desktop.fans.test_fan_page import make_page, select


def test_normal_fixed_speed_is_one_verified_write_and_a_toast(qtbot, monkeypatch):
    page, controller, notices = make_page(qtbot, monkeypatch)
    select(page, 2, "fixed")
    page.editor.fixed_spin.setValue(60)
    page.editor.apply_button.click()
    assert controller.writes == [(2, 153)]
    assert controller.config["fan_channels"]["2"]["percent"] == 60
    assert notices["confirms"] == notices["dialogs"] == []
    assert notices["toasts"][-1][0] == "Fan speed applied"


@pytest.mark.parametrize("accepted", [True, False])
def test_low_duty_asks_before_saving_or_writing(qtbot, monkeypatch, accepted):
    page, controller, notices = make_page(qtbot, monkeypatch)
    select(page, 2, "fixed")
    page.editor.fixed_spin.setValue(25)
    notices["answer"] = QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected
    page.editor.apply_button.click()
    assert notices["confirms"][0][0] == "Apply a low fan speed"
    assert controller.writes == ([(2, 64)] if accepted else [])
    if not accepted:
        assert controller.saved == []
        assert page.editor.dirty


def test_firmware_restores_automatic_once_with_service_off(qtbot, monkeypatch):
    page, controller, notices = make_page(qtbot, monkeypatch, config={"fan_channels": {"2": {"mode": "fixed", "percent": 60}}})
    select(page, 2, "firmware")
    page.editor.apply_button.click()
    assert controller.writes == [(2, "auto")]
    assert notices["dialogs"] == []
    assert notices["toasts"][-1][0] == "Automatic fan control restored"


def test_failed_readback_never_reports_success(qtbot, monkeypatch):
    page, controller, notices = make_page(qtbot, monkeypatch)
    controller.verified_value = 127
    select(page, 2, "fixed")
    page.editor.fixed_spin.setValue(60)
    page.editor.apply_button.click()
    assert controller.writes == [(2, 153)]
    assert notices["dialogs"][-1][0] == "Fan PWM operation failed"
    assert "read-back was 127" in notices["dialogs"][-1][1]
    assert notices["toasts"] == []
    assert not page._busy


@pytest.mark.parametrize("result", [None, {}, {"verified": {"pwm": 3, "value": 153}}, {"verified": {"pwm": 2, "value": 127}}])
def test_missing_or_mismatched_verification_is_rejected(result):
    assert FansPage._verify(result, pwm=2, raw=153)



def test_profiles_round_trip_a_file_without_touching_hardware(qtbot, monkeypatch, tmp_path):
    page, controller, notices = make_page(qtbot, monkeypatch)
    target = tmp_path / "profiles.json"
    monkeypatch.setattr(fans_module.QFileDialog, "getSaveFileName", lambda *a, **kw: (str(target), ""))
    page.export_profiles_to_file()
    document = json.loads(target.read_text())
    assert document["kind"] == "bc250-fan-profiles"
    assert len(document["profiles"]) == 3
    document["profiles"][0].update(name="Night", percent=33)
    target.write_text(json.dumps(document))
    saved = []
    monkeypatch.setattr(fans_module, "save_fan_profile", lambda index, profile: saved.append((index, profile)))
    monkeypatch.setattr(fans_module.QFileDialog, "getOpenFileName", lambda *a, **kw: (str(target), ""))
    page.import_profiles_from_file()
    assert (saved[0][1].name, saved[0][1].percent) == ("Night", 33)
    assert controller.writes == controller.policies == []
    assert notices["toasts"][-1][0] == "Fan profiles imported"


def test_bad_profile_file_is_refused_without_partial_import(qtbot, monkeypatch, tmp_path):
    page, controller, notices = make_page(qtbot, monkeypatch)
    target = tmp_path / "bad.json"
    target.write_text(json.dumps({"kind": "something"}))
    saved = []
    monkeypatch.setattr(fans_module, "save_fan_profile", lambda *a: saved.append(a))
    page._import_profiles(target)
    assert notices["dialogs"][-1][0] == "Could not import fan profiles"
    assert saved == controller.writes == controller.policies == []


@pytest.mark.parametrize("installed", [False, True])
def test_decky_export_preserves_names_and_reports_plugin_and_speed_floor(qtbot, monkeypatch, installed):
    profiles = list(fans_module.load_fan_profiles())
    profiles[0] = replace(profiles[0], percent=10)
    profiles[1] = replace(profiles[1], name="Night")
    monkeypatch.setattr(fans_module, "load_fan_profiles", lambda: profiles)
    page, controller, notices = make_page(qtbot, monkeypatch)
    controller.estado_quick_access_decky = lambda: {"decky_detected": True, "plugin_present": installed}
    page.export_profiles_to_decky()
    qtbot.waitUntil(lambda: bool(notices["toasts"] or notices["dialogs"]))
    assert [entry["key"] for entry in controller.exports[0]] == ["quiet", "balanced", "boost"]
    assert [entry["name"] for entry in controller.exports[0]][:2] == ["Quiet", "Night"]
    assert controller.exports[0][0]["percent"] == 20
    message = (notices["toasts"] or notices["dialogs"])[-1][1]
    assert "PWM3–PWM8" in message and "never PWM2" in message
    assert "Quiet: 10 % → 20 % in Decky." in message
    if installed:
        assert message.startswith("Profiles exported to Decky Quick Access.")
    else:
        assert "the plugin is not installed yet" in message
    assert controller.writes == controller.policies == []


def test_handoff_blocks_channel_writes_until_control_is_taken_back(qtbot, monkeypatch):
    page, controller, notices = make_page(qtbot, monkeypatch)
    page._system_fan_control["managers"] = ["CoolerControl"]
    page._toggle_external_control()
    qtbot.waitUntil(page._fan_external)
    assert notices["confirms"][-1][0] == "Hand off the fan"
    assert controller.writes == [("external", True)]
    assert not page.editor.isEnabled()
    before = controller.read_local_config()
    page._apply_channel(2, {"mode": "fixed", "percent": 80})
    page._apply_channel(2, None)
    assert controller.config == before
    assert controller.writes == [("external", True)]
    qtbot.waitUntil(lambda: not page._background.is_running("fan-external-control"))
    page._toggle_external_control()
    qtbot.waitUntil(lambda: not page._fan_external())
    assert controller.writes == [("external", True), ("external", False)]
    assert len(notices["confirms"]) == 1
    assert page.editor.isEnabled()



# --------------------------- reported 2026-11-08: profile with every channel on Firmware


def _render(page, fans):
    page.current_state = {**page.current_state, "sensores": {"chip": "nct6686", "fans": fans}}
    page._render()


def _header(pwm, rpm):
    return {"index": pwm, "rpm": rpm, "pwm": 128, "pwm_path": f"/sys/class/hwmon/hwmon2/pwm{pwm}",
            "pwm_root_writable": True}


def test_balanced_with_every_channel_on_firmware_drives_the_turning_fan(qtbot, monkeypatch):
    """The report: 0 controlled, Profile Balanced, Apply -> "This fan mode has
    no valid channel" shown as hardware error BC250-FAN-001."""
    page, controller, notices = make_page(qtbot, monkeypatch)
    _render(page, [_header(2, 2068)] + [_header(pwm, 0) for pwm in (1, 3, 4, 5)])
    page.profile_combo.setCurrentIndex(page.profile_combo.findData("Balanced"))

    page._apply_profile()

    assert not any(title == "Could not save fan curve" for title, _m in notices["dialogs"])
    assert list(controller.config["fan_channels"]) == ["2"]
    assert controller.config["fan_channels"]["2"]["mode"] == "curve"


def test_a_profile_with_no_fan_turning_uses_the_selected_header(qtbot, monkeypatch):
    page, controller, _notices = make_page(qtbot, monkeypatch)
    _render(page, [_header(pwm, 0) for pwm in (1, 2, 3, 4, 5)])
    select(page, 4)

    page._apply_profile()

    assert list(controller.config["fan_channels"]) == ["4"]


def test_a_profile_with_nothing_writable_is_a_plain_notice_not_a_hardware_error(qtbot, monkeypatch):
    page, controller, notices = make_page(qtbot, monkeypatch)
    _render(page, [])

    page._apply_profile()

    assert [title for title, _m in notices["dialogs"]] == ["No PWM channel"]
    assert "fan_channels" not in controller.config
