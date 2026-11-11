"""Per-channel fan settings and named modes, as the desktop saves them.

Config keys (all optional, in the local desktop config):

``fan_channels``
    ``{"<pwm>": <engine channel>}``: the active setting of every channel the
    user configured. Each entry is a schema 2 channel exactly as
    :func:`bc250cc.domain.fan.engine.validate_policy` accepts it.
``fan_channel_labels``
    ``{"<pwm>": "Front intake"}``: names the user gave the headers. A label
    never changes which channel is driven.
``fan_modes``
    ``[{"name": "Quiet", "channels": {...}}]``: named snapshots of
    ``fan_channels``. Applying one **replaces** the active set: a channel the
    mode does not mention goes back to the firmware, it never reappears from
    an older setting (debate round 2).
``fan_active_mode``
    The name of the mode last applied, or ``""`` once a channel was edited.

Pure functions only; persistence and the root policy sync live elsewhere.
"""

from __future__ import annotations

from copy import deepcopy

from bc250cc.domain.fan import engine

LABEL_MAX_LENGTH = 40
MODE_NAME_MAX_LENGTH = 32
MAX_MODES = 12

#: Curves for the built-in modes, by the sensor the BC-250 is limited by
#: (``hottest``: GPU edge, Tctl or the regulator, whichever is closest).
BUILTIN_MODE_CURVES = {
    "quiet": [[40, 20], [60, 35], [75, 60], [85, 100]],
    "balanced": [[40, 30], [60, 50], [72, 75], [82, 100]],
    "performance": [[35, 45], [55, 65], [68, 90], [78, 100]],
}
BUILTIN_MODE_NAMES = {"quiet": "Quiet", "balanced": "Balanced", "performance": "Performance"}


def _valid_channel(pwm: int, entry: object) -> dict | None:
    if not isinstance(entry, dict):
        return None
    try:
        policy = engine.validate_policy({"schema": 2, "channels": {str(pwm): entry}})
    except ValueError:
        return None
    return policy["channels"][str(pwm)]


def _pwm(key: object) -> int | None:
    try:
        pwm = int(str(key))
    except ValueError:
        return None
    return pwm if engine.PWM_MIN <= pwm <= engine.PWM_MAX else None


def normalize_fan_channels(value: object) -> dict[str, dict]:
    """Every valid channel entry, normalized; invalid ones are dropped one by
    one, so a broken entry never takes the others back to the firmware."""
    channels: dict[str, dict] = {}
    if not isinstance(value, dict):
        return channels
    for key, entry in value.items():
        pwm = _pwm(key)
        if pwm is None:
            continue
        channel = _valid_channel(pwm, entry)
        if channel is not None:
            channels[str(pwm)] = channel
    return dict(sorted(channels.items(), key=lambda item: int(item[0])))


def normalize_fan_labels(value: object) -> dict[str, str]:
    labels: dict[str, str] = {}
    if not isinstance(value, dict):
        return labels
    for key, label in value.items():
        pwm = _pwm(key)
        if pwm is None or not isinstance(label, str):
            continue
        text = " ".join(label.split())[:LABEL_MAX_LENGTH]
        if text:
            labels[str(pwm)] = text
    return labels


def normalize_fan_modes(value: object) -> list[dict]:
    modes: list[dict] = []
    seen: set[str] = set()
    if not isinstance(value, list):
        return modes
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        name = " ".join(item["name"].split())[:MODE_NAME_MAX_LENGTH]
        if not name or name.casefold() in seen:
            continue
        channels = normalize_fan_channels(item.get("channels"))
        if not channels:
            continue
        seen.add(name.casefold())
        modes.append({"name": name, "channels": channels})
        if len(modes) == MAX_MODES:
            break
    return modes


def legacy_channels(config: dict) -> dict[str, dict]:
    """The v1 single curve / preset as ``fan_channels`` entries."""
    from bc250cc.domain.fan.persistence import (
        CUSTOM_FAN_PRESET,
        normalize_fan_curve,
        normalize_fan_preset,
        safe_bool,
    )

    curve = normalize_fan_curve(config.get("fan_curve"))
    preset = normalize_fan_preset(config.get("fan_preset"))
    if safe_bool(curve.get("enabled")):
        pwm = int(curve["pwm"])
        entry = {
            "mode": "curve", "source": "hottest",
            "points": [[int(p["temperature"]), int(p["speed"])] for p in curve["points"]],
        }
    elif safe_bool(preset.get("enabled")):
        pwm = int(preset["pwm"])
        named = preset.get("preset") if preset.get("preset") != CUSTOM_FAN_PRESET else ""
        entry = {"mode": "fixed", "percent": int(preset["percent"]), "preset": named or ""}
    else:
        return {}
    channel = _valid_channel(pwm, entry)
    return {str(pwm): channel} if channel is not None else {}


def migrate_legacy_config(config: dict) -> dict:
    """Config updates that move a v1 curve/preset into ``fan_channels`` once.

    The v1 keys are switched off afterwards, so the legacy merge in
    ``build_system_fan_policy`` can never bring an omitted channel back.
    Returns ``{}`` when there is nothing to migrate.
    """
    if normalize_fan_channels(config.get("fan_channels")):
        return {}
    migrated = legacy_channels(config)
    if not migrated:
        return {}
    curve = dict(config.get("fan_curve") or {})
    preset = dict(config.get("fan_preset") or {})
    curve["enabled"] = False
    preset["enabled"] = False
    return {"fan_channels": migrated, "fan_curve": curve, "fan_preset": preset}


def set_channel(config: dict, pwm: int, entry: dict | None) -> dict:
    """Config updates for one channel edited on the channel board.

    ``entry=None`` (or mode ``firmware``) hands the channel back. Raises
    ValueError for an entry the engine refuses; the user sees why.
    """
    if _pwm(pwm) is None:
        raise ValueError(f"PWM channels go from {engine.PWM_MIN} to {engine.PWM_MAX}.")
    channels = normalize_fan_channels(config.get("fan_channels"))
    if not channels:
        channels = legacy_channels(config)
    if entry is None or entry.get("mode") == "firmware":
        channels.pop(str(pwm), None)
    else:
        engine.validate_policy({"schema": 2, "channels": {str(pwm): entry}})
        channels[str(pwm)] = _valid_channel(pwm, entry)
    updates = {
        "fan_channels": dict(sorted(channels.items(), key=lambda item: int(item[0]))),
        "fan_active_mode": "",
    }
    for key in ("fan_curve", "fan_preset"):
        legacy = dict(config.get(key) or {})
        if legacy.get("enabled"):
            legacy["enabled"] = False
            updates[key] = legacy
    return updates


def builtin_mode(name: str, config: dict, targets=()) -> dict:
    """A built-in mode for the channels the user already drives.

    Fans follow the mode's curve on ``hottest``; a pump keeps its own setting
    (a quiet mode must never slow an AIO pump). When no channel is configured
    yet (every header on Firmware), the mode goes to ``targets``: the headers
    the caller sees a fan turning on, or the one selected. A pump is never
    among them: it only becomes one when the user says so.
    """
    if name not in BUILTIN_MODE_CURVES:
        raise ValueError(f"Unknown built-in fan mode {name!r}.")
    channels = normalize_fan_channels(config.get("fan_channels")) or legacy_channels(config)
    if not channels:
        channels = {
            str(pwm): {"mode": "firmware", "role": "fan"}
            for pwm in sorted({int(pwm) for pwm in targets})
            if engine.PWM_MIN <= int(pwm) <= engine.PWM_MAX
        }
    snapshot: dict[str, dict] = {}
    for key, channel in channels.items():
        if channel["role"] == "pump":
            snapshot[key] = deepcopy(channel)
            continue
        snapshot[key] = _valid_channel(int(key), {
            "mode": "curve", "source": "hottest", "points": BUILTIN_MODE_CURVES[name],
            "max_down_step_percent": 5 if name == "quiet" else 10,
            "hysteresis_c": 2.0 if name == "quiet" else 1.0,
        })
    return {"name": BUILTIN_MODE_NAMES[name], "channels": snapshot}


def save_mode(config: dict, name: str, *, channels: dict | None = None) -> dict:
    """Config updates that store the active channels as mode ``name``
    (replacing a mode of the same name)."""
    text = " ".join(str(name).split())[:MODE_NAME_MAX_LENGTH]
    if not text:
        raise ValueError("A fan mode needs a name.")
    if text.casefold() in {label.casefold() for label in BUILTIN_MODE_NAMES.values()}:
        raise ValueError("Reserved profile name")
    active = normalize_fan_channels(config.get("fan_channels"))
    channels = active if channels is None else normalize_fan_channels(channels)
    if not channels:
        raise ValueError("Configure at least one fan before saving a fan mode.")
    modes = [m for m in normalize_fan_modes(config.get("fan_modes")) if m["name"].casefold() != text.casefold()]
    if len(modes) >= MAX_MODES:
        raise ValueError(f"At most {MAX_MODES} fan modes can be saved.")
    modes.append({"name": text, "channels": channels})
    return {"fan_modes": modes, "fan_active_mode": text if channels == active else ""}


def delete_mode(config: dict, name: str) -> dict:
    modes = [m for m in normalize_fan_modes(config.get("fan_modes")) if m["name"] != name]
    updates: dict = {"fan_modes": modes}
    if config.get("fan_active_mode") == name:
        updates["fan_active_mode"] = ""
    return updates


def apply_mode(config: dict, mode: dict) -> dict:
    """Config updates that make ``mode`` the active set, replacing it."""
    channels = normalize_fan_channels(mode.get("channels"))
    if not channels:
        raise ValueError("This fan mode has no valid channel.")
    updates = {"fan_channels": channels, "fan_active_mode": str(mode.get("name") or "")}
    for key in ("fan_curve", "fan_preset"):
        legacy = dict(config.get(key) or {})
        if legacy.get("enabled"):
            legacy["enabled"] = False
            updates[key] = legacy
    return updates
