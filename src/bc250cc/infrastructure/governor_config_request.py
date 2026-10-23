"""Validated requests for the privileged governor configuration helper."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from bc250cc.infrastructure.polkit_session import pkexec_argv

GOVERNOR_CONFIG_HELPER_PROTOCOL = 7
_PROTOCOL_PATTERN = re.compile(r"^BC250_GOVERNOR_CONFIG_PROTOCOL\s*=\s*(\d+)\s*$", re.MULTILINE)


def governor_config_helper_protocol(source: object) -> int | None:
    match = _PROTOCOL_PATTERN.search(str(source or ""))
    return int(match.group(1)) if match else None


GOVERNOR_CONFIG_HELPER_CANDIDATES = (
    Path("/usr/libexec/bc250-control-center/bc250-governor-config-helper"),
    Path("/usr/local/libexec/bc250-control-center/bc250-governor-config-helper"),
)


def find_governor_config_helper(candidates=GOVERNOR_CONFIG_HELPER_CANDIDATES) -> tuple[str, int | None]:
    """The trusted helper speaking this protocol, and any other one seen.

    Returns ``(path, None)`` when one matches, ``("", protocol)`` when only a
    trusted helper of another version is installed (an install older or newer
    than this application), and ``("", None)`` when there is none at all.
    """
    other: int | None = None
    for candidate in candidates:
        try:
            metadata = candidate.stat(follow_symlinks=False)
        except OSError:
            continue
        if candidate.is_symlink() or not candidate.is_file():
            continue
        if metadata.st_uid != 0 or metadata.st_mode & 0o022:
            continue
        if not os.access(candidate, os.X_OK):
            continue
        try:
            source = candidate.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeError):
            continue
        protocol = governor_config_helper_protocol(source)
        if protocol == GOVERNOR_CONFIG_HELPER_PROTOCOL:
            return str(candidate), None
        if other is None:
            other = protocol if protocol is not None else 0
    return "", other


def missing_governor_config_helper_message(purpose: str, candidates=GOVERNOR_CONFIG_HELPER_CANDIDATES) -> str:
    """Why no helper can be used: absent, or installed by another version.

    Both used to read "is not installed", which sent people looking for a
    missing file when the real fix was reinstalling after an update.
    """
    _path, other = find_governor_config_helper(candidates)
    if other is not None:
        installed = f"protocol {other}" if other else "an unversioned build"
        return (
            "The installed privileged helper is older than this application "
            f"({installed}, this version needs protocol {GOVERNOR_CONFIG_HELPER_PROTOCOL}). "
            f"Reinstall BC250 Control Center locally or from its package before {purpose}."
        )
    return (
        "The privileged governor configuration helper is not installed. "
        f"Reinstall BC250 Control Center locally or from its package before {purpose}."
    )


NO_ARGUMENT_ACTIONS = frozenset({
    "clear-frequency-range",
    "enable-high-points",
    "disable-high-points",
    "migrate-legacy-frequency-range",
})


@dataclass(frozen=True)
class GovernorConfigRequest:
    action: str
    arguments: tuple[str, ...]

    def argv(self, helper: str) -> list[str]:
        return pkexec_argv("pkexec", helper, self.action, *self.arguments)


def _integers(
    action: str,
    arguments: tuple[object, ...],
    *,
    count: int,
    arity_message: str,
    type_message: str,
) -> GovernorConfigRequest:
    if len(arguments) != count:
        raise ValueError(arity_message)
    normalized = tuple(str(_exact_integer(value, type_message)) for value in arguments)
    return GovernorConfigRequest(action, normalized)


def _exact_integer(value: object, message: str) -> int:
    if isinstance(value, bool):
        raise ValueError(message)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
        return int(value.strip())
    raise ValueError(message)


#: Mirrors FLOOR/ABSOLUTE_CEILING in gpu_governor_view.py: the widest range
#: any Cyan profile editor already lets a user stage, before the live D-Bus
#: envelope check (which still runs, on this exact data, inside the root
#: helper) narrows it further.
DECKY_PROFILE_MIN_MHZ = 500
DECKY_PROFILE_MAX_MHZ = 2400
DECKY_PROFILE_KEYS = ("balanced", "gaming", "benchmark")


def _decky_gpu_profiles_argument(arguments: tuple[object, ...]) -> tuple[str, ...]:
    if len(arguments) != 1:
        raise ValueError("set-decky-gpu-profiles needs exactly one profile list.")
    (profiles,) = arguments
    if not isinstance(profiles, (list, tuple)) or not 1 <= len(profiles) <= len(DECKY_PROFILE_KEYS):
        raise ValueError("Decky GPU profiles must be a list of one to three entries.")
    seen_keys: set[str] = set()
    normalized: list[dict[str, object]] = []
    for entry in profiles:
        if not isinstance(entry, dict):
            raise ValueError("Each Decky GPU profile must be an object.")
        key = entry.get("key")
        if key not in DECKY_PROFILE_KEYS or key in seen_keys:
            raise ValueError("Each Decky GPU profile needs a unique known key.")
        seen_keys.add(key)
        name = str(entry.get("name") or "").strip()
        if not name or len(name) > 40:
            raise ValueError("Decky GPU profile names must be 1-40 characters.")
        minimum = _exact_integer(entry.get("min"), "Decky GPU profile bounds must be integers.")
        maximum = _exact_integer(entry.get("max"), "Decky GPU profile bounds must be integers.")
        if not DECKY_PROFILE_MIN_MHZ <= minimum <= maximum <= DECKY_PROFILE_MAX_MHZ:
            raise ValueError(
                f"Decky GPU profile range must be within {DECKY_PROFILE_MIN_MHZ}-"
                f"{DECKY_PROFILE_MAX_MHZ} MHz with minimum not above maximum."
            )
        normalized.append({"key": key, "name": name, "min": minimum, "max": maximum})
    return (json.dumps(normalized, separators=(",", ":"), sort_keys=True),)


#: Mirrors the desktop's DEFAULT_CPU_PROFILES three slots
#: (cpu_control_view.py) and the same 3100-4200 MHz / 950-1325 mV envelope
#: Decky's own CPU_FREQUENCIES/CPU_VIDS ladders already enforce at apply
#: time, so an exported preset can only ever be rejected there, never used
#: to reach a value neither side already allows.
DECKY_CPU_PROFILE_MIN_MHZ = 3100
DECKY_CPU_PROFILE_MAX_MHZ = 4200
DECKY_CPU_PROFILE_MIN_VID = 950
DECKY_CPU_PROFILE_MAX_VID = 1325
#: The same steps cpu-detect and Decky's CPU_FREQUENCIES/CPU_VIDS ladders
#: accept; a value between two steps used to be stored here and then dropped
#: without a word by the readers.
DECKY_CPU_PROFILE_FREQUENCY_STEP = 50
DECKY_CPU_PROFILE_VID_STEP = 5
#: The cap of the desktop's CPU cards. Optional in a request (an older caller
#: never sent it) and then 90 C, the limit Decky always used before.
DECKY_CPU_PROFILE_MIN_TEMPERATURE = 70
DECKY_CPU_PROFILE_MAX_TEMPERATURE = 90
DECKY_CPU_PROFILE_KEYS = ("board_average", "mid_point", "safe_maximum")



#: Decky's own fan presets (quiet/balanced/boost), which the Desktop's three
#: fan profiles are published as; the same 20-100 % the Decky helper and its
#: fan slider allow.
DECKY_FAN_PROFILE_KEYS = ("quiet", "balanced", "boost")
DECKY_FAN_PROFILE_MIN_PERCENT = 20
DECKY_FAN_PROFILE_MAX_PERCENT = 100


def _decky_fan_profiles_argument(arguments: tuple[object, ...]) -> tuple[str, ...]:
    if len(arguments) != 1:
        raise ValueError("set-decky-fan-profiles needs exactly one profile list.")
    (profiles,) = arguments
    if not isinstance(profiles, (list, tuple)) or not 1 <= len(profiles) <= len(DECKY_FAN_PROFILE_KEYS):
        raise ValueError("Decky fan profiles must be a list of one to three entries.")
    seen_keys: set[str] = set()
    normalized: list[dict[str, object]] = []
    for entry in profiles:
        if not isinstance(entry, dict):
            raise ValueError("Each Decky fan profile must be an object.")
        key = entry.get("key")
        if key not in DECKY_FAN_PROFILE_KEYS or key in seen_keys:
            raise ValueError("Each Decky fan profile needs a unique known key.")
        seen_keys.add(key)
        name = str(entry.get("name") or "").strip()
        if not name or len(name) > 40:
            raise ValueError("Decky fan profile names must be 1-40 characters.")
        percent = _exact_integer(entry.get("percent"), "Decky fan profile speeds must be integers.")
        if not DECKY_FAN_PROFILE_MIN_PERCENT <= percent <= DECKY_FAN_PROFILE_MAX_PERCENT:
            raise ValueError(
                f"Decky fan profile speeds must be {DECKY_FAN_PROFILE_MIN_PERCENT}-"
                f"{DECKY_FAN_PROFILE_MAX_PERCENT} %."
            )
        normalized.append({"key": key, "name": name, "percent": percent})
    return (json.dumps(normalized, separators=(",", ":"), sort_keys=True),)


def _decky_cpu_profiles_argument(arguments: tuple[object, ...]) -> tuple[str, ...]:
    if len(arguments) != 1:
        raise ValueError("set-decky-cpu-profiles needs exactly one profile list.")
    (profiles,) = arguments
    if not isinstance(profiles, (list, tuple)) or not 1 <= len(profiles) <= len(DECKY_CPU_PROFILE_KEYS):
        raise ValueError("Decky CPU profiles must be a list of one to three entries.")
    seen_keys: set[str] = set()
    normalized: list[dict[str, object]] = []
    for entry in profiles:
        if not isinstance(entry, dict):
            raise ValueError("Each Decky CPU profile must be an object.")
        key = entry.get("key")
        if key not in DECKY_CPU_PROFILE_KEYS or key in seen_keys:
            raise ValueError("Each Decky CPU profile needs a unique known key.")
        seen_keys.add(key)
        name = str(entry.get("name") or "").strip()
        if not name or len(name) > 40:
            raise ValueError("Decky CPU profile names must be 1-40 characters.")
        frequency = _exact_integer(entry.get("frequency"), "Decky CPU profile values must be integers.")
        vid = _exact_integer(entry.get("vid"), "Decky CPU profile values must be integers.")
        if not DECKY_CPU_PROFILE_MIN_MHZ <= frequency <= DECKY_CPU_PROFILE_MAX_MHZ:
            raise ValueError(
                f"Decky CPU profile frequency must be within {DECKY_CPU_PROFILE_MIN_MHZ}-"
                f"{DECKY_CPU_PROFILE_MAX_MHZ} MHz."
            )
        if not DECKY_CPU_PROFILE_MIN_VID <= vid <= DECKY_CPU_PROFILE_MAX_VID:
            raise ValueError(
                f"Decky CPU profile VID must be within {DECKY_CPU_PROFILE_MIN_VID}-"
                f"{DECKY_CPU_PROFILE_MAX_VID} mV."
            )
        if (
            (frequency - DECKY_CPU_PROFILE_MIN_MHZ) % DECKY_CPU_PROFILE_FREQUENCY_STEP
            or (vid - DECKY_CPU_PROFILE_MIN_VID) % DECKY_CPU_PROFILE_VID_STEP
        ):
            raise ValueError(
                f"Decky CPU profile values must be on the {DECKY_CPU_PROFILE_FREQUENCY_STEP} MHz "
                f"and {DECKY_CPU_PROFILE_VID_STEP} mV steps."
            )
        temperature = _exact_integer(
            entry.get("temperature", DECKY_CPU_PROFILE_MAX_TEMPERATURE),
            "Decky CPU profile values must be integers.",
        )
        if not DECKY_CPU_PROFILE_MIN_TEMPERATURE <= temperature <= DECKY_CPU_PROFILE_MAX_TEMPERATURE:
            raise ValueError(
                f"Decky CPU profile values must keep the temperature within {DECKY_CPU_PROFILE_MIN_TEMPERATURE}-"
                f"{DECKY_CPU_PROFILE_MAX_TEMPERATURE} C."
            )
        normalized.append(
            {"key": key, "name": name, "frequency": frequency, "vid": vid, "temperature": temperature}
        )
    return (json.dumps(normalized, separators=(",", ":"), sort_keys=True),)


def _custom_voltage_arguments(arguments: tuple[object, ...]) -> tuple[str, ...]:
    if not arguments:
        raise ValueError("No custom values to apply.")
    normalized: dict[int, int] = {}
    for item in arguments:
        if not isinstance(item, str) or item.count("=") != 1:
            raise ValueError("Custom GPU voltages must use frequency=millivolts.")
        raw_frequency, raw_voltage = item.split("=", 1)
        frequency = _exact_integer(raw_frequency, "Custom GPU voltage values must be integers.")
        voltage = _exact_integer(raw_voltage, "Custom GPU voltage values must be integers.")
        if frequency <= 0 or not 600 <= voltage <= 1210:
            raise ValueError("Custom GPU voltage value is outside the safe editor range.")
        previous = normalized.get(frequency)
        if previous is not None and previous != voltage:
            raise ValueError("A GPU frequency cannot have conflicting voltage values.")
        normalized[frequency] = voltage
    return tuple(f"{frequency}={normalized[frequency]}" for frequency in sorted(normalized))


def plan_governor_config_request(
    action: object, arguments: tuple[object, ...]
) -> GovernorConfigRequest:
    """Validate an IPC request before any privilege prompt can be opened."""
    if not isinstance(action, str):
        raise ValueError("Invalid governor TOML action.")
    if action in NO_ARGUMENT_ACTIONS:
        if arguments:
            raise ValueError(f"{action} does not accept additional arguments.")
        return GovernorConfigRequest(action, ())
    if action == "set-frequency-range":
        return _integers(
            action,
            arguments,
            count=2,
            arity_message="set-frequency-range needs minimum and maximum values.",
            type_message="Frequency range values must be integers.",
        )
    if action == "set-frequency-floor":
        return _integers(
            action,
            arguments,
            count=1,
            arity_message="set-frequency-floor needs one minimum value.",
            type_message="Frequency floor must be an integer.",
        )
    if action == "set-oberon-operating-points":
        return _integers(
            action,
            arguments,
            count=4,
            arity_message="Oberon operating points need four integer values.",
            type_message="Oberon operating-point values must be integers.",
        )
    if action == "ensure-cyan-telemetry":
        if len(arguments) != 1:
            raise ValueError("ensure-cyan-telemetry needs one boolean flag.")
        flag = arguments[0]
        if not isinstance(flag, bool):
            raise ValueError("Cyan telemetry frequency fix flag must be boolean.")
        return GovernorConfigRequest(action, ("1" if flag else "0",))
    if action == "set-cyan-metrics-fix":
        if len(arguments) != 1:
            raise ValueError("set-cyan-metrics-fix needs one boolean flag.")
        flag = arguments[0]
        if not isinstance(flag, bool):
            raise ValueError("Cyan metrics fix flag must be boolean.")
        return GovernorConfigRequest(action, ("1" if flag else "0",))
    if action == "set-cyan-compatibility":
        if len(arguments) not in {4, 5}:
            raise ValueError(
                "set-cyan-compatibility needs set-method, usage-method, "
                "fix-metrics, fix-freq and optionally temp-read."
            )
        set_method, usage_method, fix_metrics, fix_frequency = arguments[:4]
        # Optional and last; None leaves the TOML line as it is.
        temp_read = arguments[4] if len(arguments) == 5 else None
        normalized_set_method = str(set_method).strip().lower()
        if normalized_set_method not in {"smu", "kernel"}:
            raise ValueError("Cyan set-method must be smu or kernel.")
        normalized_usage_method = str(usage_method).strip().lower()
        if normalized_usage_method not in {"busy-flag", "process", "kernel"}:
            raise ValueError(
                "Cyan usage-method must be busy-flag, process or kernel."
            )
        if not isinstance(fix_metrics, bool) or not isinstance(fix_frequency, bool):
            raise ValueError("Cyan compatibility fix flags must be boolean.")
        values = (
            normalized_set_method,
            normalized_usage_method,
            "1" if fix_metrics else "0",
            "1" if fix_frequency else "0",
        )
        if temp_read is not None:
            normalized_temp_read = str(temp_read).strip().lower()
            if normalized_temp_read not in {"drm", "sysfs"}:
                raise ValueError("Cyan temp-read must be drm or sysfs.")
            values += (normalized_temp_read,)
        return GovernorConfigRequest(action, values)
    if action == "set-cyan-voltage-level":
        request = _integers(
            action,
            arguments,
            count=1,
            arity_message="GPU voltage level needs one value.",
            type_message="GPU voltage level must be an integer.",
        )
        if int(request.arguments[0]) not in {0, 1, 2, 3, 4, 5, 6}:
            raise ValueError("Invalid lab level. Use an integer from 0 through 6.")
        return request
    if action == "set-cyan-custom-voltages":
        return GovernorConfigRequest(action, _custom_voltage_arguments(arguments))
    if action == "set-decky-gpu-profiles":
        return GovernorConfigRequest(action, _decky_gpu_profiles_argument(arguments))
    if action == "set-decky-cpu-profiles":
        return GovernorConfigRequest(action, _decky_cpu_profiles_argument(arguments))
    if action == "set-decky-fan-profiles":
        return GovernorConfigRequest(action, _decky_fan_profiles_argument(arguments))
    raise ValueError("Invalid governor TOML action.")
