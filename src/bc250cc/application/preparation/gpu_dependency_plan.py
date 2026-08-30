"""Pure request planning for the GPU dependency-preparation workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

DEFAULT_PREPARATION_COMPONENTS = frozenset(
    {"runtime", "governor", "cpu_oc", "core_unlock", "umr", "cu_manager", "fan_pwm"}
)
KNOWN_PREPARATION_ACTIONS = frozenset(
    {"prepare", "remove", "steamos_compat", "steamos_diagnostics"}
)


@dataclass(frozen=True)
class GpuDependencyPlan:
    action: str
    route: str
    preference: str
    resolved_governor: str
    components: frozenset[str]
    conflicts: tuple[str, ...]
    kernel_ready: bool
    os_label: str
    kernel: str

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)

    @property
    def include_pwm(self) -> bool:
        return "fan_pwm" in self.components

    @property
    def requires_kernel_confirmation(self) -> bool:
        return self.action == "steamos_compat" and not self.kernel_ready


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _conflict_name(value: object) -> str:
    state = _mapping(value)
    if state:
        return str(state.get("identifier") or state.get("service") or "Unknown governor")
    return str(value or "Unknown governor")


def _normalized_components(values: object) -> frozenset[str]:
    try:
        components = {str(value) for value in values}  # type: ignore[union-attr]
    except TypeError:
        components = set(DEFAULT_PREPARATION_COMPONENTS)
    components.add("runtime")
    if "cu_manager" in components:
        components.add("umr")
    return frozenset(components)


def _active_governor_conflicts(
    tools: Mapping[str, object], *, resolved_governor: str, preference: str,
) -> tuple[str, ...]:
    states = _mapping(tools.get("supported_gpu_governors"))
    calculated = [
        str(
            _mapping(state).get("identifier")
            or _mapping(state).get("service")
            or identifier
        )
        for identifier, state in states.items()
        if identifier != resolved_governor
        and bool(_mapping(state).get("active") or _mapping(state).get("enabled"))
    ]
    candidates: object = calculated
    if preference == "auto":
        candidates = tools.get("incompatible_gpu_governors") or calculated
    try:
        names = tuple(_conflict_name(item) for item in candidates)  # type: ignore[union-attr]
    except TypeError:
        names = ()
    return tuple(dict.fromkeys(names))


def build_gpu_dependency_plan(
    tools: Mapping[str, object],
    *,
    current_governor: object,
    action: object,
    preference: object,
    selected_components: object = DEFAULT_PREPARATION_COMPONENTS,
) -> GpuDependencyPlan:
    action_name = str(action or "")
    if action_name not in KNOWN_PREPARATION_ACTIONS:
        raise ValueError(f"Unsupported dependency action: {action_name or '--'}")

    current = str(
        tools.get("governor_backend")
        or current_governor
        or "cyan-skillfish-governor-smu"
    )
    requested = str(preference or ("auto" if action_name == "prepare" else ""))
    resolved = current if requested == "auto" else requested
    components = _normalized_components(selected_components)
    conflicts = ()
    if action_name == "prepare" and "governor" in components:
        conflicts = _active_governor_conflicts(
            tools,
            resolved_governor=resolved,
            preference=requested,
        )

    routes = {
        "steamos_compat": "compatibility",
        "steamos_diagnostics": "diagnostics",
        "remove": "remove",
        "prepare": "shared" if requested == "auto" else "governor",
    }
    gfx_state = _mapping(tools.get("gfx1013_compute"))
    return GpuDependencyPlan(
        action=action_name,
        route=routes[action_name],
        preference=requested,
        resolved_governor=resolved,
        components=components,
        conflicts=conflicts,
        kernel_ready=bool(gfx_state.get("steamos_kernel_ready")),
        os_label=str(tools.get("os_label") or "SteamOS"),
        kernel=str(gfx_state.get("kernel") or "Unknown"),
    )
