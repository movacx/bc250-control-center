"""Live data for the terminal interface.

Hardware reads can take a while, so none of them run on the thread that draws:
one worker keeps the real-time metrics fresh, another keeps the open page's own
data fresh. Both only call the service layer the desktop application uses.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from bc250cc.shared.failure_text import describe_failure

from .i18n import tr

logger = logging.getLogger(__name__)

HISTORY_SAMPLES = 120


def describe_error(error: BaseException) -> str:
    """An exception as text a person can act on, with the catalogue's code."""
    return describe_failure(1, "", str(error) or error.__class__.__name__, translate=tr)


def describe_result(result: object) -> str:
    """The sentence a service result carries, whatever shape it came in."""
    if isinstance(result, str):
        return result.strip()
    if isinstance(result, dict):
        for key in ("operation_message", "message", "detail", "status_text", "resultado"):
            if result.get(key):
                return str(result[key]).strip()
        return ""
    return ""


@dataclass
class Context:
    """Everything a page may read; pages never reach for globals."""

    service: Any
    settings: Any = None
    activity: Any = None
    platform: Any = None
    metrics: dict[str, Any] = field(default_factory=dict)
    metrics_error: str = ""
    history: dict[str, deque] = field(default_factory=dict)
    page_data: dict[str, Any] = field(default_factory=dict)
    page_error: dict[str, str] = field(default_factory=dict)
    page_state: dict[str, dict] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    lock: threading.RLock = field(default_factory=threading.RLock)

    def state(self, key: str) -> dict:
        return self.page_state.setdefault(key, {})

    def record(self, name: str, value: object) -> None:
        try:
            self.history.setdefault(name, deque(maxlen=HISTORY_SAMPLES)).append(float(value))
        except (TypeError, ValueError):
            pass


def _section(mapping: dict, name: str) -> dict:
    value = mapping.get(name)
    return value if isinstance(value, dict) else {}


def record_metrics(ctx: Context, metrics: dict[str, Any]) -> None:
    """Keep the series the dashboard and Monitoring draw as trends."""
    gpu, cpu = _section(metrics, "gpu"), _section(metrics, "cpu")
    power, memory = _section(metrics, "power"), _section(metrics, "memory")
    sensors = _section(metrics, "sensors")
    ctx.record("gpu_clock", gpu.get("frequency_mhz"))
    ctx.record("gpu_temp", gpu.get("temperature_c"))
    ctx.record("gpu_power", power.get("value_w") if power.get("value_w") is not None else gpu.get("power_w"))
    ctx.record("gpu_volt", gpu.get("voltage_mv"))
    ctx.record("gpu_load", gpu.get("usage_percent") if gpu.get("usage_percent") is not None else gpu.get("compute_busy_percent"))
    ctx.record("cpu_load", cpu.get("usage_percent"))
    ctx.record("cpu_clock", cpu.get("frequency_mhz"))
    ctx.record("cpu_temp", cpu.get("temperature_c"))
    ctx.record("ram", memory.get("usage_percent"))
    ctx.record("vrm_temp", sensors.get("vrm_temperature_c"))


class Poller:
    """Two daemon threads: real-time metrics, and the visible page's data."""

    def __init__(self, ctx: Context, pages: dict[str, Any], *, metrics_interval: float = 1.0):
        self.ctx = ctx
        self.pages = pages
        self.metrics_interval = metrics_interval
        self.active = ""
        self.active_tab = ""
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._threads: list[threading.Thread] = []
        self._loaded: dict[str, float] = {}
        self.dirty = threading.Event()

    def start(self) -> None:
        for target, name in ((self._metrics_loop, "metrics"), (self._page_loop, "page")):
            thread = threading.Thread(target=target, name=f"bc250-tui-{name}", daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def show(self, key: str, tab: str = "") -> None:
        self.active, self.active_tab = key, tab
        self.refresh()

    def refresh(self) -> None:
        self._loaded.pop(self.active, None)
        self._wake.set()

    def _metrics_loop(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                metrics = self.ctx.service.metricas_tiempo_real()
                metrics = metrics if isinstance(metrics, dict) else {}
                # Performance keeps its own two-minute histories once it has been opened, as the desktop does.
                recorder = self.ctx.page_state.get("performance", {}).get("recorder")
                readings = recorder.read(metrics) if recorder is not None else None
                with self.ctx.lock:
                    self.ctx.metrics = metrics
                    self.ctx.metrics_error = ""
                    record_metrics(self.ctx, self.ctx.metrics)
                    if recorder is not None:
                        recorder.record(metrics, readings)
            except Exception as error:  # a failed read must not end the loop
                logger.debug("metrics read failed", exc_info=True)
                with self.ctx.lock:
                    self.ctx.metrics_error = describe_error(error)
            self.dirty.set()
            self._stop.wait(max(0.1, self.metrics_interval - (time.monotonic() - started)))

    def _page_loop(self) -> None:
        while not self._stop.is_set():
            key = self.active
            page = self.pages.get(key)
            if page is not None and page.loads:
                due = self._loaded.get(key, 0.0) + page.interval
                if time.monotonic() >= due:
                    self._load(key, page)
            self._wake.wait(0.25)
            self._wake.clear()

    def _load(self, key: str, page: Any) -> None:
        self._loaded[key] = time.monotonic()
        try:
            data = page.load(self.ctx)
            with self.ctx.lock:
                self.ctx.page_data[key] = data
                self.ctx.page_error.pop(key, None)
        except Exception as error:
            logger.debug("page %s failed to load", key, exc_info=True)
            with self.ctx.lock:
                self.ctx.page_error[key] = describe_error(error)
        self.dirty.set()
