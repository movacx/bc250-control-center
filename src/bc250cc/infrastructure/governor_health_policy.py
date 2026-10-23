"""Pure health classification for parsed Cyan and Oberon configuration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GovernorHealthDecision:
    status: str
    title: str
    detail: str
    recommendation: str = ""
    repair_action: str = ""

