"""Incorporation of the redesigned CPU module into ``CpuSmuPage``.

Destination: ``frontends/desktop/pages/cpu_overview_integration.py``

Strategy, mirroring ``gpu_governor_integration.py``: ``cpu_smu.py`` is **not
rewritten** (2500+ lines of tested tuning, persistence and core-unlock logic).
Only the *Overview and live monitoring* workspace changes.

``CpuSmuPage`` already has::

    page.workspace_stack
      ├── page.overview_page       ← QGridLayout `page.workspace`
      └── page.configuration_page

This module adds a *third* stack page holding :class:`CpuOverviewView` and
points the Overview tab at it. The legacy ``overview_page`` is left entirely
alone rather than emptied, because ``_reflow`` rebuilds that grid from the
four legacy cards on every width change and would undo anything mounted
inside it. Those cards stay instantiated and simply never shown, so every
existing method that writes to ``processor_stats``, ``core_stats``,
``metric_tiles`` or ``core_shape_line`` keeps working untouched.

Consequences:

* ``_apply_refresh_payload`` is wrapped, not replaced: the legacy widgets are
  still updated first, and the new view is then given a state object built
  from the very same payload. There is no second telemetry source to drift.
* Hardware actions still go through the page's own methods
  (``_request_core_unlock``, ``_open_firmware_persistence_guide``), keeping
  their confirmation dialogs, concurrency gate and console output.
* The GDDR6 readings are not this page's business: they belong to the board,
  and the dashboard's own strip drives them. This module only reads the shared
  monitor so the telemetry tile can show the average.

Integration (two lines at the end of ``CpuSmuPage.__init__``)::

    from .cpu_overview_integration import install_redesigned_cpu_overview
    ...
    install_redesigned_cpu_overview(self)

To roll back, delete those two lines. Nothing else was modified.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout, QWidget

from ..core.gddr6_monitor import Gddr6Reading, gddr6_monitor_for
from ..i18n import tr, tr_format
from .cpu_overview_view import (
    CoreReading,
    CoreUnlockState,
    CpuOverviewState,
    CpuOverviewView,
)

_ATTRIBUTE = "_redesigned_cpu_overview"

#: Live sampling interval. Every sample is eight SMU mailbox round trips plus
#: a Polkit check, so this is deliberately slower than the 4 s page refresh.
LIVE_INTERVAL_MS = 5_000

def _number(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _dict(value) -> dict:
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    try:
        return dict(value or {})
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# State assembly — one payload in, one state out
# ─────────────────────────────────────────────────────────────────────────────

def _core_readings(core_unlock: dict) -> tuple[CoreReading, ...]:
    raw = core_unlock.get("cores")
    entries = raw if isinstance(raw, list) else []
    readings = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        index = int(_number(item.get("index"), -1))
        if index < 0:
            continue
        threads = tuple(item.get("threads") or ())
        readings.append(
            CoreReading(
                index=index,
                frequency_mhz=_number(item.get("frequency_mhz")),
                usage_percent=_number(item.get("usage_percent")),
                threads=", ".join(str(thread) for thread in threads),
                online=True,
            )
        )
    return tuple(readings)


def _core_unlock_state(page, core_unlock: dict) -> CoreUnlockState:
    governor_active = bool(core_unlock.get("governor_active"))
    return CoreUnlockState(
        detected_shape=tr_format(
            "{cores} cores / {threads} threads",
            cores=int(_number(core_unlock.get("physical_cores"))),
            threads=int(_number(core_unlock.get("logical_cpus"))),
        ),
        source_ready=bool(core_unlock.get("repository_ready")),
        helper_ready=bool(core_unlock.get("helper_ready")),
        governor_state=tr("Active now") if governor_active else tr("Inactive"),
        unlock_allowed=bool(page.core_unlock_button.isEnabled()),
        unlocked=bool(core_unlock.get("unlocked")),
    )


def _overview_state(page, payload: dict, gddr6: Gddr6Reading) -> CpuOverviewState:
    core_unlock = _dict(payload.get("core_unlock"))
    processor = _dict(core_unlock.get("processor"))
    performance = _dict(payload.get("performance"))
    # The performance payload publishes this flat, as ``vrm_temp``; only the
    # dashboard's own state object nests it under ``sensors``. Reading just the
    # nested spelling reported "not detected" on a board whose nct6686 does
    # expose a VRM MOS sensor.
    sensors = _dict(performance.get("sensors"))
    vrm = performance.get("vrm_temp", sensors.get("vrm_temperature_c"))
    return CpuOverviewState(
        model_name=str(processor.get("model_name") or ""),
        architecture=str(processor.get("architecture") or ""),
        vendor=str(processor.get("vendor") or ""),
        platform_process=str(processor.get("platform_process") or ""),
        microcode=str(processor.get("microcode") or ""),
        topology=str(processor.get("topology") or ""),
        cache=str(processor.get("cache") or ""),
        features=str(processor.get("features") or ""),
        total_usage_percent=_number(processor.get("total_usage_percent")),
        frequency_text=page.frequency_metric.value.text(),
        voltage_text=page.voltage_metric.value.text(),
        temperature_text=page.temperature_metric.value.text(),
        power_text=page.power_metric.value.text(),
        power_label=page.power_metric.label.text(),
        power_detail=page.power_metric.detail.text(),
        vrm_temperature_c=_number(vrm) if vrm not in (None, "", 0) else None,
        cores=_core_readings(core_unlock),
        core_unlock=_core_unlock_state(page, core_unlock),
        gddr6=gddr6,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Controller — owns only what has no legacy counterpart
# ─────────────────────────────────────────────────────────────────────────────

class CpuOverviewController:
    """Feeds the redesigned view; the GDDR6 engine lives in the shared monitor."""

    def __init__(self, page, view: CpuOverviewView):
        self.page = page
        self.view = view
        self.monitor = gddr6_monitor_for(page.controller)
        self._payload: dict = {}

        self.monitor.changed.connect(self._on_reading)

        view.unlock_cores_requested.connect(page._request_core_unlock)
        view.firmware_persistence_requested.connect(page._open_firmware_persistence_guide)

    # -------------------------------------------------------------- refreshes

    def _redraw(self) -> None:
        self.view.apply_state(
            _overview_state(self.page, self._payload, self.monitor.reading)
        )

    def _on_reading(self, _reading) -> None:
        self._redraw()

    def apply_payload(self, payload: dict) -> None:
        """Called right after the legacy widgets consumed the same payload."""
        self._payload = payload
        self._redraw()

    def refresh_status(self) -> None:
        self.monitor.refresh_status()


# ─────────────────────────────────────────────────────────────────────────────
# Mounting
# ─────────────────────────────────────────────────────────────────────────────

def install_redesigned_cpu_overview(page) -> CpuOverviewView:
    """Point the Overview tab at the redesigned module."""
    existing = getattr(page, _ATTRIBUTE, None)
    if existing is not None:
        return existing

    view = CpuOverviewView()
    controller = CpuOverviewController(page, view)

    host = QWidget()
    host.setProperty("cpuWorkspacePage", True)
    host.setMinimumWidth(0)
    host_box = QVBoxLayout(host)
    host_box.setContentsMargins(0, 0, 0, 0)
    host_box.addWidget(view)
    page.overview_redesigned_page = host
    page.workspace_stack.addWidget(host)

    original_select = page._select_workspace

    def _select_workspace(name: str) -> None:
        original_select(name)
        if name != "configuration":
            page.workspace_stack.setCurrentWidget(host)

    page._select_workspace = _select_workspace

    original_apply = page._apply_refresh_payload

    def _apply_refresh_payload(payload: dict) -> None:
        # The legacy widgets consume the payload first and unchanged; the new
        # view is then given a state built from that very same payload, so
        # there is never a second telemetry source to drift.
        original_apply(payload)
        controller.apply_payload(payload)

    page._apply_refresh_payload = _apply_refresh_payload
    # AsyncRefresh captured the bound method at construction time, so the
    # instance attribute above would otherwise never be reached.
    page._refresher._apply_result = _apply_refresh_payload

    original_retranslate = getattr(page, "retranslate_dynamic_copy", None)

    def retranslate_dynamic_copy() -> None:
        if original_retranslate is not None:
            original_retranslate()
        view.retranslate_dynamic_copy()

    page.retranslate_dynamic_copy = retranslate_dynamic_copy

    setattr(page, _ATTRIBUTE, view)
    page._cpu_overview_controller = controller
    controller.refresh_status()
    return view
