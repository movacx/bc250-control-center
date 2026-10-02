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

The BC-250 kernel (linux-cachyos-bc250) carries its own driver for the same
regulator, ``bc250_vrm``, which exposes the rails through hwmon. It claims the
PMIC's address on every BC-250, so the daemon cannot open that bus there; when
the daemon has nothing valid, the same rails are read from that hwmon device
instead, and reported as coming from the kernel.
"""
from __future__ import annotations

import fcntl
import json
import os
import time
from pathlib import Path
from typing import Any

DEFAULT_TELEMETRY_PATH = Path("/run/apu_telemetry.json")
DEFAULT_MAX_AGE_SECONDS = 5.0
#: The BC-250 kernel's own VRM driver. It loads on every BC-250 (a DMI alias)
#: and registers an hwmon device only when a wired regulator answers.
KERNEL_VRM_MODULE = Path("/sys/module/bc250_vrm")
HWMON_ROOT = Path("/sys/class/hwmon")
KERNEL_VRM_HWMON_NAME = "bc250_vrm"
#: Each attribute read is an I2C transaction with a settling delay, and the
#: dashboard asks for the rails from more than one place per refresh.
_KERNEL_CACHE_SECONDS = 1.0
#: Held exclusively by a CPU tuning run for its whole length (see
#: ``bc250-cpu-smu-helper``). Reading the VRM driver means PMBus traffic on the
#: bus the SMU also uses, so nothing is read while a run holds it.
SMU_RUN_LOCK = Path("/run/bc250-smu-run.lock")
_kernel_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}

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


def kernel_vrm_driver_present(module: Path = KERNEL_VRM_MODULE) -> bool:
    """Whether this kernel carries the bc250_vrm driver, wired board or not.

    It instantiates a client at the PMIC's address on every BC-250, so a
    userspace program asking the kernel for that address is told it is busy.
    """
    try:
        return module.is_dir()
    except OSError:
        return False


def _kernel_vrm_device(root: Path) -> Path | None:
    try:
        entries = sorted(root.glob("hwmon*"))
    except OSError:
        return None
    for entry in entries:
        try:
            if (entry / "name").read_text(encoding="utf-8").strip() == KERNEL_VRM_HWMON_NAME:
                return entry
        except (OSError, UnicodeError):
            continue
    return None


def _attribute(device: Path, name: str, divisor: float) -> float | None:
    """One hwmon attribute in its base unit, or None when it cannot be read.

    The driver answers EIO when the regulator returns a glitch, which is a
    missing sample and not a failure of the board.
    """
    try:
        value = int((device / name).read_text(encoding="utf-8").strip())
    except (OSError, ValueError, UnicodeError):
        return None
    return None if value < 0 else value / divisor


def _smu_run_in_progress(lock: Path) -> bool:
    """Whether a CPU tuning run holds the SMU right now. Read-only: it never waits."""
    try:
        fd = os.open(lock, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except OSError:
        return False  # no run has happened this boot, or it cannot be asked
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except OSError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def _kernel_vrm_hardware(
    root: Path = HWMON_ROOT, *, run_lock: Path = SMU_RUN_LOCK
) -> dict[str, Any] | None:
    """The rails as the daemon's snapshot would show them, from the kernel driver.

    hwmon units: voltage mV, current mA, temperature m°C, power µW. Channels
    are the driver's own: in0 is the 12 V input, in1/in2 the CPU and GPU rails.
    ``None`` when the driver has no device, that is, no regulator answered.
    """
    key = str(root)
    now = time.monotonic()
    cached = _kernel_cache.get(key)
    if cached is not None and now - cached[0] < _KERNEL_CACHE_SECONDS:
        return cached[1]
    if _smu_run_in_progress(run_lock):
        return None  # not cached: the next ask, after the run, reads again
    device = _kernel_vrm_device(root)
    hardware: dict[str, Any] | None = None
    if device is not None:
        vin = _attribute(device, "in0_input", 1000.0)
        hardware = {}
        powers = []
        for index, rail in enumerate(("cpu", "gpu"), start=1):
            vout = _attribute(device, f"in{index}_input", 1000.0)
            iout = _attribute(device, f"curr{index}_input", 1000.0)
            temp = _attribute(device, f"temp{index}_input", 1000.0)
            pout = _attribute(device, f"power{index}_input", 1_000_000.0)
            valid = None not in (vin, vout, iout, temp, pout)
            hardware[rail] = {
                "valid": valid,
                "vin": vin, "vout": vout, "iout": iout, "temp": temp, "pout": pout,
            }
            if valid:
                powers.append(pout)
        hardware["total_power_valid"] = len(powers) == 2
        hardware["total_power"] = sum(powers) if len(powers) == 2 else None
    _kernel_cache[key] = (now, hardware)
    return hardware


def _has_valid_rail(hardware: Any) -> bool:
    return isinstance(hardware, dict) and any(
        isinstance(hardware.get(rail), dict) and hardware[rail].get("valid")
        for rail in ("cpu", "gpu")
    )


def leer_telemetria_vrm(
    path: Path = DEFAULT_TELEMETRY_PATH,
    *,
    max_age: float = DEFAULT_MAX_AGE_SECONDS,
    hwmon_root: Path = HWMON_ROOT,
    run_lock: Path = SMU_RUN_LOCK,
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
    if not _has_valid_rail(hardware):
        # The daemon has nothing: on the BC-250 kernel it cannot even open the
        # bus, but the kernel driver reads the same regulator itself.
        hardware = _kernel_vrm_hardware(hwmon_root, run_lock=run_lock) or hardware
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
    hwmon_root: Path = HWMON_ROOT,
    run_lock: Path = SMU_RUN_LOCK,
) -> dict[str, Any]:
    """What the rails report right now, from the daemon or else from the kernel.

    ``daemon`` says where it came from: "running" (the daemon's own snapshot),
    "kernel" (the bc250_vrm driver, when the daemon has nothing valid), or why
    there is nothing: "missing", "unreadable" or "stale".
    """
    probe = _probe_daemon(path, max_age=max_age)
    if any(rail.get("valid") for rail in probe["rails"].values()):
        return probe
    hardware = _kernel_vrm_hardware(hwmon_root, run_lock=run_lock)
    if hardware is None:
        return probe
    rails = {
        rail: {
            "valid": bool(hardware[rail]["valid"]),
            **{key: _number(hardware[rail].get(key)) for key in ("vin", "vout", "iout", "pout", "temp")},
        }
        for rail in ("cpu", "gpu")
    }
    return {
        "daemon": "kernel",
        "age_s": 0.0,
        "rails": rails,
        "total_power_w": _number(hardware.get("total_power")),
        "total_power_valid": bool(hardware.get("total_power_valid")),
    }


def _probe_daemon(
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
