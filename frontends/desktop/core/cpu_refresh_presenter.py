"""Pure CPU telemetry and persistence presentation for the CPU/SMU page."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

from bc250cc.domain.cpu.active_tuning import resolve_active_cpu_tuning


@dataclass(frozen=True)
class CpuText:
    template: str
    values: tuple[tuple[str, object], ...] = ()
    literal: bool = False


@dataclass(frozen=True)
class CpuTelemetryPresentation:
    frequency_mhz: float
    voltage_mv: float
    temperature_c: float
    power_w: float
    frequency_text: CpuText
    voltage_text: CpuText
    temperature_text: CpuText
    power_text: CpuText
    power_label: CpuText
    power_detail: CpuText
    live_frequency_text: str
    live_temperature_text: str
    live_frequency_mhz: int | None
    live_temperature_c: int | None


@dataclass(frozen=True)
class CpuPersistencePresentation:
    available: bool
    failed: bool
    enabled: bool
    active_state: str
    prepared_state: str
    prepared_detail: str
    config_exists: bool
    config_valid: bool
    config_protected: bool
    boot_config: tuple[tuple[str, object], ...]
    service_text: CpuText
    runtime_text: CpuText
    status_value: CpuText
    status_detail: CpuText


@dataclass(frozen=True)
class CpuTuningPresentation:
    detection_value: CpuText
    detection_detail: CpuText
    live_value: CpuText
    live_detail: CpuText
    applied_value: CpuText
    applied_detail: CpuText
    override_status: CpuText | None
    detection_matches: bool
    detection_same_boot: bool
    detection_recorded: bool
    detection_snapshot: tuple[tuple[str, object], ...]
    live_matches_detection: bool
    live_active_this_session: bool
    live_valid_for_persistence: bool
    live_test: tuple[tuple[str, object], ...]
    active_scale: object
    active_source: str
    active_source_kind: str


@dataclass(frozen=True)
class CpuSessionSummaryPresentation:
    live_now: CpuText
    last_applied: CpuText
    automatic_detection: CpuText
    manual_live_test: CpuText
    next_boot: CpuText
    recommended_next_step: CpuText


def _number(value: object) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else 0.0
    except (TypeError, ValueError):
        return 0.0


def _literal(value: object) -> CpuText:
    return CpuText(str(value), literal=True)


def _text(template: str, **values: object) -> CpuText:
    return CpuText(template, tuple(values.items()))


def present_cpu_telemetry(perf: Mapping[str, object]) -> CpuTelemetryPresentation:
    frequency = _number(perf.get("cpu_freq"))
    voltage = _number(perf.get("cpu_voltage"))
    if 0 < voltage < 10:
        voltage *= 1000
    temperature = _number(perf.get("cpu_temp"))
    power = _number(perf.get("power_w"))
    if perf.get("power_is_total"):
        power_detail = "Dedicated total-board power sensor"
    elif str(perf.get("power_scope") or "") == "gpu_soc":
        power_detail = "AMDGPU SoC power sensor; total board power unavailable"
    else:
        power_detail = "No live power sensor exposed"
    frequency_int = int(round(frequency)) if frequency else None
    temperature_int = int(round(temperature)) if temperature else None
    return CpuTelemetryPresentation(
        frequency_mhz=frequency,
        voltage_mv=voltage,
        temperature_c=temperature,
        power_w=power,
        frequency_text=_literal(f"{frequency / 1000:.2f} GHz") if frequency else _text("Not detected"),
        voltage_text=_literal(f"{voltage / 1000:.3f} V") if voltage else _text("Not exposed"),
        temperature_text=_literal(f"{temperature:.1f} °C") if temperature else _text("Not detected"),
        power_text=_literal(f"{power:.0f} W") if power else _text("Not detected"),
        power_label=_text(str(perf.get("power_label") or "Power sensor unavailable")),
        power_detail=_text(power_detail),
        live_frequency_text=f"{frequency_int} MHz" if frequency_int is not None else "-- MHz",
        live_temperature_text=f"{temperature_int} °C" if temperature_int is not None else "-- °C",
        live_frequency_mhz=frequency_int,
        live_temperature_c=temperature_int,
    )


def _cpu_persistence_status(
    *,
    failed: bool,
    supported: bool,
    enabled: bool,
    prepared_state: str,
    prepared_detail: str,
    protected: bool,
    config_valid: bool,
    persistent: Mapping[str, object],
    boot_config: Mapping[str, object],
) -> tuple[CpuText, CpuText]:
    if failed:
        return _text("Unavailable"), _text("Could not read persistence state; live telemetry remains available")
    if not supported:
        return _text("Unavailable"), _text(
            str(
                persistent.get("persistence_detail")
                or "Boot persistence is not supported by the active init system; live telemetry remains available"
            )
        )
    if enabled and boot_config.get("valid"):
        return _text("Enabled"), _text(
            "{frequency} MHz · scale {scale} · {temperature} °C",
            frequency=boot_config.get("frequency", "--"),
            scale=boot_config.get("scale", "--"),
            temperature=boot_config.get("max_temperature", "--"),
        )
    if enabled and persistent.get("ui_state"):
        return _text(prepared_state), _text(prepared_detail)
    if protected:
        if enabled:
            return _text("Enabled"), _text("Boot configuration is present; reinstall this build once to enable desktop validation")
        return _text("Disabled"), _text("Boot configuration is present but protected from desktop validation")
    if boot_config.get("exists"):
        if not config_valid:
            return _text("Attention"), _text("persistent config could not be validated")
        return _text("Disabled"), _text("Configuration exists but does not start automatically")
    return _text("Disabled"), _text("Does not start automatically")


def present_cpu_persistence(
    persistent: Mapping[str, object],
    refresh_errors: Mapping[str, object],
) -> CpuPersistencePresentation:
    failed = "persistent" in refresh_errors
    supported = persistent.get("persistence_supported") is not False
    available = bool(persistent) and not failed and supported
    enabled = available and str(persistent.get("enabled") or "").lower() == "enabled"
    active_state = str(persistent.get("active_state") or persistent.get("active") or "unknown")
    prepared_state = str(persistent.get("ui_state") or active_state)
    prepared_detail = str(persistent.get("ui_detail") or "systemd state")
    config_exists = bool(persistent) and not failed and bool(persistent.get("config_exists"))
    config_valid = bool(persistent) and not failed and bool(persistent.get("config_valid"))
    raw_config = persistent.get("config")
    boot_config = dict(raw_config) if isinstance(raw_config, Mapping) else {}
    protected = config_exists and str(boot_config.get("error_kind") or "") == "permission"

    value, detail = _cpu_persistence_status(
        failed=failed,
        supported=supported,
        enabled=enabled,
        prepared_state=prepared_state,
        prepared_detail=prepared_detail,
        protected=protected,
        config_valid=config_valid,
        persistent=persistent,
        boot_config=boot_config,
    )

    unavailable = "Unavailable" if failed else "Not detected"
    return CpuPersistencePresentation(
        available=available,
        failed=failed,
        enabled=enabled,
        active_state=active_state,
        prepared_state=prepared_state,
        prepared_detail=prepared_detail,
        config_exists=config_exists,
        config_valid=config_valid,
        config_protected=protected,
        boot_config=tuple(boot_config.items()),
        service_text=_text("Enabled" if enabled else "Disabled") if available else _text(unavailable),
        runtime_text=_text(prepared_state) if available else _text(unavailable),
        status_value=value,
        status_detail=detail,
    )


def _cpu_detection_text(
    detection: Mapping[str, object],
    snapshot: Mapping[str, object],
) -> tuple[CpuText, CpuText, bool]:
    matches = bool(detection.get("matches_current_config"))
    if matches and snapshot:
        frequency = snapshot.get("frequency", "--")
        requested_frequency = snapshot.get("requested_frequency")
        if requested_frequency is not None and str(requested_frequency) != str(frequency):
            detail = _text(
                "Requested {requested} MHz → detected {frequency} MHz · last automatic detection · reference only",
                requested=requested_frequency,
                frequency=frequency,
            )
        else:
            detail = _text(
                "{frequency} MHz · last automatic detection · reference only",
                frequency=frequency,
            )
        return (
            _literal(snapshot.get("scale", "--")),
            detail,
            matches,
        )
    if detection.get("recorded"):
        return _text("Stale"), _text("Detector reference no longer matches overclock.conf"), matches
    return _text("Not recorded"), _text("Run automatic detection to establish a reference"), matches


def _cpu_live_text(
    *,
    source: str,
    scale: object,
    live_matches: bool,
    live_test: Mapping[str, object],
) -> tuple[CpuText, CpuText]:
    active_sources = {
        "live": "Manual scale test applied in this session",
        "boot": "Applied automatically at this boot",
        "detection": "Applied by automatic detection in this session",
    }
    if source in active_sources:
        detail = (
            "Direct manual OC applied in this session"
            if source == "live" and live_test.get("reference_source") == "manual-direct"
            else active_sources[source]
        )
        return _literal(scale if scale is not None else "--"), _text(detail)
    if live_matches and live_test:
        return _text("Not live"), _text(
            "Scale {scale} was tested in a previous session",
            scale=live_test.get("scale", "--"),
        )
    return _text("Unknown"), _text("No active scale source detected")


def _cpu_applied_text(
    *,
    source: str,
    source_kind: str,
    scale: object,
    frequency: object,
    temperature: object,
    estimated_vid: object,
    last_applied_frequency: int | None,
) -> tuple[CpuText, CpuText]:
    if frequency is None or scale is None:
        if last_applied_frequency is not None:
            return _literal(f"{last_applied_frequency} MHz"), _text(
                "Latest applied CPU frequency; active scale could not be confirmed"
            )
        return _text("None"), _text("No CPU tuning has been applied yet")

    value = _text("{frequency} MHz · scale {scale}", frequency=frequency, scale=scale)
    detail_values = {
        "vid": estimated_vid if estimated_vid is not None else "--",
        "temperature": temperature if temperature is not None else "--",
    }
    if source == "boot":
        return value, _text("~{vid} mV estimated · {temperature} °C · applied at boot", **detail_values)
    if source_kind == "quick_access":
        return value, _text(
            "Quick Access verified snapshot · ~{vid} mV estimated · {temperature} °C",
            **detail_values,
        )
    if source == "live":
        return value, _text("~{vid} mV estimated · {temperature} °C · live test", **detail_values)
    return value, _text("Automatic detection · {temperature} °C", temperature=detail_values["temperature"])


def _cpu_override_status(
    *,
    enabled: bool,
    live_active: bool,
    live_test: Mapping[str, object],
    detection_matches: bool,
    snapshot: Mapping[str, object],
) -> CpuText | None:
    if not enabled:
        return None
    if live_active and live_test:
        if live_test.get("reference_source") == "manual-direct":
            return _text(
                "Manual OC is active for this session at scale {scale}. It is temporary and cannot be saved for boot without automatic detection.",
                scale=live_test.get("scale", "--"),
            )
        return _text(
            "Scale {scale} is applied live against the current detection (test {test_id}). Test stability before enabling it at boot.",
            scale=live_test.get("scale", "--"),
            test_id=live_test.get("test_id", "--"),
        )
    if detection_matches and snapshot:
        return _text(
            "Detected scale {scale}. The selected manual value must be tested live before it can be saved for boot.",
            scale=snapshot.get("scale", "--"),
        )
    return None


def present_cpu_tuning(
    persistent: Mapping[str, object],
    detection: Mapping[str, object],
    scale_live: Mapping[str, object],
    quick_access: Mapping[str, object] | None = None,
    *,
    last_applied_frequency: int | None,
    scale_override_enabled: bool,
) -> CpuTuningPresentation:
    raw_snapshot = detection.get("snapshot")
    snapshot = dict(raw_snapshot) if isinstance(raw_snapshot, Mapping) else {}
    detection_value, detection_detail, detection_matches = _cpu_detection_text(detection, snapshot)

    raw_live_test = scale_live.get("test")
    live_test = dict(raw_live_test) if isinstance(raw_live_test, Mapping) else {}
    live_matches = bool(scale_live.get("matches_detection"))
    live_active = bool(scale_live.get("active_in_current_session"))
    active = resolve_active_cpu_tuning(persistent, detection, scale_live, quick_access)
    source = str(active.get("source") or "")
    source_kind = str(active.get("source_kind") or "")
    scale = active.get("scale")
    frequency = active.get("frequency")
    temperature = active.get("temperature")
    estimated_vid = active.get("estimated_vid")

    live_value, live_detail = _cpu_live_text(
        source=source,
        scale=scale,
        live_matches=live_matches,
        live_test=live_test,
    )
    applied_value, applied_detail = _cpu_applied_text(
        source=source,
        source_kind=source_kind,
        scale=scale,
        frequency=frequency,
        temperature=temperature,
        estimated_vid=estimated_vid,
        last_applied_frequency=last_applied_frequency,
    )
    override_status = _cpu_override_status(
        enabled=scale_override_enabled,
        live_active=live_active,
        live_test=live_test,
        detection_matches=detection_matches,
        snapshot=snapshot,
    )

    return CpuTuningPresentation(
        detection_value=detection_value,
        detection_detail=detection_detail,
        live_value=live_value,
        live_detail=live_detail,
        applied_value=applied_value,
        applied_detail=applied_detail,
        override_status=override_status,
        detection_matches=detection_matches,
        detection_same_boot=bool(detection.get("same_boot")),
        detection_recorded=bool(detection.get("recorded")),
        detection_snapshot=tuple(snapshot.items()),
        live_matches_detection=live_matches,
        live_active_this_session=live_active,
        live_valid_for_persistence=bool(scale_live.get("valid_for_persistence")),
        live_test=tuple(live_test.items()),
        active_scale=scale,
        active_source=source,
        active_source_kind=source_kind,
    )


def _session_detection(state: Mapping[str, object]) -> CpuText:
    raw_detection = state.get("detection_snapshot")
    detection = dict(raw_detection) if isinstance(raw_detection, Mapping) else {}
    if state.get("detection_matches") and detection:
        return _text(
            "{frequency} MHz | scale {scale} | {temperature} °C",
            frequency=detection.get("frequency", "--"),
            scale=detection.get("scale", "--"),
            temperature=detection.get("temperature", "--"),
        )
    if state.get("detection_recorded"):
        return _text("A previous detection exists, but it no longer matches the current detector config")
    return _text("No automatic scale has been detected yet")


def _session_live_scale(state: Mapping[str, object]) -> CpuText:
    raw_live_test = state.get("live_scale_test")
    live_test = dict(raw_live_test) if isinstance(raw_live_test, Mapping) else {}
    raw_detection = state.get("detection_snapshot")
    detection = dict(raw_detection) if isinstance(raw_detection, Mapping) else {}
    if state.get("live_scale_active_this_session") and live_test:
        if live_test.get("reference_source") == "manual-direct":
            return _text(
                "scale {scale} at {frequency} MHz — direct manual OC active for this session only",
                scale=live_test.get("scale", "--"),
                frequency=live_test.get("frequency", "--"),
            )
        return _text(
            "scale {scale} at {frequency} MHz — active from a live test in this session",
            scale=live_test.get("scale", "--"),
            frequency=live_test.get("frequency", detection.get("frequency", "--")),
        )
    if state.get("live_scale_matches") and live_test:
        return _text(
            "scale {scale} was tested previously; it is not a live test from this session",
            scale=live_test.get("scale", "--"),
        )
    if live_test:
        return _text("A previous manual scale test exists, but it belongs to an older detection")
    return _text("No manual scale has been tested live")


def _session_boot_state(state: Mapping[str, object]) -> CpuText:
    raw_boot_config = state.get("boot_config")
    boot_config = dict(raw_boot_config) if isinstance(raw_boot_config, Mapping) else {}
    if state.get("service_enabled") and boot_config.get("valid"):
        return _text(
            "Enabled: {frequency} MHz | scale {scale} | {temperature} °C will be applied at boot",
            frequency=boot_config.get("frequency", "--"),
            scale=boot_config.get("scale", "--"),
            temperature=boot_config.get("max_temperature", "--"),
        )
    if boot_config.get("exists"):
        return _text("Disabled: a configuration file exists, but it will not start automatically")
    return _text("Disabled: no CPU overclock will be applied automatically at boot")


def _session_next_step(state: Mapping[str, object]) -> CpuText:
    raw_live_test = state.get("live_scale_test")
    live_test = dict(raw_live_test) if isinstance(raw_live_test, Mapping) else {}
    raw_detection = state.get("detection_snapshot")
    detection = dict(raw_detection) if isinstance(raw_detection, Mapping) else {}
    if state.get("live_scale_active_this_session") and live_test:
        if live_test.get("reference_source") == "manual-direct":
            return _text(
                "Keep testing this temporary manual OC. Run automatic detection before saving any CPU configuration for boot."
            )
        return _text("If this exact live scale remains stable under your real workload, you can save it for boot.")
    if state.get("active_scale_source") == "boot":
        return _text("This tuning was applied successfully at boot. Keep testing stability under your real workload.")
    if state.get("detection_matches") and detection:
        return _text("Test the detected result under your real workload. If you want another scale, test it live before saving it for boot.")
    return _text("Run automatic scale detection first. Nothing should be saved for boot until a detection result exists.")


def present_cpu_session_summary(
    state: Mapping[str, object],
    *,
    last_applied_frequency: int | None,
) -> CpuSessionSummaryPresentation:
    frequency = state.get("live_frequency_mhz")
    temperature = state.get("live_temperature_c")
    live_now = (
        _text("{temperature} °C | {frequency} MHz", temperature=temperature, frequency=frequency)
        if frequency is not None and temperature is not None
        else _text("Live CPU telemetry is not available yet")
    )
    last_applied = (
        _literal(f"{last_applied_frequency} MHz")
        if last_applied_frequency is not None
        else _text("None yet")
    )
    return CpuSessionSummaryPresentation(
        live_now=live_now,
        last_applied=last_applied,
        automatic_detection=_session_detection(state),
        manual_live_test=_session_live_scale(state),
        next_boot=_session_boot_state(state),
        recommended_next_step=_session_next_step(state),
    )
