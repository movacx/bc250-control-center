"""Monitoring keeps recording while you look at something else.

Sampling used to stop the moment the page was hidden, so every visit to
another page (or a minimised window) left a hole in the two-minute history,
and the graph drew each hole as a break in the line. Sampling now runs
whichever page is on screen; only the drawing waits for the page.
"""

from __future__ import annotations

import pytest

from frontends.desktop.pages.performance import PerformancePage

SAMPLE = {
    "cpu": {"usage_percent": 9.0, "frequency_mhz": 1070, "temperature_c": 47.4, "load_average": [1.99]},
    "gpu": {"usage_percent": 40.0, "frequency_mhz": 1500, "vram_used": 3 * 1024 ** 3, "vram_total": 8 * 1024 ** 3},
    "memory": {"usage_percent": 38.0, "used": 6 * 1024 ** 3, "total": 16 * 1024 ** 3, "available": 10 * 1024 ** 3},
    "disk": {"usage_percent": 61.0, "used": 300 * 1024 ** 3, "total": 500 * 1024 ** 3,
             "read_bps": 2 * 1024 ** 2, "write_bps": 0},
    "network": {"download_bps": 1.2 * 1024 ** 2, "upload_bps": 200 * 1024, "interface": "enp3s0"},
}


class _Controller:
    def __init__(self):
        self.samples = 0

    def metricas_tiempo_real(self):
        self.samples += 1
        return {**SAMPLE, "cpu": {**SAMPLE["cpu"], "usage_percent": float(self.samples % 90)}}


@pytest.fixture
def page(qtbot):
    page = PerformancePage(_Controller())
    qtbot.addWidget(page)
    page.resize(1400, 900)
    page.show()
    # Fast ticks: the behaviour under test is "keeps ticking", not the rate.
    page.timer.setInterval(20)
    yield page
    page.stop_recording()


def test_sampling_continues_while_another_page_is_on_screen(page, qtbot):
    page.set_updates_active(True)
    qtbot.waitUntil(lambda: len(page.histories["cpu"].times) >= 2, timeout=3000)

    page.set_updates_active(False)
    page.hide()
    before = len(page.histories["cpu"].times)
    qtbot.waitUntil(lambda: len(page.histories["cpu"].times) >= before + 3, timeout=3000)

    assert page.timer.isActive()


def test_hidden_samples_are_recorded_but_not_drawn(page, qtbot):
    page.hide()
    shown_primary = page.detail.primary.text()
    page._sample_ready(SAMPLE)

    assert len(page.histories["cpu"].times) == 1
    assert page.detail.primary.text() == shown_primary

    page.show()
    # Coming back catches up on what was recorded meanwhile.
    assert page.detail.primary.text() == "9%"


def test_a_visible_page_draws_every_sample(page):
    page._sample_ready(SAMPLE)
    assert page.detail.primary.text() == "9%"
    # The CPU tile carries its reading into its views menu, not a tooltip.
    assert page.tiles["cpu"].reading[0] == "9%"
    assert "Download" in page.tiles["network"].toolTip() or "MiB" in page.tiles["network"].toolTip()


def test_the_history_has_no_break_across_a_visit_elsewhere(page, qtbot):
    page.set_updates_active(True)
    qtbot.waitUntil(lambda: len(page.histories["cpu"].times) >= 2, timeout=3000)
    page.hide()
    qtbot.wait(150)
    page.show()
    qtbot.waitUntil(lambda: len(page.histories["cpu"].times) >= 10, timeout=3000)

    page.detail.graph.set_history(page.histories["cpu"])
    assert len(page.detail.graph.segments("Usage")) == 1


def test_recording_stops_for_good_when_asked(page, qtbot):
    page.start_recording()
    assert page.timer.isActive()
    page.stop_recording()
    count = len(page.histories["cpu"].times)
    qtbot.wait(120)
    assert not page.timer.isActive()
    assert len(page.histories["cpu"].times) <= count + 1


def test_starting_twice_keeps_one_recorder(page):
    page.start_recording()
    timer_id = page.timer.timerId()
    page.start_recording()
    assert page.timer.timerId() == timer_id
