"""Passive reader for the onlinermm/BC250-Telemetry daemon's JSON snapshot.

``apu-telemetry.service`` is an independent, optional systemd unit (part of
https://github.com/onlinermm/BC250-Telemetry) that reads CPU/GPU VRM
voltage, current, power and temperature over PMBus/I2C and writes a JSON
snapshot to ``/run/apu_telemetry.json`` every ~700 ms. Getting real PMBus
data on this bus requires a physical I2C mod described in that project's
``hardware.md``; without it the file simply never appears.

The board has **two** VRMs, one per rail, and the PMIC reports far more than
temperature: input voltage, per-rail output voltage, current and power, and
four status bits that fire before anything is damaged. Reading only the two
temperatures threw the rest away, so this module now returns the whole
snapshot and lets the layers above decide what to show.

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

#: Status bits the PMIC raises on its own. A warning is the rail asking for
#: attention; a fault is the rail already outside its limits.
RAIL_ALERTS = (
    "iout_warning",
    "iout_fault",
    "temp_warning",
    "temp_fault",
)

_RAIL_MEASUREMENTS = (
    ("temperature_c", "temp"),
    ("voltage_v", "vout"),
    ("current_a", "iout"),
    ("power_w", "pout"),
)


def _empty_result() -> dict[str, Any]:
    empty: dict[str, Any] = {
        "vrm_available": False,
        "vrm_input_voltage_v": None,
        "vrm_total_power_w": None,
        "vrm_alerts": (),
    }
    for rail in ("cpu", "gpu"):
        for field, _source in _RAIL_MEASUREMENTS:
            empty[f"vrm_{rail}_{field}"] = None
    return empty


def leer_telemetria_vrm(
    path: Path = DEFAULT_TELEMETRY_PATH,
    *,
    max_age: float = DEFAULT_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    """Return the CPU/GPU VRM rails reported by the external telemetry daemon.

    Every measurement is ``None`` when the daemon is not installed, not
    running, reporting a stale sample, or the snapshot is unreadable. This
    function never raises: a missing physical I2C mod (the common case) is an
    expected, silent "not detected", not an error.
    """
    result = _empty_result()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return result
    if time.time() - mtime > max_age:
        return result

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return result

    hardware = payload.get("hardware") if isinstance(payload, dict) else None
    if not isinstance(hardware, dict):
        return result

    alerts: list[str] = []
    input_voltages: list[float] = []
    for rail in ("cpu", "gpu"):
        data = hardware.get(rail)
        if not isinstance(data, dict) or not data.get("valid"):
            continue
        for field, source in _RAIL_MEASUREMENTS:
            result[f"vrm_{rail}_{field}"] = _number(data.get(source))
        # Both rails are fed from the same 12 V input; the daemon repeats it
        # per rail, so one value stands for the board.
        inbound = _number(data.get("vin"))
        if inbound is not None:
            input_voltages.append(inbound)
        alerts.extend(f"{rail}_{alert}" for alert in RAIL_ALERTS if data.get(alert))

    result["vrm_input_voltage_v"] = max(input_voltages) if input_voltages else None
    if hardware.get("total_power_valid"):
        result["vrm_total_power_w"] = _number(hardware.get("total_power"))
    result["vrm_alerts"] = tuple(alerts)
    result["vrm_available"] = any(
        result[f"vrm_{rail}_temperature_c"] is not None for rail in ("cpu", "gpu")
    )
    return result


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    # The daemon writes -1 for "this sensor did not answer".
    return None if number != number or number < 0 else number
