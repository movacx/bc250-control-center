"""Compute-unit topology and WGP mask models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class WgpMaskTable:
    rows: tuple[int, int, int, int]

    def __post_init__(self) -> None:
        if not isinstance(self.rows, tuple):
            raise ValueError("The WGP table rows must be an immutable tuple.")
        if len(self.rows) != 4:
            raise ValueError("The WGP table must contain exactly four shader rows.")
        if any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 0 <= value <= 0x1F
            for value in self.rows
        ):
            raise ValueError("Every WGP row mask must be an integer between 0 and 31.")

    @classmethod
    def from_values(cls, values: Iterable[object]) -> "WgpMaskTable":
        raw = tuple(values)
        if len(raw) != 4:
            raise ValueError("The WGP table must contain exactly four shader rows.")
        if any(type(value) is not int for value in raw):
            raise ValueError("Every WGP row mask must be an integer between 0 and 31.")
        rows = raw
        if any(not 0 <= value <= 0x1F for value in rows):
            raise ValueError("Every WGP row mask must be between 0x00 and 0x1f.")
        return cls(rows)  # type: ignore[arg-type]

    @property
    def active_cus(self) -> int:
        return sum(mask.bit_count() * 2 for mask in self.rows)


@dataclass(frozen=True, slots=True)
class ComputeUnitState:
    factory_cus: int
    active_cus: int
    live: WgpMaskTable
    persisted: WgpMaskTable | None = None

    def __post_init__(self) -> None:
        for name, value in (("factory_cus", self.factory_cus), ("active_cus", self.active_cus)):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 40:
                raise ValueError(f"{name} must be an integer between 0 and 40.")
        if self.live.active_cus != self.active_cus:
            raise ValueError("active_cus must match the live WGP table.")
        if self.persisted is not None and not isinstance(self.persisted, WgpMaskTable):
            raise ValueError("persisted must be a WgpMaskTable or None.")
