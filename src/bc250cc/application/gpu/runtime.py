"""Pure presentation contract for GPU governor runtime status cards."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class RuntimeText:
    template: str
    values: tuple[tuple[str, object], ...] = ()
    literal: bool = False


@dataclass(frozen=True)
class RuntimeLine:
    value: RuntimeText
    detail: RuntimeText


@dataclass(frozen=True)
class GpuRuntimePresentation:
    lines: tuple[RuntimeLine, ...]
    card_status: RuntimeText
    card_tone: str


def _literal(value: object) -> RuntimeText:
    return RuntimeText(str(value), literal=True)


def _text(value: object) -> RuntimeText:
    return RuntimeText(str(value))


def present_gpu_runtime(
    gpu: Mapping[str, object],
    *,
    is_oberon: bool,
    running: bool,
    enabled_at_boot: bool,
    range_control_ok: bool,
    active: object,
    enabled: object,
    dbus_ok: bool,
    range_text: object,
    profile_name: object,
    safe_point_count: int,
    refreshed_at: str | None = None,
) -> GpuRuntimePresentation:
    active_text = "Running" if running else str(active or "").capitalize()
    enabled_text = "Enabled" if enabled_at_boot else str(enabled or "").capitalize()
    if is_oberon and range_control_ok:
        api_state = "Validated"
    elif dbus_ok:
        api_state = "Connected"
    else:
        api_state = "Unavailable"
    lines = (
        RuntimeLine(
            _text(active_text),
            _text(gpu.get("service_sub") or "systemd state"),
        ),
        RuntimeLine(
            _text(enabled_text),
            _text("persistent at boot" if enabled_at_boot else "not persistent"),
        ),
        RuntimeLine(
            _text(api_state),
            _text("Oberon YAML + service restart" if is_oberon else "runtime range API"),
        ),
        RuntimeLine(_text(range_text), _text(profile_name)),
        RuntimeLine(
            _literal(int(safe_point_count)),
            _text(
                "Oberon endpoint OPPs"
                if is_oberon
                else "active TOML entries with frequency"
            ),
        ),
        # Kept in the presentation contract for API compatibility.  The
        # desktop runtime card intentionally does not render this redundant
        # passive timestamp tile anymore.
        RuntimeLine(_literal(refreshed_at or "--:--:--"), _text("passive refresh")),
    )
    return GpuRuntimePresentation(
        lines=lines,
        card_status=_text(active_text),
        card_tone="green" if running and range_control_ok else "orange",
    )
