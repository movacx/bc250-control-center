"""Pure confirmation plan for GPU governor service lifecycle actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class GpuServiceActionPlan:
    action: str
    backend: str
    service: str
    label: str
    description: str
    description_values: tuple[tuple[str, object], ...]
    boot_persistence: str
    conflicts: tuple[str, ...]
    confirm_text: str
    tone: str

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)


_ACTIONS = {
    "activar": (
        "Enable and start",
        "This starts the governor now and enables it at boot, restoring the persistence control from the original GUI.",
        "Enabled",
    ),
    "reiniciar": (
        "Restart",
        "This restarts the active governor service without changing its boot-enabled state.",
        "Unchanged",
    ),
    "desactivar": (
        "Stop and disable",
        "This stops the governor now and disables it at boot. GPU range controls will be unavailable until it is enabled again.",
        "Disabled",
    ),
}


def _conflict_name(value: object) -> str:
    if isinstance(value, Mapping):
        return str(value.get("identifier") or value.get("service") or "unknown")
    return str(value or "unknown")


def plan_gpu_service_action(
    action: object,
    *,
    backend: object,
    incompatible_governors: object = (),
) -> GpuServiceActionPlan:
    action_name = str(action or "")
    if action_name not in _ACTIONS:
        raise ValueError(f"Unsupported governor service action: {action_name or '--'}")
    backend_name = str(backend or "cyan-skillfish-governor-smu")
    service = (
        "oberon-governor.service"
        if backend_name == "oberon-governor"
        else "cyan-skillfish-governor-smu.service"
    )
    label, description, persistence = _ACTIONS[action_name]
    conflicts: tuple[str, ...] = ()
    if action_name in {"activar", "reiniciar"}:
        try:
            conflicts = tuple(dict.fromkeys(
                _conflict_name(item) for item in incompatible_governors
            ))
        except TypeError:
            conflicts = ()
    values: tuple[tuple[str, object], ...] = ()
    confirm_text = label
    tone = "orange" if action_name == "desactivar" else "blue"
    if conflicts:
        description = (
            "{governors} conflicts with {selected_governor}. Starting both can crash the GPU or produce a green screen at boot. This action will stop and disable the other service before enabling the selected governor."
        )
        values = (
            ("governors", ", ".join(conflicts)),
            ("selected_governor", backend_name),
        )
        confirm_text = "Disable conflict and enable service"
        tone = "red"
    return GpuServiceActionPlan(
        action=action_name,
        backend=backend_name,
        service=service,
        label=label,
        description=description,
        description_values=values,
        boot_persistence=persistence,
        conflicts=conflicts,
        confirm_text=confirm_text,
        tone=tone,
    )
