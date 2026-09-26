"""Deterministic runtime control for cyan-skillfish-governor on BC-250.

Runtime requests, Cyan's D-Bus state and the frequency physically observed from
amdgpu are deliberately separate evidence.  BC250 Control Center's reviewed
patched Cyan runtime fixes the upstream v0.4.12 shared ``max_freq`` state at the
source, so normal upward transitions never restart the governor as a hidden
workaround.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import asdict, dataclass

from bc250cc.shared.failure_text import describe_failure

CYAN_DBUS_SERVICE = "com.cyanskillfish.Governor"
CYAN_DBUS_OBJECT = "/com/cyanskillfish/Governor"
CYAN_PERFORMANCE_INTERFACE = "com.cyanskillfish.Governor.PerformanceMode"


class CyanGpuRuntimeError(RuntimeError):
    """Raised when Cyan cannot prove the requested runtime state."""


@dataclass(frozen=True)
class CyanApplyResult:
    mode: str
    requested_min: int
    requested_max: int
    current_min: int
    current_max: int
    allowed_min: int
    allowed_max: int
    performance_enabled: bool | None
    observed_frequency: int | None
    observed_voltage: int | None
    observed_busy: int | None
    observed_temperature: float | None
    thermal_throttling: int | None
    thermal_recovery: int | None
    hardware_verification: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def range_matches(current: tuple[int, int] | None, minimum: int, maximum: int) -> bool:
    return current == (int(minimum), int(maximum))


def fixed_request_matches(
    current: tuple[int, int] | None,
    frequency: int,
    performance_enabled: bool | None,
) -> bool:
    """Validate Cyan's SetFixedFrequency D-Bus contract.

    Cyan keeps the active lower bound and publishes the requested frequency as
    the upper bound while PerformanceMode is enabled; it does not promise a
    ``frequency..frequency`` Current object.
    """

    if current is None or performance_enabled is not True:
        return False
    minimum, maximum = int(current[0]), int(current[1])
    return minimum <= int(frequency) and maximum == int(frequency)


class CyanGpuEngine:
    """Small adapter around Cyan's D-Bus and physical GPU evidence contracts."""

    def __init__(
        self,
        repository,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.repository = repository
        self._monotonic = monotonic
        self._sleep = sleep

    def _unavailable_detail(self) -> str:
        reader = getattr(self.repository, "_cyan_dbus_unavailable_detail", None)
        try:
            return str(reader() or "") if callable(reader) else ""
        except Exception:
            return ""

    def _read_range(self, kind: str) -> tuple[int, int] | None:
        value = self.repository._leer_rango_governor(kind)
        if value is None:
            return None
        return int(value[0]), int(value[1])

    def _performance_enabled(self) -> bool | None:
        reader = getattr(self.repository, "_dbus_bool_property", None)
        if not callable(reader):
            return None
        try:
            value = reader(CYAN_DBUS_OBJECT, CYAN_PERFORMANCE_INTERFACE, "Enabled")
        except (OSError, RuntimeError, TypeError, ValueError, AttributeError):
            return None
        return value if isinstance(value, bool) else None

    def _thermal_thresholds(self) -> tuple[int | None, int | None]:
        reader = getattr(self.repository, "_dbus_uint_property", None)
        if not callable(reader):
            return None, None
        values: list[int | None] = []
        for name in ("TemperatureThrottling", "TemperatureRecovery"):
            try:
                value = reader(CYAN_DBUS_OBJECT, CYAN_PERFORMANCE_INTERFACE, name)
            except (OSError, RuntimeError, TypeError, ValueError, AttributeError):
                value = None
            values.append(int(value) if value is not None else None)
        return values[0], values[1]

    def _device_temperature(self) -> float | None:
        reader = getattr(self.repository, "temperatura_chip", None)
        if not callable(reader):
            return None
        try:
            value = reader("amdgpu", "edge")
        except (OSError, RuntimeError, TypeError, ValueError, AttributeError):
            return None
        return float(value) if value is not None else None

    def _device_sample(self) -> tuple[int | None, int | None, int | None]:
        """Read the same coherent evidence object used by the main GPU status."""

        try:
            gpu = self.repository._gpu_device_path()
            evidence_reader = getattr(self.repository, "_gpu_device_evidence", None)
            if callable(evidence_reader):
                evidence = evidence_reader(gpu)
                frequency = (
                    int(evidence.sclk_actual)
                    if evidence.sclk_actual is not None
                    else None
                )
                voltage = (
                    int(evidence.voltage_actual)
                    if evidence.voltage_actual is not None
                    else None
                )
                busy = int(evidence.busy) if evidence.busy is not None else None
                return frequency, voltage, busy
        except (OSError, RuntimeError, TypeError, ValueError, AttributeError):
            return None, None, None
        return None, None, None

    def _call(self, method: str, signature: str, *arguments: int) -> None:
        command = [
            "busctl",
            "call",
            CYAN_DBUS_SERVICE,
            CYAN_DBUS_OBJECT,
            CYAN_PERFORMANCE_INTERFACE,
            method,
            signature,
            *(str(int(value)) for value in arguments),
        ]
        code, stdout, stderr = self.repository._ejecutar(command, timeout=5)
        if code != 0:
            # A silent D-Bus failure used to surface as a bare number; the
            # catalog maps it to the governor diagnosis instead.
            raise CyanGpuRuntimeError(describe_failure(code, stdout, stderr))

    def _wait_range(
        self,
        predicate: Callable[[tuple[int, int]], bool],
        *,
        timeout: float = 2.0,
    ) -> tuple[int, int] | None:
        deadline = self._monotonic() + max(0.1, float(timeout))
        current = None
        while self._monotonic() < deadline:
            current = self._read_range("Current")
            if current is not None and predicate(current):
                return current
            self._sleep(0.05)
        return current

    @staticmethod
    def _require_bounds(
        minimum: int,
        maximum: int,
        allowed: tuple[int, int] | None,
    ) -> tuple[int, int]:
        minimum, maximum = int(minimum), int(maximum)
        if minimum <= 0 or maximum <= 0:
            raise ValueError(
                "GPU runtime range requires positive minimum and maximum frequencies."
            )
        if minimum > maximum:
            raise ValueError("GPU minimum frequency cannot exceed maximum frequency.")
        if allowed is None:
            raise CyanGpuRuntimeError(
                "Cyan D-Bus Allowed range is unavailable. The governor is not ready for a GPU request."
            )
        if minimum < allowed[0] or maximum > allowed[1]:
            raise ValueError(
                f"GPU range {minimum}-{maximum} MHz is outside Cyan's active "
                f"{allowed[0]}-{allowed[1]} MHz range."
            )
        return minimum, maximum

    def _hardware_summary_once(
        self, requested_max: int, *, fixed: bool
    ) -> tuple[
        int | None,
        int | None,
        int | None,
        float | None,
        int | None,
        int | None,
        str,
    ]:
        frequency, voltage, busy = self._device_sample()
        temperature = self._device_temperature()
        throttling, recovery = self._thermal_thresholds()
        if frequency is None:
            return (
                frequency,
                voltage,
                busy,
                temperature,
                throttling,
                recovery,
                "not-observable",
            )

        tolerance = max(25, int(requested_max) // 50)  # 2%, minimum 25 MHz.
        if abs(int(frequency) - int(requested_max)) <= tolerance:
            verification = "confirmed"
        elif temperature is not None and throttling and temperature >= throttling:
            verification = "thermal-throttled"
        # Being above the recovery threshold does not prove that Cyan is
        # recovering from a previous thermal throttle.  Treating that state as
        # thermal recovery can hide a real frequency-control failure (for
        # example 1000 MHz at 99% load while the GPU is 80 C with an 85 C
        # throttle).  Without explicit evidence that the throttle threshold was
        # crossed, report the hardware mismatch normally.
        elif fixed:
            verification = "not-confirmed"
        elif busy is not None and int(busy) >= 80:
            verification = "not-confirmed-under-load"
        else:
            verification = "pending-load"
        return (
            frequency,
            voltage,
            busy,
            temperature,
            throttling,
            recovery,
            verification,
        )

    def _hardware_summary(
        self,
        requested_max: int,
        *,
        fixed: bool,
        timeout: float = 2.5,
    ) -> tuple[
        int | None,
        int | None,
        int | None,
        float | None,
        int | None,
        int | None,
        str,
    ]:
        """Wait briefly only when hardware should already be approaching target."""

        deadline = self._monotonic() + max(0.0, float(timeout))
        summary = self._hardware_summary_once(requested_max, fixed=fixed)
        while self._monotonic() < deadline:
            verification = summary[-1]
            if verification in {
                "confirmed",
                "thermal-throttled",
                "pending-load",
            }:
                return summary
            self._sleep(0.1)
            summary = self._hardware_summary_once(requested_max, fixed=fixed)
        return summary

    def apply_range(self, minimum: int, maximum: int) -> CyanApplyResult:
        allowed = self._read_range("Allowed")
        if allowed is None:
            raise CyanGpuRuntimeError(
                "Cyan D-Bus Allowed range is unavailable. The governor is not ready for a GPU request."
                + self._unavailable_detail()
            )
        minimum, maximum = self._require_bounds(minimum, maximum, allowed)

        # SetRange also exits PerformanceMode and TestMode. Equal bounds alone
        # do not prove the governor is already running adaptively.
        self._call("SetRange", "uu", minimum, maximum)
        current = self._wait_range(lambda value: range_matches(value, minimum, maximum))
        if not range_matches(current, minimum, maximum):
            raise CyanGpuRuntimeError(
                "Cyan accepted SetRange but did not publish the requested "
                f"{minimum}-{maximum} MHz runtime range (reported {current!r})."
            )

        (
            observed_frequency,
            observed_voltage,
            observed_busy,
            observed_temperature,
            thermal_throttling,
            thermal_recovery,
            verification,
        ) = self._hardware_summary(maximum, fixed=False, timeout=0.0)
        return CyanApplyResult(
            mode="adaptive-range",
            requested_min=minimum,
            requested_max=maximum,
            current_min=current[0],
            current_max=current[1],
            allowed_min=allowed[0],
            allowed_max=allowed[1],
            performance_enabled=self._performance_enabled(),
            observed_frequency=observed_frequency,
            observed_voltage=observed_voltage,
            observed_busy=observed_busy,
            observed_temperature=observed_temperature,
            thermal_throttling=thermal_throttling,
            thermal_recovery=thermal_recovery,
            hardware_verification=verification,
        )

    def apply_fixed(self, frequency: int) -> CyanApplyResult:
        frequency = int(frequency)
        allowed = self._read_range("Allowed")
        if allowed is None:
            raise CyanGpuRuntimeError(
                "Cyan D-Bus Allowed range is unavailable." + self._unavailable_detail()
            )
        if not allowed[0] <= frequency <= allowed[1]:
            raise ValueError(
                f"GPU frequency {frequency} MHz is outside Cyan's active "
                f"{allowed[0]}-{allowed[1]} MHz range."
            )

        self._call("SetFixedFrequency", "u", frequency)
        current = self._wait_range(lambda value: int(value[1]) == frequency)
        performance = self._performance_enabled()
        if not fixed_request_matches(current, frequency, performance):
            raise CyanGpuRuntimeError(
                "Cyan accepted SetFixedFrequency but did not publish its fixed-frequency "
                f"contract for {frequency} MHz (range {current!r}, performance={performance!r})."
            )

        (
            observed_frequency,
            observed_voltage,
            observed_busy,
            observed_temperature,
            thermal_throttling,
            thermal_recovery,
            verification,
        ) = self._hardware_summary(frequency, fixed=True)
        return CyanApplyResult(
            mode="fixed-frequency",
            requested_min=current[0],
            requested_max=frequency,
            current_min=current[0],
            current_max=current[1],
            allowed_min=allowed[0],
            allowed_max=allowed[1],
            performance_enabled=performance,
            observed_frequency=observed_frequency,
            observed_voltage=observed_voltage,
            observed_busy=observed_busy,
            observed_temperature=observed_temperature,
            thermal_throttling=thermal_throttling,
            thermal_recovery=thermal_recovery,
            hardware_verification=verification,
        )
