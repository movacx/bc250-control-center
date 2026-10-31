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


def test_gauge_draws_a_heavy_line_over_a_hairline_and_clamps():
    assert gauge(0, 0.5, 10, "ok", ASCII) == [("", "dim"), ("=====", "ok"), ("-----", "dim")]
    assert gauge(0, 2.0, 4, "ok", ASCII)[1] == ("====", "ok")
    assert gauge(0.25, 0.75, 8, "accent", UNICODE) == [("──", "dim"), ("━━━━", "accent"), ("──", "dim")]
    assert sum(len(text) for text, _ in gauge(0, -1, 6, "", UNICODE)) == 6


def test_a_section_heading_takes_one_row_and_meters_share_one_bar_width():
    layout = build_layout([Heading("GPU"), Meter("Load", 0.1, "1 %"), Meter("Temperature", 0.9, "90.0 °C")], 50, ASCII)
    assert len(layout.rows) == 3 and layout.rows[0].spans[0][0] == "GPU"
    widths = [sum(len(t) for t, tone in row.spans if tone in ("dim", "", "ok")) for row in layout.rows[1:]]
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


def test_a_chart_line_is_one_stroke_with_round_ticks_and_a_labelled_average():
    from frontends.tui.content import Chart
    from frontends.tui.layout import chart_rows

    times = list(range(120))
    values = [10 + (i % 20) for i in times]
    rows = chart_rows(Chart([("Usage", values, "accent")], times, 0, 30, 8, lambda v: f"{v:.0f}%",
                            average=19.5, average_label="avg 19.5%", ticks=(0, 10, 20, 30)), 80, UNICODE)
    text = ["".join(t for t, _ in row) for row in rows]
    assert any("avg 19.5%" in line for line in text) and any(line.rstrip().endswith("│ 20%") for line in text)
    plot = [line[:60] for line in text[:8]]
    used = [any(0x2800 < ord(char) <= 0x28FF and char not in "⡀⢀" for char in column) for column in zip(*plot)]
    assert all(used[10:60])  # no column of the stroke left empty: the samples are joined
    assert text[-1].startswith("-2:00") and "-1:00" in text[-1]


def test_cards_side_by_side_keep_every_button_and_each_row_knows_whose_span_is_whose():
    from frontends.tui.content import Buttons, Panel, Split

    pressed = []
    left = Panel("Left", [Buttons([Choice("One", lambda ui: pressed.append(1)), Choice("Two", lambda ui: None)])])
    right = Panel("Right", [Choice("Three", lambda ui: None)], action=Choice("Export", lambda ui: None))
    layout = build_layout([Split([left], [right], minimum=60)], 100, UNICODE)
    assert [c.label for c in layout.choices] == ["One", "Two", "Three", "Export"]
    row = next(r for r in layout.rows if r.owners and 0 in r.owners and 1 in r.owners)  # both buttons on one row
    texts = {owner: "".join(t for (t, _), o in zip(row.spans, row.owners) if o == owner) for owner in (0, 1)}
    assert "One" in texts[0] and "Two" in texts[1]
    assert all(cell_width("".join(t for t, _ in r.spans)) == 100 for r in layout.rows)  # nothing spills past the edge


def test_buttons_share_space_and_remain_compact_on_a_narrow_terminal():
    from frontends.tui.content import Buttons

    block = Buttons([Choice("Save", lambda ui: None), Choice("Remove permanently", lambda ui: None, tone="bad")])
    wide = build_layout([block], 60, UNICODE)
    assert len(wide.rows) == 1 and wide.choice_rows == [0, 0]
    phone = build_layout([block], 20, UNICODE)
    assert phone.choice_rows == [0, 1] and cell_width("".join(t for t, _ in phone.rows[0].spans)) == 20


def test_the_range_rail_marks_the_chosen_span_and_turns_red_past_the_danger_stop():
    from frontends.tui.content import Slider

    rail = build_layout([Slider([500, 1000, 2000, 2400], 500, 2000, 2000)], 40, UNICODE).rows[0]
    tones = {tone for text, tone in rail.spans if "━" in text or "●" in text}
    assert tones == {"accent"} and any(tone == "bad" for _text, tone in rail.spans)


def test_a_pad_cell_is_a_tap_target_of_its_own():
    from frontends.tui.content import Pad, PadCell, PadRow

    placed = []
    pad = Pad(["A", "B"], [PadRow("r0", [PadCell("x"), PadCell("y")], "1")], (0, 0), lambda r, c: False,
              lambda ui: None, place=lambda r, c: placed.append((r, c)))
    row = next(r for r in build_layout([pad], 40, UNICODE).rows if r.cells)
    assert [(r, c) for _a, _b, r, c in row.cells] == [(0, 0), (0, 1)]
