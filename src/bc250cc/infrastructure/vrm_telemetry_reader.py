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

The same snapshot carries a ``memory`` object from the project's optional
GDDR6 collector (``bc250-memory.service``). When that collector is running it
owns the SMU mailbox the memory temperatures are read through, so its
published reading is the one to show: a second sampler on that mailbox is
what used to hang the board.

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

#: The BC-250 carries eight GDDR6 devices; JEDEC MR3 temperature codes run
#: 0..80, and 80 means "at least 120 °C".
MEMORY_CHIP_COUNT = 8
MEMORY_CODE_MAX = 80
#: The collector is running but has no valid reading to publish yet.
_MEMORY_WAITING = frozenset({"starting", "invalid_reading"})

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
    payload = _fresh_snapshot(path, max_age)
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


def sondear_telemetria_vrm(
    path: Path = DEFAULT_TELEMETRY_PATH,
    *,
    max_age: float = DEFAULT_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    """What the daemon reports about the rails, checked or not.

    :func:`leer_telemetria_vrm` keeps only fresh, valid rails: the right
    answer for the rest of the interface, and useless while someone is
    soldering the I2C mod and wants to see what the daemon actually gets.
    This says whether the daemon is publishing, how old its snapshot is, and
    every rail with the daemon's own ``valid`` flag beside its numbers.

    ``daemon`` is "missing" (no snapshot), "unreadable", "stale" (older than
    ``max_age``) or "running". Never raises.
    """
    probe: dict[str, Any] = {
        "daemon": "missing",
        "age_s": None,
        "rails": {},
        "total_power_w": None,
        "total_power_valid": False,
    }
    try:
        age = max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return probe
    probe["age_s"] = round(age, 1)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        probe["daemon"] = "unreadable"
        return probe
    hardware = payload.get("hardware") if isinstance(payload, dict) else None
    if not isinstance(hardware, dict):
        probe["daemon"] = "unreadable"
        return probe
    probe["daemon"] = "stale" if age > max_age else "running"
    rails: dict[str, dict[str, Any]] = {}
    for rail in ("cpu", "gpu"):
        data = hardware.get(rail)
        if not isinstance(data, dict):
            continue
        rails[rail] = {
            "valid": bool(data.get("valid")),
            **{source: _number(data.get(source)) for source in ("vin", "vout", "iout", "pout", "temp")},
        }
    probe["rails"] = rails
    probe["total_power_w"] = _number(hardware.get("total_power"))
    probe["total_power_valid"] = bool(hardware.get("total_power_valid"))
    return probe


def leer_memoria_telemetria(
    path: Path = DEFAULT_TELEMETRY_PATH,
    *,
    max_age: float = DEFAULT_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    """What BC250-Telemetry's optional GDDR6 collector last published.

    ``state`` is ``""`` when that collector is not running (or its daemon is
    not publishing), ``"active"`` with the eight readings, ``"waiting"`` while
    it runs without a valid reading yet, and ``"stale"`` when it stopped
    updating, which can mean it is stuck inside an SMU operation. Never
    raises, for the same reason as :func:`leer_telemetria_vrm`.
    """
    result: dict[str, Any] = {
        "state": "",
        "status": "",
        "chips": [],
        "average_c": None,
        "hotspot_c": None,
        "hotspot_chip": None,
    }
    payload = _fresh_snapshot(path, max_age)
    memory = payload.get("memory") if isinstance(payload, dict) else None
    if not isinstance(memory, dict):
        return result
    status = str(memory.get("status") or "")
    result["status"] = status
    chips = _memory_chips(memory)
    if status == "ok" and chips:
        temperatures = [chip["temperature_c"] for chip in chips]
        hotspot = max(temperatures)
        result.update(
            state="active",
            chips=chips,
            average_c=sum(temperatures) / len(temperatures),
            hotspot_c=hotspot,
            hotspot_chip=temperatures.index(hotspot),
        )
    elif status == "ok" or status in _MEMORY_WAITING:
        result["state"] = "waiting"
    elif status == "stale":
        result["state"] = "stale"
    return result


def _memory_chips(memory: dict[str, Any]) -> list[dict[str, Any]]:
    """The eight readings from the raw MR3 words, or nothing at all.

    One invalid word invalidates the sample, as it does for the collector.
    """
    raw = memory.get("raw")
    if memory.get("valid") is not True or not isinstance(raw, list):
        return []
    if len(raw) != MEMORY_CHIP_COUNT:
        return []
    chips: list[dict[str, Any]] = []
    for index, word in enumerate(raw):
        if type(word) is not int or not 0 <= word <= 0xFFFFFFFF:
            return []
        code = word & 0xFF
        if code > MEMORY_CODE_MAX:
            return []
        chips.append(
            {"chip": index, "raw": word, "code": code, "temperature_c": float(code * 2 - 40)}
        )
    return chips


def _fresh_snapshot(path: Path, max_age: float) -> Any:
    """The daemon's snapshot, or ``None`` when it is missing, old or unreadable."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    if time.time() - mtime > max_age:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    # The daemon writes -1 for "this sensor did not answer".
    return None if number != number or number < 0 else number
