"""GitHub issue #15, option A: a root service follows the fan from boot.

The curve used to be followed only by the per-user daemon, whose writes go
through pkexec; after every reboot the NCT chip is back in firmware mode, so
the first write of the session -- and its password prompt -- was nearly
certain. These tests pin the replacement: the policy the desktop hands over,
the root loop that follows it, and the desktop side standing aside.
"""

from __future__ import annotations

import json
import random
import runpy
from contextlib import contextmanager
from pathlib import Path

import pytest

from bc250cc.domain.fan.persistence import FanControlMemory, plan_persistent_fan
from bc250cc.infrastructure import system_fan_control
from bc250cc.infrastructure.daemon import BC250ControlCenterDaemon
from bc250cc.infrastructure.system_fan_control import (
    build_system_fan_policy,
    policy_digest,
    read_system_fan_control,
    system_fan_control_owns_fan,
)

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "privileged" / "helpers" / "bc250-fan-pwm-helper"
OPENRC_HELPER = ROOT / "privileged" / "helpers" / "bc250-openrc-service-helper"

CURVE_CONFIG = {
    "fan_curve": {
        "enabled": True,
        "pwm": 2,
        "points": [
            {"temperature": 45, "speed": 70},
            {"temperature": 60, "speed": 90},
            {"temperature": 68, "speed": 100},
        ],
    },
    "fan_preset": {"enabled": False},
    "fan_daemon_hysteresis_c": 1.0,
    "fan_daemon_duty_deadband_percent": 2,
    "fan_daemon_max_down_step_percent": 10,
}


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{value}\n", encoding="ascii")


@pytest.fixture
def board(tmp_path, monkeypatch):
    """The helper module with a BC-250-shaped sysfs and every root path in tmp."""
    module = runpy.run_path(str(HELPER))
    g = module["apply_pwm"].__globals__
    hwmon = tmp_path / "hwmon"
    nct = hwmon / "hwmon3"
    _write(nct / "name", "nct6686")
    for index, (label, value) in enumerate(
        (("CPU", 50000), ("System", 45000), ("VRM MOS", 44500), ("PCH", 0)), start=1
    ):
        (nct / f"temp{index}_label").write_text(label + "\n", encoding="utf-8")
        _write(nct / f"temp{index}_input", value)
    _write(nct / "pwm2", 127)
    _write(nct / "pwm2_enable", 2)
    gpu = hwmon / "hwmon1"
    _write(gpu / "name", "amdgpu")
    (gpu / "temp1_label").write_text("edge\n", encoding="utf-8")
    _write(gpu / "temp1_input", 48000)
    k10 = hwmon / "hwmon2"
    _write(k10 / "name", "k10temp")
    (k10 / "temp1_label").write_text("Tctl\n", encoding="utf-8")
    _write(k10 / "temp1_input", 52000)

    state = tmp_path / "state"
    run = tmp_path / "run"
    monkeypatch.setitem(g, "HWMON_BASE", hwmon)
    monkeypatch.setitem(g, "find_sensor", lambda: nct)
    monkeypatch.setitem(g, "STATE_DIR", state)
    monkeypatch.setitem(g, "STATE_FILE", state / "fan-last-applied.json")
    monkeypatch.setitem(g, "POLICY_FILE", state / "fan-policy.json")
    monkeypatch.setitem(g, "STATUS_FILE", run / "fan-control.json")
    monkeypatch.setitem(g, "OVERRIDE_FILE", run / "fan-override.json")
    monkeypatch.setattr(g["time"], "sleep", lambda _seconds: None)

    @contextmanager
    def no_lock():
        yield

    monkeypatch.setitem(g, "fan_operation_lock", no_lock)
    return module, g, nct, k10


def _policy(config=CURVE_CONFIG):
    return build_system_fan_policy(config)


# -- the policy handed across the privilege boundary -------------------------


def test_the_desktop_policy_is_exactly_what_the_root_helper_accepts(board):
    module, _g, _nct, _k10 = board
    for config in (
        CURVE_CONFIG,
        {"fan_curve": {"enabled": False}, "fan_preset": {
            "enabled": True, "preset": "cooling", "percent": 70, "pwm": 2,
        }},
    ):
        policy = _policy(config)
        validated = module["validate_policy"](json.loads(json.dumps(policy)))
        assert validated == policy
        # Both sides must agree on the digest, or the Fans page would call a
        # perfectly synced service "out of date".
        assert module["policy_digest"](validated) == policy_digest(policy)


def test_nothing_to_follow_means_no_policy():
    assert build_system_fan_policy({"fan_curve": {"enabled": False}}) is None
    assert build_system_fan_policy({}) is None


@pytest.mark.parametrize("mutation, message", [
    (lambda p: p.update(extra=1), "Unknown fan policy keys"),
    (lambda p: p.update(schema=2), "schema"),
    (lambda p: p.update(pwm=True), "pwm"),
    (lambda p: p.update(pwm=13), "pwm"),
    (lambda p: p.update(points=[[45, 70], [45, 90], [68, 100]]), "strictly increasing"),
    (lambda p: p.update(points=[[45, 70], [60, 101], [68, 100]]), "s must be"),
    (lambda p: p.update(points=[[45, 70]]), "between 3 and 8"),
    (lambda p: p.update(failsafe_percent=20), "failsafe_percent"),
    (lambda p: p.update(hysteresis_c=float("nan")), "hysteresis_c"),
    (lambda p: p.update(critical_c={"gpu": 200}), "gpu must be"),
    (lambda p: p.update(offsets_c={"nvme": 1}), "offsets_c accepts only"),
    (lambda p: p.update(mode="turbo"), "mode"),
])
def test_the_root_helper_refuses_rather_than_repairs(board, mutation, message):
    module, _g, _nct, _k10 = board
    policy = json.loads(json.dumps(_policy()))
    mutation(policy)
    with pytest.raises(ValueError, match=message):
        module["validate_policy"](policy)


def test_session_policy_command_saves_the_file_and_ends_a_takeover(board):
    module, g, _nct, _k10 = board
    g["OVERRIDE_FILE"].parent.mkdir(parents=True, exist_ok=True)
    g["OVERRIDE_FILE"].write_text('{"channels": [2]}', encoding="utf-8")
    payload = json.dumps(_policy(), separators=(",", ":"))

    reply = module["session_policy_command"](f"POLICY {payload}")

    assert reply == f"OK POLICY {policy_digest(_policy())}"
    assert json.loads(g["POLICY_FILE"].read_text()) == _policy()
    assert not g["OVERRIDE_FILE"].exists()
    assert module["session_policy_command"]("POLICY {not json").startswith("ERR ")
    assert module["session_policy_command"]("POLICY " + "x" * 5000) == "ERR The fan policy is too large."
    assert module["session_policy_command"]("POLICY-CLEAR") == "OK POLICY CLEARED"
    assert not g["POLICY_FILE"].exists()


# -- the root loop -----------------------------------------------------------


def test_the_hottest_labelled_input_wins_and_disconnected_ones_are_ignored(board):
    module, g, _nct, _k10 = board
    readings = module["read_temperatures"](g["HWMON_BASE"])
    # PCH reads 0 on a BC-250: disconnected, never a real 0 °C.
    assert readings == {"gpu": 48.0, "cpu": 52.0, "vrm": 44.5, "board": 45.0}


def test_the_loop_follows_the_curve_from_firmware_mode(board):
    module, g, nct, k10 = board
    module["save_policy"](_policy())
    clock = iter(range(0, 10_000, 10)).__next__
    controller = module["FanController"](clock=clock)

    controller.step()
    assert controller.state == "active"
    assert (nct / "pwm2_enable").read_text().strip() == "1"
    assert (nct / "pwm2").read_text().strip() == str(round(70 * 255 / 100))

    _write(k10 / "temp1_input", 63000)
    controller.step()
    assert (nct / "pwm2").read_text().strip() == str(round(90 * 255 / 100))
    status = controller.status()
    assert status["state"] == "active" and status["sensor"] == "cpu"
    assert status["policy_digest"] == policy_digest(_policy())


def test_a_takeover_pauses_the_loop_until_a_critical_reading(board):
    module, g, nct, k10 = board
    module["save_policy"](_policy())
    clock = iter(range(0, 10_000, 10)).__next__
    controller = module["FanController"](clock=clock)
    controller.step()
    _write(nct / "pwm2", 40)
    g["OVERRIDE_FILE"].parent.mkdir(parents=True, exist_ok=True)
    g["OVERRIDE_FILE"].write_text('{"channels": [2], "source": "decky"}', encoding="utf-8")

    for _ in range(5):
        controller.step()
    assert controller.state == "override"
    assert (nct / "pwm2").read_text().strip() == "40"

    _write(k10 / "temp1_input", 97000)
    controller.step()
    assert (nct / "pwm2").read_text().strip() == "255"
    assert controller.snapshot["source"] == "critical"
    assert not g["OVERRIDE_FILE"].exists()


def test_missing_sensors_fall_back_to_the_failsafe_after_the_timeout(board):
    module, g, nct, _k10 = board
    module["save_policy"](_policy())
    for hwmon in g["HWMON_BASE"].iterdir():
        for path in hwmon.glob("temp*_input"):
            _write(path, 0)
    moments = iter([0.0, 5.0, 20.0])
    controller = module["FanController"](clock=lambda: next(moments))

    controller.step()
    assert controller.state == "waiting-sensor"
    controller.step()
    assert controller.state == "waiting-sensor"
    controller.step()
    assert (nct / "pwm2").read_text().strip() == "255"
    assert controller.snapshot["source"] == "failsafe"


def test_drift_is_repaired_on_the_verify_interval(board):
    module, _g, nct, _k10 = board
    module["save_policy"](_policy())
    moments = iter([0.0, 10.0, 40.0])
    controller = module["FanController"](clock=lambda: next(moments))
    controller.step()
    _write(nct / "pwm2_enable", 2)  # a driver reload put firmware back in charge
    controller.step()
    assert (nct / "pwm2_enable").read_text().strip() == "2"  # not due yet
    controller.step()
    assert (nct / "pwm2_enable").read_text().strip() == "1"


def test_removing_the_policy_hands_the_fan_back_to_firmware(board):
    module, g, nct, _k10 = board
    module["save_policy"](_policy())
    clock = iter(range(0, 10_000, 10)).__next__
    controller = module["FanController"](clock=clock)
    controller.step()
    g["POLICY_FILE"].unlink()

    controller.step()

    assert controller.state == "idle"
    assert (nct / "pwm2_enable").read_text().strip() == "2"


def test_an_invalid_policy_file_is_reported_and_never_followed(board):
    module, g, nct, _k10 = board
    g["POLICY_FILE"].parent.mkdir(parents=True, exist_ok=True)
    g["POLICY_FILE"].write_text('{"schema": 1, "mode": "curve", "pwm": 2}', encoding="utf-8")
    controller = module["FanController"](clock=lambda: 0.0)

    controller.step()

    assert controller.state == "idle"
    assert "invalid" in controller.error
    assert (nct / "pwm2_enable").read_text().strip() == "2"


def test_the_root_math_matches_the_desktop_daemon(board):
    """Same curve, same smoothing: the service may not pick another duty."""
    module, _g, _nct, _k10 = board
    policy = _policy()
    rng = random.Random(15)
    controller = module["FanController"](clock=lambda: 0.0)
    controller.policy = policy
    memory = FanControlMemory()
    temperature = 50.0
    for step in range(400):
        now = 100.0 + step * 10.0
        temperature = max(30.0, min(90.0, temperature + rng.uniform(-4.0, 4.0)))
        metric = {"cpu_temp": temperature}
        decision = plan_persistent_fan(metric, CURVE_CONFIG, memory, now=now)
        planned = controller.plan({"cpu": temperature}, now)
        assert planned is not None
        percent = planned[0]
        if decision.action == "apply":
            assert decision.target.percent == percent, (step, temperature)
            target = decision.target
            memory = FanControlMemory(
                last_apply=now, last_percent=target.percent, last_target=target.identity,
                last_verify=now, last_temperature=target.temperature,
            )
        else:
            assert memory.last_percent == percent, (step, temperature)
        raw = round(percent * 255 / 100)
        if raw != controller.last_raw:
            controller.last_raw = raw
            controller.last_percent = percent
            controller.last_source = "curve"
            controller.last_temperature = temperature


def test_restore_boot_stands_aside_for_the_control_service(board, monkeypatch):
    module, g, nct, _k10 = board
    module["save_policy"](_policy())
    g["_remember_applied"](2, 60)
    monkeypatch.setitem(g, "control_service_enabled", lambda: True)
    monkeypatch.setitem(g, "bc250_identity_present", lambda: True)
    monkeypatch.setattr(g["os"], "geteuid", lambda: 0)

    assert module["restore_boot_state"]() == 0
    assert (nct / "pwm2").read_text().strip() == "127"  # untouched


def test_the_unit_is_hardened_and_never_replaces_a_foreign_file(board, tmp_path, monkeypatch):
    module, g, _nct, _k10 = board
    text = module["control_unit_text"](Path("/usr/libexec/bc250-control-center/bc250-fan-pwm-helper"))
    assert "ExecStart=/usr/libexec/bc250-control-center/bc250-fan-pwm-helper --control-loop" in text
    for directive in ("NoNewPrivileges=yes", "ProtectHome=yes", "ProtectSystem=full",
                      "RestartPreventExitStatus=19 77", "WantedBy=multi-user.target"):
        assert directive in text
    assert text.startswith(g["CONTROL_MARKER"])

    unit = tmp_path / "etc" / "bc250-fan-control.service"
    unit.parent.mkdir()
    unit.write_text("[Service]\nExecStart=/bin/true\n", encoding="utf-8")
    calls = []
    monkeypatch.setitem(g, "CONTROL_UNIT_PATH", unit)
    monkeypatch.setitem(g, "_init_system", lambda: "systemd")
    monkeypatch.setitem(g, "_trusted_self", lambda: Path("/usr/libexec/x"))
    monkeypatch.setitem(g, "_run", lambda argv: calls.append(argv))
    module["save_policy"](_policy())

    assert module["enable_control_service"]().startswith("ERR Refusing to replace")
    assert module["disable_control_service"]().startswith("ERR Refusing to remove")
    assert calls == []
    assert unit.read_text() == "[Service]\nExecStart=/bin/true\n"


def test_enabling_without_a_policy_is_refused(board):
    module, _g, _nct, _k10 = board
    assert module["enable_control_service"]() == (
        "ERR Save a fan curve or preset before enabling system fan control."
    )


def test_openrc_knows_the_control_service():
    helper = OPENRC_HELPER.read_text(encoding="utf-8")
    assert "'bc250-fan-control'" in helper
    assert 'command_args="--control-loop"' in helper
    assert 'supervisor="supervise-daemon"' in helper


# -- the desktop side stands aside --------------------------------------------


def _paths(tmp_path, monkeypatch):
    monkeypatch.setattr(system_fan_control, "POLICY_FILE", tmp_path / "fan-policy.json")
    monkeypatch.setattr(system_fan_control, "STATUS_FILE", tmp_path / "fan-control.json")
    monkeypatch.setattr(system_fan_control, "OVERRIDE_FILE", tmp_path / "fan-override.json")
    monkeypatch.setattr(system_fan_control, "UNIT_WANTS", tmp_path / "wants.service")
    monkeypatch.setattr(system_fan_control, "OPENRC_LINK", tmp_path / "runlevel")


def test_a_stale_heartbeat_is_reported_as_stopped(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    (tmp_path / "wants.service").symlink_to("/dev/null")
    (tmp_path / "fan-policy.json").write_text(json.dumps(_policy()))
    (tmp_path / "fan-control.json").write_text(json.dumps({"heartbeat": 100.0, "state": "active"}))

    fresh = read_system_fan_control(now=105.0)
    stale = read_system_fan_control(now=200.0)

    assert fresh["running"] and fresh["state"] == "active"
    assert not stale["running"] and stale["state"] == "stopped"
    assert fresh["policy_digest"] == policy_digest(_policy())
    # Enabled with a policy owns the fan even before the first heartbeat:
    # early boot is exactly when a desktop write would prompt.
    assert system_fan_control_owns_fan(stale)


def test_disabled_service_owns_nothing(tmp_path, monkeypatch):
    _paths(tmp_path, monkeypatch)
    (tmp_path / "fan-policy.json").write_text(json.dumps(_policy()))
    snapshot = read_system_fan_control(now=0.0)
    assert snapshot["state"] == "off"
    assert not system_fan_control_owns_fan(snapshot)


def test_the_desktop_daemon_never_writes_while_the_service_owns_the_fan(monkeypatch):
    daemon = object.__new__(BC250ControlCenterDaemon)
    daemon.ultimo_fan_curve_apply = 0
    daemon.ultimo_fan_curve_percent = None
    daemon.ultimo_fan_curve_error = 0
    daemon._health_enabled = False
    applied = []
    daemon.servicio = type("Service", (), {
        "aplicar_pwm_fan": lambda self, pwm, value: applied.append((pwm, value)),
    })()
    daemon._system_fan_control_snapshot = lambda: {"enabled": True, "policy": {"mode": "curve"}}
    monkeypatch.setattr("bc250cc.infrastructure.daemon.time.monotonic", lambda: 10.0)

    daemon.aplicar_ventilador_persistente_si_corresponde({"gpu_temp": 70}, CURVE_CONFIG)

    assert applied == []
