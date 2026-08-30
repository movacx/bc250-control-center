"""Pure health classification for parsed Cyan and Oberon configuration."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class GovernorHealthDecision:
    status: str
    title: str
    detail: str
    recommendation: str = ""
    repair_action: str = ""


def classify_oberon_health(
    state: Mapping[str, object],
    *,
    voltage_floor_mv: int,
) -> GovernorHealthDecision:
    if state.get("safe_voltage"):
        return GovernorHealthDecision(
            "healthy",
            "Oberon YAML",
            f"Valid Oberon YAML: {state.get('frequency_min')}-{state.get('frequency_max')} MHz, "
            f"{state.get('voltage_min')}-{state.get('voltage_max')} mV.",
        )
    return GovernorHealthDecision(
        "error",
        "Oberon YAML",
        f"Oberon YAML contains a voltage below the enforced {int(voltage_floor_mv)} mV safety floor.",
        "Review the endpoint voltages before starting Oberon.",
    )


def classify_cyan_health(
    *,
    migration: Mapping[str, object],
    frequency_range: Mapping[str, object],
    safe_points: Sequence[object],
    telemetry: Mapping[str, object],
    runtime: Mapping[str, object],
    needs_frequency_fix: bool,
) -> GovernorHealthDecision:
    if migration.get("needed"):
        return GovernorHealthDecision(
            "warning",
            "Governor TOML",
            str(migration.get("reason") or "A legacy frequency-range layout was detected."),
            "Normalize the section without replacing its saved values.",
            "migrate-legacy-frequency-range",
        )
    if not frequency_range.get("valid"):
        return GovernorHealthDecision(
            "error",
            "Governor TOML",
            str(frequency_range.get("error") or "Invalid frequency range."),
            "Disable the complete frequency-range section to restore deterministic profile mode.",
            "clear-frequency-range",
        )
    if not safe_points:
        return GovernorHealthDecision(
            "error", "Governor TOML", "No safe-points were found.",
            "Back up the file and restore a valid upstream TOML configuration.",
        )
    if needs_frequency_fix and not runtime.get("supports_frequency_fix"):
        return GovernorHealthDecision(
            "warning",
            "Governor runtime",
            "The TOML requests Cyan fix-freq, but the service binary does not contain the upstream GPU frequency reporting fix.",
            "Update Cyan from its official SMU release and verify the active service override.",
            "update-cyan-runtime",
        )
    if telemetry.get("fix_metrics") and runtime.get("metrics_fix_runtime_error"):
        return GovernorHealthDecision(
            "warning",
            "Cyan GPU metrics overlay",
            "Cyan's optional GPU usage metrics overlay is failing on the active runtime. GPU frequency reporting remains independent.",
            "Review the four Cyan compatibility controls explicitly. Disable fix-metrics only if this kernel does not provide the required metrics target.",
            "review-cyan-compatibility",
        )
    telemetry_ok = bool(telemetry.get("valid"))
    if not telemetry_ok:
        return GovernorHealthDecision(
            "warning",
            "Governor TOML",
            "Cyan compatibility configuration is incomplete or contains an unsupported value.",
            "Choose gpu.set-method, gpu-usage.method, and both telemetry switches explicitly, then validate the TOML.",
            "review-cyan-compatibility",
        )
    return GovernorHealthDecision(
        "healthy",
        "Governor TOML",
        f"Valid TOML; range mode: {frequency_range.get('mode')}; {len(safe_points)} safe-points.",
    )
