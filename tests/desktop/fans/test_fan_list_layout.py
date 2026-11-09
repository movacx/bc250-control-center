"""The board is a compact table, with a responsive editor and text controls."""

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QLabel, QPushButton, QTableView, QWidget

from frontends.desktop.pages.fans import (
    BIOS,
    BOARD_CHANNELS,
    COLUMNS,
    RPM,
    FanCurvePlot,
)
from tests.desktop.fans.test_fan_page import make_page


def test_five_board_headers_always_listed_in_bios_order_at_zero_rpm(qtbot, monkeypatch):
    page, _, _ = make_page(qtbot, monkeypatch)
    for fan in page.current_state["sensores"]["fans"]:
        fan["rpm"] = 0
    page._render()
    assert isinstance(page.table, QTableView)
    assert page.model.columnCount() == 8
    assert [label for label, _ in COLUMNS] == ["Fan", "BIOS", "Mode", "Follows", "°C", "PWM %", "RPM", "State"]
    expected = [2, 3, 4, 5, 1]
    assert set(BOARD_CHANNELS) == set(expected)
    assert [page.model.pwm_at(i) for i in range(page.model.rowCount())] == expected
    for row in range(5):
        assert page.model.data(page.model.index(row, BIOS)) == str(row + 1)
        assert page.model.data(page.model.index(row, RPM)) == "0"


@pytest.mark.parametrize("width,orientation", [(1400, Qt.Orientation.Horizontal), (1059, Qt.Orientation.Vertical), (1060, Qt.Orientation.Horizontal), (720, Qt.Orientation.Vertical)])
def test_splitter_breakpoint(qtbot, monkeypatch, width, orientation):
    page, _, _ = make_page(qtbot, monkeypatch)
    page.resize(width, 900)
    page.show()
    qtbot.waitUntil(lambda: page.splitter.orientation() == orientation)
    assert page.width() == width


def test_page_uses_text_without_icon_badges_or_card_headers(qtbot, monkeypatch):
    """The one page card has no header (no title, no icon badge), like Processes."""
    page, _, _ = make_page(qtbot, monkeypatch)
    assert not any(type(widget).__name__ == "IconBadge" and widget.isVisible() for widget in page.findChildren(QWidget))
    cards = [widget for widget in page.findChildren(QWidget) if type(widget).__name__ == "SectionCard"]
    assert cards == [page.panel]
    assert not any(label.isVisible() and label.property("cardTitle") for label in page.findChildren(QLabel))
    for button in page.findChildren(QPushButton):
        assert button.icon().isNull(), button.text()
    for label in page.findChildren(QLabel):
        assert label.pixmap() is None or label.pixmap().isNull(), label.text()


def test_the_page_is_one_card_with_the_standard_shell(qtbot, monkeypatch):
    """Same shell as Processes and Black box; no Thermal view (the Sensors
    list under Performance shows every temperature)."""
    page, _, _ = make_page(qtbot, monkeypatch)
    margins = page.content.layout().contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (18, 8, 18, 20)
    assert page.panel.property("pageCard") is True
    assert page.panel.isAncestorOf(page.table) and page.panel.isAncestorOf(page.editor)
    assert not hasattr(page, "thermal_table") and not hasattr(page, "tabs")


def test_the_curve_chart_numbers_its_points_and_reads_the_one_under_the_pointer(qtbot):
    plot = FanCurvePlot()
    qtbot.addWidget(plot)
    plot.set_curve([(45, 70), (60, 90), (68, 100), (73, 100), (78, 100), (83, 100), (88, 100), (93, 100)])
    plot.set_live(62.9, 90, "cpu")
    plot.set_target(4)
    plot.resize(900, 460)
    plot.show()
    qtbot.wait(5)
    assert plot.scale.minimumHeight() >= 420
    assert plot.live_text() == "PWM 4 · CPU 62.9 °C → 90%"
    positions = plot.scale._point_positions()
    assert len(positions) == 8
    assert plot.scale.point_at(positions[3]) == 3
    assert plot.scale.point_at(QPointF(positions[3].x() + 40, positions[3].y() + 60)) is None
