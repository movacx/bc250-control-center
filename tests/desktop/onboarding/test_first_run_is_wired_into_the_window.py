"""The window's side of the first run.

The panel and the tour are only useful if the window actually raises one,
applies what it is told, and stops floating widgets from being drawn over it.
These check the seams rather than the panel, which has its own file.
"""

import pytest
from PyQt6.QtWidgets import QMainWindow, QWidget

from frontends.desktop.app import ControlCenterWindow
from frontends.desktop.onboarding import TourGuide, WelcomeOverlay, tour_stops


def test_the_window_offers_the_two_entry_points():
    """Settings promises a way back to the tour; it has to exist."""
    for name in ("open_welcome", "start_tour", "is_presenting_overlay"):
        assert callable(getattr(ControlCenterWindow, name, None)), name


def test_the_update_bubble_waits_while_a_panel_covers_the_shell(qtbot):
    """It is a sibling of the panel, so nothing but this stops it landing on top."""
    from frontends.desktop.pages.dashboard import DashboardPage

    source = DashboardPage._place_callout.__code__.co_consts
    assert any(
        isinstance(constant, str) and "is_presenting_overlay" in constant
        for constant in source
    ), "the bubble no longer asks whether something is covering the shell"


@pytest.fixture
def window(qtbot):
    host = QMainWindow()
    host.resize(1200, 800)
    central = QWidget(host)
    host.setCentralWidget(central)
    qtbot.addWidget(host)
    yield host


def test_a_panel_reports_its_answers_in_the_shape_the_window_applies_them(qtbot, window):
    """Three values in one signal, because the window applies them together."""
    panel = WelcomeOverlay(window, mode="dark", accent="cyan", density="compact")
    qtbot.addWidget(panel)
    seen = []
    panel.appearance_chosen.connect(lambda *args: seen.append(args))

    panel._choose_accent("green")

    assert seen == [("dark", "green", "compact")]


def test_the_shipped_tour_visits_pages_the_window_actually_has(qtbot, window):
    """A stop naming a page that does not exist would navigate nowhere."""
    known = {"dashboard", "cpu", "gpu", "cu", "performance", "fans", "processes"}
    for stop in tour_stops():
        assert stop.page in known, stop.page


def test_every_shipped_stop_says_something(qtbot, window):
    for stop in tour_stops():
        assert stop.title.strip()
        assert len(stop.body.split()) >= 8, stop.title


def test_the_route_runs_in_the_order_the_modules_are_used(qtbot, window):
    """Dashboard first and whole, then each module, with fans last.

    The order is a product decision rather than an accident of the file, so it
    is pinned: the readings, the four halves of preparing the board, the CPU's
    two tabs, the GPU, compute units, performance, and the two kinds of fan
    control.
    """
    assert [stop.page for stop in tour_stops()] == [
        "dashboard", "dashboard", "dashboard", "dashboard", "dashboard",
        "cpu", "cpu",
        "gpu",
        "cu",
        "performance",
        "fans", "fans",
        "dashboard",
    ]


def test_the_stops_that_live_on_a_tab_open_it_first(qtbot, window):
    """Four preparation tabs, two CPU tabs, two fan modes: eight in all."""
    arranged = [stop for stop in tour_stops() if stop.arrange is not None]
    assert len(arranged) == 8


def test_a_guide_built_over_a_bare_window_does_not_raise(qtbot, window):
    """Every anchor is missing here, so it must skip its way to the end."""
    guide = TourGuide(window, tour_stops())
    seen = []
    guide.finished.connect(lambda: seen.append(True))

    guide.start()
    qtbot.waitUntil(lambda: seen == [True], timeout=6000)

    assert guide.running is False


def test_a_bubble_already_on_screen_is_taken_down_for_the_panel(qtbot):
    """Asking before appearing is not enough for one that is already there."""
    from frontends.desktop.pages.dashboard import DashboardPage

    assert callable(getattr(DashboardPage, "dismiss_floating_callout", None))
    source = ControlCenterWindow._clear_floating_widgets.__code__.co_consts
    assert any(
        isinstance(constant, str) and constant == "dismiss_floating_callout"
        for constant in source
    ), "the window no longer takes floating bubbles down"


def test_both_overlays_clear_the_screen_before_they_open():
    import inspect

    for name in ("open_welcome", "start_tour"):
        body = inspect.getsource(getattr(ControlCenterWindow, name))
        assert "_clear_floating_widgets" in body, name
