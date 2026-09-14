"""The four questions, and the promise that none of them is a gate.

Two rules run through all of it. Every choice reaches the application the
moment it is made — the panel is transparent about what it is doing because
you can see it happening behind the glass — and every step can be left, from
the rail, from the footer, or with Escape.
"""

import pytest

from frontends.desktop import theme as theme_module
from frontends.desktop.i18n import LANGUAGE_OPTIONS
from frontends.desktop.onboarding.welcome import WelcomeOverlay


@pytest.fixture
def overlay(qtbot):
    from PyQt6.QtWidgets import QWidget

    window = QWidget()
    window.resize(1300, 860)
    qtbot.addWidget(window)
    panel = WelcomeOverlay(
        window, language="auto", mode="system", accent="blue",
        density="comfortable", collapsed=False, system_mode="dark",
    )
    panel.setGeometry(window.rect())
    qtbot.addWidget(panel)
    # yield, not return: qtbot keeps only weak references, so a window that
    # went out of scope here would take the panel parented to it with it.
    yield panel


# ------------------------------------------------------------------- moving


def test_it_opens_on_the_first_question(overlay):
    assert overlay.steps.currentIndex() == 0
    assert overlay.progress.text() == f"1 / {overlay.STEP_COUNT}"


def test_there_is_nowhere_back_from_the_first_step(overlay):
    # isHidden, not isVisible: the window behind this panel is never shown in
    # a test, and nothing inside an unshown window is ever "visible".
    assert overlay.back_button.isHidden()

    overlay._reach(1)

    assert not overlay.back_button.isHidden()


def test_the_rail_reaches_any_step_directly(overlay):
    """A stepper that only goes forward is a wizard pretending to be a map."""
    overlay.step_rows[2].click()

    assert overlay.steps.currentIndex() == 2


def test_the_last_step_offers_the_tour_rather_than_more_steps(overlay):
    overlay._reach(overlay.STEP_COUNT - 1)

    assert overlay.progress.text() == f"{overlay.STEP_COUNT} / {overlay.STEP_COUNT}"
    assert overlay.next_button.text().strip()
    seen = []
    overlay.finished.connect(seen.append)
    overlay.next_button.click()
    assert seen == [True]


def test_skipping_leaves_without_the_tour(overlay):
    seen = []
    overlay.finished.connect(seen.append)

    overlay.skip_button.click()

    assert seen == [False]
    assert overlay.isHidden()


def test_escape_is_a_way_out_too(overlay, qtbot):
    from PyQt6.QtCore import Qt

    seen = []
    overlay.finished.connect(seen.append)

    qtbot.keyPress(overlay, Qt.Key.Key_Escape)

    assert seen == [False]


# ------------------------------------------------------------------ choosing


def test_every_shipped_language_is_offered(overlay):
    assert set(overlay.language_chips) == {code for code, _name in LANGUAGE_OPTIONS}


def test_choosing_a_language_reports_it_and_marks_it(overlay):
    seen = []
    overlay.language_chosen.connect(seen.append)

    overlay._choose_language("pt-BR")

    assert seen == ["pt-BR"]
    assert overlay.language_chips["pt-BR"].isChecked()
    assert not overlay.language_chips["auto"].isChecked()


def test_choosing_a_theme_reports_the_whole_appearance(overlay):
    """The window applies the three together, so it is told all three."""
    seen = []
    overlay.appearance_chosen.connect(lambda *args: seen.append(args))

    overlay.theme_cards["light"].chosen.emit("light")

    assert seen == [("light", "blue", "comfortable")]
    assert overlay.theme_cards["light"].selected
    assert not overlay.theme_cards["system"].selected


def test_choosing_an_accent_keeps_the_theme_that_was_chosen(overlay):
    overlay._choose_mode("dark")
    seen = []
    overlay.appearance_chosen.connect(lambda *args: seen.append(args))

    overlay.accent_dots["cyan"].chosen.emit("cyan")

    assert seen == [("dark", "cyan", "comfortable")]


def test_choosing_a_density_keeps_the_rest(overlay):
    seen = []
    overlay.appearance_chosen.connect(lambda *args: seen.append(args))

    overlay.density_buttons["compact"].click()

    assert seen == [("system", "blue", "compact")]


def test_the_sidebar_answer_is_a_boolean_the_window_can_use(overlay):
    seen = []
    overlay.sidebar_chosen.connect(seen.append)

    overlay.sidebar_cards["collapsed"].chosen.emit("collapsed")

    assert seen == [True]
    assert overlay.sidebar_cards["collapsed"].selected

    overlay.sidebar_cards["expanded"].chosen.emit("expanded")
    assert seen == [True, False]


def test_the_system_card_describes_the_desktop_not_the_choice(overlay):
    """Picking Light must not repaint "System" as light; it means the desktop."""
    overlay._choose_mode("light")

    assert overlay.theme_cards["system"]._mode == "dark"


# --------------------------------------------------------------- the preview


def test_a_preview_never_writes_to_the_live_palette(qapp):
    """It is painted from a copy; the real one belongs to every open widget."""
    from frontends.desktop.onboarding.previews import palette_for

    theme_module.configure_theme("dark", "green", "comfortable", 100)
    before = dict(theme_module.COLORS)

    palette_for("light", "orange")["blue"] = "#000000"

    assert theme_module.COLORS == before


def test_the_itinerary_names_the_stops_the_tour_will_make(overlay):
    from frontends.desktop.onboarding.script import tour_stops

    titles = [stop.title for stop in tour_stops()]
    assert len(overlay.stop_chips) == len(titles)
    for chip, title in zip(overlay.stop_chips, titles):
        assert title in chip.text()


# ------------------------------------------------------------------ the glass


def test_the_panel_survives_having_nothing_to_photograph(overlay):
    overlay.set_backdrop_source(None)

    assert overlay._backdrop.isNull()


def test_the_portrait_follows_the_shell_it_was_given(overlay, qtbot):
    from PyQt6.QtWidgets import QWidget

    shell = QWidget(overlay.parentWidget())
    shell.resize(600, 400)

    overlay.set_backdrop_source(shell)

    assert not overlay._backdrop.isNull()
    assert overlay._backdrop.size() == shell.size()


def test_a_resize_does_not_re_photograph_inside_its_own_handler(overlay, qtbot):
    """Grabbing the shell flushes its layout, which comes back as a resize.

    Done synchronously the two called each other until the stack ran out, and
    PyQt turns that into an abort rather than an exception.
    """
    from PyQt6.QtWidgets import QWidget

    shell = QWidget(overlay.parentWidget())
    shell.resize(600, 400)
    overlay.set_backdrop_source(shell)

    overlay.resize(700, 500)

    assert overlay._regrab.isActive()
    assert overlay._refreshing is False
