"""Performance: the desktop's resource tabs, their views and the sensor list, drawn in a terminal.

Every number comes from the desktop's own model (``performance_model``): the
same two-minute histories, the same views per resource, the same summaries
and the same sensor grouping. This page only lays them out.
"""

from __future__ import annotations

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
    view_summary,
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
    Raw,
    cell_width,
)
from ..i18n import tr, tr_format
from .base import Page

TONES = ("accent", "ok", "warn", "bad", "", "dim")  # one per series, in the desktop's slot order
STATUS = "120 samples · 1 s cadence · 2 minute window"


def shower(unit: str, rate: bool = False):
    """How a value of ``unit`` reads on an axis, a legend or a card."""
    if rate:
        return format_rate
    return (lambda value: f"{value:.1f}%") if unit == "%" else (lambda value: format_sensor_value(value, unit))


def axis(values: list[float], unit: str, fixed: bool, rate: bool):
    """The desktop's axis for this data: round ticks, a sensible range (see ``chart_axes``)."""
    from frontends.desktop.components.chart_axes import (
        range_axis,
        value_axis,
        zoomed_percent_axis,
    )

    peak = max(values, default=0.0)
    if unit == "%" and not rate:
        return value_axis(0, fixed_maximum=100) if fixed else zoomed_percent_axis(peak)
    if rate:
        return value_axis(peak, minimum_span=1024.0)
    return range_axis(min(values, default=0.0), peak, minimum_span=MINIMUM_SPAN.get(unit, 1.0))


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
            state["recorder"] = PerformanceRecorder()
        return state["recorder"]

    def build(self, ctx, data, tab, ui):
        recorder = self.recorder(ctx)
        if not recorder.plans:
            return [Note(tr("Waiting for first sample"), "dim")]
        height = ui.size()[0] if hasattr(ui, "size") else 30
        return self._sensors(ctx, recorder, ui, height) if (tab or "sensors") == "sensors" \
            else self._resource(ctx, recorder, tab, height)

    # -- a resource: its chart, in the view chosen from its menu --------------------------

    def _resource(self, ctx, recorder, key, height):
        state = ctx.state(self.key)
        definition = RESOURCE_BY_KEY[key]
        view = VIEW_BY_KEY.get(state.get(f"view:{key}", key), VIEW_BY_KEY.get(key))
        plan = recorder.plans.get(key)
        if view is None or view.is_summary:
            history, chart_def = recorder.histories[key], definition
            primary, context, stats = plan.primary, plan.context, plan.stats
        else:
            history = recorder.history(view.key)
            chart_def = history.definition if history else definition
            primary, context, stats = view_summary(view, history, recorder.available) if history \
                else ("--", tr(view.unavailable_hint or "Waiting for sample"), ("--",) * 4)
        unit, rate = chart_def.unit, definition.rate_scale and (view is None or view.is_summary)
        show = shower(unit, rate)
        fixed = state.get(f"scale:{key}", "auto") == "fixed"

        out = [Heading(f"{tr(definition.title)}  {primary}  {context}"),
               Note(tr(view.hint if view and not view.is_summary else definition.subtitle), "dim")]
        views = views_for(key)
        if len(views) > 1:
            def choose_view(ui_):
                options = [(item.key, f"{tr(item.title)}  ·  {tr(item.hint)}"
                            + ("" if item.key in recorder.available else "  (--)")) for item in views]
                picked = ui_.choose(f"{tr(definition.title)} · {primary} · {context}", options)
                if picked is not None:
                    state[f"view:{key}"] = picked

            out.append(Choice(tr("Views"), choose_view, f"{tr(view.title)} ›"))
        if unit == "%":
            def scale(ui_, _direction=1):
                state[f"scale:{key}"] = "auto" if fixed else "fixed"

            out.append(Choice(tr("Scale"), scale, "0–100 %" if fixed else tr("Auto"), adjust=scale))

        names = [name for name, _tone in chart_def.series] if history else []
        series = [(tr(name), list(history.values[name]), TONES[index % len(TONES)])
                  for index, name in enumerate(names) if history.values.get(name)]
        if not series:
            return out + [Note(context, "dim")]
        if len(series) <= 8 and chart_def.form != "heatmap":  # the legend: min · average · peak of each series
            width = max(cell_width(name) for name, _v, _t in series)
            for (name, _values, tone), raw in zip(series, names):
                low, average, high = series_statistics(history, raw) or (0.0, 0.0, 0.0)
                out.append(Raw([f"● {name.ljust(width)}  {tr_format('min {value}', value=show(low))} · "
                                f"{tr_format('avg {value}', value=show(average))} · "
                                f"{tr_format('max {value}', value=show(high))}"], tone))
        values = [value for _name, data, _tone in series for value in data]
        scale = axis(values, unit, fixed, rate)
        single = series[0][1] if len(series) == 1 else None
        out.append(Chart(series, list(history.times), scale.minimum, scale.maximum,
                         max(6, min(18, height - 20 - len(series))), show,
                         average=sum(single) / len(single) if single else None,
                         heatmap=chart_def.form == "heatmap", ticks=scale.ticks, now=tr("Now")))
        out.append(Columns([Card(tr(label), [], value) for label, value in zip(chart_def.stat_labels, stats)],
                           minimum=16))
        out.append(Note(f"{tr('Sampling')} · {tr(STATUS)} · {tr_format('Last sample {time}', time=recorder.sampled_at)}",
                        "dim"))
        return out

    # -- the sensor list ------------------------------------------------------------------

    def _sensors(self, ctx, recorder, ui, height):
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
            picked = ui_.choose(tr("Views"), [(item.key, f"{tr(item.title)}  ·  {tr(item.hint)}") for item in SENSOR_VIEWS])
            if picked is not None:
                state["layout"] = picked

        out = [Choice(tr("Filter by name"), ask_filter, query or "--"),
               Choice(tr("Type"), pick_kind, f"< {tr(KIND_FILTERS[kind][0])} >", adjust=step_kind),
               Choice(f"[{'x' if hide else ' '}] {tr('Hide unused channels')}", lambda ui_: state.update(hide=not hide)),
               Choice(tr("Reset min/max"), lambda ui_: log.reset_statistics()),
               Choice(tr("Views"), pick_layout, f"{tr(dict((v.key, v.title) for v in SENSOR_VIEWS)[layout])} ›")]

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
                                  columns(*row)))
            out.append(Note(tr_format("{shown} of {count} sensors", shown=len(shown), count=len(entries)), "dim"))
        if layout != "list":
            plotted = [entry for entry in shown if entry.reading.key in ticked]
            out.append(Gap())
            if not plotted:
                out.append(Note(tr("Tick a sensor in the list to draw its last two minutes here."), "dim"))
            for index, entry in enumerate(plotted):
                times = [moment for moment, _value in entry.trace]
                values = [value for _moment, value in entry.trace]
                if not values:
                    continue
                unit, show_value = entry.reading.unit, shower(entry.reading.unit, entry.reading.unit == "B/s")
                scale = axis(values, unit, False, entry.reading.unit == "B/s")
                out += [Heading(f"{sensor_label(entry.reading)}  {show_value(values[-1])}"),
                        Chart([(sensor_label(entry.reading), values, TONES[index % len(TONES)])], times,
                              scale.minimum, scale.maximum, 8 if layout == "graphs" else 5, show_value,
                              ticks=scale.ticks, now=tr("Now"))]
        return out
