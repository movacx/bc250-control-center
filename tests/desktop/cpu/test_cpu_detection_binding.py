from pathlib import Path

import pytest

from bc250cc.infrastructure.cpu_repository import CPURepository


def _config_text(frequency=3850, scale=-37, temperature=90):
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


def _repository(tmp_path):
    repo = CPURepository()
    repo.configuracion = MemoryConfig()
    repo.estado_herramientas_bc250 = lambda: {
        "smu_oc_exists": True,
        "smu_oc_path": str(tmp_path),
    }
    return repo


def test_completed_detection_run_binds_exact_latest_scale(tmp_path):
    config = tmp_path / "overclock.conf"
    repo = _repository(tmp_path)

    config.write_text(_config_text(frequency=3650, scale=-20), encoding="utf-8")
    first = repo.registrar_resultado_deteccion_cpu({
        "frequency": 4000, "vid": 1275, "temperature": 90,
    })
    assert first["scale"] == -20

    # A later clean run must replace the throttled run as the persistence source.
    config.write_text(_config_text(frequency=3850, scale=-37), encoding="utf-8")
    latest = repo.registrar_resultado_deteccion_cpu({
        "frequency": 4000, "vid": 1275, "temperature": 90,
    })
    state = repo.estado_resultado_deteccion_cpu()

    assert latest["scale"] == -37
    assert state["matches_current_config"] is True
    analysis = repo.evaluar_override_escala_cpu(-33)
    assert analysis["reference_scale"] == -37
    assert analysis["allowed_min"] == -50
    assert analysis["allowed_max"] == 0
    assert analysis["reference_source"] == "recorded-detection-run"


def test_stale_detection_snapshot_is_rejected_instead_of_using_old_scale(tmp_path):
    config = tmp_path / "overclock.conf"
    repo = _repository(tmp_path)

    config.write_text(_config_text(frequency=3850, scale=-37), encoding="utf-8")
    repo.registrar_resultado_deteccion_cpu()

    # Simulate another detector/manual process changing the file without the UI
    # recording that completed run.
    config.write_text(_config_text(frequency=3650, scale=-20), encoding="utf-8")

    with pytest.raises(RuntimeError, match="changed after the last completed"):
        repo.evaluar_override_escala_cpu(-20)


def test_external_upstream_detection_can_be_persisted_but_manual_scale_requires_app_binding(tmp_path):
    config = tmp_path / "overclock.conf"
    repo = _repository(tmp_path)
    config.write_text(_config_text(frequency=3800, scale=-32), encoding="utf-8")

    with pytest.raises(RuntimeError, match="requires a bc250-detect run recorded by Control Center"):
        repo.evaluar_override_escala_cpu(-30)


def test_embedded_detection_explicitly_writes_to_repository_config(tmp_path):
    repo = CPURepository()
    repo.estado_herramientas_bc250 = lambda: {
        "stress": True,
        "bc250_detect": "/usr/bin/bc250-detect",
        "smu_oc_exists": True,
        "smu_oc_path": str(tmp_path),
    }
    repo._usar_steamos_game_helper = lambda: False

    def command_path(name):
        return {
            "pkexec": "/usr/bin/pkexec",
            "bash": "/usr/bin/bash",
            "python3": "/usr/bin/python3",
        }.get(name, "")

    repo._command_path = command_path
    repo._cpu_smu_helper_path = lambda: "/usr/libexec/bc250-control-center/bc250-cpu-smu-helper"

    argv = repo.comando_cpu_oc_temporal_embebido(3850, 1275, 90)

    expected_config = str(tmp_path / "overclock.conf")
    assert argv == [
        "pkexec",
        "--disable-internal-agent",
        "/usr/libexec/bc250-control-center/bc250-cpu-smu-helper",
        "detect", "3850", "1275", "90", expected_config,
    ]


def test_terminal_detection_uses_the_same_protected_config_boundary(tmp_path):
    repo = CPURepository()
    repo.estado_herramientas_bc250 = lambda: {
        "stress": True,
        "smu_oc_exists": True,
        "smu_oc_path": str(tmp_path),
    }
    repo.comando_cpu_oc_temporal_embebido = lambda *_args: [
        "pkexec", "/usr/libexec/bc250-control-center/bc250-cpu-smu-helper",
        "detect", "3850", "1275", "90", str(tmp_path / "overclock.conf"),
    ]
    launched = []
    repo._abrir_terminal = lambda command, title: launched.append((command, title)) or True

    assert repo.ejecutar_cpu_oc_temporal(3850, 1275, 90) is True
    command, _title = launched[0]
    assert "bc250-cpu-smu-helper" in command
    assert str(tmp_path / "overclock.conf") in command
    assert "bc250_detect.py" not in command


def test_embedded_detection_refuses_global_detector_without_local_repository():
    repo = CPURepository()
    repo.estado_herramientas_bc250 = lambda: {
        "stress": True,
        "bc250_detect": "/usr/bin/bc250-detect",
        "smu_oc_exists": False,
        "smu_oc_path": "",
    }
    repo._usar_steamos_game_helper = lambda: False
    repo._command_path = lambda name: "/usr/bin/pkexec" if name == "pkexec" else "/usr/bin/bash"

    with pytest.raises(RuntimeError, match="share the same ResourceTools/overclock.conf"):
        repo.comando_cpu_oc_temporal_embebido(3850, 1275, 90)


def test_temporary_cpu_oc_limits_match_upstream_bc250_smu_oc(tmp_path):
    repo = CPURepository()
    repo._usar_steamos_game_helper = lambda: False
    repo._command_path = lambda name: "/usr/bin/pkexec" if name == "pkexec" else "/usr/bin/bash"
    repo.estado_herramientas_bc250 = lambda: {
        "stress": True,
        "bc250_detect": "/usr/bin/bc250-detect",
        "smu_oc_exists": True,
        "smu_oc_path": str(tmp_path),
    }

    with pytest.raises(ValueError, match="3100-4200"):
        repo.comando_cpu_oc_temporal_embebido(3099, 1200, 90)
    with pytest.raises(ValueError, match="950-1325"):
        repo.comando_cpu_oc_temporal_embebido(3100, 1326, 90)


def test_steamos_helper_binds_detection_to_same_repository_config():
    game_helper = (
        Path(__file__).resolve().parents[3]
        / "privileged" / "helpers" / "bc250-steamos-game-helper"
    ).read_text(encoding="utf-8")
    cpu_helper = (
        Path(__file__).resolve().parents[3]
        / "privileged" / "helpers" / "bc250-cpu-smu-helper"
    ).read_text(encoding="utf-8")

    assert "Frequency must be between 3100 and 4200 MHz." in game_helper
    assert "VID must be between 950 and 1325 mV." in game_helper
    assert "CPU_SMU_HELPER" in game_helper
    assert "def user_detection_config_fd" in cpu_helper
    assert "O_NOFOLLOW" in cpu_helper
    assert "'--config', f'/proc/self/fd/{fd}'" in cpu_helper
    assert "pass_fds=(fd,)" in cpu_helper
    assert "Frequency must be between 3000 and 4200 MHz." not in game_helper
    assert "VID must be between 900 and 1375 mV." not in game_helper


def test_legacy_in_place_override_requires_one_fresh_detection(tmp_path):
    config = tmp_path / "overclock.conf"
    repo = _repository(tmp_path)
    config.write_text(_config_text(frequency=3850, scale=-37), encoding="utf-8")
    original = repo.registrar_resultado_deteccion_cpu()

    # Simulate the pre-professional workflow, which edited detector evidence
    # in place and advanced the expected digest/current_scale.
    # Recreate the state written by the pre-professional implementation:
    # canonical detector evidence was edited in place and the expected digest
    # advanced while the original detector SHA/scale remained in the snapshot.
    config.write_text(_config_text(frequency=3850, scale=-33), encoding="utf-8")
    legacy = dict(repo.configuracion.data["cpu_oc_detection_run"])
    legacy["current_scale"] = -33
    legacy["scale_override"] = -33
    legacy["config_sha256"] = repo._cpu_oc_config_digest(config)
    repo.configuracion.guardar_config({"cpu_oc_detection_run": legacy})

    state = repo.estado_resultado_deteccion_cpu()
    assert state["matches_current_config"] is True
    assert state["detector_evidence_pristine"] is False
    assert state["legacy_override_in_detector_config"] is True
    assert state["snapshot"]["scale"] == -37
    assert state["snapshot"]["current_scale"] == -33
    assert state["snapshot"]["detected_config_sha256"] == original["detected_config_sha256"]
    assert state["snapshot"]["config_sha256"] != original["config_sha256"]

    with pytest.raises(RuntimeError, match="older Control Center build"):
        repo.evaluar_override_escala_cpu(-34)
