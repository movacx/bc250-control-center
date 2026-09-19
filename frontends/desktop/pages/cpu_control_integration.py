"""Incorporation of the unified CPU module into ``CpuSmuPage``.

Destination: ``frontends/desktop/pages/cpu_control_integration.py``

Strategy, mirroring ``gpu_governor_integration.py``: ``cpu_smu.py`` is **not
rewritten** (2500+ lines of tested tuning, persistence and core-unlock logic).
Only what the user sees changes.

``CpuSmuPage`` builds two workspace pages behind a tab bar::

    page.workspace_tabs                ← "CPU configuration" / "Overview"
    page.workspace_stack
      ├── page.overview_page           ← QGridLayout `page.workspace`
      └── page.configuration_page

This module adds one more stack page holding :class:`CpuControlView`, makes it
the only page the user can reach, and hides the tab bar — the whole point of
the redesign is that there is nothing left to switch between. The legacy
pages are left entirely alone rather than emptied, because ``_reflow``
rebuilds those grids from the legacy cards on every width change and would
undo anything mounted inside them. Those cards stay instantiated and simply
never shown, so every existing method that writes to ``processor_stats``,
``core_stats``, ``metric_tiles``, ``runtime_stats`` or ``core_shape_line``
keeps working untouched.

Consequences:

* ``_apply_refresh_payload`` is wrapped, not replaced: the legacy widgets are
  still updated first, and the new view is then given a state object built
  from the very same payload. There is no second telemetry source to drift.
* Hardware actions still go through the page's own methods (``_apply_custom``,
  ``enable_persistence``, ``disable_persistence``, ``show_persistence_status``,
  ``_request_core_unlock``), keeping their validation, confirmation dialogs
  and concurrency gate. The view states intent; it never builds a privileged
  command and never owns a confirmation.
* Persistence reports go to the application's embedded terminal through the
  ``_report_persistence`` seam, so there is one place command output is read
  rather than a second read-only box inside this page.
* Staged values are mirrored onto the legacy controls before those methods
  run, so both halves always agree on what is being applied.
* The GDDR6 readings are not this page's business: they belong to the board,
  and the dashboard's own strip drives them.

Integration (two lines at the end of ``CpuSmuPage.__init__``)::

    from .cpu_control_integration import install_unified_cpu_control
    ...
    install_unified_cpu_control(self)

To roll back, delete those two lines. Nothing else was modified.
"""

from __future__ import annotations

from dataclasses import replace

from PyQt6.QtCore import QProcess
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from ..core.preferences import application_settings
from ..i18n import tr, tr_format
from .cpu_control_view import (
    DEFAULT_CPU_PROFILES,
    CoreReading,
    CoreUnlockState,
    CpuControlState,
    CpuControlView,
    CpuProfile,
    CpuTuningRequest,
    CpuTuningState,
    RuntimeReading,
)

_ATTRIBUTE = "_unified_cpu_control"

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
# Saved profiles — one QSettings slot per card, like the GPU module's
# ─────────────────────────────────────────────────────────────────────────────

def _profile_prefix(index: int) -> str:
    return f"cpu/profile_{index}/"


def _load_profiles() -> tuple[CpuProfile, ...]:
    """Reads the user's profile overrides, falling back per slot."""
    settings = application_settings()
    profiles: list[CpuProfile] = []
    for index, default in enumerate(DEFAULT_CPU_PROFILES):
        prefix = _profile_prefix(index)
        # The slot also records which default it was saved against. Without
        # that, changing the shipped set silently loaded the previous tier's
        # numbers into its replacement, and the card showed a frequency the
        # release notes said had changed.
        stored_key = str(settings.value(prefix + "key", "") or "").strip()
        name = str(settings.value(prefix + "name", "") or "").strip()
        if not name or stored_key != default.key:
            profiles.append(replace(default))
            continue
        try:
            frequency = int(settings.value(prefix + "frequency", default.frequency_mhz))
            vid = int(settings.value(prefix + "vid", default.vid_mv))
            temperature = int(
                settings.value(prefix + "temperature", default.temperature_c)
            )
        except (TypeError, ValueError):
            profiles.append(replace(default))
            continue
        profiles.append(
            replace(
                default,
                name=name,
                frequency_mhz=frequency,
                vid_mv=vid,
                temperature_c=temperature,
            )
        )
    return tuple(profiles)


def _persist_profile(profile: CpuProfile) -> None:
    """Saves one edited profile into its own slot."""
    slot = next(
        (
            index
            for index, default in enumerate(DEFAULT_CPU_PROFILES)
            if default.key == profile.key
        ),
        None,
    )
    if slot is None:
        return
    settings = application_settings()
    prefix = _profile_prefix(slot)
    settings.setValue(prefix + "key", profile.key)
    settings.setValue(prefix + "name", profile.name)
    settings.setValue(prefix + "frequency", int(profile.frequency_mhz))
    settings.setValue(prefix + "vid", int(profile.vid_mv))
    settings.setValue(prefix + "temperature", int(profile.temperature_c))
    settings.sync()


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


def _is_running(page) -> bool:
    process = getattr(page, "process", None)
    running = process is not None and process.state() != QProcess.ProcessState.NotRunning
    return bool(running or getattr(page, "_command_build_pending", False))


#: Where each runtime reading already lives on the legacy page. Reading the
#: rendered widgets rather than recomputing the values keeps one source of
#: truth: ``_apply_refresh_payload`` fills these, and this only mirrors them.
_RUNTIME_SOURCES = (
    ("persistence", "persistence_stat"),
    ("last_operation", "last_operation_stat"),
    ("applied", "applied_tuning_stat"),
    ("detection", "detected_scale_stat"),
    ("scale", "live_scale_stat"),
    ("live", "live_telemetry_stat"),
)


def _runtime_readings(page) -> dict[str, RuntimeReading]:
    readings: dict[str, RuntimeReading] = {}
    for key, attribute in _RUNTIME_SOURCES:
        stat = getattr(page, attribute, None)
        if stat is None:
            continue
        readings[key] = RuntimeReading(
            value=stat.value.text(), detail=stat.detail.text()
        )
    return readings


def _tuning_state(page) -> CpuTuningState:
    """Reads what the legacy controls and the page's own status already know."""
    current = _dict(getattr(page, "current_state", {}))
    return CpuTuningState(
        frequency_mhz=int(page.frequency_control.value()),
        vid_mv=int(page.vid_control.value()),
        temperature_c=int(page.temperature_control.value()),
        scale=int(page.scale_control.value()),
        manual_scale_available=bool(getattr(page, "_manual_scale_available", False)),
        applying=_is_running(page),
        persistence_enabled=bool(current.get("service_enabled")),
        runtime=_runtime_readings(page),
    )


def _control_state(page, payload: dict) -> CpuControlState:
    core_unlock = _dict(payload.get("core_unlock"))
    processor = _dict(core_unlock.get("processor"))
    return CpuControlState(
        model_name=str(processor.get("model_name") or ""),
        architecture=str(processor.get("architecture") or ""),
        vendor=str(processor.get("vendor") or ""),
        platform_process=str(processor.get("platform_process") or ""),
        microcode=str(processor.get("microcode") or ""),
        topology=str(processor.get("topology") or ""),
        cache=str(processor.get("cache") or ""),
        features=str(processor.get("features") or ""),
        total_usage_percent=_number(processor.get("total_usage_percent")),
        cores=_core_readings(core_unlock),
        core_unlock=_core_unlock_state(page, core_unlock),
        tuning=_tuning_state(page),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Controller — owns only what has no legacy counterpart
# ─────────────────────────────────────────────────────────────────────────────

class CpuControlController:
    """Feeds the unified view from the payload the legacy page already reads."""

    def __init__(self, page, view: CpuControlView):
        self.page = page
        self.view = view
        self._payload: dict = {}

        view.apply_requested.connect(self._apply)
        view.profile_changed.connect(_persist_profile)
        view.persistence_requested.connect(self._persistence)
        view.unlock_cores_requested.connect(page._request_core_unlock)
        view.firmware_persistence_requested.connect(
            page._open_firmware_persistence_guide
        )

    # ------------------------------------------------------------- intentions

    def _apply(self, request: CpuTuningRequest) -> None:
        """Mirror the staged values, then let the page validate and confirm.

        ``_apply_custom`` owns the range checks and both confirmation dialogs
        (automatic and manual). Reimplementing either here would mean two
        places deciding what is safe, which is exactly how the two halves of
        this screen drifted apart before.
        """
        self._stage(request)
        self.view.follow_hardware_again()
        self.page._apply_custom()

    def _stage(self, request: CpuTuningRequest) -> None:
        page = self.page
        # The manual-scale check box gates which controls the page reads, so
        # it has to be set before the values it guards.
        if page.scale_override_check.isEnabled():
            page.scale_override_check.setChecked(bool(request.manual_scale))
        page.frequency_control.setValue(int(request.frequency_mhz))
        page.vid_control.setValue(int(request.vid_mv))
        page.temperature_control.setValue(int(request.temperature_c))
        if request.manual_scale:
            page.scale_control.setValue(int(request.scale))

    def _persistence(self, action: str) -> None:
        page = self.page
        if action == "save":
            self._stage(self.view.staged_request())
            page.enable_persistence()
        elif action == "remove":
            page.disable_persistence()
        else:
            page.show_persistence_status()

    # -------------------------------------------------------------- refreshes

    def _redraw(self) -> None:
        self.view.apply_state(_control_state(self.page, self._payload))

    def apply_payload(self, payload: dict) -> None:
        """Called right after the legacy widgets consumed the same payload."""
        self._payload = payload
        self._redraw()

    def refresh_runtime(self) -> None:
        """Re-read only what the legacy controls hold, without a new payload."""
        self._redraw()


# ─────────────────────────────────────────────────────────────────────────────
# Mounting
# ─────────────────────────────────────────────────────────────────────────────

def install_unified_cpu_control(page) -> CpuControlView:
    """Replace the two CPU tabs with one workspace."""
    existing = getattr(page, _ATTRIBUTE, None)
    if existing is not None:
        return existing

    view = CpuControlView()
    controller = CpuControlController(page, view)

    host = QWidget()
    host.setProperty("cpuWorkspacePage", True)
    host.setMinimumWidth(0)
    host_box = QVBoxLayout(host)
    host_box.setContentsMargins(0, 0, 0, 0)
    host_box.addWidget(view)
    page.unified_cpu_page = host
    page.workspace_stack.addWidget(host)
    page.workspace_stack.setCurrentWidget(host)

    # One workspace means nothing left to switch between. The tab bar stays
    # constructed so ``_reflow_workspace_tabs`` keeps working; a hidden widget
    # consumes no layout space.
    page.workspace_tabs.hide()

    # The session console moves with the workspace instead of being rebuilt:
    # everything the page already writes to it keeps arriving, and the column
    # that would otherwise end in dead space now ends in the operation log.
    console = getattr(page, "console", None)
    if console is not None:
        view.mount_console(console)

    original_select = page._select_workspace

    def _select_workspace(name: str) -> None:
        original_select(name)
        page.workspace_stack.setCurrentWidget(host)
        # Both dashboard shortcuts now land on the same screen, so the one
        # that promises the core unlock has to scroll to it.
        if name == "configuration":
            view.scroll_to_top()
        else:
            view.reveal_danger_zone()

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

    # Whether an operation is running does not arrive through the refresh
    # payload, so without this the view would keep offering Apply while a
    # privileged command was still going.
    original_set_running = page._set_running

    def _set_running(running: bool, success: bool | None = None) -> None:
        original_set_running(running, success)
        controller.refresh_runtime()

    page._set_running = _set_running


    original_retranslate = getattr(page, "retranslate_dynamic_copy", None)

    def retranslate_dynamic_copy() -> None:
        if original_retranslate is not None:
            original_retranslate()
        view.retranslate_dynamic_copy()

    page.retranslate_dynamic_copy = retranslate_dynamic_copy

    setattr(page, _ATTRIBUTE, view)
    page._cpu_control_controller = controller
    view.set_profiles(_load_profiles())
    return view
