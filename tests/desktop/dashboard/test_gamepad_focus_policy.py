import pytest

from frontends.desktop.core.gamepad_focus_policy import (
    FocusRect,
    select_directional_target,
)


def _choose(current, candidates, direction, weight=1.7, penalty=95.0):
    return select_directional_target(
        current,
        candidates,
        direction,
        orthogonal_weight=weight,
        nonoverlap_penalty=penalty,
    )


def test_directional_focus_prefers_nearest_aligned_candidate():
    current = FocusRect(100, 100, 199, 139)
    candidates = [
        FocusRect(100, 200, 199, 239),
        FocusRect(100, 150, 199, 189),
        FocusRect(100, 20, 199, 59),
    ]

    assert _choose(current, candidates, "down") == 1


def test_directional_focus_penalizes_off_axis_candidate():
    current = FocusRect(100, 100, 199, 139)
    candidates = [
        FocusRect(260, 130, 359, 169),
        FocusRect(100, 180, 199, 219),
    ]

    assert _choose(current, candidates, "down") == 1


def test_directional_focus_returns_none_without_candidate_in_direction():
    current = FocusRect(100, 100, 199, 139)
    candidates = [FocusRect(100, 50, 199, 89), FocusRect(20, 100, 89, 139)]

    assert _choose(current, candidates, "down") is None


def test_directional_focus_uses_candidate_order_as_tie_breaker():
    current = FocusRect(100, 100, 199, 139)
    candidates = [FocusRect(20, 100, 89, 139), FocusRect(210, 100, 279, 139)]

    assert _choose(current, candidates, "left") == 0


def test_directional_focus_rejects_unknown_direction():
    with pytest.raises(ValueError, match="Unsupported focus direction"):
        _choose(FocusRect(0, 0, 9, 9), [], "diagonal")
