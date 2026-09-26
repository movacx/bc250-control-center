"""Light mode has to be as legible as dark mode, tooltips included.

Two reports led here. Captions, eyebrows and orange/cyan/green badges washed
out in light mode because their colours measured 2.6–3.4:1 on a white card.
And tooltips could not be read in either theme: the page's text colour
reached the tooltip window through the stylesheet's universal rule and was
painted over the desktop's own tooltip background.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication, QPushButton, QToolTip, QVBoxLayout, QWidget

from frontends.desktop import theme
from frontends.desktop.components.widgets import PillLabel


def _luminance(color: str) -> float:
    channels = [int(color[index:index + 2], 16) / 255.0 for index in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first: str, second: str) -> float:
    light, dark = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


@pytest.fixture(autouse=True)
def _restore_theme():
    yield
    theme.configure_theme("light", "blue", "comfortable", 100)
    theme.apply_tooltip_palette()


@pytest.mark.parametrize("token", ["text", "muted", "subtle", "blue", "purple",
                                   "orange", "cyan", "green", "red"])
def test_every_light_text_token_meets_wcag_aa_on_a_card(token):
    palette = theme.LIGHT_COLORS
    assert _contrast(palette[token], palette["panel"]) >= 4.5, token


@pytest.mark.parametrize("accent", sorted(theme.ACCENTS))
def test_every_light_accent_carries_white_button_text(accent):
    light_value = theme.ACCENTS[accent][0]
    assert _contrast(light_value, "#FFFFFF") >= 4.5, accent


def test_nested_surfaces_are_a_visible_step_from_their_card():
    palette = theme.LIGHT_COLORS
    assert _contrast(palette["panel_alt"], palette["panel"]) > 1.08
    assert _contrast(palette["window"], palette["panel"]) > 1.12


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_tooltip_pair_is_high_contrast_in_both_themes(mode):
    palette = theme.DARK_COLORS if mode == "dark" else theme.LIGHT_COLORS
    assert _contrast(palette["tooltip_text"], palette["tooltip_bg"]) >= 7.0


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_a_real_tooltip_uses_the_tooltip_pair_not_the_page_text(qtbot, mode):
    theme.configure_theme(mode, "blue", "comfortable", 100)
    theme.apply_tooltip_palette()
    window = QWidget()
    window.setStyleSheet(theme.application_stylesheet())
    layout = QVBoxLayout(window)
    button = QPushButton("Aplicar", window)
    layout.addWidget(button)
    pill = PillLabel("Activo", "orange")
    layout.addWidget(pill)
    qtbot.addWidget(window)
    window.show()

    for owner in (button, pill):
        QToolTip.showText(owner.mapToGlobal(QPoint(4, 4)), "Texto de ayuda", owner)
        qtbot.waitUntil(lambda: _visible_tip() is not None, timeout=2000)
        tip = _visible_tip()
        foreground = tip.palette().color(tip.foregroundRole()).name().upper()
        background = tip.palette().color(tip.backgroundRole()).name().upper()
        assert foreground == theme.COLORS["tooltip_text"].upper(), owner
        assert background == theme.COLORS["tooltip_bg"].upper(), owner
        QToolTip.hideText()
        qtbot.waitUntil(lambda: _visible_tip() is None, timeout=2000)


def _visible_tip():
    for widget in QApplication.topLevelWidgets():
        if widget.metaObject().className() == "QTipLabel" and widget.isVisible():
            return widget
    return None


def test_density_pass_survives_a_page_that_shadows_layout(qtbot):
    """Pages keep a layout in ``self.layout``; the pass must not call it."""
    from PyQt6.QtWidgets import QVBoxLayout

    from frontends.desktop.components.density import apply_layout_density

    page = QWidget()
    page.layout = QVBoxLayout(page)
    page.layout.setContentsMargins(20, 20, 20, 20)
    qtbot.addWidget(page)

    assert apply_layout_density(page, True) == 1
    assert page.layout.contentsMargins().left() == 12
    assert apply_layout_density(page, False) == 1
    assert page.layout.contentsMargins().left() == 20


#: The surfaces text is laid on inside a card, not only the card itself. A
#: rendered audit found light captions at 4.2:1 and orange/cyan chips at
#: 4.0:1 there while every token passed on white.
NESTED_SURFACES = (
    "panel", "panel_alt", "window", "neutral_soft", "control_hover", "selection",
    "blue_soft", "purple_soft", "orange_soft", "cyan_soft", "green_soft", "red_soft",
)
LIGHT_PALETTES = {"standard": theme.LIGHT_COLORS, "formal": theme.FORMAL_LIGHT_COLORS}


@pytest.mark.parametrize("style", sorted(LIGHT_PALETTES))
@pytest.mark.parametrize("token", ["text", "muted", "subtle"])
def test_light_text_stays_aa_on_every_nested_surface(style, token):
    palette = LIGHT_PALETTES[style]
    worst = min(_contrast(palette[token], palette[surface]) for surface in NESTED_SURFACES)
    assert worst >= 4.5, (style, token, round(worst, 2))


@pytest.mark.parametrize("style", sorted(LIGHT_PALETTES))
@pytest.mark.parametrize("tone", ["blue", "purple", "orange", "cyan", "green", "red"])
def test_light_tones_stay_aa_on_their_own_soft_fill(style, tone):
    palette = LIGHT_PALETTES[style]
    for surface in ("panel", "panel_alt", "window", f"{tone}_soft"):
        assert _contrast(palette[tone], palette[surface]) >= 4.5, (style, tone, surface)


#: The dark palettes added when theme and style became separate choices:
#: graphite in the formal style, and night blue in both styles.
NEW_DARK_PALETTES = {
    "dark/formal": theme.FORMAL_DARK_COLORS,
    "midnight/formal": theme.MIDNIGHT_COLORS,
    "midnight/standard": theme.MIDNIGHT_STANDARD_COLORS,
}


@pytest.mark.parametrize("name", sorted(NEW_DARK_PALETTES))
@pytest.mark.parametrize("token", ["text", "muted", "subtle", "blue", "purple",
                                   "orange", "cyan", "green", "red"])
def test_new_dark_palettes_meet_aa_on_their_surfaces(name, token):
    palette = NEW_DARK_PALETTES[name]
    surfaces = ["panel", "panel_alt", "panel_raised", "window"]
    if token in ("text", "muted", "subtle"):
        surfaces += ["selection", "neutral_soft", "control_hover"]
    else:
        surfaces.append(f"{token}_soft")
    for surface in surfaces:
        assert _contrast(palette[token], palette[surface]) >= 4.5, (name, token, surface)


@pytest.mark.parametrize("accent", sorted(theme.ACCENTS))
def test_formal_accents_keep_white_button_text_and_read_on_dark(accent):
    light_value, _light_soft, dark_value, _dark_soft = theme.ACCENTS[accent]
    assert _contrast(theme.formal_accent(light_value, "light"), "#FFFFFF") >= 4.5, accent
    for surface in (theme.FORMAL_DARK_COLORS["panel"], theme.MIDNIGHT_COLORS["panel"]):
        assert _contrast(theme.formal_accent(dark_value, "dark"), surface) >= 4.5, accent
        assert _contrast(theme.formal_accent(dark_value, "midnight"), surface) >= 4.5, accent
    assert _contrast(dark_value, theme.MIDNIGHT_STANDARD_COLORS["panel"]) >= 4.5, accent
    # Accent text on its own soft fill, the pairing a rendered audit caught.
    for name in theme.THEMES:
        if name == "light":
            continue
        for style in theme.STYLES:
            palette = theme.theme_palette(name, accent, style)
            if (name, style) == ("dark", "standard"):
                continue  # the original graphite pairs, left as they were
            assert _contrast(palette["blue"], palette["blue_soft"]) >= 4.5, (accent, name, style)


def test_formal_is_a_style_in_every_theme_and_night_blue_is_a_theme():
    """Reported: Formal in dark mode turned the application blue. The blue
    belongs with the themes; the style keeps the surfaces of the theme."""
    try:
        theme.configure_theme("dark", "blue", "comfortable", 100, "formal")
        assert theme.COLORS["window"] == theme.DARK_COLORS["window"]
        assert theme.COLORS["panel"] == theme.DARK_COLORS["panel"]
        graphite = theme.application_stylesheet()

        theme.configure_theme("midnight", "blue", "comfortable", 100, "formal")
        assert (theme.ACTIVE_THEME, theme.ACTIVE_MODE) == ("midnight", "dark")
        assert theme.COLORS["window"] == theme.MIDNIGHT_COLORS["window"]
        assert theme.application_stylesheet() != graphite

        theme.configure_theme("midnight", "blue", "comfortable", 100, "standard")
        assert theme.COLORS["panel"] == theme.MIDNIGHT_COLORS["panel"]
        assert theme.COLORS["blue"] == theme.ACCENTS["blue"][2]
        assert "border-radius: 16px" in theme.scale_stylesheet("QFrame { border-radius: 16px; }", 100)

        # A value the theme module does not know falls back instead of breaking.
        theme.configure_theme("sepia", "blue", "comfortable", 100, "standard")
        assert theme.ACTIVE_THEME == "light"
    finally:
        theme.configure_theme("light", "blue", "comfortable", 100, "standard")


def test_the_preview_palette_is_the_installed_one_without_installing_it():
    before = dict(theme.COLORS)
    for name in theme.THEMES:
        for style in theme.STYLES:
            preview = theme.theme_palette(name, "teal", style)
            try:
                theme.configure_theme(name, "teal", "comfortable", 100, style)
                assert preview == theme.COLORS, (name, style)
            finally:
                theme.configure_theme("light", "blue", "comfortable", 100, "standard")
    assert theme.COLORS == before


def test_formal_style_swaps_palette_squares_corners_and_keeps_pills_round():
    theme.configure_theme("dark", "blue", "comfortable", 100, "formal")
    try:
        assert theme.ACTIVE_STYLE == "formal"
        assert theme.COLORS["window"] == theme.FORMAL_DARK_COLORS["window"]
        assert theme.COLORS["blue"] == theme.formal_accent(theme.ACCENTS["blue"][2], "dark")
        squared = theme.scale_stylesheet("QFrame { border-radius: 16px; } QLabel { border-radius: 999px; }", 100)
        assert "border-radius: 8px" in squared and "border-radius: 999px" in squared
        assert theme.application_stylesheet() != ""
        assert _contrast(theme.COLORS["tooltip_text"], theme.COLORS["tooltip_bg"]) >= 7.0
    finally:
        theme.configure_theme("light", "blue", "comfortable", 100, "standard")
