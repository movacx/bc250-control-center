"""Read-only health domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Mapping


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class HealthFinding:
    identifier: str
    status: HealthStatus
    title: str
    detail: str
    data: Mapping[str, object] = field(default_factory=dict)
    repair_action: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.identifier, str) or not self.identifier.strip():
            raise ValueError("Health finding identifier cannot be empty.")
        if not isinstance(self.status, HealthStatus):
            raise ValueError("Health finding status must be a HealthStatus.")
        if not isinstance(self.title, str) or not isinstance(self.detail, str):
            raise ValueError("Health finding title and detail must be strings.")


@dataclass(frozen=True)
class HealthSnapshot:
    findings: tuple[HealthFinding, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.findings, tuple):
            raise ValueError("Health snapshot findings must be an immutable tuple.")
        if not all(isinstance(item, HealthFinding) for item in self.findings):
            raise ValueError("Health snapshot contains an invalid finding.")

    @property
    def status(self) -> HealthStatus:
        if any(item.status is HealthStatus.ERROR for item in self.findings):
            return HealthStatus.ERROR
        if any(item.status is HealthStatus.WARNING for item in self.findings):
            return HealthStatus.WARNING
        return HealthStatus.HEALTHY
