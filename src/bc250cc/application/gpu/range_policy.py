"""Pure preflight policy for Cyan and Oberon frequency ranges."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from bc250cc.domain.gpu.oberon import OBERON_SAFE_PROFILES
from bc250cc.domain.gpu.voltage_profiles import VOLTAGE_BOOST_START_MHZ, voltage_profile


@dataclass(frozen=True)
class RangeNotice:
    title: str
    message: str
    tone: str
    values: tuple[tuple[str, object], ...] = ()
    details: str = ""


@dataclass(frozen=True)
class RangeEvidence:
    backend: str
    allowed_min: int
    allowed_max: int
    safe_frequencies: tuple[int, ...]
    safe_voltages: Mapping[int, int]
    packaged_voltages: Mapping[int, int]
    lab_frequencies: tuple[int, ...]
    voltage_errors: tuple[Mapping[str, object], ...] = ()
    duplicate_frequencies: tuple[int, ...] = ()
    missing_voltage: tuple[int, ...] = ()
    config_error: str = ""
    current_max: int = 0
    actual_clock: int = 0
    gpu_busy: int | None = None
    set_method: str = "smu"


@dataclass(frozen=True)
class RangeDecision:
    valid: bool
    notice: RangeNotice | None = None
    warnings: tuple[RangeNotice, ...] = ()


def _notice(title: str, message: str, tone: str = "orange", **values) -> RangeDecision:
    return RangeDecision(False, RangeNotice(title, message, tone, tuple(values.items())))


def high_oc_voltage_gaps(maximum: int, evidence: RangeEvidence) -> tuple[tuple[int, int, int | None], ...]:
    if maximum <= 2000:
        return ()
    required = voltage_profile(3)
    gaps = []
    for frequency in evidence.lab_frequencies:
        if frequency < VOLTAGE_BOOST_START_MHZ or frequency > maximum:
            continue
        expected = required[frequency]
        current = evidence.safe_voltages.get(frequency)
        if current is None or int(current) < expected:
            gaps.append((frequency, expected, current))
    return tuple(gaps)


def _bounds_rejection(
    minimum: int, maximum: int, evidence: RangeEvidence
) -> RangeDecision | None:
    if minimum <= 0 or maximum <= 0:
        return _notice("Invalid range", "Enter both minimum and maximum frequencies.")
    if minimum > maximum:
        return _notice("Invalid range", "Minimum frequency cannot be greater than maximum frequency.")
    if minimum < evidence.allowed_min or maximum > evidence.allowed_max:
        return _notice(
            "Range outside allowed limits",
            "Requested {minimum}–{maximum} MHz, while D-Bus currently allows {allowed_min}–{allowed_max} MHz.",
            minimum=minimum, maximum=maximum,
            allowed_min=evidence.allowed_min, allowed_max=evidence.allowed_max,
        )
    return None


def _curve_rejection(evidence: RangeEvidence) -> RangeDecision | None:
    if evidence.config_error:
        return _notice(
            "Governor TOML curve rejected",
            "The Cyan TOML could not be validated. Repair the configuration or run Prepare dependencies before applying a GPU range.",
            "red",
        )
    if evidence.duplicate_frequencies:
        return RangeDecision(False, RangeNotice(
            "Governor TOML curve rejected",
            "Duplicate safe-point frequencies make the active voltage curve ambiguous. Remove or comment the duplicate blocks before applying a GPU range.",
            "red",
            details=", ".join(f"{value} MHz" for value in evidence.duplicate_frequencies),
        ))
    if evidence.missing_voltage:
        return RangeDecision(False, RangeNotice(
            "Governor TOML curve rejected",
            "Every active safe-point must define a voltage before a GPU range can be applied.",
            "red",
            details=", ".join(f"{value} MHz" for value in evidence.missing_voltage),
        ))
    if evidence.voltage_errors:
        details = "; ".join(
            f"{item.get('previous_frequency')} MHz/{item.get('previous_voltage')} mV > "
            f"{item.get('frequency')} MHz/{item.get('voltage')} mV"
            for item in evidence.voltage_errors
        )
        return RangeDecision(False, RangeNotice(
            "Governor TOML curve rejected",
            "The voltage curve decreases while frequency rises. No profile will be applied until the TOML is corrected and the governor is restarted.",
            "red", details=details,
        ))
    return None


def _cyan_point_rejection(
    maximum: int, evidence: RangeEvidence
) -> RangeDecision | None:
    if not evidence.safe_frequencies:
        return _notice(
            "No active safe-point table",
            "The governor did not expose any TOML safe-point with frequency and voltage. Read the service status and correct the configuration before applying a range.",
        )
    # Cyan interpolates voltage between adjacent safe-points. Requiring the
    # requested maximum to be an exact TOML entry was a Control Center policy,
    # not an upstream runtime requirement. D-Bus Allowed bounds are the
    # authoritative runtime envelope.
    lowest = min(int(value) for value in evidence.safe_frequencies)
    highest = max(int(value) for value in evidence.safe_frequencies)
    if maximum < lowest or maximum > highest:
        return _notice(
            "Range outside active safe-points",
            "Requested maximum {maximum} MHz is outside the active Cyan safe-point envelope {lowest}–{highest} MHz.",
            maximum=maximum, lowest=lowest, highest=highest,
        )
    return None


def _accepted_decision(maximum: int, evidence: RangeEvidence) -> RangeDecision:
    if evidence.backend == "oberon-governor":
        warnings = (
            RangeNotice(
                "",
                "Oberon reloads two YAML endpoints and restarts its service. Control Center uses the upstream 1000 mV baseline for both endpoints; board stability still varies.",
                "orange",
            ),
        ) if maximum >= 1850 else ()
        return RangeDecision(True, warnings=warnings)

    warnings: list[RangeNotice] = []
    voltage = evidence.safe_voltages.get(maximum)
    original = evidence.packaged_voltages.get(maximum)
    if maximum > 1500 and (original is None or voltage is None or voltage < original):
        warnings.append(RangeNotice(
            "",
            "{maximum} MHz is configured at {voltage} mV; the packaged original voltage is {original} mV. This is an undervolt laboratory condition.",
            "orange",
            (("maximum", maximum), ("voltage", voltage or "--"), ("original", original or "--")),
        ))

    # High-OC voltage levels are guidance, not a Cyan protocol requirement.
    # Keep the information visible without blocking an otherwise valid request.
    gaps = high_oc_voltage_gaps(maximum, evidence)
    if gaps:
        details = ", ".join(
            f"{frequency} MHz: {current if current is not None else '--'}/{required} mV"
            for frequency, required, current in gaps
        )
        warnings.append(RangeNotice(
            "",
            "The selected +2000 MHz range is experimental. Some points are below the previous Level 3 guidance; stability is board-specific.",
            "orange",
            details=details,
        ))

    drop = evidence.current_max - maximum if evidence.current_max else 0
    high_load = evidence.gpu_busy is not None and evidence.gpu_busy >= 35
    abrupt = drop >= 500 or (evidence.actual_clock >= 1800 and maximum <= 1500)
    if drop > 0 and abrupt and high_load:
        warnings.append(RangeNotice(
            "",
            "GPU load is {busy}% while the ceiling is being reduced from {actual_max} MHz. A large live transition can destabilize the display; stop the workload or step down gradually if this board is sensitive.",
            "orange",
            (("busy", evidence.gpu_busy), ("actual_max", evidence.current_max)),
        ))
    elif drop >= 700:
        warnings.append(RangeNotice(
            "",
            "This is a {drop} MHz ceiling reduction. Stop all 3D load and lower the range in steps if the display has frozen during previous tests.",
            "orange", (("drop", drop),),
        ))

    if maximum >= 1850:
        warnings.append(RangeNotice(
            "", "Do not change frequency while a game, FurMark, or another 3D workload is active.", "orange"
        ))
    return RangeDecision(True, warnings=tuple(warnings))


def validate_gpu_range(minimum: int, maximum: int, evidence: RangeEvidence) -> RangeDecision:
    rejection = _bounds_rejection(minimum, maximum, evidence)
    if rejection is not None:
        return rejection
    if evidence.backend == "oberon-governor" and (minimum, maximum) not in OBERON_SAFE_PROFILES:
        return _notice(
            "Unsupported Oberon profile",
            "Oberon supports 1000–1500, 1000–1850, or the fixed 2000 MHz benchmark profile. The benchmark profile requires an idle GPU and explicit confirmation.",
        )
    rejection = _curve_rejection(evidence)
    if rejection is not None:
        return rejection
    if evidence.backend != "oberon-governor":
        rejection = _cyan_point_rejection(maximum, evidence)
        if rejection is not None:
            return rejection
    return _accepted_decision(maximum, evidence)
