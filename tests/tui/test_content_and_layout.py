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
from frontends.tui.layout import Glyphs, build_layout, gauge, sparkline

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


def test_gauge_fills_proportionally_with_reverse_spaces_and_clamps():
    assert gauge(0, 0.5, 10, "ok", ASCII) == [("", "dim"), ("     ", "bar:ok"), ("-----", "dim")]
    assert gauge(0, 2.0, 4, "ok", ASCII)[1] == ("    ", "bar:ok")
    assert gauge(0.25, 0.75, 8, "accent", ASCII) == [("--", "dim"), ("    ", "bar:accent"), ("--", "dim")]
    assert sum(len(text) for text, _ in gauge(0, -1, 6, "", UNICODE)) == 6


def test_a_section_heading_takes_one_row_and_meters_share_one_bar_width():
    layout = build_layout([Heading("GPU"), Meter("Load", 0.1, "1 %"), Meter("Temperature", 0.9, "90.0 °C")], 50, ASCII)
    assert len(layout.rows) == 3 and layout.rows[0].spans[0][0] == "GPU"
    widths = [sum(len(t) for t, tone in row.spans if tone in ("dim", "") or tone.startswith("bar:")) for row in layout.rows[1:]]
    assert widths[0] == widths[1]  # values right-aligned in one column


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
