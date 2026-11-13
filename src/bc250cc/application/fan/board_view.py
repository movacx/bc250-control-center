"""The fan channel board as every front end reads it: Qt-free, untranslated.

The desktop Fans page, the web interface and the terminal interface all show
the same rows, states and notices. The rules that decide them live here once;
each front end only translates the English source strings it gets back
(``tr`` on the desktop and the terminal, ``t`` in the web app).
"""

from __future__ import annotations

import math

from bc250cc.application.fan.channels import ChannelBoard, FanChannelsService
from bc250cc.domain.fan.headers import BC250_FAN_HEADERS
from bc250cc.infrastructure.system_fan_control import (
    downgrade_policy_to_v1,
    policy_digest,
    system_fan_control_owns_fan,
)

#: The five fan signals of a BC-250 (J4003 F1..F5 / CPU_FAN1) are always
#: listed: 0 RPM does not prove a header is empty (a stopped fan, a pump with
#: no tach wire). Other NCT channels show only once they are used.
BOARD_CHANNELS = tuple(sorted(BC250_FAN_HEADERS))
#: Below this duty a fixed speed written right now asks before it is written.
LOW_DUTY_CONFIRM_PERCENT = 30

MODE_LABELS = (("firmware", "Firmware"), ("fixed", "Fixed"), ("curve", "Curve"), ("mix", "Mix"))
ROLE_LABELS = (("fan", "Fan"), ("pump", "Pump"))
SOURCE_LABELS = (
    ("hottest", "Hottest chip"), ("gpu", "GPU"), ("cpu", "CPU"), ("vrm", "VRM"), ("board", "Board"),
)
DEFAULT_CURVE = [[40, 30], [60, 50], [72, 75], [82, 100]]

NOT_READY_TITLE = "PWM control is not ready"
READ_ONLY_NOTE = "This channel is read-only until the PWM driver is prepared."
EXTERNAL_NOTE = "The fan is handed to another program. Nothing here writes to it."


# ------------------------------------------------------------------ numbers


def as_dict(value) -> dict:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    try:
        return dict(value or {})
    except Exception:
        return {}


def integer(value, default=0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return int(default)


def finite_number(value: object) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def pwm_to_percent(value) -> int | None:
    if value is None:
        return None
    return max(0, min(100, round(integer(value) * 100 / 255)))


def percent_to_pwm(value) -> int:
    return max(0, min(255, round(integer(value) * 255 / 100)))


# ------------------------------------------------------------------- board


class _SavedConfig:
    """A config already read, for ``FanChannelsService.board()`` (read only)."""

    def __init__(self, config: dict):
        self._config = dict(config or {})

    def read_local_config(self) -> dict:
        return dict(self._config)

    def save_local_config(self, values: dict) -> dict:
        raise RuntimeError("The fan board was read from a saved copy of the config.")


def board_from_config(config: dict) -> ChannelBoard:
    """The channel board a page shows, from the config it already read."""
    return FanChannelsService(_SavedConfig(config)).board()


# ----------------------------------------------------------------- headers


def header_text(pwm: int) -> str:
    header = BC250_FAN_HEADERS.get(pwm)
    return header.header if header else f"PWM {pwm}"


def short_header(pwm: int) -> str:
    """``J4003 F1`` for a table; an editor or tooltip names it in full."""
    header = BC250_FAN_HEADERS.get(pwm)
    if header is None:
        return f"PWM {pwm}"
    return header.header.split("/")[-1].strip().replace("J4003 Fan ", "J4003 F")


def bios_number(pwm: int) -> int | None:
    header = BC250_FAN_HEADERS.get(pwm)
    return header.bios_number if header else None


# ------------------------------------------------------------------ reading


def fan_rows(fans_state: object) -> dict[int, dict]:
    """``estado_fans_bc250()`` rows by PWM number."""
    sensors = as_dict(as_dict(fans_state).get("sensores"))
    rows: dict[int, dict] = {}
    for fan in sensors.get("fans") or []:
        if isinstance(fan, dict):
            rows[integer(fan.get("index"), -1)] = fan
    return rows


def is_writable(fan: dict) -> bool:
    return bool(fan.get("pwm_writable") or fan.get("pwm_root_writable"))


def control_available(fans_state: object) -> bool:
    state = as_dict(fans_state)
    return bool(state.get("driver_control")) and any(
        is_writable(fan) for fan in fan_rows(state).values() if fan.get("pwm_path")
    )


def channel_numbers(rows: dict[int, dict], configured) -> list[int]:
    """The board's channels, in BIOS order: the five BC-250 headers, then any
    other channel with a fan turning or a saved setting."""
    configured = {int(pwm) for pwm in configured}
    numbers = set(BOARD_CHANNELS)
    for pwm, row in rows.items():
        if pwm in BOARD_CHANNELS or pwm < 1:
            continue
        if row.get("pwm_path") and (integer(row.get("rpm")) > 0 or pwm in configured):
            numbers.add(pwm)

    def order(pwm: int) -> tuple[int, int]:
        header = BC250_FAN_HEADERS.get(pwm)
        return (header.bios_number, pwm) if header else (99, pwm)

    return sorted(numbers | configured, key=order)


def service_status(snapshot: object) -> dict:
    return as_dict(as_dict(snapshot).get("status"))


def channel_status(snapshot: object, pwm: int) -> dict:
    """The root service's view of one channel. A root helper from before v2
    publishes one channel at the top level only, with its state."""
    snapshot = as_dict(snapshot)
    service = service_status(snapshot)
    channels = as_dict(service.get("channels"))
    if channels:
        return as_dict(channels.get(str(pwm)))
    if integer(service.get("pwm"), -1) != pwm:
        return {}
    return {
        "state": snapshot.get("state"),
        "percent": service.get("percent"),
        "source": service.get("source"),
        "sensor": service.get("sensor"),
        "temperature": service.get("temperature"),
    }


def row_state(mode: str, fan: dict, status: dict, *, external: bool, service_enabled: bool,
              pending: bool = False, verified: bool = False) -> tuple[str, str]:
    """``(English state, tone)`` of one channel; tones: green, blue, orange,
    red or "" (muted)."""
    fault = str(status.get("fault") or "")
    if fault == "pump-stalled":
        return "Pump stopped", "red"
    if fault == "stalled":
        return "Fan stopped", "red"
    if status.get("error"):
        return "Error", "red"
    if external:
        return "Another program", "blue"
    if not fan:
        return "Not detected", ""
    if pending:
        return "Pending", "orange"
    if mode == "firmware":
        return "BIOS", ""
    if not service_enabled:
        if mode == "fixed" and verified:
            return "Applied", "green"
        return "Saved", "orange"
    state = str(status.get("state") or "")
    if state == "active":
        source = str(status.get("source") or "")
        if source == "critical":
            return "Critical", "red"
        if source == "failsafe":
            return "Failsafe", "orange"
        return "Active", "green"
    if state == "override":
        return "Paused", "orange"
    if state == "waiting-sensor":
        return "Waiting", "blue"
    return "Stopped", "orange"


def profile_targets(rows: dict[int, dict], numbers, selected: int | None) -> list[int]:
    """Where a built-in profile goes when no channel is configured yet: the
    writable headers with a fan turning, else the selected one. A pump is
    never among them: a channel only becomes one when the user says so."""

    def writable(pwm: int) -> bool:
        fan = rows.get(pwm, {})
        return bool(fan.get("pwm_path") and is_writable(fan))

    spinning = [pwm for pwm in numbers if writable(pwm) and integer(rows[pwm].get("rpm")) > 0]
    if spinning:
        return spinning
    return [selected] if selected is not None and writable(selected) else []


def verify_pwm_result(result: object, *, pwm: int, raw: int | None = None,
                      automatic: bool = False) -> tuple[str, dict]:
    """``("", {})`` when the helper's read-back confirms the write, else an
    English template and its values. An acknowledgement without the
    promised read-back is a failure."""
    if not isinstance(result, dict):
        return "The PWM helper returned no verification result.", {}
    verified = as_dict(result.get("verified"))
    if not verified:
        detail = str(result.get("verification_error") or "").strip()
        return (detail, {}) if detail else ("The PWM change could not be verified from hwmon.", {})
    if integer(verified.get("pwm"), -1) != int(pwm):
        return ("PWM verification reported channel {actual}, expected PWM {expected}.",
                {"actual": verified.get("pwm", "--"), "expected": int(pwm)})
    if automatic:
        if integer(verified.get("enable"), -1) != 2:
            return ("PWM {pwm} did not verify firmware automatic mode (read-back: {value}).",
                    {"pwm": int(pwm), "value": verified.get("enable", "--")})
        return "", {}
    if integer(verified.get("value"), -1) != int(raw):
        return ("PWM {pwm} read-back was {actual}, expected {expected}.",
                {"pwm": int(pwm), "actual": verified.get("value", "--"), "expected": int(raw)})
    return "", {}


def policy_supported(snapshot: object, policy: dict | None) -> bool:
    """False when the installed root helper only reads schema 1 and this
    policy cannot be said in schema 1 without losing something."""
    if policy is None:
        return True
    snapshot = as_dict(snapshot)
    status = service_status(snapshot)
    schemas = snapshot.get("policy_schemas") or status.get("policy_schemas")
    if not schemas and status.get("schema") == 1:
        schemas = [1]
    return not (schemas == [1] and downgrade_policy_to_v1(policy) is None)


def needs_service_notice(needs_root_service: bool) -> str:
    return ("Several fans need control from boot" if needs_root_service
            else "Only the desktop follows the curve, and only after you log in.")


def service_summary(snapshot: object, desktop_policy: dict | None, *,
                    sync_error: str = "") -> tuple[str, dict, str]:
    """The one line about the root service under the board:
    ``(English template, values, tone)``."""
    snapshot = as_dict(snapshot)
    enabled = bool(snapshot.get("enabled"))
    available = bool(snapshot.get("available"))
    state = str(snapshot.get("state") or "")
    status = service_status(snapshot)
    out_of_date = service_out_of_date(snapshot, desktop_policy)
    if snapshot.get("external"):
        managers = [str(item) for item in snapshot.get("managers") or []]
        if managers:
            return "{program} controls the fan. Nothing here writes to it.", {"program": ", ".join(managers)}, "blue"
        return EXTERNAL_NOTE, {}, "blue"
    if not snapshot:
        return "Checking the system fan service…", {}, ""
    if not enabled and not available:
        return "Needs the installed BC250 Control Center package and systemd or OpenRC.", {}, ""
    if not enabled:
        return "Only the desktop follows the curve, and only after you log in.", {}, ""
    if sync_error:
        return sync_error, {}, "red"
    if out_of_date:
        return "The service still follows an older curve or preset. Sync it to use the one on screen.", {}, "orange"
    if state == "active":
        controlled = status.get("controlled") or ([status.get("pwm")] if status.get("pwm") else [])
        return ("The system service follows {channels}.",
                {"channels": ", ".join(f"PWM {pwm}" for pwm in controlled) or "—"}, "green")
    if state == "override":
        return "A fan was changed by hand or from Quick Access. Apply its setting again to resume.", {}, "orange"
    if state == "waiting-driver":
        return "Waiting for the NCT fan driver.", {}, "blue"
    if state == "waiting-sensor":
        return "Waiting for temperature sensors.", {}, "blue"
    if state == "error":
        return str(status.get("error") or "The service reported an error."), {}, "red"
    if state == "idle":
        return "No curve or preset to follow; the firmware drives the fan.", {}, ""
    return "The service is enabled but not running. The firmware drives the fan.", {}, "orange"


def service_out_of_date(snapshot: object, desktop_policy: dict | None) -> bool:
    snapshot = as_dict(snapshot)
    return bool(snapshot.get("enabled") and desktop_policy is not None
                and snapshot.get("policy_digest") != policy_digest(desktop_policy))


def follows(entry: dict) -> tuple[str, dict]:
    """What a channel follows: ``(English template, values)``."""
    mode = entry.get("mode", "firmware")
    if mode == "curve":
        return dict(SOURCE_LABELS).get(entry.get("source", "hottest"), str(entry.get("source"))), {}
    if mode == "mix":
        return "{count} curves", {"count": len(entry.get("mix") or [])}
    return "—", {}


def board_rows(board, fans_state: object, snapshot: object, *, pending=(), verified=()) -> list[dict]:
    """Every channel of the board as plain data (English labels)."""
    rows = fan_rows(fans_state)
    snapshot = as_dict(snapshot)
    channels = board.channels if board else {}
    labels = board.labels if board else {}
    out = []
    for pwm in channel_numbers(rows, channels):
        entry = channels.get(str(pwm)) or {"mode": "firmware"}
        mode = entry.get("mode", "firmware")
        fan = rows.get(pwm, {})
        status = channel_status(snapshot, pwm)
        state, tone = row_state(mode, fan, status, external=bool(snapshot.get("external")),
                                service_enabled=bool(snapshot.get("enabled")),
                                pending=pwm in pending, verified=pwm in verified)
        follow, follow_values = follows(entry)
        out.append({
            "pwm": pwm,
            "label": labels.get(str(pwm), ""),
            "header": header_text(pwm),
            "short_header": short_header(pwm),
            "bios": bios_number(pwm),
            "entry": entry,
            "mode": mode,
            "mode_label": dict(MODE_LABELS)[mode],
            "role": entry.get("role", "fan"),
            "follows": follow,
            "follows_values": follow_values,
            "temperature": finite_number(status.get("temperature")),
            "sensor": str(status.get("sensor") or ""),
            "target": status.get("percent") if isinstance(status.get("percent"), (int, float)) else None,
            "duty": pwm_to_percent(fan.get("pwm")) if fan.get("pwm") is not None else None,
            "rpm": integer(fan.get("rpm")) if fan.get("rpm") is not None else None,
            "detected": bool(fan),
            "writable": bool(fan.get("pwm_path") and is_writable(fan)),
            "state": state,
            "tone": tone,
            "fault": str(status.get("fault") or status.get("error") or ""),
        })
    return out


def followed_channels(snapshot: object) -> list[int]:
    """The channels the root service drives right now, in its own order."""
    status = service_status(snapshot)
    controlled = status.get("controlled")
    if isinstance(controlled, list):
        return [integer(pwm, -1) for pwm in controlled if integer(pwm, -1) > 0]
    pwm = integer(status.get("pwm"), -1)
    return [pwm] if pwm > 0 else []


def dashboard_fan(fans_state: object, snapshot: object, config: dict | None = None) -> dict:
    """The one fan a dashboard's Cooling card shows: the channel the root
    service follows, else one that is turning (BIOS order, so CPU_FAN1 /
    J4003 F1 first), else PWM 2, else the first header. Never an empty
    header just because it is listed first.

    Returns ``{}`` without fans, else the hwmon row plus ``pwm_channel``, ``name``
    (the user's label or the header) and ``owner`` (a ``FAN_OWNER_LABELS``
    key: system, daemon, firmware, manual or external).
    """
    rows = fan_rows(fans_state)
    if not rows:
        return {}
    snapshot = as_dict(snapshot)
    board = board_from_config(config or {})
    order = [pwm for pwm in channel_numbers(rows, board.channels) if pwm in rows]
    order += [pwm for pwm in sorted(rows) if pwm not in order]
    followed = [pwm for pwm in followed_channels(snapshot) if pwm in rows] if snapshot.get("enabled") else []
    turning = [pwm for pwm in order if integer(rows[pwm].get("rpm")) > 0]
    pwm = (followed or turning or [pwm for pwm in order if pwm == 2] or order)[0]
    row = rows[pwm]
    if snapshot.get("external"):
        owner = "external"
    elif system_fan_control_owns_fan(snapshot) and (pwm in followed or not followed_channels(snapshot)):
        owner = "system"
    elif integer(row.get("pwm_enable"), -1) == 2:
        owner = "firmware"
    elif str(pwm) in board.channels:
        owner = "daemon"
    else:
        owner = "manual"
    name = board.labels.get(str(pwm)) or f"{header_text(pwm)} · PWM {pwm}"
    return {**row, "pwm_channel": pwm, "name": name, "owner": owner}
