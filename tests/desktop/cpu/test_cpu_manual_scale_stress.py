"""A typed CPU scale is stress-tested in steps, like a detected one.

A Bazzite tester asked two things: why manual OC only unlocked after one of
the presets had run, and why a manual scale then applied at once "without
the stress run in steps". bc250-detect only ever searches for a scale; a
scale typed by hand went straight to bc250-apply. The helper now runs the
detector's own steps with the scale held instead of searched, and manual
mode no longer waits for a detection.

The same tester noticed the terminal showed nothing while bc250-detect ran:
Python buffers a pipe, so every "Stress Testing ..." line arrived at the end.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import signal
from pathlib import Path

import pytest

from bc250cc.infrastructure.cpu_command_policy import (
    CPUScaleTarget,
    build_verify_scale_command,
)
from frontends.desktop.pages.cpu_control_view import CpuControlView, CpuTuningState
from frontends.desktop.pages.cpu_smu import CpuSmuPage

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "privileged/helpers/bc250-cpu-smu-helper"


def _helper():
    loader = importlib.machinery.SourceFileLoader("bc250_cpu_smu_helper", str(HELPER))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class FakeSmu:
    """Six active cores; each step reads a voltage, some steps throttle."""

    ACTIVE = (True, True, True, False, True, True, True, False)

    def __init__(self, *, voltages=None, throttle_at=None):
        self.voltages = voltages or {}
        self.throttle_at = throttle_at
        self.clock = 3500
        self.scale = 0
        self.stressing = False
        self.calls: list[tuple] = []

    def q3_0x8b_set_cpu_max_temperature(self, value):
        self.calls.append(("cpu_temp", value))

    def q3_0x8c_set_gpu_max_temperature(self, value):
        self.calls.append(("gpu_temp", value))

    def disable_extra_cpu_gpu_voltage(self, value):
        self.calls.append(("extra_voltage_off", value))

    def q3_0x50_scale_f_vid_curve(self, scale):
        self.scale = scale
        self.calls.append(("scale", scale))

    def q3_0x8f_set_max_cpu_boost_clk(self, clock):
        self.clock = clock
        self.calls.append(("clock", clock))

    def q3_0x43_get_core_freq(self, index):
        if not self.ACTIVE[index]:
            return 400
        if self.throttle_at is not None and self.clock >= self.throttle_at:
            return self.clock - 300
        return self.clock

    def q3_0x36_get_current_cpu_voltage(self):
        return self.voltages.get(self.clock, 1000 + (self.clock - 3500) // 4)


class FakeStress:
    def __init__(self, smu):
        self.smu = smu
        self.running = False

    def start(self):
        self.running = True

    def stop(self):
        self.running = False


def _run(helper, smu, frequency, scale=-30, temperature=90):
    stress = FakeStress(smu)
    written = []
    result = helper.verify_scale_steps(
        smu,
        stress,
        frequency,
        scale,
        temperature,
        write_result=lambda *values: written.append(values),
        sleep=lambda _seconds: None,
    )
    return result, written, stress


def test_every_step_up_to_the_target_is_loaded_and_written(capsys):
    helper = _helper()
    smu = FakeSmu()
    (passed, voltage), written, stress = _run(helper, smu, 3850)

    # The detector's own steps: 3550 is 3500 + (3850 % 100), then +100 each.
    assert [values[0] for values in written] == [3550, 3650, 3750, 3850]
    assert all(values[1:] == (-30, 90) for values in written)
    assert passed == 3850 and voltage == smu.q3_0x36_get_current_cpu_voltage()
    assert smu.scale == -30
    assert not stress.running
    out = capsys.readouterr().out
    assert "Detected Active Cores: 012X456X" in out
    assert "Stress Testing 3550 MHz @" in out
    assert "Stress Testing 3850 MHz @" in out
    # Temperature limits and extra voltage exactly as bc250-detect sets them.
    assert ("cpu_temp", 90) in smu.calls and ("extra_voltage_off", True) in smu.calls


def test_throttling_keeps_the_highest_step_that_held(capsys):
    helper = _helper()
    smu = FakeSmu(throttle_at=3750)
    (passed, _voltage), written, stress = _run(helper, smu, 3950)

    assert passed == 3650
    assert [values[0] for values in written] == [3550, 3650]
    assert not stress.running
    assert "Aborting because throttling was detected" in capsys.readouterr().out


def test_a_voltage_above_the_absolute_limit_stops_the_test(capsys):
    helper = _helper()
    smu = FakeSmu(voltages={3650: helper.VERIFY_VID_LIMIT_MV + 5})
    (passed, _voltage), written, stress = _run(helper, smu, 3850)

    assert passed == 3550
    assert [values[0] for values in written] == [3550]
    assert not stress.running
    assert "above the 1325 mV limit" in capsys.readouterr().out


def test_nothing_is_kept_when_even_the_first_step_fails():
    helper = _helper()
    smu = FakeSmu(throttle_at=3500)
    (passed, voltage), written, _stress = _run(helper, smu, 3800)

    assert (passed, voltage) == (0, 0)
    assert written == []


def test_a_failed_test_puts_the_detector_defaults_back(capsys):
    helper = _helper()
    smu = FakeSmu()
    helper._revert_smu_defaults(smu)

    assert smu.clock == helper.VERIFY_START_MHZ
    assert smu.scale == 0
    assert ("extra_voltage_off", False) in smu.calls
    assert ("cpu_temp", 100) in smu.calls and ("gpu_temp", 100) in smu.calls
    assert "Restored Default Parameters" in capsys.readouterr().out


def test_the_result_file_has_the_detectors_format():
    helper = _helper()
    assert helper._config_text(3850, -38, 90) == (
        "[overclock]\nfrequency = 3850\nscale = -38\nmax_temperature = 90\n\n"
    )


def test_cancelling_from_the_desktop_unwinds_instead_of_dying():
    """SIGTERM must reach the finally blocks that stop stress and revert."""
    helper = _helper()
    with pytest.raises(SystemExit):
        helper._raise_system_exit(signal.SIGTERM, None)


def test_the_detector_prints_each_step_as_it_happens(monkeypatch):
    helper = _helper()
    seen = {}

    def fake_run(command, **kwargs):
        seen.update(kwargs)
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(helper.subprocess, "run", fake_run)
    helper.run_vendor_module("bc250_detect", ["--frequency", "3850"])

    assert seen["env"]["PYTHONUNBUFFERED"] == "1"


def test_the_verify_command_carries_the_exact_values_and_the_detector_file():
    command = build_verify_scale_command(
        ["pkexec"],
        "/usr/libexec/bc250-control-center/bc250-cpu-smu-helper",
        CPUScaleTarget(3850, -38, 90, None),
        "/home/user/.local/share/bc250-control-center/ResourceTools/bc250_smu_oc/overclock.conf",
    )
    assert command[-5:] == [
        "verify-scale",
        "3850",
        "-38",
        "90",
        "/home/user/.local/share/bc250-control-center/ResourceTools/bc250_smu_oc/overclock.conf",
    ]


# ------------------------------------------------------------------ desktop


class _AcceptedDialog:
    def __init__(self, *args, **kwargs):
        self.args = args

    def exec(self):
        from PyQt6.QtWidgets import QDialog

        return QDialog.DialogCode.Accepted


class _Controller:
    def __init__(self):
        self.calls = []

    def evaluar_aplicacion_manual_cpu(self, frequency, scale, temperature):
        return {"estimated_vid": 1150}

    def comando_cpu_oc_manual_verificado_embebido(self, *args):
        self.calls.append(("verify", args))
        return ["pkexec", "helper", "verify-scale"]

    def comando_cpu_oc_manual_embebido(self, *args):  # pragma: no cover
        raise AssertionError("a typed scale must not skip the stress test")

    def registrar_resultado_deteccion_cpu(self, target):
        self.calls.append(("recorded", dict(target)))
        return {"frequency": 3750, "scale": -38, "temperature": 90}


def test_manual_apply_runs_the_stepped_test_and_records_it_like_a_detection(qtbot, monkeypatch):
    monkeypatch.setattr("frontends.desktop.pages.cpu_smu.ConfirmDialog", _AcceptedDialog)
    controller = _Controller()
    page = CpuSmuPage(controller)
    qtbot.addWidget(page)
    started = []
    page._start_process = lambda command, label: started.append((command, label))
    page._build_and_start_process = lambda operation, label, _title: started.append(
        (operation(), label)
    )

    page._request_manual_apply(3850, -38, 90)

    assert ("verify", (3850, -38, 90, True)) in controller.calls
    assert page._pending_cpu_target == {"frequency": 3850, "temperature": 90, "manual_scale": -38}

    page.scale_override_check.setChecked(True)
    page._operation = "manual"
    page._process_finished(0, None)

    recorded = [call for call in controller.calls if call[0] == "recorded"]
    assert recorded and recorded[0][1]["frequency"] == 3850
    text = page.scale_test_status.text()
    assert "held its stress test up to 3750 MHz" in text
    assert "requested 3850 MHz" in text
    # Still in manual mode: the tester was typing scales, not detecting.
    assert page.scale_override_check.isChecked()


def test_the_unified_view_offers_manual_scale_without_a_detection(qtbot):
    view = CpuControlView()
    qtbot.addWidget(view)
    view._apply_tuning(CpuTuningState(manual_scale_available=False, applying=False))
    assert view.manual_scale_check.isEnabled()

    view._apply_tuning(CpuTuningState(manual_scale_available=False, applying=True))
    assert not view.manual_scale_check.isEnabled()
