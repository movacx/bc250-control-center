"""Validated requests for the privileged governor configuration helper."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from bc250cc.infrastructure.polkit_session import pkexec_argv

GOVERNOR_CONFIG_HELPER_PROTOCOL = 6
_PROTOCOL_PATTERN = re.compile(r"^BC250_GOVERNOR_CONFIG_PROTOCOL\s*=\s*(\d+)\s*$", re.MULTILINE)


def governor_config_helper_protocol(source: object) -> int | None:
    match = _PROTOCOL_PATTERN.search(str(source or ""))
    return int(match.group(1)) if match else None


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
        if not DECKY_PROFILE_MIN_MHZ <= minimum < maximum <= DECKY_PROFILE_MAX_MHZ:
            raise ValueError(
                f"Decky GPU profile range must be within {DECKY_PROFILE_MIN_MHZ}-"
                f"{DECKY_PROFILE_MAX_MHZ} MHz with minimum below maximum."
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
DECKY_CPU_PROFILE_KEYS = ("board_average", "mid_point", "safe_maximum")


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
        normalized.append({"key": key, "name": name, "frequency": frequency, "vid": vid})
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
        if len(arguments) != 4:
            raise ValueError(
                "set-cyan-compatibility needs set-method, usage-method, "
                "fix-metrics and fix-freq."
            )
        set_method, usage_method, fix_metrics, fix_frequency = arguments
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
        return GovernorConfigRequest(
            action,
            (
                normalized_set_method,
                normalized_usage_method,
                "1" if fix_metrics else "0",
                "1" if fix_frequency else "0",
            ),
        )
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
    raise ValueError("Invalid governor TOML action.")
