from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QGridLayout,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from bc250cc.application.gpu.diagnostics import (
    DiagnosticText,
)
from bc250cc.application.gpu.range_policy import (
    RangeEvidence,
    RangeNotice,
    validate_gpu_range,
)
from bc250cc.application.gpu.runtime import RuntimeText
from bc250cc.application.gpu.safe_points import build_safe_point_plan
from bc250cc.application.gpu.safety import SafetyMessage
from bc250cc.application.gpu.service_action import plan_gpu_service_action
from bc250cc.application.gpu.telemetry import (
    TelemetryText,
    present_gpu_telemetry,
)
from bc250cc.application.gpu.voltage_apply import plan_voltage_apply
from bc250cc.application.preparation.gpu_dependency_plan import (
    DEFAULT_PREPARATION_COMPONENTS,
    GpuDependencyPlan,
)
from bc250cc.domain.gpu.oberon import OBERON_DESKTOP_PROFILES
from bc250cc.domain.gpu.profiles import (
    default_cyan_profiles,
)
from bc250cc.infrastructure.bazzite_async_compute import (
    BAZZITE_ASYNC_COMPUTE_REPOSITORY,
)
from bc250cc.infrastructure.gpu.governor_toml import (
    GOVERNOR_DEFAULT_VOLTAGES,
    SUPPORTED_VOLTAGE_LEVELS,
    VOLTAGE_BOOST_START_MHZ,
)
from bc250cc.infrastructure.system_setup import (
    CU_UNLOCK_OPTION,
    CU_UNLOCK_THERMAL_NOTE,
    HIDE_BOOT_MESSAGES_OPTION,
)

from ..components.async_tools import AsyncRefresh, BackgroundExecutor
from ..components.page_widgets import (
    ConfirmDialog,
    ControlPageHeader,
    PresetButton,
)
from ..components.responsive import (
    clear_grid,
    configure_responsive_scroll_area,
    effective_viewport_width,
)
from ..components.system_setup_controls import (
    MEMORY_OPTIONS,
    vram_size_label,
)
from ..components.toast import show_toast
from ..components.voltage_lab_drawer import VoltageLabDrawer
from ..components.widgets import InfoDialog
from ..core.external_links import open_external_url, open_local_file
from ..core.gfx1013_presenter import RADV_ROUTE_SECOND_FIX, present_gfx1013
from ..core.operation_gate import OperationGate
from ..core.preferences import application_settings
from ..core.state import state_cache_for
from ..core.voltage_keypad_guard import (
    clear_voltage_keypad_state,
    voltage_keypad_edit_active,
)
from ..i18n import shipped_name, tr, tr_format
from .gpu_governor_helpers import (  # noqa: F401  (re-exported: other modules and tests import them from here)
    _dict,
    _integer,
)
from .gpu_governor_widgets import (  # noqa: F401  (re-exported: other modules and tests import them from here)
    DependencyPreparationDialog,
    DynamicSafetyNotice,
    GpuProfileEditDialog,
    GpuSummaryStrip,
)

# Custom Cyan operating profiles (name + reference safe-point + range) are
# small enough to live directly in the shared UI settings file rather than a
# dedicated store. Three fixed slots mirror the three preset buttons.
_CUSTOM_PROFILE_SLOTS = 3
#: The shipped name of each slot, the source every language translates.
_CUSTOM_PROFILE_DEFAULT_NAMES = ("Balanced", "Gaming", "Benchmark")


def _custom_profile_name(index: int, name: object) -> str:
    """A slot's default saved in any language reads back as the source."""
    if 0 <= index < len(_CUSTOM_PROFILE_DEFAULT_NAMES):
        return shipped_name(name, _CUSTOM_PROFILE_DEFAULT_NAMES[index])
    return str(name or "").strip()



def _load_custom_gpu_profile(settings, index: int) -> dict | None:
    prefix = f"gpu/cyan_profile_{index}/"
    if not settings.contains(prefix + "name"):
        return None
    name = str(settings.value(prefix + "name", "")).strip()
    if not name:
        return None
    try:
        minimum = int(settings.value(prefix + "min", 0))
        maximum = int(settings.value(prefix + "max", 0))
        frequency = int(settings.value(prefix + "frequency", 0))
        voltage = int(settings.value(prefix + "voltage", 0))
    except (TypeError, ValueError):
        return None
    if minimum <= 0 or maximum <= 0 or minimum > maximum:
        return None
    return {
        "name": _custom_profile_name(index, name),
        "min": minimum,
        "max": maximum,
        "frequency": frequency,
        "voltage": voltage,
    }


def _save_custom_gpu_profile(settings, index: int, profile: dict) -> None:
    prefix = f"gpu/cyan_profile_{index}/"
    settings.setValue(prefix + "name", _custom_profile_name(index, profile["name"]))
    settings.setValue(prefix + "min", int(profile["min"]))
    settings.setValue(prefix + "max", int(profile["max"]))
    settings.setValue(prefix + "frequency", int(profile["frequency"]))
    settings.setValue(prefix + "voltage", int(profile["voltage"]))
    settings.sync()




from .gpu_governor_state import GpuGovernorStateMixin  # noqa: E402  (needs names defined above, so imported here)


class GpuGovernorPage(GpuGovernorStateMixin, QWidget):
    """Complete GPU control studio using the validated cyan-skillfish governor backend."""

    #: True while a hardware operation is in flight, False once it has ended.
    operation_busy_changed = pyqtSignal(bool)

    GOVERNOR_CONFIG_PATH = Path("/etc/cyan-skillfish-governor-smu/config.toml")
    OBERON_CONFIG_PATH = Path("/etc/oberon-config.yaml")
    SELECTED_RANGE_FLOOR = 1000

    CYAN_PROFILE_VALUES = tuple(
        (profile.label, f"{profile.minimum_mhz}–{profile.maximum_mhz} MHz", (profile.minimum_mhz, profile.maximum_mhz))
        for profile in default_cyan_profiles()
    )
    OBERON_PROFILE_VALUES = (
        ("Balanced", "1000–1500 MHz", OBERON_DESKTOP_PROFILES[0]),
        ("Gaming", "1000–1850 MHz", OBERON_DESKTOP_PROFILES[1]),
        ("Benchmark", "1000–2000 MHz", OBERON_DESKTOP_PROFILES[2]),
    )
    PROFILE_VALUES = CYAN_PROFILE_VALUES
    VOLTAGE_PROFILE_LEVELS = SUPPORTED_VOLTAGE_LEVELS
    VOLTAGE_LAB_FREQUENCIES = tuple(GOVERNOR_DEFAULT_VOLTAGES)
    VOLTAGE_LAB_BASE = GOVERNOR_DEFAULT_VOLTAGES
    # The packaged upstream curve is the only documented baseline. Previous
    # local reference values were guesses and omitted 2230 MHz.
    PACKAGED_DEFAULT_VOLTAGES = GOVERNOR_DEFAULT_VOLTAGES

    def __init__(self, controller, parent: QWidget | None = None, *, settings_service=None):
        super().__init__(parent)
        self.setProperty("redesignedModule", True)
        self.controller = controller
        self.settings_service = settings_service
        self.current_state: dict = {}
        self._updates_active = False
        self._state_cache = state_cache_for(controller)
        self._background = BackgroundExecutor(self)
        self._action_gate = OperationGate()
        self._action_busy = False
        self.current_perf: dict = {}
        self.allowed_min = 300
        self.allowed_max = 2000
        self.active_min = 500
        self.active_max = 1500
        self._controls_initialized = False
        self._syncing_range_controls = False
        self._range_user_dirty = False
        self._active_range_signature: tuple[int, int] | None = None
        self.safe_frequencies: list[int] = []
        self.safe_voltage_map: dict[int, int] = {}
        self._safe_point_combo_signature: tuple[tuple[int, int], ...] = ()
        self._workspace_columns = 0
        self._preset_columns = 0
        self._field_columns = 0
        self._metric_columns = 0
        self._runtime_columns = 0
        self._runtime_action_columns = 0
        self._advanced_columns = 0
        self._voltage_summary_columns = 0
        self._voltage_workspace_columns = 0
        self._voltage_profile_columns = 0
        self._voltage_custom_values: dict[int, int] = {}
        #: Points typed into the custom editor and not applied yet. The rest
        #: of the custom values follow the curve on disk.
        self._voltage_custom_edited: set[int] = set()
        self._voltage_editable_frequencies: set[int] = set()
        self._voltage_profile_frequencies: set[int] = set()
        self._voltage_detected_level = 0
        self._voltage_applied_level: int | None = None
        self._last_operation_summary = "No hardware command has been executed."
        self._detailed_diagnostics = False
        self._profile_backend = ""
        self._cyan_compatibility_dirty = False
        self._custom_profile_overrides: dict[int, dict] = {}
        settings = application_settings()
        for slot in range(_CUSTOM_PROFILE_SLOTS):
            saved_profile = _load_custom_gpu_profile(settings, slot)
            if saved_profile is not None:
                self._custom_profile_overrides[slot] = saved_profile

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.page_stack = QStackedWidget()
        outer.addWidget(self.page_stack)

        self.overview_page = QWidget()
        overview_layout = QVBoxLayout(self.overview_page)
        overview_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        self.overview_scroll = scroll

        self.content = QWidget()
        configure_responsive_scroll_area(scroll, self.content)
        self.content.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(18, 8, 18, 24)
        layout.setSpacing(14)
        scroll.setWidget(self.content)
        overview_layout.addWidget(scroll)
        self.page_stack.addWidget(self.overview_page)

        self.header = ControlPageHeader(
            "GPU / GOVERNOR CONTROL",
            "Graphics tuning",
            "Validated runtime frequency control, passive hardware telemetry, governor persistence, and safe-point operations.",
            mode_text="● LIVE GOVERNOR",
        )
        self.header.refresh_requested.connect(self._manual_refresh)
        layout.addWidget(self.header)
        # Preserve the existing signal wiring without rendering the introductory
        # banner. The main GPU workspace now occupies the released top area.
        self.header.hide()

        # Preserve the shared live-value model without rendering the former
        # duplicate telemetry rail above the main GPU workspace.
        self.summary = GpuSummaryStrip(self.content)
        self.summary.hide()


        self.workspace = QGridLayout()
        self.workspace.setContentsMargins(0, 0, 0, 0)
        self.workspace.setHorizontalSpacing(14)
        self.workspace.setVerticalSpacing(14)
        layout.addLayout(self.workspace)

        self.configuration_card = self._build_configuration_card()
        # Restore any saved profile names/ranges over the just-built default
        # button text, so a returning user sees their own profiles immediately
        # rather than the stock Balanced/Gaming/Benchmark labels.
        self._apply_profile_overrides()
        # Keep the existing guide available for a future Help surface without
        # occupying the compact GPU configuration header.
        self.metrics_card = self._build_metrics_card()
        self.configuration_card.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.metrics_card.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.runtime_card = self._build_runtime_card()
        self._merge_runtime_into_metrics()
        # Runtime status is now part of the live telemetry card.  Keep the
        # original object alive as the update target, but never render its
        # former standalone governor-status frame.
        self.runtime_card.hide()
        self.advanced_card = self._build_advanced_card()
        layout.addWidget(self.advanced_card)
        layout.addStretch(1)


        # The normal GPU action opens this compact overlay and delegates every
        # write to the same validated apply path.
        self.voltage_lab_drawer = VoltageLabDrawer(self)
        self.voltage_lab_drawer.profile_requested.connect(
            self._select_drawer_voltage_profile
        )
        self.voltage_lab_drawer.custom_voltage_changed.connect(
            self._drawer_custom_voltage_changed
        )
        self.voltage_lab_drawer.apply_requested.connect(
            self._request_apply_voltage_curve_from_drawer
        )
        self.voltage_lab_drawer.restore_requested.connect(
            self._request_restore_voltage_defaults
        )

        self._reflow(1400)
        self.timer = QTimer(self)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(self.refresh)
        self._refresher = AsyncRefresh(
            self,
            "gpu-governor-refresh",
            self._fetch_refresh_payload,
            self._apply_refresh_payload,
            self._refresh_failed,
        )

        # Redesigned GPU view. Mounts inside overview_page and hides
        # overview_scroll for every backend (Cyan and Oberon); the original
        # widgets stay built because the apply logic still reads them.
        # Delete these two lines to roll back to the legacy layout.
        from .gpu_governor_integration import install_redesigned_gpu_view
        install_redesigned_gpu_view(self)


    def _request_cyan_compatibility(self) -> None:
        set_method = str(self.cyan_set_method.currentData() or "smu")
        usage_method = str(self.cyan_usage_method.currentData() or "busy-flag")
        fix_metrics = self.cyan_fix_metrics.isChecked()
        fix_frequency = self.cyan_fix_frequency.isChecked()
        compatibility_message = tr(
            "This validates and updates only gpu.set-method, gpu-usage.fix-metrics and gpu-usage.fix-freq. If Cyan is active, its current D-Bus range is read first, the service restarts, and that range is restored."
        ).replace("gpu.set-method", "gpu.set-method, gpu-usage.method", 1)
        dialog = ConfirmDialog(
            "Apply Cyan compatibility settings",
            compatibility_message,
            summary=(
                ("GPU set-method", set_method),
                ("gpu-usage.method", usage_method),
                ("fix-metrics", "Enabled" if fix_metrics else "Disabled"),
                ("fix-freq", "Enabled" if fix_frequency else "Disabled"),
            ),
            confirm_text="Apply compatibility settings",
            tone="blue" if set_method == "kernel" else "orange",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def success(result: object) -> None:
            self._cyan_compatibility_dirty = False
            self._last_operation_summary = tr(
                str(result or "Cyan compatibility settings updated.")
            )
            self.last_operation_line.set_values(
                "Cyan compatibility", self._last_operation_summary
            )
            self._append_console(self._last_operation_summary)

        self._run_backend_action(
            lambda: self.controller.configurar_compatibilidad_gpu_cyan(
                set_method, usage_method, fix_metrics, fix_frequency
            ),
            success,
            "Could not update Cyan compatibility settings",
            controls=(self.apply_cyan_compatibility,),
        )



    def _merge_runtime_into_metrics(self) -> None:
        """Place governor evidence and actions directly below live telemetry."""
        if not hasattr(self, "runtime_stats_panel") or not hasattr(
            self, "runtime_controls_panel"
        ):
            return
        for panel in (self.runtime_stats_panel, self.runtime_controls_panel):
            self.runtime_card.body.removeWidget(panel)
            self.metrics_card.body.addWidget(panel)
            panel.show()

    def _place_runtime_actions(self, *, oberon: bool) -> None:
        """Keep service actions beside the controls for Oberon, below telemetry for Cyan."""
        panel = getattr(self, "runtime_controls_panel", None)
        if panel is None:
            return
        target = self.configuration_card.body if oberon else self.metrics_card.body
        # removeWidget is intentionally idempotent and keeps the panel
        # available for the target layout.
        self.metrics_card.body.removeWidget(panel)
        self.configuration_card.body.removeWidget(panel)
        target.addWidget(panel)
        panel.show()




    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reflow(effective_viewport_width(self, self.overview_scroll))
        if getattr(self, "voltage_lab_drawer", None) is not None:
            self.voltage_lab_drawer.setGeometry(self.rect())
            if self.voltage_lab_drawer.is_open():
                self.voltage_lab_drawer.raise_()

    def _reflow(self, width: int) -> None:
        self._reflow_presets(width)
        self._reflow_range_fields(width)
        self._reflow_range_actions(width)
        self._reflow_metric_tiles(width)
        self._reflow_runtime_stats(width)
        self._reflow_runtime_actions(width)
        self._reflow_advanced(width)

        columns = 2 if width >= 1080 else 1
        if columns == self._workspace_columns and self.workspace.count():
            return
        self._workspace_columns = columns
        self._clear_grid(self.workspace)
        self.workspace.setColumnStretch(0, 0)
        self.workspace.setColumnStretch(1, 0)
        if columns == 2:
            # Keep configuration and telemetry on one shared baseline.  Using
            # the grid's natural row height avoids the previous “floating”
            # telemetry card and guarantees that the action row below starts
            # directly beneath both frames.
            # Oberon receives the service-action panel below its apply button,
            # so both columns can share the same natural content height.
            card_vertical_policy = QSizePolicy.Policy.Expanding
            self.configuration_card.setSizePolicy(
                QSizePolicy.Policy.Expanding, card_vertical_policy
            )
            self.metrics_card.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            self.workspace.addWidget(self.configuration_card, 0, 0)
            self.workspace.addWidget(self.metrics_card, 0, 1)
            self.workspace.setColumnStretch(0, 7)
            self.workspace.setColumnStretch(1, 5)
        else:
            # Restore natural heights when the viewport becomes narrow; this
            # prevents the stacked cards from inheriting the wide-layout
            # stretch and leaving an empty block between telemetry and actions.
            self.configuration_card.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            self.metrics_card.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            self.workspace.addWidget(
                self.configuration_card, 0, 0, 1, 1, Qt.AlignmentFlag.AlignTop
            )
            self.workspace.addWidget(
                self.metrics_card, 1, 0, 1, 1, Qt.AlignmentFlag.AlignTop
            )
            self.workspace.setColumnStretch(0, 1)











    @staticmethod
    def _clear_grid(layout: QGridLayout) -> None:
        clear_grid(layout)

    def _select_preset(self, button: PresetButton) -> None:
        minimum, maximum = button.payload
        self._range_user_dirty = True
        self._stage_range(
            int(minimum), int(maximum), preset=button.text().splitlines()[0]
        )

    def _stage_range(self, minimum: int, maximum: int, *, preset: str = "") -> None:
        minimum = max(self.allowed_min, min(self.allowed_max, int(minimum)))
        maximum = max(minimum, min(self.allowed_max, int(maximum)))
        self._syncing_range_controls = True
        try:
            self.minimum_control.setValue(minimum)
            self.maximum_control.setValue(maximum)
        finally:
            self._syncing_range_controls = False
        if preset:
            for button in self.preset_buttons:
                # Cyan owns four controls while Oberon owns three.  A hidden
                # Cyan button must never take the exclusive check state away
                # from the visible Oberon profile with the same title.
                if not button.isHidden():
                    button.setChecked(button.text().splitlines()[0] == preset)

    def _mark_custom_range(self, _text: str = "") -> None:
        if self._syncing_range_controls:
            return
        self._range_user_dirty = True
        current = (self.minimum_control.value(), self.maximum_control.value())
        matched = False
        for button in self.preset_buttons:
            if button.isHidden():
                continue
            if tuple(button.payload) == current:
                button.setChecked(True)
                matched = True
                break
        if not matched:
            self.preset_group.setExclusive(False)
            for button in self.preset_buttons:
                button.setChecked(False)
            self.preset_group.setExclusive(True)

    def _use_active_range(self) -> None:
        self._save_active_range_for_startup()

    def _save_active_range_for_startup(self) -> None:
        minimum = _integer(self.current_state.get("current_min"), 0)
        maximum = _integer(self.current_state.get("current_max"), 0)
        if minimum <= 0 or maximum <= 0 or minimum > maximum:
            self._show_info(
                "Active range unavailable",
                "Refresh GPU status before saving a startup range.",
                tone="orange",
            )
            return
        dialog = ConfirmDialog(
            "Save active range for startup",
            "This writes the currently active Cyan D-Bus range to the managed "
            "TOML. Cyan will use it at the next startup. The running GPU range "
            "and governor service will not be changed.",
            summary=(
                ("Minimum", f"{minimum} MHz"),
                ("Maximum", f"{maximum} MHz"),
                ("TOML section", "[frequency-range]"),
                ("Service", "No restart"),
            ),
            confirm_text="Save startup range",
            tone="orange",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def success(result: object) -> None:
            self._last_operation_summary = str(result or tr_format(
                "Saved {minimum}-{maximum} MHz for Cyan startup.",
                minimum=minimum,
                maximum=maximum,
            ))
            self.last_operation_line.set_values(
                "Save startup range", self._last_operation_summary
            )
            self._append_console(self._last_operation_summary)

        self._run_backend_action(
            self.controller.guardar_rango_gpu_arranque,
            success,
            "Could not save the startup range",
            controls=(self.use_active_button,),
        )

    def _clear_profile_checks(self) -> None:
        self.preset_group.setExclusive(False)
        for button in self.preset_buttons:
            button.setChecked(False)
        self.preset_group.setExclusive(True)





    def _show_operation_in_progress(self) -> None:
        """Ask the user to wait, and stop asking the moment they can act.

        The request that was refused is not queued: once the running
        operation ends, the dialog closes by itself and the control is free
        to be used again.
        """
        pending = self._action_gate.busy
        dialog = InfoDialog(
            "GPU operation in progress",
            "Wait for the current GPU operation to finish.",
            "warning_orange",
            self,
            eyebrow="GPU GOVERNOR",
            notice="",
            tone="orange",
            busy=pending,
        )
        if not pending:
            dialog.exec()
            return

        def close_when_idle(active: bool) -> None:
            if not active:
                dialog.accept()

        self.operation_busy_changed.connect(close_when_idle)
        try:
            dialog.exec()
        finally:
            self.operation_busy_changed.disconnect(close_when_idle)

    def _request_custom_range(self) -> None:
        minimum = self.minimum_control.value()
        maximum = self.maximum_control.value()
        self._request_runtime_range(
            minimum,
            maximum,
            controls=(self.apply_range_button,),
        )

    def _request_selected_safe_point_range(self) -> None:
        maximum = _integer(self.oc_frequency.currentData(), 0)
        if maximum <= 0:
            self._show_info(
                "No safe-point selected",
                "Refresh after installing or configuring the governor.",
                tone="orange",
            )
            return
        self._request_runtime_range(
            self.SELECTED_RANGE_FLOOR,
            maximum,
            controls=(self.apply_selected_range_button,),
        )

    def _request_runtime_range(
        self,
        minimum: int,
        maximum: int,
        *,
        controls: tuple[QWidget, ...],
    ) -> None:
        valid, warning = self._validate_range(minimum, maximum)
        if not valid:
            return
        risk = maximum >= 1850 or minimum >= 2000
        is_oberon = (
            str(self.current_state.get("governor_backend") or "") == "oberon-governor"
        )
        high_points = _dict(self.current_state.get("high_frequency_points"))
        reload_high_points = (
            not is_oberon
            and maximum > self.allowed_max
            and bool(high_points.get("enabled"))
        )
        message = tr(
            "This updates Oberon's two YAML endpoints to the upstream 1000 mV baseline and restarts the service if it is active."
            if is_oberon
            else "This updates only the active Cyan range through D-Bus. Persistent TOML limits are left unchanged; advanced safe-points are loaded only when explicitly enabled."
        )
        if reload_high_points:
            message += "\n\n" + tr(
                "Cyan will restart once to load the enabled high safe-points, then the requested D-Bus range will be verified."
            )
        if maximum >= 2000:
            message += "\n\n" + tr(
                "High-frequency confirmation: this 2000 MHz range changes live GPU hardware state. Verify cooling and stability before applying it."
            )
        if warning:
            message += "\n\n" + tr_format("Safety note: {warning}", warning=warning)
        dialog = ConfirmDialog(
            "Apply GPU runtime range",
            message,
            summary=(
                ("Minimum", f"{minimum} MHz"),
                ("Maximum", f"{maximum} MHz"),
                ("Safe-point voltage", self._safe_point_voltage_text(maximum)),
                (
                    "Persistence",
                    "Oberon YAML endpoints"
                    if is_oberon
                    else "Runtime D-Bus only; persistent TOML range unchanged",
                ),
            ),
            confirm_text="Apply high-frequency range" if maximum >= 2000 else "Apply range",
            tone="orange" if risk else "blue",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def success(result: object) -> None:
            self._range_user_dirty = False
            self._active_range_signature = (int(minimum), int(maximum))
            backend_message = (
                str(result.get("operation_message") or "")
                if isinstance(result, dict)
                else ""
            )
            self._last_operation_summary = backend_message or (
                f"Saved Oberon range {minimum}–{maximum} MHz and reloaded its active service."
                if is_oberon
                else f"Requested runtime range {minimum}–{maximum} MHz through D-Bus."
            )
            self.last_operation_line.set_values(
                "Apply range", self._last_operation_summary
            )
            self._append_console(self._last_operation_summary)

        self._run_backend_action(
            lambda: self.controller.aplicar_perfil_gpu(minimum, maximum),
            success,
            "GPU range failed",
            controls=controls,
        )

    def _open_governor_config(self) -> None:
        is_oberon = str(self.current_state.get("governor_backend") or "") == "oberon-governor"
        default_path = self.OBERON_CONFIG_PATH if is_oberon else self.GOVERNOR_CONFIG_PATH
        config_path = Path(
            str(self.current_state.get("config_path") or default_path)
        )
        if not config_path.is_file():
            self._show_info(
                tr("Governor configuration was not found"),
                tr_format(
                    "{path} does not exist. Install or repair the selected governor before opening its configuration.",
                    path=str(config_path),
                ),
                tone="orange",
            )
            return
        opened, message = open_local_file(config_path)
        if not opened:
            self._show_info(
                "Governor configuration could not be opened",
                tr_format(
                    "{path}: {error}",
                    path=str(config_path),
                    error=tr(message),
                ),
                tone="orange",
            )
            return
        self._append_console(
            tr_format(
                "Opened {path} with the system default editor.",
                path=str(config_path),
            )
        )

    def _open_telemetry_guide(self) -> None:
        url = "https://gitlab.com/mothenjoyer69/oberon-governor"
        opened, message = open_external_url(url)
        if not opened:
            self._show_info(
                "Oberon Governor repository could not be opened",
                tr_format("{url}: {error}", url=url, error=tr(message)),
                tone="orange",
            )

    def _request_high_points_toggle(self) -> None:
        state = _dict(self.current_state.get("high_frequency_points"))
        currently_enabled = bool(state.get("enabled"))
        enable = not currently_enabled
        frequencies = (
            ", ".join(str(value) for value in state.get("frequencies") or ()) or "2050+"
        )
        governor_active = (
            str(self.current_state.get("service_active") or "").lower() == "active"
        )
        dialog = ConfirmDialog(
            "Enable advanced +2000 MHz points"
            if enable
            else "Disable advanced +2000 MHz points",
            (
                "This edits only the TOML safe-point blocks above 2000 MHz and validates the complete "
                "file. These frequencies are experimental, are not guaranteed stable, and can crash "
                "the display or system. This does not reload Cyan or change the live GPU range; "
                "use Apply active range explicitly after selecting a point."
                if enable
                else "This comments the TOML safe-point blocks above 2000 MHz and validates the complete "
                "file. Active 3D workloads must be stopped first. This does not reload Cyan or "
                "change the live GPU range."
            ),
            summary=(
                ("Safe-points", frequencies),
                ("Requested state", "Enabled" if enable else "Commented"),
                ("Validation", "Full TOML parse before replacement"),
                (
                    "Service",
                    "No restart or clock change"
                    if governor_active
                    else "Keep disabled; no automatic start",
                ),
            ),
            confirm_text="Enable advanced points"
            if enable
            else "Disable advanced points",
            tone="red" if enable else "orange",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def success(result: object) -> None:
            self._apply_high_points_toggle_feedback(enable)
            self._last_operation_summary = str(result or "Governor TOML updated.")
            self.last_operation_line.set_values(
                "Advanced safe-points", self._last_operation_summary
            )
            self._append_console(self._last_operation_summary)

        self._run_backend_action(
            lambda: self.controller.alternar_puntos_gpu_altos(enable),
            success,
            "Could not update advanced safe-points",
            controls=(self.high_points_button,),
        )


    def _range_evidence(self) -> RangeEvidence:
        busy_raw = self.current_state.get("gpu_busy")
        high_points = _dict(self.current_state.get("high_frequency_points"))
        allowed_max = int(self.allowed_max)
        # A just-enabled high TOML curve is not visible to the current Cyan
        # process until it is restarted. The explicitly confirmed Apply action
        # below performs that reload and verifies fresh D-Bus bounds first.
        if bool(high_points.get("enabled")):
            high_ceiling = max(
                (int(value) for value in self.safe_frequencies if int(value) > 2000),
                default=0,
            )
            allowed_max = max(allowed_max, high_ceiling)
        return RangeEvidence(
            backend=str(self.current_state.get("governor_backend") or ""),
            allowed_min=int(self.allowed_min),
            allowed_max=allowed_max,
            safe_frequencies=tuple(int(value) for value in self.safe_frequencies),
            safe_voltages=dict(self.safe_voltage_map),
            packaged_voltages=dict(self.PACKAGED_DEFAULT_VOLTAGES),
            lab_frequencies=tuple(int(value) for value in self.VOLTAGE_LAB_FREQUENCIES),
            voltage_errors=tuple(
                item
                for item in self.current_state.get("safe_points_voltage_errors") or ()
                if isinstance(item, dict)
            ),
            duplicate_frequencies=tuple(
                int(value)
                for value in self.current_state.get("safe_points_duplicate_frequencies")
                or ()
            ),
            missing_voltage=tuple(
                int(item["frequency"])
                for item in self.current_state.get("safe_points_missing_voltage") or ()
                if isinstance(item, dict) and "frequency" in item
            ),
            config_error=str(self.current_state.get("safe_points_error") or ""),
            current_max=_integer(
                self.current_state.get("current_max"), self.active_max
            ),
            actual_clock=_integer(self.current_state.get("sclk_actual"), 0),
            gpu_busy=None if busy_raw is None else _integer(busy_raw, 0),
            set_method=str(
                _dict(self.current_state.get("cyan_telemetry")).get("set_method")
                or "smu"
            ),
        )

    def _show_range_notice(self, notice: RangeNotice) -> None:
        values = dict(notice.values)
        message = tr_format(notice.message, **values) if values else tr(notice.message)
        if notice.details:
            message += "\n\n" + notice.details
        self._show_info(notice.title, message, tone=notice.tone)

    def _validate_range(self, minimum: int, maximum: int) -> tuple[bool, str]:
        decision = validate_gpu_range(
            int(minimum), int(maximum), self._range_evidence()
        )
        if decision.notice is not None:
            self._show_range_notice(decision.notice)
        warnings = []
        for warning in decision.warnings:
            values = dict(warning.values)
            warnings.append(
                tr_format(warning.message, **values) if values else tr(warning.message)
            )
        return decision.valid, " ".join(warnings)

    def prepare_dependencies(self, *, dialog_parent: QWidget | None = None) -> None:
        tools = _dict(self.current_state.get("tools"))
        selected_governor = str(
            tools.get("governor_backend")
            or self.current_state.get("governor_backend")
            or "cyan-skillfish-governor-smu"
        )
        dialog = DependencyPreparationDialog(
            tools,
            selected_governor,
            dialog_parent or self,
            controller=self.controller,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        GpuGovernorPage.execute_dependency_action(
            self,
            action=dialog.action,
            preference=dialog.governor,
            selected_components=getattr(
                dialog,
                "selected_components",
                DEFAULT_PREPARATION_COMPONENTS,
            ),
            dialog_parent=dialog_parent,
            memory_policy=getattr(dialog, "memory_policy", "current"),
            memory_ttm_gib=getattr(dialog, "memory_ttm_gib", 0),
            vram_uma_size_mb=getattr(dialog, "vram_uma_size_mb", 0),
        )


    def _prepare_bazzite_memory_tuning(
        self,
        *,
        policy: str,
        ttm_gib: int,
        scope: str,
        dialog_parent: QWidget | None,
        takeover_zram: bool = False,
        target_mount: str = "",
    ) -> None:
        swap_label = {**{value: tr(label) for label, value in MEMORY_OPTIONS}, **{
            "current": tr("Keep Bazzite default (ZRAM)"),
            "zram-swap-16": tr("Recommended · ZRAM + 16 GiB emergency swap"),
            "zswap-16": tr("Advanced · ZSWAP + 16 GiB swapfile"),
            "zswap-32": tr("Advanced heavy loads · ZSWAP + 32 GiB swapfile"),
            "preserve": tr("Unchanged"),
        }}.get(policy, tr("Unknown"))
        bazzite = _dict(self.current_state.get("tools")).get("os_family") == "bazzite"
        ttm_label = (
            tr("Keep current TTM limit")
            if not ttm_gib
            else tr("Default (remove TTM limit)" if bazzite else "Restore previous TTM limit")
            if ttm_gib < 0
            else tr_format("{size} GiB TTM limit", size=ttm_gib)
        )
        takeover_zram = bool(takeover_zram) and not bazzite and scope == "swap"
        target_mount = str(target_mount or "").strip() if scope == "swap" else ""
        summary = (
            (
                (tr("Swap mode"), swap_label),
                *((
                    (tr("Swapfile location"), target_mount),
                ) if target_mount else ()),
                *((
                    (tr("Existing ZRAM"), tr("Will be disabled to make room for ZSWAP")),
                ) if takeover_zram else ()),
                (tr("Reboot"), tr("Required to activate the selected configuration" if bazzite
                                   else "Required to finish disabling the existing ZRAM" if takeover_zram
                                   else "A reboot may be required.")),
            )
            if scope == "swap"
            else (
                (tr("Dynamic GPU Memory Limit (TTM)"), ttm_label),
                # amdgpu sizes GTT when it loads: a boot argument, on every system.
                (tr("Reboot"), tr("Required to activate the selected configuration")),
            )
        )
        confirmation = ConfirmDialog(
            tr("Apply Swap" if scope == "swap" else "Apply TTM limit"),
            tr("This disables the ZRAM the distribution set up by default; ZSWAP takes over once you reboot. "
               "Nothing else about that ZRAM configuration is touched, and it comes back if you restore this setting.")
            if takeover_zram
            else tr("The limit is saved as a kernel boot argument, shared with BC250 Quick Access in Game Mode, "
                    "and takes effect at the next reboot.")
            if scope != "swap"
            else tr("A reboot may be required.") if bazzite
            else tr("Optional system setup. Disk swap uses up to 32 GiB of storage; existing user swap is preserved. TTM is applied live when supported. ZRAM and deferred restoration require a reboot. Hardware testing is still required."),
            summary=summary,
            confirm_text=tr("Apply Swap" if scope == "swap" else "Apply TTM"),
            tone="orange",
            parent=dialog_parent or self,
        )
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_backend_action(
            lambda: (self.controller.preparar_memoria_bazzite(policy, ttm_gib) if bazzite and scope == "swap"
                     else self.controller.preparar_memoria(
                         policy, ttm_gib, takeover_zram=takeover_zram, target_mount=target_mount)),
            lambda _result: GpuGovernorPage._record_preparation_result(
                self,
                tr("Memory & Swap"),
                tr("Workflow opened. Check the terminal result before rebooting."),
            ),
            tr("Could not prepare memory setup"),
            controls=(),
            error_parent=dialog_parent,
        )

    def _prepare_vram(self, *, uma_size_mb: int, dialog_parent: QWidget | None) -> None:
        """Write UMA_SIZE (VRAM) straight to the battery-backed CMOS bank.

        Every other CMOS byte -- clock speed and every memory timing strap --
        is read back unmodified and rewritten as-is; only this one field
        changes. See github.com/fanoush/bc250_memcfg for the reviewed layout.
        """
        uma_size_mb = int(uma_size_mb)
        if uma_size_mb <= 0:
            return
        confirmation = ConfirmDialog(
            tr("Apply VRAM size"),
            tr(
                "This writes directly to the BC250's battery-backed CMOS memory "
                "configuration. Only the VRAM allocation is changed; clock speed "
                "and memory timings are read back and rewritten unmodified. The "
                "new size takes effect after the next reboot, and can only be "
                "reverted from Control Center or by clearing CMOS."
            ),
            summary=(
                (tr("VRAM size (UMA_SIZE)"), vram_size_label(uma_size_mb)),
                (tr("Reboot"), tr("Required to activate the new VRAM size")),
            ),
            confirm_text=tr("Apply VRAM"),
            tone="orange",
            parent=dialog_parent or self,
        )
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_backend_action(
            lambda: self.controller.preparar_vram(uma_size_mb),
            lambda _result: GpuGovernorPage._record_preparation_result(
                self,
                tr("VRAM size"),
                tr("Workflow opened. Check the terminal result before rebooting."),
            ),
            tr("Could not prepare VRAM setup"),
            controls=(),
            error_parent=dialog_parent,
        )

    def _prepare_bazzite_mitigations(
        self, action: str, *, dialog_parent: QWidget | None
    ) -> None:
        action = str(action or "").strip().lower()
        if action not in {"disable", "restore"}:
            raise ValueError("Unsupported Bazzite CPU-mitigation action.")
        disabling = action == "disable"
        confirmation = ConfirmDialog(
            tr("Disable CPU security mitigations" if disabling else "Restore CPU security mitigations"),
            tr(
                "This disables optional kernel protections against multiple CPU vulnerabilities. It may improve performance in some workloads. The change applies after reboot and can be restored from Control Center."
                if disabling
                else "This restores the exact CPU mitigation arguments that existed before Control Center disabled them. The change applies after reboot."
            ),
            summary=(
                (tr("Platform"), "Bazzite"),
                (tr("Kernel argument"), "mitigations=off"),
                (tr("Reboot"), tr("Required to activate the selected configuration")),
            ),
            confirm_text=tr("Disable mitigations" if disabling else "Restore mitigations"),
            tone="red" if disabling else "orange",
            parent=dialog_parent or self,
        )
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_backend_action(
            lambda: self.controller.gestionar_mitigaciones_bazzite(action),
            lambda _result: GpuGovernorPage._record_preparation_result(
                self,
                tr("CPU security mitigations"),
                tr("The CPU mitigation change was staged. Reboot after the terminal reports success."),
            ),
            tr("Could not update CPU security mitigations"),
            controls=(),
            error_parent=dialog_parent,
        )

    def _prepare_bazzite_smt(
        self, action: str, *, dialog_parent: QWidget | None
    ) -> None:
        action = str(action or "").strip().lower()
        if action not in {"disable", "restore"}:
            raise ValueError("Unsupported Bazzite SMT action.")
        if action == "disable":
            # Same question the other distributions ask; restoring needs none.
            confirmation = ConfirmDialog(
                tr("Disable simultaneous multithreading"),
                tr(
                    "The CPU runs one thread per core: 6 or 8 threads instead of 12 or 16. Some games run smoother, others slower; measure yours. The change applies after reboot and can be restored from Control Center."
                ),
                summary=(
                    (tr("Platform"), "Bazzite"),
                    (tr("Kernel argument"), "nosmt"),
                    (tr("Reboot"), tr("Required to activate the selected configuration")),
                ),
                confirm_text=tr("Disable SMT"),
                tone="orange",
                parent=dialog_parent or self,
            )
            if confirmation.exec() != QDialog.DialogCode.Accepted:
                return
        self._run_backend_action(
            lambda: self.controller.gestionar_smt_bazzite(action),
            lambda _result: GpuGovernorPage._record_preparation_result(
                self,
                tr("Kernel boot options"),
                tr("The change was staged. Reboot after the terminal reports success."),
            ),
            tr("Could not change the kernel boot options"),
            controls=(),
            error_parent=dialog_parent,
        )

    def _prepare_bazzite_boot_messages(
        self, action: str, *, dialog_parent: QWidget | None
    ) -> None:
        action = str(action or "").strip().lower()
        if action not in {"hide", "restore"}:
            raise ValueError("Unsupported Bazzite boot-messages action.")
        hiding = action == "hide"
        confirmation = ConfirmDialog(
            tr("Hide the kernel's boot messages" if hiding else "Show the kernel's boot messages"),
            tr(
                "The BC-250's CPU makes the kernel print a warning about its random-number instructions (RDSEED) at every boot. This hides it by silencing all kernel messages on screen while the system starts, errors included, so a boot problem will show nothing there. It fixes nothing: the messages stay in dmesg and the system log. The change applies after reboot and can be restored from Control Center."
                if hiding
                else "This restores the exact kernel log level that existed before Control Center hid the boot messages. The change applies after reboot."
            ),
            summary=(
                (tr("Platform"), "Bazzite"),
                (tr("Kernel argument"), "loglevel=0"),
                (tr("Reboot"), tr("Required to activate the selected configuration")),
            ),
            confirm_text=tr("Hide boot messages" if hiding else "Show boot messages"),
            tone="orange",
            parent=dialog_parent or self,
        )
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_backend_action(
            lambda: self.controller.gestionar_mensajes_arranque_bazzite(action),
            lambda _result: GpuGovernorPage._record_preparation_result(
                self,
                tr("Boot messages"),
                tr("The boot-messages change was staged. Reboot after the terminal reports success."),
            ),
            tr("Could not update the kernel boot messages"),
            controls=(),
            error_parent=dialog_parent,
        )

    def _manage_kernel_options(
        self, options: tuple[str, ...], *, changed: str, dialog_parent: QWidget | None
    ) -> None:
        """Turn one of the managed kernel boot options on or off at the next boot."""
        if changed in options:
            # Adding any of them changes how the board runs, so it is asked
            # first; restoring needs no question.
            if changed == CU_UNLOCK_OPTION:
                title = "Unlock all 40 compute units with the kernel"
                body = (
                    "The BC-250 kernel unlocks the compute units by itself when amdgpu starts, so umr "
                    "and the CU live manager are not needed. Turn off the live manager's boot service "
                    "so only one of them sets the CUs. A board with a damaged CU pair cannot run all "
                    "40. The change applies after reboot and can be restored from Control Center."
                )
                body = tr(body) + "\n\n" + tr(CU_UNLOCK_THERMAL_NOTE)
                confirm_text, tone = "Unlock 40 CUs", "orange"
            elif changed == "mitigations=off":
                title = "Disable CPU security mitigations"
                body = (
                    "This disables optional kernel protections against multiple CPU vulnerabilities. "
                    "It may improve performance in some workloads. The change applies after reboot "
                    "and can be restored from Control Center."
                )
                confirm_text, tone = "Disable mitigations", "red"
            elif changed == HIDE_BOOT_MESSAGES_OPTION:
                title = "Hide the kernel's boot messages"
                body = (
                    "The BC-250's CPU makes the kernel print a warning about its random-number "
                    "instructions (RDSEED) at every boot. This hides it by silencing all kernel messages "
                    "on screen while the system starts, errors included, so a boot problem will show "
                    "nothing there. It fixes nothing: the messages stay in dmesg and the system log. "
                    "The change applies after reboot and can be restored from Control Center."
                )
                confirm_text, tone = "Hide boot messages", "orange"
            else:
                title = "Disable simultaneous multithreading"
                body = (
                    "The CPU runs one thread per core: 6 or 8 threads instead of 12 or 16. Some games "
                    "run smoother, others slower; measure yours. The change applies after reboot and "
                    "can be restored from Control Center."
                )
                confirm_text, tone = "Disable SMT", "orange"
            confirmation = ConfirmDialog(
                tr(title),
                # The unlock's body is already translated: it carries the
                # thermal paragraph, which has its own catalog entry.
                body if changed == CU_UNLOCK_OPTION else tr(body),
                summary=(
                    (tr("Kernel argument"), changed),
                    (tr("Reboot"), tr("Required to activate the selected configuration")),
                ),
                confirm_text=tr(confirm_text),
                tone=tone,
                parent=dialog_parent or self,
            )
            if confirmation.exec() != QDialog.DialogCode.Accepted:
                return
        self._run_backend_action(
            lambda: self.controller.gestionar_opciones_kernel(options),
            lambda _result: GpuGovernorPage._record_preparation_result(
                self,
                tr("Kernel boot options"),
                tr("The change was staged. Reboot after the terminal reports success."),
            ),
            tr("Could not change the kernel boot options"),
            controls=(),
            error_parent=dialog_parent,
        )

    def _manage_smt_live(self, mode: str, *, dialog_parent: QWidget | None) -> None:
        """Switch simultaneous multithreading now; it is not kept across a reboot."""
        mode = str(mode or "").strip().lower()
        if mode not in {"on", "off"}:
            raise ValueError("Unsupported SMT action.")
        if mode == "off":
            confirmation = ConfirmDialog(
                tr("Turn SMT off now"),
                tr(
                    "The CPU runs one thread per core until you turn it back on or restart: some games run smoother, others slower. "
                    "Nothing is saved: the next boot starts as the kernel boot options say."
                ),
                summary=((tr("Applies"), tr("Right now, until the next boot")),),
                confirm_text=tr("Turn SMT off now"),
                tone="orange",
                parent=dialog_parent or self,
            )
            if confirmation.exec() != QDialog.DialogCode.Accepted:
                return
        self._run_backend_action(
            lambda: self.controller.gestionar_smt_vivo(mode),
            lambda _result: GpuGovernorPage._record_preparation_result(
                self,
                tr("SMT"),
                tr("The terminal shows the new state."),
            ),
            tr("Could not switch SMT"),
            controls=(),
            error_parent=dialog_parent,
        )

    def _manage_steamos_readonly(
        self, action: str, *, dialog_parent: QWidget | None
    ) -> None:
        action = str(action or "").strip().lower()
        if action not in {"disable", "enable"}:
            raise ValueError("Unsupported SteamOS read-only action.")
        if action == "disable":
            # Turning the protection back on is always safe and needs no
            # question; taking it off is the step worth one.
            confirmation = ConfirmDialog(
                tr("Disable SteamOS read-only mode"),
                tr(
                    "The system files become writable so packages can be installed. The next SteamOS update turns the protection back on and removes anything installed into them. Control Center workflows that need it already switch it off and back on by themselves."
                ),
                summary=(
                    (tr("Platform"), "SteamOS"),
                    (tr("Command"), "steamos-readonly disable"),
                ),
                confirm_text=tr("Disable read-only mode"),
                tone="orange",
                parent=dialog_parent or self,
            )
            if confirmation.exec() != QDialog.DialogCode.Accepted:
                return
        self._run_backend_action(
            lambda: self.controller.gestionar_solo_lectura_steamos(action),
            lambda _result: GpuGovernorPage._record_preparation_result(
                self,
                tr("SteamOS read-only mode"),
                tr("The terminal shows the new state."),
            ),
            tr("Could not change SteamOS read-only mode"),
            controls=(),
            error_parent=dialog_parent,
        )

    def _manage_acpi(self, action: str, dialog_parent: QWidget | None = None) -> None:
        if action == "acpi-status":
            self._run_backend_action(
                lambda: self.controller.gestionar_acpi("acpi-check"),
                lambda _result: GpuGovernorPage._record_preparation_result(self, tr("CPU power management · ACPI"),
                                tr("No hardware command was executed.")),
                tr("Could not check ACPI status"), controls=(), error_parent=dialog_parent,
            )
            return
        tools = _dict(self.current_state.get("tools"))
        family = str(tools.get("os_family") or "")
        acpi_status = str(_dict(_dict(tools.get("system_setup")).get("acpi")).get("status") or "")
        # On SteamOS the same action writes the tables back after an update.
        repair = action == "acpi-update" and acpi_status == "needs-repair"
        label = (
            tr("Install correction") if action == "acpi-install"
            else tr("Repair correction") if repair
            else tr("Update correction") if action == "acpi-update"
            else tr("Uninstall")
        )
        body = (
            tr("A SteamOS update replaced /boot, so this image starts without the ACPI tables. This writes them back beside the kernel and regenerates the boot menu; nothing else changes. Reboot only after the terminal reports success.")
            if repair
            else tr("This replaces the tables of the BC250 ACPI boot entry with v1.1.1, which drops the C3 idle state that can freeze the board. The boot entries themselves are not changed. Reboot only after the terminal reports success.")
            if action == "acpi-update"
            else tr("On Bazzite every boot entry loads the ACPI tables, through GRUB's early_initrd setting; your BIOS and the system image are not changed. If it does not boot, open the submenu 'Bazzite without the BC250 ACPI tables (recovery)' at the end of the boot menu. Reboot only after the terminal reports success. Beta on Bazzite.")
            if action == "acpi-install" and family == "bazzite"
            else tr("On SteamOS every entry of this SteamOS image loads the ACPI tables, through GRUB's early initrd list; your BIOS is not changed and the other SteamOS image keeps the stock tables. If it does not boot, press e on the entry in the boot menu, delete /boot/bc250-acpi.cpio from the initrd line and press Ctrl+X, or start the other image. After a SteamOS update, use Repair correction. Reboot only after the terminal reports success. Beta on SteamOS.")
            if action == "acpi-install" and family == "steamos"
            else tr("This changes the default boot entry, not your BIOS. The original boot entry remains available for recovery. Use it if the ACPI entry does not boot. Reboot only after the terminal reports success. This optional integration still requires hardware testing.")
        )
        confirmation = ConfirmDialog(
            tr("CPU power management · ACPI"),
            body,
            summary=((tr("Action"), label),
                     (tr("Version"), "e-tho v1.1.1")),
            confirm_text=label,
            tone="orange", parent=dialog_parent or self,
        )
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_backend_action(
            lambda: self.controller.gestionar_acpi(action),
            lambda _result: GpuGovernorPage._record_preparation_result(self, tr("CPU power management · ACPI"),
                            tr("Workflow opened. Check the terminal result before rebooting.")),
            tr("Could not prepare ACPI setup"), controls=(), error_parent=dialog_parent,
        )

    def _prepare_steamos_quick_access(
        self,
        *,
        install_decky: bool,
        dialog_parent: QWidget | None,
    ) -> None:
        if install_decky:
            title = tr("Install Decky and BC250 Quick Access (Beta)")
            family = str(_dict(self.current_state.get("tools")).get("os_family") or "")
            bazzite_native = family == "bazzite"
            body = tr(
                "Bazzite installs Decky through its native ujust setup-decky install workflow. BC250 then installs only its local Quick Access panel. Continue?"
                if bazzite_native
                else "Decky Loader is an external third-party root-plugin service. This Beta workflow downloads its official stable installer to a temporary file and displays its SHA-256 in the terminal before it runs. Your confirmation in this dialog authorizes that explicit action. BC250 then installs only its local Quick Access panel. Continue?"
            )
            decky_method = (
                "ujust setup-decky install"
                if bazzite_native
                else tr("Official stable installer downloaded at execution time")
            )
            summary = (
                (tr("Decky"), decky_method),
                (
                    tr("BC250 plugin"),
                    tr("Installed only after Decky creates its plugin directory"),
                ),
                (
                    tr("Compatibility fallback"),
                    tr(
                        "Official Decky prerelease only when the installed stable version cannot support the current Steam initialization API"
                    ),
                ),
                (tr("Hardware"), tr("No GPU, CPU, CU or fan action is requested")),
                (tr("Game Mode"), tr("Restart or reload Decky after success")),
            )
            confirm_text = tr("Install Beta integration")
        else:
            title = tr("Install / repair BC250 Quick Access")
            body = tr(
                "This installs or repairs only the local BC250 Quick Access plugin and its protected helper inside an existing Decky installation. It does not reinstall Decky or apply a hardware setting. Continue?"
            )
            summary = (
                (tr("Decky"), tr("Existing installation required")),
                (tr("BC250 plugin"), tr("Transactional install / repair")),
                (tr("Hardware"), tr("No GPU, CPU, CU or fan action is requested")),
            )
            confirm_text = tr("Install / repair")
        confirmation = ConfirmDialog(
            title,
            body,
            summary=summary,
            confirm_text=confirm_text,
            tone="orange",
            parent=dialog_parent or self,
        )
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_backend_action(
            lambda: self.controller.preparar_quick_access_steamos(
                install_decky=install_decky
            ),
            lambda _result: GpuGovernorPage._record_preparation_result(
                self,
                "Game Mode Quick Access (Beta)",
                "Opened the explicit Game Mode Quick Access Beta workflow. Review the terminal output, then restart Game Mode after the official Decky installer and local BC250 panel finish successfully.",
            ),
            "Could not prepare Game Mode Quick Access",
            controls=(),
            error_parent=dialog_parent,
        )

    def _prepare_cachyos_bc250(
        self, action: str, *, dialog_parent: QWidget | None
    ) -> None:
        action = str(action or "kernel").strip().lower()
        actions = {
            "kernel": (
                "Install external Arch/CachyOS BC-250 kernel",
                "linux-cachyos-bc250 + headers",
                tr("Stock CachyOS kernel remains installed"),
            ),
            "mesa": (
                "Install external Arch/CachyOS BC-250 Mesa",
                "mesa + optional lib32-mesa",
                tr("System kernel is not changed"),
            ),
            "full": (
                "Install external Arch/CachyOS BC-250 kernel and Mesa",
                "linux-cachyos-bc250 + headers · mesa + optional lib32-mesa",
                tr("Stock CachyOS kernel remains installed"),
            ),
        }
        proton_packages = {
            "proton-native": "proton-cachyos-native-bc250",
            "proton-ge": "protonge-latest-bc250",
            "proton-slr": "proton-cachyos-slr-bc250",
        }
        for key, package in proton_packages.items():
            actions[key] = (
                "Install external Arch/CachyOS BC-250 Proton",
                package,
                tr("Kernel and Mesa are not changed"),
            )
        if action.startswith("remove-proton-"):
            package = proton_packages.get(action.removeprefix("remove-"))
            if package is None:
                raise ValueError("Unsupported CachyOS BC-250 action.")
            removal = ConfirmDialog(
                "Remove Proton BC-250",
                tr("This removes the Proton package from your system. Games that used it will ask for another Proton."),
                summary=((tr("Packages"), package),),
                confirm_text=tr("Open removal terminal"),
                tone="orange",
                parent=dialog_parent or self,
            )
            if removal.exec() != QDialog.DialogCode.Accepted:
                return
            self._run_backend_action(
                lambda: self.controller.preparar_cachyos_bc250(action),
                lambda _result: GpuGovernorPage._record_preparation_result(
                    self,
                    "Arch/CachyOS BC-250 Proton",
                    "Opened the removal terminal. Review its output, then restart Steam.",
                ),
                "Could not prepare the BC-250 Proton removal",
                controls=(),
                error_parent=dialog_parent,
            )
            return
        if action not in actions:
            raise ValueError("Unsupported CachyOS BC-250 action.")
        title, packages, recovery = actions[action]
        confirmation = ConfirmDialog(
            title,
            tr(
                "This is not a standard dependency. It adds MastaG's external pacman repository, whose packages are unsigned (Optional TrustAll). Continue only if you trust that upstream repository."
            ),
            summary=(
                (tr("Source"), "github.com/MastaG/linux-cachyos-bc250"),
                (tr("Packages"), packages),
                (
                    tr("Package trust"),
                    tr("Unsigned external repository (Optional TrustAll)"),
                ),
                (tr("Recovery"), recovery),
                (tr("Reboot"), tr("Restart Steam after installation") if action.startswith("proton-") else tr("Required after installation") if action != "mesa" else tr("Recommended after Mesa changes")),
            ),
            confirm_text=tr("Open Proton installation terminal") if action.startswith("proton-") else tr("Open kernel installation terminal"),
            tone="red",
            parent=dialog_parent or self,
        )
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_backend_action(
            lambda: self.controller.preparar_cachyos_bc250(action),
            lambda _result: GpuGovernorPage._record_preparation_result(
                self,
                "Arch/CachyOS BC-250 kernel/Mesa",
                "Opened the explicit external Arch/CachyOS workflow. Review its terminal output and reboot only after successful kernel package verification.",
            ),
            "Could not prepare the Arch/CachyOS BC-250 kernel/Mesa workflow",
            controls=(),
            error_parent=dialog_parent,
        )

    def _manage_fsr4_bc250(
        self, action: str, *, dialog_parent: QWidget | None
    ) -> None:
        """FSR4 INT8 through the BC250 build of OptiScaler Client."""
        if action == "launch":
            self._run_backend_action(
                lambda: self.controller.gestionar_fsr4_bc250("launch"),
                lambda _result: GpuGovernorPage._record_preparation_result(
                    self,
                    "FSR4 · OptiScaler Client",
                    "OptiScaler Client opened. Choose Scan Games, select games and press Install / update selected.",
                ),
                "Could not open OptiScaler Client",
                controls=(),
                error_parent=dialog_parent,
            )
            return
        if action == "releases":
            # Only GitHub's list of client builds is read; nothing is installed.
            self._run_backend_action(
                lambda: self.controller.gestionar_fsr4_bc250("releases"),
                lambda _result: GpuGovernorPage._record_preparation_result(
                    self, "FSR4 · OptiScaler Client", "Opened the FSR4 workflow in the terminal.",
                ),
                "Could not manage FSR4",
                controls=(),
                error_parent=dialog_parent,
            )
            return
        if action.startswith("select:"):
            # Only the pick is saved: Install or Update downloads it.
            tag = action.partition(":")[2]
            self._run_backend_action(
                lambda: self.controller.gestionar_fsr4_bc250(f"select:{tag}"),
                lambda result: GpuGovernorPage._record_preparation_result(
                    self,
                    "FSR4 · OptiScaler Client",
                    tr_format(
                        "OptiScaler Client {version} is selected. Install or Update brings it in.",
                        version=str(_dict(result).get("version") or tag),
                    ),
                ),
                "Could not manage FSR4",
                controls=(),
                error_parent=dialog_parent,
            )
            return
        from bc250cc.infrastructure.bc250_opticlient import OPTICLIENT_TAG

        fsr4 = _dict(_dict(self.current_state.get("tools")).get("fsr4"))
        release_tag = str(fsr4.get("tag") or OPTICLIENT_TAG)
        if action.startswith("upgrade:"):
            newer = _dict(fsr4.get("newer"))
            release_tag = action.partition(":")[2]
            version = str(newer.get("version") or release_tag)
            copy = (
                tr_format("Update OptiScaler Client to {version}", version=version),
                tr("Downloads the new build from GitHub, checks it and replaces the current one. Your games keep what the client installed in them.")
                + ("" if newer.get("reviewed") else " " + tr("This build has not been reviewed with Control Center yet.")),
                "Update",
                "blue",
            )
        else:
            copy = {
                "install": (
                    "Install OptiScaler Client",
                    "Downloads the client from GitHub, checks it and installs it in your user folder. You add games from the client afterwards.",
                    "Install",
                    "blue",
                ),
                "uninstall": (
                    "Remove OptiScaler Client",
                    "Removes the client. What it installed in your games stays, and so do its backups in ~/.config/OptiscalerClient-BC250.",
                    "Remove client",
                    "orange",
                ),
                "legacy_uninstall": (
                    "Remove the old FSR4 V3 runtime",
                    "Removes the old V3 runtime. Also remove its VK_DRIVER_FILES launch option from any game that still has it.",
                    "Remove V3 runtime",
                    "orange",
                ),
            }.get(action)
        if copy is None:
            raise ValueError("Unsupported FSR4 action.")
        title, body, confirm, tone = copy
        confirmation = ConfirmDialog(
            title,
            tr(body),
            summary=(
                (tr("Source"), "github.com/daniel-h-0/bc250-fsr4-fork"),
                (tr("Version"), release_tag.removeprefix("opticlient-v")),
            ),
            confirm_text=confirm,
            eyebrow="FSR4 INT8",
            tone=tone,
            parent=dialog_parent or self,
        )
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_backend_action(
            lambda: self.controller.gestionar_fsr4_bc250(action),
            lambda _result: GpuGovernorPage._record_preparation_result(
                self,
                "FSR4 · OptiScaler Client",
                "Opened the FSR4 workflow in the terminal.",
            ),
            "Could not manage FSR4",
            controls=(),
            error_parent=dialog_parent,
        )

    def _save_helixsr_settings(self, values: dict, *, dialog_parent: QWidget | None) -> None:
        """Keep helixsr.ini's settings and write them into every game with HelixSR."""

        def done(result) -> None:
            result = _dict(result)
            message = tr_format(
                "HelixSR settings saved. {count} games with HelixSR use them now.",
                count=int(result.get("games") or 0),
            )
            skipped = [str(name) for name in result.get("skipped") or ()]
            if skipped:
                message += " " + tr_format(
                    "Close {games} and save again to reach them.", games=", ".join(skipped)
                )
            GpuGovernorPage._record_preparation_result(self, "HelixSR", message)

        self._run_backend_action(
            lambda: self.controller.guardar_ajustes_helixsr(values),
            done,
            "Could not save the HelixSR settings",
            controls=(),
            error_parent=dialog_parent,
        )

    def _manage_helixsr(self, action: str, *, dialog_parent: QWidget | None) -> None:
        """HelixSR: release and network files in the terminal, games in place."""
        from bc250cc.infrastructure.helixsr import HELIXSR_TAG

        label = "HelixSR"
        if action == "scan":
            self._run_backend_action(
                lambda: self.controller.gestionar_helixsr("scan"),
                lambda result: GpuGovernorPage._record_preparation_result(
                    self,
                    label,
                    tr_format(
                        "Found {count} Steam games with an FSR 3.1 DLL.",
                        count=int(_dict(result).get("games") or 0),
                    ),
                ),
                "Could not search for FSR 3.1 games",
                controls=(),
                error_parent=dialog_parent,
            )
            return
        if action == "add_opti_folder":
            # OptiScaler installed by hand: the folder that holds OptiScaler.ini.
            folder = QFileDialog.getExistingDirectory(
                dialog_parent or self, tr("Choose the game's folder"), str(Path.home())
            )
            if not folder:
                return
            self._run_backend_action(
                lambda: self.controller.gestionar_helixsr(f"add_opti_folder:{folder}"),
                lambda result: GpuGovernorPage._record_preparation_result(
                    self,
                    label,
                    tr_format(
                        "{game} was added. Add HelixSR to it from the list.",
                        game=str(_dict(result).get("game") or Path(folder).name),
                    ),
                ),
                "Could not add the game folder",
                controls=(),
                error_parent=dialog_parent,
            )
            return
        if action == "add_folder":
            # A game outside Steam: the user points at its folder, which is
            # searched for an FSR 3.1 DLL like a Steam game's.
            folder = QFileDialog.getExistingDirectory(
                dialog_parent or self, tr("Choose the game's folder"), str(Path.home())
            )
            if not folder:
                return
            self._run_backend_action(
                lambda: self.controller.gestionar_helixsr(f"add_folder:{folder}"),
                lambda result: GpuGovernorPage._record_preparation_result(
                    self,
                    label,
                    tr_format(
                        "{game} was added. Add HelixSR to it from the list.",
                        game=str(_dict(result).get("game") or Path(folder).name),
                    ),
                ),
                "Could not add the game folder",
                controls=(),
                error_parent=dialog_parent,
            )
            return
        if action == "releases":
            # Only GitHub's list of releases is read; nothing is installed.
            self._run_backend_action(
                lambda: self.controller.gestionar_helixsr(action),
                lambda _result: GpuGovernorPage._record_preparation_result(
                    self, label, "Opened the HelixSR workflow in the terminal.",
                ),
                "Could not manage HelixSR",
                controls=(),
                error_parent=dialog_parent,
            )
            return
        if action == "update_all":
            self._update_all_helixsr_games(dialog_parent=dialog_parent)
            return
        game_action, _sep, appid = action.partition(":")
        if game_action == "select":
            # Only the pick is saved: Install or Update downloads it.
            self._run_backend_action(
                lambda: self.controller.gestionar_helixsr(action),
                lambda result: GpuGovernorPage._record_preparation_result(
                    self,
                    label,
                    tr_format(
                        "HelixSR {version} is selected. Install or Update brings it in.",
                        version=str(_dict(result).get("version") or appid),
                    ),
                ),
                "Could not manage HelixSR",
                controls=(),
                error_parent=dialog_parent,
            )
            return
        if game_action == "forget_folder":
            self._run_backend_action(
                lambda: self.controller.gestionar_helixsr(action),
                lambda result: GpuGovernorPage._record_preparation_result(
                    self,
                    label,
                    tr_format(
                        "{game} was taken off the list.",
                        game=str(_dict(result).get("game") or appid),
                    ),
                ),
                "Could not manage HelixSR",
                controls=(),
                error_parent=dialog_parent,
            )
            return
        if game_action == "game_update":
            # Only HelixSR's own files are replaced, so nothing to confirm;
            # the backend still refuses while the game is running.
            self._run_backend_action(
                lambda: self.controller.gestionar_helixsr(action),
                lambda result: GpuGovernorPage._record_preparation_result(
                    self,
                    label,
                    tr_format(
                        "{game} now uses HelixSR {version}.",
                        game=str(_dict(result).get("game") or appid),
                        version=str(_dict(result).get("version") or ""),
                    ),
                ),
                "Could not update HelixSR",
                controls=(),
                error_parent=dialog_parent,
            )
            return
        if game_action in {"opti_install", "opti_remove"}:
            self._manage_helixsr_optiscaler(action, dialog_parent=dialog_parent)
            return
        if game_action.startswith("scaler_"):
            self._manage_helixsr_scaler(action, dialog_parent=dialog_parent)
            return
        if game_action in {"game_install", "game_remove"}:
            helixsr = _dict(_dict(self.current_state.get("tools")).get("helixsr"))
            game = next(
                (
                    dict(item) for item in helixsr.get("games") or ()
                    if str(_dict(item).get("appid")) == appid
                ),
                {"appid": appid, "name": appid, "files": []},
            )
            installing = game_action == "game_install"
            confirmation = ConfirmDialog(
                "Add HelixSR to this game" if installing else "Remove HelixSR from this game",
                tr(
                    "HelixSR replaces the game's FSR 3.1 file; the original is kept. In the game, choose AMD FSR."
                    if installing else
                    "The game gets its own FSR file back."
                ) + " " + tr("Close the game first."),
                summary=((tr("Game"), str(game.get("name") or appid)),),
                confirm_text="Add HelixSR" if installing else "Remove",
                eyebrow="HelixSR",
                tone="blue" if installing else "orange",
                parent=dialog_parent or self,
            )
            if confirmation.exec() != QDialog.DialogCode.Accepted:
                return
            self._run_backend_action(
                lambda: self.controller.gestionar_helixsr(action),
                lambda result: GpuGovernorPage._record_preparation_result(
                    self,
                    label,
                    tr_format(
                        "HelixSR was added to {game}. In the game, choose AMD FSR as the upscaler."
                        if installing else
                        "HelixSR was removed from {game}; its own FSR file is back.",
                        game=str(_dict(result).get("game") or game.get("name") or appid),
                    ),
                ),
                "Could not change the game's files",
                controls=(),
                error_parent=dialog_parent,
            )
            return
        helixsr = _dict(_dict(self.current_state.get("tools")).get("helixsr"))
        release = str(helixsr.get("tag") or HELIXSR_TAG)
        if action.startswith("upgrade:"):
            newer = _dict(helixsr.get("newer"))
            release = action.partition(":")[2]
            version = str(newer.get("version") or release.removeprefix("v"))
            copy = (
                tr_format("Update HelixSR to {version}", version=version),
                tr("Downloads the new release from GitHub and builds its network on this PC; the terminal asks before it downloads NVIDIA's DLSS file. Your games keep their current version until you update them.")
                + ("" if newer.get("reviewed") else " " + tr("This release has not been reviewed with Control Center yet.")),
                "Update",
                "blue",
            )
        else:
            copy = {
                "install": (
                    "Install HelixSR",
                    "Downloads HelixSR from GitHub and builds its network on this PC. The terminal asks before it downloads NVIDIA's DLSS file. It takes about five minutes.",
                    "Install",
                    "blue",
                ),
                "network": (
                    "Build network files",
                    "Builds HelixSR's network on this PC. The terminal asks before it downloads NVIDIA's DLSS file. It takes about five minutes.",
                    "Build network files",
                    "blue",
                ),
                "fg": (
                    "Build frame generation",
                    "Builds DLSS frame generation for games with HelixSR Scaler. The terminal asks before each download from NVIDIA (about 400 MB). No game is changed.",
                    "Build frame generation",
                    "blue",
                ),
                "uninstall": (
                    "Remove HelixSR",
                    "Removes HelixSR and everything it built on this PC. Remove it from your games first.",
                    "Remove HelixSR",
                    "orange",
                ),
            }.get(action)
        if copy is None:
            raise ValueError("Unsupported HelixSR action.")
        title, body, confirm, tone = copy
        if helixsr.get("prerelease") and not action.startswith("upgrade:"):
            release = tr_format("{version} (pre-release)", version=release)
        confirmation = ConfirmDialog(
            title,
            tr(body),
            summary=(
                (tr("Source"), "github.com/lonewolf0622/HelixSR"),
                (tr("Version"), release.removeprefix("v")),
            ),
            confirm_text=confirm,
            eyebrow="HelixSR",
            tone=tone,
            parent=dialog_parent or self,
        )
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_backend_action(
            lambda: self.controller.gestionar_helixsr(action),
            lambda _result: GpuGovernorPage._record_preparation_result(
                self, label, "Opened the HelixSR workflow in the terminal.",
            ),
            "Could not manage HelixSR",
            controls=(),
            error_parent=dialog_parent,
        )

    def _manage_helixsr_scaler(self, action: str, *, dialog_parent: QWidget | None) -> None:
        """HelixSR Scaler in a Steam game, through the HelixSR release's own bridge."""
        game_action, _sep, appid = action.partition(":")
        helixsr = _dict(_dict(self.current_state.get("tools")).get("helixsr"))
        game = next(
            (dict(item) for item in helixsr.get("scaler_games") or ()
             if str(_dict(item).get("appid")) == appid),
            {"appid": appid, "name": appid},
        )
        name = str(game.get("name") or appid)
        version = str(helixsr.get("version") or "")
        copy = {
            "scaler_install": (
                "Add HelixSR Scaler to this game",
                "HelixSR Scaler goes next to the game and keeps any file it replaces. In the game, choose DLSS. Don't use it in online games with anti-cheat.",
                "Add HelixSR Scaler", "blue",
            ),
            "scaler_remove": (
                "Remove HelixSR Scaler from this game",
                "Every file HelixSR Scaler replaced is put back.",
                "Remove", "orange",
            ),
            "scaler_update": (
                tr_format("Update HelixSR Scaler to {version}", version=version),
                tr_format("The game keeps version {version} so you can go back to it.", version=str(game.get("version") or "?")),
                "Update", "blue",
            ),
            "scaler_rollback": (
                tr_format("Go back to HelixSR {version}", version=str(game.get("previous") or "?")),
                "The game gets back the version it had before its last update. You can undo this the same way.",
                "Go back", "orange",
            ),
        }.get(game_action)
        if copy is not None:
            title, body, confirm, tone = copy
            confirmation = ConfirmDialog(
                title,
                tr(body) + " " + tr("Close the game first."),
                summary=((tr("Game"), name),),
                confirm_text=confirm,
                eyebrow="HelixSR",
                tone=tone,
                parent=dialog_parent or self,
            )
            if confirmation.exec() != QDialog.DialogCode.Accepted:
                return

        def done(result: object) -> None:
            result = _dict(result)
            game_name = str(result.get("game") or name)
            if game_action == "scaler_install":
                message = tr_format(
                    "HelixSR Scaler was added to {game}. In the game, choose DLSS as the upscaler.", game=game_name
                )
                if result.get("launch_option_error"):
                    message = f"{message} " + tr_format(
                        "Steam also needs this launch option for it: {option}", option=str(result.get("launch_options"))
                    )
            elif game_action == "scaler_remove":
                message = tr_format("HelixSR Scaler was removed from {game}; its own files are back.", game=game_name)
            elif game_action in {"scaler_update", "scaler_rollback"}:
                message = tr_format("{game} now has HelixSR {version}.", game=game_name,
                                    version=str(result.get("version") or "?"))
            elif game_action == "scaler_fg_on":
                message = tr_format(
                    "Frame generation is on in {game}. Turn on DLSS Frame Generation in the game.", game=game_name
                )
            else:
                message = tr_format("Frame generation is off in {game}.", game=game_name)
            GpuGovernorPage._record_preparation_result(self, "HelixSR", message)

        self._run_backend_action(
            lambda: self.controller.gestionar_helixsr(action),
            done,
            "Could not change the game's files",
            controls=(),
            error_parent=dialog_parent,
        )

    def _update_all_helixsr_games(self, *, dialog_parent: QWidget | None) -> None:
        """Every game with another HelixSR release, given the installed one."""
        helixsr = _dict(_dict(self.current_state.get("tools")).get("helixsr"))
        version = str(helixsr.get("version") or "")
        count = int(helixsr.get("outdated_games") or 0)
        confirmation = ConfirmDialog(
            tr_format("Update {count} games to HelixSR {version}", count=count, version=version),
            tr("Games that are open are skipped; close them and update them later. Games with HelixSR Scaler keep their current version to go back to."),
            confirm_text="Update",
            eyebrow="HelixSR",
            tone="blue",
            parent=dialog_parent or self,
        )
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return

        def done(result: object) -> None:
            result = _dict(result)
            message = tr_format("{count} games now have HelixSR {version}.",
                                count=len(result.get("updated") or ()), version=str(result.get("version") or version))
            skipped = [str(name) for name in result.get("skipped") or ()]
            if skipped:
                message += " " + tr_format("Not updated: {games}. Close them and try again.", games=", ".join(skipped))
            GpuGovernorPage._record_preparation_result(self, "HelixSR", message)

        self._run_backend_action(
            lambda: self.controller.gestionar_helixsr("update_all"),
            done,
            "Could not change the game's files",
            controls=(),
            error_parent=dialog_parent,
        )

    def _manage_helixsr_optiscaler(self, action: str, *, dialog_parent: QWidget | None) -> None:
        """Point a game's OptiScaler at HelixSR, or put its settings back."""
        game_action, _sep, appid = action.partition(":")
        installing = game_action == "opti_install"
        helixsr = _dict(_dict(self.current_state.get("tools")).get("helixsr"))
        game = next(
            (
                dict(item) for item in helixsr.get("games") or ()
                if _dict(item).get("kind") == "optiscaler" and str(_dict(item).get("appid")) == appid
            ),
            {"appid": appid, "name": appid},
        )
        name = str(game.get("name") or appid)
        confirmation = ConfirmDialog(
            "Use HelixSR in OptiScaler" if installing else "Remove HelixSR from OptiScaler",
            tr(
                "This game's OptiScaler is pointed at HelixSR; its settings are saved first. In the game, press Insert and pick FSR HelixSR."
                if installing else
                "OptiScaler's settings are put back as they were."
            ) + " " + tr("Close the game first."),
            summary=((tr("Game"), name),),
            confirm_text="Use HelixSR in OptiScaler" if installing else "Remove",
            eyebrow="HelixSR",
            tone="blue" if installing else "orange",
            parent=dialog_parent or self,
        )
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_backend_action(
            lambda: self.controller.gestionar_helixsr(action),
            lambda result: GpuGovernorPage._record_preparation_result(
                self,
                "HelixSR",
                tr_format(
                    "OptiScaler in {game} now uses HelixSR. In the game, press Insert and choose FSR HelixSR."
                    if installing else
                    "OptiScaler in {game} is back to its previous settings.",
                    game=str(_dict(result).get("game") or name),
                ),
            ),
            "Could not change the game's files",
            controls=(),
            error_parent=dialog_parent,
        )

    def _manage_opticlient_files(self, action: str, *, dialog_parent: QWidget | None) -> None:
        """Undo OptiScaler Client's install in a game into a backup, or put it back."""
        verb, _sep, target = action.partition(":")
        fsr4 = _dict(_dict(self.current_state.get("tools")).get("fsr4"))
        if verb == "undo":
            record = next(
                (dict(item) for item in fsr4.get("installations") or ()
                 if str(_dict(item).get("key")) == target),
                {"name": "", "files": 0},
            )
            clear = record.get("state") == "removed"
            title, body, confirm = (
                ("Clear OptiScaler Client's record",
                 "OptiScaler's files are already gone. The client's record moves into a backup, so the client can install the game again. Close OptiScaler Client first.",
                 "Clear record")
                if clear else
                ("Remove OptiScaler from this game",
                 "OptiScaler Client's files move into a backup and any game file they replaced comes back. Close the game and OptiScaler Client first.",
                 "Remove, keep a backup")
            )
            summary = [(tr("Game"), str(record.get("name") or tr("Unknown")))]
            if not clear:
                summary.append((tr("Files"), str(record.get("files") or 0)))
        else:
            record = next(
                (dict(item) for item in fsr4.get("backups") or ()
                 if str(_dict(item).get("id")) == target),
                {"name": "", "files": 0, "path": ""},
            )
            title, body, confirm = (
                "Put OptiScaler back",
                "The files and the client's record go back exactly as they were. Close the game and OptiScaler Client first.",
                "Put back",
            )
            summary = [
                (tr("Game"), str(record.get("name") or tr("Unknown"))),
                (tr("Files"), str(record.get("files") or 0)),
                (tr("Backup folder"), str(record.get("path") or "")),
            ]
        confirmation = ConfirmDialog(
            title, tr(body), summary=tuple(summary), confirm_text=confirm, eyebrow="FSR4 INT8",
            tone="blue" if verb != "undo" else "orange", parent=dialog_parent or self,
        )
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return

        def done(result: object) -> None:
            result = _dict(result)
            game = str(result.get("game") or record.get("name") or "")
            if verb != "undo":
                message = tr_format("OptiScaler is back in {game}.", game=game)
            elif result.get("record_only"):
                message = tr_format(
                    "OptiScaler Client's record of {game} was cleared. It is kept in {path}.",
                    game=game, path=str(result.get("backup") or ""),
                )
            else:
                message = tr_format(
                    "OptiScaler was removed from {game}. Its {count} files are kept in {path}.",
                    game=game, count=int(result.get("files") or 0), path=str(result.get("backup") or ""),
                )
            GpuGovernorPage._record_preparation_result(self, "FSR4 · OptiScaler Client", message)

        self._run_backend_action(
            lambda: self.controller.gestionar_fsr4_bc250(action),
            done,
            "Could not change the game's files",
            controls=(),
            error_parent=dialog_parent,
        )

    def _add_fsr4_steam_option_to_library(self, *, dialog_parent: QWidget | None) -> None:
        """The same option for every installed Steam game, asked for on Reddit."""
        from bc250cc.infrastructure.steam_launch_options import installed_steam_games

        games = installed_steam_games()
        confirmation = ConfirmDialog(
            "Add the launch option to every Steam game",
            tr(
                "Every installed Steam game gets the option OptiScaler needs. What each game already had stays, "
                "and games without OptiScaler run as before. Close Steam first."
            ),
            summary=(
                (tr("Games"), str(len(games))),
                (tr("Option"), 'WINEDLLOVERRIDES="dxgi=n,b"'),
            ),
            confirm_text="Add to every game",
            tone="blue",
            parent=dialog_parent or self,
        )
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_backend_action(
            lambda: self.controller.gestionar_fsr4_bc250("steam_option_all"),
            lambda result: GpuGovernorPage._record_preparation_result(
                self,
                "FSR4 · OptiScaler Client",
                tr_format(
                    "Added to {changed} Steam games; {already} already had it.",
                    changed=int(_dict(result).get("changed") or 0),
                    already=int(_dict(result).get("already") or 0),
                ),
            ),
            "Could not change the Steam launch option",
            controls=(),
            error_parent=dialog_parent,
        )

    def _add_fsr4_steam_option(self, appid: str, *, dialog_parent: QWidget | None) -> None:
        """Write the launch option that makes Proton load OptiScaler, after a confirm."""
        from bc250cc.infrastructure.steam_launch_options import merge_dll_override

        fsr4 = _dict(_dict(self.current_state.get("tools")).get("fsr4"))
        games = list(fsr4.get("games") or ())
        if not games:
            # This page may not hold the dashboard's latest tools read yet;
            # the list is only a few small files away.
            from bc250cc.infrastructure.bc250_opticlient import opticlient_games

            games = opticlient_games()
        game = next(
            (dict(item) for item in games if str(item.get("appid")) == str(appid)),
            None,
        )
        if game is None:
            return
        dll = str(game.get("adapter") or "dxgi.dll").removesuffix(".dll")
        before = str(game.get("launch_options") or "")
        after = merge_dll_override(before, dll)
        confirmation = ConfirmDialog(
            "Add the launch option to Steam",
            tr("This game gets the option OptiScaler needs. What it already had stays. Close Steam first."),
            summary=(
                (tr("Game"), str(game.get("name") or appid)),
                (tr("Now"), before or tr("(empty)")),
                (tr("After"), after),
            ),
            confirm_text="Add to Steam",
            tone="blue",
            parent=dialog_parent or self,
        )
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_backend_action(
            lambda: self.controller.gestionar_fsr4_bc250(f"steam_option:{appid}"),
            lambda _result: GpuGovernorPage._record_preparation_result(
                self,
                "FSR4 · OptiScaler Client",
                tr_format(
                    "Added to Steam for {game}. Start it from Steam, choose DLSS, FSR or XeSS in its settings and press Insert.",
                    game=str(game.get("name") or appid),
                ),
            ),
            "Could not change the Steam launch option",
            controls=(),
            error_parent=dialog_parent,
        )

    def _manage_gfx1013_source(
        self, action: str, *, dialog_parent: QWidget | None
    ) -> None:
        """The independent GFX1013 source build: confirm, then run it in the terminal."""
        copy = {
            "install": (
                "Build and install the GFX1013 fix",
                "This builds DryhoppedIPA's V33 amdgpu patches for the running kernel and RADV with the compute-queue patch, then installs them beside the stock driver and Mesa, which stay untouched. amdgpu is then loaded by a small boot service: if a boot with the fix does not reach the desktop, the next boot uses the stock driver and switches the fix off by itself. To skip it for one boot, press e in the boot menu and add bc250.gfx1013=0. Building needs your password, an internet connection and 15-30 minutes.",
                "Build and install",
                "orange",
            ),
            "rebuild": (
                "Rebuild for this kernel",
                "The kernel was updated, so the patched module has to be built again for it. The private RADV stays as it is. This takes a few minutes and a restart.",
                "Rebuild",
                "blue",
            ),
            "enable": (
                "Switch the GFX1013 fix on",
                "The patched driver is used again from the next boot, with the same automatic fallback if that boot fails.",
                "Switch on",
                "blue",
            ),
            "disable": (
                "Switch the GFX1013 fix off",
                "The stock amdgpu and system Mesa are used from the next boot. The fix stays installed and can be switched on again.",
                "Switch off",
                "blue",
            ),
            "uninstall": (
                "Remove the GFX1013 fix",
                "Removes the patched module, the private RADV and the boot service, and rebuilds the initramfs. The stock driver is used from the next boot.",
                "Remove",
                "orange",
            ),
        }.get(action)
        if copy is None:
            raise ValueError("Unsupported GFX1013 source-build action.")
        title, body, confirm, tone = copy
        confirmation = ConfirmDialog(
            title,
            tr(body),
            summary=(
                (tr("Source"), "github.com/DryhoppedIPA/bc250-gfx1013-fix"),
                (tr("Stock driver"), tr("Kept; used whenever the fix is off or fails")),
                (tr("Restart"), tr("Required")),
            ),
            confirm_text=confirm,
            tone=tone,
            parent=dialog_parent or self,
        )
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_backend_action(
            lambda: self.controller.gestionar_gfx1013_source(action),
            lambda _result: GpuGovernorPage._record_preparation_result(
                self,
                "GFX1013 fix",
                "Opened the GFX1013 source-build workflow in the terminal.",
            ),
            "Could not run the GFX1013 source build",
            controls=(),
            error_parent=dialog_parent,
        )

    def _manage_debian_kernel(self, *, dialog_parent: QWidget | None) -> None:
        """Kernel and Mesa from Debian backports: confirm, then run it in the terminal."""
        upgrade = _dict(
            _dict(_dict(self.current_state.get("tools")).get("gfx1013_compute")).get("kernel_upgrade")
        )
        with_kernel = bool(upgrade.get("install_kernel", True))
        summary = [(tr("Source"), "deb.debian.org · backports")]
        if with_kernel:
            summary.append((tr("Current kernel"), tr("Kept; choose it in the boot menu to go back")))
        summary.append((tr("Restart"), tr("Required")))
        confirmation = ConfirmDialog(
            "Install from backports",
            (
                tr(
                    "Debian 13 ships a kernel and a Mesa that do not know the BC-250 GPU, so the desktop is drawn by the CPU. This adds the Debian backports suite in its own source file and installs from it a newer Mesa, a newer kernel with its headers and the GPU firmware. The current kernel stays installed and in the boot menu under Advanced options. Restart afterwards, then build the GFX1013 fix from this same card. Needs your password and an internet connection."
                )
                if with_kernel
                else tr(
                    "Debian 13 ships a Mesa that does not know the BC-250 GPU, so the desktop is drawn by the CPU. This adds the Debian backports suite in its own source file and installs the newer Mesa from it. Restart afterwards. Needs your password and an internet connection."
                )
            ),
            summary=tuple(summary),
            confirm_text="Install from backports",
            tone="orange",
            parent=dialog_parent or self,
        )
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_backend_action(
            lambda: self.controller.gestionar_kernel_debian("install"),
            lambda _result: GpuGovernorPage._record_preparation_result(
                self,
                "Debian backports",
                "Opened the backports workflow in the terminal.",
            ),
            "Could not install from backports",
            controls=(),
            error_parent=dialog_parent,
        )

    def _manage_mesa_ppa(self, *, dialog_parent: QWidget | None) -> None:
        """A newer Mesa from the kisak-mesa PPA: confirm what is added, then run it in the terminal."""
        confirmation = ConfirmDialog(
            "Update Mesa",
            tr(
                "This adds the kisak-mesa PPA (ppa:kisak/kisak-mesa), a third-party source, in its own source file after checking that its signing key is the expected one, and updates Mesa and, if present, its 32-bit libraries from it. Other packages are not touched. To go back, delete the source file and key and downgrade Mesa; the terminal prints the commands. Restart afterwards. Needs your password and an internet connection."
            ),
            summary=(
                (tr("Source"), "ppa.launchpadcontent.net · kisak/kisak-mesa"),
                (tr("Restart"), tr("Required")),
            ),
            confirm_text="Update Mesa",
            tone="orange",
            parent=dialog_parent or self,
        )
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_backend_action(
            lambda: self.controller.gestionar_mesa_desktop("install"),
            lambda _result: GpuGovernorPage._record_preparation_result(
                self,
                "Mesa",
                "Opened the Mesa update in the terminal.",
            ),
            "Could not update Mesa",
            controls=(),
            error_parent=dialog_parent,
        )

    def _manage_vaapi(self, action: str, *, dialog_parent: QWidget | None) -> None:
        """The BC-250 VA-API driver: confirm what changes, then run it in the terminal."""
        copy = {
            "install": (
                "Install hardware video",
                "Downloads simpmix's VA-API driver at a reviewed version, checks it, and builds it in a container: about 5 minutes and a few hundred MB the first time. It is switched on only after it starts and offers H.264 and HEVC. Programs that use VA-API (Sunshine, OBS, Steam Remote Play, ffmpeg, browsers) then encode and decode with it. For streaming while you play, choose H.264: HEVC encodes mostly on the CPU. Log out and back in afterwards.",
                "Build and install",
                "orange",
            ),
            "install32": (
                "Add the 32-bit video driver",
                "Steam Remote Play and Steam Link are 32-bit programs and use software video without a 32-bit driver. This installs the signed 32-bit libraries (on SteamOS it turns the read-only protection off for the install and back on), builds the 32-bit driver in a container from the same reviewed source, checks it starts on this GPU, and only then adds it beside the 64-bit one. A SteamOS update removes the 32-bit libraries; this button then reads Repair 32-bit driver and brings them back without rebuilding. Log out and back in afterwards.",
                "Add",
                "orange",
            ),
            "flatpak": (
                "Allow Flatpak apps to use hardware video",
                "Flatpak apps (GPU Screen Recorder, OBS, Steam) run in a sandbox that cannot see the driver, so they list H.264 as not available. This gives them read-only access to the driver folder and the two libva variables, for your user only. Restart those apps afterwards.",
                "Allow",
                "orange",
            ),
            "uninstall": (
                "Remove hardware video",
                "Removes the driver and the two files that switch it on. Programs go back to software video from the next login.",
                "Remove",
                "orange",
            ),
        }.get(action)
        if action == "test":
            copy = None
        elif copy is None:
            raise ValueError("Unsupported VA-API action.")
        if copy is not None:
            title, body, confirm, tone = copy
            confirmation = ConfirmDialog(
                title,
                tr(body),
                summary=(
                    (tr("Source"), "github.com/simpmix/bc250-encoding-decoding-fix"),
                    (tr("License"), "GPL-3.0"),
                    (tr("Apply"), tr("Restart the app") if action == "flatpak" else tr("Log out and back in")),
                ),
                confirm_text=confirm,
                tone=tone,
                parent=dialog_parent or self,
            )
            if confirmation.exec() != QDialog.DialogCode.Accepted:
                return
        self._run_backend_action(
            lambda: self.controller.gestionar_vaapi(action),
            lambda _result: GpuGovernorPage._record_preparation_result(
                self,
                "Hardware video",
                "Opened the hardware video workflow in the terminal.",
            ),
            "Could not run the hardware video workflow",
            controls=(),
            error_parent=dialog_parent,
        )

    def _manage_radv_async(
        self, action: str, *, dialog_parent: QWidget | None
    ) -> None:
        """The RADV-only async compute: confirm what changes, then run it in the terminal."""
        copy = {
            "install": (
                "Build and install async compute",
                "This builds RADV with the GFX1013 compute-queue patch from tri3gubki-ops' Bazzite release and installs it as a second Vulkan driver beside the system Mesa, which stays untouched. Kernel 7.2 or newer needs no patched amdgpu for it: its amdgpu is the one that release runs on. New sessions use it: log out and back in, and games need no launch options. If the desktop does not come back, press e in the boot menu and add bc250.async=0. Building needs your password, an internet connection and 10-20 minutes.",
                "Build and install",
                "orange",
            ),
            "enable": (
                "Switch async compute on",
                "Sessions started from now on use the patched RADV. Log out and back in to apply.",
                "Switch on",
                "blue",
            ),
            "disable": (
                "Switch async compute off",
                "Sessions started from now on use the system driver. The patched RADV stays installed, and one game can still use it with the launch option bc250cc-async-compute run %command%.",
                "Switch off",
                "blue",
            ),
            "uninstall": (
                "Remove async compute",
                "Removes the patched RADV, its test tools and the session switch. The system driver is used from the next login.",
                "Remove",
                "orange",
            ),
        }.get(action)
        if action in {"status", "test"}:
            copy = None
        elif copy is None:
            raise ValueError("Unsupported async-compute action.")
        if copy is not None:
            title, body, confirm, tone = copy
            confirmation = ConfirmDialog(
                title,
                tr(body),
                summary=(
                    (tr("Source"), "github.com/tri3gubki-ops/bc250-async-compute-bazzite"),
                    (tr("System Mesa"), tr("Kept untouched; used whenever this is off")),
                    (tr("Apply"), tr("Log out and back in")),
                ),
                confirm_text=confirm,
                tone=tone,
                parent=dialog_parent or self,
            )
            if confirmation.exec() != QDialog.DialogCode.Accepted:
                return
        self._run_backend_action(
            lambda: self.controller.gestionar_radv_async(action),
            lambda _result: GpuGovernorPage._record_preparation_result(
                self,
                "Async compute",
                "Opened the async-compute workflow in the terminal.",
            ),
            "Could not run the async-compute workflow",
            controls=(),
            error_parent=dialog_parent,
        )

    def _open_fsr4_upstream(self, *, dialog_parent: QWidget | None) -> None:
        """Open the fork's step-by-step guide without running anything."""
        opened, message = open_external_url(
            "https://github.com/daniel-h-0/bc250-fsr4-fork/blob/v4/docs/optiscaler-client.md"
        )
        if opened:
            return
        InfoDialog(
            tr("Could not open upstream project"),
            tr("The upstream project link could not be opened by this desktop session.")
            + "\n\n"
            + tr(message),
            tone="orange",
            parent=dialog_parent or self,
        ).exec()

    def _open_compatibility_upstream(
        self, action: str, *, dialog_parent: QWidget | None
    ) -> None:
        gfx_state = _dict(
            _dict(self.current_state.get("tools")).get("gfx1013_compute")
        )
        gfx_url = str(
            gfx_state.get("upstream_url")
            or "https://github.com/DryhoppedIPA/bc250-gfx1013-fix"
        )
        urls = {
            "acpi_upstream": "https://github.com/e-tho/bc250-acpi-fix",
            "gfx1013_upstream": gfx_url,
            "bazzite_async_upstream": BAZZITE_ASYNC_COMPUTE_REPOSITORY,
            "bazzite_image_upstream": "https://github.com/62fixolab/Latest-Bazzite-AMD-BC-250-Patched-Images",
            "helixsr_upstream": "https://github.com/lonewolf0622/HelixSR",
            "vaapi_upstream": "https://github.com/simpmix/bc250-encoding-decoding-fix",
        }
        opened, message = open_external_url(urls[action])
        if opened:
            return
        InfoDialog(
            tr("Could not open upstream project"),
            tr("The upstream project link could not be opened by this desktop session.")
            + "\n\n"
            + tr(message),
            tone="orange",
            parent=dialog_parent or self,
        ).exec()

    def _open_steamos_graphics_upstream(
        self, *, dialog_parent: QWidget | None
    ) -> None:
        """Open the external SteamOS graphics documentation without executing it."""
        opened, message = open_external_url(
            "https://github.com/keyboardspecialist/bc250-steamos"
        )
        if opened:
            return
        InfoDialog(
            tr("Could not open SteamOS graphics guide"),
            tr("The upstream project link could not be opened by this desktop session.")
            + "\n\n"
            + tr(message),
            tone="orange",
            parent=dialog_parent or self,
        ).exec()

    def _manage_gfx1013_fedora(
        self,
        action: str,
        *,
        dialog_parent: QWidget | None,
    ) -> None:
        tools = _dict(self.current_state.get("tools"))
        state = _dict(tools.get("gfx1013_compute"))
        presentation = present_gfx1013(state)
        if action == "uninstall" and presentation.radv_route is not None:
            # Removed beside the patched RADV, which makes it redundant.
            detail = tr(RADV_ROUTE_SECOND_FIX)
        else:
            detail = " ".join(
                tr_format(part, **presentation.detail_values) for part in presentation.detail
            )
        version_id = str(state.get("version_id") or "").strip()
        system_label = f"Fedora {version_id}" if version_id else "Fedora"
        summary = [
            (tr("System"), system_label),
            (tr("Running kernel"), str(state.get("kernel") or tr("Unknown"))),
            (tr("Source"), "DryhoppedIPA/bc250-gfx1013-fix"),
        ]
        if action == "activate":
            summary.append((tr("Recovery"), tr("Stock entry stays in the boot menu")))
        else:
            summary.append((tr("Recovery"), tr("Stock boot remains the default")))
            summary.append((tr("Reboot"), tr("Required after installation")))
        confirmation = ConfirmDialog(
            tr("GFX1013 async compute"),
            detail,
            summary=tuple(summary),
            confirm_text=tr({
                "uninstall": "Uninstall",
                "boot-patched": "Boot with the fix",
                "activate": "Make the fix the default",
            }.get(action, "Install / update")),
            tone="red" if action == "uninstall" else "orange",
            parent=dialog_parent or self,
        )
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_backend_action(
            lambda: self.controller.gestionar_gfx1013_fedora(action),
            lambda _result: GpuGovernorPage._record_preparation_result(
                self,
                tr("GFX1013 async compute"),
                detail,
            ),
            tr("Failed"),
            controls=(),
            error_parent=dialog_parent,
        )

    def _manage_gfx1013_bazzite(
        self,
        action: str,
        *,
        dialog_parent: QWidget | None,
    ) -> None:
        tools = _dict(self.current_state.get("tools"))
        state = _dict(tools.get("gfx1013_compute"))
        presentation = present_gfx1013(state)
        detail = " ".join(tr(part) for part in presentation.detail)
        if action == "status":
            self._run_backend_action(
                lambda: self.controller.gestionar_gfx1013_bazzite("status"),
                lambda _result: GpuGovernorPage._record_preparation_result(
                    self, tr("GFX1013 async compute"), detail
                ),
                tr("Failed"),
                controls=(),
                error_parent=dialog_parent,
            )
            return
        install = action == "install"
        confirmation = ConfirmDialog(
            tr("GFX1013 async compute"),
            detail,
            summary=(
                (tr("System"), "Bazzite 44"),
                (tr("Running kernel"), str(state.get("kernel") or tr("Unknown"))),
                (tr("Source"), "tri3gubki-ops/bc250-async-compute-bazzite v0.2.4"),
                (tr("System Mesa"), tr("Not modified")),
                (tr("Activation"), tr("Log out and back in")),
                (tr("Recovery"), "Ctrl+Alt+F3 · remove 95-bc250-async-compute.conf"),
            ),
            confirm_text=tr("Install / update" if install else "Uninstall"),
            tone="orange" if install else "red",
            parent=dialog_parent or self,
        )
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_backend_action(
            lambda: self.controller.gestionar_gfx1013_bazzite(action),
            lambda _result: GpuGovernorPage._record_preparation_result(
                self,
                tr("GFX1013 async compute"),
                tr(
                    "The Bazzite async-compute workflow finished. Log out and back in so the selected RADV driver takes effect."
                ),
            ),
            tr("Failed"),
            controls=(),
            error_parent=dialog_parent,
        )

    def _record_preparation_result(self, label: str, message: str) -> None:
        self._last_operation_summary = tr(message)
        self.last_operation_line.set_values(tr(label), self._last_operation_summary)
        self._append_console(self._last_operation_summary)

    def _prepare_steamos_compatibility(
        self,
        plan: GpuDependencyPlan,
        dialog_parent: QWidget | None,
    ) -> None:
        high_points = _dict(self.current_state.get("high_frequency_points"))
        high_point_frequencies = tuple(
            int(value)
            for value in high_points.get("enabled_frequencies")
            or high_points.get("frequencies")
            or ()
            if str(value).isdigit() and int(value) > 2230
        )
        needs_module_safe_points = bool(high_points.get("enabled")) and bool(
            high_point_frequencies
        )

        def start_preparation() -> None:
            self._run_backend_action(
                self.controller.preparar_compatibilidad_steamos,
                lambda _result: GpuGovernorPage._record_preparation_result(
                    self,
                    "SteamOS compatibility",
                    "Opened the explicit SteamOS kernel compatibility workflow. Review the terminal result and reboot only when it reports a successful installation.",
                ),
                "Could not prepare SteamOS compatibility",
                controls=(),
                error_parent=dialog_parent,
            )

        if plan.requires_kernel_confirmation:
            confirmation = ConfirmDialog(
                "Prepare SteamOS kernel compatibility",
                tr(
                    "This explicit SteamOS repair builds and installs a kernel-matched amdgpu override for DisplayPort/audio, GPU telemetry and GFX1013 compute-queue support. It regenerates initramfs and requires a reboot. If exact headers are unavailable, the upstream fallback can require about 40 GiB of temporary space. The legacy mesh/task RADV path is not installed."
                ),
                summary=(
                    ("Distribution", plan.os_label),
                    ("Running kernel", plan.kernel),
                    ("Kernel change", "amdgpu override + initramfs"),
                    ("RADV mesh/task", "Not installed"),
                    ("Reboot", "Required after installation"),
                    *((
                        ("Safe-points", "Disable +2000 MHz TOML points"),
                    ) if needs_module_safe_points else ()),
                ),
                confirm_text="Prepare SteamOS compatibility",
                tone="orange",
                parent=dialog_parent or self,
            )
            if confirmation.exec() != QDialog.DialogCode.Accepted:
                return
        if not needs_module_safe_points:
            start_preparation()
            return

        confirmation = ConfirmDialog(
            "Disable advanced +2000 MHz points",
            "This comments the TOML safe-point blocks above 2000 MHz and validates the complete "
            "file. Active 3D workloads must be stopped first. This does not reload Cyan or "
            "change the live GPU range.",
            summary=(
                ("Safe-points", ", ".join(map(str, high_point_frequencies))),
                ("Requested state", "Commented"),
                ("Service", "No restart or clock change"),
            ),
            confirm_text="Disable +2000 MHz TOML points",
            tone="orange",
            parent=dialog_parent or self,
        )
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return

        def disabled_points(_result: object) -> None:
            self._apply_high_points_toggle_feedback(False)
            start_preparation()

        self._run_backend_action(
            lambda: self.controller.alternar_puntos_gpu_altos(False),
            disabled_points,
            "Could not update advanced safe-points",
            controls=(),
            error_parent=dialog_parent,
        )

    def _manage_steamos_graphics(
        self,
        action: str,
        *,
        dialog_parent: QWidget | None,
    ) -> None:
        if action == "status":
            self._run_backend_action(
                lambda: self.controller.gestionar_graficos_steamos("status"),
                lambda _result: GpuGovernorPage._record_preparation_result(
                    self,
                    "SteamOS graphics stack",
                    "Opened the verified SteamOS kernel, RADV and FSR4 status. No component was changed.",
                ),
                "Could not check the SteamOS graphics stack",
                controls=(),
                error_parent=dialog_parent,
            )
            return

        installing = action in {"install", "install-fsr4"}
        fsr4_only = action in {"install-fsr4", "uninstall-fsr4"}
        if action == "install":
            title = "Install matched SteamOS Mesa / RADV"
            body = (
                "This builds the reviewed Mesa 26.2.2 async-compute runtime for the active verified AMDGPU module. "
                "It installs a separate 64-bit RADV driver, keeps stock 32-bit RADV as fallback and enables it only when module attestation and amdgpu.sched_policy=2 agree. A reboot is required when the scheduler policy changes."
            )
            confirm_text = "Install Mesa / RADV"
        elif action == "install-fsr4":
            title = "Install SteamOS FSR4 V3 profile"
            body = (
                "This reuses the verified Mesa build and creates a private per-game FSR4 V3 driver. "
                "It is never enabled globally; each game must opt in with the launch command shown after installation."
            )
            confirm_text = "Install per-game FSR4"
        elif action == "uninstall-fsr4":
            title = "Remove SteamOS FSR4 profile"
            body = (
                "This removes only the private per-game FSR4 profile. Remove its launch option from each game before using system RADV again."
            )
            confirm_text = "Remove FSR4"
        else:
            title = "Remove SteamOS Mesa / RADV runtime"
            body = (
                "This removes the alternate RADV driver, ICD and activation generator, then removes the scheduler policy when it belongs to this toolkit. Build caches are preserved for recovery."
            )
            confirm_text = "Remove Mesa / RADV"
        confirmation = ConfirmDialog(
            tr(title),
            tr(body),
            summary=(
                (tr("Source"), "keyboardspecialist/bc250-steamos"),
                (tr("Reviewed revision"), "b8b293ca5781"),
                (
                    tr("Scope"),
                    tr("Private per-game FSR4 profile")
                    if fsr4_only
                    else tr("Mesa / RADV + verified scheduler policy"),
                ),
                (
                    tr("Recovery"),
                    tr("Stock 32-bit RADV remains available")
                    if installing
                    else tr("Build cache is preserved"),
                ),
            ),
            confirm_text=tr(confirm_text),
            tone="orange" if installing else "red",
            parent=dialog_parent or self,
        )
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_backend_action(
            lambda: self.controller.gestionar_graficos_steamos(action),
            lambda _result: GpuGovernorPage._record_preparation_result(
                self,
                "SteamOS graphics stack",
                "Opened the reviewed SteamOS graphics transaction. Follow its verified result and reboot or sign out only when requested.",
            ),
            "Could not manage the SteamOS graphics stack",
            controls=(),
            error_parent=dialog_parent,
        )

    def _prepare_steamos_diagnostics(
        self,
        _plan: GpuDependencyPlan,
        dialog_parent: QWidget | None,
    ) -> None:
        self._run_backend_action(
            self.controller.diagnostico_steamos,
            lambda _result: GpuGovernorPage._record_preparation_result(
                self,
                "SteamOS diagnostics",
                "Opened Control Center's native SteamOS diagnostics. No system setting was changed.",
            ),
            "Could not open SteamOS diagnostics",
            controls=(),
            error_parent=dialog_parent,
        )

    def _prepare_governor_removal(
        self,
        plan: GpuDependencyPlan,
        dialog_parent: QWidget | None,
    ) -> None:
        confirmation = ConfirmDialog(
            "Uninstall GPU governor",
            tr_format(
                "Stop and uninstall {governor}? Its configuration and cloned source will be preserved.",
                governor=plan.preference,
            ),
            summary=(
                ("Governor", plan.preference),
                ("Service", "Stopped and disabled"),
                ("Configuration", "Preserved"),
                ("Cloned source", "Preserved"),
            ),
            confirm_text="Uninstall",
            tone="red",
            parent=dialog_parent or self,
        )
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return
        if self.settings_service is None:
            raise RuntimeError("GpuGovernorPage requires a settings service to save preferences")
        self.settings_service.save_local_config({"gpu_governor": "auto"})
        self._run_backend_action(
            lambda: self.controller.desinstalar_governor(plan.preference),
            lambda _result: GpuGovernorPage._record_preparation_result(
                self,
                "Uninstall GPU governor",
                tr_format(
                    "Opened the safe removal workflow for {governor}.",
                    governor=plan.preference,
                ),
            ),
            "Could not uninstall GPU governor",
            controls=(),
            error_parent=dialog_parent,
        )

    def _prepare_governor_installation(
        self,
        plan: GpuDependencyPlan,
        dialog_parent: QWidget | None,
    ) -> None:
        if plan.has_conflicts and not GpuGovernorPage._confirm_governor_conflicts(
            self, plan, dialog_parent
        ):
            return
        if self.settings_service is None:
            raise RuntimeError("GpuGovernorPage requires a settings service to save preferences")
        self.settings_service.save_local_config({"gpu_governor": plan.preference})
        if plan.route == "shared":
            def operation():
                return self.controller.instalar_dependencias_bc250(
                    plan.has_conflicts,
                    plan.has_conflicts,
                    plan.preference,
                    plan.include_pwm,
                    set(plan.components),
                )
        else:
            def operation():
                return self.controller.instalar_governor(
                    plan.has_conflicts, plan.has_conflicts, plan.preference
                )
        self._run_backend_action(
            operation,
            lambda _result: GpuGovernorPage._record_preparation_result(
                self,
                "Prepare dependencies",
                "Opened the shared BC250 dependency preparation workflow.",
            ),
            "Could not prepare dependencies",
            controls=(),
            error_parent=dialog_parent,
        )

    def _confirm_governor_conflicts(
        self,
        plan: GpuDependencyPlan,
        dialog_parent: QWidget | None,
    ) -> bool:
        conflict_names = ", ".join(
            tr(name) if name == "Unknown governor" else name for name in plan.conflicts
        )
        confirmation = ConfirmDialog(
            "Switch GPU governor safely",
            tr_format(
                "{governors} is active or enabled. Running two GPU frequency governors can crash the GPU or cause a green screen at boot. Stop and disable it before preparing {selected_governor}?",
                governors=conflict_names,
                selected_governor=plan.resolved_governor,
            ),
            summary=(
                ("Selected governor", plan.resolved_governor),
                ("Conflicting governor", conflict_names),
                ("Required action", "Stop and disable conflicting service"),
            ),
            confirm_text="Disable conflict and continue",
            tone="red",
            parent=dialog_parent or self,
        )
        return confirmation.exec() == QDialog.DialogCode.Accepted

    def _service_action(self, action: str, *, reset_cyan_fix_flags: bool = False) -> None:
        tools = _dict(self.current_state.get("tools"))
        plan = plan_gpu_service_action(
            action,
            backend=self.current_state.get("governor_backend"),
            incompatible_governors=tools.get("incompatible_gpu_governors") or (),
        )
        description = tr_format(plan.description, **dict(plan.description_values))
        # Starting, stopping or restarting the governor asks nothing here: the
        # terminal asks for the password right after, and a window in front
        # of it was one more click for the same decision. Starting it over
        # another governor still asks, because that also stops the other one.
        if not plan.has_conflicts:
            self._run_service_plan(plan, reset_cyan_fix_flags=reset_cyan_fix_flags)
            return
        dialog = ConfirmDialog(
            tr_format("{action} GPU governor", action=tr(plan.label)),
            description,
            summary=(
                ("Service", plan.service),
                ("Backend", plan.backend),
                ("Action", tr(plan.label)),
                ("Boot persistence", plan.boot_persistence),
                *((("Conflict", ", ".join(plan.conflicts)),) if plan.conflicts else ()),
            ),
            confirm_text=tr(plan.confirm_text),
            tone=plan.tone,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_service_plan(plan, reset_cyan_fix_flags=reset_cyan_fix_flags)


    def read_service_status(self) -> None:
        def success(result: object) -> None:
            if isinstance(result, str):
                # No service manager to ask (runit, s6...): its own explanation.
                self._append_console(result)
                show_toast(self, "Governor status", result, tone="blue")
                return
            self._last_operation_summary = "Opened the governor status in the terminal."
            self.last_operation_line.set_values("Read status", self._last_operation_summary)

        self._run_backend_action(
            self.controller.status_governor,
            success,
            "Could not read governor status",
            refresh=False,
        )

    def open_voltage_lab(self) -> None:
        self._sync_voltage_lab(self.current_state)
        self.page_stack.setCurrentWidget(self.overview_page)
        self.voltage_lab_drawer.set_profile(self._voltage_opening_level())
        self._sync_voltage_drawer()
        self.voltage_lab_drawer.show_animated()

    def _voltage_opening_level(self) -> int:
        """The level the laboratory opens on: what the board runs now.

        It used to open on whatever was chosen last, +10 mV after a start,
        so a +30 mV curve that had been saved looked as if it had not been,
        and Review and apply would have taken it back down to +10.
        """
        if self._voltage_custom_edited:
            # Values typed and not applied yet are shown, not dropped.
            return -1
        applied = self._voltage_applied_level
        if applied in self.voltage_lab_drawer.profile_buttons:
            return int(applied)
        if applied == 0:
            # The packaged curve: nothing is boosted, so the first level is
            # offered as the proposal, as before.
            return 1
        # A curve of its own, or a level the drawer has no button for: the
        # custom table shows it point by point.
        return -1

    def gamepad_focus_scope(self) -> QWidget:
        if self.voltage_lab_drawer.is_open():
            return self.voltage_lab_drawer.drawer
        return self.page_stack.currentWidget() or self

    def gamepad_back(self) -> bool:
        if self.voltage_lab_drawer.is_open():
            self.voltage_lab_drawer.close_animated()
            return True
        return False

    def _voltage_keypad_edit_active(self) -> bool:
        drawer = getattr(self, "voltage_lab_drawer", None)
        drawer_editors = drawer.editors() if drawer is not None else ()
        return voltage_keypad_edit_active(
            drawer_editors, application=QApplication.instance()
        )



    def _select_drawer_voltage_profile(self, level: int) -> None:
        self._clear_stale_voltage_keypad_state()
        self.voltage_lab_drawer.set_profile(int(level))
        self._sync_voltage_drawer()

    def _drawer_custom_voltage_changed(self, frequency: int, value: int) -> None:
        """Record what was typed. Do not redraw the row it was typed into.

        ``set_curve`` rebuilds the row widgets whenever the values change, so
        syncing the drawer from its own editor destroys the spin box under the
        user's fingers mid-edit — and takes the keypad's target with it.
        """
        self._voltage_custom_values[int(frequency)] = int(value)
        self._voltage_custom_edited.add(int(frequency))

    def _request_apply_voltage_curve_from_drawer(self) -> None:
        self._request_apply_voltage_curve(
            level_override=self.voltage_lab_drawer.selected_level(),
            custom_values_override=self.voltage_lab_drawer.custom_values(),
            source_controls=(self.voltage_lab_drawer.apply_button,),
        )

    def _request_restore_voltage_defaults(self) -> None:
        self._request_apply_voltage_curve(
            level_override=0,
            custom_values_override={},
            source_controls=(self.voltage_lab_drawer.restore_button,),
        )

    def _clear_stale_voltage_keypad_state(self) -> None:
        drawer = getattr(self, "voltage_lab_drawer", None)
        clear_voltage_keypad_state(drawer.editors() if drawer is not None else ())


    def _request_apply_voltage_curve(
        self,
        *,
        level_override: int | None = None,
        custom_values_override: dict[int, int] | None = None,
        source_controls: tuple[QWidget, ...] = (),
    ) -> None:
        if bool(getattr(self, "_is_oberon_backend", False)):
            self._show_info(
                "Oberon voltage changes are unavailable",
                "Oberon has only two YAML endpoints, not a validated voltage curve. No voltage was written. Use a protected Oberon frequency profile while the GPU is idle, or switch to Cyan for voltage-curve testing.",
                tone="orange",
            )
            return
        # Every caller passes the drawer's own selection; the detected level
        # is the fallback now that no combo box exists to read.
        level = (
            _integer(level_override, 0)
            if level_override is not None
            else _integer(getattr(self, "_voltage_detected_level", 0), 0)
        )
        custom_values = (
            dict(custom_values_override)
            if custom_values_override is not None
            else {
                frequency: int(self._voltage_custom_values[frequency])
                for frequency in sorted(self._voltage_editable_frequencies)
                if frequency in self._voltage_custom_values
            }
            if level == -1
            else {}
        )
        plan = plan_voltage_apply(
            level=level,
            editable_frequencies=self._voltage_editable_frequencies,
            profile_frequencies=self._voltage_profile_frequencies,
            current_voltages=self._voltage_current_map,
            custom_values=custom_values,
            is_oberon=bool(getattr(self, "_is_oberon_backend", False)),
        )
        if not plan.available:
            self._show_info(
                "No editable voltage points",
                "The active TOML does not contain voltage safe-points supported by the selected profile.",
                tone="orange",
            )
            return

        if plan.custom_mode:
            values = dict(plan.custom_values)
            title = "Apply custom GPU voltage curve"
            description = (
                "Only the editable frequencies shown in the table will be changed. A timestamped TOML backup is created, "
                "the governor restarts, and the previous D-Bus range is restored."
            )
            profile_label = "Custom"
        else:
            values = None
            title = tr_format("Apply GPU voltage Level {level}", level=level)
            if level == 0:
                description = tr(
                    "This restores every packaged original voltage and disables the +2000 MHz TOML points. If the current range exceeds 2000 MHz, it is safely limited after the governor restarts. A backup is created first."
                )
            else:
                description = tr_format(
                    "This restores the complete packaged governor curve, then adds +{added} mV to every safe-point from {start} MHz. A backup is created before the governor restarts.",
                    added=level * 10,
                    start=VOLTAGE_BOOST_START_MHZ,
                )
            profile_label = tr_format("Level {level}", level=level)

        if plan.violation is not None:
            violation = plan.violation
            self._show_info(
                "Invalid voltage curve",
                tr_format(
                    "{frequency} MHz uses {voltage} mV, below {previous_frequency} MHz at {previous_voltage} mV. Voltage cannot decrease while frequency increases.",
                    frequency=violation.frequency,
                    voltage=violation.voltage,
                    previous_frequency=violation.previous_frequency,
                    previous_voltage=violation.previous_voltage,
                ),
                tone="red",
            )
            return

        dialog = ConfirmDialog(
            title,
            f"{tr(description)} {tr('Stop every game, benchmark, and 3D workload before continuing.')}",
            summary=(
                ("Profile", profile_label),
                ("Curve points", str(len(plan.active_frequencies))),
                ("Maximum result", f"{plan.maximum_voltage} mV"),
                (
                    "D-Bus range",
                    "Safely limited to active points after restart"
                    if level == 0
                    else "Preserved and restored after restart",
                ),
            ),
            confirm_text="Apply voltage curve",
            tone="orange",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def operation() -> object:
            if plan.custom_mode:
                return self.controller.aplicar_laboratorio_voltaje_gpu_personalizado(
                    values
                )
            return self.controller.aplicar_laboratorio_voltaje_gpu(level)

        def success(output: object) -> None:
            # What was typed is on disk now; the editor follows the file again.
            self._voltage_custom_edited.clear()
            self._last_operation_summary = f"Applied GPU voltage {profile_label} from the integrated Voltage Curve Studio."
            self.last_operation_line.set_values(
                "Voltage curve", self._last_operation_summary
            )
            self._append_console(self._last_operation_summary)
            if output:
                self._append_console(str(output))
            self._show_info(
                "Voltage curve applied",
                "The governor restarted successfully and the previous runtime range was requested again.",
                tone="blue",
            )

        self._run_backend_action(
            operation,
            success,
            "Voltage curve failed",
            controls=tuple(source_controls),
            keep_voltage_lab=True,
        )

    def _toggle_advanced(
        self, _checked: bool = False, *, show: bool | None = None
    ) -> None:
        # Kept as a compatibility hook for older callers.  Diagnostics are a
        # permanent part of the GPU page and are no longer collapsible.
        self.advanced_card.setVisible(True)
        if self.advanced_status is not None:
            self.advanced_status.setText(tr("Available"))
            self.advanced_status.set_tone("blue")

    def _manual_refresh(self) -> None:
        self._state_cache.invalidate("gpu", "performance")
        self.refresh()


    def _fetch_refresh_payload(self) -> dict[str, dict]:
        # state_cache.gpu() delegates to controller.estado_bc250() in a worker;
        # the UI refresh slot only schedules/coalesces the request.
        return {
            "gpu": self._state_cache.gpu(),
            "performance": self._state_cache.performance(),
        }

    def refresh(self) -> None:
        if self._action_busy:
            return
        self._refresher.request()

    def _refresh_failed(self, message: str) -> None:
        self._append_console(f"GPU refresh warning: {message}")



    @staticmethod
    def _telemetry_copy(gpu: dict, perf: dict) -> dict[str, object]:
        presentation = present_gpu_telemetry(gpu, perf)
        return {
            "temperature": presentation.temperature,
            "utilization": presentation.utilization,
            "voltage_text": GpuGovernorPage._render_telemetry_text(
                presentation.voltage_text
            ),
            "temperature_text": GpuGovernorPage._render_telemetry_text(
                presentation.temperature_text
            ),
            "utilization_text": GpuGovernorPage._render_telemetry_text(
                presentation.utilization_text
            ),
            "vram_value": GpuGovernorPage._render_telemetry_text(
                presentation.vram_value
            ),
            "vram_detail": GpuGovernorPage._render_telemetry_text(
                presentation.vram_detail
            ),
            "power_label": GpuGovernorPage._render_telemetry_text(
                presentation.power_label
            ),
            "power_text": GpuGovernorPage._render_telemetry_text(
                presentation.power_text
            ),
            "power_detail": GpuGovernorPage._render_telemetry_text(
                presentation.power_detail
            ),
        }

    @staticmethod
    def _render_telemetry_text(value: TelemetryText) -> str:
        return (
            value.template
            if value.literal
            else tr_format(value.template, **dict(value.values))
        )


    @staticmethod
    def _persistent_range_copy(frequency_range: dict) -> str:
        if not frequency_range.get("valid"):
            return tr_format(
                "invalid: {error}",
                error=str(frequency_range.get("error") or tr("unknown TOML state")),
            )
        if not frequency_range.get("enabled"):
            return tr("disabled for runtime profile mode")
        if frequency_range.get("mode") == "floor":
            return tr_format(
                "persistent floor {minimum} MHz; maximum remains controlled by the runtime profile",
                minimum=_integer(frequency_range.get("min"), 0),
            )
        persistent_maximum = _integer(frequency_range.get("max"), 0)
        return tr_format(
            "custom floor {minimum} MHz, maximum {maximum}",
            minimum=_integer(frequency_range.get("min"), 0),
            maximum=(persistent_maximum or tr("unlimited")),
        )


    @staticmethod
    def _render_runtime_text(value: RuntimeText) -> str:
        return (
            value.template
            if value.literal
            else tr_format(value.template, **dict(value.values))
        )






    def _retranslate_cyan_compatibility_labels(self) -> None:
        """Keep compact Cyan correction labels accurate after a live language switch."""
        from ..i18n import governor_fix_label

        self.cyan_fix_metrics.setText(governor_fix_label("metrics"))
        self.cyan_fix_frequency.setText(governor_fix_label("frequency"))
        self.cyan_fix_metrics.setToolTip(
            tr("Corrects Cyan telemetry metrics when the active kernel needs it.")
        )
        self.cyan_fix_frequency.setToolTip(
            tr("Corrects live GPU frequency reporting when the active Cyan runtime supports it.")
        )

    def retranslate_dynamic_copy(self) -> None:
        self._retranslate_cyan_compatibility_labels()
        redesigned = getattr(self, "_redesigned_gpu_view", None)
        if redesigned is not None:
            redesigned.retranslate_dynamic_copy()

    def _populate_points(self, points: list, current: int) -> None:
        plan = build_safe_point_plan(
            points,
            current=current,
            active_maximum=self.active_max,
            packaged_voltages=self.PACKAGED_DEFAULT_VOLTAGES,
        )
        cleaned = list(plan.points)
        self.safe_frequencies = list(plan.frequencies)
        self.safe_voltage_map = dict(plan.voltage_map)

        # A passive refresh must not rebuild an open combo box. Clearing it
        # closes Qt's popup and discards the row currently highlighted with a
        # gamepad even when the safe-point data is unchanged.
        popup_visible = self._safe_point_popup_visible()
        if not popup_visible:
            self._update_safe_points_table(plan.rows)
            self._sync_safe_point_combo(cleaned, current)
        self._update_selected_safe_point()



    def _safe_point_popup_visible(self) -> bool:
        try:
            return bool(self.oc_frequency.view().isVisible())
        except (RuntimeError, TypeError):
            return False



    def _quick_safe_point_changed(self, _index: int = 0) -> None:
        frequency = _integer(self.quick_safe_point_combo.currentData(), 0)
        if frequency <= 0:
            return
        index = self.oc_frequency.findData(frequency)
        if index >= 0 and index != self.oc_frequency.currentIndex():
            # This naturally re-runs _update_selected_safe_point through the
            # existing oc_frequency signal, which also calls back into
            # _sync_quick_safe_point_selection above to keep both panels
            # showing the same pick.
            self.oc_frequency.setCurrentIndex(index)
        else:
            self._update_selected_safe_point()

    def _current_safe_points(self) -> list[tuple[int, int]]:
        return [
            (frequency, self.safe_voltage_map.get(frequency, 0))
            for frequency in self.safe_frequencies
        ]


    def _edit_profile(self, index: int) -> None:
        if index < 0 or index >= len(self.preset_buttons):
            return
        button = self.preset_buttons[index]
        override = self._custom_profile_overrides.get(index)
        minimum, maximum = button.payload
        name = override["name"] if override else button.text().splitlines()[0]
        reference_frequency = override["frequency"] if override else maximum
        safe_points = self._current_safe_points()
        if not safe_points:
            self._show_info(
                "No validated safe-points yet",
                "Refresh GPU status at least once before editing a profile.",
                tone="orange",
            )
            return
        dialog = GpuProfileEditDialog(
            name=name,
            minimum_mhz=minimum,
            maximum_mhz=maximum,
            reference_frequency=reference_frequency,
            safe_points=safe_points,
            allowed_min=self.allowed_min,
            allowed_max=self.allowed_max,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        profile = dialog.result_profile()
        profile["name"] = _custom_profile_name(index, profile["name"])
        self._custom_profile_overrides[index] = profile
        _save_custom_gpu_profile(application_settings(), index, profile)
        self._apply_profile_overrides()
        self._update_profile_availability()



    @staticmethod
    def _render_safety_message(message: SafetyMessage) -> str:
        if message.literal:
            return message.template
        return tr_format(message.template, **dict(message.values))


    def _copy_apu_diagnostics(self) -> None:
        payload = dict(self.current_state.get("apu_telemetry") or {})
        payload["cyan_compatibility"] = {
            key: _dict(self.current_state.get("cyan_telemetry")).get(key)
            for key in ("set_method", "method", "fix_metrics", "fix_frequency")
        }
        QApplication.clipboard().setText(json.dumps(payload, indent=2, ensure_ascii=False))


    @staticmethod
    def _render_diagnostic_text(value: DiagnosticText) -> str:
        if value.literal:
            return value.template
        translated_values = set(value.translate_values)
        values = {
            key: tr(item) if key in translated_values else item
            for key, item in value.values
        }
        return tr_format(value.template, **values)

    def _safe_point_voltage_text(self, frequency: int) -> str:
        voltage = self.safe_voltage_map.get(int(frequency))
        return f"{voltage} mV" if voltage else tr("Not specified")

    @classmethod
    def _profile_name(cls, minimum: int, maximum: int) -> str:
        profiles = {
            tuple(payload): name
            for values in (cls.CYAN_PROFILE_VALUES, cls.OBERON_PROFILE_VALUES)
            for name, _summary, payload in values
        }
        if minimum and maximum and minimum == maximum:
            return "Fixed"
        return profiles.get((minimum, maximum), "Custom")

    @staticmethod
    def _temperature_status(value: float) -> str:
        if value <= 0:
            return "Sensor unavailable"
        if value < 75:
            return tr("Normal")
        if value < 85:
            return tr("Warm")
        return "High"

    def _append_console(self, message: str) -> None:
        if not hasattr(self, "console"):
            return
        timestamp = datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S")
        text = str(message or "").strip("\n")
        if not text:
            return
        self.console.appendPlainText(f"[{timestamp}] {text}")
        scrollbar = self.console.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _clear_console(self) -> None:
        self.console.setPlainText(
            "GPU Governor console cleared. No hardware command has been executed."
        )

    def _show_info(
        self,
        title: str,
        message: str,
        *,
        tone: str = "blue",
        parent: QWidget | None = None,
        modal: bool | None = None,
    ) -> None:
        # Outcomes go to a toast; warnings and errors that ask for something
        # before carrying on stay a dialog.
        if not (tone in {"orange", "red"} if modal is None else modal):
            show_toast(parent or self, title, message, tone=tone)
            return
        icons = {
            "red": "warning_orange",
            "orange": "warning_orange",
            "purple": "gpu_purple",
            "green": "shield_green",
            "blue": "info_blue",
        }
        dialog = InfoDialog(
            title,
            message,
            icons.get(tone, "info_blue"),
            parent or self,
            eyebrow="GPU GOVERNOR",
            notice="",
            tone=tone,
        )
        dialog.exec()
