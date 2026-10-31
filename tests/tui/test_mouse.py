"""Full mouse routing without enabling a touch layout or changing keyboard semantics."""
import curses

import pytest

from frontends.tui.console import Console
from frontends.tui.pointer import Mouse, character_at

from .test_screen import make_screen


def event(monkeypatch, screen, x, y, state=curses.BUTTON1_PRESSED):
    monkeypatch.setattr(curses, 'getmouse', lambda: (0, x, y, 0, state))
    screen.handle(curses.KEY_MOUSE)


def point(screen, label):
    layout = screen.build()
    index = next(i for i, choice in enumerate(layout.choices) if label in choice.label)
    screen._reveal(screen._slot(), layout.choice_rows[index])
    screen.draw()
    for y, spans in screen._choice_at.items():
        for left, right, owner in spans:
            if owner == index and right > left:
                return left, y
    raise AssertionError(label)


def hit(screen, key):
    y, left, _right, _key = next(item for item in screen._dialog_hits if item[3] == key)
    return 0, left, y, 0, curses.BUTTON1_PRESSED


def test_sidebar_has_categories_and_firmware_settings_stay_pinned_after_resize():
    window, screen = make_screen(height=24, width=100)
    for height in (24, 40, 14):
        window.height = height
        screen.draw()
        assert screen._sidebar_at[height - 4] == screen.order.index('firmware')
        assert screen._sidebar_at[height - 2] == screen.order.index('settings')
        if height >= 24:
            assert all(group in window.text() for group in ('HARDWARE', 'MONITORING', 'SYSTEM'))
    for key, target in [('0', 'firmware'), ('.', 'remote'), (',', 'settings')]:
        screen.handle_key(key)
        assert screen.page_key == target


def test_clicks_open_sections_and_tabs_while_keys_keep_working(monkeypatch):
    window, screen = make_screen()
    screen.draw()
    y = next(y for y, index in screen._sidebar_at.items() if screen.order[index] == 'gpu')
    event(monkeypatch, screen, 3, y)
    assert screen.page_key == 'gpu'
    screen.draw()
    y, left, _right, _key = next(item for item in screen._hits if item[3] == 'tab:service')
    event(monkeypatch, screen, left, y)
    assert screen._tab_key() == 'service'
    screen.handle_key('[')
    assert screen._tab_key() == 'governor'


def test_click_toggles_an_option_and_arrows_adjust_without_opening_a_prompt(monkeypatch):
    _, screen = make_screen(height=40)
    screen.goto('cpu')
    x, y = point(screen, 'Use manual scale')
    event(monkeypatch, screen, x, y)
    assert screen.ctx.state('cpu')['target']['manual']
    screen.draw()
    y = next(y for y, (_x, text) in screen._row_at.items() if '< -34 scale >' in text)
    left, text = screen._row_at[y]
    screen.ask_int = lambda *args: pytest.fail('the arrow opened a prompt')
    event(monkeypatch, screen, left + text.index('>'), y)
    assert screen.ctx.state('cpu')['target']['scale'] == -33


def test_cu_cell_click_selects_exact_pair_and_does_not_write_hardware(monkeypatch):
    _, screen = make_screen(width=120, height=45)
    screen.goto('cu')
    screen.draw()
    y, left, column = next((y, left, col) for y, cells in screen._cells_at.items()
                           for left, _right, row, col in cells if row == 2 and col == 3)
    event(monkeypatch, screen, left, y)
    assert screen.ctx.state('cu')['cursor'] == (2, 3)
    assert screen.ctx.state('cu')['masks'] == [31, 31, 23, 31]
    assert not screen.ctx.service.calls


def test_scroll_wheel_and_scrollbar_drag_work_on_long_pages(monkeypatch):
    window, screen = make_screen(height=24)
    screen.goto('dashboard')
    screen.draw()
    event(monkeypatch, screen, 60, 10, curses.BUTTON5_PRESSED)
    assert screen.scroll[screen._slot()] > 0
    screen.draw()
    track = screen._scroll_track
    assert track and track[0] == 'content'
    _kind, x, top, view, _thumb, maximum, _offset = track
    event(monkeypatch, screen, x, top + view - 1)
    assert screen.scroll[screen._slot()] == maximum
    monkeypatch.setattr('frontends.tui.pointer.read_mouse', lambda: Mouse(x, top, 'move'))
    screen.handle(curses.KEY_MOUSE)
    assert screen.scroll[screen._slot()] == 0
    monkeypatch.setattr('frontends.tui.pointer.read_mouse', lambda: Mouse(x, top, 'release'))
    screen.handle(curses.KEY_MOUSE)
    assert screen._pointer_drag is None


def test_modal_clicks_cannot_fall_through_and_explicit_yes_confirms_danger(monkeypatch):
    window, screen = make_screen()
    window.queue = [curses.KEY_MOUSE, curses.KEY_MOUSE]
    events = iter([False, True])
    def mouse():
        if not next(events):
            return 0, 2, 2, 0, curses.BUTTON1_PRESSED  # outside the dialog
        return hit(screen, 'y')
    monkeypatch.setattr(curses, 'getmouse', mouse)
    assert screen.confirm('Apply change?', danger=True)
    assert screen.page_key == 'dashboard'
    assert not screen.ctx.service.calls


def test_mouse_selects_menu_entries_and_positions_text_cursor(monkeypatch):
    window, screen = make_screen()
    window.queue = [curses.KEY_MOUSE]
    monkeypatch.setattr(curses, 'getmouse', lambda: hit(screen, 'pick:2'))
    assert screen.choose('Menu', [(i, str(i)) for i in range(5)]) == 2
    keys = iter(['cursor:1', 'enter'])
    monkeypatch.setattr(curses, 'getmouse', lambda: hit(screen, next(keys)))
    window.queue = [curses.KEY_MOUSE, ord('X'), curses.KEY_MOUSE]
    assert screen.ask_text('Name', 'abc') == 'aXbc'
    assert character_at('界a', 2) == (1, 'a')


def test_console_wheel_scrolls_and_sidebar_click_cannot_interrupt_or_navigate(monkeypatch):
    _, screen = make_screen(height=24)
    console = Console('test')
    console.write('\n'.join(str(i) for i in range(200)))
    screen.active_console = console
    screen.draw()
    monkeypatch.setattr(curses, 'getmouse', lambda: (0, 60, 8, 0, curses.BUTTON4_PRESSED))
    screen._console_key(console, curses.KEY_MOUSE)
    assert screen.console_scroll == 3
    monkeypatch.setattr(curses, 'getmouse', lambda: (0, 3, 5, 0, curses.BUTTON1_PRESSED))
    assert screen._console_key(console, curses.KEY_MOUSE) == ''
    assert screen.page_key == 'dashboard'
    console.finish(True, None)
    screen.draw()
    y, left, _right, _key = next(item for item in screen._hits if item[3] == 'enter')
    monkeypatch.setattr(curses, 'getmouse', lambda: (0, left, y, 0, curses.BUTTON1_PRESSED))
    assert screen._console_key(console, curses.KEY_MOUSE) == 'close'


def test_resized_or_refreshed_hit_regions_never_activate_an_old_action(monkeypatch):
    window, screen = make_screen()
    screen.goto('gpu')
    x, y = point(screen, 'Gaming')
    screen.confirm = lambda *args, **kwargs: pytest.fail('stale action was dispatched')
    screen.ctx.page_data['gpu'] = dict(screen.ctx.page_data['gpu'])
    event(monkeypatch, screen, x, y)
    window.width += 20
    event(monkeypatch, screen, x, y)


def test_right_click_cancels_a_dialog_and_wheel_changes_menu_selection(monkeypatch):
    window, screen = make_screen()
    window.queue = [curses.KEY_MOUSE]
    monkeypatch.setattr(curses, 'getmouse', lambda: (0, 50, 12, 0, curses.BUTTON3_PRESSED))
    assert screen.ask_text('Name', 'abc') is None
    window.queue = [curses.KEY_MOUSE, 10]
    monkeypatch.setattr(curses, 'getmouse', lambda: (0, 50, 12, 0, curses.BUTTON5_PRESSED))
    assert screen.choose('Options', [(i, str(i)) for i in range(10)]) == 3
