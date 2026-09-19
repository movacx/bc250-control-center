from PyQt6.QtWidgets import QDialog

from frontends.desktop.core.cpu_persistence_plan import (
    CpuPersistencePlan,
    PersistenceBlocker,
    plan_cpu_persistence,
    validate_detection_for_persistence,
)
from frontends.desktop.pages.cpu_smu import CpuSmuPage


def detection(**updates):
    value = {
        "recorded": True,
        "matches_current_config": True,
        "snapshot": {
            "run_id": "run-1",
            "frequency": 3850,
            "scale": -35,
            "temperature": 90,
        },
    }
    value.update(updates)
    return value


def test_legacy_and_stale_detection_fail_before_candidate_planning():
    legacy = validate_detection_for_persistence(
        detection(legacy_override_in_detector_config=True)
    )
    stale = validate_detection_for_persistence(
        detection(matches_current_config=False)
    )

    assert legacy and legacy.tone == "orange"
    assert stale and stale.tone == "red"


def test_missing_detector_config_is_blocked_before_confirmation():
    result = plan_cpu_persistence(
        {"recorded": False, "current_config": {"exists": False, "valid": False}},
        scale_override=None,
        candidate_frequency=3700,
        candidate_temperature=90,
    )

    assert isinstance(result, PersistenceBlocker)
    assert result.title == "Run CPU detection first"
    assert "correct user-owned path" in result.message


def test_manual_scale_requires_exact_live_validation():
    result = plan_cpu_persistence(
        detection(),
        scale_override=-30,
        candidate_frequency=3700,
        candidate_temperature=85,
        scale_analysis={"requested_estimated_vid": 1175},
        live_state={"valid_for_persistence": False},
    )

    assert isinstance(result, PersistenceBlocker)
    assert result.title == "Apply this scale temporarily first"
    assert "main temporary apply button" in result.message


def test_manual_plan_binds_dialog_and_helper_arguments_to_same_candidate():
    result = plan_cpu_persistence(
        detection(),
        scale_override=-30,
        candidate_frequency=3700,
        candidate_temperature=85,
        scale_analysis={
            "requested_estimated_vid": 1175,
            "requires_extra_confirmation": True,
        },
        live_state={"valid_for_persistence": True, "test": {"test_id": "test-9"}},
    )

    assert isinstance(result, CpuPersistencePlan)
    assert result.boot_candidate == "3700 MHz | scale -30 | 85 °C"
    assert result.command_frequency == 3700
    assert result.command_temperature == 85
    assert result.confirm_scale_jump is True
    assert result.validation_source.template == "Live test {test_id}"
    assert dict(result.validation_source.values) == {"test_id": "test-9"}


def test_detected_plan_does_not_override_frequency_or_temperature_arguments():
    result = plan_cpu_persistence(
        detection(),
        scale_override=None,
        candidate_frequency=4000,
        candidate_temperature=70,
    )

    assert isinstance(result, CpuPersistencePlan)
    assert result.boot_candidate == "3850 MHz | scale -35 | 90 °C"
    assert result.command_frequency is None
    assert result.command_temperature is None


class _AcceptedDialog:
    def __init__(self, *_args, **_kwargs):
        pass

    def exec(self):
        return QDialog.DialogCode.Accepted


def test_real_page_dispatches_the_exact_live_tested_candidate(qtbot, monkeypatch):
    calls = []
    controller = type(
        "Controller",
        (),
        {
            "estado_resultado_deteccion_cpu": lambda _self: detection(),
            "evaluar_override_escala_cpu": lambda _self, scale, frequency: {
                "requested_estimated_vid": 1175,
                "requires_extra_confirmation": True,
            },
            "estado_prueba_escala_cpu": lambda _self, scale, frequency, temperature: {
                "valid_for_persistence": True,
                "test": {"test_id": "bound-test"},
            },
            "comando_cpu_oc_persistente_embebido": lambda _self, *args: calls.append(args) or ["safe-helper"],
        },
    )()
    monkeypatch.setattr("frontends.desktop.pages.cpu_smu.ConfirmDialog", _AcceptedDialog)
    page = CpuSmuPage(controller)
    qtbot.addWidget(page)
    page._set_manual_scale_available(True)
    page.scale_override_check.setChecked(True)
    page.scale_control.setValue(-30)
    page.frequency_control.setValue(3700)
    page.temperature_control.setValue(85)
    page._build_and_start_process = lambda operation, *_args: operation()

    page.enable_persistence()

    assert calls == [(-30, True, 3700, 85)]


def test_real_page_blocks_stale_detection_before_scale_queries(qtbot):
    calls = []
    controller = type(
        "Controller",
        (),
        {
            "estado_resultado_deteccion_cpu": lambda _self: detection(
                matches_current_config=False
            ),
            "evaluar_override_escala_cpu": lambda *_args: calls.append("unsafe query"),
        },
    )()
    page = CpuSmuPage(controller)
    qtbot.addWidget(page)
    page._set_manual_scale_available(True)
    page.scale_override_check.setChecked(True)
    notices = []
    page._show_info = lambda *args, **kwargs: notices.append((args, kwargs))

    page.enable_persistence()

    assert calls == []
    assert notices[0][0][0] == "CPU detection result changed"


def test_manual_mode_uses_one_apply_button_and_disables_unused_vid(qtbot):
    page = CpuSmuPage(type("Controller", (), {})())
    qtbot.addWidget(page)

    assert not hasattr(page, "test_scale_button")
    assert page.apply_button.text() == "Apply configuration + automatic scale"
    assert page.scale_override_check.isChecked() is False
    assert page.scale_override_check.isEnabled() is False
    assert page.vid_control.isEnabled() is True
    assert page.scale_control.isEnabled() is False

    page.scale_override_check.setChecked(True)

    assert page.scale_override_check.isChecked() is False
    assert page.scale_control.isEnabled() is False

    page._set_manual_scale_available(True)
    page.scale_override_check.setChecked(True)

    assert page.apply_button.text() == "Apply temporary OC + manual scale"
    assert page.vid_control.isEnabled() is False
    assert page.scale_control.isEnabled() is True


def test_manual_apply_dispatches_exact_frequency_scale_and_temperature(qtbot):
    page = CpuSmuPage(type("Controller", (), {})())
    qtbot.addWidget(page)
    calls = []
    page._set_manual_scale_available(True)
    page.scale_override_check.setChecked(True)
    page.frequency_control.setValue(3700)
    page.scale_control.setValue(-34)
    page.temperature_control.setValue(85)
    # An invalid VID must not block manual mode because the disabled VID field
    # is not part of the direct helper command.
    page.vid_control.setRange(0, 2000)
    page.vid_control.setValue(0)
    page._request_manual_apply = lambda *args: calls.append(args)

    page._apply_custom()

    assert calls == [(3700, -34, 85)]


def test_manual_scale_unlocks_only_for_current_verified_detection(qtbot):
    page = CpuSmuPage(object())
    qtbot.addWidget(page)

    def apply_detection(*, same_boot: bool, matches: bool = True):
        page._apply_refresh_payload({
            "performance": {},
            "tools": {},
            "persistent": {},
            "scale_live": {},
            "quick_access": {},
            "core_unlock": {},
            "detection": detection(
                same_boot=same_boot,
                matches_current_config=matches,
            ),
        })

    apply_detection(same_boot=True)
    assert page.scale_override_check.isEnabled() is True

    page.scale_override_check.setChecked(True)
    assert page.scale_override_check.isChecked() is True

    apply_detection(same_boot=False)
    assert page.scale_override_check.isChecked() is False
    assert page.scale_override_check.isEnabled() is False
    assert page.scale_control.isEnabled() is False
    assert "automatic live configuration" in page.scale_test_status.text()


def live_manual(scale):
    """A manual scale applied live this boot, which may never be persisted."""
    return {
        "active_in_current_session": True,
        "direct_manual": True,
        "valid_for_persistence": False,
        "test": {"scale": scale, "frequency": 3550, "temperature": 90},
    }


def test_the_plan_names_the_scale_that_is_running_when_another_one_would_boot():
    """The dialog promised -35 while the processor was running -26.

    Manual scale unlocks only for the detection session that produced it, so
    the check box can be switched off underneath the user while their manual
    value stays live in hardware. The save dialog then described the detector
    result and said nothing about the difference.
    """
    plan = plan_cpu_persistence(
        detection(),
        scale_override=None,
        candidate_frequency=3850,
        candidate_temperature=90,
        live_state=live_manual(-26),
    )

    assert isinstance(plan, CpuPersistencePlan)
    assert plan.active_scale == "-26"
    assert plan.live_notice is not None
    assert "automatic detection" in plan.live_notice.template


def test_nothing_is_said_when_what_runs_is_what_boots():
    matching = plan_cpu_persistence(
        detection(),
        scale_override=None,
        candidate_frequency=3850,
        candidate_temperature=90,
        live_state=live_manual(-35),
    )
    unknown = plan_cpu_persistence(
        detection(),
        scale_override=None,
        candidate_frequency=3850,
        candidate_temperature=90,
    )

    assert matching.active_scale == "" and matching.live_notice is None
    assert unknown.active_scale == "" and unknown.live_notice is None


def test_the_confirmation_shows_the_active_scale_and_drops_repeated_rows(qtbot):
    page = CpuSmuPage(object())
    qtbot.addWidget(page)
    plan = plan_cpu_persistence(
        detection(),
        scale_override=None,
        candidate_frequency=3850,
        candidate_temperature=90,
        live_state=live_manual(-26),
    )
    shown = {}

    class Dialog:
        def __init__(self, *args, **kwargs):
            shown.update(kwargs)

        def exec(self):
            return QDialog.DialogCode.Rejected

    import frontends.desktop.pages.cpu_smu as module

    original = module.ConfirmDialog
    module.ConfirmDialog = Dialog
    try:
        page._confirm_cpu_persistence(plan)
    finally:
        module.ConfirmDialog = original

    labels = [label for label, _value in shown["summary"]]
    assert ("Active scale", "-26") in shown["summary"]
    # The detected result equals the candidate here, and the scale line only
    # repeats it, so neither earns a row.
    assert "Detected result" not in labels
    assert "Scale" not in labels
    assert "automatic detection" in shown["notice"]
