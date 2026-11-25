"""The sensor list beside CPU, compute units and GPU."""

from __future__ import annotations

import curses
from types import SimpleNamespace
from unittest import mock

import pytest

from bc250cc.infrastructure.sensor_inventory import SensorReading
from frontends.desktop.core.performance_model import PerformanceRecorder
from frontends.tui.layout import side_widths
from frontends.tui.pages import build_pages
from frontends.tui.screen import Screen
from scripts.qa.tui.render import Window
from tests.tui.fakes import make_context


def readings():
    def one(key, group, label, value, unit, kind):
        return SensorReading(key=key, group=group, device=group, kind=kind, label=label, value=value, unit=unit)

    return [one(f"c{n}", "cpu", f"cpu{n}", 1000.0 + n, "MHz", "clock") for n in range(60)] + [
        one("g", "gpu", "edge", 91.0, "°C", "temperature"), one("s", "storage", "lastone", 5.0, "%", "usage")]


@pytest.fixture
def make_screen():
    patches = [mock.patch.object(curses, name, value, create=True) for name, value in (
        ("has_colors", lambda: False), ("color_pair", lambda n: n << 8), ("COLORS", 0))]
    for patch in patches:
        patch.start()

    def make(page, width=195, height=45):
        ctx = make_context()
        recorder = ctx.state("performance")["recorder"] = PerformanceRecorder(depth=60)
        recorder.sensors = False
        recorder.record(ctx.metrics, readings())
        screen = Screen(Window(width, height), ctx, build_pages(), None, theme="mono",
                        foreground=lambda label, work: (True, work()))
        ctx.page_data[page] = screen.pages[page].load(ctx)
        screen.goto(page)
        screen._focus("content")
        screen.draw()
        return screen

    yield make
    for patch in patches:
        patch.stop()


def text(screen):
    window = screen.stdscr
    return "\n".join("".join(window.cells.get((y, x), (" ", 0))[0] for x in range(window.width))
                     for y in range(window.height))


@pytest.mark.parametrize("page,first", [("cpu", "cpu0"), ("gpu", "edge"), ("cu", "edge")])
def test_the_list_starts_with_what_the_page_controls(make_screen, page, first):
    screen = make_screen(page)
    assert first in text(screen)
    assert screen._rendered_layout.side.rows[1].spans[0][0].strip() == first
    assert screen.ctx.state("performance")["recorder"].sensors


def test_the_list_scrolls_alone(make_screen):
    screen = make_screen("cpu")
    cursor = dict(screen.cursor)
    assert "lastone" not in text(screen)
    for _ in range(6):
        screen.handle_key("pgdn")
        screen.draw()
    assert "lastone" in text(screen) and screen.cursor == cursor
    assert "Operating profile" in text(screen) and "Live" in text(screen)
    screen._event = lambda: SimpleNamespace(kind="up", x=150, y=20, shift=False)
    before = screen.side_scroll["cpu"]
    screen._mouse()
    assert screen.side_scroll["cpu"] == before - 3 and screen.cursor == cursor


def test_a_narrow_screen_keeps_the_page_as_it_was(make_screen):
    screen = make_screen("cpu", width=90)
    assert screen._rendered_layout.side is None
    assert "Live" in "".join(t for row in screen.build().rows for t, _tone in row.spans)
    assert not screen.ctx.state("performance")["recorder"].sensors


def test_the_page_never_loses_the_columns_it_needs():
    for width in range(60, 260):
        widths = side_widths(width, 66)
        assert widths is None or (widths[0] >= 66 and widths[1] >= 46 and sum(widths) < width)
