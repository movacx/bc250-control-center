from frontends.desktop.core.operation_gate import OperationGate


def test_gate_allows_only_one_generation_at_a_time():
    gate = OperationGate()

    first = gate.begin()

    assert first == 1
    assert gate.busy is True
    assert gate.begin() is None
    assert gate.is_current(first) is True


def test_finished_generation_cannot_affect_a_later_operation():
    gate = OperationGate()
    first = gate.begin()
    assert gate.finish(first) is True
    second = gate.begin()

    assert second == 2
    assert gate.finish(first) is False
    assert gate.is_current(second) is True
    assert gate.finish(second) is True
    assert gate.busy is False
