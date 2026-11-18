"""What the interface may offer from the SteamOS providers, and what is protected.

The two providers (the Real Toolkit and the keyboardspecialist alternative) are
infrastructure adapters. The interface learns their closed action sets, their
labels and which actions our own configuration protects only through this module,
so a provider can be changed or removed without touching a frontend.
"""
from __future__ import annotations

from collections.abc import Mapping

from bc250cc.infrastructure.steamos_alternative import ALTERNATIVE_ACTIONS
from bc250cc.infrastructure.steamos_real_toolkit import ACTIONS, guarded_component
from bc250cc.infrastructure.steamos_toolkit_conflicts import BULK_COMPONENTS

__all__ = (
    "ALTERNATIVE_ACTIONS", "alternative_action_keys", "protected_actions", "real_toolkit_action_keys",
)


def real_toolkit_action_keys() -> tuple[str, ...]:
    """Every action the Real Toolkit adapter dispatches, in registry order."""
    return tuple(action.key for action in ACTIONS)


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
        action.key for action in ACTIONS
        if any(claims.get(component) for component in _components(guarded_component(action.key)))
    )
