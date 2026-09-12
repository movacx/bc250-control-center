"""The glyphs and the grid have to agree, exactly, at every column.

A terminal positions the cursor, the selection and every coloured cell
background by column number, and draws the text with the font's own advances.
When the two disagree by a fraction of a pixel the error accumulates: DejaVu
Sans Mono advances 7.8125px at the default size, so a cell rounded to 8px
drifts 15px over eighty columns — nearly two characters. The cursor then sits
beside the prompt instead of after it, which is exactly how this was noticed.
"""

from __future__ import annotations

import pytest
from PyQt6.QtGui import QFontMetricsF

from frontends.desktop.console.terminal_view import (
    LINE_HEIGHT,
    PADDING_TOP,
    PADDING_X,
    TerminalView,
)


@pytest.fixture
def view(qtbot):
    widget = TerminalView()
    qtbot.addWidget(widget)
    widget.resize(900, 300)
    return widget


@pytest.mark.parametrize("columns", [1, 2, 10, 40, 80, 120, 200])
def test_text_lands_on_the_grid_at_every_width(view, columns):
    metrics = QFontMetricsF(view.font())
    measured = metrics.horizontalAdvance("M" * columns)
    assert measured == pytest.approx(view._cell_width * columns, abs=0.01), columns


def test_one_glyph_advances_exactly_one_cell(view):
    metrics = QFontMetricsF(view.font())
    assert metrics.horizontalAdvance("M") == pytest.approx(view._cell_width, abs=0.01)


@pytest.mark.parametrize("size", [8, 10, 12, 16, 20])
def test_the_grid_holds_at_every_font_size(view, size):
    view.apply_theme(size)
    metrics = QFontMetricsF(view.font())
    assert metrics.horizontalAdvance("M" * 80) == pytest.approx(
        view._cell_width * 80, abs=0.01
    ), size


def test_the_cell_is_taller_than_the_glyph_so_lines_can_breathe(view):
    metrics = QFontMetricsF(view.font())
    assert view._cell_height > metrics.height()
    assert view._cell_height == pytest.approx(round(metrics.height() * LINE_HEIGHT))


def test_the_baseline_sits_inside_its_own_row(view):
    metrics = QFontMetricsF(view.font())
    assert view._baseline >= metrics.ascent()
    assert view._baseline <= view._cell_height


def test_the_grid_is_inset_from_the_frame(view):
    """Text flush against the edge is the difference between built and emitted."""
    assert PADDING_X > 0 and PADDING_TOP > 0
    columns_without_inset = int(view.viewport().width() // view._cell_width)
    assert view.columns < columns_without_inset


def test_a_click_snaps_to_the_nearest_character_edge(view):
    """These are selection boundaries, so they snap between characters.

    Clicking the left half of a character starts the selection before it and
    the right half starts it after, which is what every text editor does. The
    property worth pinning is that the inset the painter adds is exactly the
    inset the mouse removes, at every column.
    """
    from PyQt6.QtCore import QPointF

    view.screen.resize(80, 10)
    for column in (0, 1, 7, 25, 60):
        left = QPointF(
            PADDING_X + column * view._cell_width + 1,
            PADDING_TOP + view._cell_height / 2,
        )
        _row, landed = view._position_at(left)
        assert landed == column, ("borde izquierdo", column, landed)

        right = QPointF(
            PADDING_X + (column + 1) * view._cell_width - 1,
            PADDING_TOP + view._cell_height / 2,
        )
        _row, landed = view._position_at(right)
        assert landed == column + 1, ("borde derecho", column, landed)


def test_a_click_lands_on_the_row_under_it(view):
    """Rows are addressed from the top of the visible area, not the top of the
    history, so the answer is offset by however far the view is scrolled."""
    from PyQt6.QtCore import QPointF

    top = view.verticalScrollBar().value()
    for row in (0, 1, 4):
        point = QPointF(
            PADDING_X + 1, PADDING_TOP + row * view._cell_height + view._cell_height / 2
        )
        landed, _column = view._position_at(point)
        assert landed == top + row, (row, landed, top)


def test_a_click_on_the_left_inset_selects_the_first_column(view):
    from PyQt6.QtCore import QPointF

    _row, column = view._position_at(QPointF(2.0, PADDING_TOP + 1))
    assert column == 0


# --------------------------------------------- the grid inside the real panel


def _panel(qtbot, height=330, window=(1200, 800)):
    from PyQt6.QtWidgets import QVBoxLayout, QWidget

    from frontends.desktop.console.console_panel import ConsolePanel

    host = QWidget()
    host.resize(*window)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(QWidget(host), 1)
    panel = ConsolePanel(host)
    layout.addWidget(panel)
    qtbot.addWidget(host)
    host.show()
    panel.set_auto_hide(False)
    panel.set_panel_height(height)
    # qtbot keeps only a weak reference, so without this the window is
    # collected the moment this helper returns and takes the panel with it.
    panel._test_window = host
    return panel


def _rows_that_fit(panel) -> int:
    view = panel.view
    return int((view.viewport().height() - PADDING_TOP) // view._cell_height)


@pytest.mark.parametrize("height", [160, 240, 330, 400])
def test_the_grid_never_claims_more_rows_than_it_can_show(qtbot, height):
    """The last lines of a workflow were being drawn under the answer row.

    The grid is sized before the panel finishes sliding, from an estimate of
    how much height it will get. The estimate subtracted the header but not the
    input row, so the grid came out a few rows too tall — and since the guess
    stayed larger than the real viewport forever, nothing ever corrected it.
    """
    panel = _panel(qtbot, height)
    try:
        assert panel.run(["/bin/sleep", "300"], title="Prueba")
        qtbot.waitUntil(lambda: panel.maximumHeight() == panel.panel_height(), timeout=4000)
        qtbot.wait(60)
        assert panel.view.rows <= _rows_that_fit(panel), (
            height, panel.view.rows, _rows_that_fit(panel)
        )
    finally:
        panel.shutdown()


def test_the_estimate_does_not_outlive_the_animation(qtbot):
    panel = _panel(qtbot)
    try:
        assert panel.run(["/bin/sleep", "300"], title="Prueba")
        assert panel.view._expected_height > 0, "the estimate carries the slide"
        qtbot.waitUntil(lambda: panel.view._expected_height == 0, timeout=4000)
    finally:
        panel.shutdown()


def test_captured_text_gets_the_room_the_answer_row_is_not_using(qtbot):
    """No process, no input row, so the grid may use that height instead."""
    panel = _panel(qtbot)
    try:
        with_input = panel._grid_height(with_input=True)
        without_input = panel._grid_height(with_input=False)
        assert without_input > with_input
        assert without_input - with_input == panel.input_row.sizeHint().height()
    finally:
        panel.shutdown()


def test_the_last_line_of_a_workflow_is_inside_the_visible_grid(qtbot):
    """End to end: print more lines than fit and read the bottom one back."""
    panel = _panel(qtbot)
    try:
        script = "for i in $(seq 1 40); do echo linea-$i; done; sleep 300"
        assert panel.run(["/bin/sh", "-c", script], title="Prueba")
        qtbot.waitUntil(lambda: "linea-40" in panel.view.screen.full_text(), timeout=8000)
        qtbot.waitUntil(lambda: panel.maximumHeight() == panel.panel_height(), timeout=4000)
        qtbot.wait(120)

        view = panel.view
        bottom = view.verticalScrollBar().value() + view.rows - 1
        lines = view.screen.all_lines()
        assert bottom < len(lines)
        painted_bottom = PADDING_TOP + view.rows * view._cell_height
        assert painted_bottom <= view.viewport().height(), (
            painted_bottom, view.viewport().height()
        )
    finally:
        panel.shutdown()
