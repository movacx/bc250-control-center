from pathlib import Path
from types import SimpleNamespace

import pytest

import bc250cc.infrastructure.cpu_repository as cpu_repository_module
from bc250cc.domain.cpu.active_tuning import resolve_active_cpu_tuning
from bc250cc.infrastructure.cpu_repository import CPURepository


def _config_text(frequency=3850, scale=-36, temperature=90):
    return (
        "[overclock]\n"
        f"frequency = {frequency}\n"
        f"scale = {scale}\n"
        f"max_temperature = {temperature}\n"
    )


class MemoryConfig:
    def __init__(self):
        self.data = {}

    def leer_config(self):
        return dict(self.data)

    def guardar_config(self, update):
        self.data.update(update)
        return True


def _repo(tmp_path):
    repo = CPURepository()
    repo.configuracion = MemoryConfig()
    repo.estado_herramientas_bc250 = lambda: {
        "smu_oc_exists": True,
        "smu_oc_path": str(tmp_path),
    }
    repo._usar_steamos_game_helper = lambda: False
    repo._command_path = lambda name: {
        "pkexec": "/usr/bin/pkexec",
        "bash": "/usr/bin/bash",
        "python3": "/usr/bin/python3",
    }.get(name, "")
    repo._cpu_smu_helper_path = lambda: "/usr/libexec/bc250-control-center/bc250-cpu-smu-helper"
    return repo


def _record_detection(repo, tmp_path, *, scale=-36):
    (tmp_path / "overclock.conf").write_text(
        _config_text(scale=scale), encoding="utf-8"
    )
    (tmp_path / "bc250_apply.py").write_text("# upstream apply stub\n", encoding="utf-8")
    return repo.registrar_resultado_deteccion_cpu({
        "frequency": 3850,
        "vid": 1150,
        "temperature": 90,
    })


def test_scale_minus_30_is_not_silently_clamped_after_minus_36_detection(tmp_path):
    repo = _repo(tmp_path)
    _record_detection(repo, tmp_path, scale=-36)

    analysis = repo.evaluar_override_escala_cpu(-30)

    assert analysis["requested_scale"] == -30
    assert analysis["reference_scale"] == -36
    assert analysis["delta_steps"] == 6
    assert analysis["allowed"] is True
    assert analysis["requested_estimated_vid"] == 1199
    assert analysis["reference_estimated_vid"] == 1159
    assert analysis["estimated_vid_delta"] == 40


def test_live_scale_candidate_does_not_mutate_detector_evidence(tmp_path):
    repo = _repo(tmp_path)
    detection = _record_detection(repo, tmp_path, scale=-36)
    detector_path = tmp_path / "overclock.conf"
    original_bytes = detector_path.read_bytes()
    original_digest = detection["config_sha256"]

    argv = repo.comando_cpu_scale_live_embebido(-30, confirm_scale_jump=True)

    assert argv == [
        "pkexec",
        "--disable-internal-agent",
        "/usr/libexec/bc250-control-center/bc250-cpu-smu-helper",
        "apply-live", "3850", "-30", "90",
    ]
    assert detector_path.read_bytes() == original_bytes
    assert repo._cpu_oc_config_digest(detector_path) == original_digest
    candidate = repo._read_cpu_oc_config(tmp_path / "overclock.live.conf")
    assert candidate["frequency"] == 3850
    assert candidate["scale"] == -30
    assert candidate["max_temperature"] == 90
    assert (tmp_path / "overclock.live.conf").is_file()


def test_live_candidate_can_use_selected_frequency_instead_of_detected_frequency(tmp_path):
    repo = _repo(tmp_path)
    detection = _record_detection(repo, tmp_path, scale=-39)
    detector_path = tmp_path / "overclock.conf"
    original_bytes = detector_path.read_bytes()

    analysis = repo.evaluar_override_escala_cpu(-30, 3700)
    assert analysis["frequency"] == 3700
    assert analysis["detected_frequency"] == 3850

    argv = repo.comando_cpu_scale_live_embebido(
        -30, confirm_scale_jump=True,
        frequency_override=3700, temperature_override=85,
    )
    assert argv == [
        "pkexec",
        "--disable-internal-agent",
        "/usr/libexec/bc250-control-center/bc250-cpu-smu-helper",
        "apply-live", "3700", "-30", "85",
    ]
    assert detector_path.read_bytes() == original_bytes
    assert repo._cpu_oc_config_digest(detector_path) == detection["config_sha256"]

    live = repo.registrar_prueba_escala_cpu(-30, 3700, 85)
    assert live["frequency"] == 3700
    assert live["temperature"] == 85
    assert live["detected_frequency"] == 3850
    assert repo.estado_prueba_escala_cpu(-30, 3700, 85)["valid_for_persistence"] is True
    assert repo.estado_prueba_escala_cpu(-30, 3850, 85)["valid_for_persistence"] is False

    persistent = repo.comando_cpu_oc_persistente_embebido(
        -30, confirm_scale_jump=True,
        frequency_override=3700, temperature_override=85,
    )
    assert persistent == [
        "pkexec",
        "--disable-internal-agent",
        "/usr/libexec/bc250-control-center/bc250-cpu-smu-helper",
        "install-boot", "3700", "-30", "85",
    ]


def test_persistence_rejects_manual_scale_until_same_scale_was_applied_live(tmp_path):
    repo = _repo(tmp_path)
    _record_detection(repo, tmp_path, scale=-36)

    with pytest.raises(RuntimeError, match="Apply the selected manual OC temporarily"):
        repo.comando_cpu_oc_persistente_embebido(-30, confirm_scale_jump=True)

    live = repo.registrar_prueba_escala_cpu(-30)
    assert live["scale"] == -30

    argv = repo.comando_cpu_oc_persistente_embebido(-30, confirm_scale_jump=True)
    candidate = repo._read_cpu_oc_config(tmp_path / "overclock.persist.conf")
    assert candidate["scale"] == -30
    assert argv == [
        "pkexec",
        "--disable-internal-agent",
        "/usr/libexec/bc250-control-center/bc250-cpu-smu-helper",
        "install-boot", "3850", "-30", "90",
    ]
    assert live["test_id"]


def test_game_mode_persistent_cpu_service_avoids_direct_pkexec_cpu_helper(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    repo._usar_steamos_game_helper = lambda: True
    repo._comando_steamos_game_helper = lambda *args: list(args)
    monkeypatch.setattr(
        cpu_repository_module,
        "detect_init_manager",
        lambda: SimpleNamespace(
            persistence_supported=True,
            display_name="systemd",
        ),
    )
    _record_detection(repo, tmp_path, scale=-36)

    assert repo.comando_cpu_oc_persistente_embebido() == [
        "cpu-oc-service", "install", 3850, -36, 90,
    ]
    assert repo.comando_cpu_oc_desactivar_persistente_embebido() == [
        "cpu-oc-service", "remove",
    ]


def test_game_mode_rejects_manual_persistent_override_before_staging_config(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    repo._usar_steamos_game_helper = lambda: True
    monkeypatch.setattr(
        cpu_repository_module,
        "detect_init_manager",
        lambda: SimpleNamespace(
            persistence_supported=True,
            display_name="systemd",
        ),
    )
    _record_detection(repo, tmp_path, scale=-36)

    with pytest.raises(RuntimeError, match="Manual CPU scale persistence from Game Mode"):
        repo.comando_cpu_oc_persistente_embebido(-30)
    assert not (tmp_path / "overclock.persist.conf").exists()


def test_new_detection_invalidates_previous_live_scale_test(tmp_path):
    repo = _repo(tmp_path)
    _record_detection(repo, tmp_path, scale=-36)
    repo.registrar_prueba_escala_cpu(-30)
    assert repo.estado_prueba_escala_cpu(-30)["valid_for_persistence"] is True

    (tmp_path / "overclock.conf").write_text(
        _config_text(scale=-37), encoding="utf-8"
    )
    repo.registrar_resultado_deteccion_cpu({
        "frequency": 3850,
        "vid": 1150,
        "temperature": 90,
    })

    state = repo.estado_prueba_escala_cpu(-30)
    assert state["recorded"] is False
    assert state["valid_for_persistence"] is False


def test_external_change_after_live_test_invalidates_persistence_binding(tmp_path):
    repo = _repo(tmp_path)
    _record_detection(repo, tmp_path, scale=-36)
    repo.registrar_prueba_escala_cpu(-30)

    (tmp_path / "overclock.conf").write_text(
        _config_text(scale=-35), encoding="utf-8"
    )

    state = repo.estado_prueba_escala_cpu(-30)
    assert state["matches_detection"] is False
    assert state["valid_for_persistence"] is False
    with pytest.raises(RuntimeError, match="changed after the last completed"):
        repo.comando_cpu_oc_persistente_embebido(-30, confirm_scale_jump=True)


def test_scale_that_exceeds_upstream_estimated_vid_ceiling_is_blocked():
    # At 4200 MHz, scale 0 predicts a VID above the 1325 mV upstream ceiling.
    analysis = CPURepository._scale_override_analysis(4200, -30, 0)
    assert analysis["allowed"] is False
    assert "1325 mV" in analysis["blocked_reason"]


def test_direct_manual_apply_does_not_require_detector_evidence(tmp_path):
    repo = _repo(tmp_path)

    argv = repo.comando_cpu_oc_manual_embebido(
        3700, -34, 85, confirm_manual=True
    )

    assert argv == [
        "pkexec",
        "--disable-internal-agent",
        "/usr/libexec/bc250-control-center/bc250-cpu-smu-helper",
        "apply-live", "3700", "-34", "85",
    ]
    assert not (tmp_path / "overclock.conf").exists()


def test_direct_manual_apply_requires_confirmation_and_enforces_vid_ceiling(tmp_path):
    repo = _repo(tmp_path)

    with pytest.raises(ValueError, match="explicit confirmation"):
        repo.comando_cpu_oc_manual_embebido(3700, -34, 85)
    with pytest.raises(ValueError, match="1325 mV"):
        repo.comando_cpu_oc_manual_embebido(
            4200, 0, 90, confirm_manual=True
        )


def test_direct_manual_record_without_detection_is_live_but_not_persistent(tmp_path):
    repo = _repo(tmp_path)
    repo._current_boot_id = lambda: "boot-manual"

    record = repo.registrar_aplicacion_manual_cpu(3700, -34, 85)
    state = repo.estado_prueba_escala_cpu(-34, 3700, 85)

    assert record["reference_source"] == "manual-direct"
    assert state["direct_manual"] is True
    assert state["active_in_current_session"] is True
    assert state["valid_for_persistence"] is False

    repo._current_boot_id = lambda: "boot-next"
    assert repo.estado_prueba_escala_cpu(-34, 3700, 85)[
        "active_in_current_session"
    ] is False


def test_direct_manual_record_reuses_pristine_detection_for_persistence(tmp_path):
    repo = _repo(tmp_path)
    repo._current_boot_id = lambda: "boot-manual"
    _record_detection(repo, tmp_path, scale=-36)

    record = repo.registrar_aplicacion_manual_cpu(3700, -34, 85)
    state = repo.estado_prueba_escala_cpu(-34, 3700, 85)

    assert record["reference_source"] == "recorded-detection-run"
    assert record["persistence_eligible"] is True
    assert state["direct_manual"] is False
    assert state["active_in_current_session"] is True
    assert state["valid_for_persistence"] is True
    assert repo.comando_cpu_oc_persistente_embebido(
        -34,
        confirm_scale_jump=True,
        frequency_override=3700,
        temperature_override=85,
    ) == [
        "pkexec",
        "--disable-internal-agent",
        "/usr/libexec/bc250-control-center/bc250-cpu-smu-helper",
        "install-boot", "3700", "-34", "85",
    ]


def test_previous_revision_direct_record_is_promoted_on_explicit_boot_save(tmp_path):
    repo = _repo(tmp_path)
    repo._current_boot_id = lambda: "boot-legacy-direct"
    _record_detection(repo, tmp_path, scale=-36)
    repo.configuracion.guardar_config({
        "cpu_oc_scale_live_test": {
            "test_id": "legacy-direct-test",
            "applied_at_epoch_ns": 123,
            "boot_id": "boot-legacy-direct",
            "detection_run_id": "",
            "detected_config_sha256": "",
            "frequency": 3700,
            "temperature": 85,
            "scale": -34,
            "estimated_vid": repo.evaluar_aplicacion_manual_cpu(3700, -34, 85)["estimated_vid"],
            "reference_source": "manual-direct",
            "persistence_eligible": False,
            "result": "applied-live",
        }
    })

    before = repo.estado_prueba_escala_cpu(-34, 3700, 85)
    promoted = repo.preparar_evidencia_persistencia_escala_cpu(-34, 3700, 85)

    assert before["direct_manual"] is True
    assert before["valid_for_persistence"] is False
    assert promoted["direct_manual"] is False
    assert promoted["valid_for_persistence"] is True
    assert promoted["test"]["reference_source"] == "recorded-detection-run"


def test_rejected_live_registration_does_not_write_candidate_artifact(tmp_path):
    repo = _repo(tmp_path)
    _record_detection(repo, tmp_path, scale=-30)

    with pytest.raises(ValueError, match="1325 mV"):
        repo.registrar_prueba_escala_cpu(0, frequency_override=4200)

    assert not (tmp_path / "overclock.live.conf").exists()


def test_cpu_page_source_uses_full_scale_domain_and_single_apply_action():
    source = (
        Path(__file__).resolve().parents[3]
        / "frontends" / "desktop" / "pages" / "cpu_smu.py"
    ).read_text(encoding="utf-8")

    assert '"Use manual scale"' in source
    assert '"Apply temporary OC + manual scale"' in source
    assert '"Test selected scale"' not in source
    assert "self.scale_control.setRange(-50, 0)" in source
    assert "allowed_min" not in source[source.index("def _on_scale_override_toggled"):source.index("def _profile_name_for_values")]
    persistence_plan = (
        Path(__file__).resolve().parents[3]
        / "frontends" / "desktop" / "core" / "cpu_persistence_plan.py"
    ).read_text(encoding="utf-8")
    assert "Apply this scale temporarily first" in persistence_plan
    assert "plan_cpu_persistence" in source


def test_live_scale_record_is_not_presented_as_current_after_reboot(tmp_path):
    repo = _repo(tmp_path)
    repo._current_boot_id = lambda: "boot-a"
    _record_detection(repo, tmp_path, scale=-35)
    repo.registrar_prueba_escala_cpu(-30)

    current = repo.estado_prueba_escala_cpu(-30)
    assert current["matches_detection"] is True
    assert current["same_boot"] is True
    assert current["active_in_current_session"] is True

    repo._current_boot_id = lambda: "boot-b"
    rebooted = repo.estado_prueba_escala_cpu(-30)
    assert rebooted["matches_detection"] is True
    assert rebooted["same_boot"] is False
    assert rebooted["active_in_current_session"] is False
    # Previous hardware validation remains evidence for persistence, but it is
    # no longer described as a live test in the new desktop session.
    assert rebooted["valid_for_persistence"] is True


def test_detection_snapshot_tracks_boot_identity_without_invalidating_reference(tmp_path):
    repo = _repo(tmp_path)
    repo._current_boot_id = lambda: "boot-a"
    detection = _record_detection(repo, tmp_path, scale=-35)
    assert detection["boot_id"] == "boot-a"
    assert repo.estado_resultado_deteccion_cpu()["same_boot"] is True

    repo._current_boot_id = lambda: "boot-b"
    state = repo.estado_resultado_deteccion_cpu()
    assert state["matches_current_config"] is True
    assert state["same_boot"] is False


def test_active_tuning_after_reboot_prefers_successful_boot_config_over_old_live_test():
    persistent = {
        "applied_this_boot": True,
        "config": {
            "valid": True,
            "frequency": 3850,
            "scale": -30,
            "max_temperature": 90,
            "estimated_vid": 1199,
        },
    }
    detection = {
        "same_boot": False,
        "matches_current_config": True,
        "snapshot": {"frequency": 3850, "scale": -35, "temperature": 90},
    }
    scale_live = {
        "matches_detection": True,
        "same_boot": False,
        "active_in_current_session": False,
        "test": {"frequency": 3850, "scale": -30, "temperature": 90},
    }

    active = resolve_active_cpu_tuning(persistent, detection, scale_live)

    assert active["source"] == "boot"
    assert active["frequency"] == 3850
    assert active["scale"] == -30
    assert active["temperature"] == 90


def test_active_tuning_live_test_in_current_boot_overrides_boot_config():
    persistent = {
        "applied_this_boot": True,
        "config": {"valid": True, "frequency": 3850, "scale": -30, "max_temperature": 90},
    }
    detection = {"same_boot": True, "matches_current_config": True, "snapshot": {"frequency": 3850, "scale": -35, "temperature": 90}}
    scale_live = {
        "active_in_current_session": True,
        "test": {"frequency": 3850, "scale": -32, "temperature": 90, "estimated_vid": 1186},
    }

    active = resolve_active_cpu_tuning(persistent, detection, scale_live)

    assert active["source"] == "live"
    assert active["scale"] == -32
