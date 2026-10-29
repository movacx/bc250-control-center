"""The root fan service's policy, as the frontends use it."""

from __future__ import annotations

from bc250cc.infrastructure.system_fan_control import (
    build_system_fan_policy,
    policy_digest,
    system_fan_control_owns_fan,
)

__all__ = ["build_system_fan_policy", "policy_digest", "system_fan_control_owns_fan"]
