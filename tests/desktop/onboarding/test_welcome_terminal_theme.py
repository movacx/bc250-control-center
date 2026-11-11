"""The welcome's appearance step picks the built-in terminal's theme too, and the
terminal inside the welcome wears whatever theme is chosen."""

import pytest
from PyQt6.QtWidgets import QWidget

from frontends.desktop import theme as theme_module
from frontends.desktop.onboarding.mini_console import MiniConsole
from frontends.desktop.onboarding.welcome import WelcomeOverlay


def _overlay(qtbot, terminal_theme="app"):
    window = QWidget()
    window.resize(1300, 860)
    qtbot.addWidget(window)
    panel = WelcomeOverlay(
        window, language="auto", mode="system", accent="blue", density="comfortable",
        collapsed=False, system_mode="dark", terminal_theme=terminal_theme,
    )
    panel.setGeometry(window.rect())
    qtbot.addWidget(panel)
    return window, panel


@pytest.fixture(autouse=True)
def _restore_terminal_theme():
    yield
    theme_module.set_terminal_theme("app")


def test_the_appearance_step_offers_the_app_colours_and_every_built_in_theme(qtbot):
    _window, panel = _overlay(qtbot)
    assert list(panel.terminal_cards) == ["app", *theme_module.TERMINAL_THEMES]


def test_nothing_saved_means_the_application_default_is_marked(qtbot):
    _window, panel = _overlay(qtbot)
    assert [key for key, card in panel.terminal_cards.items() if card.selected] == ["app"]


def test_a_saved_theme_is_the_one_marked(qtbot):
    _window, panel = _overlay(qtbot, terminal_theme="graphite")
    assert [key for key, card in panel.terminal_cards.items() if card.selected] == ["graphite"]


def test_choosing_a_theme_marks_it_and_reaches_the_application(qtbot):
    _window, panel = _overlay(qtbot)
    with qtbot.waitSignal(panel.terminal_theme_chosen) as signal:
        panel.terminal_cards["midnight"].chosen.emit("midnight")
    assert signal.args == ["midnight"]
    assert [key for key, card in panel.terminal_cards.items() if card.selected] == ["midnight"]
    with qtbot.waitSignal(panel.terminal_theme_chosen) as signal:
        panel.terminal_cards["app"].chosen.emit("app")
    assert signal.args == ["app"]


def test_the_cards_are_the_compact_size(qtbot):
    _window, panel = _overlay(qtbot)
    assert all(card.compact for card in panel.terminal_cards.values())


def test_the_terminal_in_the_welcome_starts_with_the_saved_theme(qtbot):
    theme_module.set_terminal_theme("midnight")
    console = MiniConsole()
    qtbot.addWidget(console)
    expected = theme_module.TERMINAL_THEMES["midnight"]["bg"].lower()
    assert console.view._colors["background"].name().lower() == expected


def test_the_terminal_in_the_welcome_changes_theme_live(qtbot):
    console = MiniConsole()
    qtbot.addWidget(console)
    theme_module.set_terminal_theme("paper")
    console.apply_theme()
    assert console.view._colors["background"].name().lower() == theme_module.TERMINAL_THEMES["paper"]["bg"].lower()
    theme_module.set_terminal_theme("app")
    console.apply_theme()
    assert console.view._colors["background"].name().lower() == theme_module.COLORS["console_bg"].lower()


def test_refreshing_the_panel_repaints_its_terminal(qtbot):
    _window, panel = _overlay(qtbot)
    theme_module.set_terminal_theme("clay-light")
    panel.refresh_appearance()
    expected = theme_module.TERMINAL_THEMES["clay-light"]["bg"].lower()
    assert panel.console.view._colors["background"].name().lower() == expected
