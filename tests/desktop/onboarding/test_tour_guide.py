"""The guided walk: where it points, what it skips, and how it ends.

The rule that shapes most of this is that a tour must never be a trap. It can
be left at any stop, it goes backwards, and a stop whose anchor is not on this
board — a panel that belongs to another governor, a control the layout folded
away — is skipped rather than pointed at from nowhere.
"""

import pytest
from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from frontends.desktop.onboarding.tour import TourGuide, TourStop


class FakeWindow(QWidget):
    """Only what a stop asks of a window: some anchors and navigate()."""

    def __init__(self):
        super().__init__()
        self.resize(1200, 800)
        layout = QVBoxLayout(self)
        self.first = QPushButton("uno", self)
        self.second = QPushButton("dos", self)
        for button in (self.first, self.second):
            button.setFixedSize(120, 40)
            layout.addWidget(button)
        self.visited: list[str] = []

    def navigate(self, key: str) -> None:
        self.visited.append(key)


def _stops(window, *, missing=False):
    stops = [
        TourStop("dashboard", lambda w: w.first, "Primera", "cuerpo uno"),
        TourStop("cpu", lambda w: w.second, "Segunda", "cuerpo dos"),
    ]
    if missing:
        stops.insert(1, TourStop("gpu", lambda w: None, "Ausente", "no está"))
    return tuple(stops)


@pytest.fixture
def guided(qtbot):
    window = FakeWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    guide = TourGuide(window, _stops(window))
    yield guide
    guide.stop()


def test_a_tour_with_no_stops_ends_immediately(qtbot):
    window = FakeWindow()
    qtbot.addWidget(window)
    guide = TourGuide(window, ())
    seen = []
    guide.finished.connect(lambda: seen.append(True))

    guide.start()

    assert seen == [True]
    assert guide.running is False


def test_it_starts_at_the_first_stop_and_navigates_to_its_page(guided, qtbot):
    guided.start()
    qtbot.waitUntil(lambda: not guided.callout.isHidden(), timeout=3000)

    assert guided.running
    assert guided.index == 0
    assert guided._window.visited == ["dashboard"]
    assert guided.callout.title.text() == "Primera"
    assert guided.callout.step_label.text() == "1 / 2"


def test_the_spotlight_opens_over_the_anchor(guided, qtbot):
    guided.start()
    qtbot.waitUntil(lambda: not guided.spotlight.hole().isNull(), timeout=3000)

    hole = guided.spotlight.hole()
    anchor = guided._window.first
    assert hole.contains(anchor.geometry().center())
    assert hole.width() > anchor.width()


def test_going_on_reaches_the_next_stop_and_its_page(guided, qtbot):
    guided.start()
    qtbot.waitUntil(lambda: guided.index == 0, timeout=3000)

    guided.go_next()
    qtbot.waitUntil(lambda: guided.callout.title.text() == "Segunda", timeout=3000)

    assert guided.index == 1
    assert guided._window.visited == ["dashboard", "cpu"]
    assert guided.callout.step_label.text() == "2 / 2"


def test_the_first_stop_offers_no_way_back(guided, qtbot):
    guided.start()
    qtbot.waitUntil(lambda: guided.index == 0, timeout=3000)

    assert guided.callout.back_button.isHidden()
    guided.go_back()
    assert guided.index == 0


def test_going_back_returns_to_the_previous_stop(guided, qtbot):
    guided.start()
    guided.go_next()
    qtbot.waitUntil(lambda: guided.index == 1, timeout=3000)

    guided.go_back()

    assert guided.index == 0


def test_going_on_past_the_last_stop_ends_the_tour(guided, qtbot):
    seen = []
    guided.finished.connect(lambda: seen.append(True))
    guided.start()
    guided.go_next()
    qtbot.waitUntil(lambda: guided.index == 1, timeout=3000)

    guided.go_next()

    assert seen == [True]
    assert guided.running is False
    assert guided.callout.isHidden()
    assert guided.spotlight.isHidden()


def test_leaving_early_ends_it_and_clears_the_screen(guided, qtbot):
    seen = []
    guided.finished.connect(lambda: seen.append(True))
    guided.start()
    qtbot.waitUntil(lambda: guided.index == 0, timeout=3000)

    guided.callout.end_button.click()

    assert seen == [True]
    assert guided.spotlight.isHidden()


def test_ending_a_tour_that_never_ran_reports_nothing(guided):
    seen = []
    guided.finished.connect(lambda: seen.append(True))

    guided.stop()

    assert seen == []


def test_a_stop_whose_anchor_is_not_on_this_board_is_skipped(qtbot):
    """Boards differ; a bubble pointing at nothing is worse than no bubble."""
    window = FakeWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    guide = TourGuide(window, _stops(window, missing=True))

    guide.start()
    guide.go_next()
    qtbot.waitUntil(lambda: guide.callout.title.text() == "Segunda", timeout=4000)

    assert guide.index == 2
    guide.stop()


def test_an_anchor_that_raises_is_treated_as_absent(qtbot):
    def explode(_window):
        raise RuntimeError("this page was never built")

    window = FakeWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    guide = TourGuide(window, (
        TourStop("gpu", explode, "Rota", "cuerpo"),
        TourStop("cpu", lambda w: w.second, "Segunda", "cuerpo dos"),
    ))

    guide.start()
    qtbot.waitUntil(lambda: guide.callout.title.text() == "Segunda", timeout=4000)

    assert guide.running
    guide.stop()


# ----------------------------------------------------------------- the bubble


def test_the_bubble_stays_inside_the_window_and_points_at_the_hole(guided, qtbot):
    guided.start()
    qtbot.waitUntil(lambda: not guided.callout.isHidden(), timeout=3000)
    callout = guided.callout
    window = guided._window

    assert callout.x() >= 0
    assert callout.y() >= 0
    assert callout.x() + callout.width() <= window.width()
    assert callout.y() + callout.height() <= window.height()


def test_the_tail_finds_a_side_even_for_an_anchor_in_the_corner(qtbot):
    """Below, above, beside — one of them has to work in a small window."""
    window = FakeWindow()
    qtbot.addWidget(window)
    window.resize(420, 300)
    window.show()
    qtbot.waitExposed(window)
    guide = TourGuide(window, _stops(window))

    guide.start()
    qtbot.waitUntil(lambda: not guide.callout.isHidden(), timeout=3000)

    assert guide.callout._side in {"top", "bottom", "left", "right"}
    assert guide.callout.x() >= 0
    guide.stop()


def test_the_spotlight_follows_the_window_when_it_is_resized(guided, qtbot):
    guided.start()
    qtbot.waitUntil(lambda: guided.running, timeout=3000)
    guided._window.resize(900, 620)

    guided.reposition()

    assert guided.spotlight.size() == guided._window.size()


def test_repositioning_an_idle_tour_does_nothing(guided):
    guided.reposition()

    assert guided.spotlight.isHidden()


def test_the_hole_travels_rather_than_jumping(guided, qtbot):
    """The eye has to be able to follow it from one control to the next."""
    guided.start()
    qtbot.waitUntil(lambda: not guided.spotlight.hole().isNull(), timeout=3000)
    first = QRect(guided.spotlight.hole())

    guided.spotlight.move_to(QRect(500, 400, 120, 40))

    assert guided.spotlight._travel.state() != guided.spotlight._travel.State.Stopped
    assert guided.spotlight.hole() == first, "it jumped instead of travelling"


# ------------------------------------------------- where the bubble ends up

def test_the_bubble_points_at_the_new_control_not_the_last_one(qtbot):
    """The spotlight animates; its live rectangle is the *previous* anchor.

    Placing the bubble against that put every label beside the control before
    the one being described — which on screen looked exactly like a bubble
    that had landed at random.
    """
    window = FakeWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    guide = TourGuide(window, _stops(window))

    guide.start()
    qtbot.waitUntil(lambda: not guide.callout.isHidden(), timeout=3000)
    guide.go_next()
    qtbot.waitUntil(lambda: guide.callout.title.text() == "Segunda", timeout=3000)

    second = window.second
    target = QRect(second.mapTo(window, second.rect().topLeft()), second.size())
    bubble = guide.callout.geometry()
    # Within one bubble's length of the control it describes, on some side.
    assert abs(bubble.center().x() - target.center().x()) < bubble.width()
    assert abs(bubble.center().y() - target.center().y()) < bubble.height() * 2
    guide.stop()


def test_a_stop_can_arrange_its_page_before_being_measured(qtbot):
    """A control on an unopened tab is invisible, and invisible means skipped."""
    window = FakeWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    window.second.hide()
    opened = []

    def reveal(host):
        opened.append(True)
        host.second.show()

    guide = TourGuide(window, (
        TourStop("cpu", lambda w: w.second, "Segunda", "cuerpo", arrange=reveal),
    ))

    guide.start()
    qtbot.waitUntil(lambda: not guide.callout.isHidden(), timeout=3000)

    assert opened == [True]
    assert guide.callout.title.text() == "Segunda"
    guide.stop()


def test_an_arrange_that_raises_does_not_take_the_tour_down(qtbot):
    def explode(_window):
        raise RuntimeError("that tab does not exist on this board")

    window = FakeWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    guide = TourGuide(window, (
        TourStop("cpu", lambda w: w.first, "Primera", "cuerpo", arrange=explode),
    ))

    guide.start()
    qtbot.waitUntil(lambda: not guide.callout.isHidden(), timeout=3000)

    assert guide.running
    guide.stop()


def test_several_widgets_are_highlighted_as_one(qtbot):
    """The dashboard's readings are one subject spread over two blocks."""
    window = FakeWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    guide = TourGuide(window, (
        TourStop("dashboard", lambda w: [w.first, w.second], "Ambas", "cuerpo"),
    ))

    guide.start()
    qtbot.waitUntil(lambda: not guide.spotlight.hole().isNull(), timeout=3000)

    hole = guide.spotlight.target()
    for widget in (window.first, window.second):
        rect = QRect(widget.mapTo(window, widget.rect().topLeft()), widget.size())
        assert hole.contains(rect), "one of the two was left outside the box"
    guide.stop()


def test_the_bubble_follows_a_control_that_moves_under_it(qtbot):
    """Pages refresh on their own timers; a label placed once drifts off."""
    window = FakeWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    guide = TourGuide(window, _stops(window))

    guide.start()
    qtbot.waitUntil(lambda: not guide.callout.isHidden(), timeout=3000)
    before = QRect(guide.spotlight.target())

    window.first.move(window.first.x(), window.first.y() + 160)
    qtbot.waitUntil(lambda: guide.spotlight.target() != before, timeout=4000)

    assert guide.spotlight.target().top() > before.top()
    guide.stop()


def test_an_anchor_below_the_fold_is_scrolled_into_view(qtbot):
    """Half of these pages are taller than the window."""
    from PyQt6.QtWidgets import QScrollArea

    from frontends.desktop.onboarding.tour import reveal_in_scroll_area

    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 300)
    area = QScrollArea(host)
    area.setWidgetResizable(True)
    area.resize(400, 300)
    content = QWidget()
    column = QVBoxLayout(content)
    buried = None
    for index in range(30):
        button = QPushButton(f"fila {index}", content)
        button.setFixedHeight(40)
        column.addWidget(button)
        if index == 25:
            buried = button
    area.setWidget(content)
    host.show()
    qtbot.waitExposed(host)

    assert area.verticalScrollBar().value() == 0
    assert reveal_in_scroll_area(buried) is True
    assert area.verticalScrollBar().value() > 0
    # And again is a no-op, which is what stops the settle loop repeating.
    assert reveal_in_scroll_area(buried) is False


def test_a_widget_outside_any_scroll_area_is_left_alone(qtbot):
    from frontends.desktop.onboarding.tour import reveal_in_scroll_area

    window = FakeWindow()
    qtbot.addWidget(window)

    assert reveal_in_scroll_area(window.first) is False


def test_the_bubble_is_tall_enough_for_its_text_in_every_language(qtbot):
    """No translation may have its last line cut off.

    The bubble is a fixed width, so its height is entirely a function of how
    many lines the text wraps into — and every language wraps into a different
    number. Sizing it from the layout's size hint measured each wrapped label
    at the width it would have chosen for itself rather than at the 340 pixels
    it actually gets, which is one line short as soon as a translation runs
    longer than the English. Checked here for all of them at once, because the
    one that overflows is never the one being edited.
    """
    from frontends.desktop import i18n, theme
    from frontends.desktop.onboarding.script import tour_stops
    from frontends.desktop.onboarding.tour import TourCallout

    window = FakeWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    # The fonts come from the stylesheet; measuring without it measures a
    # bubble nobody ever sees.
    window.setStyleSheet(theme.application_stylesheet("dark", "green"))
    original = i18n.current_language()
    callout = TourCallout(window)
    try:
        for language in sorted(i18n.SUPPORTED_LANGUAGES):
            i18n.set_language(language)
            for index, stop in enumerate(tour_stops()):
                callout.set_stop(
                    title=stop.title,
                    body=stop.body,
                    index=index + 1,
                    total=13,
                    last=False,
                    points=stop.points,
                    ordered=stop.ordered,
                    footnote=stop.footnote,
                )
                callout.point_at(QRect(600, 400, 120, 40))
                needed = callout._root.totalHeightForWidth(callout.width())
                assert callout.height() >= needed, (
                    f"{language} stop {index + 1} is {needed - callout.height()}px short"
                )
    finally:
        i18n.set_language(original)


def test_a_stop_with_a_list_widens_the_bubble_and_numbers_its_steps(qtbot):
    """The firmware stops carry a list; the bubble grows for it and shrinks back."""
    from frontends.desktop.onboarding.tour import TourCallout

    window = FakeWindow()
    qtbot.addWidget(window)
    window.show()
    callout = TourCallout(window)
    callout.set_stop(
        title="Pasos", body="cuerpo", index=1, total=2, last=False,
        points=("uno", "dos"), ordered=True, footnote="nota",
    )
    callout.point_at(QRect(600, 400, 120, 40))
    assert callout.width() == TourCallout.WIDE_WIDTH
    assert callout.points.isVisibleTo(callout) and callout.footnote.isVisibleTo(callout)
    markers = [label.text() for label in callout.points.findChildren(QLabel, "tourPointMarker")]
    assert markers == ["1.", "2."]

    callout.set_stop(title="Otra", body="cuerpo", index=2, total=2, last=True)
    qtbot.waitUntil(lambda: not callout.points.findChildren(QLabel, "tourPointMarker"))
    assert callout.width() == TourCallout.WIDTH
    assert not callout.points.isVisibleTo(callout) and not callout.footnote.isVisibleTo(callout)
