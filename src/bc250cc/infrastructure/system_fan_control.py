"""Unprivileged view of the root system fan control service (GitHub #15).

The service itself lives in ``bc250-fan-pwm-helper --control-loop`` and runs as
root from boot. Everything here only reads the world-readable files it leaves
behind, so the desktop daemon and the Fans page can tell whether the fan is
already owned without opening a polkit prompt to ask.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from bc250cc.domain.fan.persistence import (
    CUSTOM_FAN_PRESET,
    DEFAULT_CRITICAL_TEMPERATURES_C,
    FAN_PRESET_VALUES,
    bounded_float,
    bounded_int,
    normalize_fan_curve,
    normalize_fan_preset,
    safe_bool,
)

POLICY_FILE = Path("/var/lib/bc250-control-center/fan-policy.json")
STATUS_FILE = Path("/run/bc250-control-center/fan-control.json")
OVERRIDE_FILE = Path("/run/bc250-control-center/fan-override.json")
UNIT_WANTS = Path(
    "/etc/systemd/system/multi-user.target.wants/bc250-fan-control.service"
)
OPENRC_LINK = Path("/etc/runlevels/default/bc250-fan-control")
POLICY_SCHEMA = 1
HEARTBEAT_STALE_SECONDS = 15.0
_MAX_FILE_BYTES = 8192
_SENSORS = ("gpu", "cpu", "vrm", "board")


def policy_digest(policy: dict) -> str:
    """Same digest the root helper reports after ``POLICY``."""
    encoded = json.dumps(policy, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _read_json(path: Path) -> dict:
    try:
        if path.stat().st_size > _MAX_FILE_BYTES:
            return {}
        with path.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def service_enabled() -> bool:
    try:
        return UNIT_WANTS.is_symlink() or UNIT_WANTS.exists() or OPENRC_LINK.exists()
    except OSError:
        return False


def read_system_fan_control(*, now: float | None = None) -> dict:
    """Return what the service is doing, from files any user may read."""
    enabled = service_enabled()
    policy = _read_json(POLICY_FILE)
    status = _read_json(STATUS_FILE)
    current = time.time() if now is None else float(now)
    try:
        heartbeat = float(status.get("heartbeat") or 0.0)
    except (TypeError, ValueError):
        heartbeat = 0.0
    running = bool(status) and 0.0 <= current - heartbeat <= HEARTBEAT_STALE_SECONDS
    state = str(status.get("state") or "") if running else ""
    if not state:
        state = "stopped" if enabled else "off"
    return {
        "enabled": enabled,
        "running": running,
        "state": state,
        "status": status if running else {},
        "policy": policy,
        "policy_digest": policy_digest(policy) if policy else "",
        "override": bool(_read_json(OVERRIDE_FILE).get("channels")),
    }


def system_fan_control_owns_fan(snapshot: dict) -> bool:
    """True while the root service is responsible for the fan.

    Enabled with a policy is enough: during early boot the service may still
    be waiting for the NCT driver, and a desktop write at that moment is
    exactly the login-time password prompt issue #15 is about.
    """
    return bool(snapshot.get("enabled") and snapshot.get("policy"))


def build_system_fan_policy(
    config: dict, *, manual: tuple[int, int] | None = None
) -> dict | None:
    """Translate the desktop configuration into the root service's policy.

    The saved curve wins, then a named preset, then an explicit manual duty.
    ``None`` means there is nothing to follow and the service should let the
    firmware drive the fan.
    """
    settings = config if isinstance(config, dict) else {}
    curve = normalize_fan_curve(settings.get("fan_curve"))
    preset = normalize_fan_preset(settings.get("fan_preset"))
    if safe_bool(curve.get("enabled")):
        policy: dict = {
            "schema": POLICY_SCHEMA,
            "mode": "curve",
            "pwm": bounded_int(curve.get("pwm"), 2, 1, 12),
            "points": [
                [int(point["temperature"]), int(point["speed"])]
                for point in curve.get("points") or []
            ],
        }
    elif safe_bool(preset.get("enabled")) and preset.get("preset") == CUSTOM_FAN_PRESET:
        # A slider value has no tier the root helper knows: it follows it
        # as a fixed duty instead.
        policy = {
            "schema": POLICY_SCHEMA,
            "mode": "fixed",
            "pwm": bounded_int(preset.get("pwm"), 2, 1, 12),
            "percent": bounded_int(preset.get("percent"), 70, 0, 100),
            "preset": "",
        }
    elif safe_bool(preset.get("enabled")) and preset.get("preset") in FAN_PRESET_VALUES:
        policy = {
            "schema": POLICY_SCHEMA,
            "mode": "preset",
            "pwm": bounded_int(preset.get("pwm"), 2, 1, 12),
            "percent": bounded_int(preset.get("percent"), 70, 0, 100),
            "preset": str(preset.get("preset")),
        }
    elif manual is not None:
        channel, percent = manual
        policy = {
            "schema": POLICY_SCHEMA,
            "mode": "fixed",
            "pwm": bounded_int(channel, 2, 1, 12),
            "percent": bounded_int(percent, 70, 0, 100),
            "preset": "",
        }
    else:
        return None
    critical = settings.get("fan_daemon_critical_temperatures_c")
    critical = critical if isinstance(critical, dict) else {}
    offsets = settings.get("fan_daemon_sensor_offsets_c")
    offsets = offsets if isinstance(offsets, dict) else {}
    policy.update({
        "failsafe_percent": bounded_int(settings.get("fan_daemon_failsafe_percent"), 100, 40, 100),
        "hysteresis_c": bounded_float(settings.get("fan_daemon_hysteresis_c"), 1.0, 0, 10),
        "deadband_percent": bounded_int(settings.get("fan_daemon_duty_deadband_percent"), 2, 0, 20),
        "max_down_step_percent": bounded_int(
            settings.get("fan_daemon_max_down_step_percent"), 10, 1, 100
        ),
        "sensor_timeout_seconds": bounded_float(
            settings.get("fan_daemon_sensor_timeout_seconds"), 15, 3, 300
        ),
        "critical_c": {
            sensor: bounded_float(
                critical.get(sensor), DEFAULT_CRITICAL_TEMPERATURES_C[sensor], 50, 125
            )
            for sensor in _SENSORS
        },
        "offsets_c": {
            sensor: bounded_float(offsets.get(sensor), 0, -30, 30) for sensor in _SENSORS
        },
    })
    return policy
