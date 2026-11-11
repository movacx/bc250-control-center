# Generated from src/bc250cc/domain/fan/engine.py by
# scripts/development/generate_fan_engine.py. Do not edit; a test
# byte-compares this file against the generator's output.
"""The one fan-control engine: every channel, every decision, no I/O.

This module is canon for fan control (docs/FAN_CONTROL_V2.md). The root
service (``bc250-fan-pwm-helper --control-loop``) runs a generated copy of it,
``privileged/lib/bc250_fan_engine.py``, produced by
``scripts/development/generate_fan_engine.py``; a test byte-compares the two.
The desktop imports it normally.

Rules for this file, because the copy is executed as root under
``python3 -I``:

* standard library only, and nothing from ``bc250cc``;
* no I/O and no side effect at module scope: data, dataclasses and pure
  functions;
* every input from a file is validated by :func:`validate_policy`, which
  repairs nothing. A policy that is not exactly well formed is refused and the
  caller leaves the fan to the firmware.

The caller owns the hardware: it reads temperatures and tachometers, writes
the PWM registers, verifies them and decides what "missing" means for a
sensor. The engine only answers "what duty should each channel have now".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

ENGINE_REVISION = 1

POLICY_SCHEMA = 2
SUPPORTED_POLICY_SCHEMAS = (1, 2)

PWM_MIN = 1
PWM_MAX = 12
SENSORS = ("gpu", "cpu", "vrm", "board")
SOURCES = SENSORS + ("hottest",)
MODES = ("firmware", "fixed", "curve", "mix")
ROLES = ("fan", "pump")
LEGACY_PRESETS = ("quiet", "balanced", "cooling", "maximum")

DEFAULT_CRITICAL_C = {"gpu": 95.0, "cpu": 95.0, "vrm": 105.0, "board": 90.0}

CURVE_MIN_POINTS = 2
CURVE_MAX_POINTS = 8
LEGACY_CURVE_MIN_POINTS = 3
MIX_MAX_MEMBERS = 4

#: A pump must never be stopped by a policy: an AIO without flow cooks the
#: CPU long before any fan curve notices. Below this the policy is refused.
PUMP_FLOOR_PERCENT = 30
PUMP_DEFAULT_MIN_PERCENT = 50

#: A critical reading drives every controlled channel here, whatever the
#: sensor-loss failsafe is set to, and never lowers a channel already above.
CRITICAL_PERCENT = 100
#: Once latched, the emergency holds until every sensor is this far back
#: under its limit, so a reading hovering at the limit does not flap the fans.
CRITICAL_RECOVERY_C = 5.0

#: The duty only moves once per this many seconds (critical and failsafe
#: excepted), so step limits are "per change", not "per two-second tick".
CHANGE_INTERVAL_SECONDS = 5.0
#: How long a spin-up kick holds before the curve takes over.
KICK_SECONDS = 3.0
#: Below this commanded duty a stopped tachometer is not a fault: many fans
#: legitimately stop (0 dB mode) at low PWM.
STALL_MIN_PERCENT = 25
#: A fan that reads 0 RPM this long while commanded above the minimum.
STALL_GRACE_SECONDS = 10.0
#: Highest plausible tachometer value; above it the reading is a sentinel.
RPM_MAX_PLAUSIBLE = 20000

POLICY_MAX_CHANNELS = 12

_GLOBAL_KEYS = frozenset({
    "schema", "failsafe_percent", "sensor_timeout_seconds", "critical_c",
    "offsets_c", "channels",
})
_CHANNEL_KEYS = frozenset({
    "mode", "percent", "preset", "source", "points", "mix", "role",
    "min_percent", "max_percent", "hysteresis_c", "response_delay_seconds",
    "deadband_percent", "max_up_step_percent", "max_down_step_percent",
    "start_percent", "stall_detect",
})
_MIX_MEMBER_KEYS = frozenset({"source", "points"})
_LEGACY_KEYS = frozenset({
    "schema", "mode", "pwm", "points", "percent", "preset", "failsafe_percent",
    "hysteresis_c", "deadband_percent", "max_down_step_percent",
    "sensor_timeout_seconds", "critical_c", "offsets_c",
})


# --------------------------------------------------------------- validation


def _integer(data: dict, key: str, default: int | None, low: int, high: int) -> int:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{key} must be an integer between {low} and {high}.")
    return value


def _number(data: dict, key: str, default: float | None, low: float, high: float) -> float:
    value = data.get(key, default)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not low <= value <= high
    ):
        raise ValueError(f"{key} must be a number between {low} and {high}.")
    return float(value)


def _boolean(data: dict, key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"Fan setting {key} must be true or false.")
    return value


def _sensor_map(data: dict, key: str, defaults: dict, low: float, high: float) -> dict:
    raw = data.get(key, {})
    if not isinstance(raw, dict) or not set(raw) <= set(SENSORS):
        raise ValueError(f"Fan setting {key} accepts only {', '.join(SENSORS)}.")
    return {
        sensor: _number({sensor: raw.get(sensor, defaults[sensor])}, sensor, None, low, high)
        for sensor in SENSORS
    }


def _points(raw: object, minimum: int = CURVE_MIN_POINTS) -> list[list[int]]:
    if not isinstance(raw, list) or not minimum <= len(raw) <= CURVE_MAX_POINTS:
        raise ValueError(
            f"A fan curve needs between {minimum} and {CURVE_MAX_POINTS} points."
        )
    points: list[list[int]] = []
    for point in raw:
        if not isinstance(point, list) or len(point) != 2:
            raise ValueError("Each fan curve point is [temperature, speed].")
        temperature = _integer({"t": point[0]}, "t", None, 0, 120)
        speed = _integer({"s": point[1]}, "s", None, 0, 100)
        if points and temperature <= points[-1][0]:
            raise ValueError("Fan curve temperatures must be strictly increasing.")
        points.append([temperature, speed])
    return points


def _source(data: dict) -> str:
    source = data.get("source", "hottest")
    if source not in SOURCES:
        raise ValueError(f"Fan curve source must be one of {', '.join(SOURCES)}.")
    return source


def _channel(raw: object, pwm: int) -> dict:
    if not isinstance(raw, dict):
        raise ValueError(f"Channel {pwm} must be a JSON object.")
    unknown = set(raw) - _CHANNEL_KEYS
    if unknown:
        raise ValueError(f"Unknown keys on fan channel {pwm}: {', '.join(sorted(unknown))}.")
    mode = raw.get("mode")
    if mode not in MODES:
        raise ValueError(f"Fan channel {pwm} mode must be one of {', '.join(MODES)}.")
    role = raw.get("role", "fan")
    if role not in ROLES:
        raise ValueError(f"Fan channel {pwm} role must be fan or pump.")
    channel: dict = {"mode": mode, "role": role}
    if mode == "firmware":
        return channel
    pump = role == "pump"
    floor = PUMP_FLOOR_PERCENT if pump else 0
    if mode == "fixed":
        channel["percent"] = _integer(raw, "percent", None, floor, 100)
        preset = raw.get("preset", "")
        if preset not in ("",) + LEGACY_PRESETS:
            raise ValueError("Unknown fan preset.")
        channel["preset"] = preset
    elif mode == "curve":
        channel["source"] = _source(raw)
        channel["points"] = _points(raw.get("points"))
    else:
        members = raw.get("mix")
        if not isinstance(members, list) or not 2 <= len(members) <= MIX_MAX_MEMBERS:
            raise ValueError(f"A fan mix needs between 2 and {MIX_MAX_MEMBERS} curves.")
        channel["mix"] = []
        for member in members:
            if not isinstance(member, dict) or set(member) - _MIX_MEMBER_KEYS:
                raise ValueError("Each fan mix member is {source, points}.")
            channel["mix"].append({"source": _source(member), "points": _points(member.get("points"))})
    if mode in ("curve", "mix"):
        default_min = PUMP_DEFAULT_MIN_PERCENT if pump else 0
        channel["min_percent"] = _integer(raw, "min_percent", default_min, floor, 100)
        channel["max_percent"] = _integer(raw, "max_percent", 100, channel["min_percent"], 100)
        channel["hysteresis_c"] = _number(raw, "hysteresis_c", 1.0, 0.0, 10.0)
        channel["response_delay_seconds"] = _number(raw, "response_delay_seconds", 0.0, 0.0, 30.0)
        channel["deadband_percent"] = _integer(raw, "deadband_percent", 2, 0, 20)
        channel["max_up_step_percent"] = _integer(raw, "max_up_step_percent", 100, 1, 100)
        channel["max_down_step_percent"] = _integer(raw, "max_down_step_percent", 10, 1, 100)
        channel["start_percent"] = _integer(raw, "start_percent", 0, 0, 100)
    channel["stall_detect"] = _boolean(raw, "stall_detect", True)
    return channel


def _globals(data: dict) -> dict:
    return {
        "failsafe_percent": _integer(data, "failsafe_percent", 100, 40, 100),
        "sensor_timeout_seconds": _number(data, "sensor_timeout_seconds", 15.0, 3.0, 300.0),
        "critical_c": _sensor_map(data, "critical_c", DEFAULT_CRITICAL_C, 50.0, 125.0),
        "offsets_c": _sensor_map(
            data, "offsets_c", {sensor: 0.0 for sensor in SENSORS}, -30.0, 30.0
        ),
    }


def _migrate_legacy(data: dict) -> dict:
    """A schema 1 policy (one channel) as the equivalent schema 2 policy."""
    unknown = set(data) - _LEGACY_KEYS
    if unknown:
        raise ValueError(f"Unknown fan policy keys: {', '.join(sorted(unknown))}.")
    mode = data.get("mode")
    if mode not in ("curve", "preset", "fixed"):
        raise ValueError("The fan policy mode must be curve, preset or fixed.")
    pwm = _integer(data, "pwm", None, PWM_MIN, PWM_MAX)
    if mode == "curve":
        channel: dict = {
            "mode": "curve",
            "source": "hottest",
            "points": _points(data.get("points"), LEGACY_CURVE_MIN_POINTS),
            "hysteresis_c": data.get("hysteresis_c", 1.0),
            "deadband_percent": data.get("deadband_percent", 2),
            "max_down_step_percent": data.get("max_down_step_percent", 10),
        }
    else:
        preset = data.get("preset", "")
        if mode == "preset" and preset not in LEGACY_PRESETS:
            raise ValueError("Unknown fan preset.")
        channel = {
            "mode": "fixed",
            "percent": data.get("percent"),
            "preset": preset if mode == "preset" else "",
        }
    policy = _globals(data)
    policy["schema"] = POLICY_SCHEMA
    policy["channels"] = {str(pwm): _channel(channel, pwm)}
    return policy


def validate_policy(data: object) -> dict:
    """Return a complete, normalized schema 2 policy or raise ValueError.

    Schema 1 (a single ``pwm``) is accepted and migrated, so a newer service
    keeps following a policy an older desktop wrote.
    """
    if not isinstance(data, dict):
        raise ValueError("The fan policy must be a JSON object.")
    schema = data.get("schema")
    if schema == 1:
        return _migrate_legacy(data)
    if schema != POLICY_SCHEMA:
        raise ValueError("Unsupported fan policy schema.")
    unknown = set(data) - _GLOBAL_KEYS
    if unknown:
        raise ValueError(f"Unknown fan policy keys: {', '.join(sorted(unknown))}.")
    raw_channels = data.get("channels")
    if (
        not isinstance(raw_channels, dict)
        or not 1 <= len(raw_channels) <= POLICY_MAX_CHANNELS
    ):
        raise ValueError(f"A fan policy needs between 1 and {POLICY_MAX_CHANNELS} channels.")
    channels: dict[str, dict] = {}
    for key, raw in raw_channels.items():
        if not isinstance(key, str) or not key.isdigit() or str(int(key)) != key:
            raise ValueError("Channel keys are PWM numbers written as text, like \"2\".")
        pwm = int(key)
        if not PWM_MIN <= pwm <= PWM_MAX:
            raise ValueError(f"PWM channels go from {PWM_MIN} to {PWM_MAX}.")
        channels[key] = _channel(raw, pwm)
    policy = _globals(data)
    policy["schema"] = POLICY_SCHEMA
    policy["channels"] = dict(sorted(channels.items(), key=lambda item: int(item[0])))
    return policy


def controlled_channels(policy: dict) -> list[int]:
    """Channels the policy drives (every mode except firmware)."""
    return [
        int(key) for key, channel in policy["channels"].items()
        if channel["mode"] != "firmware"
    ]


# --------------------------------------------------------------- evaluation


def interpolate(points, temperature: float) -> int:
    """The duty at ``temperature``: straight lines between neighbouring
    points, flat at the first point's duty below it and the last one's above.
    Rounds half up, like v1, so saved curves keep their exact behaviour."""
    first_temperature, first_speed = points[0]
    if temperature <= first_temperature:
        return max(0, min(100, int(first_speed)))
    for (low_t, low_s), (high_t, high_s) in zip(points, points[1:]):
        if temperature < high_t:
            span = high_t - low_t
            if span <= 0:
                return max(0, min(100, int(high_s)))
            value = low_s + (high_s - low_s) * (temperature - low_t) / span
            return max(0, min(100, math.floor(value + 0.5)))
    return max(0, min(100, int(points[-1][1])))


def clean_readings(readings: object) -> dict[str, float]:
    """Only known sensors with a plausible, finite value (0 < t <= 130 °C)."""
    clean: dict[str, float] = {}
    if not isinstance(readings, dict):
        return clean
    for sensor in SENSORS:
        value = readings.get(sensor)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        value = float(value)
        if math.isfinite(value) and 0 < value <= 130:
            clean[sensor] = value
    return clean


def critical_reading(
    policy: dict, readings: dict[str, float], *, latched: bool = False,
) -> tuple[str, float] | None:
    """The sensor furthest past its critical limit, on raw (un-offset) values.

    ``latched`` (an emergency already in force) lowers every limit by
    :data:`CRITICAL_RECOVERY_C`, so leaving the emergency needs real margin.
    """
    margin = CRITICAL_RECOVERY_C if latched else 0.0
    past = [
        (value - policy["critical_c"][sensor], value, sensor)
        for sensor, value in readings.items()
        if value >= policy["critical_c"][sensor] - margin
    ]
    if not past:
        return None
    _excess, value, sensor = max(past)
    return sensor, value


def source_temperature(
    policy: dict, readings: dict[str, float], source: str,
) -> tuple[str, float] | None:
    """The offset-corrected temperature a curve follows, and which sensor.

    ``hottest`` is taken over whatever is present; whether something it
    should include is missing is decided by the caller (``expected``).
    """
    effective = {
        sensor: value + policy["offsets_c"][sensor] for sensor, value in readings.items()
    }
    if source == "hottest":
        if not effective:
            return None
        sensor = max(effective, key=lambda name: (effective[name], name))
        return sensor, effective[sensor]
    if source not in effective:
        return None
    return source, effective[source]


@dataclass(frozen=True)
class ChannelMemory:
    """What one channel's controller remembers between ticks."""

    percent: int | None = None
    source: str = ""
    #: The duty the channel is walking toward (the last accepted curve value).
    goal_percent: int | None = None
    #: Temperature at the last accepted change; hysteresis is measured from it.
    reference_temperature: float | None = None
    changed_at: float | None = None
    pending_percent: int | None = None
    pending_since: float | None = None
    missing_since: float | None = None
    kick_until: float | None = None
    stalled_since: float | None = None
    seen_spinning: bool = False


def replace_memory(memory: ChannelMemory, **changes) -> ChannelMemory:
    """``dataclasses.replace`` for callers that only hold this module."""
    return replace(memory, **changes)


@dataclass(frozen=True)
class ChannelDecision:
    """``action`` is ``set`` (drive ``percent``), ``hold`` (leave the
    register alone this tick) or ``release`` (back to firmware)."""

    action: str
    percent: int | None
    source: str
    sensor: str = ""
    temperature: float | None = None
    reason: str = ""

    @property
    def raw(self) -> int | None:
        return None if self.percent is None else round(self.percent * 255 / 100)


_SMOOTHED = ("curve", "mix")
_RECOVERING = ("critical", "failsafe")


def _curve_target(
    channel: dict, policy: dict, readings: dict[str, float], expected: frozenset,
) -> tuple[int | None, str, float | None, bool]:
    """(duty, sensor, temperature, complete). ``complete`` is false when any
    source the channel needs is missing: a named sensor that does not answer,
    or, for ``hottest``, any sensor in ``expected`` that stopped answering.
    A lost sensor is never hidden behind a cooler one that still answers."""
    if channel["mode"] == "curve":
        members = [{"source": channel["source"], "points": channel["points"]}]
    else:
        members = channel["mix"]
    best: tuple[int, str, float] | None = None
    complete = True
    for member in members:
        found = source_temperature(policy, readings, member["source"])
        if member["source"] == "hottest" and not expected <= set(readings):
            complete = False
        if found is None:
            complete = False
            continue
        sensor, temperature = found
        duty = interpolate(member["points"], temperature)
        if best is None or duty > best[0]:
            best = (duty, sensor, temperature)
    if best is None:
        return None, "", None, False
    return best[0], best[1], best[2], complete


def _smooth(
    channel: dict, memory: ChannelMemory, target: int, temperature: float, now: float,
) -> tuple[int, ChannelMemory]:
    """Move from the current duty toward the curve.

    Two steps. Hysteresis and the response delay decide whether the curve's
    value becomes the new *goal* (measured from the temperature at which the
    current goal was accepted). The output then walks toward the goal at most
    one step per :data:`CHANGE_INTERVAL_SECONDS`, and keeps walking even when
    the temperature holds still.
    """
    previous = memory.percent
    if previous is None or memory.source not in _SMOOTHED + _RECOVERING:
        return target, replace(
            memory, goal_percent=target, reference_temperature=temperature,
            changed_at=now, pending_percent=None, pending_since=None,
        )
    # Coming back from an emergency the duty steps down at the channel's
    # pace instead of dropping from 100 % straight to the curve.
    steady = memory.source in _SMOOTHED and memory.goal_percent is not None
    goal = memory.goal_percent if steady else target
    reference = memory.reference_temperature
    if steady and target != goal and not (
        reference is not None and abs(temperature - reference) < channel["hysteresis_c"]
    ):
        delay = channel["response_delay_seconds"]
        rising = target > goal
        pending = memory.pending_percent
        same_way = pending is not None and (pending > goal) == rising
        since = memory.pending_since if same_way and memory.pending_since is not None else now
        if delay > 0 and now - since < delay:
            memory = replace(memory, pending_percent=target, pending_since=since)
        else:
            goal, reference = target, temperature
            memory = replace(memory, pending_percent=None, pending_since=None)
    elif steady:
        memory = replace(memory, pending_percent=None, pending_since=None)
    memory = replace(memory, goal_percent=goal, reference_temperature=reference)
    if not steady:
        memory = replace(memory, reference_temperature=temperature)
    if goal == previous or (
        steady and abs(goal - previous) <= channel["deadband_percent"]
        and goal not in (0, 100)
    ):
        return previous, memory
    if memory.changed_at is not None and now - memory.changed_at < CHANGE_INTERVAL_SECONDS:
        return previous, memory
    if goal > previous:
        output = min(goal, previous + channel["max_up_step_percent"])
    else:
        output = max(goal, previous - channel["max_down_step_percent"])
    return output, replace(memory, changed_at=now)


def plan_channel(
    channel: dict,
    policy: dict,
    readings: dict[str, float],
    memory: ChannelMemory,
    now: float,
    *,
    critical: tuple[str, float] | None = None,
    expected: frozenset = frozenset(),
) -> tuple[ChannelDecision, ChannelMemory]:
    """One channel, one tick. ``readings`` must come from :func:`clean_readings`.

    The returned memory is a *proposal*: the caller commits it only once the
    duty is verified on the hardware, so a failed write never becomes the
    baseline the next tick smooths from.
    """
    mode = channel["mode"]
    if mode == "firmware":
        return ChannelDecision("release", None, "firmware"), ChannelMemory()
    if critical is not None:
        sensor, value = critical
        percent = max(CRITICAL_PERCENT, memory.percent or 0)
        known = math.isfinite(value)
        reason = (
            f"{sensor.upper()} {value:.1f} C is past its critical limit" if known
            else f"{sensor.upper()} stopped answering during an emergency"
        )
        return (
            ChannelDecision("set", percent, "critical", sensor, value if known else None, reason),
            replace(memory, percent=percent, source="critical", changed_at=now,
                    missing_since=None, pending_percent=None, pending_since=None),
        )
    if mode == "fixed":
        source = f"preset:{channel['preset']}" if channel.get("preset") else "fixed"
        percent = channel["percent"]
        return (
            ChannelDecision("set", percent, source),
            replace(memory, percent=percent, source="fixed", changed_at=now,
                    missing_since=None, pending_percent=None, pending_since=None),
        )

    target, sensor, temperature, complete = _curve_target(
        channel, policy, readings, expected
    )
    if not complete:
        missing_since = memory.missing_since if memory.missing_since is not None else now
        memory = replace(memory, missing_since=missing_since)
        if now - missing_since >= policy["sensor_timeout_seconds"]:
            percent = max(policy["failsafe_percent"], memory.percent or 0)
            return (
                ChannelDecision("set", percent, "failsafe", sensor, temperature,
                                "a temperature this channel follows is missing"),
                replace(memory, percent=percent, source="failsafe", changed_at=now),
            )
        if target is None:
            return (
                ChannelDecision("hold", memory.percent, "waiting-sensor",
                                reason="waiting for the temperature this channel follows"),
                memory,
            )
        # Inside the grace period: follow what still answers, but never go
        # down while part of the picture is missing.
        if memory.percent is not None and memory.source in _SMOOTHED:
            target = max(target, memory.percent)
    else:
        memory = replace(memory, missing_since=None)

    percent, memory = _smooth(channel, memory, target, temperature, now)
    percent = max(channel["min_percent"], min(channel["max_percent"], percent))
    kick_until = memory.kick_until
    if (
        channel["start_percent"] > percent > 0
        and (memory.percent == 0 or (kick_until is not None and now < kick_until))
    ):
        kick_until = kick_until if kick_until is not None and now < kick_until else now + KICK_SECONDS
        output = channel["start_percent"]
    else:
        kick_until = None
        output = percent
    memory = replace(memory, percent=percent, source=mode, kick_until=kick_until)
    return ChannelDecision("set", output, mode, sensor, temperature), memory


def plan(
    policy: dict,
    readings: object,
    memories: dict[int, ChannelMemory],
    now: float,
    *,
    expected: object = (),
) -> tuple[dict[int, ChannelDecision], dict[int, ChannelMemory]]:
    """Every channel of ``policy`` for one tick.

    A critical reading on any sensor drives every controlled channel to
    :data:`CRITICAL_PERCENT` at once: on a single-board machine every fan
    moves air over the same heatsink. ``expected`` is the set of sensors that
    have answered before (this boot); losing one of them counts as missing.
    """
    clean = clean_readings(readings)
    latched = any(memory.source == "critical" for memory in memories.values())
    critical = critical_reading(policy, clean, latched=latched)
    wanted = frozenset(sensor for sensor in expected if sensor in SENSORS)
    if critical is None and latched and not wanted <= set(clean):
        # An emergency only ends on evidence: if a sensor that answered
        # before is gone, the one that was too hot may be the one missing.
        critical = (sorted(wanted - set(clean))[0], math.nan)
    decisions: dict[int, ChannelDecision] = {}
    updated: dict[int, ChannelMemory] = {}
    for key, channel in policy["channels"].items():
        pwm = int(key)
        decision, memory = plan_channel(
            channel, policy, clean, memories.get(pwm, ChannelMemory()), now,
            critical=critical, expected=wanted,
        )
        decisions[pwm] = decision
        updated[pwm] = memory
    return decisions, updated


def assess_stall(
    channel: dict,
    memory: ChannelMemory,
    commanded_percent: int | None,
    rpm: object,
    now: float,
) -> tuple[str, ChannelMemory]:
    """Return (fault, memory). Fault is ``""``, ``"stalled"`` or
    ``"pump-stalled"``.

    A header whose tachometer never reported a speed this boot is assumed to
    have no tach wire (a 3-pin splitter, a PWM-only fan) and is never called
    stalled; a fan commanded below :data:`STALL_MIN_PERCENT` may legitimately
    stop.
    """
    if isinstance(rpm, bool) or not isinstance(rpm, (int, float)) or not math.isfinite(rpm):
        return "", replace(memory, stalled_since=None)
    if rpm < 0 or rpm > RPM_MAX_PLAUSIBLE:
        return "", replace(memory, stalled_since=None)
    if rpm > 0:
        return "", replace(memory, stalled_since=None, seen_spinning=True)
    if (
        not channel.get("stall_detect", True)
        or not memory.seen_spinning
        or commanded_percent is None
        or commanded_percent < STALL_MIN_PERCENT
        or (memory.kick_until is not None and now < memory.kick_until)
    ):
        return "", replace(memory, stalled_since=None)
    since = memory.stalled_since if memory.stalled_since is not None else now
    memory = replace(memory, stalled_since=since)
    if now - since < STALL_GRACE_SECONDS:
        return "", memory
    return ("pump-stalled" if channel.get("role") == "pump" else "stalled"), memory
