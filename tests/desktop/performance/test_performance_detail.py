"""The performance detail: a reading in the header and the rest for the chart.

The live value used to sit in a band of its own between the title and the
chart. It now shares the title's row, the chart takes the height the band
held, and its scale gets finer as it grows.
"""

from __future__ import annotations

import math

import pytest
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QLabel

from frontends.desktop.components.chart_axes import (
    ticks_for_height,
    zoomed_percent_axis,
)
from frontends.desktop.components.widgets import IconBadge
from frontends.desktop.i18n import set_language, tr
from frontends.desktop.pages.performance import (
    RESOURCE_BY_KEY,
    DetailGraph,
    MetricHistory,
    PerformancePage,
    series_statistics,
)
from frontends.desktop.theme import COLORS

SAMPLE = {
    "cpu": {"usage_percent": 9.0, "frequency_mhz": 1070, "temperature_c": 47.4, "load_average": [1.99]},
    "gpu": {"usage_percent": 40.0, "frequency_mhz": 1500, "vram_used": 3 * 1024 ** 3, "vram_total": 8 * 1024 ** 3},
    "memory": {"usage_percent": 38.0, "used": 6 * 1024 ** 3, "total": 16 * 1024 ** 3, "available": 10 * 1024 ** 3},
    "disk": {"usage_percent": 61.0, "used": 300 * 1024 ** 3, "total": 500 * 1024 ** 3,
             "read_bps": 2 * 1024 ** 2, "write_bps": 0},
    "network": {"download_bps": 1.2 * 1024 ** 2, "upload_bps": 200 * 1024, "interface": "enp3s0"},
}


@pytest.fixture
def page(qtbot):
    page = PerformancePage(object())
    qtbot.addWidget(page)
    page.resize(1400, 900)
    page.show()
    qtbot.wait(5)
    return page


def test_the_reading_sits_beside_the_name_with_no_icon_or_band(page):
    page._sample_ready(SAMPLE)
    detail = page.detail
    assert detail.primary.text() == "9%"
    assert detail.context.text() == "1.07 GHz"
    # "CPU 9% 1.07 GHz" on one line, then the description and the window
    # statistics, then the chart.
    assert detail.primary.x() > detail.title.x() + detail.title.width()
    assert detail.context.x() > detail.primary.x() + detail.primary.width()
    for label in (detail.primary, detail.context):
        assert label.geometry().top() < detail.title.geometry().bottom()
        assert label.geometry().bottom() > detail.title.geometry().top()
    assert detail.title.geometry().bottom() <= detail.subtitle.y()
    assert detail.subtitle.geometry().bottom() <= detail.graph.y()
    assert abs(detail.legend.y() - detail.subtitle.y()) < 12
    assert detail.legend.x() > detail.subtitle.x()
    assert not detail.findChildren(IconBadge)
    assert not [label for label in detail.findChildren(QLabel) if label.text() == tr("CURRENT")]
    # The sampling state moved to the footer, beside the sample count.
    assert abs(detail.sample_state.y() - detail.footer_left.y()) < 12


def test_a_narrow_panel_stacks_the_description_and_statistics(qtbot, page):
    page.resize(420, 900)
    qtbot.wait(5)
    page._sample_ready(SAMPLE)
    detail = page.detail
    assert detail.primary.x() > detail.title.x()
    assert detail.legend.y() > detail.subtitle.y()
    assert page.scroll.horizontalScrollBar().maximum() == 0


def test_the_legend_carries_the_window_statistics(page):
    for usage in (4.0, 9.0, 14.0):
        page._sample_ready({**SAMPLE, "cpu": {**SAMPLE["cpu"], "usage_percent": usage}})
    legend = page.detail.legend.text().replace("&nbsp;", " ")
    for value in ("4.0%", "9.0%", "14.0%"):
        assert value in legend
    assert series_statistics(page.histories["cpu"], "Usage") == (4.0, 9.0, 14.0)

    page._select_resource("disk")
    legend = page.detail.legend.text().replace("&nbsp;", " ")
    # Throughput has no useful minimum (it idles at zero): average and peak.
    assert tr("Read") in legend and tr("Write") in legend
    assert "min" not in legend and "2.0 MiB/s" in legend


def test_the_legend_and_captions_follow_a_language_change(page):
    page._sample_ready(SAMPLE)
    try:
        set_language("es")
        page.retranslate_dynamic_copy()
        assert page.detail.stats[0].label.text() == tr("Frequency").upper()
        assert "mín" in page.detail.legend.text()
    finally:
        set_language("en")


def test_a_taller_chart_gets_a_finer_scale():
    assert ticks_for_height(200) == 4
    assert ticks_for_height(520) == 10
    assert ticks_for_height(2000) == 10
    coarse, fine = zoomed_percent_axis(14.7, target_ticks=5), zoomed_percent_axis(14.7, target_ticks=10)
    assert coarse.step == 5 and fine.step == 2
    assert fine.maximum >= 14.7


def test_a_missed_sample_breaks_the_line():
    history = MetricHistory(RESOURCE_BY_KEY["cpu"])
    for moment in (0, 1, 2, 3, 10, 11):
        history.append({"Usage": moment}, moment=moment)
    graph = DetailGraph()
    graph.set_history(history)
    runs = graph.segments("Usage")
    assert [[moment for moment, _value in run] for run in runs] == [[0, 1, 2, 3], [10, 11]]


def test_the_area_under_a_hump_is_filled(qtbot):
    """A brush left on the painter used to close the line back to its start.

    That painted the chart background over everything between the line and
    the straight chord from its first to its last point, so the fill under a
    curve looked like a flat wedge.
    """
    history = MetricHistory(RESOURCE_BY_KEY["gpu"])
    for moment in range(120):
        history.append({"Usage": 90 * math.sin(math.pi * moment / 119)}, moment=100 + moment)
    graph = DetailGraph()
    qtbot.addWidget(graph)
    graph.set_history(history)
    graph.set_scale_mode("full")
    graph.resize(640, 400)
    graph.show()
    image = graph.grab().toImage()
    background = QColor(COLORS["chart_surface"])
    # Well inside the hump, halfway between the chord (at 0 %) and the line.
    x = int(graph.width() * 0.55)
    y = int(graph.height() * 0.55)
    assert image.pixelColor(x, y) != background


def test_the_pointer_moves_over_a_cached_chart(qtbot, monkeypatch):
    """Every mouse move redrew the whole chart; now only a sample redraws it.

    Six per-core clock lines swinging 1.5–3.5 GHz took over a second a frame
    to stroke on the BC-250, and the window froze while the pointer was on it.
    """
    history = MetricHistory(RESOURCE_BY_KEY["cpu"])
    for moment in range(120):
        history.append({"Usage": 5 if moment % 2 else 95}, moment=100 + moment)
    graph = DetailGraph()
    qtbot.addWidget(graph)
    graph.set_history(history)
    graph.resize(900, 420)
    graph.show()
    renders = []
    original = DetailGraph._render
    monkeypatch.setattr(DetailGraph, "_render", lambda self, painter: renders.append(1) or original(self, painter))

    graph.grab()
    for x in range(100, 800, 70):
        graph._hover_x, graph._hover_y = float(x), 200.0
        graph.grab()
    assert len(renders) == 1

    history.append({"Usage": 50}, moment=220)
    graph.grab()
    assert len(renders) == 2


def test_fast_strokes_draw_the_same_line_and_leave_gaps(qtbot):
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QImage, QPainter

    from frontends.desktop.components.chart_strokes import draw_series, fill_area

    image = QImage(200, 100, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("black"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    runs = [[QPointF(10, 90), QPointF(50, 10), QPointF(90, 90)], [QPointF(150, 50), QPointF(190, 50)]]
    fill_area(painter, runs[0], 95.0, QColor("#303030"))
    draw_series(painter, runs, QColor("white"), 2.0)
    painter.end()

    assert image.pixelColor(50, 11).red() > 128  # the apex, where two segments join
    assert image.pixelColor(170, 50).red() > 128  # the second run
    assert image.pixelColor(120, 50) == QColor("black")  # nothing bridges the gap
    assert image.pixelColor(50, 80) == QColor("#303030")  # the area under the first run
