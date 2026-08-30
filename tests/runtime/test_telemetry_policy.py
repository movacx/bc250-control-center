import subprocess

import pytest

from bc250cc.infrastructure import telemetry_policy
from bc250cc.infrastructure.gpu_repository import GPURepository
from frontends.desktop.core.state import ControllerStateCache, DashboardState


@pytest.mark.parametrize(
    "command",
    (
        ["git", "status"], ["systemctl", "status", "x"],
        ["rc-service", "cyan-skillfish-governor-smu", "restart"],
        ["rc-update", "add", "cyan-skillfish-governor-smu", "default"],
        ["sudo", "sensors"], ["curl", "https://example.invalid"],
    ),
)
def test_passive_telemetry_rejects_remote_privileged_and_service_commands(command):
    with telemetry_policy.passive_probe_budget(1), pytest.raises(PermissionError):
        telemetry_policy.run_passive_probe(command, timeout=1)


def test_passive_probe_requires_explicit_refresh_scope():
    with pytest.raises(RuntimeError, match="outside a refresh budget"):
        telemetry_policy.run_passive_probe(["sensors"], timeout=1)


def test_refresh_budget_prevents_an_accidental_second_subprocess(monkeypatch):
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(telemetry_policy.subprocess, "run", fake_run)
    with telemetry_policy.passive_probe_budget(1):
        telemetry_policy.run_passive_probe(["sensors"], timeout=3)
        with pytest.raises(RuntimeError, match="budget exceeded"):
            telemetry_policy.run_passive_probe(["sensors"], timeout=3)
    assert calls == [["sensors"]]


def test_timeout_is_capped_for_fast_refresh(monkeypatch):
    observed = {}

    def fake_run(command, **kwargs):
        observed.update(kwargs)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(telemetry_policy.subprocess, "run", fake_run)
    with telemetry_policy.passive_probe_budget(1):
        telemetry_policy.run_passive_probe(["sensors"], timeout=500)
    assert observed["timeout"] == 5.0


def test_dashboard_cold_and_warm_refresh_stay_inside_probe_budget(monkeypatch):
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "Pump Fan: 1700 RPM\n", "")

    class Controller:
        def rendimiento(self):
            return {}

        def metricas_tiempo_real(self):
            return {}

        def estado_bc250(self):
            return {}

        def estado_herramientas_bc250(self):
            return {}

        def estado_fans_bc250(self):
            return {}

        def obtener_estado_cu_cache(self):
            return {}

        def obtener_eventos(self, _limit):
            return []

    monkeypatch.setattr(telemetry_policy.subprocess, "run", fake_run)
    controller = Controller()
    cache = ControllerStateCache(controller)
    first = DashboardState.from_controller(controller, cache)
    second = DashboardState.from_controller(controller, cache)
    assert first.pump_fan_rpm == second.pump_fan_rpm == 1700
    assert calls == [["sensors"]]


@pytest.mark.parametrize(
    "command",
    (
        ["systemctl", "restart", "cyan.service"],
        ["systemctl", "show", "../../evil", "--property=ActiveState,SubState"],
        ["busctl", "call", "com.cyanskillfish.Governor"],
        ["git", "status"],
    ),
)
def test_daemon_governor_lane_rejects_mutation_and_unbounded_queries(command):
    with telemetry_policy.daemon_governor_probe_budget(), pytest.raises(
        PermissionError
    ):
        telemetry_policy.run_daemon_governor_probe(command)


def test_daemon_governor_lane_is_scoped_capped_and_limited_to_three(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(telemetry_policy.subprocess, "run", fake_run)
    command = [
        "systemctl", "show", "cyan-skillfish-governor-smu.service",
        "--property=ActiveState,SubState",
    ]
    with pytest.raises(RuntimeError, match="outside a refresh budget"):
        telemetry_policy.run_daemon_governor_probe(command)
    with telemetry_policy.daemon_governor_probe_budget(99):
        for _index in range(3):
            telemetry_policy.run_daemon_governor_probe(command, timeout=99)
        with pytest.raises(RuntimeError, match="budget exceeded"):
            telemetry_policy.run_daemon_governor_probe(command)
    assert len(calls) == 3
    assert all(call[1]["timeout"] == 2.0 for call in calls)


def _daemon_repository():
    class Configuration:
        @staticmethod
        def leer_config():
            return {"gpu_governor": "cyan"}

    repository = GPURepository.__new__(GPURepository)
    repository.configuracion = Configuration()
    repository._command_path = lambda _name: "/usr/bin/tool"
    repository._gpu_device_path = lambda: None
    repository._parse_dpm_actual = lambda _text: None
    return repository


def test_daemon_snapshot_uses_one_service_and_two_dbus_probes(monkeypatch):
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        if command[0] == "systemctl":
            return subprocess.CompletedProcess(
                command, 0, "ActiveState=active\nSubState=running\n", ""
            )
        value = "1000" if command[-1] == "Min" else "1850"
        return subprocess.CompletedProcess(command, 0, f"u {value}\n", "")

    monkeypatch.setattr(telemetry_policy.subprocess, "run", fake_run)
    state = _daemon_repository().estado_bc250_daemon()

    assert state["service_active"] == "active"
    assert state["service_sub"] == "running"
    assert state["current_min"] == 1000
    assert state["current_max"] == 1850
    assert state["dbus_ok"] is True
    assert len(calls) == 3
    assert all(command[0] in {"systemctl", "busctl"} for command in calls)


def test_daemon_snapshot_skips_dbus_when_service_is_inactive(monkeypatch):
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command, 0, "ActiveState=inactive\nSubState=dead\n", ""
        )

    monkeypatch.setattr(telemetry_policy.subprocess, "run", fake_run)
    state = _daemon_repository().estado_bc250_daemon()

    assert state["service_active"] == "inactive"
    assert state["dbus_ok"] is False
    assert calls == [[
        "systemctl", "show", "cyan-skillfish-governor-smu.service",
        "--property=ActiveState,SubState",
    ]]
