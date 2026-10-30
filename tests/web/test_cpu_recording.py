"""Temporary web OC records the exact completed native result, never a request."""
from types import SimpleNamespace

import pytest

from bc250cc.infrastructure.cpu_repository import CPURepository
from frontends.tui.runtime import Context
from frontends.web.actions import cpu_apply
from frontends.web.data import _cpu


class Settings:
    def __init__(self):
        self.data = {}

    def leer_config(self):
        return dict(self.data)

    read_local_config = leer_config

    def guardar_config(self, values):
        self.data.update(values)

    save_local_config = guardar_config


@pytest.fixture
def cpu(tmp_path):
    settings = Settings()
    repo = CPURepository()
    repo.configuracion = settings
    repo.estado_herramientas_bc250 = lambda: {"smu_oc_exists": True, "smu_oc_path": str(tmp_path)}
    calls = []

    def command(*args, **kwargs):
        calls.append((args, kwargs))
        return ["native-helper-placeholder"]

    service = SimpleNamespace(
        comando_cpu_oc_manual_verificado_embebido=command,
        comando_cpu_oc_temporal_embebido=command,
        registrar_resultado_deteccion_cpu=repo.registrar_resultado_deteccion_cpu,
    )
    return Context(service=service, settings=settings), repo, tmp_path / "overclock.conf", calls


@pytest.mark.parametrize("manual,actual", [(True, 3850), (True, 3750), (False, 3650)])
def test_completed_oc_records_measured_result_and_refreshes_web(cpu, manual, actual):
    ctx, repo, config, calls = cpu
    params = {"frequency": 3850, "temperature": 90, "manual": manual,
              "scale": -34, "vid": 1150}

    def shell(argv):
        assert argv == ["native-helper-placeholder"]
        assert not ctx.settings.data
        config.write_text(f"[overclock]\nfrequency={actual}\nscale=-34\nmax_temperature=90\n")

    level, work = cpu_apply(ctx, params, shell)
    assert level == 1 and not calls  # Review/validation does not apply hardware.
    message = work()
    snapshot = ctx.settings.data["cpu_oc_detection_run"]
    assert snapshot["frequency"] == actual
    assert snapshot["requested_frequency"] == 3850
    assert snapshot["scale"] == -34
    assert snapshot["boot_id"] and snapshot["config_sha256"]
    assert ctx.settings.data["cpu_oc_last_applied_frequency"] == actual
    assert str(actual) in message and "-34" in message
    assert len(calls) == 1
    assert calls[0][1] == ({"confirm_manual": True} if manual else {})

    # The parent was created before the worker wrote settings, and remains
    # alive across page refreshes. It must still see the new durable evidence.
    assert ctx.config == {}
    raw = {"detection": repo.estado_resultado_deteccion_cpu()}
    tuning = _cpu(raw, ctx)["tuning"]
    assert str(actual) in tuning["applied_value"]
    assert "-34" in tuning["applied_value"] and tuning["live_value"] == "-34"
    assert tuning["detection_value"] == "-34"

    # After reboot, the saved detection is history, not proof of active scale.
    repo._current_boot_id = lambda: "next-boot"
    tuning = _cpu({"detection": repo.estado_resultado_deteccion_cpu()}, ctx)["tuning"]
    assert "-34" not in tuning["applied_value"]


@pytest.mark.parametrize("failure", [RuntimeError("Authorization rejected"), KeyboardInterrupt()])
def test_failed_or_cancelled_oc_does_not_register_existing_file(cpu, failure):
    ctx, repo, config, calls = cpu
    config.write_text("[overclock]\nfrequency=3550\nscale=-20\nmax_temperature=90\n")
    repo.registrar_resultado_deteccion_cpu()
    previous = dict(ctx.settings.data)

    def shell(argv):
        raise failure

    _, work = cpu_apply(ctx, {"frequency": 3850, "temperature": 90, "manual": True, "scale": -34}, shell)
    with pytest.raises(type(failure)):
        work()
    assert ctx.settings.data == previous
    assert len(calls) == 1


def test_evidence_write_failure_warns_without_repeating_successful_hardware(cpu):
    ctx, repo, config, calls = cpu
    executed = []
    _, work = cpu_apply(ctx, {"frequency": 3850, "temperature": 90, "vid": 1150, "manual": False}, executed.append)
    message = work()  # Missing detector file: registration fails after command success.
    assert "Warning" in message
    assert len(executed) == len(calls) == 1
    assert not ctx.settings.data


def test_missing_dependencies_do_not_register_an_old_result(cpu):
    ctx, repo, config, calls = cpu

    def missing(*args):
        raise RuntimeError("stress is missing")

    ctx.service.comando_cpu_oc_temporal_embebido = missing
    _, work = cpu_apply(ctx, {"frequency": 3850, "temperature": 90, "vid": 1150, "manual": False}, None)
    with pytest.raises(RuntimeError, match="stress is missing"):
        work()
    assert not ctx.settings.data and not calls
