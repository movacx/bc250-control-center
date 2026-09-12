"""The redesigned GPU screen has to be usable with a controller.

The navigation promotes ordinary widgets to controller targets on its own, so
every custom widget on this screen was already reachable — and several of them
answered nothing once reached. The safe-point rail was the worst of them: it
carries two values, a D-pad has no position to pick one with, and arrow keys
fell through to the navigation instead of moving anything.

What is checked here is the contract the navigation actually uses:
``gamepad_activate`` for the accept button, the ``gamepadSkip`` property for
things that are only read, and real key handling for the rail.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent

from frontends.desktop.pages.gpu_governor_view import (
    FrequencyField,
    PickerRow,
    SafePointRail,
    offered_points,
)


def press(widget, key, modifiers=Qt.KeyboardModifier.NoModifier):
    widget.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, key, modifiers))


@pytest.fixture
def rail(qtbot):
    widget = SafePointRail()
    qtbot.addWidget(widget)
    widget.resize(700, 90)
    widget.set_range(1000, 1850)
    return widget


# --------------------------------------------------------------- the rail


def test_the_rail_can_hold_focus_at_all(rail):
    """Without this the arrows never reach it."""
    assert rail.focusPolicy() == Qt.FocusPolicy.StrongFocus


def test_right_moves_the_active_handle_up_one_safe_point(rail):
    points = offered_points(unlocked=False)
    rail.set_active_handle("maximum")
    before = rail.range()[1]
    press(rail, Qt.Key.Key_Right)
    after = rail.range()[1]
    assert after > before
    assert after in points
    assert points.index(after) == points.index(before) + 1


def test_left_moves_it_back_down(rail):
    rail.set_active_handle("maximum")
    press(rail, Qt.Key.Key_Right)
    raised = rail.range()[1]
    press(rail, Qt.Key.Key_Left)
    assert rail.range()[1] < raised


def test_the_accept_button_swaps_which_end_is_being_edited(rail):
    """One rail, two values, one controller cursor."""
    assert rail.active_handle() == "maximum"
    rail.gamepad_activate()
    assert rail.active_handle() == "minimum"
    rail.gamepad_activate()
    assert rail.active_handle() == "maximum"


def test_the_floor_can_be_moved_too(rail):
    rail.set_active_handle("minimum")
    before = rail.range()[0]
    press(rail, Qt.Key.Key_Right)
    assert rail.range()[0] > before
    assert rail.range()[1] == 1850, "moving the floor must not move the ceiling"


def test_the_floor_never_passes_the_ceiling(rail):
    rail.set_range(1000, 1000)
    rail.set_active_handle("minimum")
    for _ in range(20):
        press(rail, Qt.Key.Key_Right)
    minimum, maximum = rail.range()
    assert minimum <= maximum


def test_the_ceiling_never_falls_below_the_floor(rail):
    rail.set_range(1500, 1500)
    rail.set_active_handle("maximum")
    for _ in range(20):
        press(rail, Qt.Key.Key_Left)
    minimum, maximum = rail.range()
    assert maximum >= minimum


def test_the_rail_stops_at_the_ends_instead_of_wrapping(rail):
    points = offered_points(unlocked=False)
    rail.set_active_handle("maximum")
    for _ in range(len(points) + 10):
        press(rail, Qt.Key.Key_Right)
    assert rail.range()[1] == points[-1]


def test_a_locked_rail_will_not_step_past_the_safe_ceiling(rail):
    from frontends.desktop.pages.gpu_governor_view import SAFE_CEILING

    rail.set_unlocked(False)
    rail.set_active_handle("maximum")
    for _ in range(40):
        press(rail, Qt.Key.Key_Right)
    assert rail.range()[1] <= SAFE_CEILING


def test_unlocking_opens_the_points_above_the_ceiling(rail):
    from frontends.desktop.pages.gpu_governor_view import SAFE_CEILING

    rail.set_unlocked(True)
    rail.set_active_handle("maximum")
    for _ in range(40):
        press(rail, Qt.Key.Key_Right)
    assert rail.range()[1] > SAFE_CEILING


def test_every_step_reports_the_new_range(rail, qtbot):
    seen: list[tuple[int, int]] = []
    rail.range_changed.connect(lambda low, high: seen.append((low, high)))
    rail.set_active_handle("maximum")
    press(rail, Qt.Key.Key_Right)
    assert seen and seen[-1] == rail.range()


def test_up_and_down_are_left_for_the_navigation_to_use(rail):
    """Otherwise the rail is a trap: nothing would move focus off it."""
    before = rail.range()
    press(rail, Qt.Key.Key_Up)
    press(rail, Qt.Key.Key_Down)
    assert rail.range() == before


def test_home_and_end_jump_to_the_extremes(rail):
    points = offered_points(unlocked=False)
    rail.set_active_handle("maximum")
    press(rail, Qt.Key.Key_End)
    assert rail.range()[1] == points[-1]
    rail.set_active_handle("minimum")
    press(rail, Qt.Key.Key_Home)
    assert rail.range()[0] == points[0]


def test_a_pointer_press_adopts_the_handle_it_grabbed(rail, qtbot):
    """So the arrows continue from where the mouse left off."""
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QMouseEvent

    rail.set_active_handle("maximum")
    x = rail._x_for(rail.range()[0])
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(x, 20),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    rail.mousePressEvent(event)
    assert rail.active_handle() == "minimum"


# ------------------------------------------------------------- the picker


def test_the_picker_answers_the_accept_button(qtbot, monkeypatch):
    """It is not a QComboBox, so the navigation's popup fallback misses it."""
    picker = PickerRow("Governor method")
    qtbot.addWidget(picker)
    picker.addItem("SMU", "smu")
    picker.addItem("kernel", "kernel")

    opened: list[bool] = []
    monkeypatch.setattr(picker, "open_options", lambda: opened.append(True))
    assert callable(getattr(picker, "gamepad_activate", None))
    picker.gamepad_activate()
    assert opened == [True]


def test_the_picker_answers_enter_as_well(qtbot, monkeypatch):
    picker = PickerRow("Usage reading")
    qtbot.addWidget(picker)
    picker.addItem("busy-flag", "busy-flag")
    opened: list[bool] = []
    monkeypatch.setattr(picker, "open_options", lambda: opened.append(True))
    press(picker, Qt.Key.Key_Return)
    assert opened == [True]


def test_an_empty_picker_opens_nothing(qtbot):
    picker = PickerRow("Vacío")
    qtbot.addWidget(picker)
    picker.open_options()  # must not raise or block on an empty menu


# ----------------------------------------------------- read-only dead ends


def test_a_frequency_readout_is_not_a_controller_stop(qtbot):
    field = FrequencyField("Minimum frequency", "detalle")
    qtbot.addWidget(field)
    assert bool(field.property("gamepadSkip"))


def test_the_check_rows_are_buttons_so_accept_already_works(qtbot):
    from PyQt6.QtWidgets import QAbstractButton

    from frontends.desktop.pages.gpu_governor_view import CheckRow

    row = CheckRow("Fix metrics")
    qtbot.addWidget(row)
    assert isinstance(row, QAbstractButton)
