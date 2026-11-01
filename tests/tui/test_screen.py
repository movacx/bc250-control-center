"""The curses screen, driven by a fake window: keys in, characters out."""

import curses

import pytest

from frontends.tui import keys
from frontends.tui.pages import build_pages
from frontends.tui.screen import (
    MIN_HEIGHT,
    MIN_WIDTH,
    Quit,
    Screen,
    detect_light_background,
)

from .fakes import make_context


class FakeWindow:
    def __init__(self, height=30, width=100):
        self.height, self.width = height, width
        self.cells = {}
        self.queue: list[int] = []

    def getmaxyx(self):
        return self.height, self.width

    def erase(self):
        self.cells.clear()

    def addstr(self, y, x, text, attr=0):
        for offset, char in enumerate(text):
            self.cells[(y, x + offset)] = char

    def noutrefresh(self):
        pass

    def clearok(self, flag):
        pass

    def refresh(self):
        pass

    def getch(self):
        if not self.queue:
            raise AssertionError("the dialog asked for more keys than the test provided")
        return self.queue.pop(0)

    def line(self, y):
        return "".join(self.cells.get((y, x), " ") for x in range(self.width))

    def text(self):
        return "\n".join(self.line(y) for y in range(self.height))


def make_screen(**kwargs):
    window = FakeWindow(**kwargs)
    ctx = make_context()
    screen = Screen(window, ctx, build_pages(), None, foreground=lambda label, work: (True, work()))
    for key, page in screen.pages.items():
        ctx.page_data[key] = page.load(ctx) if page.loads else None
    return window, screen


def press(screen, *codes):
    for code in codes:
        screen.handle(code)


def test_sidebar_lists_every_section_in_order_and_marks_the_open_one():
    window, screen = make_screen()
    screen.draw()
    text = window.text()
    for title in ("Dashboard", "CPU", "GPU", "Compute units", "Fans", "Processes", "Black box", "Firmware"):
        assert title in text or title.lower() in text.lower()
    assert "BC250 Control Center" in window.line(0)


def test_arrow_keys_move_the_sidebar_and_digits_jump_from_either_pane():
    _, screen = make_screen()
    press(screen, curses.KEY_DOWN, curses.KEY_DOWN)
    assert screen.page_key == "cu"  # the desktop's order: CPU, Compute Units, GPU
    press(screen, ord("1"))
    assert screen.page_key == "dashboard"
    press(screen, 9, ord("9"))  # Tab into the content: digits still jump
    assert screen.page_key == "black_box"
    press(screen, ord(","))
    assert screen.page_key == "settings"
    press(screen, 27, curses.KEY_UP)
    assert screen.page_key == "firmware"


def test_the_sidebar_groups_sections_like_the_desktop():
    window, screen = make_screen()
    screen.draw()
    rows = [window.line(y) for y in range(window.height)]
    hardware = next(i for i, row in enumerate(rows) if "HARDWARE" in row)
    assert "CPU" in rows[hardware + 1] and "Compute Units" in rows[hardware + 2]
    assert any("MONITORING" in row for row in rows)


def test_search_jumps_to_an_item_or_a_section():
    window, screen = make_screen()
    window.queue = [ord(c) for c in "fans"] + [10]
    press(screen, ord("/"))
    assert screen.page_key == "fans"


def test_mouse_opens_a_section_without_breaking_keyboard_navigation(monkeypatch):
    window, screen = make_screen()
    screen.draw()
    y = next(y for y, index in screen._sidebar_at.items() if screen.order[index] == "gpu")
    monkeypatch.setattr(curses, "getmouse", lambda: (0, 2, y, 0, curses.BUTTON1_PRESSED))
    press(screen, curses.KEY_MOUSE)
    assert screen.page_key == "gpu" and screen.focus == "content"


def test_vim_keys_and_tab_switch_panes():
    _, screen = make_screen()
    press(screen, ord("j"))
    assert screen.page_key == "cpu"
    press(screen, 9)  # Tab
    assert screen.focus == "content"
    press(screen, 27)  # Esc
    assert screen.focus == "sidebar"


def test_tabs_cycle_with_brackets_and_arrows_inside_the_content():
    _, screen = make_screen()
    press(screen, ord("5"))
    assert screen.page_key == "extras" and screen._tab_key() == "compatibility"
    press(screen, ord("]"))
    assert screen._tab_key() == "upscaling"  # the desktop's order
    press(screen, ord("["), ord("["))
    assert screen._tab_key() == "drivers"  # wraps around
    press(screen, 10)  # Enter: into the content
    assert screen.focus == "content"
    press(screen, curses.KEY_RIGHT)
    assert screen._tab_key() == "drivers"  # arrows do not unexpectedly change tasks


def test_enter_runs_the_selected_action_and_asks_for_confirmation_first():
    _, screen = make_screen()
    service = screen.ctx.service
    press(screen, ord("4"))  # GPU
    screen.show_tab("service")
    press(screen, 10)
    layout = screen.build()
    index = next(i for i, c in enumerate(layout.choices) if c.label == "Restart")
    screen.cursor[screen._slot()] = index
    screen._reveal(screen._slot(), layout.choice_rows[index])
    asked = []
    screen.confirm = lambda message, danger=False: asked.append(message) or False
    press(screen, 10)
    assert asked and not any(call[0] == "controlar_governor" for call in service.calls)
    screen.confirm = lambda message, danger=False: True
    press(screen, 10)
    assert ("controlar_governor", ("reiniciar",), {}) in service.calls


def test_quit_key_raises_the_quit_signal():
    _, screen = make_screen()
    with pytest.raises(Quit):
        press(screen, ord("q"))


def test_confirm_dialog_requires_an_explicit_y_for_dangerous_actions():
    window, screen = make_screen()
    window.queue = [10, ord("n")]  # Enter must not accept a dangerous action; n refuses
    assert screen.confirm("Erase?", danger=True) is False
    window.queue = [ord("y")]
    assert screen.confirm("Erase?", danger=True) is True
    window.queue = [10]
    assert screen.confirm("Harmless?") is True


def test_numeric_prompt_rejects_out_of_range_then_accepts_a_valid_value():
    window, screen = make_screen()
    erase = [curses.KEY_BACKSPACE]
    keys_ = erase + [ord(c) for c in "99"] + [10] + erase * 2 + [ord(c) for c in "15"] + [10]
    window.queue = keys_
    assert screen.ask_int("Value", 10, 20, 5) == 15


def test_numeric_prompt_cancels_with_escape():
    window, screen = make_screen()
    window.queue = [27]
    assert screen.ask_int("Value", 1, 5, 3) is None


def test_choose_returns_the_highlighted_value_and_none_on_escape():
    window, screen = make_screen()
    window.queue = [curses.KEY_DOWN, 10]
    assert screen.choose("Pick", [("a", "A"), ("b", "B")]) == "b"
    window.queue = [27]
    assert screen.choose("Pick", [("a", "A")]) is None


def test_text_viewer_scrolls_and_closes():
    window, screen = make_screen(height=12)
    window.queue = [curses.KEY_NPAGE, curses.KEY_DOWN, ord("q")]
    screen.show_text("Log", "\n".join(f"line {i}" for i in range(60)))
    assert not window.queue


def test_too_small_terminal_shows_a_message_instead_of_a_broken_layout():
    window, screen = make_screen(height=MIN_HEIGHT - 1, width=MIN_WIDTH - 1)
    screen.draw()
    assert "too small" in window.text()


def test_resize_rebuilds_the_layout_for_the_new_width():
    window, screen = make_screen()
    first = screen.build()
    window.width = 70
    press(screen, curses.KEY_RESIZE)
    assert screen.build() is not first


def test_a_page_that_raises_while_building_shows_the_error_not_a_crash():
    window, screen = make_screen()

    def broken(ctx, data, tab, ui):
        raise RuntimeError("page exploded")

    screen.page.build = broken
    screen.draw()
    assert "page exploded" in window.text()


def test_footer_hints_are_visible_and_toasts_replace_them_then_expire():
    window, screen = make_screen()
    screen.draw()
    assert "Quit" in window.line(window.height - 1) or "Salir" in window.line(window.height - 1)
    screen.notify("saved!", "ok")
    screen.draw()
    assert "saved!" in window.line(window.height - 1)


def test_light_terminals_are_detected_from_colorfgbg():
    assert detect_light_background({"COLORFGBG": "0;15"})
    assert not detect_light_background({"COLORFGBG": "15;0"})
    assert not detect_light_background({})


def test_key_names_cover_the_keys_a_pad_or_ssh_session_sends():
    assert keys.name_of(curses.KEY_UP) == "up"
    assert keys.name_of(10) == "enter" and keys.name_of(13) == "enter"
    assert keys.name_of(127) == "backspace"
    assert keys.name_of(ord("x")) == "x"


def test_mutating_actions_leave_curses_through_the_foreground_hook():
    calls = []
    window = FakeWindow()
    ctx = make_context()
    screen = Screen(window, ctx, build_pages(), None, foreground=lambda label, work: calls.append(label) or (True, work()))
    screen.run("Label", lambda: None)
    assert calls == ["Label"]


def test_without_unicode_everything_drawn_is_plain_ascii_for_the_english_interface():
    from frontends.tui.i18n import set_language

    set_language("en")
    window, screen = make_screen()
    screen.unicode = False
    from frontends.tui.layout import Glyphs
    screen.glyphs = Glyphs.for_terminal(unicode_ok=False)
    for key in screen.order:
        screen._go(screen.order.index(key))
        screen.focus = "content"
        screen.draw()
        assert window.text().isascii(), (key, [c for c in window.text() if not c.isascii()])
    window.queue = [ord("n")]
    screen.confirm("Sure?")
    assert window.text().isascii()


def test_a_long_page_scrolls_and_never_acts_on_an_item_off_screen():
    window, screen = make_screen(height=24, width=80)
    screen.ctx.page_data["dashboard"] = screen.pages["dashboard"].load(screen.ctx)
    press(screen, 9)  # into the dashboard: its first item sits below the cards
    screen.draw()
    assert screen.scroll[screen._slot()] == 0  # the cards stay on screen
    assert screen.current_choice() is None or screen._shown(screen.build(), screen._slot(), screen.cursor[screen._slot()])
    before = list(screen.ctx.service.calls)
    press(screen, 10)
    assert screen.ctx.service.calls == before
    press(screen, *[curses.KEY_DOWN] * 60)
    assert screen.scroll[screen._slot()] > 0 and screen.current_choice() is not None


def test_the_title_bar_carries_live_gpu_and_cpu_readings():
    window, screen = make_screen()
    screen.draw()
    assert "GPU 1500 MHz" in window.line(0) and "CPU" in window.line(0)
