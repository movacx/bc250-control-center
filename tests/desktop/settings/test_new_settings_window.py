"""The redesigned Settings window: its sections, the terminal themes and the subpages."""

from PyQt6.QtCore import QSettings

from frontends.desktop import theme
from frontends.desktop.pages.settings import SettingsPage, TerminalThemeCard


class _Settings:
    def read_local_config(self):
        return {"gpu_governor": "auto"}


class _Activity:
    def clear(self):
        return True


def _page(qtbot, tmp_path):
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    page = SettingsPage(object(), settings_service=_Settings(), activity_service=_Activity(), app_settings=settings)
    qtbot.addWidget(page)
    return page, settings


def test_the_unused_privacy_section_is_gone(qtbot, tmp_path):
    page, _ = _page(qtbot, tmp_path)
    assert "security" not in page.section_order


def test_the_overview_and_repositories_open_inside_about(qtbot, tmp_path):
    page, _ = _page(qtbot, tmp_path)
    assert page.SUBPAGES == {"overview": "about", "repositories": "about"}
    shown = []
    page._show_section = shown.append
    for key in page.SUBPAGES:
        page.select_section(key)
    assert shown == ["overview", "repositories"]


def test_every_section_builds_without_error(qtbot, tmp_path):
    page, _ = _page(qtbot, tmp_path)
    for key in page.section_order:
        assert page._ensure_section(key) is not None


def test_the_terminal_theme_list_offers_the_app_colours_and_every_built_in_theme(qtbot, tmp_path):
    page, _ = _page(qtbot, tmp_path)
    page._ensure_section("console")
    assert list(page.terminal_theme_cards) == ["app", *theme.TERMINAL_THEMES]


def test_choosing_a_terminal_theme_is_saved_and_announced(qtbot, tmp_path):
    page, settings = _page(qtbot, tmp_path)
    page._ensure_section("console")
    with qtbot.waitSignal(page.console_theme_changed) as signal:
        page.terminal_theme_cards["midnight"].chosen.emit("midnight")
    assert signal.args == ["midnight"]
    assert settings.value("settings/console_theme") == "midnight"
    assert page.terminal_theme_cards["midnight"].selected
    assert not page.terminal_theme_cards["app"].selected


def test_a_theme_card_paints_in_both_sizes(qtbot):
    for compact in (False, True):
        card = TerminalThemeCard("graphite", "Graphite", compact=compact)
        qtbot.addWidget(card)
        card.resize(220, card.minimumHeight())
        assert not card.grab().isNull()
        assert card.minimumHeight() == (122 if compact else 196)


def test_the_terminal_theme_overlays_the_console_colours_and_goes_back():
    theme.configure_theme("dark", "blue", "comfortable")
    base = theme.COLORS["console_bg"]
    theme.set_terminal_theme("paper")
    assert theme.COLORS["console_bg"].lower() == theme.TERMINAL_THEMES["paper"]["bg"].lower()
    assert len(theme.terminal_ansi()) == 16
    theme.set_terminal_theme("app")
    assert theme.COLORS["console_bg"] == base
    assert theme.terminal_ansi() is None or theme.terminal_ansi() == ()


def test_every_terminal_theme_is_complete():
    for key, entry in theme.TERMINAL_THEMES.items():
        for field in ("name", "bg", "text", "border", "muted", "accent"):
            assert entry[field], (key, field)
        assert len(entry["ansi"]) == 16, key
