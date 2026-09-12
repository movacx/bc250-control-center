"""The colours a terminal names by number, mapped to something readable here.

Programs ask for "colour 1", not for a hex value, and the classic VGA answer to
that (#AA0000) is unreadable on a dark panel. The table below keeps the
identity of each slot — red stays red, so a failure still reads as a failure —
while raising contrast to the level the rest of the interface holds itself to.
"""

from __future__ import annotations

# The sixteen named slots, tuned for the dark console background that both the
# light and the dark application themes use.
BASE_16 = (
    "#2A3444",  # 0 black, lifted off the background so it stays visible
    "#F1707A",  # 1 red
    "#5BD08A",  # 2 green
    "#E2C275",  # 3 yellow
    "#6FA8FF",  # 4 blue
    "#C89BF0",  # 5 magenta
    "#5CCFD6",  # 6 cyan
    "#D3DCEC",  # 7 white
    "#5A6678",  # 8 bright black
    "#FF9098",  # 9 bright red
    "#7EE7A6",  # 10 bright green
    "#F5D98C",  # 11 bright yellow
    "#93C1FF",  # 12 bright blue
    "#DDB6FF",  # 13 bright magenta
    "#7FE4EA",  # 14 bright cyan
    "#FFFFFF",  # 15 bright white
)

_CUBE_LEVELS = (0, 95, 135, 175, 215, 255)


def _hex(red: int, green: int, blue: int) -> str:
    return f"#{red:02X}{green:02X}{blue:02X}"


def indexed_color(index: int) -> str:
    """Resolve one of the 256 palette slots to a hex colour."""
    value = max(0, min(255, int(index)))
    if value < 16:
        return BASE_16[value]
    if value < 232:
        offset = value - 16
        return _hex(
            _CUBE_LEVELS[offset // 36],
            _CUBE_LEVELS[(offset // 6) % 6],
            _CUBE_LEVELS[offset % 6],
        )
    level = 8 + (value - 232) * 10
    return _hex(level, level, level)


def resolve(color: object, default: str) -> str:
    """Turn a screen colour — index, triple, or None — into a hex string."""
    if color is None:
        return default
    if isinstance(color, tuple) and len(color) == 3:
        return _hex(*(max(0, min(255, int(part))) for part in color))
    if isinstance(color, int):
        return indexed_color(color)
    return default


def brighten_for_bold(color: object) -> object:
    """Bold text in one of the first eight slots uses its bright twin.

    Terminals have done this since hardware could not do both, and scripts
    still rely on it: ``\\033[1;31m`` is how most of our own workflows write a
    heading, and without the promotion those headings read as body text.
    """
    if isinstance(color, int) and 0 <= color < 8:
        return color + 8
    return color
