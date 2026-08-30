"""Pure presentation policy for the GPU governor safety banner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from bc250cc.domain.gpu.oberon import OBERON_SAFE_PROFILES


@dataclass(frozen=True)
class SafetyMessage:
    template: str
    values: tuple[tuple[str, object], ...] = ()
    literal: bool = False


@dataclass(frozen=True)
class GpuSafetyPresentation:
    title: str
    message: SafetyMessage
    tone: str
    status: str
    status_tone: str
    suffixes: tuple[SafetyMessage, ...] = ()


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _notice(
    title: str,
    message: str,
    tone: str,
    status: str,
    status_tone: str | None = None,
    *,
    values: Mapping[str, object] | None = None,
    literal: bool = False,
    suffixes: Sequence[SafetyMessage] = (),
) -> GpuSafetyPresentation:
    return GpuSafetyPresentation(
        title=title,
        message=SafetyMessage(message, tuple((values or {}).items()), literal),
        tone=tone,
        status=status,
        status_tone=status_tone or tone,
        suffixes=tuple(suffixes),
    )


def _oberon_notice(state: Mapping[str, object]) -> GpuSafetyPresentation:
    active = str(state.get("service_active") or "not-found").strip().lower()
    tools = _mapping(state.get("tools"))
    supported = _mapping(tools.get("supported_gpu_governors"))
    oberon = _mapping(supported.get("oberon-governor"))
    installed = bool(oberon.get("detected")) or any(
        bool(oberon.get(key))
        for key in ("binary_path", "unit_path", "package_installed", "active", "enabled")
    )
    installed = installed or active not in {"", "not-found", "unknown"}
    running = active in {"active", "running"} or bool(oberon.get("active"))
    if not installed:
        return _notice(
            "Oberon Governor was not found",
            "Oberon is selected, but its program or system service is missing. Use Prepare dependencies to install it, or select Cyan Skillfish Governor for full BC250 Control Center support.",
            "orange", "Not installed",
        )
    if not running:
        return _notice(
            "Oberon Governor is not active",
            "Oberon is installed, but its service is stopped. Use Activate service to start it. BC250 Control Center provides full integration only with Cyan Skillfish Governor.",
            "orange", "Offline",
        )
    current = int(state.get("current_min") or 0), int(state.get("current_max") or 0)
    if all(current) and current not in OBERON_SAFE_PROFILES:
        return _notice(
            "Oberon recovery required",
            "The current Oberon range {minimum}–{maximum} MHz is not a protected profile on this system. Stop all 3D load, wait for 1000 MHz, then select Gaming 1000–1850 MHz.",
            "orange", "Review",
            values={"minimum": current[0], "maximum": current[1]},
        )
    return _notice(
        "Oberon profiles ready",
        "Oberon is active. Choose 1000–1500 or 1000–1850 MHz, or the fixed 2000 MHz benchmark profile after stopping all 3D load. BC250 verifies GPU idle state before restarting Oberon. MangoHud or radeontop may still report about 655% GPU usage.",
        "blue", "Protected", "green",
    )


def _conflict_notice(
    state: Mapping[str, object], selected: str
) -> GpuSafetyPresentation | None:
    tools = _mapping(state.get("tools"))
    conflicts = tuple(tools.get("incompatible_gpu_governors") or ())
    if not conflicts:
        return None
    names = ", ".join(
        str(item.get("identifier") or item.get("service") or "unknown")
        for item in conflicts if isinstance(item, Mapping)
    ) or "unknown"
    return _notice(
        "Incompatible GPU governor detected",
        "{governors} is installed, enabled, or running. Two GPU frequency governors can issue conflicting clock commands and cause a crash or green screen at the next boot. Use Prepare dependencies to stop and disable the other service before changing {selected_governor}.",
        "red", "Blocked", values={"governors": names, "selected_governor": selected},
    )


def _runtime_notice(
    state: Mapping[str, object], *, is_oberon: bool
) -> GpuSafetyPresentation | None:
    if str(state.get("safe_points_error") or "").strip() and not is_oberon:
        return _notice(
            "Governor configuration could not be validated",
            "The safe-point curve was not loaded because the Cyan TOML is invalid. Repair the configuration or run Prepare dependencies before changing GPU clocks.",
            "red", "Blocked",
        )
    if is_oberon:
        return _oberon_notice(state)
    if state.get("safe_points_voltage_errors"):
        return _notice(
            "Governor blocked by invalid voltage curve",
            "A later safe-point has lower voltage than an earlier frequency. Correct or comment the invalid TOML entry, then restart cyan-skillfish-governor-smu.service.",
            "orange", "Blocked",
        )
    telemetry_warning = str(state.get("telemetry_warning") or "").strip()
    if telemetry_warning:
        return _notice(
            "Cyan runtime update required", telemetry_warning, "orange", "Update required",
            literal=True,
        )
    return None


def _high_point_notice(
    state: Mapping[str, object], safe_frequencies: Sequence[int]
) -> GpuSafetyPresentation | None:
    high_points = _mapping(state.get("high_frequency_points"))
    high_visible = (
        bool(high_points.get("enabled"))
        if "enabled" in high_points
        else any(int(frequency) > 2000 for frequency in safe_frequencies)
    )
    if not high_visible:
        return None
    suffixes = []
    if state.get("safe_points_duplicate_frequencies"):
        suffixes.append(SafetyMessage("Duplicate frequencies were also detected in the TOML."))
    if not bool(state.get("dbus_ok")):
        suffixes.append(SafetyMessage(
            "The governor is currently offline; these points will take effect after the service is activated."
        ))
    return _notice(
        "High OC laboratory mode",
        "Active safe-points above 2000 MHz are visible by default. Voltage is compared with the packaged upstream curve, but these points can still be unstable. Stop all 3D load before every change.",
        "orange", "Lab mode", suffixes=suffixes,
    )


def _offline_notice(state: Mapping[str, object]) -> GpuSafetyPresentation | None:
    dbus_ok = bool(state.get("dbus_ok"))
    if bool(state.get("range_control_ok", dbus_ok)):
        return None
    suffixes = []
    missing = tuple(state.get("safe_points_missing_voltage") or ())
    if missing:
        values = ", ".join(
            str(item.get("frequency") or item) if isinstance(item, Mapping) else str(item)
            for item in missing
        )
        suffixes.append(SafetyMessage("Missing voltage entries: {values}.", (("values", values),)))
    return _notice(
        "Governor D-Bus unavailable",
        "The page can still show passive telemetry, but runtime ranges cannot be applied. Read the service status and inspect the TOML before continuing. The governor service may be disabled; enable it with the Enable service button.",
        "orange", "Offline", suffixes=suffixes,
    )


def present_gpu_safety(
    state: Mapping[str, object], *, safe_frequencies: Sequence[int] = ()
) -> GpuSafetyPresentation:
    """Choose one deterministic safety state from passive governor evidence."""
    selected = str(state.get("governor_backend") or "cyan-skillfish-governor-smu")
    is_oberon = selected == "oberon-governor"
    for candidate in (
        _conflict_notice(state, selected),
        _runtime_notice(state, is_oberon=is_oberon),
        _high_point_notice(state, safe_frequencies),
        _offline_notice(state),
    ):
        if candidate is not None:
            return candidate
    return _notice(
        "Safe mode enabled",
        "Every active TOML safe-point is visible. Points above 2000 MHz will appear automatically when they are enabled in the TOML.",
        "blue", "Safe mode", "green",
    )
