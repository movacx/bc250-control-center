"""TTY contracts: reachable tasks, stable focus, idle redraw and terminal input."""
import curses

import pytest

from frontends.tui.app import _parser
from frontends.tui.content import Choice, Field
from frontends.tui.layout import Glyphs, build_layout
from frontends.tui.pages import build_pages

from .fakes import make_context
from .test_screen import make_screen, press


@pytest.mark.parametrize('width,height', [(60, 14), (80, 24), (100, 30), (160, 50)])
def test_every_section_is_visible_when_selected_even_on_short_ttys(width, height):
    window, screen = make_screen(width=width, height=height)
    for key in screen.order:
        screen.goto(key)
        screen.draw()
        assert screen.section in screen._sidebar_at.values(), key
        assert screen.page_key == key
        assert not hasattr(screen, 'touch')


def test_retired_touch_flag_is_rejected_and_legacy_config_cannot_restore_it(monkeypatch):
    with pytest.raises(SystemExit) as error:
        _parser().parse_args(['--touch'])
    assert error.value.code == 2
    monkeypatch.setenv('BC250_TUI_TOUCH', '1')
    _, screen = make_screen(width=80, height=24)
    screen.ctx.state('ui').update(touch=True, keybar=True)
    screen.draw()
    assert screen._content_box()[0] > 2
    assert not hasattr(screen, 'keybar')


def test_tab_and_shift_tab_visit_enabled_actions_and_reveal_their_rows():
    _, screen = make_screen(width=80, height=24)
    screen.goto('cpu')
    screen.handle_key('tab')
    layout = screen.build()
    expected = {i for i, choice in enumerate(layout.choices) if choice.enabled}
    seen = set()
    for _ in range(len(expected)):
        screen.handle_key('tab')
        current = screen.cursor[screen._slot()]
        seen.add(current)
        assert screen.current_choice() is layout.choices[current]
    assert seen == expected
    last = screen.cursor[screen._slot()]
    screen.handle_key('tab')
    screen.handle_key('btab')
    assert screen.cursor[screen._slot()] == last
    screen.handle_key('f6')
    assert screen.focus == 'sidebar'


def test_f2_reaches_last_section_and_f3_reaches_network_off_the_tab_strip():
    window, screen = make_screen(width=80, height=24)
    window.queue = [curses.KEY_END, 10]
    press(screen, curses.KEY_F2)
    assert screen.page_key == 'settings'
    screen.goto('performance')
    window.queue = [curses.KEY_END, 10]
    press(screen, curses.KEY_F3)
    assert screen._tab_key() == 'network'
    screen.handle_key('[')
    assert screen._tab_key() == 'disk'


def test_unicode_input_uses_wide_terminal_keys_without_reinterpreting_them():
    window, screen = make_screen()
    incoming = iter(['ñ', '界', '\n'])
    window.get_wch = lambda: next(incoming)
    assert screen.ask_text('Name') == 'ñ界'


def test_arrows_do_not_accidentally_change_a_task_and_invalid_task_is_ignored():
    _, screen = make_screen()
    screen.goto('gpu')
    screen.handle_key('tab')
    screen.show_tab('service')
    screen._switch_tab(0, 'missing')
    assert screen._tab_key() == 'service'
    screen.handle_key('left')
    assert screen._tab_key() == 'service'


def test_gpu_cpu_and_cu_are_linear_forms_without_desktop_cards():
    from frontends.tui.content import Panel, Split, Tiles

    ctx = make_context()
    pages = build_pages()
    for key in ('cpu', 'gpu', 'cu', 'extras'):
        page = pages[key]
        data = page.load(ctx)
        for tab, _ in page.tabs(ctx):
            blocks = page.build(ctx, data, tab, object())
            assert not any(isinstance(block, (Panel, Split, Tiles)) for block in blocks), (key, tab)
            layout = build_layout(blocks, 52, Glyphs.for_terminal(unicode_ok=False))
            assert layout.rows


def test_resize_keeps_actions_safe_when_the_old_selection_no_longer_exists():
    window, screen = make_screen()
    screen.goto('cpu')
    screen.focus = 'content'
    screen.cursor[screen._slot()] = 999
    window.height, window.width = 14, 60
    screen.handle_key('resize')
    screen.draw()
    assert screen.current_choice() is None
    screen.handle_key('enter')
    assert not screen.ctx.service.calls


def test_keyboard_focus_skips_a_disabled_action():
    _, screen = make_screen()
    screen.focus = 'content'
    screen._layout = build_layout([Field('read', 'value'), Choice('disabled', None, enabled=False),
                                  Choice('enabled', lambda _: None)], 50, screen.glyphs)
    screen.build = lambda: screen._layout
    screen.cursor[screen._slot()] = 0
    screen.handle_key('tab')
    assert screen.current_choice().label == 'enabled'
