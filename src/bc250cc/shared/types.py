"""Small immutable value types shared by domains and frontends."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Range:
    minimum: int
    maximum: int

    def __post_init__(self) -> None:
        if any(isinstance(value, bool) or not isinstance(value, int) for value in (self.minimum, self.maximum)):
            raise ValueError("range boundaries must be integers")
        if self.minimum > self.maximum:
            raise ValueError("minimum must not exceed maximum")
