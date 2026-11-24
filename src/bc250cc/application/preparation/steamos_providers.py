"""What the interface may offer from the SteamOS providers, and what is protected.

The two providers (the Real Toolkit and the keyboardspecialist alternative) are
infrastructure adapters. The interface learns their closed action sets, their
labels and which actions our own configuration protects only through this module,
so a provider can be changed or removed without touching a frontend.
"""
from __future__ import annotations

from collections.abc import Mapping

from bc250cc.infrastructure.steamos_alternative import ALTERNATIVE_ACTIONS
from bc250cc.infrastructure.steamos_real_toolkit import (
    ACTIONS,
    DIRECT_ACTIONS,
    guarded_component,
    toolkit_restore_actions,
)
from bc250cc.infrastructure.steamos_toolkit_conflicts import (
    BULK_COMPONENTS,
    NATIVE_COMPONENTS,
)

__all__ = (
    "ALTERNATIVE_ACTIONS", "alternative_action_keys", "protected_actions", "real_toolkit_action_keys",
    "real_toolkit_direct_action_keys", "real_toolkit_running", "steamos_ownership", "toolkit_restore_actions",
)


def real_toolkit_action_keys() -> tuple[str, ...]:
    """Every action the Real Toolkit adapter dispatches, in registry order."""
    return tuple(action.key for action in ACTIONS)


def real_toolkit_direct_action_keys() -> tuple[str, ...]:
    return tuple(action.key for action in DIRECT_ACTIONS)


def real_toolkit_running() -> bool:
    """Whether a Real Toolkit action holds its session now."""
    from bc250cc.infrastructure import steamos_real_toolkit, steamos_root_guard

    return bool(steamos_root_guard.session_running(
        steamos_root_guard.read_session(steamos_real_toolkit.STATE_ROOT)
    ))


def alternative_action_keys() -> tuple[str, ...]:
    return tuple(ALTERNATIVE_ACTIONS)


def _components(component: str | None) -> tuple[str | None, ...]:
    if component == "all":
        return tuple(BULK_COMPONENTS)
    if component == "performance":
        return ("cpu", "gpu", "cu")
    return (component,)


def protected_actions(ownership: Mapping[str, object] | None) -> frozenset[str]:
    """Toolkit actions that would touch a component this application already manages.

    ``ownership`` maps a component to the native files that claim it (empty when
    nothing does; ``None`` when that could not be read, which counts as unclaimed
    here because the privileged checker still refuses at operation time).
    """
    claims = dict(ownership or {})
    return frozenset(
        action.key for action in ACTIONS + DIRECT_ACTIONS
        if any(claims.get(component) for component in _components(guarded_component(action.key)))
    )


def steamos_ownership(toolkit: Mapping, alternative: Mapping) -> dict[str, tuple[str, ...]]:
    """Summarize provider claims from the read-only conflict and status probes."""
    native = toolkit.get("native_ownership") or {}
    components = toolkit.get("components") or {}
    graphics = toolkit.get("graphics") or {}
    radv = alternative.get("radv") or {}
    kernel = alternative.get("kernel") or {}
    foreign = toolkit.get("foreign_graphics")
    claimed_native = tuple(key for key in NATIVE_COMPONENTS if native.get(key))
    claimed_toolkit = [
        key for key in ("acpi", "video", "ac3", "dual-audio", "dualsense", "aic8800",
                        "xbox-adapter", "cec", "cec-retrain", "recovery") if components.get(key)
    ]
    claimed_alternative = []
    if kernel.get("installed"):
        claimed_alternative.append("amdgpu")
    elif graphics.get("kernel_override_installed") and foreign == [] and graphics.get("kernel_toolkit_marker"):
        claimed_toolkit.append("amdgpu")
    if radv.get("state") == "ready" or alternative.get("orphaned"):
        claimed_alternative.append("radv")
    if graphics.get("state") in {"configured", "incomplete"}:
        claimed_toolkit.append("radv")
    if (toolkit.get("proton") or {}).get("state") == "installed":
        claimed_toolkit.append("proton")
    if toolkit.get("alternative_proton"):
        claimed_alternative.append("alternative-proton")
    return {"real-toolkit": tuple(claimed_toolkit), "keyboardspecialist": tuple(claimed_alternative),
            "native": claimed_native}
