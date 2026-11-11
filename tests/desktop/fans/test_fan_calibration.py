"""Hardware-free calibration sweeps and safety exits."""

from dataclasses import FrozenInstanceError

import pytest

from bc250cc.application.fan.calibration import CalibrationStep, calibrate


class Fan:
    def __init__(self, stop=20, start=30):
        self.stop = stop
        self.start = start
        self.spinning = True
        self.writes = []
        self.sleeps = []

    def write(self, percent):
        assert 0 <= percent <= 100
        self.writes.append(percent)
        if self.spinning and percent < self.stop:
            self.spinning = False
        elif not self.spinning and percent >= self.start:
            self.spinning = True

    def rpm(self):
        return 1200 if self.spinning else 0

    def run(self, **kwargs):
        callbacks = dict(
            write=self.write, read_rpm=self.rpm, hottest_c=lambda: 40.0,
            sleep=self.sleeps.append,
        )
        callbacks.update(kwargs)
        return calibrate(**callbacks)


def test_normal_fan_measures_hysteresis_and_records_each_settled_step():
    fan = Fan()
    result = fan.run()
    assert result.aborted == ""
    assert (result.stop_percent, result.start_percent) == (20, 30)
    assert (result.proposed_min, result.proposed_start) == (25, 35)
    expected = list(range(100, 10, -5)) + list(range(0, 35, 5))
    assert [s.percent for s in result.steps] == expected
    assert fan.writes == expected + [100]
    assert fan.sleeps == [3.0] * len(expected)
    assert result.steps[0] == CalibrationStep(100, 1200)
    assert CalibrationStep(15, 0) in result.steps
    assert isinstance(result.steps, tuple)
    with pytest.raises(FrozenInstanceError):
        result.proposed_min = 0
    with pytest.raises(FrozenInstanceError):
        result.steps[0].rpm = 0


def test_fan_that_never_stops_has_no_measurable_thresholds():
    fan = Fan(stop=0)
    result = fan.run()
    assert result.aborted == ""
    assert (result.stop_percent, result.start_percent) == (None, None)
    assert (result.proposed_min, result.proposed_start) == (0, 0)
    assert result.steps[-1] == CalibrationStep(0, 1200)
    assert fan.writes[-1] == 100


@pytest.mark.parametrize("rpm", [None, 0])
def test_no_tach_at_full_speed_aborts(rpm):
    fan = Fan()
    result = fan.run(read_rpm=lambda: rpm)
    assert result.aborted == "no tachometer reading"
    assert result.steps == (CalibrationStep(100, rpm),)
    assert fan.writes == [100, 100]


def test_tach_disappearing_mid_sweep_is_not_treated_as_a_stopped_fan():
    fan = Fan()
    readings = iter([1200, None])
    result = fan.run(read_rpm=lambda: next(readings))
    assert result.aborted == "no tachometer reading"
    assert fan.writes == [100, 95, 100]


@pytest.mark.parametrize("reason", ["heat", "cancel"])
def test_safety_exit_immediately_after_settling(reason):
    fan = Fan()
    options = dict(
        hottest_c=lambda: 80.0 if reason == "heat" and fan.sleeps else 40.0,
        cancelled=lambda: reason == "cancel" and bool(fan.sleeps),
    )
    result = fan.run(**options)
    assert ("overheating" if reason == "heat" else "cancelled") in result.aborted
    assert result.steps == ()
    assert fan.writes == [100, 100]


def test_already_cancelled_does_not_start_a_sweep():
    fan = Fan()
    assert fan.run(cancelled=lambda: True).aborted == "cancelled"
    assert fan.writes == [100]
    assert fan.sleeps == []


@pytest.mark.parametrize("callback", ["write", "read_rpm", "hottest_c", "sleep", "cancelled"])
def test_callback_exception_returns_abort_and_attempts_safe_speed(callback):
    fan = Fan()

    def fail(*args):
        if callback == "write":
            fan.writes.append(args[0])
        raise OSError("device unavailable")

    result = fan.run(**{callback: fail})
    assert "device unavailable" in result.aborted
    assert fan.writes[-1] == 100
    assert (result.proposed_min, result.proposed_start) == (0, 0)
    if callback == "write":
        assert fan.writes == [100, 100]
        assert "final write" in result.aborted


def test_write_failure_mid_run_still_restores_full_speed():
    fan = Fan()

    def write(percent):
        fan.write(percent)
        if percent == 95:
            raise OSError("write failed")

    result = fan.run(write=write)
    assert result.aborted == "calibration failed: write failed"
    assert fan.writes == [100, 95, 100]


def test_final_write_failure_changes_success_to_abort():
    fan = Fan(stop=0)

    def write(percent):
        fan.write(percent)
        if percent == 100 and len(fan.writes) > 1:
            raise OSError("restore failed")

    assert "final write of 100 percent failed" in fan.run(write=write).aborted
    assert fan.writes[-1] == 100


def test_pump_is_refused_without_invoking_any_callback():
    def unexpected(*args):
        pytest.fail("pump calibration must not perform I/O")

    result = calibrate(
        write=unexpected, read_rpm=unexpected, hottest_c=unexpected,
        sleep=unexpected, cancelled=unexpected, pump=True,
    )
    assert result.aborted == "pumps are not calibrated: stopping a pump is unsafe"
    assert result.steps == ()


@pytest.mark.parametrize("step", [1, 7, 100])
def test_valid_step_bounds_include_both_endpoints(step):
    fan = Fan()
    result = fan.run(step=step, settle_seconds=0)
    assert result.aborted == ""
    assert result.steps[0].percent == 100
    assert any(s.percent == 0 for s in result.steps)
    assert all(0 <= p <= 100 for p in fan.writes)
    assert all(s == 0 for s in fan.sleeps)
    assert fan.writes[-1] == 100


@pytest.mark.parametrize(
    "options, message",
    [
        ({"step": v}, "step") for v in (0, -1, 101, 2.5, True)
    ] + [
        ({"margin": v}, "margin") for v in (-1, 101, 2.5, True)
    ] + [
        ({"settle_seconds": v}, "settle_seconds")
        for v in (-1, float("inf"), float("nan"))
    ] + [
        ({"abort_c": v}, "abort_c") for v in (float("inf"), float("nan"))
    ],
)
def test_invalid_parameters_abort_and_attempt_safe_speed(options, message):
    fan = Fan()
    result = fan.run(**options)
    assert message in result.aborted
    assert result.steps == ()
    assert fan.writes == [100]


@pytest.mark.parametrize("margin, expected", [(0, (20, 30)), (10, (30, 0)), (100, (100, 0))])
def test_margin_and_redundant_start_boost(margin, expected):
    result = Fan().run(margin=margin)
    assert result.aborted == ""
    assert (result.proposed_min, result.proposed_start) == expected


def test_start_proposal_is_clamped_to_100():
    result = Fan(start=100).run(margin=5)
    assert (result.proposed_min, result.proposed_start) == (25, 100)


def test_fan_that_fails_to_restart_aborts():
    fan = Fan(start=101)
    result = fan.run()
    assert result.aborted == "fan did not restart at 100 percent"
    assert (result.proposed_min, result.proposed_start) == (0, 0)
    assert fan.writes[-1] == 100


@pytest.mark.parametrize("temperature", [None, float("nan"), float("inf"), -1, 0, 131])
def test_missing_or_invalid_temperature_never_starts_calibration(temperature):
    fan = Fan()
    result = fan.run(hottest_c=lambda: temperature)
    assert result.aborted == "temperature reading unavailable"
    assert fan.writes == [100]
    assert not result.steps


def test_losing_temperature_mid_sweep_aborts_at_full_speed():
    fan = Fan()
    result = fan.run(hottest_c=lambda: None if len(fan.writes) > 1 else 40.0)
    assert result.aborted == "temperature reading unavailable"
    assert fan.writes == [100, 95, 100]
