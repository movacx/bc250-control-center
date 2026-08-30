from pathlib import Path

import pytest

import bc250cc.infrastructure.cpu_oc_config as cpu_oc_config
from bc250cc.infrastructure.cpu_repository import CPURepository
from frontends.desktop.pages.cpu_smu import CpuSmuPage


def _config_text(frequency=3800, scale=-32, temperature=90):
    return (
        "[overclock]\n"
        f"frequency = {frequency}\n"
        f"scale = {scale}\n"
        f"max_temperature = {temperature}\n"
    )


def test_cpu_oc_config_parser_exposes_real_persistent_values(tmp_path):
    config = tmp_path / "bc250-smu-oc.conf"
    config.write_text(_config_text(), encoding="utf-8")

    state = CPURepository._read_cpu_oc_config(config)

    assert state["valid"] is True
    assert state["frequency"] == 3800
    assert state["scale"] == -32
    assert state["max_temperature"] == 90
    assert state["estimated_vid"] == 1154
    assert state["vid_source"] == "upstream-curve-estimate"


@pytest.mark.parametrize(
    "content, expected_error",
    (
        ("[overclock]\nfrequency = 9999\nscale = -32\nmax_temperature = 90\n", "frequency"),
        ("[overclock]\nfrequency = 3800\nscale = -99\nmax_temperature = 90\n", "scale"),
        ("[overclock]\nfrequency = nope\nscale = -32\nmax_temperature = 90\n", "Invalid"),
    ),
)
def test_cpu_oc_config_parser_rejects_invalid_persistent_values(tmp_path, content, expected_error):
    config = tmp_path / "bc250-smu-oc.conf"
    config.write_text(content, encoding="utf-8")

    state = CPURepository._read_cpu_oc_config(config)

    assert state["valid"] is False
    assert expected_error.lower() in state["error"].lower()


def test_manual_scale_candidate_uses_separate_file_and_preserves_detector(tmp_path):
    detector = tmp_path / "overclock.conf"
    candidate = tmp_path / "overclock.live.conf"
    detector.write_text(_config_text(frequency=3850, scale=-35), encoding="utf-8")
    before = detector.read_bytes()

    state = CPURepository._write_cpu_candidate_config(
        candidate, frequency=3850, scale=-32, temperature=90
    )

    assert detector.read_bytes() == before
    assert state["frequency"] == 3850
    assert state["scale"] == -32
    assert state["max_temperature"] == 90
    assert not list(tmp_path.glob("*.tmp"))


def test_manual_scale_candidate_is_strictly_validated(tmp_path):
    candidate = tmp_path / "overclock.live.conf"

    with pytest.raises((TypeError, ValueError)):
        CPURepository._write_cpu_candidate_config(
            candidate, frequency=3850, scale="-32; reboot", temperature=90
        )


def test_scale_override_blocks_large_jump_and_exposes_estimated_vid():
    analysis = CPURepository._scale_override_analysis(3850, -34, -10)

    assert analysis["allowed"] is False
    assert analysis["allowed_min"] == -50
    assert analysis["allowed_max"] == 0
    assert analysis["requested_estimated_vid"] > analysis["reference_estimated_vid"]
    assert analysis["estimated_vid_delta"] > 0


def test_scale_override_exposes_confirmation_requirement_after_two_steps():
    analysis = CPURepository._scale_override_analysis(3850, -34, -31)

    assert analysis["allowed"] is True
    assert analysis["requires_extra_confirmation"] is True
    assert analysis["delta_steps"] == 3


def test_scale_reference_does_not_drift_after_an_app_override():
    class MemoryConfig:
        def __init__(self):
            self.data = {}

        def leer_config(self):
            return dict(self.data)

        def guardar_config(self, update):
            self.data.update(update)

    repository = CPURepository()
    repository.configuracion = MemoryConfig()
    parsed = {
        "valid": True,
        "frequency": 3850,
        "scale": -34,
        "max_temperature": 90,
    }

    assert repository._remembered_scale_reference(parsed) == -34
    repository._store_scale_context(parsed, detected_scale=-34, last_written_scale=-31)
    parsed["scale"] = -31
    assert repository._remembered_scale_reference(parsed) == -34

    # A value not written by the app means bc250-detect regenerated the file.
    parsed["scale"] = -33
    assert repository._remembered_scale_reference(parsed) == -33


def test_cpu_page_initializes_from_active_custom_config_without_resetting_edits(qtbot):
    page = CpuSmuPage(object())
    qtbot.addWidget(page)
    persistent = {
        "config": {
            "exists": True,
            "valid": True,
            "frequency": 3800,
            "scale": -32,
            "max_temperature": 90,
            "estimated_vid": 1154,
            "vid_source": "upstream-curve-estimate",
        }
    }

    page._sync_active_cpu_config(persistent)

    assert page.frequency_control.value() == 3800
    assert page.vid_control.value() == 1154
    assert page.scale_control.value() == -32
    assert page._selected_profile_name == "Custom"
    assert "~1154 mV" in page.profile_stat.detail.text()

    page.frequency_control.setValue(3900)
    page._sync_active_cpu_config(persistent)
    assert page.frequency_control.value() == 3900


def test_cpu_page_restores_exact_profile_when_saved_vid_matches(qtbot):
    page = CpuSmuPage(object())
    qtbot.addWidget(page)

    page._sync_active_cpu_config({
        "config": {
            "exists": True,
            "valid": True,
            "frequency": 3850,
            "scale": -35,
            "max_temperature": 90,
            "estimated_vid": 1166,
            "target_vid": 1150,
            "vid_source": "saved-ui-target",
        }
    })

    assert page.vid_control.value() == 1150
    assert page._selected_profile_name == "Punto medio"
    assert any(button.isChecked() for button in page.preset_buttons)


def test_cpu_page_uses_prepared_one_shot_state_instead_of_raw_inactive(qtbot):
    page = CpuSmuPage(object())
    qtbot.addWidget(page)

    page._apply_refresh_payload({
        "performance": {},
        "tools": {},
        "core_unlock": {},
        "persistent": {
            "enabled": "enabled",
            "active_state": "inactive",
            "ui_state": "Applied / enabled",
            "ui_detail": "One-shot finished successfully; it will repeat at boot",
            "config_exists": True,
            "config_valid": True,
            "config": {"exists": True, "valid": False, "error": "test"},
        },
    })

    assert page.state_stat.value.text() == "Applied / enabled"
    assert "One-shot finished successfully" in page.state_stat.detail.text()
    assert page.current_state["raw_active_state"] == "inactive"


def test_cpu_oc_config_parser_distinguishes_permission_error_from_invalid_content(tmp_path, monkeypatch):
    config = tmp_path / "bc250-smu-oc.conf"
    config.write_text(_config_text(frequency=3850, scale=-30), encoding="utf-8")

    original_open = cpu_oc_config.os.open

    def protected_open(path, *args, **kwargs):
        if Path(path) == config:
            raise PermissionError(13, "Permission denied", str(path))
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(cpu_oc_config.os, "open", protected_open)
    state = CPURepository._read_cpu_oc_config(config)

    assert state["exists"] is True
    assert state["valid"] is False
    assert state["readable"] is False
    assert state["error_kind"] == "permission"
    assert "protected" in state["error"].lower()
