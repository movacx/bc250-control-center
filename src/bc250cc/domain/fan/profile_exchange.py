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
MAX_DOCUMENT_BYTES = 64 * 1024


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
