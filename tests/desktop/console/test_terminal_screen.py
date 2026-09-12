"""The screen must reproduce what our own workflows actually print.

Every case here was taken from output this application produces or consumes:
package-manager progress that redraws with a carriage return, coloured status
lines, ``clear`` before a summary, and translated text in scripts that reach
CJK locales. Terminal emulation fails quietly — a wrong cursor move looks like
garbled output, not like a crash — so the checks are on the resulting grid.
"""

from __future__ import annotations

from frontends.desktop.console.terminal_screen import (
    DEFAULT_STYLE,
    TerminalScreen,
)


def screen(columns: int = 20, rows: int = 5, **kwargs) -> TerminalScreen:
    return TerminalScreen(columns, rows, **kwargs)


# ------------------------------------------------------------------ plain text


def test_plain_text_lands_on_the_first_line():
    term = screen()
    term.feed(b"installing")
    assert term.visible_text().splitlines()[0] == "installing"


def test_a_newline_moves_down_without_resetting_the_column():
    term = screen()
    term.feed(b"ab\ncd")
    lines = term.visible_text().splitlines()
    assert lines[0] == "ab"
    assert lines[1] == "  cd"


def test_a_carriage_return_returns_to_the_left_margin():
    term = screen()
    term.feed(b"ab\r\ncd")
    lines = term.visible_text().splitlines()
    assert lines[0] == "ab"
    assert lines[1] == "cd"


def test_a_backspace_moves_back_one_column_without_erasing():
    term = screen()
    term.feed(b"abc\b")
    assert term.cursor.x == 2
    assert term.visible_text().splitlines()[0] == "abc"


def test_a_tab_advances_to_the_next_eight_column_stop():
    term = screen()
    term.feed(b"ab\tc")
    assert term.visible_text().splitlines()[0] == "ab      c"


# -------------------------------------------------------- progress redrawing


def test_a_carriage_return_progress_bar_overwrites_in_place():
    """This is the pacman and dnf case, and the reason a grid is required."""
    term = screen(columns=20)
    term.feed(b"downloading  10%\rdownloading  95%")
    assert term.visible_text().splitlines()[0] == "downloading  95%"
    assert len([line for line in term.visible_text().splitlines() if line]) == 1


def test_a_shorter_redraw_leaves_the_tail_of_the_longer_one():
    """Faithful to a real terminal: without an erase the old tail survives."""
    term = screen(columns=20)
    term.feed(b"progress 100%\rdone")
    assert term.visible_text().splitlines()[0] == "doneress 100%"


def test_erase_to_end_of_line_clears_the_tail_a_redraw_left():
    term = screen(columns=20)
    term.feed(b"progress 100%\rdone\x1b[K")
    assert term.visible_text().splitlines()[0] == "done"


# --------------------------------------------------------------------- colour


def test_a_basic_colour_applies_until_it_is_reset():
    term = screen()
    term.feed(b"\x1b[31mERROR\x1b[0m ok")
    runs = list(TerminalScreen.runs(term.lines[0]))
    assert runs[0][1] == "ERROR"
    assert runs[0][2].foreground == 1
    assert runs[1][2] == DEFAULT_STYLE


def test_bright_colours_map_above_the_first_eight():
    term = screen()
    term.feed(b"\x1b[92mok")
    assert term.lines[0][0].style.foreground == 10


def test_a_256_colour_index_is_kept_as_an_index():
    term = screen()
    term.feed(b"\x1b[38;5;208mwarn")
    assert term.lines[0][0].style.foreground == 208


def test_truecolor_is_kept_as_a_triple():
    term = screen()
    term.feed(b"\x1b[38;2;12;34;56mx")
    assert term.lines[0][0].style.foreground == (12, 34, 56)


def test_the_colon_spelling_of_truecolor_parses_the_same_way():
    term = screen()
    term.feed(b"\x1b[38:2::12:34:56mx")
    assert term.lines[0][0].style.foreground == (12, 34, 56)


def test_attributes_combine_and_clear_individually():
    term = screen()
    term.feed(b"\x1b[1;4mx\x1b[24my")
    assert term.lines[0][0].style.bold and term.lines[0][0].style.underline
    assert term.lines[0][1].style.bold and not term.lines[0][1].style.underline


def test_inverse_video_swaps_the_resolved_pair():
    term = screen()
    term.feed(b"\x1b[7;31mx")
    foreground, background = term.lines[0][0].style.resolved()
    assert background == 1
    assert foreground == "inverse-default-foreground"


def test_a_malformed_parameter_does_not_raise():
    term = screen()
    term.feed(b"\x1b[38;5;mx\x1b[999max")
    assert "x" in term.visible_text()


# ------------------------------------------------------------ cursor movement


def test_absolute_positioning_places_the_cursor_on_the_named_cell():
    term = screen(columns=20, rows=5)
    term.feed(b"\x1b[3;5Hx")
    assert term.visible_text().splitlines()[2] == "    x"


def test_positioning_beyond_the_grid_clamps_instead_of_growing_it():
    term = screen(columns=10, rows=3)
    term.feed(b"\x1b[99;99Hx")
    assert term.cursor.y == 2
    assert len(term.lines) == 3
    assert all(len(line) == 10 for line in term.lines)


def test_relative_moves_respect_the_edges():
    term = screen(columns=10, rows=3)
    term.feed(b"\x1b[10A\x1b[10D")
    assert (term.cursor.x, term.cursor.y) == (0, 0)


def test_column_addressing_is_one_based():
    term = screen()
    term.feed(b"abcdef\x1b[3Gx")
    assert term.visible_text().splitlines()[0] == "abxdef"


# ------------------------------------------------------------------- erasing


def test_clear_screen_empties_the_grid_but_keeps_the_scrollback():
    term = screen(columns=10, rows=3)
    term.feed(b"one\ntwo\nthree\nfour")  # forces one scroll
    assert term.scrollback
    term.feed(b"\x1b[2J")
    assert term.visible_text().strip() == ""
    assert term.scrollback


def test_erase_with_mode_three_also_drops_the_scrollback():
    term = screen(columns=10, rows=2)
    term.feed(b"a\nb\nc")
    assert term.scrollback
    term.feed(b"\x1b[3J")
    assert term.scrollback == []


def test_erase_keeps_the_active_background_so_a_band_stays_whole():
    term = screen(columns=6, rows=2)
    term.feed(b"\x1b[44m\x1b[K")
    assert term.lines[0][3].style.background == 4


# ------------------------------------------------------------------ scrolling


def test_output_past_the_last_row_scrolls_and_fills_the_scrollback():
    term = screen(columns=10, rows=2)
    term.feed(b"one\r\ntwo\r\nthree")
    assert term.visible_text().splitlines() == ["two", "three"]
    assert len(term.scrollback) == 1
    assert term.scrollback[0][0].text == "o"


def test_the_scrollback_is_capped():
    term = screen(columns=10, rows=2, scrollback=3)
    for index in range(20):
        term.feed(f"line{index}\r\n".encode())
    assert len(term.scrollback) == 3


def test_a_scroll_region_confines_the_scrolling_to_its_rows():
    term = screen(columns=10, rows=4)
    term.feed(b"\x1b[2;3r")          # region is rows 2-3
    term.feed(b"\x1b[4;1Hbottom")    # outside the region, must stay put
    term.feed(b"\x1b[2;1Ha\nb\nc")
    lines = term.visible_text().splitlines()
    assert lines[3] == "bottom"


def test_a_full_height_region_still_feeds_the_scrollback():
    term = screen(columns=10, rows=3)
    term.feed(b"\x1b[1;3r")
    term.feed(b"a\r\nb\r\nc\r\nd")
    assert term.scrollback


def test_a_partial_region_does_not_pollute_the_scrollback():
    term = screen(columns=10, rows=4)
    term.feed(b"\x1b[1;2r")
    term.feed(b"a\r\nb\r\nc\r\nd")
    assert term.scrollback == []


def test_reverse_index_scrolls_the_other_way_at_the_top():
    term = screen(columns=10, rows=3)
    term.feed(b"\x1b[3;1Hbottom\x1b[1;1H\x1bMtop")
    lines = term.visible_text().splitlines()
    assert lines[0] == "top"


# -------------------------------------------------------------- line editing


def test_insert_line_pushes_the_rest_down():
    term = screen(columns=10, rows=3)
    term.feed(b"a\r\nb\r\nc\x1b[1;1H\x1b[L")
    assert term.visible_text().splitlines() == ["", "a", "b"]


def test_delete_line_pulls_the_rest_up():
    term = screen(columns=10, rows=3)
    term.feed(b"a\r\nb\r\nc\x1b[1;1H\x1b[M")
    assert term.visible_text().splitlines()[:2] == ["b", "c"]


def test_delete_character_closes_the_gap():
    term = screen(columns=10)
    term.feed(b"abcdef\x1b[1;2H\x1b[2P")
    assert term.visible_text().splitlines()[0] == "adef"


def test_insert_character_opens_a_gap_without_growing_the_line():
    term = screen(columns=6)
    term.feed(b"abcdef\x1b[1;1H\x1b[2@")
    assert len(term.lines[0]) == 6
    assert term.visible_text().splitlines()[0] == "  abcd"


# ----------------------------------------------------------------- wrapping


def test_the_wrap_is_deferred_until_one_more_character_arrives():
    """A bar that exactly fills the width must not create a blank line."""
    term = screen(columns=4, rows=3)
    term.feed(b"abcd")
    assert term.cursor.y == 0
    term.feed(b"e")
    assert term.cursor.y == 1
    assert term.visible_text().splitlines()[:2] == ["abcd", "e"]


def test_a_carriage_return_cancels_a_pending_wrap():
    term = screen(columns=4, rows=3)
    term.feed(b"abcd\rZ")
    assert term.visible_text().splitlines()[0] == "Zbcd"
    assert term.cursor.y == 0


def test_autowrap_off_overprints_the_last_column():
    term = screen(columns=4, rows=2)
    term.feed(b"\x1b[?7labcdef")
    assert term.cursor.y == 0
    assert term.visible_text().splitlines()[0] == "abcf"


# ------------------------------------------------------------ text encoding


def test_a_utf8_character_split_across_two_reads_survives():
    term = screen()
    term.feed("é".encode()[:1])
    term.feed("é".encode()[1:])
    assert term.visible_text().splitlines()[0] == "é"


def test_invalid_bytes_do_not_raise():
    term = screen()
    term.feed(b"ok\xff\xfe")
    assert term.visible_text().startswith("ok")


def test_a_wide_character_occupies_two_columns():
    term = screen(columns=6)
    term.feed("宽字".encode())
    assert term.cursor.x == 4
    assert term.lines[0][1].placeholder
    assert term.visible_text().splitlines()[0] == "宽字"


def test_overwriting_half_of_a_wide_character_erases_the_other_half():
    term = screen(columns=6)
    term.feed("宽".encode())
    term.feed(b"\x1b[1;1Hx")
    assert term.visible_text().splitlines()[0] == "x"


def test_a_wide_character_exactly_filling_the_row_stays_on_it():
    term = screen(columns=3, rows=2)
    term.feed("a宽".encode())
    assert term.visible_text().splitlines()[0] == "a宽"


def test_a_wide_character_never_straddles_the_right_margin():
    term = screen(columns=4, rows=2)
    term.feed("abc宽".encode())
    assert term.visible_text().splitlines()[0] == "abc"
    assert term.visible_text().splitlines()[1] == "宽"


def test_a_combining_mark_joins_the_character_before_it():
    term = screen()
    term.feed("é".encode())
    assert term.cursor.x == 1
    assert term.lines[0][0].text == "é"


# --------------------------------------------------------- modes and replies


def test_the_window_title_is_taken_from_an_osc_sequence():
    term = screen()
    term.feed(b"\x1b]0;Instalar Cyan\x07")
    assert term.title == "Instalar Cyan"


def test_a_string_terminator_also_ends_the_title():
    term = screen()
    term.feed(b"\x1b]2;Fan PWM\x1b\\rest")
    assert term.title == "Fan PWM"
    assert term.visible_text().splitlines()[0] == "rest"


def test_hiding_the_cursor_is_recorded():
    term = screen()
    term.feed(b"\x1b[?25l")
    assert term.cursor_visible is False
    term.feed(b"\x1b[?25h")
    assert term.cursor_visible is True


def test_bracketed_paste_is_recorded_so_input_can_honour_it():
    term = screen()
    term.feed(b"\x1b[?2004h")
    assert term.bracketed_paste is True


def test_the_alternate_screen_is_isolated_and_restores_the_original():
    term = screen(columns=10, rows=3)
    term.feed(b"kept")
    term.feed(b"\x1b[?1049h")
    assert term.in_alternate_screen
    term.feed(b"\x1b[2Jtemporary")
    assert "kept" not in term.visible_text()
    term.feed(b"\x1b[?1049l")
    assert term.in_alternate_screen is False
    assert "kept" in term.visible_text()


def test_the_alternate_screen_never_writes_to_the_scrollback():
    term = screen(columns=10, rows=2)
    term.feed(b"\x1b[?1049h")
    for index in range(10):
        term.feed(f"row{index}\r\n".encode())
    assert term.scrollback == []


def test_a_cursor_report_is_queued_for_the_process():
    term = screen()
    term.feed(b"\x1b[3;7H\x1b[6n")
    assert term.take_response() == "\x1b[3;7R"
    assert term.take_response() == ""


def test_device_attributes_answer_as_a_plain_vt100():
    term = screen()
    term.feed(b"\x1b[c")
    assert term.take_response() == "\x1b[?1;2c"


def test_a_bell_is_counted_and_not_printed():
    term = screen()
    term.feed(b"a\x07b")
    assert term.bell_count == 1
    assert term.visible_text().splitlines()[0] == "ab"


def test_a_full_reset_returns_a_dirty_screen_to_the_start():
    term = screen(columns=10, rows=2)
    term.feed(b"\x1b[31mnoise\r\nmore\r\nagain")
    term.feed(b"\x1bc")
    assert term.visible_text().strip() == ""
    assert term.scrollback == []
    assert term.cursor.style == DEFAULT_STYLE


# --------------------------------------------------------------- save/restore


def test_the_cursor_and_its_style_survive_a_save_and_restore():
    term = screen()
    term.feed(b"\x1b[2;3H\x1b[31m\x1b7")
    term.feed(b"\x1b[1;1H\x1b[0m")
    term.feed(b"\x1b8x")
    assert term.lines[1][2].text == "x"
    assert term.lines[1][2].style.foreground == 1


# ------------------------------------------------------------------ resizing


def test_narrowing_truncates_and_keeps_the_cursor_inside():
    term = screen(columns=20, rows=4)
    term.feed(b"abcdefghij")
    term.resize(5, 4)
    assert all(len(line) == 5 for line in term.lines)
    assert term.cursor.x < 5
    assert term.visible_text().splitlines()[0] == "abcde"


def test_shrinking_the_height_keeps_the_newest_rows():
    term = screen(columns=10, rows=4)
    term.feed(b"a\r\nb\r\nc\r\nd")
    term.resize(10, 2)
    assert term.visible_text().splitlines() == ["c", "d"]
    assert len(term.lines) == 2


def test_growing_adds_blank_rows_at_the_bottom():
    term = screen(columns=10, rows=2)
    term.feed(b"a\r\nb")
    term.resize(10, 4)
    assert len(term.lines) == 4
    assert term.visible_text().splitlines()[:2] == ["a", "b"]


def test_an_absurd_size_request_is_capped():
    term = screen()
    term.resize(100000, 100000)
    assert term.columns <= 1000
    assert term.rows <= 400


# --------------------------------------------------------------------- views


def test_full_text_joins_the_scrollback_and_the_screen_in_order():
    term = screen(columns=10, rows=2)
    term.feed(b"first\r\nsecond\r\nthird")
    assert term.full_text().splitlines() == ["first", "second", "third"]


def test_runs_group_adjacent_cells_that_share_a_style():
    term = screen()
    term.feed(b"\x1b[31maaa\x1b[32mbb")
    runs = [(start, text) for start, text, _ in TerminalScreen.runs(term.lines[0])]
    assert runs[0] == (0, "aaa")
    assert runs[1] == (3, "bb")


def test_runs_skip_the_placeholder_of_a_wide_glyph():
    term = screen(columns=6)
    term.feed("宽x".encode())
    texts = [text for _, text, _ in TerminalScreen.runs(term.lines[0])]
    assert "".join(texts).startswith("宽x")


def test_application_cursor_mode_is_recorded_for_the_keyboard():
    """A TUI that sets DECCKM expects SS3 arrows; sending CSI inserts junk."""
    term = screen()
    assert term.application_cursor is False
    term.feed(b"\x1b[?1h")
    assert term.application_cursor is True
    term.feed(b"\x1b[?1l")
    assert term.application_cursor is False


def test_a_full_reset_returns_the_cursor_key_mode_to_normal():
    term = screen()
    term.feed(b"\x1b[?1h\x1bc")
    assert term.application_cursor is False


def test_growing_the_screen_takes_its_history_back():
    """A panel that starts small and grows must not show blanks over one line.

    The console begins a workflow while it is still sliding open, so the first
    output can arrive on a three-row grid and scroll straight into the
    scrollback. When the panel reaches full height those lines have to come
    back, or the user sees the last line of an installation and nothing else.
    """
    term = screen(columns=20, rows=3)
    for index in range(1, 9):
        term.feed(f"linea {index}\r\n".encode())
    assert term.scrollback

    term.resize(20, 10)
    visible = [line for line in term.visible_text().splitlines() if line]
    assert "linea 1" in visible
    assert "linea 8" in visible


def test_recovered_history_is_padded_to_the_new_width():
    term = screen(columns=10, rows=2)
    term.feed(b"corta\r\nb\r\nc\r\nd")
    term.resize(30, 6)
    assert all(len(line) == 30 for line in term.lines)
    assert "corta" in term.visible_text()


def test_the_cursor_follows_the_recovered_history():
    term = screen(columns=20, rows=3)
    for index in range(6):
        term.feed(f"fila {index}\r\n".encode())
    term.resize(20, 8)
    term.feed(b"despues")
    lines = term.visible_text().splitlines()
    assert lines[term.cursor.y].startswith("despues")
    assert "fila 0" in term.visible_text()


def test_growing_beyond_the_history_still_pads_with_blanks():
    term = screen(columns=10, rows=2)
    term.feed(b"solo")
    term.resize(10, 6)
    assert len(term.lines) == 6
    assert "solo" in term.visible_text()


def test_a_resize_during_the_alternate_screen_leaves_the_primary_whole():
    """The alternate buffer grows with blanks; the primary keeps its history."""
    term = screen(columns=10, rows=2)
    term.feed(b"historia\r\nb\r\nc")
    term.feed(b"\x1b[?1049h")
    term.resize(10, 8)
    assert len(term.lines) == 8
    assert term.visible_text().strip() == ""  # the alternate buffer stays empty

    term.feed(b"\x1b[?1049l")
    restored = [line for line in term.visible_text().splitlines() if line]
    assert restored == ["historia", "b", "c"]
