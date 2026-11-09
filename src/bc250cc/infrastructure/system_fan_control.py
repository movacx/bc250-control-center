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

from bc250cc.domain.fan import engine
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
#: Written by the root helper when the user hands the fan to another program.
EXTERNAL_FILE = Path("/var/lib/bc250-control-center/fan-external.json")
FAN_EXTERNAL_MESSAGE = (
    "The fan is handed to another program. Take control back on the Fans page first."
)
#: Other fan controllers, by the name the kernel gives their process
#: (/proc/PID/comm, at most 15 characters).
EXTERNAL_FAN_MANAGERS = {
    "coolercontrold": "CoolerControl",
    "fancontrol": "fancontrol",
    "fan2go": "fan2go",
    "thinkfan": "thinkfan",
}
UNIT_WANTS = Path(
    "/etc/systemd/system/multi-user.target.wants/bc250-fan-control.service"
)
OPENRC_LINK = Path("/etc/runlevels/default/bc250-fan-control")
POLICY_SCHEMA = engine.POLICY_SCHEMA
HEARTBEAT_STALE_SECONDS = 15.0
#: The service rounds its heartbeat to 0.1 s, so a read right after a write
#: can see it up to 0.05 s in the future. Treating that as "not running"
#: made the Fans page flicker between Active and Stopped.
HEARTBEAT_FUTURE_TOLERANCE_SECONDS = 2.0
_MAX_FILE_BYTES = 32768
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


def fan_handed_to_external() -> bool:
    """True while the user handed the fan to another program."""
    try:
        return EXTERNAL_FILE.is_file()
    except OSError:
        return False


def running_fan_managers(proc: Path = Path("/proc")) -> list[str]:
    """Other fan controllers running now, by display name, sorted."""
    found: set[str] = set()
    try:
        entries = list(proc.iterdir())
    except OSError:
        return []
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            name = (entry / "comm").read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if name in EXTERNAL_FAN_MANAGERS:
            found.add(EXTERNAL_FAN_MANAGERS[name])
    return sorted(found)


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
    age = current - heartbeat
    running = bool(status) and (
        -HEARTBEAT_FUTURE_TOLERANCE_SECONDS <= age <= HEARTBEAT_STALE_SECONDS
    )
    state = str(status.get("state") or "") if running else ""
    if not state:
        state = "stopped" if enabled else "off"
    return {
        "enabled": enabled,
        "running": running,
        "state": state,
        "status": status if running else {},
        "policy": policy,
        "policy_digest": normalized_policy_digest(policy),
        "override": bool(_read_json(OVERRIDE_FILE).get("channels")),
        "external": fan_handed_to_external(),
    }


def system_fan_control_owns_fan(snapshot: dict) -> bool:
    """True while the root service is responsible for the fan.

    Enabled with a policy is enough: during early boot the service may still
    be waiting for the NCT driver, and a desktop write at that moment is
    exactly the login-time password prompt issue #15 is about.
    """
    return bool(snapshot.get("enabled") and snapshot.get("policy"))


def _legacy_policy(config: dict, manual: tuple[int, int] | None) -> dict | None:
    """The v1 single-channel translation of the saved curve / preset."""
    curve = normalize_fan_curve(config.get("fan_curve"))
    preset = normalize_fan_preset(config.get("fan_preset"))
    if safe_bool(curve.get("enabled")):
        policy: dict = {
            "schema": 1,
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
            "schema": 1,
            "mode": "fixed",
            "pwm": bounded_int(preset.get("pwm"), 2, 1, 12),
            "percent": bounded_int(preset.get("percent"), 70, 0, 100),
            "preset": "",
        }
    elif safe_bool(preset.get("enabled")) and preset.get("preset") in FAN_PRESET_VALUES:
        policy = {
            "schema": 1,
            "mode": "preset",
            "pwm": bounded_int(preset.get("pwm"), 2, 1, 12),
            "percent": bounded_int(preset.get("percent"), 70, 0, 100),
            "preset": str(preset.get("preset")),
        }
    elif manual is not None:
        channel, percent = manual
        policy = {
            "schema": 1,
            "mode": "fixed",
            "pwm": bounded_int(channel, 2, 1, 12),
            "percent": bounded_int(percent, 70, 0, 100),
            "preset": "",
        }
    else:
        return None
    policy.update({
        "hysteresis_c": bounded_float(config.get("fan_daemon_hysteresis_c"), 1.0, 0, 10),
        "deadband_percent": bounded_int(config.get("fan_daemon_duty_deadband_percent"), 2, 0, 20),
        "max_down_step_percent": bounded_int(
            config.get("fan_daemon_max_down_step_percent"), 10, 1, 100
        ),
    })
    return policy


def _global_settings(config: dict) -> dict:
    critical = config.get("fan_daemon_critical_temperatures_c")
    critical = critical if isinstance(critical, dict) else {}
    offsets = config.get("fan_daemon_sensor_offsets_c")
    offsets = offsets if isinstance(offsets, dict) else {}
    return {
        "failsafe_percent": bounded_int(config.get("fan_daemon_failsafe_percent"), 100, 40, 100),
        "sensor_timeout_seconds": bounded_float(
            config.get("fan_daemon_sensor_timeout_seconds"), 15, 3, 300
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
    }


def configured_channels(config: dict) -> dict[str, dict]:
    """Per-channel settings saved by the v2 Fans page (``fan_channels``).

    Each entry is validated on its own with the engine; one broken channel is
    dropped rather than taking every other channel back to the firmware.
    """
    raw = config.get("fan_channels")
    if not isinstance(raw, dict):
        return {}
    channels: dict[str, dict] = {}
    for key, value in raw.items():
        if not isinstance(value, dict):
            continue
        try:
            pwm = int(str(key))
        except ValueError:
            continue
        entry = {name: item for name, item in value.items() if name != "label"}
        try:
            engine.validate_policy({"schema": 2, "channels": {str(pwm): entry}})
        except ValueError:
            continue
        channels[str(pwm)] = entry
    return channels


def build_system_fan_policy(
    config: dict, *, manual: tuple[int, int] | None = None
) -> dict | None:
    """Translate the desktop configuration into the root service's policy.

    The result is always a normalized schema 2 policy, exactly what the root
    helper's ``validate_policy`` returns for it, so the digest the helper
    acknowledges is the digest computed here. Per-channel settings
    (``fan_channels``) set every channel; an enabled legacy curve / preset (the
    classic editor, used last) replaces its own channel. ``None`` means there
    is nothing to follow and the service should let the firmware drive the fan.
    """
    settings = config if isinstance(config, dict) else {}
    channels: dict[str, dict] = configured_channels(settings)
    legacy = _legacy_policy(settings, manual)
    if legacy is not None:
        # The classic editor is only enabled when the user just used it (the
        # channel board switches it off when it takes a channel over), so its
        # channel follows it: the newest intent wins.
        migrated = engine.validate_policy({**legacy, **_global_settings(settings)})
        channels.update(migrated["channels"])
    if not any(channel.get("mode") != "firmware" for channel in channels.values()):
        return None
    return engine.validate_policy({
        "schema": POLICY_SCHEMA, **_global_settings(settings), "channels": channels,
    })


def policy_overview(policy: dict) -> dict:
    """What a confirmation dialog says about a schema 2 policy.

    ``channels`` lists every controlled PWM; ``pwm``, ``mode``, ``points`` and
    ``percent`` describe the first one, the way the v1 single-channel dialogs
    did (``mode`` is ``curve``, ``mix``, ``preset`` or ``fixed``).
    """
    controlled = engine.controlled_channels(policy)
    overview: dict = {
        "channels": controlled,
        "channels_text": ", ".join(f"PWM {pwm}" for pwm in controlled),
        "pwm": controlled[0] if controlled else None,
        "mode": "",
        "points": 0,
        "percent": None,
        "failsafe_percent": policy.get("failsafe_percent"),
    }
    if not controlled:
        return overview
    channel = policy["channels"][str(controlled[0])]
    mode = channel["mode"]
    if mode == "fixed" and channel.get("preset"):
        mode = "preset"
    overview["mode"] = mode
    overview["points"] = len(channel.get("points") or [])
    overview["percent"] = channel.get("percent")
    return overview


#: What a root helper from before fan control v2 answers to a schema 2 policy.
#: Its validator checks unknown keys before the schema, so the real answer is
#: the first one; the second is kept for a policy without ``channels``.
LEGACY_HELPER_REFUSALS = ("Unknown fan policy keys: channels", "Unsupported fan policy schema")


def is_legacy_helper_refusal(message: object) -> bool:
    text = str(message)
    return any(marker in text for marker in LEGACY_HELPER_REFUSALS)


def downgrade_policy_to_v1(policy: dict) -> dict | None:
    """The same policy in schema 1, for a root helper older than v2.

    Only when nothing is lost: one controlled channel, following the hottest
    sensor (curve) or a fixed duty, with no v2-only setting changed from its
    default. ``None`` means the policy cannot be represented and the helper
    must be updated instead; silently following a different policy as root is
    worse than refusing.
    """
    controlled = engine.controlled_channels(policy)
    if len(controlled) != 1:
        return None
    pwm = controlled[0]
    channel = policy["channels"][str(pwm)]
    if channel["role"] != "fan" or not channel.get("stall_detect", True):
        return None
    legacy: dict = {"schema": 1, "pwm": pwm}
    if channel["mode"] == "curve":
        defaults = {
            "source": "hottest", "min_percent": 0, "max_percent": 100,
            "response_delay_seconds": 0.0, "max_up_step_percent": 100, "start_percent": 0,
        }
        if any(channel.get(key) != value for key, value in defaults.items()):
            return None
        if len(channel["points"]) < engine.LEGACY_CURVE_MIN_POINTS:
            return None
        legacy.update({
            "mode": "curve", "points": [list(point) for point in channel["points"]],
            "hysteresis_c": channel["hysteresis_c"],
            "deadband_percent": channel["deadband_percent"],
            "max_down_step_percent": channel["max_down_step_percent"],
        })
    elif channel["mode"] == "fixed":
        preset = channel.get("preset") or ""
        legacy.update({
            "mode": "preset" if preset else "fixed", "percent": channel["percent"],
            "preset": preset,
        })
    else:
        return None
    for key in ("failsafe_percent", "sensor_timeout_seconds", "critical_c", "offsets_c"):
        legacy[key] = policy[key]
    return legacy


def normalized_policy_digest(policy: object) -> str:
    """Digest of a saved policy after the engine's normalization, so a v1
    file written by an older helper compares equal to the v2 policy that
    describes the same thing."""
    if not isinstance(policy, dict) or not policy:
        return ""
    try:
        return policy_digest(engine.validate_policy(policy))
    except ValueError:
        return policy_digest(policy)
