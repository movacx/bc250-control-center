"""Pure spatial-focus decisions used by the Qt gamepad adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

_VERTICAL_DIRECTIONS = {"up", "down"}
_HORIZONTAL_DIRECTIONS = {"left", "right"}


@dataclass(frozen=True)
class FocusRect:
    """Inclusive rectangle coordinates matching ``QRect`` geometry."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def center_x(self) -> int:
        return (self.left + self.right) // 2

    @property
    def center_y(self) -> int:
        return (self.top + self.bottom) // 2


def select_directional_target(
    current: FocusRect,
    candidates: Sequence[FocusRect],
    direction: str,
    *,
    orthogonal_weight: float,
    nonoverlap_penalty: float,
    direction_threshold: int = 2,
) -> int | None:
    """Return the best candidate index in ``direction``, or ``None``.

    Candidate order is the deterministic tie breaker, matching Python's
    stable ``min`` behavior used by the former inline Qt implementation.
    """

    if direction not in _VERTICAL_DIRECTIONS | _HORIZONTAL_DIRECTIONS:
        raise ValueError(f"Unsupported focus direction: {direction}")

    scored: list[tuple[float, int]] = []
    for index, candidate in enumerate(candidates):
        dx = candidate.center_x - current.center_x
        dy = candidate.center_y - current.center_y
        if direction == "up" and dy >= -direction_threshold:
            continue
        if direction == "down" and dy <= direction_threshold:
            continue
        if direction == "left" and dx >= -direction_threshold:
            continue
        if direction == "right" and dx <= direction_threshold:
            continue

        if direction in _VERTICAL_DIRECTIONS:
            primary = abs(dy)
            orthogonal = abs(dx)
            overlaps = candidate.right >= current.left and candidate.left <= current.right
        else:
            primary = abs(dx)
            orthogonal = abs(dy)
            overlaps = candidate.bottom >= current.top and candidate.top <= current.bottom
        score = primary + orthogonal * orthogonal_weight
        if not overlaps:
            score += nonoverlap_penalty
        scored.append((score, index))

    return min(scored, default=(0.0, None), key=lambda item: item[0])[1]
