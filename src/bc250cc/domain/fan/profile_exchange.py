"""Fan profiles as a file, and as Decky Quick Access presets.

The Fans page keeps three named speeds and one curve. Exported, they become
a small JSON document a user can keep, move to another board or share;
imported, the same document is checked field by field before anything is
kept, and nothing in it ever reaches the fan by itself — the user still
applies a profile or turns the curve on.

For Decky the three speeds are published under its own preset keys, so its
Quiet/Balanced/Boost buttons carry the names and speeds chosen here.
"""

from __future__ import annotations

from copy import deepcopy

from bc250cc.domain.fan import channels as channel_model
from bc250cc.domain.fan import engine
from bc250cc.domain.fan.persistence import (
    bounded_int,
    normalize_fan_curve,
    validate_fan_curve_points,
)

DOCUMENT_KIND = "bc250-fan-profiles"
DOCUMENT_SCHEMA = 1
#: The Fans page's three profile slots, by the key each is saved under.
PROFILE_KEYS = ("quiet", "balanced", "maximum")
#: Which Decky preset each slot is published as.
DECKY_PRESET_FOR = {"quiet": "quiet", "balanced": "balanced", "maximum": "boost"}
#: Decky never offers a speed outside what its own slider allows.
DECKY_MIN_PERCENT = 20
DECKY_MAX_PERCENT = 100
MAX_NAME_LENGTH = 24
#: A profile file is a few hundred bytes; anything far larger is not one.
MAX_DOCUMENT_BYTES = 256 * 1024


def channel_profiles_document(profiles: list[dict], config: dict) -> dict:
    """Export every channel and named mode, keeping the v1 speed slots too."""
    document = fan_profiles_document(profiles)
    document.update({
        "schema": 2,
        "channels": channel_model.normalize_fan_channels(config.get("fan_channels")),
        "labels": channel_model.normalize_fan_labels(config.get("fan_channel_labels")),
        "modes": channel_model.normalize_fan_modes(config.get("fan_modes")),
        "active_mode": str(config.get("fan_active_mode") or ""),
    })
    return document


def parse_channel_profiles_document(payload: object) -> dict:
    """Validate the entire bundle before persistence; never activate a fan.

    v1's optional curve becomes an importable snapshot rather than disappearing.
    The caller stores snapshots as named modes; active channels stay unchanged.
    """
    if not isinstance(payload, dict) or payload.get("kind") != DOCUMENT_KIND:
        raise ValueError("This file is not a BC250 fan profile export.")
    if type(payload.get("schema")) is not int or payload["schema"] not in (1, 2):
        raise ValueError("This fan profile file was made by a different version.")
    legacy = {**payload, "schema": 1}
    profiles, curve = parse_fan_profiles_document(legacy)
    if payload["schema"] == 1:
        channels = {}
        if curve:
            channels = engine.validate_policy({"schema": 2, "channels": {
                str(curve["pwm"]): {"mode": "curve", "source": "hottest", "points": [
                    [p["temperature"], p["speed"]] for p in curve["points"]
                ]},
            }})["channels"]
        return {"profiles": profiles, "channels": channels, "labels": {}, "modes": [], "active_mode": ""}

    def validate_channels(raw: object) -> dict:
        if not isinstance(raw, dict):
            raise ValueError("Invalid fan channels")
        if not raw:
            return {}
        return engine.validate_policy({"schema": 2, "channels": raw})["channels"]

    channels = validate_channels(payload.get("channels", {}))
    raw_modes = payload.get("modes", [])
    if not isinstance(raw_modes, list) or len(raw_modes) > channel_model.MAX_MODES:
        raise ValueError("Invalid fan profiles")
    modes = []
    seen = set()
    reserved = {s.casefold() for s in channel_model.BUILTIN_MODE_NAMES.values()}
    for raw in raw_modes:
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
            raise ValueError("Invalid fan profiles")
        name = " ".join(raw["name"].split())
        if not name or len(name) > channel_model.MODE_NAME_MAX_LENGTH or name.casefold() in seen:
            raise ValueError("Invalid fan profiles")
        if name.casefold() in reserved:
            raise ValueError("Reserved profile name")
        seen.add(name.casefold())
        value = validate_channels(raw.get("channels"))
        if not value:
            raise ValueError("This fan mode has no valid channel.")
        modes.append({"name": name, "channels": value})
    labels = payload.get("labels", {})
    if not isinstance(labels, dict) or any(
        not isinstance(value, str) or len(value) > channel_model.LABEL_MAX_LENGTH
        or key not in {str(pwm) for pwm in range(1, engine.PWM_MAX + 1)}
        for key, value in labels.items()
    ):
        raise ValueError("Invalid fan labels")
    return {"profiles": profiles, "channels": channels, "labels": deepcopy(labels),
            "modes": modes, "active_mode": str(payload.get("active_mode") or "")}


def imported_profile_updates(config: dict, bundle: dict, *, snapshot_name: str) -> dict:
    """Merge saved profiles atomically, keeping current hardware policy intact."""
    modes = channel_model.normalize_fan_modes(config.get("fan_modes"))
    incoming = deepcopy(bundle.get("modes") or [])
    channels = bundle.get("channels") or {}
    if channels and not any(m["channels"] == channels for m in modes + incoming):
        names = {m["name"].casefold() for m in modes + incoming}
        name = snapshot_name
        index = 2
        while name.casefold() in names:
            name = f"{snapshot_name[:25]} {index}"
            index += 1
        incoming.append({"name": name, "channels": deepcopy(channels)})
    for mode in incoming:
        modes = [m for m in modes if m["name"].casefold() != mode["name"].casefold()]
        modes.append(mode)
    if len(modes) > channel_model.MAX_MODES:
        raise ValueError(f"At most {channel_model.MAX_MODES} fan modes can be saved.")
    return {"fan_modes": modes, "fan_channel_labels": {
        **channel_model.normalize_fan_labels(config.get("fan_channel_labels")),
        **(bundle.get("labels") or {}),
    }}


def fan_profiles_document(profiles: list[dict], curve: dict | None = None) -> dict:
    """The exported form of the three profiles and, if given, the curve."""
    document: dict = {
        "kind": DOCUMENT_KIND,
        "schema": DOCUMENT_SCHEMA,
        "profiles": [
            {
                "key": str(entry["key"]),
                "name": str(entry["name"]),
                "percent": bounded_int(entry.get("percent"), 70, 0, 100),
            }
            for entry in profiles
            if isinstance(entry, dict) and entry.get("key") in PROFILE_KEYS
        ],
    }
    if isinstance(curve, dict):
        normalized = normalize_fan_curve(curve)
        document["curve"] = {
            "pwm": normalized["pwm"],
            "points": [
                [int(point["temperature"]), int(point["speed"])]
                for point in normalized.get("points") or []
            ],
        }
    return document


def parse_fan_profiles_document(payload: object) -> tuple[list[dict], dict | None]:
    """Profiles and curve from an imported document, or ``ValueError``.

    Unknown slots are an error rather than ignored: a file from something
    else must not half-import. The curve is optional; when present it must
    be a valid one, and it comes back switched off.
    """
    if not isinstance(payload, dict) or payload.get("kind") != DOCUMENT_KIND:
        raise ValueError("This file is not a BC250 fan profile export.")
    if payload.get("schema") != DOCUMENT_SCHEMA:
        raise ValueError("This fan profile file was made by a different version.")
    entries = payload.get("profiles")
    if not isinstance(entries, list) or not entries:
        raise ValueError("The file holds no fan profiles.")
    profiles: list[dict] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("A fan profile in the file is not valid.")
        key = entry.get("key")
        if key not in PROFILE_KEYS or key in seen:
            raise ValueError("The file names a fan profile this version does not have.")
        seen.add(key)
        name = str(entry.get("name") or "").strip()
        if not name or len(name) > MAX_NAME_LENGTH:
            raise ValueError(f"Fan profile names must be 1-{MAX_NAME_LENGTH} characters.")
        percent = entry.get("percent")
        if isinstance(percent, bool) or not isinstance(percent, int) or not 0 <= percent <= 100:
            raise ValueError("Fan profile speeds must be whole numbers from 0 to 100 %.")
        profiles.append({"key": key, "name": name, "percent": percent})

    curve = None
    raw_curve = payload.get("curve")
    if raw_curve is not None:
        if not isinstance(raw_curve, dict):
            raise ValueError("The fan curve in the file is not valid.")
        raw_points = raw_curve.get("points")
        try:
            points = [(int(temperature), int(speed)) for temperature, speed in raw_points]
        except (TypeError, ValueError):
            raise ValueError("The fan curve in the file is not valid.") from None
        valid, reason = validate_fan_curve_points(points)
        if not valid:
            raise ValueError(reason or "The fan curve in the file is not valid.")
        curve = normalize_fan_curve({
            "enabled": False,
            "pwm": raw_curve.get("pwm"),
            "points": [{"temperature": t, "speed": s} for t, s in points],
        })
    return profiles, curve


def decky_fan_profiles(profiles: list[dict]) -> list[dict]:
    """The three profiles under Decky's preset keys, within its speed range."""
    published: list[dict] = []
    for entry in profiles:
        if not isinstance(entry, dict):
            continue
        preset = DECKY_PRESET_FOR.get(str(entry.get("key")))
        name = str(entry.get("name") or "").strip()[:40]
        if preset is None or not name:
            continue
        published.append({
            "key": preset,
            "name": name,
            "percent": bounded_int(
                entry.get("percent"), 60, DECKY_MIN_PERCENT, DECKY_MAX_PERCENT
            ),
        })
    return published


def decky_fan_raised(profiles: list[dict]) -> list[tuple[str, int, int]]:
    """(name, speed, Decky's speed) for each profile Decky would run faster.

    Decky's slider starts at its floor, so a slower profile is published at
    the floor; the user is told rather than finding out in Game Mode.
    """
    raised: list[tuple[str, int, int]] = []
    for entry in profiles:
        if not isinstance(entry, dict) or str(entry.get("key")) not in DECKY_PRESET_FOR:
            continue
        percent = bounded_int(entry.get("percent"), 60, 0, DECKY_MAX_PERCENT)
        if percent < DECKY_MIN_PERCENT:
            raised.append((str(entry.get("name") or ""), percent, DECKY_MIN_PERCENT))
    return raised
