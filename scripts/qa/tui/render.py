"""Draw any page of the terminal interface without a terminal, with the test doubles' data.

    python scripts/qa/tui/render.py --page gpu --tab voltage --size 120x36 [--lang es] [--ascii|--mono] [--png out.png]

Prints text; ``--ansi`` adds colour, ``--png`` writes a picture (needs Pillow).
"""

from __future__ import annotations

import argparse
import curses
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]


class Window:
    def __init__(self, width: int, height: int):
        self.width, self.height, self.cells = width, height, {}

    def getmaxyx(self):
        return self.height, self.width

    def erase(self):
        self.cells.clear()

    def addstr(self, y, x, text, attr=0):
        from frontends.tui.content import cell_width
        for char in text:
            self.cells[y, x] = (char, attr)
            x += max(1, cell_width(char))

    def noutrefresh(self):
        pass

    def clearok(self, flag):
        pass


PAIRS: dict[int, tuple[int, int]] = {}


def colour_patches(colours: int):
    return (mock.patch.object(curses, "has_colors", lambda: colours > 0),
            mock.patch.object(curses, "use_default_colors", lambda: None),
            mock.patch.object(curses, "init_pair", lambda n, f, b: PAIRS.__setitem__(n, (f, b))),
            mock.patch.object(curses, "color_pair", lambda n: n << 8),
            mock.patch.object(curses, "COLORS", colours, create=True))


def xterm(index: int) -> tuple[int, int, int]:
    base = [(0, 0, 0), (205, 49, 49), (13, 188, 121), (229, 229, 16), (36, 114, 200), (188, 63, 188),
            (17, 168, 205), (229, 229, 229)]
    if index < 16:
        return base[index % 8]
    if index >= 232:
        return (8 + (index - 232) * 10,) * 3
    index -= 16
    levels = (0, 95, 135, 175, 215, 255)
    return levels[index // 36], levels[index // 6 % 6], levels[index % 6]


def style(attr: int, dark: bool):
    fg, bg = ((204, 208, 214), (20, 23, 28)) if dark else ((40, 44, 52), (250, 250, 250))
    pair = PAIRS.get((attr >> 8) & 0xFF)
    if pair:
        fg = xterm(pair[0]) if pair[0] >= 0 else fg
        bg = xterm(pair[1]) if pair[1] >= 0 else bg
    if attr & curses.A_DIM:
        fg = tuple((a + b) // 2 for a, b in zip(fg, bg))
    if attr & curses.A_REVERSE:
        fg, bg = bg, fg
    return fg, bg, bool(attr & curses.A_BOLD), bool(attr & curses.A_UNDERLINE)


def png(window: Window, path: str, dark: bool) -> None:
    from PIL import Image, ImageDraw, ImageFont
    font_dir = next((p for p in ("/usr/share/fonts/TTF", "/usr/share/fonts/truetype/dejavu",
                                 "/usr/share/fonts/dejavu-sans-mono-fonts") if Path(p).is_dir()), "")
    def face(bold):
        for name in (("JetBrainsMono-Bold.ttf" if bold else "JetBrainsMono-Regular.ttf"),):
            if (Path(font_dir) / name).exists():
                return ImageFont.truetype(str(Path(font_dir) / name), 14)
        return ImageFont.load_default(14)
    fonts, cw, ch = {False: face(False), True: face(True)}, 8, 17
    image = Image.new("RGB", (window.width * cw, window.height * ch), style(0, dark)[1])
    draw = ImageDraw.Draw(image)
    for (y, x), (char, attr) in window.cells.items():
        fg, bg, bold, under = style(attr, dark)
        draw.rectangle((x * cw, y * ch, (x + 1) * cw - 1, (y + 1) * ch - 1), fill=bg)
        draw.text((x * cw, y * ch), char, font=fonts[bold], fill=fg)
        if under:
            draw.line((x * cw, (y + 1) * ch - 2, (x + 1) * cw, (y + 1) * ch - 2), fill=fg)
    image.save(path)


def render(args):
    from frontends.tui.pages import build_pages
    from frontends.tui.i18n import set_language
    from frontends.tui.screen import Screen
    from tests.tui.fakes import make_context

    set_language(args.lang)
    width, height = (int(part) for part in args.size.split("x"))
    window, ctx = Window(width, height), make_context()
    for patch in colour_patches(0 if args.mono else 256):
        patch.start()
    screen = Screen(window, ctx, build_pages(), None, theme="mono" if args.mono else "light" if args.light else "dark",
                    foreground=lambda label, work: (True, work()))
    if args.ascii:
        from frontends.tui.layout import Glyphs
        screen.unicode, screen.glyphs = False, Glyphs.for_terminal(unicode_ok=False)
    page = screen.pages[args.page]
    ctx.page_data[args.page] = page.load(ctx) if page.loads else None
    screen.goto(args.page)
    if args.tab:
        screen.tab[args.page] = args.tab
    if args.focus:
        screen._focus("content")
    for key in args.keys.split():
        screen.handle_key(key)
    screen.scroll[screen._slot()] = args.scroll or screen.scroll.get(screen._slot(), 0)
    screen.draw()
    return window


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--page", default="dashboard")
    parser.add_argument("--tab", default="")
    parser.add_argument("--size", default="120x36")
    parser.add_argument("--lang", default="en")
    parser.add_argument("--keys", default="", help="keys to press first, separated by spaces (down down i)")
    parser.add_argument("--scroll", type=int, default=0)
    parser.add_argument("--png", default="")
    for flag in ("ascii", "mono", "light", "focus"):
        parser.add_argument("--" + flag, action="store_true")
    args = parser.parse_args()
    window = render(args)
    if args.png:
        png(window, args.png, not args.light)
    else:
        for y in range(window.height):
            print("".join(window.cells.get((y, x), (" ", 0))[0] for x in range(window.width)).rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
