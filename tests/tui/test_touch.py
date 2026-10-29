"""The phone / tablet layout: no sidebar, on-screen keys, taps on everything."""

import curses

from frontends.tui.app import _parser, touch_choice
from frontends.tui.pages import build_pages
from frontends.tui.screen import KEYBAR, Screen

from .fakes import make_context
from .test_screen import FakeWindow


def touch_screen(width=70, height=30):
    window, ctx = FakeWindow(height=height, width=width), make_context()
    ctx.state("ui")["touch"] = None  # decided by the width, as on a phone
    screen = Screen(window, ctx, build_pages(), None, foreground=lambda label, work: (True, work()))
    for key, page in screen.pages.items():
        ctx.page_data[key] = page.load(ctx) if page.loads else None
    return window, screen


def tap(monkeypatch, screen, x, y, button=curses.BUTTON1_PRESSED):
    monkeypatch.setattr(curses, "getmouse", lambda: (0, x, y, 0, button))
    screen.handle(curses.KEY_MOUSE)


def test_a_narrow_terminal_gets_the_touch_layout_and_a_wide_one_does_not():
    window, screen = touch_screen()
    screen.draw()
    assert screen.touch and "Menu" in window.line(1) and "Esc" in window.text()
    assert "HARDWARE" not in window.text()  # no sidebar
    _, wide = touch_screen(width=160, height=45)
    assert not wide.touch


def test_on_screen_keys_and_the_section_strip_are_taps(monkeypatch):
    window, screen = touch_screen()
    screen.draw()
    y, x0, _x1, _key = next(hit for hit in screen._hits if hit[3] == "go:1")
    tap(monkeypatch, screen, x0, y)
    assert screen.page_key == "cpu"
    screen.draw()
    y, x0, _x1, key = next(hit for hit in screen._hits if hit[3] == "down")
    before = screen.scroll.get(screen._slot(), 0), screen.cursor.get(screen._slot())
    tap(monkeypatch, screen, x0, y)
    assert (screen.scroll.get(screen._slot(), 0), screen.cursor.get(screen._slot())) != before
    assert len(KEYBAR) == 12


def test_a_tap_opens_a_button_and_a_tap_on_the_arrows_steps_a_value(monkeypatch):
    window, screen = touch_screen(height=60)
    screen.goto("gpu")
    screen.draw()
    rows = {text.strip(): y for y, (_x, text) in screen._row_at.items()}
    y = next(y for text, y in rows.items() if text.startswith("Maximum frequency"))
    x, text = screen._row_at[y]
    tap(monkeypatch, screen, x + text.index(">"), y)  # 1850 -> 2000
    screen.draw()
    assert "2000 MHz" in screen._row_at[y][1]
    asked = []
    screen.confirm = lambda message, danger=False: asked.append(message) or False
    y = next(y for y, (_x, text) in screen._row_at.items() if "Review and apply range" in text)
    tap(monkeypatch, screen, 5, y)
    assert asked  # one tap is enough: no select-then-open


def test_the_menu_and_dialog_answers_are_taps(monkeypatch):
    window, screen = touch_screen()
    read = screen._read

    def tap_the_seventh_option():  # once the list is drawn, tap "Fans"
        y, x0, _x1, _key = next(hit for hit in screen._hits if hit[3] == "pick:6")
        monkeypatch.setattr(curses, "getmouse", lambda: (0, x0, y, 0, curses.BUTTON1_PRESSED))
        window.queue = [curses.KEY_MOUSE]
        return read()

    monkeypatch.setattr(screen, "_read", tap_the_seventh_option)
    screen.section_menu()
    assert screen.page_key == "fans"
    monkeypatch.undo()

    screen.draw()
    window.queue = [-1]  # draws the dialog, then the tap below arrives
    real_modal = screen._modal_key

    def tap_yes():
        y, x0, _x1, _key = next(hit for hit in screen._hits if hit[3] == "y")
        monkeypatch.setattr(curses, "getmouse", lambda: (0, x0, y, 0, curses.BUTTON1_PRESSED))
        window.queue = [curses.KEY_MOUSE]
        return real_modal()

    monkeypatch.setattr(screen, "_modal_key", tap_yes)
    assert screen.confirm("Erase?", danger=True) is True


def test_touch_is_forced_by_the_flag_or_the_environment_and_otherwise_remembered(monkeypatch):
    args = _parser().parse_args(["--touch"])
    assert touch_choice(args, {}) is True
    args = _parser().parse_args([])
    monkeypatch.setenv("BC250_TUI_TOUCH", "0")
    assert touch_choice(args, {"tui_touch": True}) is False
    monkeypatch.delenv("BC250_TUI_TOUCH")
    assert touch_choice(args, {"tui_touch": True}) is True and touch_choice(args, {}) is None
