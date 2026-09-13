"""Passive reader for the onlinermm/BC250-Telemetry daemon's JSON snapshot.

``apu-telemetry.service`` is an independent, optional systemd unit (part of
https://github.com/onlinermm/BC250-Telemetry) that reads CPU/GPU VRM
voltage, current, power and temperature over PMBus/I2C and writes a JSON
snapshot to ``/run/apu_telemetry.json`` every ~700 ms. Getting real PMBus
data on this bus requires a physical I2C mod described in that project's
``hardware.md``; without it the file simply never appears.

This module never starts, stops or configures that daemon. It only reads a
world-readable file that may or may not exist, matching the "telemetría
rápida no debe iniciar servicios" boundary in docs/ARQUITECTURA_MVC.md.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

DEFAULT_TELEMETRY_PATH = Path("/run/apu_telemetry.json")
DEFAULT_MAX_AGE_SECONDS = 5.0

_EMPTY_RESULT: dict[str, float | None] = {
    "vrm_cpu_temperature_c": None,
    "vrm_gpu_temperature_c": None,
}


def leer_telemetria_vrm(
    path: Path = DEFAULT_TELEMETRY_PATH,
    *,
    max_age: float = DEFAULT_MAX_AGE_SECONDS,
) -> dict[str, float | None]:
    """Return CPU/GPU VRM temperature reported by the external telemetry daemon.

    Every field is ``None`` when the daemon is not installed, not running,
    reporting a stale sample, or the snapshot is unreadable/malformed. This
    function never raises: a missing physical I2C mod (the common case) is
    an expected, silent "not detected", not an error.
    """
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return dict(_EMPTY_RESULT)
    if time.time() - mtime > max_age:
        return dict(_EMPTY_RESULT)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(_EMPTY_RESULT)

    hardware = payload.get("hardware") if isinstance(payload, dict) else None
    if not isinstance(hardware, dict):
        return dict(_EMPTY_RESULT)

    return {
        "vrm_cpu_temperature_c": _rail_temperature(hardware.get("cpu")),
        "vrm_gpu_temperature_c": _rail_temperature(hardware.get("gpu")),
    }


def _rail_temperature(rail: Any) -> float | None:
    if not isinstance(rail, dict) or not rail.get("valid"):
        return None
    try:
        return float(rail["temp"])
    except (KeyError, TypeError, ValueError):
        return None
