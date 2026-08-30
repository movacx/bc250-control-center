"""Declarative contract for BC250 preparation components.

This module deliberately contains no package-manager or UI code.  It is the
shared source of truth used to normalize a request, expose capabilities and
build the final verification plan on every supported Linux family.
"""

from __future__ import annotations

import shlex
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_FAMILIES = frozenset({
    "arch", "manjaro", "cachyos", "debian", "ubuntu", "fedora",
    "bazzite", "steamos", "gentoo", "alpine",
})

# A family may support the desktop runtime and the init-service layer while a
# particular upstream tool still lacks the exact executable it needs.  Keep
# this fact in the capability contract so the UI and the callable backend fail
# before opening a terminal or authenticating a package operation.
FAMILY_COMPONENT_LIMITATIONS: Mapping[str, Mapping[str, str]] = {
    "alpine": {
        "cpu_oc": (
            "CPU OC is unavailable on Alpine: bc250_smu_oc requires the exact "
            "stress binary, while Alpine packages stress-ng with an incompatible interface."
        ),
    },
}


@dataclass(frozen=True)
class ComponentSpec:
    key: str
    required: bool
    risk: str
    detail: str
    dependencies: tuple[str, ...] = ()
    reboot_families: frozenset[str] = frozenset()


COMPONENT_SPECS: Mapping[str, ComponentSpec] = {
    "runtime": ComponentSpec(
        "runtime", True, "low",
        "Python, Qt, telemetry and authenticated-action runtime.",
        reboot_families=frozenset({"bazzite"}),
    ),
    "governor": ComponentSpec(
        "governor", False, "medium",
        "Installs only the GPU governor selected in the application.",
        reboot_families=frozenset({"bazzite"}),
    ),
    "cpu_oc": ComponentSpec(
        "cpu_oc", False, "medium",
        "Stages the reviewed CPU OC source; it does not apply an overclock.",
    ),
    "core_unlock": ComponentSpec(
        "core_unlock", False, "high",
        "Stages the official source only; unlocking remains a separate action.",
    ),
    "umr": ComponentSpec(
        "umr", False, "medium",
        "Register inspection backend required by live CU routing.",
        reboot_families=frozenset({"bazzite"}),
    ),
    "cu_manager": ComponentSpec(
        "cu_manager", False, "high",
        "Stages the distribution-specific 40CU manager; no CU map is applied.",
        dependencies=("umr",),
    ),
    "fan_pwm": ComponentSpec(
        "fan_pwm", False, "high",
        "Builds the kernel-matched NCT PWM driver and validates writable PWM.",
        reboot_families=frozenset({"bazzite"}),
    ),
}


class UnknownComponentError(ValueError):
    """Raised before any system mutation when a component name is unknown."""


def normalize_components(selected: Iterable[str] | None) -> frozenset[str]:
    requested = set(COMPONENT_SPECS if selected is None else selected)
    unknown = requested.difference(COMPONENT_SPECS)
    if unknown:
        raise UnknownComponentError(
            "Unknown BC250 preparation component(s): " + ", ".join(sorted(unknown))
        )
    requested.add("runtime")
    pending = list(requested)
    while pending:
        key = pending.pop()
        for dependency in COMPONENT_SPECS[key].dependencies:
            if dependency not in requested:
                requested.add(dependency)
                pending.append(dependency)
    return frozenset(requested)


def component_capabilities(os_info) -> dict[str, dict[str, object]]:
    family = str(os_info.family)
    supported = family in SUPPORTED_FAMILIES
    limitations = FAMILY_COMPONENT_LIMITATIONS.get(family, {})
    return {
        key: {
            "available": supported and key not in limitations,
            "required": spec.required,
            "risk": spec.risk,
            "reboot": family in spec.reboot_families,
            "detail": limitations.get(key, spec.detail),
            "dependencies": list(spec.dependencies),
        }
        for key, spec in COMPONENT_SPECS.items()
    }


def unavailable_components(selected: Iterable[str] | None, os_info) -> dict[str, str]:
    """Return the reason for each requested component unavailable on this host."""
    requested = normalize_components(selected)
    capabilities = component_capabilities(os_info)
    return {
        key: str(capabilities[key]["detail"])
        for key in requested
        if not bool(capabilities[key]["available"])
    }


def preparation_plan(selected: Iterable[str] | None, family: str) -> list[dict[str, object]]:
    normalized = normalize_components(selected)
    return [
        {
            "component": key,
            "risk": COMPONENT_SPECS[key].risk,
            "reboot": family in COMPONENT_SPECS[key].reboot_families,
            "dependencies": list(COMPONENT_SPECS[key].dependencies),
        }
        for key in COMPONENT_SPECS
        if key in normalized
    ]


def verification_shell(
    selected: Iterable[str],
    *,
    governor_binary: str,
    cpu_oc_script: Path,
    core_unlock_script: Path,
    cu_manager_script: Path,
) -> list[str]:
    """Return checks for exactly the normalized request.

    Component-specific install stages retain their deeper hardware checks. The
    final pass proves only durable artifacts and never requires an unselected
    optional tool.
    """
    normalized = normalize_components(selected)
    commands = [
        'for cmd in python3 git lspci pkexec; do command -v "$cmd" >/dev/null 2>&1 && echo "OK: $cmd -> $(command -v "$cmd")" || { echo "ERROR: runtime command missing: $cmd"; exit 34; }; done',
        'python3 -c "import PyQt6, psutil" || { echo "ERROR: Python GUI dependencies are unavailable"; exit 35; }',
    ]
    if "governor" in normalized:
        qgovernor = shlex.quote(governor_binary)
        commands.append(
            f'command -v {qgovernor} >/dev/null 2>&1 || '
            f'{{ echo "ERROR: selected governor is unavailable: {qgovernor}"; exit 33; }}'
        )
    if "cpu_oc" in normalized:
        qcpu = shlex.quote(str(cpu_oc_script))
        commands.append(
            f'test -f {qcpu} || '
            '{ echo "ERROR: CPU OC source validation failed"; exit 30; }'
        )
    if "core_unlock" in normalized:
        qunlock = shlex.quote(str(core_unlock_script))
        commands.append(
            f'test -f {qunlock} || '
            '{ echo "ERROR: core-unlock source validation failed"; exit 36; }'
        )
    if "umr" in normalized:
        commands.append(
            'command -v umr >/dev/null 2>&1 || { echo "ERROR: UMR is unavailable"; exit 32; }'
        )
    if "cu_manager" in normalized:
        qcu = shlex.quote(str(cu_manager_script))
        commands.append(
            f'test -x {qcu} || '
            '{ echo "ERROR: 40CU manager validation failed"; exit 31; }'
        )
    return commands
