"""The CPU workspace keeps its proportions and stays reachable at any size.

Two regressions a user reported together:

* Reopening the application and letting the window manager maximize it left
  the monitoring column squeezed: the reflow back from the stacked form reset
  its stretch to 1 against the controls' 18.
* A compact window could not be scrolled at all, because the page dropped
  wheel input and hid its scrollbar. The GPU workspace always scrolled.
"""

from PyQt6.QtCore import Qt

from frontends.desktop.pages.cpu_control_view import (
    CONTROLS_STRETCH,
    STACK_WIDTH,
    TELEMETRY_STRETCH,
    CpuControlView,
)
from frontends.desktop.pages.cpu_smu import CpuSmuPage


def test_narrow_then_wide_restores_the_same_split_as_a_wide_first_layout(qtbot):
    view = CpuControlView()
    qtbot.addWidget(view)

    view._reflow(STACK_WIDTH - 200)
    assert view._workspace.itemAtPosition(1, 0) is not None
    assert view._workspace.columnStretch(1) == 0

    view._reflow(STACK_WIDTH + 400)

    assert view._workspace.itemAtPosition(0, 1) is not None
    assert view._workspace.columnStretch(0) == CONTROLS_STRETCH
    assert view._workspace.columnStretch(1) == TELEMETRY_STRETCH


def test_a_compact_window_can_scroll_the_cpu_workspace_like_the_gpu_one(qtbot):
    page = CpuSmuPage(object())
    qtbot.addWidget(page)

    policy = page.scroll.verticalScrollBarPolicy()
    assert policy == Qt.ScrollBarPolicy.ScrollBarAsNeeded

    page.resize(900, 420)
    page.show()
    qtbot.waitUntil(lambda: page.scroll.verticalScrollBar().maximum() > 0, timeout=2000)

    bar = page.scroll.verticalScrollBar()
    bar.setValue(0)
    # A real wheel notch, delivered to the viewport the way the pointer does.
    from PyQt6.QtCore import QPoint, QPointF
    from PyQt6.QtGui import QWheelEvent
    from PyQt6.QtWidgets import QApplication

    viewport = page.scroll.viewport()
    centre = QPointF(viewport.width() / 2, viewport.height() / 2)
    event = QWheelEvent(
        centre,
        QPointF(viewport.mapToGlobal(centre.toPoint())),
        QPoint(0, 0),
        QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(viewport, event)

    assert bar.value() > 0
