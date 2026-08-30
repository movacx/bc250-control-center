import pytest

from bc250cc.shared import Operation, OperationState, Range


def test_range_rejects_boolean_or_inverted_boundaries():
    with pytest.raises(ValueError):
        Range(True, 10)
    with pytest.raises(ValueError):
        Range(20, 10)


def test_operation_rejects_untyped_state_and_metadata():
    assert Operation("prepare", OperationState.PLANNED).name == "prepare"
    with pytest.raises(ValueError):
        Operation("prepare", "planned")
    with pytest.raises(ValueError):
        Operation("prepare", metadata={"attempt": 1})
