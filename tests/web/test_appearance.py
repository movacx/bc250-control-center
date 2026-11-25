"""The palettes the web draws with are the desktop's own."""

from frontends.desktop.theme import ACCENTS, STYLES, THEMES, theme_palette
from frontends.web.server import theme_data


def test_every_desktop_palette_is_offered():
    data = theme_data({})
    assert set(data["palettes"]) == {f"{style}/{theme}/{accent}" for style in STYLES for theme in THEMES for accent in ACCENTS}
    assert (data["theme"], data["accent"]) == ("dark", "green")
    for key, colours in data["palettes"].items():
        style, theme, accent = key.split("/")
        desktop = theme_palette(theme, accent, style)
        assert {name: colours[name] for name in desktop if isinstance(desktop[name], str)} == {
            name: value for name, value in desktop.items() if isinstance(value, str)}


def test_the_saved_choice_is_used_and_a_bad_one_is_not():
    assert theme_data({"web_theme": "light", "web_accent": "teal"})["theme"] == "light"
    data = theme_data({"web_theme": "../x", "web_accent": 7})
    assert (data["theme"], data["accent"]) == ("dark", "green")
