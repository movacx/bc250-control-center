"""Hiding the console mid-workflow must not be a one-way door.

Before this, pressing Hide while dependencies were being prepared left no way
back: the panel only reappears when a workflow starts, and that one had
already started.
"""

from frontends.desktop.console.beacon import ConsoleBeacon, ConsoleCounter


class FakeConsole:
    """Only the two answers the window asks the console for."""

    def __init__(self, *, busy=False):
        self.busy = busy
        self.slid_in = 0

    def slide_in(self):
        self.slid_in += 1


def _beacon(qtbot):
    beacon = ConsoleBeacon()
    qtbot.addWidget(beacon)
    return beacon


def test_it_stays_out_of_the_way_when_there_is_nothing_to_return_to(qtbot):
    beacon = _beacon(qtbot)

    beacon.set_active(False)

    assert beacon.isHidden()


def test_it_appears_only_while_a_workflow_is_hidden(qtbot):
    beacon = _beacon(qtbot)

    beacon.set_active(True)
    assert not beacon.isHidden()

    beacon.set_active(False)
    assert beacon.isHidden()


def test_it_animates_only_while_it_is_on_screen(qtbot):
    """An idle window should not be running two loops forever."""
    beacon = _beacon(qtbot)

    beacon.set_active(True)
    assert beacon._bounce.state() != beacon._bounce.State.Stopped

    beacon.set_active(False)
    assert beacon._bounce.state() == beacon._bounce.State.Stopped


def test_it_sits_against_the_right_edge_not_the_bottom_corner(qtbot, qapp):
    """The console slides up from the bottom; a button it covers is useless."""
    from PyQt6.QtWidgets import QWidget

    window = QWidget()
    qtbot.addWidget(window)
    window.resize(1200, 800)
    beacon = ConsoleBeacon(window)

    beacon.reposition()

    assert beacon.x() + beacon.width() < 1200
    assert beacon.x() > 1000
    # Vertically centred, so a panel rising from the bottom never reaches it.
    assert 300 < beacon.y() < 500


def test_clicking_it_reports_the_intent(qtbot):
    beacon = _beacon(qtbot)
    beacon.set_active(True)
    seen = []
    beacon.clicked.connect(lambda: seen.append(True))

    beacon.clicked.emit()

    assert seen == [True]


def test_the_queue_badge_hides_itself_at_zero(qtbot):
    counter = ConsoleCounter()
    qtbot.addWidget(counter)

    counter.set_count(2)
    assert not counter.isHidden()

    counter.set_count(0)
    assert counter.isHidden()


def test_one_workflow_needs_no_number_two_does(qtbot):
    """The badge answers "how many", and with one the answer is obvious."""
    beacon = _beacon(qtbot)

    beacon.set_count(1)
    assert beacon.counter.isHidden()

    beacon.set_count(2)
    assert not beacon.counter.isHidden()

    beacon.set_count(0)
    assert beacon.counter.isHidden()
