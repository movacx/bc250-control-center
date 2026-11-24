"""Random keys on every page: nothing raises, and what Enter would act on is always on screen."""

import random

import pytest

from frontends.tui.screen import Quit

from .test_screen import make_screen

KEYS = ("up", "down", "left", "right", "tab", "btab", "pgup", "pgdn", "home", "end", "[", "]", "f6", "r", "esc", "enter", "space")
SIZES = ((14, 60), (24, 80), (36, 120), (50, 170))


def answer_dialogs(screen):
    """Every dialog is left without choosing: this test moves, it does not change anything."""
    screen.choose = lambda title, options: None
    screen.confirm = lambda message, danger=False: False
    screen.ask_text = lambda label, default="", **_k: None
    screen.ask_int = lambda *args: None
    screen.show_text = lambda *args, **_k: None


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("seed", range(2))
def test_moving_anywhere_never_breaks_and_the_target_is_visible(size, seed):
    window, screen = make_screen(height=size[0], width=size[1])
    answer_dialogs(screen)
    moves = random.Random(seed)
    for page in screen.order:
        screen.goto(page)
        for _ in range(60):
            key = moves.choice(KEYS)
            try:
                screen.handle_key(key)
            except Quit:
                pytest.fail(f"{key} quit the program on {page}")
            if moves.random() < 0.08:  # a refresh can bring other rows at any moment
                screen.ctx.page_data[screen.page_key] = screen.page.load(screen.ctx) if screen.page.loads else None
                screen._layout_key = None
            screen.draw()
            layout, slot = screen.build(), screen._slot()
            cursor = screen.cursor.get(slot, 0)
            assert cursor < len(layout.choices) or not layout.choices, (page, key)
            current = screen.current_choice()
            if current is not None:
                assert screen._shown(layout, slot, cursor), (page, key)
            assert 0 <= screen.scroll.get(slot, 0) <= max(0, len(layout.rows)), (page, key)


@pytest.mark.parametrize("size", SIZES)
def test_every_enabled_item_can_be_reached_with_the_arrows(size):
    window, screen = make_screen(height=size[0], width=size[1])
    answer_dialogs(screen)
    for page in screen.order:
        screen.goto(page)
        for tab in [key for key, _label in screen._tabs()] or [""]:
            if tab:
                screen.show_tab(tab)
            screen._focus("content")
            screen.draw()
            layout = screen.build()
            wanted = {i for i, choice in enumerate(layout.choices) if choice.enabled}
            seen = set()
            screen.handle_key("home")
            for _ in range(len(layout.choices) + 2):  # Tab walks everything, once around
                screen.handle_key("tab")
                seen.add(screen.cursor.get(screen._slot(), -1))
            assert wanted <= seen, (page, tab, [layout.choices[i].label for i in wanted - seen])


def test_the_cursor_stays_on_its_row_when_a_refresh_adds_rows_above():
    from types import SimpleNamespace

    window, screen = make_screen(height=40, width=120)
    screen.goto("processes")
    screen._focus("content")

    def listing(names):
        return {"oomd": False, "processes": [SimpleNamespace(
            pid=i + 10, nombre=name, app_name=name, app_key=name, kind="app", memoria=(9 - i) * 2**30, pss=1,
            cpu_percent=1.0, protegido=False) for i, name in enumerate(names)]}

    screen.ctx.page_data["processes"] = listing(["beta", "gamma"])
    layout = screen.build()
    index = next(i for i, choice in enumerate(layout.choices) if "gamma" in choice.label)
    screen.cursor[screen._slot()] = index
    screen.ctx.page_data["processes"] = listing(["alpha", "beta", "gamma"])
    layout = screen.build()
    assert "gamma" in layout.choices[screen.cursor[screen._slot()]].label
