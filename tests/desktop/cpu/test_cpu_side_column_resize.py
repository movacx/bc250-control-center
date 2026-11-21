"""CPU screen: the monitoring column can be dragged wider and stays that way.

The right-hand column (telemetry, core sensors, persistence, core unlock) had
a fixed share of the window. A bar between the columns now resizes it, the
width is stored, and a double-click gives the default split back.
"""

from __future__ import annotations

import pytest

from frontends.desktop.core.preferences import application_settings
from frontends.desktop.pages import cpu_control_view as module
from frontends.desktop.pages.cpu_control_view import CpuControlView


@pytest.fixture(autouse=True)
def clean_setting():
    application_settings().remove(module.SIDE_WIDTH_KEY)
    yield
    application_settings().remove(module.SIDE_WIDTH_KEY)


def _view(qtbot) -> CpuControlView:
    view = CpuControlView()
    qtbot.addWidget(view)
    view.resize(1600, 1000)
    view.show()
    qtbot.waitExposed(view)
    return view


def test_dragging_left_widens_the_column_and_it_is_remembered(qtbot):
    view = _view(qtbot)
    before = view._telemetry.width()
    grip = view._side_grip
    grip.pressed.emit()
    grip.dragged.emit(-120)
    grip.released.emit()
    qtbot.wait(20)
    assert view._telemetry.width() == before + 120
    assert int(application_settings().value(module.SIDE_WIDTH_KEY)) == before + 120

    again = _view(qtbot)
    assert again.side_width() == before + 120
    assert again._telemetry.width() == before + 120


def test_the_column_never_takes_the_controls_room(qtbot):
    view = _view(qtbot)
    view._side_grip.pressed.emit()
    view._side_grip.dragged.emit(-5000)
    low, high = view._side_bounds()
    assert view.side_width() == high
    view._side_grip.dragged.emit(5000)
    assert view.side_width() == low == module.SIDE_MIN_WIDTH


def test_double_click_gives_the_default_split_back(qtbot):
    view = _view(qtbot)
    view._side_grip.pressed.emit()
    view._side_grip.dragged.emit(-100)
    view._side_grip.released.emit()
    view._side_grip.double_clicked.emit()
    assert view.side_width() == 0
    assert application_settings().value(module.SIDE_WIDTH_KEY) is None
    assert view._workspace.columnStretch(2) == module.TELEMETRY_STRETCH


def test_a_narrow_window_stacks_and_hides_the_bar(qtbot):
    view = _view(qtbot)
    view._side_grip.pressed.emit()
    view._side_grip.dragged.emit(-100)
    view._reflow(module.STACK_WIDTH - 200)
    assert view._side_grip.isHidden()
    assert view._telemetry.maximumWidth() > 10000
    view._reflow(module.STACK_WIDTH + 400)
    assert not view._side_grip.isHidden()
