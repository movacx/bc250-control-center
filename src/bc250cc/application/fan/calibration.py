"""Synchronous fan calibration using only caller-supplied I/O."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class CalibrationStep:
    percent: int
    rpm: int | None


@dataclass(frozen=True)
class CalibrationResult:
    stop_percent: int | None
    start_percent: int | None
    proposed_min: int
    proposed_start: int
    steps: tuple[CalibrationStep, ...]
    aborted: str


class _Abort(Exception):
    """An expected safety stop or unavailable measurement."""


def calibrate(
    *,
    write: Callable[[int], None],
    read_rpm: Callable[[], int | None],
    hottest_c: Callable[[], float | None],
    sleep: Callable[[float], None],
    cancelled: Callable[[], bool] = lambda: False,
    step: int = 5,
    settle_seconds: float = 3.0,
    abort_c: float = 80.0,
    margin: int = 5,
    pump: bool = False,
) -> CalibrationResult:
    """Measure running/stopped thresholds, then always attempt full speed.

    ``step`` must be an integer in 1..100 and ``margin`` in 0..100;
    settling must be finite and nonnegative and the temperature limit finite.
    Invalid arguments and I/O exceptions return an abort message. Even these
    paths attempt a final write of 100; pumps alone are refused without I/O.
    A failed final write is reported, since safe speed cannot be guaranteed.

    Endpoints 0 and 100 are sampled even when step does not divide 100.
    A fan still spinning at 0 has no measurable stop/start thresholds: both
    are None, proposals are 0/0, and calibration completes without a restart
    sweep. Missing tach readings later in either sweep abort as well.
    Aborted runs retain measurements but propose 0/0; callers must check
    ``aborted`` before applying proposals. The final safety write is not a
    measurement and is excluded from ``steps``.
    """
    if pump:
        return CalibrationResult(
            None, None, 0, 0, (),
            "pumps are not calibrated: stopping a pump is unsafe",
        )

    steps: list[CalibrationStep] = []
    stop_percent = start_percent = None
    aborted = ""

    def guard() -> None:
        if cancelled():
            raise _Abort("cancelled")
        temperature = hottest_c()
        if temperature is None or isinstance(temperature, bool) or not isfinite(temperature) or not 0 < temperature <= 130:
            raise _Abort("temperature reading unavailable")
        if temperature >= abort_c:
            raise _Abort(f"overheating: temperature at or above {abort_c:g} C")

    def measure(percent: int) -> int:
        guard()
        write(percent)
        guard()
        sleep(settle_seconds)
        guard()
        rpm = read_rpm()
        steps.append(CalibrationStep(percent, rpm))
        guard()
        if rpm is None or rpm < 0:
            raise _Abort("no tachometer reading")
        return rpm

    try:
        if type(step) is not int or not 1 <= step <= 100:
            raise ValueError("step must be an integer in 1..100")
        if type(margin) is not int or not 0 <= margin <= 100:
            raise ValueError("margin must be an integer in 0..100")
        if not isfinite(settle_seconds) or settle_seconds < 0:
            raise ValueError("settle_seconds must be finite and nonnegative")
        if not isfinite(abort_c):
            raise ValueError("abort_c must be finite")
        if measure(100) == 0:
            raise _Abort("no tachometer reading")
        last_spinning = 100
        for percent in (*range(100 - step, 0, -step), 0):
            if measure(percent) == 0:
                stop_percent = last_spinning
                break
            last_spinning = percent

        if stop_percent is not None:
            # Establish a stopped baseline before measuring the start duty.
            if steps[-1].percent != 0:
                baseline_rpm = measure(0)
            else:
                baseline_rpm = steps[-1].rpm
            if baseline_rpm != 0:
                raise _Abort("fan did not remain stopped at 0 percent")
            for percent in (*range(step, 100, step), 100):
                if measure(percent) > 0:
                    start_percent = percent
                    break
            if start_percent is None:
                raise _Abort("fan did not restart at 100 percent")
    except _Abort as exc:
        aborted = str(exc)
    except Exception as exc:
        aborted = f"calibration failed: {exc}"
    finally:
        try:
            write(100)
        except Exception as exc:
            failure = f"final write of 100 percent failed: {exc}"
            aborted = f"{aborted}; {failure}" if aborted else failure

    proposed_min = proposed_start = 0
    if not aborted and stop_percent is not None:
        proposed_min = max(0, min(100, stop_percent + margin))
        if start_percent is not None and start_percent > proposed_min:
            proposed_start = max(0, min(100, start_percent + margin))
    return CalibrationResult(
        stop_percent, start_percent, proposed_min, proposed_start,
        tuple(steps), aborted,
    )
