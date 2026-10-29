from frontends.tui.content import (
    Choice,
    Field,
    Heading,
    Meter,
    Trend,
    cell_width,
    clip,
    wrap,
)
from frontends.tui.layout import Glyphs, bar, build_layout, sparkline

ASCII = Glyphs.for_terminal(unicode_ok=False)
UNICODE = Glyphs.for_terminal(unicode_ok=True)


def test_wide_and_combining_glyphs_are_measured_in_terminal_columns():
    assert cell_width("日本語") == 6
    assert cell_width("é") == 1
    assert cell_width("ไทย") == 3 - 0  # base letters count; marks do not
    assert cell_width(clip("日本語のテキスト", 7)) <= 7


def test_clip_marks_the_cut_and_leaves_short_text_alone():
    assert clip("abcdef", 4) == "abc…"
    assert clip("abc", 4) == "abc"
    assert clip("abc", 0) == ""


def test_wrap_never_exceeds_the_width_even_for_one_long_word():
    lines = wrap("short " + "x" * 25, 10)
    assert all(cell_width(line) <= 10 for line in lines)
    assert "".join(lines).replace(" ", "").count("x") == 25


def test_bar_fills_proportionally_and_clamps():
    assert bar(0.5, 10, ASCII) == "#####-----"
    assert bar(2.0, 4, ASCII) == "####"
    assert bar(-1, 4, ASCII) == "----"
    assert len(bar(None, 6, UNICODE)) == 6


def test_sparkline_scales_to_the_series_and_pads_to_width():
    line = sparkline([1, 2, 3, 4], 8, ASCII)
    assert len(line) == 8 and line.lstrip()[0] == ASCII.spark[0] and line[-1] == ASCII.spark[-1]
    assert sparkline([], 5, ASCII) == ""
    assert set(sparkline([5, 5, 5], 3, ASCII)) == {ASCII.spark[0]}


def test_layout_tracks_selectable_rows_and_stays_within_width():
    blocks = [Heading("GPU"), Field("Frequency", "1500 MHz"), Meter("Usage", 0.4, "40 %", "ok"),
              Trend("Clock", [1, 2, 3], "3"), Choice("Apply", lambda ui: None, "detail"),
              Choice("Other", None, enabled=False)]
    layout = build_layout(blocks, 50, UNICODE)
    assert len(layout.choices) == 2
    assert [layout.rows[i].choice for i in layout.choice_rows] == [0, 1]
    for row in layout.rows:
        assert sum(cell_width(text) for text, _ in row.spans) <= 50
