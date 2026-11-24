"""The terminal interface's own settings, kept in the shared config under ``tui_`` keys.

Nothing here needs the desktop application: what the two share (the language,
the governor, the alert limits) lives in the same file under its common name.
"""

from __future__ import annotations

from typing import Any

#: The accent colour in 256 colours: (dark terminal, light terminal, its fill for the selected row).
ACCENTS = {"blue": (75, 26, 24), "cyan": (80, 30, 23), "green": (114, 28, 22), "violet": (141, 61, 54),
           "pink": (176, 127, 53), "orange": (215, 130, 94)}
ACCENT_LABELS = {"blue": "Blue", "cyan": "Cyan", "green": "Green", "violet": "Violet", "pink": "Pink", "orange": "Orange"}
STYLES = {"standard": "Standard", "formal": "Formal"}  # rounded or square corners
DENSITIES = {"comfortable": "Comfortable", "compact": "Compact"}

DEFAULTS: dict[str, Any] = {
    "tui_theme": "auto", "tui_accent": "blue", "tui_style": "standard", "tui_density": "comfortable",
    "tui_live_bar": True, "tui_details": True, "tui_sidebar_collapsed": False, "tui_start_page": "dashboard",
    "tui_reopen": True, "tui_last_page": "", "tui_auto_hide": False, "tui_language": "", "tui_temperature_unit": "",
    "tui_interval": 1,
}
_CHOICES = {"tui_accent": ACCENTS, "tui_style": STYLES, "tui_density": DENSITIES}


def read(config: dict | None) -> dict[str, Any]:
    """Every preference with a usable value, whatever the file holds."""
    values = {}
    for key, default in DEFAULTS.items():
        value = (config or {}).get(key, default)
        if isinstance(default, bool):
            value = value if isinstance(value, bool) else default
        elif key in _CHOICES:
            value = value if value in _CHOICES[key] else default
        elif isinstance(default, int):
            value = value if isinstance(value, int) and 1 <= value <= 10 else default
        else:
            value = str(value or default)
        values[key] = value
    return values
