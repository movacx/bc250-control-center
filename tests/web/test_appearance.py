"""The web must use every desktop Formal palette with legible button text."""
import re

import pytest

from frontends.desktop.theme import ACCENTS, THEMES, _contrast, theme_palette
from frontends.web.server import theme_css


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("accent", ACCENTS)
def test_every_web_combination_matches_formal_desktop_colours(theme, accent):
    selector = ":root" if accent == "violet" else f":root[data-accent={accent}]"
    selector += f"[data-theme={theme}]"
    match = re.search(re.escape(selector) + r"\{([^}]+)\}", theme_css())
    assert match, (theme, accent)
    values = dict(item.split(":", 1) for item in match[1].split(";") if item)
    formal = theme_palette(theme, accent, "formal")
    for key, value in formal.items():
        if isinstance(value, str) and key != "on_accent":
            assert values[f"--c-{key.replace('_', '-')}"] == value
    assert _contrast(values["--c-blue"], values["--c-on-accent"]) >= 4.5
    for key in ACCENTS:
        assert values[f"--c-accent-{key}"] == theme_palette(theme, key, "formal")["blue"]
    assert values["color-scheme"] == ("light" if theme == "light" else "dark")
