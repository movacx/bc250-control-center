"""What the pages read: live metrics, each page's state and the Performance charts.

Everything comes from the same places the terminal interface reads: its page
``load`` functions, its ``Context`` and the desktop's Qt-free performance model.
Nothing samples while nobody is looking, so the service costs nothing idle.
"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict

from bc250cc.application.fan.system_control import system_fan_control_owns_fan
from bc250cc.application.gpu.voltage_lab_state import build_voltage_lab_state
from bc250cc.domain.compute_units import WgpMaskTable
from bc250cc.domain.fan.persistence import normalize_fan_curve, normalize_fan_preset
from bc250cc.domain.gpu.profiles import profiles_for_allowed_range
from bc250cc.domain.gpu.voltage_profiles import (
    CUSTOM_VOLTAGE_MAX_MV,
    CUSTOM_VOLTAGE_MIN_MV,
    SUPPORTED_VOLTAGE_LEVELS,
    voltage_profile,
)
from bc250cc.shared.contract import DESKTOP_FAN_PRESET_PERCENT
from frontends.desktop.components.chart_axes import (
    range_axis,
    value_axis,
    zoomed_percent_axis,
)
from frontends.desktop.core.cpu_refresh_presenter import (
    present_cpu_persistence,
    present_cpu_tuning,
)
from frontends.desktop.core.cu_balance import engine_balance
from frontends.desktop.core.dashboard_presenter import FAN_OWNER_LABELS, fan_owner
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
from frontends.desktop.i18n import governor_fix_label
from frontends.tui.i18n import tr, tr_format
from frontends.tui.pages import build_pages
from frontends.tui.pages.cpu import said
from frontends.tui.runtime import Context, record_metrics
from frontends.web.gddr6 import Gddr6Page

IDLE_SECONDS = 20  # sampling stops this long after the last request
PAGES = ("dashboard", "cpu", "gpu", "cu", "fans", "gddr6")


class Live:
    """The one-second metrics sampler, started by the first request and ended when they stop."""

    def __init__(self, ctx: Context):
        self.ctx, self.recorder = ctx, PerformanceRecorder()
        self.pages = build_pages()
        self.pages["gddr6"] = Gddr6Page()
        self.monitor_job = lambda: {}
        self.gddr6 = {"active": False, "sample": {}}
        self._wanted = 0.0
        self._thread: threading.Thread | None = None
        self._cache: dict[str, tuple[float, object]] = {}
        self._locks = {key: threading.Lock() for key in PAGES}
        ctx.state("performance")["recorder"] = self.recorder

    def touch(self) -> None:
        self._wanted = time.monotonic()
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._loop, name="bc250-web-metrics", daemon=True)
            self._thread.start()

    def _loop(self) -> None:
        ctx = self.ctx
        while time.monotonic() - self._wanted < IDLE_SECONDS:
            started = time.monotonic()
            try:
                metrics = ctx.service.metricas_tiempo_real()
                metrics = metrics if isinstance(metrics, dict) else {}
                job = self.monitor_job()
                active = job.get("kind") == "gddr6.monitor" and not job.get("done", True)
                sample = job.get("sample") or {} if active and job.get("sample_age", 999) <= 15 else {}
                source = "web" if active else ""
                stamp, status = self._cache.get("gddr6", (0, {}))
                external = (status or {}).get("external") or {}
                if not active and time.monotonic() - stamp <= 15 and external.get("state") == "active":
                    sample, source = external, "bc250-telemetry"
                readings = self.recorder.read(metrics)
                self.gddr6 = {"active": active or source == "bc250-telemetry", "sample": sample, "source": source}
                with ctx.lock:
                    ctx.metrics, ctx.metrics_error = metrics, ""
                    record_metrics(ctx, metrics)
                    self.recorder.record(metrics, readings)
            except Exception as error:  # a failed read must not end the loop
                with ctx.lock:
                    ctx.metrics_error = str(error) or error.__class__.__name__
            time.sleep(max(0.1, 1.0 - (time.monotonic() - started)))

    def live(self) -> dict:
        with self.ctx.lock:
            return {"metrics": self.ctx.metrics, "gddr6": self.gddr6, "error": self.ctx.metrics_error,
                    "history": {name: list(values) for name, values in self.ctx.history.items()}}

    def page(self, key: str) -> dict:
        """A page's state, read at the pace the terminal interface reads it."""
        page = self.pages[key]
        with self._locks[key]:
            stamp, value = self._cache.get(key, (0.0, None))
            if value is None or time.monotonic() - stamp >= page.interval:
                value = _derive(key, page.load(self.ctx), self.ctx)
                self._cache[key] = (time.monotonic(), value)
        return value

    def forget(self) -> None:
        self._cache.clear()


# -- pages ----------------------------------------------------------------------------------------

def _derive(key: str, raw: dict, ctx: Context) -> dict:
    return {"cpu": _cpu, "gpu": _gpu, "cu": _cu, "fans": _fans}.get(key, lambda r, c: r)(raw or {}, ctx)


def _cpu(raw: dict, ctx: Context) -> dict:
    persistent = raw.get("persistent") or {}
    # Actions run in a separate user worker. Read the settings it just saved,
    # rather than the server's startup snapshot.
    config = ctx.settings.read_local_config()
    stored = present_cpu_persistence(persistent, {} if persistent else {"persistent": "--"})
    tuning = present_cpu_tuning(persistent, raw.get("detection") or {}, raw.get("scale") or {}, raw.get("quick"),
                                last_applied_frequency=config.get("cpu_oc_last_applied_frequency"),
                                scale_override_enabled=False)
    return {**raw, "persistence": {"enabled": stored.enabled, "value": said(stored.status_value),
                                   "detail": said(stored.status_detail)},
            "tuning": {name: said(getattr(tuning, name)) for name in (
                "detection_value", "detection_detail", "live_value", "live_detail", "applied_value", "applied_detail")}}


def _gpu(raw: dict, ctx: Context) -> dict:
    low, high = int(raw.get("allowed_min") or 500), int(raw.get("allowed_max") or 2000)
    lab = build_voltage_lab_state(raw)
    # D-Bus describes loaded points; the file can already contain additional
    # enabled points. Profile application handles their explicit reload.
    configured = [frequency for frequency, _ in lab.points]
    high_points = raw.get("high_frequency_points") or {}
    enabled = set(high_points.get("enabled_frequencies") or [])
    allowed_values = high_points.get("allowed_frequencies")
    allowed = enabled if allowed_values is None else set(allowed_values)
    governor = "oberon" if str(raw.get("governor_backend") or "").startswith("oberon") else "cyan"
    profile_max = high if governor == "oberon" else max(
        (f for f in configured if f <= 2000 or f in enabled & allowed), default=high)
    profiles = [{"key": item.key, "label": tr(item.label), "min": item.minimum_mhz, "max": item.maximum_mhz}
                for item in profiles_for_allowed_range(low, profile_max, governor=governor)]
    return {**raw, "profile_max": profile_max, "voltage_lab": {
        **asdict(lab), "minimum_mv": CUSTOM_VOLTAGE_MIN_MV, "maximum_mv": CUSTOM_VOLTAGE_MAX_MV,
        "levels": [{"level": level, "values": voltage_profile(level)} for level in SUPPORTED_VOLTAGE_LEVELS],
    }, "profiles": profiles, "fix_labels": {kind: governor_fix_label(kind) for kind in ("metrics", "frequency")}}


def _cu(raw: dict, ctx: Context) -> dict:
    cu = raw.get("cu") or {}
    masks = [int(row.get("mask", 31)) for row in cu.get("rows") or []][:4]
    if len(masks) < 4:
        return raw
    balance = engine_balance(masks)
    return {**raw, "active": WgpMaskTable.from_values(masks).active_cus,
            "balance": {"se0": balance.se0, "se1": balance.se1, "balanced": balance.balanced,
                        "effective": balance.effective, "idle": balance.idle}}


def _fans(raw: dict, ctx: Context) -> dict:
    fans, system, config = raw.get("fans") or {}, raw.get("system") or {}, raw.get("config") or {}
    rows = [row for row in (fans.get("sensores") or {}).get("fans") or [] if isinstance(row, dict)]
    curve, preset = normalize_fan_curve(config.get("fan_curve")), normalize_fan_preset(config.get("fan_preset"))
    selected = next((row for row in rows if row.get("index") == curve.get("pwm")), rows[0] if rows else {})
    owner = fan_owner(system_owned=system_fan_control_owns_fan(system), pwm_enable=selected.get("pwm_enable"),
                      curve_enabled=bool(curve.get("enabled")), preset_enabled=bool(preset.get("enabled")),
                      external=bool(system.get("external")))
    return {"rows": rows, "owner": tr(FAN_OWNER_LABELS.get(owner, owner)), "curve": curve, "preset": preset,
            "external": bool(system.get("external")), "boot": bool(system.get("enabled")),
            "presets": DESKTOP_FAN_PRESET_PERCENT}


# -- Performance ----------------------------------------------------------------------------------

def _axis(values: list[float], unit: str, fixed: bool, rate: bool):
    peak = max(values, default=0.0)
    if unit == "%" and not rate:
        return value_axis(0, fixed_maximum=100) if fixed else zoomed_percent_axis(peak)
    if rate:
        return value_axis(peak, minimum_span=1024.0)
    return range_axis(min(values, default=0.0), peak, minimum_span=MINIMUM_SPAN.get(unit, 1.0))


def _shower(unit: str, rate: bool = False):
    if rate:
        return format_rate
    return (lambda value: f"{value:.1f}%") if unit == "%" else (lambda value: format_sensor_value(value, unit))


def _chart(series: list[tuple[str, list[float]]], ages: list[float], unit: str, fixed: bool, rate: bool,
           heatmap: bool = False) -> dict:
    axis = _axis([v for _n, values in series for v in values], unit, fixed, rate)
    show = _shower(unit, rate)
    chart = {"series": [{"name": name, "values": values} for name, values in series], "ages": ages,
             "min": axis.minimum, "max": axis.maximum,
             "ticks": [{"value": tick, "label": f"{tick:g}%" if unit == "%" and not rate else show(tick)} for tick in axis.ticks],
             "heatmap": heatmap, "unit": unit, "rate": rate}
    if len(series) == 1 and series[0][1]:
        values = series[0][1]
        chart.update(avg=show(sum(values) / len(values)), last=show(values[-1]), peak=show(max(values)))
    return chart


def performance(live: Live, query: dict) -> dict:
    recorder = live.recorder
    tabs = [{"key": "sensors", "title": tr("Sensors")}] + [
        {"key": item.key, "title": tr(item.title)} for item in RESOURCE_DEFINITIONS]
    out = {"tabs": tabs, "tab": query.get("tab") or "sensors", "waiting": not recorder.plans}
    if out["waiting"]:
        return out
    tab = query.get("tab") or "sensors"
    with live.ctx.lock:
        out.update(_sensors(recorder, query) if tab == "sensors" else _resource(recorder, tab, query))
    out["sampled"] = recorder.sampled_at
    return out


def _resource(recorder: PerformanceRecorder, key: str, query: dict) -> dict:
    if key not in RESOURCE_BY_KEY:
        return {}
    definition = RESOURCE_BY_KEY[key]
    view = VIEW_BY_KEY.get(query.get("view") or key) or VIEW_BY_KEY[key]
    if view.resource != key:
        view = VIEW_BY_KEY[key]
    plan = recorder.plans.get(key)
    if view.is_summary:
        history, chart_def = recorder.histories[key], definition
        primary, context, stats = plan.primary, plan.context, plan.stats
    else:
        history = recorder.history(view.key)
        chart_def = history.definition if history else definition
        primary, context, stats = view_summary(view, history, recorder.available) if history \
            else ("--", tr(view.unavailable_hint or "Waiting for sample"), ("--",) * 4)
    unit, rate = chart_def.unit, bool(definition.rate_scale and view.is_summary)
    show = _shower(unit, rate)
    out = {"title": tr(definition.title), "primary": primary, "context": context,
           "hint": tr(definition.subtitle if view.is_summary else view.hint), "view": view.key,
           "views": [{"key": item.key, "title": tr(item.title), "hint": tr(item.hint),
                      "available": item.key in recorder.available} for item in views_for(key)],
           "percent": unit == "%", "legend": [], "cards": []}
    names = [name for name, _tone in chart_def.series] if history else []
    series = [(name, list(history.values[name])) for name in names if history.values.get(name)]
    if not series:
        return out
    now = time.monotonic()
    for name, _values in series:
        low, average, high = series_statistics(history, name) or (0.0, 0.0, 0.0)
        out["legend"].append({"name": tr(name), "min": show(low), "avg": show(average), "max": show(high)})
    out["chart"] = _chart([(tr(name), values) for name, values in series], [now - moment for moment in history.times], unit,
                          query.get("scale") == "fixed", rate, chart_def.form == "heatmap")
    out["cards"] = [{"label": tr(label), "value": value} for label, value in zip(chart_def.stat_labels, stats)]
    return out


def _sensors(recorder: PerformanceRecorder, query: dict) -> dict:
    log = recorder.log
    kind = int(query.get("kind") or 0) % len(KIND_FILTERS)
    needle = (query.get("q") or "").casefold()
    hide = query.get("hide", "1") != "0"
    ticked = set(query["ticked"].split(",")) if "ticked" in query else set(DEFAULT_PLOTTED)
    kinds = KIND_FILTERS[kind][1]
    shown = [entry for entry in map(log.entries.get, log.order)
             if (not kinds or entry.reading.kind in kinds) and (not hide or entry.active)
             and (not needle or needle in search_text(entry.reading))]
    rows, group = [], None
    for entry in shown:
        reading = entry.reading
        if (reading.group, reading.device) != group:
            group = (reading.group, reading.device)
            rows.append({"group": group_title(reading.group, reading)})

        def text(value, unit=reading.unit):
            return format_sensor_value(value, unit) if value is not None else "--"

        rows.append({"key": reading.key, "label": sensor_label(reading), "value": text(entry.value),
                     "min": text(entry.minimum), "avg": text(entry.average), "max": text(entry.maximum),
                     "ticked": reading.key in ticked})
    now, traces = time.monotonic(), []
    for entry in (log.entries[key] for key in log.order if key in log.entries):
        values = [value for _moment, value in entry.trace]
        if entry.reading.key in ticked and values:
            unit = entry.reading.unit
            chart = _chart([(sensor_label(entry.reading), values)], [now - moment for moment, _v in entry.trace],
                           unit, False, unit == "B/s")
            traces.append({"key": entry.reading.key, "label": sensor_label(entry.reading), "value": _shower(unit, unit == "B/s")(values[-1]),
                           "chart": chart, "fresh": now - entry.trace[-1][0] <= 15,
                           "min": _shower(unit, unit == "B/s")(entry.minimum) if entry.minimum is not None else "--",
                           "avg": _shower(unit, unit == "B/s")(entry.average) if entry.average is not None else "--",
                           "max": _shower(unit, unit == "B/s")(entry.maximum) if entry.maximum is not None else "--"})
    return {"rows": rows, "traces": traces,
            "missing_traces": [{"key": key, "label": sensor_label(log.entries[key].reading) if key in log.entries else key}
                               for key in sorted(ticked - {item["key"] for item in traces})], "ticked": sorted(ticked), "count": tr_format("{shown} of {count} sensors", shown=len(shown),
                                                              count=len(log.order)),
            "kinds": [{"index": index, "title": tr(label)} for index, (label, _k) in enumerate(KIND_FILTERS)],
            "layouts": [{"key": item.key, "title": tr(item.title), "hint": tr(item.hint)} for item in SENSOR_VIEWS]}
