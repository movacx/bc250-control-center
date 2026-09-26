"""Shader-engine balance of a BC-250 WGP routing table.

The GPU is two shader engines, SE0 and SE1, each made of two shader arrays
(the four rows of the routing table: SE0.SH0, SE0.SH1, SE1.SH0, SE1.SH1).
Testing on BC-250 boards (Old Lamer, June 2026, measured with FurMark while
toggling WGPs live) shows throughput following the *weaker* engine: 20 CUs on
one engine and 18 on the other performs like 18 + 18. So 38 active CUs are 36
effective, and the two extra CUs only add heat.

Pure functions, no Qt: the Compute Units page, its confirmation dialog and the
dashboard all read the same numbers.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

#: Table rows belonging to each shader engine.
ENGINE_ROWS = ((0, 1), (2, 3))
WGPS_PER_ROW = 5


def _masks(values: Sequence[object]) -> list[int]:
    masks = []
    for value in list(values)[:4]:
        try:
            masks.append(max(0, min(0x1F, int(value))))
        except (TypeError, ValueError):
            masks.append(0)
    return masks + [0] * (4 - len(masks))


@dataclass(frozen=True)
class EngineBalance:
    se0: int
    se1: int

    @property
    def total(self) -> int:
        return self.se0 + self.se1

    @property
    def effective(self) -> int:
        """CUs that add throughput: twice the weaker engine."""
        return 2 * min(self.se0, self.se1)

    @property
    def idle(self) -> int:
        """Active CUs on the stronger engine that add nothing but heat."""
        return self.total - self.effective

    @property
    def balanced(self) -> bool:
        return self.se0 == self.se1


def engine_balance(masks: Sequence[object]) -> EngineBalance:
    values = _masks(masks)
    counts = [
        sum(values[row].bit_count() * 2 for row in rows) for rows in ENGINE_ROWS
    ]
    return EngineBalance(counts[0], counts[1])


def balanced_masks(
    masks: Sequence[object], locked: Sequence[object] = (0, 0, 0, 0)
) -> list[int]:
    """Switch off WGPs on the stronger engine until both engines match.

    Only removes routing, never adds it: a WGP this board cannot run must not
    be switched on by a convenience button. The fullest row of the stronger
    engine gives up its highest WGP first, and driver-locked WGPs, which
    cannot be disabled live, are never touched.
    """
    values = _masks(masks)
    held = _masks(locked)
    while True:
        balance = engine_balance(values)
        if balance.balanced:
            return values
        strong = 0 if balance.se0 > balance.se1 else 1
        rows = sorted(
            ENGINE_ROWS[strong],
            key=lambda row: values[row].bit_count(),
            reverse=True,
        )
        for row in rows:
            removable = values[row] & ~held[row]
            if removable:
                values[row] &= ~(1 << (removable.bit_length() - 1))
                break
        else:
            # Everything left on the stronger engine is driver-locked.
            return values
