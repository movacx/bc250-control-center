"""The update badge: seen when it matters, silent otherwise, free when hidden.

Three footer buttons are always present, so a fourth appearing among them is
easy to miss. It therefore pulses — and because a looping animation on an
invisible widget is pure waste, it has to stop with the widget.

The more important half is what it does *not* do. This badge is driven by the
only network request the application makes on its own, so:

* the dashboard asks in the background and never blocks a frame;
* it asks once per session, not once per visit;
* with the preference off it does not ask at all;
* a failure shows nothing — no dialog, no error row, no badge.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPropertyAnimation

from frontends.desktop.components.dashboard_widgets import (
    DashboardFooter,
    _UpdateBadgeButton,
)


@pytest.fixture
def footer(qtbot):
    widget = DashboardFooter()
    qtbot.addWidget(widget)
    widget.resize(420, 48)
    widget.show()
    return widget


def _running(badge: _UpdateBadgeButton) -> bool:
    return badge._pulse.state() == QPropertyAnimation.State.Running


# ------------------------------------------------------------ when it appears


def test_the_badge_is_absent_until_there_is_something_to_say(footer):
    assert footer.update_button.isHidden()
    assert not _running(footer.update_button)


def test_it_sits_with_the_other_links(footer):
    """One row: this leads, then repositories, contact, support."""
    order = [footer.layout.itemAt(i).widget() for i in range(footer.layout.count())]
    assert order == [
        footer.update_button,
        footer.repositories_button,
        footer.contact_button,
        footer.support_button,
    ]


def test_a_published_version_reveals_it(footer):
    footer.announce_update("1.20.0")
    assert footer.update_button.isVisible()
    assert footer.update_button.published_version == "1.20.0"


def test_no_version_keeps_it_hidden(footer):
    footer.announce_update("1.20.0")
    footer.announce_update("")
    assert footer.update_button.isHidden()


def test_the_tooltip_names_the_version(footer):
    footer.announce_update("1.21.3")
    assert "1.21.3" in footer.update_button.toolTip()
    assert "1.21.3" in footer.update_button.accessibleName()


def test_the_named_version_survives_a_retranslation_pass(footer):
    """The generic pass rewrites tooltips from ``i18nSourceToolTip``.

    Leaving that property set would replace "Version 1.21.3 is available" with
    the untranslated source string on the next language change.
    """
    footer.announce_update("1.21.3")
    assert footer.update_button.property("i18nSourceToolTip") is None
    assert footer.update_button.property("i18nSourceAccessibleName") is None


# ------------------------------------------------------------------ the pulse


def test_it_pulses_while_visible(footer):
    footer.announce_update("1.20.0")
    assert _running(footer.update_button)
    assert footer.update_button._pulse.loopCount() == -1


def test_the_glow_really_moves(qtbot, footer):
    footer.announce_update("1.20.0")
    effect = footer.update_button.graphicsEffect()
    seen: set[float] = set()

    def sample() -> bool:
        seen.add(round(effect.blurRadius(), 1))
        return len(seen) > 2

    qtbot.waitUntil(sample, timeout=4000)
    assert min(seen) >= footer.update_button.GLOW_MIN - 0.5
    assert max(seen) <= footer.update_button.GLOW_MAX + 0.5


def test_the_glow_is_a_glow_and_not_a_shadow(footer):
    """A black drop shadow offset downwards reads as depth, not as attention."""
    effect = footer.update_button.graphicsEffect()
    assert effect.offset().x() == 0 and effect.offset().y() == 0
    assert effect.color().alpha() > 0
    assert effect.color().name() != "#000000"


def test_hiding_it_stops_the_animation(footer):
    footer.announce_update("1.20.0")
    assert _running(footer.update_button)
    footer.announce_update("")
    assert not _running(footer.update_button)


def test_hovering_does_not_fight_the_pulse(footer):
    """Both drive ``blurRadius``; while breathing, the pulse owns it."""
    footer.announce_update("1.20.0")
    footer.update_button._animate_lift(True)
    assert _running(footer.update_button)
    assert footer.update_button._lift.state() != QPropertyAnimation.State.Running


def test_the_badge_has_its_own_icon():
    from frontends.desktop.components.widgets import ICON_DIR

    assert (ICON_DIR / "update_badge.png").is_file()


# ------------------------------------------------- how the dashboard asks


@pytest.fixture
def dashboard_page(qtbot):
    """Build dashboard pages and always disarm them again.

    ``qtbot.addWidget`` holds a weak reference, so a page is collectable the
    moment a test ends — with its five-second timer and its background
    refreshers still armed. A read that lands afterwards reaches into widgets
    Qt has already destroyed, which surfaces as a failure in whichever
    unrelated test happens to run next.
    """
    built = []

    def make():
        from frontends.desktop.pages import dashboard as dashboard_module

        widget = dashboard_module.DashboardPage(object())
        qtbot.addWidget(widget)
        built.append(widget)
        return widget

    yield make
    for widget in built:
        widget.set_updates_active(False)


class _Status:
    def __init__(self, published: str, available: bool) -> None:
        self.published = published
        self.update_available = available


def _lookup(published: str, available: bool, source=None):
    from frontends.desktop.pages.dashboard import _UpdateLookup

    return _UpdateLookup(status=_Status(published, available), source=source)


def _aur_source(helper: str = "paru", package: str = "bc250-control-center-git"):
    from bc250cc.infrastructure.install_source import InstallSource, UpdateChannel

    return InstallSource(UpdateChannel.AUR, package=package, manager="pacman", helper=helper)


def _package_source(manager: str = "rpm"):
    from bc250cc.infrastructure.install_source import InstallSource, UpdateChannel

    return InstallSource(UpdateChannel.PACKAGE, package="bc250-control-center", manager=manager)


@pytest.fixture
def page(monkeypatch, dashboard_page):
    from frontends.desktop.pages import dashboard as dashboard_module

    asked: list[str] = []
    monkeypatch.setattr(
        dashboard_module,
        "_look_for_update",
        lambda: asked.append("lookup") or _lookup("1.20.0", True, _package_source()),
    )
    widget = dashboard_page()
    widget._asked = asked
    return widget


def test_every_arrival_at_the_dashboard_checks_again(monkeypatch, page):
    """Asked on entry, as intended — the cache below makes it cheap.

    Asserted on the call rather than on the worker finishing twice: whether a
    second submission reaches the thread pool depends on a cross-thread signal
    arriving first, which made the earlier version of this test race. That
    submission rule has its own test below.
    """
    arrivals: list[int] = []
    monkeypatch.setattr(page, "_check_for_update", lambda: arrivals.append(1))
    for _ in range(3):
        page.set_updates_active(True)
        page.set_updates_active(False)
    assert len(arrivals) == 3


def test_leaving_the_dashboard_does_not_check(monkeypatch, page):
    arrivals: list[int] = []
    monkeypatch.setattr(page, "_check_for_update", lambda: arrivals.append(1))
    page.set_updates_active(False)
    assert arrivals == []


def test_the_check_actually_reaches_the_worker(qtbot, page):
    page._check_for_update()
    qtbot.waitUntil(lambda: page._asked == ["lookup"], timeout=4000)


def test_a_second_arrival_while_the_first_read_runs_is_not_stacked(page):
    """One read at a time; the executor refuses a duplicate key."""
    page.set_updates_active(True)
    started_again = page._release_executor.start(
        "release-check", lambda: None, lambda _r: None, lambda _m: None
    )
    assert started_again is False


def test_the_answer_reaches_the_badge(qtbot, page):
    page.set_updates_active(True)
    qtbot.waitUntil(lambda: page.update_button.published_version == "1.20.0", timeout=4000)
    # ``isHidden`` rather than ``isVisible``: this page was never shown, and a
    # child of an unshown parent is not visible however it was configured.
    assert not page.update_button.isHidden()


def test_a_version_that_is_not_newer_shows_nothing(qtbot, page):
    page._apply_update_status(_lookup("1.19.0", False))
    assert page.update_button.isHidden()
    assert page.update_callout.isHidden()


def test_an_unreachable_network_shows_nothing(qtbot, page):
    page._apply_update_status(_lookup("", False))
    assert page.update_button.isHidden()
    assert page.update_callout.isHidden()


def test_a_result_of_the_wrong_shape_is_survived(qtbot, page):
    """The worker hands back whatever it got; the badge must not raise on it."""
    page._apply_update_status(None)
    page._apply_update_status("nonsense")
    assert page.update_button.isHidden()


def test_the_preference_off_means_no_request_at_all(monkeypatch, dashboard_page):
    from frontends.desktop.pages import dashboard as dashboard_module

    def explode():  # pragma: no cover - must not be reached
        raise AssertionError("the network was contacted with the check disabled")

    monkeypatch.setattr(dashboard_module, "_look_for_update", explode)
    monkeypatch.setattr(dashboard_module, "update_checks_enabled", lambda: False)
    widget = dashboard_page()
    widget.set_updates_active(True)
    assert widget.update_button.isHidden()


# ------------------------------------------------------------ what it advises


def test_an_aur_install_is_told_to_use_its_helper(page):
    page._apply_update_status(_lookup("1.20.0", True, _aur_source(helper="paru")))
    assert page.update_callout.action_button.text() == "paru -Syu bc250-control-center-git"
    assert "AUR" in page.update_callout.detail.text()


def test_the_helper_that_is_actually_installed_is_the_one_named(page):
    page._apply_update_status(_lookup("1.20.0", True, _aur_source(helper="yay")))
    assert page.update_callout.action_button.text().startswith("yay ")


def test_a_packaged_install_is_sent_to_the_release(page):
    page._apply_update_status(_lookup("1.20.0", True, _package_source("rpm")))
    action = page.update_callout.action_button.text()
    assert "-Syu" not in action
    assert "1.20.0" in page.update_callout.detail.text()


def test_an_unknown_install_is_also_sent_to_the_release(page):
    page._apply_update_status(_lookup("1.20.0", True, None))
    assert "-Syu" not in page.update_callout.action_button.text()


def test_following_the_advice_opens_the_release_for_a_package(monkeypatch, page):
    from frontends.desktop.pages import dashboard as dashboard_module

    opened: list[str] = []
    monkeypatch.setattr(
        dashboard_module, "open_external_url", lambda url: opened.append(url) or (True, "")
    )
    page._apply_update_status(_lookup("1.20.0", True, _package_source()))
    page._follow_update_advice()
    assert opened == [dashboard_module.RELEASES_PAGE_URL]


def test_following_the_advice_never_opens_a_browser_for_an_aur_install(monkeypatch, page):
    from frontends.desktop.pages import dashboard as dashboard_module

    def explode(_url):  # pragma: no cover - must not be reached
        raise AssertionError("an AUR install must not be sent to a download page")

    monkeypatch.setattr(dashboard_module, "open_external_url", explode)
    shown: list[tuple] = []
    monkeypatch.setattr(
        dashboard_module,
        "InfoDialog",
        lambda *args, **kwargs: shown.append(args) or _Dialog(),
    )
    page._apply_update_status(_lookup("1.20.0", True, _aur_source()))
    page._follow_update_advice()
    assert shown and "paru -Syu bc250-control-center-git" in shown[0][1]


class _Dialog:
    def exec(self):
        return 0


# ---------------------------------------------------------------- the bubble


def test_the_bubble_is_absent_until_there_is_an_update(page):
    assert page.update_callout.isHidden()


def test_the_bubble_says_what_it_is(page):
    page._apply_update_status(_lookup("1.20.0", True, _package_source()))
    assert page.update_callout.title.text()
    assert "1.20.0" in page.update_callout.detail.text()


def test_the_bubble_reopens_on_every_visit_while_unaddressed(monkeypatch, page):
    """A dismissed bubble is not a settled matter - it reopens next visit.

    An update ignored once should not go quiet for the rest of the session;
    it comes back the next time the dashboard is reached, same as the badge
    keeps pulsing regardless of the dismissal. Asserted on ``_show_callout``
    directly, because placement itself is deferred through a timer and needs
    a window actually on screen — covered separately below.
    """
    shown: list[str] = []
    monkeypatch.setattr(page, "_show_callout", lambda: shown.append("shown"))
    page._apply_update_status(_lookup("1.20.0", True, _package_source()))
    page.update_callout._dismiss()
    page._apply_update_status(_lookup("1.20.0", True, _package_source()))
    assert shown == ["shown", "shown"]


def test_a_further_release_speaks_up_again(monkeypatch, page):
    shown: list[str] = []
    monkeypatch.setattr(page, "_show_callout", lambda: shown.append("shown"))
    page._apply_update_status(_lookup("1.20.0", True, _package_source()))
    page.update_callout._dismiss()
    page._apply_update_status(_lookup("1.21.0", True, _package_source()))
    assert shown == ["shown", "shown"]
    assert "1.21.0" in page.update_callout.detail.text()


def test_dismissing_the_bubble_leaves_the_badge_pulsing(qtbot, page):
    page._apply_update_status(_lookup("1.20.0", True, _package_source()))
    page.update_callout._dismiss()
    assert not page.update_button.isHidden()
    assert page.update_button.published_version == "1.20.0"


def test_pressing_the_badge_brings_the_bubble_back(monkeypatch, page):
    placed: list[str] = []
    monkeypatch.setattr(page, "_place_callout", lambda: placed.append("placed"))
    page._apply_update_status(_lookup("1.20.0", True, _package_source()))
    page.update_callout._dismiss()
    page._badge_clicked()
    assert placed


def test_pressing_the_badge_never_opens_anything_by_itself(monkeypatch, page):
    """One click must mean one thing.

    It used to fall through to opening a browser whenever the bubble could not
    be placed, so the same press behaved differently depending on whether the
    window was on screen — and in a test it reached a modal dialog and hung.
    """
    from frontends.desktop.pages import dashboard as dashboard_module

    def explode(*_args, **_kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("pressing the badge must not act on its own")

    monkeypatch.setattr(dashboard_module, "open_external_url", explode)
    monkeypatch.setattr(dashboard_module, "InfoDialog", explode)
    page._apply_update_status(_lookup("1.20.0", True, _package_source()))
    page.update_callout._dismiss()
    page._badge_clicked()


def test_the_preference_defaults_to_on():
    """A release nobody hears about helps nobody."""
    from pathlib import Path

    source = Path("frontends/desktop/core/preferences.py").read_text(encoding="utf-8")
    assert 'self.settings.setValue("settings/update_check", "true")' in source


def test_the_check_runs_off_the_interface_thread():
    """Pins the seam: a four-second request must never sit in a frame."""
    from pathlib import Path

    source = Path("frontends/desktop/pages/dashboard.py").read_text(encoding="utf-8")
    assert "self._release_executor = BackgroundExecutor(self)" in source
    assert '"release-check"' in source


# ------------------------------------------- the bubble in a real window


@pytest.fixture
def shown_page(qtbot, monkeypatch, dashboard_page):
    """A dashboard inside a window that is actually on screen.

    The bubble is positioned against the badge's place in the window, so the
    geometry can only be checked once both have one.
    """
    from PyQt6.QtWidgets import QVBoxLayout, QWidget

    from frontends.desktop.pages import dashboard as dashboard_module

    monkeypatch.setattr(
        dashboard_module, "_look_for_update", lambda: _lookup("1.20.0", True, _package_source())
    )
    host = QWidget()
    host.resize(1200, 800)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    page = dashboard_page()
    layout.addWidget(page)
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)
    page._test_window = host
    return page


def _reveal_badge(qtbot, page) -> None:
    """Scroll until the badge is on screen, the way a user reaches it.

    The badge lives in the header of *Prepare BC250 system*, which is some way
    down a page taller than most windows. The bubble is glued to it and is
    only drawn while it can be seen, so these tests have to bring it into view
    first rather than assume it was there all along.
    """
    from PyQt6.QtCore import QPoint

    qtbot.waitUntil(lambda: not page.footer.update_button.isHidden(), timeout=4000)
    if page._badge_is_on_screen():
        return
    scrollbar = page.scroll.verticalScrollBar()
    content = page.scroll.widget()
    target = page.footer.update_button.mapTo(content, QPoint(0, 0)).y()
    scrollbar.setValue(max(0, min(target - 80, scrollbar.maximum())))
    qtbot.waitUntil(page._badge_is_on_screen, timeout=4000)


def test_the_bubble_still_appears_when_the_answer_beats_the_window_on_screen(qtbot):
    """A cached answer can resolve before the main window is shown.

    That is the common shape of a cold start straight into the dashboard:
    the release check often answers from cache, faster than the window
    takes to appear. The bubble must not be dropped on the floor because it
    was asked to place itself one frame too early — it should keep trying
    until the window is actually there.

    Built by hand rather than through the shared ``dashboard_page`` fixture:
    that fixture's own teardown and a manually added host widget disarm the
    page in an order that races Qt's deferred deletion and bleeds an
    exception into an unrelated, later test.
    """
    from PyQt6.QtWidgets import QVBoxLayout, QWidget

    from frontends.desktop.pages import dashboard as dashboard_module

    host = QWidget()
    host.resize(1200, 800)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    page = dashboard_module.DashboardPage(object())
    layout.addWidget(page)
    qtbot.addWidget(host)

    try:
        # The window is not shown yet when the answer arrives.
        page._apply_update_status(_lookup("1.20.0", True, _package_source()))
        assert host.isHidden()

        host.show()
        qtbot.waitExposed(host)
        _reveal_badge(qtbot, page)
        qtbot.waitUntil(lambda: page.update_callout.isVisible(), timeout=4000)
    finally:
        page.set_updates_active(False)


def test_the_tail_points_at_the_badge(qtbot, shown_page):
    from PyQt6.QtCore import QPoint

    shown_page._apply_update_status(_lookup("1.20.0", True, _package_source()))
    _reveal_badge(qtbot, shown_page)
    badge = shown_page.update_button
    callout = shown_page.update_callout
    qtbot.waitUntil(lambda: callout.isVisible(), timeout=4000)

    window = badge.window()
    top_left = badge.mapTo(window, QPoint(0, 0))
    tail = callout.x() + callout._tail_x
    assert abs(tail - (top_left.x() + badge.width() // 2)) <= 2, (
        "the tail does not line up with the badge"
    )
    if callout._tail_below:
        # Flipped above the badge: the bubble must sit entirely clear of it.
        assert callout.y() + callout.height() <= top_left.y() + 4
    else:
        assert callout.y() >= top_left.y() + badge.height()


def test_the_bubble_flips_above_the_badge_when_there_is_no_room_below(qtbot, shown_page):
    """Clamping to the bottom edge would cover the very thing it points at."""
    shown_page._apply_update_status(_lookup("1.20.0", True, _package_source()))
    _reveal_badge(qtbot, shown_page)
    callout = shown_page.update_callout
    qtbot.waitUntil(lambda: callout.isVisible(), timeout=4000)
    badge = shown_page.update_button
    window = badge.window()
    if not callout._tail_below:
        pytest.skip("this window has room below the badge")
    assert callout.y() + callout.height() < window.height()
    assert callout._root.contentsMargins().bottom() > callout.TAIL


def test_the_bubble_stays_inside_the_window(qtbot, shown_page):
    shown_page._apply_update_status(_lookup("1.20.0", True, _package_source()))
    _reveal_badge(qtbot, shown_page)
    callout = shown_page.update_callout
    qtbot.waitUntil(lambda: callout.isVisible(), timeout=4000)
    window = callout.parentWidget()
    assert callout.x() >= 0
    assert callout.x() + callout.width() <= window.width()
    assert callout.y() + callout.height() <= window.height()


def test_the_bubble_floats_over_the_window_and_not_in_a_layout(qtbot, shown_page):
    """It must not reserve space or shift the content underneath it."""
    shown_page._apply_update_status(_lookup("1.20.0", True, _package_source()))
    _reveal_badge(qtbot, shown_page)
    callout = shown_page.update_callout
    qtbot.waitUntil(lambda: callout.isVisible(), timeout=4000)
    assert callout.parentWidget() is shown_page.window()
    # ``page.layout`` is an attribute here, shadowing QWidget.layout().
    assert shown_page.layout.indexOf(callout) == -1


def test_the_bubble_has_room_for_its_tail(qtbot, shown_page):
    """The tail is drawn outside the body, so the layout owes it that margin."""
    callout = shown_page.update_callout
    margins = callout._root.contentsMargins()
    edge = margins.bottom() if callout._tail_below else margins.top()
    assert edge > callout.TAIL


# ------------------------------------------------- where the bubble may appear


def test_the_bubble_belongs_to_the_dashboard_and_leaves_with_it(qtbot, shown_page):
    """It points at a badge on this page; on another module it points at nothing.

    The bubble reparents itself to the window so it can hang outside the
    scroll area, and that is exactly why it does not notice on its own that
    the user has gone somewhere else.
    """
    shown_page._apply_update_status(_lookup("1.20.0", True, _package_source()))
    _reveal_badge(qtbot, shown_page)
    qtbot.waitUntil(lambda: not shown_page.update_callout.isHidden(), timeout=4000)

    shown_page.hide()

    assert shown_page.update_callout.isHidden()


def test_coming_back_to_the_dashboard_asks_for_it_again(qtbot, shown_page):
    shown_page._apply_update_status(_lookup("1.20.0", True, _package_source()))
    _reveal_badge(qtbot, shown_page)
    qtbot.waitUntil(lambda: not shown_page.update_callout.isHidden(), timeout=4000)
    shown_page.hide()
    assert shown_page.update_callout.isHidden()

    shown_page.show()

    qtbot.waitUntil(lambda: not shown_page.update_callout.isHidden(), timeout=4000)


def test_nothing_is_announced_again_when_there_is_no_update(qtbot, shown_page):
    asked = []
    shown_page._show_callout = lambda: asked.append(True)
    shown_page._update_pending = False

    shown_page.hide()
    shown_page.show()

    assert asked == []


def test_a_badge_scrolled_out_of_the_viewport_takes_the_bubble_with_it(qtbot, shown_page):
    """A tail pointing above the viewport labels whatever is under it now."""
    shown_page._apply_update_status(_lookup("1.20.0", True, _package_source()))
    _reveal_badge(qtbot, shown_page)
    qtbot.waitUntil(lambda: not shown_page.update_callout.isHidden(), timeout=4000)

    shown_page.scroll.verticalScrollBar().setValue(0)
    qtbot.waitUntil(lambda: shown_page.update_callout.isHidden(), timeout=4000)

    assert not shown_page._badge_is_on_screen()


def test_scrolling_re_places_the_bubble_rather_than_leaving_it_behind(qtbot, page):
    placed = []
    page._place_callout = lambda: placed.append(True)
    page._update_pending = True

    scrollbar = page.scroll.verticalScrollBar()
    scrollbar.setRange(0, 500)
    scrollbar.setValue(120)

    assert placed == [True]


def test_a_scroll_with_nothing_to_announce_costs_nothing(qtbot, page):
    placed = []
    page._place_callout = lambda: placed.append(True)
    page._update_pending = False

    scrollbar = page.scroll.verticalScrollBar()
    scrollbar.setRange(0, 500)
    scrollbar.setValue(120)

    assert placed == []


def test_the_bubble_follows_a_badge_that_moved_without_a_scroll(qtbot, page):
    """A refresh can relayout the page under it; no scroll is emitted for that."""
    from PyQt6.QtCore import QRect

    placed = []
    page._place_callout = lambda: placed.append(True)
    page._update_pending = True
    page.update_callout.show()
    page._callout_anchored_at = QRect(0, 0, 10, 10)
    page._badge_rect = lambda: QRect(0, 400, 10, 10)

    page._follow_callout()

    assert placed == [True]


def test_a_badge_that_has_not_moved_is_left_alone(qtbot, page):
    """Re-placing on a timer would fight the user for a bubble they are reading."""
    from PyQt6.QtCore import QRect

    placed = []
    page._place_callout = lambda: placed.append(True)
    page._update_pending = True
    page.update_callout.show()
    here = QRect(20, 300, 36, 36)
    page._callout_anchored_at = here
    page._badge_rect = lambda: QRect(here)

    page._follow_callout()

    assert placed == []


def test_the_bubble_never_covers_the_badge_it_points_at(qtbot):
    """Neither below nor above: it steps off screen instead of onto the badge."""
    from PyQt6.QtWidgets import QPushButton, QWidget

    from frontends.desktop.components.dashboard_widgets import UpdateCallout

    window = QWidget()
    qtbot.addWidget(window)
    window.resize(400, 150)
    badge = QPushButton("x", window)
    badge.setGeometry(180, 10, 36, 36)
    callout = UpdateCallout(window)
    callout.set_message(version="9.9.9", detail="d" * 200, action="a")
    window.show()
    qtbot.waitExposed(window)

    placed = callout.point_at(badge)

    if placed:
        assert not callout.geometry().intersects(badge.geometry())
    else:
        assert callout.isHidden()
