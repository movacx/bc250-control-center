"""Performance: the desktop's resource tabs, their views and the sensor list, drawn in a terminal.

Every number comes from the desktop's own model (``performance_model``): the
same views per resource, the same summaries and the same sensor grouping. Here
the histories are longer, so the time a chart covers can be chosen.
"""

from __future__ import annotations

import math

from frontends.desktop.core.performance_model import (
    DEFAULT_PLOTTED,
    KIND_FILTERS,
    MINIMUM_SPAN,
    RESOURCE_BY_KEY,
    RESOURCE_DEFINITIONS,
    SENSOR_VIEWS,
    PerformanceRecorder,
    group_title,
    search_text,
    sensor_label,
    series_statistics,
)
from frontends.desktop.core.performance_sample_presenter import format_rate
from frontends.desktop.core.performance_views import VIEW_BY_KEY, views_for
from frontends.desktop.core.sensor_log import format_sensor_value

from ..content import (
    Card,
    Chart,
    Choice,
    Columns,
    Field,
    Gap,
    Heading,
    Note,
    Panel,
    Readings,
    Spans,
    cell_width,
)
from ..i18n import tr, tr_format
from .base import Page, switch

TONES = ("accent", "ok", "warn", "bad", "", "dim")  # one per series, in the desktop's slot order
#: The time a chart can cover, in minutes; the recorder keeps the longest of them.
WINDOWS = (1, 2, 5, 10, 30)
DEPTH = WINDOWS[-1] * 60 + 1


def shower(unit: str, rate: bool = False):
    """How a value of ``unit`` reads on an axis, a legend or a card."""
    if rate:
        return format_rate
    return (lambda value: f"{value:.1f}%") if unit == "%" else (lambda value: format_sensor_value(value, unit))


def axis(values: list[float], unit: str, fixed: bool, rate: bool, steps: int = 4):
    """The desktop's axis for this data: round ticks, a sensible range, finer on a taller plot (see ``chart_axes``)."""
    from frontends.desktop.components.chart_axes import (
        ValueAxis,
        range_axis,
        value_axis,
        zoomed_percent_axis,
    )

    peak = max(values, default=0.0)
    if unit == "%" and not rate:
        return value_axis(0, fixed_maximum=100, target_ticks=steps) if fixed else zoomed_percent_axis(peak, target_ticks=steps)
    if rate:
        # Round in the unit it is read in: 1024 bytes to the KiB.
        unit_size = 1024.0 ** max(1, int(math.log(max(peak * 1.15, 1024.0), 1024)))
        scale = value_axis(peak / unit_size, minimum_span=1.0, target_ticks=steps)
        return ValueAxis(0.0, scale.maximum * unit_size, scale.step * unit_size)
    return range_axis(min(values, default=0.0), peak, minimum_span=MINIMUM_SPAN.get(unit, 1.0), target_ticks=steps)


def view_options(views, current: str, available: set[str]) -> list[tuple[str, str]]:
    """A view menu in two columns, name then what it shows; ● marks the open one, (--) one with no data yet."""
    width = max(cell_width(item.shown_title(tr)) for item in views)
    return [(item.key, f"{'●' if item.key == current else ' '} {item.shown_title(tr).ljust(width)}   {item.shown_hint(tr)}"
             + ("" if item.key in available else "  (--)")) for item in views]


def chart_height(ui, blocks: list, minimum: int = 6) -> int:
    """The rows left for the plot: the content area less ``blocks``, the title and the two rows of time axis."""
    from ..layout import Glyphs, build_layout

    rows = ui._view() if hasattr(ui, "_view") else 30
    width = ui._content_box()[1] if hasattr(ui, "_content_box") else 100
    used = len(build_layout(blocks, width, Glyphs.for_terminal(unicode_ok=True)).rows) + 2  # the title and the space under it
    return max(minimum, min(60, rows - used - 2))


def fitted_axis(values: list[float], unit: str, fixed: bool, rate: bool, rows: int):
    """``(axis, height)``: a whole number of rows between two labels, wasting as few of ``rows`` as it can."""
    best = None
    for steps in range(max(2, min(10, rows // 3)), 1, -1):
        scale = axis(values, unit, fixed, rate, steps)
        gaps = max(1, len(scale.ticks) - 1)
        height = (rows - 1) // gaps * gaps + 1 if rows > 2 * gaps else 0
        if height and (best is None or height > best[1] + 2):
            best = scale, height
    return best or (axis(values, unit, fixed, rate, 2), rows)


def axis_for(values: list[float], unit: str, rows: int):
    """:func:`fitted_axis` for a plain reading, framed to its own range."""
    return fitted_axis(values, unit, False, False, rows)


def window_text(seconds: float) -> str:
    return window_title(int(seconds) // 60)


def tick_label(scale, unit: str, rate: bool, show):
    """Percentages on the axis without decimals, when the steps have none."""
    whole = all(float(tick).is_integer() for tick in scale.ticks)
    return (lambda value: f"{value:.0f}%") if unit == "%" and not rate and whole else show


def window_title(minutes: int) -> str:
    return f"{minutes} min"


class PerformancePage(Page):
    key = "performance"
    title = "Performance"
    loads = False

    def tabs(self, ctx):
        return [("sensors", tr("Sensors"))] + [(item.key, tr(item.title)) for item in RESOURCE_DEFINITIONS]

    @staticmethod
    def recorder(ctx) -> PerformanceRecorder:
        """Created on the first visit; from then on the poller feeds it every second, on any page."""
        state = ctx.state("performance")
        if state.get("recorder") is None:
            state["recorder"] = PerformanceRecorder(depth=DEPTH)
        return state["recorder"]

    @staticmethod
    def _window(ctx, recorder) -> Choice:
        """The time every chart of this page covers."""
        state = ctx.state("performance")
        minutes = state.get("window", 2)
        recorder.window = minutes * 60.0

        def choose(value: int) -> None:
            state["window"] = value
            recorder.window = value * 60.0

        def pick(ui_):
            picked = ui_.choose(tr("History window"), [(value, window_title(value)) for value in WINDOWS])
            if picked is not None:
                choose(picked)

        def step(ui_, direction=1):
            at = WINDOWS.index(minutes) + direction
            choose(WINDOWS[max(0, min(len(WINDOWS) - 1, at))])

        return Choice(tr("History window"), pick, f"< {window_title(minutes)} >", adjust=step)

    def build(self, ctx, data, tab, ui):
        recorder = self.recorder(ctx)
        recorder.sensors = True
        if not recorder.plans:
            return [Note(tr("Waiting for first sample"), "dim")]
        return self._sensors(ctx, recorder, ui) if (tab or "sensors") == "sensors" \
            else self._resource(ctx, recorder, tab, ui)

    # -- a resource: its chart, in the view chosen from its menu --------------------------

    def _resource(self, ctx, recorder, key, ui):
        state = ctx.state(self.key)
        definition = RESOURCE_BY_KEY[key]
        # An unplugged disk's view is gone: fall back to the tab's own.
        view = VIEW_BY_KEY.get(state.get(f"view:{key}", key)) or VIEW_BY_KEY.get(key)
        if view is not None and view.resource != key:
            view = VIEW_BY_KEY.get(key)
        history, chart_def, (primary, context, stats), summary = recorder.reading(key, view)
        unit, rate = chart_def.unit, definition.rate_scale and summary
        show = shower(unit, rate)
        fixed = state.get(f"scale:{key}", "auto") == "fixed"

        hint = view.shown_hint(tr) if view is not None and not view.is_summary else tr(definition.subtitle)
        narrow = (ui.size()[1] if hasattr(ui, "size") else 120) < 100
        out = [] if narrow else [Note(hint, "dim")]
        views = views_for(key)
        if len(views) > 1:
            def choose_view(ui_):
                picked = ui_.choose(tr(definition.title), view_options(views, view.key, recorder.available))
                if picked is not None:
                    state[f"view:{key}"] = picked

            out.append(Choice(tr("Views"), choose_view, f"{view.shown_title(tr)} ›"))
        out.append(self._window(ctx, recorder))
        if unit == "%":
            def scale(ui_, _direction=1):
                state[f"scale:{key}"] = "auto" if fixed else "fixed"

            out.append(Choice(tr("Scale"), scale, "< 0–100 % >" if fixed else f"< {tr('Auto')} >", adjust=scale))
        out.append(Readings([(tr(label), value) for label, value in zip(chart_def.stat_labels, stats)]))

        names = [name for name, _tone in chart_def.series] if history else []
        series = [(tr(name), list(history.values[name]), TONES[index % len(TONES)])
                  for index, name in enumerate(names) if history.values.get(name)]
        title = tr(definition.title) if view is None or view.is_summary else f"{tr(definition.title)} · {view.shown_title(tr)}"
        badge = "  ".join(part for part in (primary, context) if part and part != "--")
        if not series:
            return [Panel(title, [*out, Note(context, "dim")], wide=True)]
        below: list = []
        if len(series) <= 8 and chart_def.form != "heatmap":  # the legend: min · average · peak of each series
            width = max(cell_width(name) for name, _v, _t in series)
            low_high = [series_statistics(history, raw) or (0.0, 0.0, 0.0) for raw in names if history.values.get(raw)]
            for (name, _values, tone), (low, average, high) in zip(series, low_high):
                below.append(Spans([[("● " if getattr(ui, "unicode", True) else "* ", tone), (name.ljust(width), ""), (
                    f"  {tr_format('min {value}', value=show(low))} · {tr_format('avg {value}', value=show(average))} · "
                    f"{tr_format('max {value}', value=show(high))}", "dim")]]))
        covered = history.times[-1] - history.times[0]
        lasted = f"{int(covered) // 60}:{int(covered) % 60:02d}"
        status = tr_format("{count} samples in {time}", count=len(history.times), time=lasted)
        if not narrow:
            status += " · " + tr_format("Last sample {time}", time=recorder.sampled_at)
        below.append(Note(status, "dim"))
        values = [value for _name, data, _tone in series for value in data]
        scale, height = fitted_axis(values, unit, fixed, rate, chart_height(ui, [*out, Gap(), *below]))
        single = series[0][1] if len(series) == 1 else None
        chart = Chart(series, list(history.times), scale.minimum, scale.maximum, height, show,
                      average=sum(single) / len(single) if single else None,
                      average_label=tr_format("avg {value}", value=show(sum(single) / len(single))) if single else "",
                      heatmap=chart_def.form == "heatmap", window=recorder.window, ticks=scale.ticks, now=tr("Now"),
                      mark=tick_label(scale, unit, rate, show))
        return [Panel(title, [*out, Gap(), chart, *below], badge=badge, badge_tone="", wide=True)]

    # -- the sensor list ------------------------------------------------------------------

    def _sensors(self, ctx, recorder, ui):
        state = ctx.state(self.key)
        ticked = state.setdefault("ticked", set(DEFAULT_PLOTTED))
        query = state.get("filter", "")
        kind = state.get("kind", 0)
        hide = state.get("hide", True)
        layout = state.get("layout", "list")
        log = recorder.log
        narrow = (ui.size()[1] if hasattr(ui, "size") else 120) < 100

        def ask_filter(ui_):
            text = ui_.ask_text(tr("Filter by name"), query)
            if text is not None:
                state["filter"] = text.strip()

        def step_kind(ui_, direction=1):
            state["kind"] = (kind + direction) % len(KIND_FILTERS)

        def pick_kind(ui_):
            picked = ui_.choose(tr("Type"), [(index, tr(label)) for index, (label, _kinds) in enumerate(KIND_FILTERS)])
            if picked is not None:
                state["kind"] = picked

        def pick_layout(ui_):
            picked = ui_.choose(tr("Views"), view_options(SENSOR_VIEWS, layout, {item.key for item in SENSOR_VIEWS}))
            if picked is not None:
                state["layout"] = picked

        controls = [Choice(tr("Filter by name"), ask_filter, query or "--"),
                    Choice(tr("Type"), pick_kind, f"< {tr(KIND_FILTERS[kind][0])} >", adjust=step_kind),
                    switch(tr("Hide unused channels"), hide, lambda ui_: state.update(hide=not hide)),
                    Choice(tr("Reset min/max"), lambda ui_: log.reset_statistics()),
                    Choice(tr("Views"), pick_layout, f"{tr(dict((v.key, v.title) for v in SENSOR_VIEWS)[layout])} ›")]
        if layout != "list":
            controls.append(self._window(ctx, recorder))
        if narrow or getattr(ui, "touch", False):  # on a phone the list comes first; the controls fold away
            opened = state.get("options", False)
            summary = " · ".join(part for part in (query, tr(KIND_FILTERS[kind][0]),
                                                    tr(dict((v.key, v.title) for v in SENSOR_VIEWS)[layout])) if part)
            out = [Choice(tr("Options") + (" ▴" if opened else " ▾"), lambda ui_: state.update(options=not opened),
                          summary)] + (controls if opened else [])
        else:
            out = controls

        kinds = KIND_FILTERS[kind][1]
        entries = [log.entries[key] for key in log.order]
        shown = [entry for entry in entries
                 if (not kinds or entry.reading.kind in kinds) and (not hide or entry.active)
                 and (not query or query.casefold() in search_text(entry.reading))]

        def columns(*values: str) -> str:
            return "".join(value.rjust(11) for value in values)

        def show(entry, value):
            return format_sensor_value(value, entry.reading.unit) if value is not None else "--"

        if layout != "graphs":
            header = (tr("Value"), tr("Max")) if narrow else (tr("Value"), tr("Min"), tr("Avg"), tr("Max"))
            out += [Gap(), Field(tr("Sensor"), columns(*header))]
            group = None
            for entry in shown:
                reading = entry.reading
                if (reading.group, reading.device) != group:
                    group = (reading.group, reading.device)
                    out.append(Heading(group_title(reading.group, reading)))
                row = (show(entry, entry.value), show(entry, entry.maximum)) if narrow else (
                    show(entry, entry.value), show(entry, entry.minimum), show(entry, entry.average),
                    show(entry, entry.maximum))

                def tick(ui_, key=reading.key):
                    ticked.symmetric_difference_update({key})

                out.append(Choice(f"[{'x' if reading.key in ticked else ' '}] {sensor_label(reading)}", tick,
                                  columns(*row), dense=True))
            out.append(Note(tr_format("{shown} of {count} sensors", shown=len(shown), count=len(entries)), "dim"))
        if layout != "list":
            plotted = [entry for entry in shown if entry.reading.key in ticked and entry.trace]
            out.append(Gap())
            if not plotted:
                out.append(Note(tr("Tick a sensor in the list to draw it here."), "dim"))
            cards = []
            newest = max((entry.trace[-1][0] for entry in plotted), default=0.0)
            each = 7 if layout == "graphs" else 5
            for index, entry in enumerate(plotted):
                recent = [(moment, value) for moment, value in entry.trace if moment >= newest - recorder.window]
                if not recent:  # it stopped reading before this window
                    continue
                times, values = [moment for moment, _v in recent], [value for _m, value in recent]
                rate = entry.reading.unit == "B/s"
                show_value = shower(entry.reading.unit, rate)
                scale, height = fitted_axis(values, entry.reading.unit, False, rate, each)
                cards.append(Card(sensor_label(entry.reading), [
                    Chart([(sensor_label(entry.reading), values, TONES[index % 4])], times, scale.minimum,
                          scale.maximum, height, show_value, end=newest, window=recorder.window,
                          ticks=scale.ticks, now=tr("Now"),
                          mark=tick_label(scale, entry.reading.unit, rate, show_value))],
                    show_value(values[-1])))
            if cards:
                out.append(Columns(cards, minimum=66))
        return [Panel(tr("Sensors"), out, wide=True)]
