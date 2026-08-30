"""Operation metadata without coupling to Qt or a subprocess runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class OperationState(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(slots=True)
class Operation:
    name: str
    state: OperationState = OperationState.PLANNED
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("operation name cannot be empty")
        if not isinstance(self.state, OperationState):
            raise ValueError("operation state must be an OperationState")
        if not isinstance(self.metadata, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in self.metadata.items()
        ):
            raise ValueError("operation metadata must be a string dictionary")
