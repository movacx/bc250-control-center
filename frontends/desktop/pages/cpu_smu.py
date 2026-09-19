from __future__ import annotations

import logging
import time
from datetime import datetime

from PyQt6.QtCore import QProcess, QSize, Qt, QTimer
from PyQt6.QtGui import QIntValidator, QTextCursor
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from bc250cc.domain.cpu import FREQUENCY_RANGE
from bc250cc.shared.failure_text import describe_failure

from ..components.async_tools import AsyncRefresh, BackgroundExecutor
from ..components.buttons import WrappingButton as QPushButton
from ..components.page_widgets import (
    ConfirmDialog,
    ControlPageHeader,
    MetricTile,
    PresetButton,
    SectionCard,
    StatusLine,
)
from ..components.responsive import (
    clear_grid,
    configure_responsive_scroll_area,
    effective_viewport_width,
)
from ..components.widgets import IconBadge, InfoDialog, apply_shadow, icon
from ..core.cpu_persistence_plan import (
    CpuPersistencePlan,
    PersistenceBlocker,
    plan_cpu_persistence,
    validate_detection_for_persistence,
)
from ..core.cpu_refresh_presenter import (
    CpuTelemetryPresentation,
    CpuText,
    present_cpu_persistence,
    present_cpu_session_summary,
    present_cpu_telemetry,
    present_cpu_tuning,
)
from ..core.error_diagnostics import diagnose_error
from ..core.external_links import open_external_url
from ..core.state import collect_named_sources, state_cache_for
from ..i18n import tr, tr_format
from ..theme import COLORS

logger = logging.getLogger(__name__)


def _dict(value):
    if hasattr(value, "to_dict"):
        return value.to_dict()
    try:
        return dict(value or {})
    except Exception:
        return {}


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


# One source of truth: the domain owns the bound, this page does not keep
# its own copy that can silently drift from the validators and the helpers.
CPU_FREQUENCY_RANGE = FREQUENCY_RANGE
CPU_VID_RANGE = (950, 1325)
CPU_TEMPERATURE_RANGE = (70, 90)
PASSIVE_TELEMETRY_TILE_HEIGHT = 76
class CpuSummaryItem(QFrame):
    """CPU counterpart to the GPU governor summary chip."""

    def __init__(self, label: str, value: str, detail: str, icon_name: str, background: str, parent=None):
        super().__init__(parent)
        self.setProperty("gpuSummaryItem", True)
        self.setMinimumHeight(68)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(10)
        row.addWidget(IconBadge(icon_name, background, 30, radius=8))

        text = QVBoxLayout()
        text.setSpacing(0)
        self.label = QLabel(tr(label))
        self.label.setProperty("gpuSummaryLabel", True)
        self.value = QLabel(tr(value))
        self.value.setProperty("gpuSummaryValue", True)
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail = QLabel(tr(detail))
        self.detail.setProperty("gpuSummaryDetail", True)
        self.detail.setWordWrap(True)
        text.addWidget(self.label)
        text.addWidget(self.value)
        text.addWidget(self.detail)
        row.addLayout(text, 1)

    def set_values(self, value: str, detail: str | None = None) -> None:
        self.value.setText(tr(value))
        if detail is not None:
            self.detail.setText(tr(detail))


class CpuSummaryStrip(QFrame):
    """Compact top telemetry strip matching the GPU governor visual language."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("gpuSummaryStrip", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        apply_shadow(self, blur=16, y=3, alpha=10)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(8, 8, 8, 8)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(8)
        self.items = [
            CpuSummaryItem("Service", "Checking", "session only", "settings_blue", COLORS["blue_soft"]),
            CpuSummaryItem("Frequency", "Not detected", "average across active cores", "cpu_blue", COLORS["blue_soft"]),
            CpuSummaryItem("Target", "3550 MHz / 1050 mV", "temperature cap 90 °C", "compute_blue", COLORS["blue_soft"]),
            CpuSummaryItem("Voltage", "Not detected", "VDDNB / SMU telemetry", "power_gray", COLORS["orange_soft"]),
            CpuSummaryItem("Temperature", "Not detected", "k10temp Tctl", "warning_orange", COLORS["orange_soft"]),
        ]
        self.columns = 0
        self.set_columns(5)

    def set_columns(self, columns: int) -> None:
        columns = max(1, int(columns))
        if columns == self.columns and self.grid.count():
            return
        self.columns = columns
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget() is not None:
                item.widget().setParent(None)
        for index, widget in enumerate(self.items):
            self.grid.addWidget(widget, index // columns, index % columns)
        for column in range(columns):
            self.grid.setColumnStretch(column, 1)


class RuntimeStat(QFrame):
    """Compact status tile shared with the GPU governor runtime layout."""

    def __init__(self, label: str, value: str, detail: str = "", parent=None, *, compact: bool = False):
        super().__init__(parent)
        self.setProperty("runtimeStatCard", True)
        if compact:
            self.setProperty("compactRuntimeStatCard", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(62 if compact else 72)
        layout = QVBoxLayout(self)
        if compact:
            layout.setContentsMargins(10, 8, 10, 8)
            layout.setSpacing(1)
        else:
            layout.setContentsMargins(12, 10, 12, 10)
            layout.setSpacing(2)
        label_widget = QLabel(tr(label))
        label_widget.setWordWrap(True)
        label_widget.setProperty("runtimeStatLabel", True)
        self.value = QLabel(tr(value))
        self.value.setWordWrap(True)
        self.value.setProperty("runtimeStatValue", True)
        self.detail = QLabel(tr(detail))
        self.detail.setProperty("runtimeStatDetail", True)
        self.detail.setWordWrap(True)
        layout.addWidget(label_widget)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)

    def set_values(self, value: str, detail: str | None = None) -> None:
        self.value.setText(tr(value))
        if detail is not None:
            self.detail.setText(tr(detail))


class CpuValueField(QFrame):
    """Direct numeric CPU control with the same visual cadence as the GPU range fields."""

    def __init__(
        self,
        label: str,
        hint: str,
        minimum: int,
        maximum: int,
        value: int,
        unit: str,
        parent: QWidget | None = None,
        *,
        show_hint: bool = True,
        compact: bool = False,
        info_title: str | None = None,
        info_message: str | None = None,
        info_handler=None,
    ):
        super().__init__(parent)
        self.minimum = int(minimum)
        self.maximum = int(maximum)
        self.unit = unit
        self.setProperty("frequencyField", True)
        if compact:
            self.setProperty("compactFrequencyField", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        row = QHBoxLayout(self)
        if compact:
            row.setContentsMargins(12, 8, 12, 8)
            row.setSpacing(8)
        else:
            row.setContentsMargins(12, 10, 12, 10)
            row.setSpacing(10)

        copy = QVBoxLayout()
        copy.setSpacing(1)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(6)
        title = QLabel(tr(label))
        title.setWordWrap(True)
        title.setProperty("fieldLabel", True)
        title_row.addWidget(title, 0, Qt.AlignmentFlag.AlignVCenter)
        title_row.addStretch(1)
        if info_title and info_message and info_handler is not None:
            info_button = QPushButton()
            info_button.setProperty("compactAction", True)
            info_button.setIcon(icon("info_blue"))
            info_button.setToolTip(tr(info_title))
            info_button.setFixedSize(28, 28)
            info_button.setIconSize(QSize(14, 14))
            info_button.clicked.connect(lambda: info_handler(info_title, info_message))
            title_row.addWidget(info_button, 0, Qt.AlignmentFlag.AlignVCenter)
        copy.addLayout(title_row)
        if show_hint:
            detail = QLabel(tr(hint))
            detail.setProperty("fieldHint", True)
            detail.setWordWrap(True)
            copy.addWidget(detail)
        row.addLayout(copy, 1)

        self.input = QLineEdit(str(int(value)))
        self.input.setProperty("frequencyInput", True)
        self.input.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.input.setMinimumWidth(88)
        self.input.setMaximumWidth(128)
        self.input.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.input.setValidator(QIntValidator(self.minimum, self.maximum, self.input))
        row.addWidget(self.input, 0, Qt.AlignmentFlag.AlignVCenter)

        unit_label = QLabel(tr(unit))
        unit_label.setProperty("frequencyUnit", True)
        row.addWidget(unit_label, 0, Qt.AlignmentFlag.AlignVCenter)

    def value(self) -> int:
        try:
            return int(self.input.text())
        except (TypeError, ValueError):
            return 0

    def setValue(self, value: int) -> None:
        bounded = max(self.minimum, min(self.maximum, int(value)))
        self.input.setText(str(bounded))

    def setRange(self, minimum: int, maximum: int) -> None:
        self.minimum = int(minimum)
        self.maximum = max(self.minimum, int(maximum))
        self.input.setValidator(QIntValidator(self.minimum, self.maximum, self.input))


class CpuSmuPage(QWidget):
    """CPU / SMU control restyled to mirror the GPU governor studio layout."""

    PROFILE_VALUES = (
        ("Placa media", "3550 MHz · 1050 mV", (3550, 1050, 90)),
        ("Balance", "3700 MHz · 1150 mV", (3700, 1150, 90)),
        ("Punto medio", "3850 MHz · 1150 mV", (3850, 1150, 90)),
        ("Max seguro UI", "4000 MHz · 1275 mV", (4000, 1275, 90)),
    )

    def __init__(self, controller, parent: QWidget | None = None, *, activity_service=None, settings_service=None):
        super().__init__(parent)
        self.setProperty("cpuSmuPage", True)
        self.controller = controller
        self.activity_service = activity_service
        self.settings_service = settings_service
        self.process: QProcess | None = None
        self._updates_active = False
        self._state_cache = state_cache_for(controller)
        self._background = BackgroundExecutor(self)
        self.current_state: dict = {}
        self._operation = ""
        self._last_stderr = ""
        self._last_operation_summary = "No hardware command has been executed."
        self._last_applied_frequency: int | None = None
        self._summary_columns = 5
        self._workspace_columns = 0
        self._configuration_columns = 0
        self._runtime_columns = 0
        self._runtime_action_columns = 0
        self._metric_columns = 0
        self._field_columns = 0
        self._detail_columns = 0
        self._processor_columns = 0
        self._core_columns = 0
        self._selected_profile_name = "Detecting active configuration"
        self._syncing_active_config = False
        # Keep independent telemetry sources isolated.  A failed systemd read or
        # optional backend must not leave the whole CPU page stuck at
        # "Checking".  Only changed errors are written to the console so a
        # periodic refresh cannot spam the user every few seconds.
        self._last_refresh_errors: dict[str, str] = {}
        self._active_config_signature: tuple | None = None
        self._cpu_config_initialized = False
        self._pending_cpu_target: dict[str, int] | None = None
        self._pending_live_scale: int | None = None
        self._pending_live_frequency: int | None = None
        self._pending_live_temperature: int | None = None
        self._pending_manual_direct = False
        self._manual_scale_available = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        self.scroll = scroll
        self.content = QWidget()
        configure_responsive_scroll_area(scroll, self.content)
        # Long translated runtime labels must wrap inside the selected layout;
        # they must not enlarge the complete vertically scrolling page.
        self.content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(16, 12, 16, 24)
        layout.setSpacing(14)
        scroll.setWidget(self.content)
        outer.addWidget(scroll)

        self.header = ControlPageHeader(
            "CPU / SMU CONTROL",
            "Processor tuning",
            "Validated temporary CPU tuning with service visibility, telemetry, and an in-application console.",
            mode_text="● LIVE SESSION",
            action_text="Prepare CPU tools",
            action_icon="download_blue",
        )
        self.header.refresh_requested.connect(self._manual_refresh)
        self.header.action_requested.connect(self.prepare_tools)
        layout.addWidget(self.header)
        # Keep the header object as an internal signal/state holder, but do not
        # render the introductory banner. Hidden widgets consume no layout space,
        # so the CPU workspace starts at the top of the page.
        self.header.hide()

        # Kept as a hidden state sink because refresh/update code shares these
        # values with the detailed telemetry card below.  The duplicated top
        # telemetry rail is intentionally not part of the visible layout.
        self.summary_strip = CpuSummaryStrip(self.content)
        self.summary_strip.hide()

        self.prepare_tools_button = QPushButton(tr("Prepare CPU tools"))
        self.prepare_tools_button.setProperty("compactAction", True)
        self.prepare_tools_button.setIcon(icon("download_blue"))
        self.prepare_tools_button.clicked.connect(self.prepare_tools)

        self.configuration_card = self._build_configuration_card()
        self.scale_actions_card = self._build_scale_actions_card()
        self.metrics_card = self._build_metrics_card()
        self.processor_card = self._build_processor_card()
        self.cores_card = self._build_cores_card()
        self.runtime_card = self._build_runtime_card()
        self.core_unlock_card = self._build_core_unlock_card()
        for paired_card in (
            self.metrics_card,
            self.processor_card,
            self.core_unlock_card,
        ):
            paired_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # The two passive telemetry strips form one visual system.  Metrics
        # must not absorb spare grid height while the core strip stays compact.
        self.metrics_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.cores_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.configuration_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.runtime_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.scale_actions_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.advanced_card = self._build_advanced_card()
        self.advanced_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.configuration_left_column = QWidget()
        self.configuration_left_column.setMinimumWidth(0)
        self.configuration_left_column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.configuration_left_layout = QVBoxLayout(self.configuration_left_column)
        self.configuration_left_layout.setContentsMargins(0, 0, 0, 0)
        self.configuration_left_layout.setSpacing(14)
        self.configuration_left_layout.addWidget(self.configuration_card)
        self.configuration_left_layout.addWidget(self.scale_actions_card)
        self.advanced_toggle.setText(tr("Hide advanced details"))
        if self.advanced_card.status is not None:
            self.advanced_card.status.setText(tr("Visible"))
            self.advanced_card.status.set_tone("gray")

        self.workspace_tabs = QFrame()
        self.workspace_tabs.setProperty("cpuWorkspaceTabs", True)
        tabs_layout = QGridLayout(self.workspace_tabs)
        tabs_layout.setContentsMargins(5, 5, 5, 5)
        tabs_layout.setSpacing(5)
        self.workspace_tabs_layout = tabs_layout
        self._workspace_tab_columns = 0
        self.workspace_tab_group = QButtonGroup(self)
        self.workspace_tab_group.setExclusive(True)
        self.workspace_tab_buttons: dict[str, QPushButton] = {}
        tab_specs = (
            (
                "configuration",
                "CPU configuration",
                "Profiles, temporary tuning, persistence, and advanced details.",
                "settings_blue",
            ),
            (
                "overview",
                "Overview and live monitoring",
                "Processor overview, live cores, and hidden-core unlock.",
                "cpu_blue",
            ),
        )
        for index, (key, text, tooltip, icon_name) in enumerate(tab_specs):
            button = QPushButton(tr(text))
            button.setCheckable(True)
            button.setProperty("cpuWorkspaceTab", True)
            button.setIcon(icon(icon_name))
            button.setToolTip(tr(tooltip))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            button.clicked.connect(
                lambda checked, name=key: self._select_workspace(name)
                if checked
                else None
            )
            self.workspace_tab_group.addButton(button)
            self.workspace_tab_buttons[key] = button
            tabs_layout.addWidget(button, 0, index)
        layout.addWidget(self.workspace_tabs)

        self.workspace_stack = QStackedWidget()
        self.workspace_stack.setProperty("cpuWorkspaceStack", True)
        self.workspace_stack.setMinimumWidth(0)
        self.workspace_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

        self.overview_page = QWidget()
        self.overview_page.setProperty("cpuWorkspacePage", True)
        self.overview_page.setMinimumWidth(0)
        self.workspace = QGridLayout(self.overview_page)
        self.workspace.setContentsMargins(0, 0, 0, 0)
        self.workspace.setHorizontalSpacing(14)
        self.workspace.setVerticalSpacing(14)

        self.configuration_page = QWidget()
        self.configuration_page.setProperty("cpuWorkspacePage", True)
        self.configuration_page.setMinimumWidth(0)
        self.configuration_workspace = QGridLayout(self.configuration_page)
        self.configuration_workspace.setContentsMargins(0, 0, 0, 0)
        self.configuration_workspace.setHorizontalSpacing(14)
        self.configuration_workspace.setVerticalSpacing(14)

        self.workspace_stack.addWidget(self.overview_page)
        self.workspace_stack.addWidget(self.configuration_page)
        layout.addWidget(self.workspace_stack)
        layout.addStretch(1)

        self._clear_preset_checks()
        try:
            if self.settings_service is None:
                raise RuntimeError("CpuSmuPage requires a settings service to read preferences")
            local_config = _dict(self.settings_service.read_local_config())
            loaded_frequency = int(local_config.get("cpu_oc_last_applied_frequency", 0) or 0)
            self._last_applied_frequency = loaded_frequency or None
        except Exception:
            self._last_applied_frequency = None
        # Building privileged commands happens off the UI thread.  Keep this
        # explicit state separate from QProcess so a timer refresh cannot
        # re-enable an action while Polkit/repository validation is pending.
        self._command_build_pending = False
        # Preserve the most recent complete eligibility result if a later
        # optional probe (service status, Git metadata, etc.) times out.
        self._last_core_unlock_snapshot: dict = {}
        self._update_staged_target()
        self.apply_button.setEnabled(False)
        self._select_workspace("configuration")
        self._reflow(1400)
        self.timer = QTimer(self)
        self.timer.setInterval(4000)
        self.timer.timeout.connect(self.refresh)
        self._refresher = AsyncRefresh(
            self,
            "cpu-smu-refresh",
            self._fetch_refresh_payload,
            self._apply_refresh_payload,
            self._refresh_failed,
        )

        from .cpu_control_integration import install_unified_cpu_control

        install_unified_cpu_control(self)

    def _select_workspace(self, name: str) -> None:
        key = "configuration" if name == "configuration" else "overview"
        index = 1 if key == "configuration" else 0
        self.workspace_stack.setCurrentIndex(index)
        self.workspace_tab_buttons[key].setChecked(True)
        self.scroll.verticalScrollBar().setValue(0)

    def _build_configuration_card(self) -> SectionCard:
        card = SectionCard(
            "CPU configuration",
            "Choose a preset or enter the CPU frequency, VID limit, and temperature cap you want to test.",
            icon_name="settings_blue",
            icon_background=COLORS["blue_soft"],
            status=("Temporary", "green"),
        )

        preset_grid = QGridLayout()
        preset_grid.setContentsMargins(0, 0, 0, 0)
        preset_grid.setHorizontalSpacing(8)
        preset_grid.setVerticalSpacing(8)
        self.preset_grid = preset_grid
        self.preset_group = QButtonGroup(self)
        self.preset_group.setExclusive(True)
        self.preset_buttons: list[PresetButton] = []
        for index, (title, summary, payload) in enumerate(self.PROFILE_VALUES):
            button = PresetButton(title, summary, payload)
            button.setProperty("cpuFrequencyPreset", True)
            button.setMinimumHeight(64)
            button.clicked.connect(lambda checked, b=button: self._select_preset(b) if checked else None)
            self.preset_group.addButton(button)
            self.preset_buttons.append(button)
        self._reflow_presets(1400)
        card.body.addLayout(preset_grid)

        self.parameter_grid = QGridLayout()
        self.parameter_grid.setContentsMargins(0, 0, 0, 0)
        self.parameter_grid.setHorizontalSpacing(10)
        self.parameter_grid.setVerticalSpacing(10)
        self.frequency_control = CpuValueField(
            "CPU frequency",
            "Desired CPU clock for automatic detection. Control Center sends this value to bc250-detect.",
            *CPU_FREQUENCY_RANGE,
            3550,
            "MHz",
            show_hint=False,
            compact=True,
            info_title="CPU frequency",
            info_message="This is the CPU speed you want to test. Higher values can improve performance, but they also require more stability margin. If you are unsure, start with a preset.",
            info_handler=self._show_info,
        )
        self.vid_control = CpuValueField(
            "VID limit",
            "Maximum CPU voltage allowed during detection. Lower VID usually means more undervolt.",
            *CPU_VID_RANGE,
            1050,
            "mV",
            show_hint=False,
            compact=True,
            info_title="VID limit",
            info_message="This is the voltage limit used by automatic detection. A lower VID asks the detector to use less voltage. It is a detection target, not a fixed voltage saved for boot.",
            info_handler=self._show_info,
        )
        self.temperature_control = CpuValueField(
            "Temperature cap",
            "Maximum CPU/GPU temperature that the SMU may target during detection. The UI caps this at 90 °C.",
            *CPU_TEMPERATURE_RANGE,
            90,
            "°C",
            show_hint=False,
            compact=True,
            info_title="Temperature cap",
            info_message="This sets the hottest point allowed during the test. If you are unsure, leave it at 90 °C.",
            info_handler=self._show_info,
        )
        self.scale_control = CpuValueField(
            "Manual live scale",
            "Scale is not mV. More negative generally means less voltage.",
            -50,
            0,
            -34,
            "scale",
            show_hint=False,
            compact=True,
            info_title="Manual live scale",
            info_message="When manual mode is selected, this exact scale is applied together with the chosen frequency for the current session. It is not saved for boot.",
            info_handler=self._show_info,
        )
        self.parameter_fields = [
            self.frequency_control,
            self.vid_control,
            self.temperature_control,
            self.scale_control,
        ]
        for field in self.parameter_fields:
            field.input.textChanged.connect(self._on_parameter_changed)
        self._reflow_parameter_fields(1400)
        card.body.addLayout(self.parameter_grid)
        return card

    def _build_metrics_card(self) -> SectionCard:
        card = SectionCard(
            "Live metrics",
            "",
            icon_name="cpu_blue",
            icon_background=COLORS["blue_soft"],
            status=("Passive", "green"),
            compact=True,
        )
        card.root.setContentsMargins(12, 9, 12, 10)
        card.root.setSpacing(7)

        self.metrics_grid = QGridLayout()
        self.metrics_grid.setContentsMargins(0, 0, 0, 0)
        self.metrics_grid.setHorizontalSpacing(8)
        self.metrics_grid.setVerticalSpacing(8)
        self.frequency_metric = MetricTile(
            "Average frequency", "Not detected", "Kernel-reported average", icon_name="cpu_blue", icon_background=COLORS["blue_soft"], compact=True
        )
        self.voltage_metric = MetricTile(
            "Voltage sensor", "Not detected", "VDDNB / SMU telemetry", icon_name="power_gray", icon_background=COLORS["orange_soft"], compact=True
        )
        self.temperature_metric = MetricTile(
            "Temperature", "Not detected", "k10temp Tctl", icon_name="warning_orange", icon_background=COLORS["orange_soft"], compact=True
        )
        self.power_metric = MetricTile(
            "SoC package power", "Not detected", "AMDGPU hwmon sensor", icon_name="power_gray", icon_background="neutral_soft", compact=True
        )
        self.metric_tiles = [
            self.frequency_metric,
            self.voltage_metric,
            self.temperature_metric,
            self.power_metric,
        ]
        for tile in self.metric_tiles:
            # Allow the large metric value and a two-line translated detail.
            # Core tiles use the same height so both strips remain symmetric.
            tile.setFixedHeight(PASSIVE_TELEMETRY_TILE_HEIGHT)
            tile.layout().setContentsMargins(9, 7, 9, 7)
            tile.layout().setSpacing(8)
        self._reflow_metric_tiles(1400)
        card.body.addLayout(self.metrics_grid)
        return card

    def _build_processor_card(self) -> SectionCard:
        card = SectionCard(
            "Processor overview",
            "CPU-Z-style identification read directly from Linux kernel interfaces, without changing hardware state.",
            icon_name="cpu_blue",
            icon_background=COLORS["blue_soft"],
            status=("Live", "green"),
        )
        self.processor_grid = QGridLayout()
        self.processor_grid.setContentsMargins(0, 0, 0, 0)
        self.processor_grid.setHorizontalSpacing(10)
        self.processor_grid.setVerticalSpacing(10)
        self.model_stat = RuntimeStat("Processor", "Checking", "kernel model name")
        self.architecture_stat = RuntimeStat("Architecture", "Checking", "vendor / machine")
        self.platform_stat = RuntimeStat("Platform / process", "Checking", "CPU-X-compatible hardware identity")
        self.microcode_stat = RuntimeStat("Microcode", "Checking", "kernel-reported revision")
        self.topology_stat = RuntimeStat("Topology", "Checking", "physical cores / logical threads")
        self.cache_stat = RuntimeStat("Cache hierarchy", "Checking", "L1 / L2 / L3")
        self.features_stat = RuntimeStat("Instruction features", "Checking", "selected acceleration flags")
        self.total_load_stat = RuntimeStat("Total CPU load", "Checking", "average across logical threads")
        self.processor_stats = [
            self.model_stat,
            self.architecture_stat,
            self.platform_stat,
            self.microcode_stat,
            self.topology_stat,
            self.cache_stat,
            self.features_stat,
            self.total_load_stat,
        ]
        self._reflow_processor_stats(1400)
        card.body.addLayout(self.processor_grid)
        return card

    def _build_cores_card(self) -> SectionCard:
        card = SectionCard(
            "Live core monitor",
            "",
            icon_name="compute_blue",
            icon_background=COLORS["blue_soft"],
            status=("Passive", "green"),
            compact=True,
        )
        card.root.setContentsMargins(12, 9, 12, 10)
        card.root.setSpacing(7)
        self.cores_grid = QGridLayout()
        self.cores_grid.setContentsMargins(0, 0, 0, 0)
        self.cores_grid.setHorizontalSpacing(8)
        self.cores_grid.setVerticalSpacing(8)
        self.core_stats = [
            RuntimeStat(
                tr_format("Core {index}", index=index),
                "Checking",
                "logical threads",
                compact=True,
            )
            for index in range(8)
        ]
        for stat in self.core_stats:
            stat.setFixedHeight(PASSIVE_TELEMETRY_TILE_HEIGHT)
            stat.layout().setContentsMargins(9, 6, 9, 6)
            stat.layout().setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._reflow_core_stats(1400)
        card.body.addLayout(self.cores_grid)
        return card

    def _build_runtime_card(self) -> SectionCard:
        card = SectionCard(
            "Runtime status",
            "What will be used for this session and what will happen at the next boot.",
            icon_name="shield_green",
            icon_background=COLORS["green_soft"],
            status=("Session only", "green"),
        )

        stats_panel = QFrame()
        stats_panel.setProperty("compactPanel", True)
        stats_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        stats_panel_layout = QVBoxLayout(stats_panel)
        stats_panel_layout.setContentsMargins(10, 10, 10, 10)
        stats_panel_layout.setSpacing(0)
        self.runtime_stats_grid = QGridLayout()
        self.runtime_stats_grid.setContentsMargins(0, 0, 0, 0)
        self.runtime_stats_grid.setHorizontalSpacing(10)
        self.runtime_stats_grid.setVerticalSpacing(10)

        self.persistence_stat = RuntimeStat("Boot persistence", "Disabled", "Does not start automatically", compact=True)
        self.last_operation_stat = RuntimeStat("Last operation", "None", "No CPU frequency has been applied yet", compact=True)
        self.applied_tuning_stat = RuntimeStat("Applied tuning", "None", "No CPU tuning has been applied yet", compact=True)
        self.detected_scale_stat = RuntimeStat("Detection reference", "Not recorded", "Last bc250-detect result; reference only", compact=True)
        self.live_scale_stat = RuntimeStat("Active scale", "Unknown", "No active scale source detected", compact=True)
        self.live_telemetry_stat = RuntimeStat("Live CPU status", "-- °C | -- MHz", "current temperature and average frequency", compact=True)
        # Stable semantic aliases retained for integrations and older UI tests.
        # The redesigned runtime card replaced the original profile/state tiles,
        # but these values still represent the applied profile and boot state.
        self.profile_stat = self.applied_tuning_stat
        self.state_stat = self.persistence_stat
        self.runtime_stats = [
            self.persistence_stat,
            self.last_operation_stat,
            self.applied_tuning_stat,
            self.detected_scale_stat,
            self.live_scale_stat,
            self.live_telemetry_stat,
        ]
        self._reflow_runtime_stats(1400)
        stats_panel_layout.addLayout(self.runtime_stats_grid)
        card.body.addWidget(stats_panel)

        context_panel = QFrame()
        context_panel.setProperty("compactPanel", True)
        context_layout = QVBoxLayout(context_panel)
        context_layout.setContentsMargins(10, 8, 10, 8)
        context_layout.setSpacing(6)
        self.command_line = StatusLine(
            "Command",
            "bc250-detect --keep",
            "Temporary CPU session action",
            compact=True,
        )
        self.limits_line = StatusLine(
            "UI limits",
            "3100–4200 MHz",
            "950–1325 mV · up to 90 °C",
            compact=True,
        )
        context_layout.addWidget(self.command_line)
        context_layout.addWidget(self.limits_line)
        card.body.addWidget(context_panel)

        controls_panel = QFrame()
        controls_panel.setProperty("compactPanel", True)
        controls_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        controls_layout = QVBoxLayout(controls_panel)
        controls_layout.setContentsMargins(12, 10, 12, 10)
        controls_layout.setSpacing(6)

        self.runtime_actions_grid = QGridLayout()
        self.runtime_actions_grid.setContentsMargins(0, 0, 0, 0)
        self.runtime_actions_grid.setHorizontalSpacing(8)
        self.runtime_actions_grid.setVerticalSpacing(8)
        self.persistence_status_button = QPushButton(tr("Review persistence"))
        self.persistence_status_button.setProperty("compactAction", True)
        self.persistence_status_button.clicked.connect(self.show_persistence_status)

        self.enable_persistence_button = QPushButton(tr("Save for boot"))
        self.enable_persistence_button.setProperty("dangerAction", True)
        self.enable_persistence_button.clicked.connect(self.enable_persistence)

        self.disable_service_button = QPushButton(tr("Remove from boot"))
        self.disable_service_button.setProperty("dangerAction", True)
        self.disable_service_button.clicked.connect(self.disable_persistence)
        self.disable_service_button.setEnabled(False)

        self.details_button = QPushButton(tr("CPU session summary"))
        self.details_button.setProperty("compactAction", True)
        self.details_button.clicked.connect(self._show_runtime_details)

        self.advanced_toggle = QPushButton("Show advanced details")
        self.advanced_toggle.setProperty("compactAction", True)
        self.advanced_toggle.clicked.connect(self._toggle_advanced)

        self.runtime_action_buttons = [
            # Takes the slot the usage-guide toggle occupied; the guide it
            # opened has been removed and this was the action it carried.
            self.prepare_tools_button,
            self.persistence_status_button,
            self.enable_persistence_button,
            self.disable_service_button,
            self.details_button,
            self.advanced_toggle,
        ]
        self._reflow_runtime_actions(1400)
        controls_layout.addLayout(self.runtime_actions_grid)
        card.body.addWidget(controls_panel)

        return card

    def _build_scale_actions_card(self) -> SectionCard:
        card = SectionCard(
            "Temporary apply mode",
            "Start with automatic detection. Manual scale becomes available only after a verified live result.",
            icon_name="info_blue",
            icon_background=COLORS["blue_soft"],
            compact=True,
        )

        scale_panel = QFrame()
        scale_panel.setProperty("compactPanel", True)
        scale_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        scale_layout = QVBoxLayout(scale_panel)
        scale_layout.setContentsMargins(12, 10, 12, 10)
        scale_layout.setSpacing(8)

        scale_header = QHBoxLayout()
        scale_header.setContentsMargins(0, 0, 0, 0)
        scale_header.setSpacing(8)
        self.scale_override_check = QCheckBox(tr("Use manual scale"))
        self.scale_override_check.setChecked(False)
        self.scale_override_check.setEnabled(False)
        self.scale_override_check.setToolTip(
            tr(
                "Run a verified automatic live configuration first. Manual scale unlocks only for that detection session."
            )
        )
        self.scale_override_check.toggled.connect(self._on_scale_override_toggled)
        self.scale_control.setEnabled(False)
        scale_header.addWidget(self.scale_override_check)
        scale_header.addStretch(1)
        self.cpu_quick_guide_button = QPushButton(tr("Step-by-step guide"))
        self.cpu_quick_guide_button.setProperty("compactAction", True)
        self.cpu_quick_guide_button.setIcon(icon("info_blue"))
        self.cpu_quick_guide_button.clicked.connect(self._show_cpu_quick_guide)
        self.cpu_quick_guide_button.hide()
        scale_layout.addLayout(scale_header)

        self.apply_button = QPushButton(tr("Apply configuration + automatic scale"))
        self.apply_button.setObjectName("PrimaryAction")
        self.apply_button.clicked.connect(self._apply_custom)
        self.apply_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        scale_layout.addWidget(self.apply_button)

        self.scale_test_status = QLabel(tr(
            "Apply an automatic live configuration first to unlock manual scale."
        ))
        self.scale_test_status.setProperty("fieldHint", True)
        self.scale_test_status.setWordWrap(True)
        scale_layout.addWidget(self.scale_test_status)
        card.body.addWidget(scale_panel)
        return card

    def _build_core_unlock_card(self) -> SectionCard:
        card = SectionCard(
            "Unlock hidden CPU cores",
            "Experimental, restart-required action for supported BC-250 boards.",
            icon_name="cpu_blue",
            icon_background=COLORS["orange_soft"],
            status=("Checking", "gray"),
        )

        explanation = QLabel(
            "The BC-250 normally exposes 6 cores and 12 threads. This action asks the SMU to expose "
            "the two factory-hidden cores on the next warm restart. A full power-off clears the change."
        )
        explanation.setProperty("fieldHint", True)
        explanation.setWordWrap(True)
        card.body.addWidget(explanation)

        status_panel = QFrame()
        status_panel.setProperty("compactPanel", True)
        status_layout = QVBoxLayout(status_panel)
        status_layout.setContentsMargins(12, 10, 12, 10)
        status_layout.setSpacing(8)
        self.core_shape_line = StatusLine("Detected CPU", "Checking", "Expected stock shape: 6 cores / 12 threads")
        self.core_source_line = StatusLine(
            "Upstream tool",
            "Checking",
            "Official clone: rw-r-r-0644/bc250-core-unlock",
        )
        self.core_helper_line = StatusLine("Unlock support", "Checking", "Privileged local helper")
        self.core_compatibility_line = StatusLine(
            "Governor compatibility",
            "cyan governor will be disabled",
            "Reactivate it manually from GPU after the restart",
        )
        for line in (
            self.core_shape_line,
            self.core_source_line,
            self.core_helper_line,
            self.core_compatibility_line,
        ):
            status_layout.addWidget(line)
        card.body.addWidget(status_panel)

        warning = QLabel(
            "CPU core unlocking is experimental. Continue with caution and save your work before "
            "proceeding, because a restart is required to apply the changes. After unlocking, some "
            "Linux GPU clock sensors may report incorrect values; this is a documented upstream "
            "limitation and does not mean the CPU cores failed to unlock."
        )
        warning.setProperty("warningText", True)
        warning.setWordWrap(True)
        card.body.addWidget(warning)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.firmware_persistence_button = QPushButton()
        self.firmware_persistence_button.setProperty("compactAction", True)
        self.firmware_persistence_button.setIcon(icon("info_blue"))
        self.firmware_persistence_button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.firmware_persistence_button.clicked.connect(self._open_firmware_persistence_guide)
        action_row.addWidget(self.firmware_persistence_button)
        self.core_unlock_button = QPushButton("Unlock cores and restart")
        self.core_unlock_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.core_unlock_button.setProperty("dangerAction", True)
        self.core_unlock_button.clicked.connect(self._request_core_unlock)
        action_row.addWidget(self.core_unlock_button)
        card.body.addLayout(action_row)
        self._retranslate_firmware_persistence_button()
        return card

    def _build_command_context_card(self) -> SectionCard:
        card = SectionCard(
            "Technical context",
            "Current command path and validated limits for this CPU session.",
            icon_name="info_blue",
            icon_background=COLORS["blue_soft"],
            compact=True,
        )
        panel = QFrame()
        panel.setProperty("compactPanel", True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        self.command_line = StatusLine(
            "Command",
            "bc250-detect --keep",
            "Temporary CPU session action",
            compact=True,
        )
        self.limits_line = StatusLine(
            "UI limits",
            "3100–4200 MHz",
            "950–1325 mV · up to 90 °C",
            compact=True,
        )
        layout.addWidget(self.command_line)
        layout.addWidget(self.limits_line)
        card.body.addWidget(panel)
        return card

    def _build_advanced_card(self) -> SectionCard:
        card = SectionCard(
            "Advanced details",
            "Validated command context and the embedded CPU session console.",
            icon_name="logs_gray",
            icon_background="neutral_soft",
        )
        card.add_header_button("Clear console", self._clear_console)

        console_panel = QFrame()
        console_panel.setProperty("compactPanel", True)
        console_layout = QVBoxLayout(console_panel)
        console_layout.setContentsMargins(12, 12, 12, 12)
        console_layout.setSpacing(8)
        console_header = QLabel(tr("Session console"))
        console_header.setProperty("fieldLabel", True)
        console_layout.addWidget(console_header)
        self.console = QPlainTextEdit()
        self.console.setObjectName("OperationConsole")
        self.console.setReadOnly(True)
        self.console.setMinimumHeight(280)
        self.console.setPlainText(tr("CPU / SMU session console ready. No hardware command has been executed."))
        console_layout.addWidget(self.console)

        card.body.addWidget(console_panel)
        self.console_status = card.status
        return card

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reflow(effective_viewport_width(self, self.scroll))

    def _reflow(self, width: int) -> None:
        self._reflow_workspace_tabs(width)
        columns = 2 if width >= 1080 else 1
        column_width = int((width - 14) / 2) if columns == 2 else width
        configuration_width = column_width
        runtime_width = column_width
        self._reflow_presets(configuration_width)
        self._reflow_parameter_fields(configuration_width)
        self._reflow_metric_tiles(width)
        self._reflow_processor_stats(configuration_width)
        self._reflow_core_stats(width)
        self._reflow_runtime_stats(runtime_width)
        self._reflow_runtime_actions(runtime_width)

        if columns != self._workspace_columns or not self.workspace.count():
            self._workspace_columns = columns
            self._clear_grid(self.workspace)
            self.workspace.setColumnStretch(0, 0)
            self.workspace.setColumnStretch(1, 0)
            self._reset_row_stretches(self.workspace, 5)
            if columns == 2:
                self.workspace.addWidget(self.processor_card, 0, 0)
                self.workspace.addWidget(self.core_unlock_card, 0, 1)
                self.workspace.addWidget(self.metrics_card, 1, 0, 1, 2)
                self.workspace.addWidget(self.cores_card, 2, 0, 1, 2)
                self.workspace.setColumnStretch(0, 1)
                self.workspace.setColumnStretch(1, 1)
                self.workspace.setRowStretch(3, 1)
            else:
                self.workspace.addWidget(
                    self.processor_card,
                    0,
                    0,
                    Qt.AlignmentFlag.AlignTop,
                )
                self.workspace.addWidget(
                    self.metrics_card,
                    1,
                    0,
                    Qt.AlignmentFlag.AlignTop,
                )
                self.workspace.addWidget(
                    self.core_unlock_card,
                    2,
                    0,
                    Qt.AlignmentFlag.AlignTop,
                )
                self.workspace.addWidget(
                    self.cores_card,
                    3,
                    0,
                    Qt.AlignmentFlag.AlignTop,
                )
                self.workspace.setColumnStretch(0, 1)
                self.workspace.setRowStretch(4, 1)

        if (
            columns != self._configuration_columns
            or not self.configuration_workspace.count()
        ):
            self._configuration_columns = columns
            self._clear_grid(self.configuration_workspace)
            self.configuration_workspace.setColumnStretch(0, 0)
            self.configuration_workspace.setColumnStretch(1, 0)
            self._reset_row_stretches(self.configuration_workspace, 4)
            if columns == 2:
                self.configuration_workspace.addWidget(
                    self.configuration_left_column,
                    0,
                    0,
                )
                self.configuration_workspace.addWidget(
                    self.runtime_card,
                    0,
                    1,
                )
                self.configuration_workspace.addWidget(self.advanced_card, 1, 0, 1, 2)
                self.configuration_workspace.setColumnStretch(0, 1)
                self.configuration_workspace.setColumnStretch(1, 1)
                self.configuration_workspace.setRowStretch(2, 1)
            else:
                self.configuration_workspace.addWidget(
                    self.configuration_left_column,
                    0,
                    0,
                    Qt.AlignmentFlag.AlignTop,
                )
                self.configuration_workspace.addWidget(
                    self.runtime_card,
                    1,
                    0,
                    Qt.AlignmentFlag.AlignTop,
                )
                self.configuration_workspace.addWidget(
                    self.advanced_card,
                    2,
                    0,
                    Qt.AlignmentFlag.AlignTop,
                )
                self.configuration_workspace.setColumnStretch(0, 1)
                self.configuration_workspace.setRowStretch(3, 1)

    def _reflow_workspace_tabs(self, width: int) -> None:
        columns = 2 if width >= 420 else 1
        if columns == self._workspace_tab_columns and self.workspace_tabs_layout.count():
            return
        self._workspace_tab_columns = columns
        self._clear_grid(self.workspace_tabs_layout)
        for index, button in enumerate(self.workspace_tab_buttons.values()):
            self.workspace_tabs_layout.addWidget(button, index // columns, index % columns)
        for column in range(columns):
            self.workspace_tabs_layout.setColumnStretch(column, 1)

    def _reflow_presets(self, width: int) -> None:
        columns = 4 if width >= 1200 else 2 if width >= 620 else 1
        if columns == getattr(self, "_preset_columns", 0) and self.preset_grid.count():
            return
        self._preset_columns = columns
        self._clear_grid(self.preset_grid)
        for index, button in enumerate(self.preset_buttons):
            self.preset_grid.addWidget(button, index // columns, index % columns)
        for column in range(columns):
            self.preset_grid.setColumnStretch(column, 1)

    def _reflow_parameter_fields(self, width: int) -> None:
        columns = 2 if width >= 680 else 1
        if columns == self._field_columns and self.parameter_grid.count():
            return
        self._field_columns = columns
        self._clear_grid(self.parameter_grid)
        for index, field in enumerate(self.parameter_fields):
            self.parameter_grid.addWidget(field, index // columns, index % columns)
        for column in range(columns):
            self.parameter_grid.setColumnStretch(column, 1)

    def _reflow_metric_tiles(self, width: int) -> None:
        columns = 4 if width >= 860 else 2 if width >= 430 else 1
        if columns == self._metric_columns and self.metrics_grid.count():
            return
        self._metric_columns = columns
        self._clear_grid(self.metrics_grid)
        for index, tile in enumerate(self.metric_tiles):
            self.metrics_grid.addWidget(tile, index // columns, index % columns)
        for column in range(columns):
            self.metrics_grid.setColumnStretch(column, 1)

    def _reflow_processor_stats(self, width: int) -> None:
        columns = 2 if width >= 700 else 1
        if columns == self._processor_columns and self.processor_grid.count():
            return
        self._processor_columns = columns
        self._clear_grid(self.processor_grid)
        for index, stat in enumerate(self.processor_stats):
            self.processor_grid.addWidget(stat, index // columns, index % columns)
        for column in range(columns):
            self.processor_grid.setColumnStretch(column, 1)

    def _reflow_core_stats(self, width: int) -> None:
        columns = 8 if width >= 1080 else 4 if width >= 560 else 2 if width >= 360 else 1
        if columns == self._core_columns and self.cores_grid.count():
            return
        self._core_columns = columns
        self._clear_grid(self.cores_grid)
        for index, stat in enumerate(self.core_stats):
            self.cores_grid.addWidget(stat, index // columns, index % columns)
        for column in range(columns):
            self.cores_grid.setColumnStretch(column, 1)

    def _reflow_runtime_stats(self, width: int) -> None:
        columns = 3 if width >= 760 else 2 if width >= 480 else 1
        if columns == self._runtime_columns and self.runtime_stats_grid.count():
            return
        self._runtime_columns = columns
        self._clear_grid(self.runtime_stats_grid)
        for index, stat in enumerate(self.runtime_stats):
            self.runtime_stats_grid.addWidget(stat, index // columns, index % columns)
        for column in range(columns):
            self.runtime_stats_grid.setColumnStretch(column, 1)

    def _reflow_runtime_actions(self, width: int) -> None:
        columns = 2 if width >= 520 else 1
        if columns == self._runtime_action_columns and self.runtime_actions_grid.count():
            return
        self._runtime_action_columns = columns
        self._clear_grid(self.runtime_actions_grid)
        for index, button in enumerate(self.runtime_action_buttons):
            self.runtime_actions_grid.addWidget(button, index // columns, index % columns)
        for column in range(columns):
            self.runtime_actions_grid.setColumnStretch(column, 1)

    @staticmethod
    def _clear_grid(layout: QGridLayout) -> None:
        clear_grid(layout)

    @staticmethod
    def _reset_row_stretches(layout: QGridLayout, count: int) -> None:
        for row in range(count):
            layout.setRowStretch(row, 0)

    def _on_parameter_changed(self) -> None:
        if self._syncing_active_config:
            return
        frequency = self.frequency_control.value()
        vid = self.vid_control.value()
        temperature = self.temperature_control.value()
        profile = self._profile_name_for_values(frequency, vid, temperature)
        if profile:
            self._selected_profile_name = profile
            self._check_preset_button(profile)
        else:
            self._selected_profile_name = "Custom"
            self._clear_preset_checks()
        self._update_staged_target()

    def _on_scale_override_toggled(self, checked: bool) -> None:
        if checked and not self._manual_scale_available:
            self.scale_override_check.blockSignals(True)
            self.scale_override_check.setChecked(False)
            self.scale_override_check.blockSignals(False)
            self.scale_control.setEnabled(False)
            self.vid_control.setEnabled(True)
            self.apply_button.setText(tr("Apply configuration + automatic scale"))
            self.scale_test_status.setText(tr(
                "Apply an automatic live configuration first to unlock manual scale."
            ))
            return
        # Never shrink the validator around an old detection result. A dynamic
        # QIntValidator can silently leave/clamp stale text and was the source
        # of the confusing "typed -30, applied -33" behavior. Keep the real
        # upstream scale domain visible and validate risk explicitly instead.
        self.scale_control.setRange(-50, 0)
        self.scale_control.setEnabled(bool(checked))
        self.vid_control.setEnabled(not bool(checked))
        if checked:
            self.apply_button.setText(tr("Apply temporary OC + manual scale"))
            self.scale_test_status.setText(tr(
                "Manual mode applies frequency, temperature, and the exact scale entered above. The VID limit is not used and boot persistence remains unchanged."
            ))
        else:
            self.apply_button.setText(tr("Apply configuration + automatic scale"))
            self.scale_test_status.setText(tr(
                "Automatic mode runs bc250-detect with the selected frequency, VID limit, and temperature."
            ))
        if not self._syncing_active_config:
            self._update_staged_target()

    def _set_manual_scale_available(self, available: bool) -> None:
        """Expose manual scale only after a verified detector run this boot."""
        self._manual_scale_available = bool(available)
        running = self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning
        if not self._manual_scale_available:
            if self.scale_override_check.isChecked():
                self.scale_override_check.setChecked(False)
            self.scale_override_check.setEnabled(False)
            self.scale_control.setEnabled(False)
            self.vid_control.setEnabled(not running)
            self.scale_override_check.setToolTip(tr(
                "Run a verified automatic live configuration first. Manual scale unlocks only for that detection session."
            ))
            self.scale_test_status.setText(tr(
                "Apply an automatic live configuration first to unlock manual scale."
            ))
            return

        self.scale_override_check.setEnabled(not running)
        self.scale_override_check.setToolTip(tr(
            "Automatic live configuration verified. You can now test an exact manual scale for this session."
        ))
        if not self.scale_override_check.isChecked():
            self.scale_control.setEnabled(False)
            self.vid_control.setEnabled(not running)
            self.scale_test_status.setText(tr(
                "Automatic live configuration verified. Manual scale is now available."
            ))

    def _profile_name_for_values(self, frequency: int, vid: int, temperature: int) -> str:
        for name, _summary, payload in self.PROFILE_VALUES:
            if payload == (frequency, vid, temperature):
                return name
        return ""

    def _check_preset_button(self, profile_name: str) -> None:
        for button, (title, _summary, _payload) in zip(self.preset_buttons, self.PROFILE_VALUES):
            if title == profile_name:
                if not button.isChecked():
                    button.setChecked(True)
                return

    def _clear_preset_checks(self) -> None:
        self.preset_group.setExclusive(False)
        for button in self.preset_buttons:
            button.setChecked(False)
        self.preset_group.setExclusive(True)

    def _select_preset(self, button: PresetButton) -> None:
        frequency, vid, temperature = button.payload
        self._selected_profile_name = button.text().split("\n", 1)[0]
        self.frequency_control.setValue(int(frequency))
        self.vid_control.setValue(int(vid))
        self.temperature_control.setValue(int(temperature))
        self._update_staged_target()

    def _update_staged_target(self) -> None:
        frequency = self.frequency_control.value()
        vid = self.vid_control.value()
        temperature = self.temperature_control.value()
        target_value = f"{frequency} MHz / {vid} mV"
        self.summary_strip.items[2].set_values(target_value, tr_format("temperature cap {temperature} °C", temperature=temperature))

    def _apply_custom(self) -> None:
        frequency = self.frequency_control.value()
        vid = self.vid_control.value()
        temperature = self.temperature_control.value()
        if not (CPU_FREQUENCY_RANGE[0] <= frequency <= CPU_FREQUENCY_RANGE[1]):
            self._show_info(
                "Invalid CPU frequency",
                tr_format("Enter a value between {minimum} and {maximum} MHz.", minimum=CPU_FREQUENCY_RANGE[0], maximum=CPU_FREQUENCY_RANGE[1]),
                tone="orange",
            )
            return
        manual_scale = self.scale_override_check.isChecked()
        if not manual_scale and not (CPU_VID_RANGE[0] <= vid <= CPU_VID_RANGE[1]):
            self._show_info(
                "Invalid CPU VID",
                tr_format("Enter a value between {minimum} and {maximum} mV.", minimum=CPU_VID_RANGE[0], maximum=CPU_VID_RANGE[1]),
                tone="orange",
            )
            return
        if not (CPU_TEMPERATURE_RANGE[0] <= temperature <= CPU_TEMPERATURE_RANGE[1]):
            self._show_info(
                "Invalid temperature limit",
                tr_format("Enter a value between {minimum} and {maximum} °C.", minimum=CPU_TEMPERATURE_RANGE[0], maximum=CPU_TEMPERATURE_RANGE[1]),
                tone="orange",
            )
            return
        if manual_scale:
            scale = self.scale_control.value()
            if not -50 <= scale <= 0:
                self._show_info(
                    "Invalid CPU scale",
                    "Enter a scale between -50 and 0.",
                    tone="orange",
                )
                return
            self._request_manual_apply(frequency, scale, temperature)
        else:
            self._request_apply(frequency, vid, temperature)

    def _build_and_start_process(self, operation, label: str, error_title: str) -> None:
        self._command_build_pending = True
        self._set_running(True)

        def success(payload: object) -> None:
            self._command_build_pending = False
            command = list(payload or [])
            if not command:
                self._pending_cpu_target = None
                self._pending_live_scale = None
                self._pending_live_frequency = None
                self._pending_live_temperature = None
                self._pending_manual_direct = False
                self._set_running(False, success=False)
                self._show_info(error_title, "The controller returned an empty command.", tone="red")
                return
            self._start_process(command, label)

        def failure(message: str) -> None:
            self._command_build_pending = False
            self._pending_cpu_target = None
            self._pending_live_scale = None
            self._pending_live_frequency = None
            self._pending_live_temperature = None
            self._pending_manual_direct = False
            self._set_running(False, success=False)
            self._show_info(error_title, message, tone="red")

        if not self._background.start("cpu-command-build", operation, success, failure):
            self._command_build_pending = False
            self._pending_cpu_target = None
            self._pending_live_scale = None
            self._pending_live_frequency = None
            self._pending_live_temperature = None
            self._pending_manual_direct = False
            self._set_running(False, success=False)
            self._show_info("CPU operation in progress", "Wait for the current CPU operation to finish.", tone="orange")

    def _request_apply(self, frequency: int, vid: int, temperature: int) -> None:
        if self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning:
            self._show_info(
                "CPU operation in progress",
                "Wait for the current process to finish before applying another profile.",
                tone="orange",
            )
            return
        dialog = ConfirmDialog(
            "Apply temporary CPU / SMU session",
            "This operation may freeze or reset the board when the frequency and VID do not match your silicon. "
            "Save open work and stop immediately if visual artifacts appear.",
            summary=(
                ("Frequency", f"{frequency} MHz"),
                ("VID", f"{vid} mV"),
                ("Temperature limit", f"{temperature} °C"),
                ("Persistence", "Temporary — bc250-detect --keep"),
            ),
            confirm_text="Authenticate and apply",
            tone="orange",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._pending_cpu_target = {
            "frequency": int(frequency),
            "vid": int(vid),
            "temperature": int(temperature),
        }
        self._pending_manual_direct = False
        self._build_and_start_process(
            lambda: self.controller.comando_cpu_oc_temporal_embebido(frequency, vid, temperature),
            f"CPU {frequency} MHz / {vid} mV / {temperature} °C",
            "CPU profile rejected",
        )

    def _request_manual_apply(self, frequency: int, scale: int, temperature: int) -> None:
        if self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning:
            self._show_info(
                "CPU operation in progress",
                "Wait for the current process to finish before applying another profile.",
                tone="orange",
            )
            return
        try:
            analysis = _dict(
                self.controller.evaluar_aplicacion_manual_cpu(
                    frequency, scale, temperature
                )
            )
        except Exception as exc:
            self._show_info("Unsafe manual CPU configuration", str(exc), tone="red")
            return
        estimated_vid = analysis.get("estimated_vid")
        dialog = ConfirmDialog(
            "Apply temporary CPU OC with manual scale",
            "This bypasses automatic scale detection and applies the exact frequency and scale shown below. "
            "An unstable value can freeze or reset the board. Save open work before continuing.",
            summary=(
                ("Frequency", f"{frequency} MHz"),
                ("Manual scale", str(scale)),
                ("Estimated VID", f"~{estimated_vid} mV" if estimated_vid is not None else "Not available"),
                ("Temperature limit", f"{temperature} °C"),
                ("Persistence", "Temporary now — boot saving requires valid detector evidence"),
            ),
            confirm_text="Authenticate and apply manual OC",
            tone="red",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._pending_cpu_target = None
        self._pending_live_scale = int(scale)
        self._pending_live_frequency = int(frequency)
        self._pending_live_temperature = int(temperature)
        self._pending_manual_direct = True
        self._build_and_start_process(
            lambda: self.controller.comando_cpu_oc_manual_embebido(
                frequency, scale, temperature, True
            ),
            f"Manual CPU OC {frequency} MHz / scale {scale} / {temperature} °C",
            "Manual CPU configuration rejected",
        )

    def test_scale_live(self) -> None:
        if self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning:
            self._show_info(
                "CPU operation in progress",
                "Wait for the current process to finish before testing another CPU scale.",
                tone="orange",
            )
            return
        if not self.scale_override_check.isChecked():
            self._show_info(
                "Manual scale test is disabled",
                "Enable 'Test a manual scale after bc250-detect' first.",
                tone="orange",
            )
            return
        requested = self.scale_control.value()
        requested_frequency = self.frequency_control.value()
        requested_temperature = self.temperature_control.value()
        try:
            analysis = _dict(self.controller.evaluar_override_escala_cpu(
                requested, requested_frequency
            ))
        except Exception as exc:
            self._show_info("Unsafe CPU scale test", str(exc), tone="red")
            return

        reference = int(analysis.get("reference_scale", requested))
        requested_vid = analysis.get("requested_estimated_vid")
        reference_vid = analysis.get("reference_estimated_vid")
        delta_vid = analysis.get("estimated_vid_delta")
        delta_steps = int(analysis.get("delta_steps", 0))
        direction = (
            tr("less negative — estimated voltage increases")
            if delta_steps > 0
            else tr("more negative — estimated voltage decreases")
            if delta_steps < 0
            else tr("same as detected")
        )
        tone = "red" if analysis.get("requires_extreme_confirmation") else "orange"
        dialog = ConfirmDialog(
            "Test CPU scale live",
            "This applies the selected scale to the current session without changing boot persistence. "
            "Scale is a voltage-curve offset, not millivolts. A less-negative value generally raises voltage. "
            "The VID shown here is only the upstream curve estimate; monitor the real sensor and stop if the board becomes unstable.",
            summary=(
                ("Detected reference", f"scale {reference} · ~{reference_vid} mV estimated"),
                ("Live candidate", f"{requested_frequency} MHz · scale {requested} · ~{requested_vid} mV estimated"),
                ("Temperature limit", f"{requested_temperature} °C"),
                ("Difference", f"{delta_steps:+d} scale steps · {int(delta_vid or 0):+d} mV estimated"),
                ("Direction", direction),
                ("Persistence", "Unchanged — live session only"),
            ),
            confirm_text="Authenticate and test live",
            tone=tone,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._pending_live_scale = int(requested)
        self._pending_live_frequency = int(requested_frequency)
        self._pending_live_temperature = int(requested_temperature)
        self._pending_manual_direct = False
        self._build_and_start_process(
            lambda: self.controller.comando_cpu_scale_live_embebido(
                requested,
                bool(analysis.get("requires_extra_confirmation")),
                requested_frequency,
                requested_temperature,
            ),
            f"Live CPU test {requested_frequency} MHz / scale {requested}",
            "CPU scale test rejected",
        )

    def prepare_tools(self) -> None:
        self.prepare_tools_button.setEnabled(False)

        def success(result: object) -> None:
            self._append_console(
                tr("bc250_smu_oc is already available." if result is True else "Opened the existing R64 CPU tool preparation workflow.")
            )
            self._last_operation_summary = "CPU tool preparation workflow completed."
            self._state_cache.invalidate("tools", "cpu_persistence")
            self.refresh()

        def failure(message: str) -> None:
            self._show_info("Could not prepare CPU tools", message, tone="red")

        def finished() -> None:
            self.prepare_tools_button.setEnabled(True)

        if not self._background.start("cpu-tool-preparation", self.controller.instalar_cpu_oc, success, failure, finished):
            self.prepare_tools_button.setEnabled(True)

    def show_persistence_status(self) -> None:
        """Write the full systemd persistence status to the embedded console."""
        self.persistence_status_button.setEnabled(False)

        def success(payload: object) -> None:
            state = _dict(payload)
            service = str(state.get("service") or "bc250-smu-oc.service")
            enabled = str(state.get("enabled") or "unknown")
            active = str(state.get("active_state") or state.get("active") or "unknown")
            sub_state = str(state.get("sub_state") or "unknown")
            result = str(state.get("result") or "unknown")
            config = tr("present" if state.get("config_exists") else "not installed")
            status_text = str(state.get("status_text") or "No systemctl status output was returned.").rstrip()
            # Composed once, delivered once. Assembling the report here rather
            # than appending it line by line lets the embedded terminal show
            # it as a single readable block instead of eight separate writes.
            report = "\n".join((
                f"[{datetime.now().strftime('%H:%M:%S')}] Persistence status",
                tr_format("Service: {value}", value=service),
                tr_format("Enabled: {value}", value=enabled),
                tr_format("Active: {active} ({sub_state})", active=active, sub_state=sub_state),
                tr_format("Result: {value}", value=result),
                tr_format("Config: {value}", value=config),
                "",
                "--- systemctl status ---",
                status_text,
            ))
            self._report_persistence(report)
            self._last_operation_summary = "Persistence status read without changing the service."
            self.refresh()

        def failure(message: str) -> None:
            self._show_info("Could not read persistence status", message, tone="red")

        def finished() -> None:
            self.persistence_status_button.setEnabled(True)

        if not self._background.start("cpu-persistence-status", self._state_cache.cpu_persistence, success, failure, finished):
            self.persistence_status_button.setEnabled(True)

    def enable_persistence(self) -> None:
        if self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning:
            self._show_info(
                "CPU operation in progress",
                "Wait for the current process to finish before changing CPU persistence.",
                tone="orange",
            )
            return
        try:
            detection_state = _dict(self.controller.estado_resultado_deteccion_cpu())
        except Exception as exc:
            self._show_info(
                "CPU detection result unavailable",
                str(exc),
                tone="red",
            )
            return
        blocker = validate_detection_for_persistence(detection_state)
        if blocker is not None:
            self._show_persistence_blocker(blocker)
            return

        scale_override = self.scale_control.value() if self.scale_override_check.isChecked() else None
        scale_analysis = {}
        live_state = {}
        candidate_frequency = self.frequency_control.value()
        candidate_temperature = self.temperature_control.value()
        if scale_override is not None:
            try:
                scale_analysis = _dict(self.controller.evaluar_override_escala_cpu(
                    scale_override, candidate_frequency
                ))
                prepare_evidence = getattr(
                    self.controller,
                    "preparar_evidencia_persistencia_escala_cpu",
                    self.controller.estado_prueba_escala_cpu,
                )
                live_state = _dict(prepare_evidence(
                    scale_override, candidate_frequency, candidate_temperature
                ))
            except Exception as exc:
                self._show_info("Unsafe CPU scale override", str(exc), tone="red")
                return
        else:
            # Without this the dialog could only describe the detector result,
            # even while the processor was running a manual scale the rules
            # will not install. Read-only: it records nothing.
            try:
                live_state = _dict(self.controller.estado_prueba_escala_cpu())
            except Exception:
                live_state = {}
        plan = plan_cpu_persistence(
            detection_state,
            scale_override=scale_override,
            candidate_frequency=candidate_frequency,
            candidate_temperature=candidate_temperature,
            scale_analysis=scale_analysis,
            live_state=live_state,
        )
        if isinstance(plan, PersistenceBlocker):
            self._show_persistence_blocker(plan)
            return
        self._confirm_cpu_persistence(plan)

    def _report_persistence(self, report: str) -> None:
        """Show a persistence report in the session console.

        The console is part of the workspace now, so the report only has to be
        written: there is no card left to unfold before the user can read it.
        """
        self._select_workspace("configuration")
        self._append_console(f"\n{report}")

    def _show_persistence_blocker(self, blocker: PersistenceBlocker) -> None:
        self._show_info(blocker.title, blocker.message, tone=blocker.tone)

    def _confirm_cpu_persistence(self, plan: CpuPersistencePlan) -> None:
        # Only rows that say something different. In automatic mode the
        # detected result and the boot candidate are the same string, and the
        # scale line repeats what both already end with; three rows of the
        # same number teach the reader to skip the table.
        summary = [("Detection source", self._render_cpu_text(plan.detection_source))]
        if plan.detected_result != plan.boot_candidate:
            summary.append(("Detected result", plan.detected_result))
        summary.append(("Boot candidate", plan.boot_candidate))
        if plan.active_scale:
            # Right under the candidate: the two numbers being different is
            # the whole reason this row exists.
            summary.append(("Active scale", plan.active_scale))
        summary.append(
            ("Validation source", self._render_cpu_text(plan.validation_source))
        )
        if plan.scale_override is not None:
            summary.append(("Scale", self._render_cpu_text(plan.scale_summary)))
        summary.append(("Service", "bc250-smu-oc.service"))
        dialog = ConfirmDialog(
            "Enable persistent CPU overclock",
            "This enables the exact CPU configuration shown below at boot. "
            "The detector result remains unchanged; a manual scale is installed only when that exact value was previously applied live against the same detection run. "
            "A successful live apply does not prove long-term stability, so continue only after testing this exact configuration with your real workload.",
            summary=summary,
            notice=(
                self._render_cpu_text(plan.live_notice)
                if plan.live_notice is not None
                else ""
            ),
            confirm_text="Install exact tested candidate",
            tone="red",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._build_and_start_process(
            lambda: self.controller.comando_cpu_oc_persistente_embebido(
                plan.scale_override,
                plan.confirm_scale_jump,
                plan.command_frequency,
                plan.command_temperature,
            ),
            "Enable / update CPU persistence",
            "Could not enable CPU persistence",
        )

    def disable_persistence(self) -> None:
        dialog = ConfirmDialog(
            "Disable CPU boot service",
            "This stops and disables bc250-smu-oc.service. The existing configuration file is preserved for inspection.",
            summary=(("Service", "bc250-smu-oc.service"), ("Result", "Disabled now and at next boot")),
            confirm_text="Disable service",
            tone="orange",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._build_and_start_process(
            self.controller.comando_cpu_oc_desactivar_persistente_embebido,
            "Disable CPU boot service",
            "Could not build service command",
        )

    def _request_core_unlock(self) -> None:
        if (
            getattr(self, "_command_build_pending", False)
            or (
                self.process is not None
                and self.process.state() != QProcess.ProcessState.NotRunning
            )
        ):
            self._show_info(
                "CPU operation in progress",
                "Wait for the current CPU operation to finish before unlocking cores.",
                tone="orange",
            )
            return
        if not self.current_state.get("core_unlock_repository_ready", False):
            self._show_info(
                "Official CPU core unlock tool is not prepared",
                "Use Prepare dependencies to clone and validate the official rw-r-r-0644/bc250-core-unlock repository, then refresh this page.",
                tone="orange",
            )
            return
        if not self.current_state.get("core_unlock_helper_ready", False):
            self._show_info(
                "CPU core unlock support is not installed",
                "The BC250 Control Center package currently installed on this system does not include "
                "the privileged core-unlock helper. Rebuild and reinstall the local application package, "
                "then reopen the application.",
                tone="orange",
            )
            return
        dialog = ConfirmDialog(
            "Unlock CPU cores and restart",
            "CPU core unlocking is experimental. Continue with caution and save your work before "
            "proceeding, because a restart is required to apply the changes. For compatibility, "
            "the selected GPU frequency governor will be stopped and disabled before that restart.",
            summary=(
                ("Restart", "Required immediately"),
                ("CPU after restart", "Expected: 8 cores / 16 threads"),
                ("GPU governor", "Disabled for the next startup"),
                ("GPU clock sensors", "Cyan fix-freq remains ready if it was prepared beforehand"),
                ("After restart", "Enable the GPU governor; run Prepare everything only if Cyan was never prepared"),
            ),
            confirm_text="Restart",
            tone="red",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._build_and_start_process(
            self.controller.comando_desbloquear_nucleos_cpu,
            "Unlock CPU cores and restart",
            "Could not start CPU core unlock",
        )

    def _retranslate_firmware_persistence_button(self) -> None:
        from ..i18n import firmware_persistence_label

        label = firmware_persistence_label()
        self.firmware_persistence_button.setText(label)
        self.firmware_persistence_button.setToolTip(label)

    def retranslate_dynamic_copy(self) -> None:
        self._retranslate_firmware_persistence_button()

    def _open_firmware_persistence_guide(self) -> None:
        """Open the external UEFI workflow; never execute firmware actions here."""
        url = "https://github.com/Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script"
        dialog = InfoDialog(
            "Firmware persistence guide",
            "Firmware-level persistence requires the external UEFI menu workflow. The guide opens in your browser; this application does not flash firmware, change NVRAM, or reboot the system.",
            "info_blue",
            self,
            eyebrow="EXTERNAL FIRMWARE GUIDE",
            button_text="Open guide",
            notice="Only continue if you understand the firmware recovery requirements and have a backup boot option.",
            tone="orange",
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        opened, message = open_external_url(url)
        if not opened:
            self._show_info(
                "Firmware guide could not be opened",
                tr_format("{url}: {error}", url=url, error=tr(message)),
                tone="orange",
            )

    def _show_cpu_quick_guide(self) -> None:
        InfoDialog(
            "CPU / SMU quick guide",
            "1. Prepare dependencies only once, or when a required tool is missing.\n\n2. Choose a preset or enter frequency, VID limit, and temperature cap.\n\n3. Leave Use manual scale disabled to run automatic detection. The official detector uses 12 CPU workers and about 10 seconds per frequency step to find a candidate and catch immediate throttling.\n\n4. Treat the detected result as a starting candidate, not proof of long-term stability. The detector may choose a lower frequency than the requested target.\n\n5. Enable Use manual scale only to compare an exact scale live in the current session. VID is ignored in this mode, and the change is not saved for boot.\n\n6. Validate the exact candidate with variable CPU and memory load, a sustained CPU test, and your real games or workloads. Watch temperature, clock drops, calculation errors, freezes, and restarts.\n\n7. Save for boot only after those checks pass. Remove from boot disables automatic application at startup.",
            "info_blue",
            self,
            eyebrow="CPU / SMU",
            button_text="Close",
            notice="This guide only explains the workflow. It does not change hardware state.",
            tone="blue",
        ).exec()

    def _show_runtime_details(self) -> None:
        summary = present_cpu_session_summary(
            dict(self.current_state or {}),
            last_applied_frequency=self._last_applied_frequency,
        )

        message = "\n\n".join((
            tr_format("Live now: {value}", value=self._render_cpu_text(summary.live_now)),
            tr_format("Last applied frequency: {value}", value=self._render_cpu_text(summary.last_applied)),
            tr_format("Automatic detection: {value}", value=self._render_cpu_text(summary.automatic_detection)),
            tr_format("Manual live test: {value}", value=self._render_cpu_text(summary.manual_live_test)),
            tr_format("Next boot: {value}", value=self._render_cpu_text(summary.next_boot)),
            tr_format("Recommended next step: {value}", value=self._render_cpu_text(summary.recommended_next_step)),
        ))
        InfoDialog(
            "CPU session summary",
            message,
            icon_name="info_blue",
            parent=self,
            eyebrow="CPU / SMU",
            button_text="Close",
            notice="This summary compares the live session, the detected reference, and the boot configuration. It does not change hardware state.",
            tone="blue",
        ).exec()

    def _toggle_advanced(self) -> None:
        visible = self.advanced_card.isHidden()
        if visible:
            self._select_workspace("configuration")
        self.advanced_card.setVisible(visible)
        self.advanced_toggle.setText(tr("Hide advanced details" if visible else "Show advanced details"))
        if self.advanced_card.status is not None:
            if visible:
                current = self.console_status.text() if self.console_status is not None else tr("Visible")
                tone = "green" if current == "Completed" else "orange" if current == "Running" else "gray"
                self.advanced_card.status.setText(current)
                self.advanced_card.status.set_tone(tone)
            else:
                self.advanced_card.status.setText("Hidden")
                self.advanced_card.status.set_tone("gray")

    def _start_process(self, command: list[str], operation: str) -> None:
        if not command:
            self._show_info("Invalid command", "The R64 controller returned an empty command.", tone="red")
            return
        self.process = QProcess(self)
        self._last_stderr = ""
        self._operation = operation
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self.process.readyReadStandardOutput.connect(self._read_stdout)
        self.process.readyReadStandardError.connect(self._read_stderr)
        self.process.finished.connect(self._process_finished)
        self.process.errorOccurred.connect(self._process_error)
        self._set_running(True)
        self._last_operation_summary = tr_format("Started at {time}", time=datetime.now().strftime("%H:%M:%S"))
        self._select_workspace("configuration")
        if self.advanced_card.isHidden():
            self._toggle_advanced()
        self._append_console(tr_format("\n[{time}] Starting: {operation}", time=datetime.now().strftime("%H:%M:%S"), operation=operation))
        self._append_console(tr("Command source: existing R64 controller and repository validation"))
        self.process.start(command[0], command[1:])

    def _read_stdout(self) -> None:
        if self.process is None:
            return
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if data:
            self.console.moveCursor(QTextCursor.MoveOperation.End)
            self.console.insertPlainText(data)
            self.console.ensureCursorVisible()

    def _read_stderr(self) -> None:
        if self.process is None:
            return
        data = bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace")
        if data:
            # Keep the tail as evidence for the diagnosis built on exit.
            self._last_stderr = (self._last_stderr + data)[-4000:]
            self._append_console(data.rstrip())

    def _process_finished(self, exit_code: int, _status) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        if exit_code == 0:
            # A successful run is not a diagnosis; reporting a number here was
            # what made a good result read like a fault ("finished with code 0").
            self._append_console(f"[{stamp}] " + tr("Completed"))
            self._last_operation_summary = tr("Completed")
        else:
            diagnosis = diagnose_error(
                describe_failure(exit_code, "", self._last_stderr),
                context="CPU SMU",
            )
            # Composed from already-catalogued phrases so a diagnosis never
            # introduces a new translation key per message shape.
            self._append_console(f"[{stamp}] " + tr(diagnosis.summary))
            self._append_console(tr("How to fix it") + ": " + tr(diagnosis.action))
            self._append_console(tr("Diagnostic code") + ": " + diagnosis.code)
            self._last_operation_summary = f"{tr(diagnosis.summary)} [{diagnosis.code}]"
        self._set_running(False, success=exit_code == 0)
        if exit_code == 0:
            operation_name = self._operation
            cpu_target = dict(self._pending_cpu_target or {})
            live_scale = self._pending_live_scale
            live_frequency = self._pending_live_frequency
            live_temperature = self._pending_live_temperature
            manual_direct = self._pending_manual_direct
            applied_frequency = None
            if live_scale is not None:
                applied_frequency = int(self.frequency_control.value())

            def remember_applied_frequency(frequency: int | None) -> None:
                if frequency is None:
                    return
                self._last_applied_frequency = frequency
                self._last_operation_summary = tr_format("Latest applied CPU frequency from {operation}: {frequency} MHz", operation=operation_name or tr("CPU operation"), frequency=frequency)
                try:
                    if self.settings_service is None:
                        raise RuntimeError("CpuSmuPage requires a settings service to save preferences")
                    self.settings_service.save_local_config({"cpu_oc_last_applied_frequency": frequency})
                except Exception:
                    # The hardware change already succeeded; failing to
                    # remember the number must not interrupt the user. It must
                    # still leave a trace, or preferences can stop saving and
                    # nothing ever says so.
                    logger.debug(
                        "The last applied CPU frequency could not be saved", exc_info=True
                    )

            if applied_frequency is not None:
                remember_applied_frequency(applied_frequency)
            if cpu_target:
                try:
                    snapshot = _dict(self.controller.registrar_resultado_deteccion_cpu(cpu_target))
                    detected_frequency = int(snapshot.get("frequency", 0) or 0) or None
                    # bc250-detect may deliberately return a lower safe clock
                    # than the requested target. Persist and display the
                    # measured result, never the request, as the applied OC.
                    remember_applied_frequency(detected_frequency)
                    detected_scale = int(snapshot.get("scale", self.scale_control.value()))
                    self.scale_override_check.setChecked(False)
                    self._set_manual_scale_available(True)
                    self.scale_control.setRange(-50, 0)
                    self.scale_control.setValue(detected_scale)
                    self.scale_test_status.setText(
                        tr_format(
                            "Detected result {frequency} MHz · scale {scale}. Requested target was {requested} MHz; the detector may choose a lower safe frequency. This exact result is the boot reference; enable manual scale testing only if you want to compare another value live.",
                            frequency=snapshot.get("frequency", "--"),
                            scale=detected_scale,
                            requested=snapshot.get("requested_frequency", cpu_target.get("frequency", "--")),
                        )
                    )
                    self._append_console(
                        tr_format(
                            "Recorded detection run: {frequency} MHz | scale {scale} | {temperature} °C",
                            frequency=snapshot.get("frequency", "--"),
                            scale=snapshot.get("scale", "--"),
                            temperature=snapshot.get("temperature", "--"),
                        )
                    )
                except Exception as exc:
                    self._set_manual_scale_available(False)
                    self._append_console(
                        tr_format(
                            "Warning: the completed detection run could not be bound to persistence: {message}",
                            message=str(exc),
                        )
                    )
            elif live_scale is not None:
                try:
                    if manual_direct:
                        live_state = _dict(
                            self.controller.registrar_aplicacion_manual_cpu(
                                live_frequency, live_scale, live_temperature
                            )
                        )
                        if live_state.get("persistence_eligible"):
                            self.scale_test_status.setText(
                                tr_format(
                                    "Manual OC is active: {frequency} MHz · scale {scale}. The exact live-tested result is ready to save for boot after stability testing.",
                                    frequency=live_state.get("frequency", live_frequency),
                                    scale=live_state.get("scale", live_scale),
                                )
                            )
                        else:
                            self.scale_test_status.setText(
                                tr_format(
                                    "Manual OC is active for this session: {frequency} MHz · scale {scale}. It was not saved for boot.",
                                    frequency=live_state.get("frequency", live_frequency),
                                    scale=live_state.get("scale", live_scale),
                                )
                            )
                    else:
                        live_state = _dict(self.controller.registrar_prueba_escala_cpu(
                            live_scale, live_frequency, live_temperature
                        ))
                        self.scale_test_status.setText(
                            tr_format(
                                "Scale {scale} is applied live for this session (test {test_id}). Use your real workload before enabling it at boot.",
                                scale=live_state.get("scale", live_scale),
                                test_id=live_state.get("test_id", "--"),
                            )
                        )
                    self._append_console(
                        tr_format(
                            "Recorded live scale test: {frequency} MHz | scale {scale} | estimated VID ~{vid} mV | test {test_id}",
                            frequency=live_state.get("frequency", "--"),
                            scale=live_state.get("scale", live_scale),
                            vid=live_state.get("estimated_vid", "--"),
                            test_id=live_state.get("test_id", "--"),
                        )
                    )
                except Exception as exc:
                    self._append_console(
                        tr_format(
                            "Warning: the live scale apply succeeded but its validation record could not be saved: {message}",
                            message=str(exc),
                        )
                    )

            def register_event() -> object:
                if self.activity_service is None:
                    raise RuntimeError("CpuSmuPage requires an activity service to record events")
                self.activity_service.record("cpu", "success", operation_name, "CPU / SMU operation completed")
                if cpu_target:
                    if self.settings_service is None:
                        raise RuntimeError("CpuSmuPage requires a settings service to save preferences")
                    self.settings_service.save_local_config({"cpu_oc_last_target": cpu_target})
                return True

            self._background.start(
                f"cpu-event:{time.monotonic_ns()}",
                register_event,
            )
        self._pending_cpu_target = None
        self._pending_live_scale = None
        self._pending_live_frequency = None
        self._pending_live_temperature = None
        self._pending_manual_direct = False
        self._state_cache.invalidate("performance", "tools", "cpu_persistence")
        self.refresh()

    def _process_error(self, error) -> None:
        if self.process is not None:
            self._append_console(tr_format("Process error: {message} ({code})", message=self.process.errorString(), code=error))
        self._last_operation_summary = tr("Process error occurred. Review the session console output.")
        self._pending_cpu_target = None
        self._pending_live_scale = None
        self._pending_live_frequency = None
        self._pending_live_temperature = None
        self._pending_manual_direct = False
        self._set_running(False, success=False)

    def _set_running(self, running: bool, success: bool | None = None) -> None:
        self.apply_button.setEnabled(not running)
        self.scale_override_check.setEnabled(not running and self._manual_scale_available)
        self.scale_control.setEnabled(
            not running
            and self._manual_scale_available
            and self.scale_override_check.isChecked()
        )
        self.vid_control.setEnabled(not running and not self.scale_override_check.isChecked())
        self.prepare_tools_button.setEnabled(not running)
        self.persistence_status_button.setEnabled(not running)
        self.enable_persistence_button.setEnabled(
            not running and bool(self.current_state.get("persistence_available", True))
        )
        self.core_unlock_button.setEnabled(
            not running
            and not getattr(self, "_command_build_pending", False)
            and self.current_state.get("core_unlock_allowed", False)
        )
        service_enabled = self.disable_service_button.property("serviceEnabled") is True
        self.disable_service_button.setEnabled(not running and service_enabled)
        if self.runtime_card.status is not None:
            if running:
                self.runtime_card.status.setText("Running")
                self.runtime_card.status.set_tone("orange")
            elif success is True:
                self.runtime_card.status.setText("Completed")
                self.runtime_card.status.set_tone("green")
            elif success is False:
                self.runtime_card.status.setText("Failed")
                self.runtime_card.status.set_tone("red")
            else:
                enabled = self.current_state.get("service_enabled", False)
                self.runtime_card.status.setText(tr("Boot enabled" if enabled else "Session only"))
                self.runtime_card.status.set_tone("red" if enabled else "green")

        if self.console_status is not None:
            if running:
                self.console_status.setText("Running")
                self.console_status.set_tone("orange")
            elif success is True:
                self.console_status.setText("Completed")
                self.console_status.set_tone("green")
            elif success is False:
                self.console_status.setText("Failed")
                self.console_status.set_tone("red")
            else:
                if not self.advanced_card.isHidden():
                    self.console_status.setText("Idle")
                    self.console_status.set_tone("gray")
                else:
                    self.console_status.setText("Hidden")
                    self.console_status.set_tone("gray")

    def _manual_refresh(self) -> None:
        self._active_config_signature = None
        self._state_cache.invalidate("performance", "tools", "cpu_persistence")
        self.refresh()

    def set_updates_active(self, active: bool) -> None:
        self._updates_active = bool(active)
        if self._updates_active:
            if not self.timer.isActive():
                self.timer.start()
            self._refresher.activate(fresh_for=2.0)
        else:
            self._refresher.set_active(False)
            self.timer.stop()

    def _fetch_refresh_payload(self) -> dict[str, dict]:
        """Collect CPU status without allowing one source to blank the page.

        These reads come from different subsystems (psutil/sysfs, systemd,
        ResourceTools and the core-unlock helper).  Treating them as one atomic
        operation made a missing optional method freeze every card at
        "Checking".  Return successful sections and annotate only the failed
        ones so passive telemetry remains useful during a partial backend fault.
        """
        loaders = (
            ("performance", self._state_cache.performance),
            ("tools", self._state_cache.tools),
            ("persistent", self._state_cache.cpu_persistence),
            ("detection", self.controller.estado_resultado_deteccion_cpu),
            ("scale_live", self.controller.estado_prueba_escala_cpu),
            ("quick_access", self.controller.estado_cpu_qam_runtime),
            ("core_unlock", self._state_cache.core_unlock),
        )
        raw_payload, errors = collect_named_sources(loaders)
        payload = {name: _dict(value) for name, value in raw_payload.items()}
        payload["_errors"] = errors
        return payload

    def _report_partial_refresh_errors(self, errors: dict) -> None:
        current = {str(key): str(value) for key, value in errors.items() if str(value)}
        for source, message in current.items():
            if self._last_refresh_errors.get(source) != message:
                self._append_console(f"Telemetry source {source} unavailable: {message}")
        self._last_refresh_errors = current

    def refresh(self) -> None:
        self._refresher.request()

    def _refresh_failed(self, message: str) -> None:
        self._append_console(f"Telemetry refresh warning: {message}")

    def _apply_core_unlock_state(self, core_unlock: dict) -> bool:
        physical_cores = int(_number(core_unlock.get("physical_cores"), 0))
        logical_cpus = int(_number(core_unlock.get("logical_cpus"), 0))
        core_shape = tr_format(
            "{cores} cores / {threads} threads",
            cores=physical_cores,
            threads=logical_cpus,
        )
        if core_unlock.get("unlocked"):
            core_detail = tr("The hidden cores are active for this powered session.")
            status_text, status_tone = "Unlocked", "green"
        elif core_unlock.get("supported_stock_shape"):
            core_detail = tr("Supported stock CPU shape detected.")
            status_text, status_tone = "Ready", "orange"
        else:
            core_detail = tr("This CPU shape is not eligible for automatic unlock.")
            status_text, status_tone = "Unavailable", "red"

        helper_ready = bool(core_unlock.get("helper_ready"))
        repository_ready = bool(core_unlock.get("repository_ready"))
        repository_path = str(core_unlock.get("repository_path") or "")
        self.core_shape_line.set_values(core_shape, core_detail)
        self.core_source_line.set_values(
            tr("Ready" if repository_ready else "Not prepared"),
            repository_path
            if repository_ready
            else tr("Use Prepare dependencies to clone and validate the official repository."),
        )
        self.core_helper_line.set_values(
            tr("Ready" if helper_ready else "Not installed"),
            tr("Privileged local helper" if helper_ready else "Reinstall BC250 Control Center to install the helper."),
        )
        governor_active = bool(core_unlock.get("governor_active"))
        governor_enabled = bool(core_unlock.get("governor_enabled"))
        if governor_active:
            governor_value = tr("Active now")
            governor_detail = tr("It will be stopped before any future upstream unlock action.")
        else:
            governor_value = tr("Inactive")
            governor_detail = tr("Required state while the upstream unlock action is running.")
        if governor_enabled:
            governor_detail += " " + tr("Enabled again at boot.")
        self.core_compatibility_line.set_values(governor_value, governor_detail)
        if self.core_unlock_card.status is not None:
            self.core_unlock_card.status.setText(tr(status_text))
            self.core_unlock_card.status.set_tone(status_tone)
        self.core_unlock_button.setText(
            tr("Already unlocked" if core_unlock.get("unlocked") else "Unlock cores and restart")
        )
        helper_missing = bool(
            core_unlock.get("supported_stock_shape")
            and not core_unlock.get("unlocked")
            and not helper_ready
        )
        repository_missing = bool(
            core_unlock.get("supported_stock_shape")
            and not core_unlock.get("unlocked")
            and not repository_ready
        )
        self.core_unlock_button.setToolTip(
            tr(
                "Use Prepare dependencies to clone and validate the official repository."
                if repository_missing
                else "Reinstall the local application package to install the privileged helper."
                if helper_missing
                else "Restart is required and the active GPU frequency governor will be disabled."
            )
        )
        return bool(
            core_unlock.get("supported_stock_shape")
            and not core_unlock.get("unlocked")
            and helper_ready
            and repository_ready
        )

    def _apply_processor_telemetry(self, core_unlock: dict) -> None:
        processor = _dict(core_unlock.get("processor"))
        model_name = str(processor.get("model_name") or "Not detected")
        vendor = str(processor.get("vendor") or "Not detected")
        architecture = str(processor.get("architecture") or "Not detected")
        self.model_stat.set_values(model_name, tr("kernel model name"))
        self.architecture_stat.set_values(architecture, vendor)
        self.platform_stat.set_values(
            str(processor.get("platform_process") or "Not exposed"),
            tr("CPU-X-compatible hardware identity"),
        )
        self.microcode_stat.set_values(
            str(processor.get("microcode") or "Not exposed"),
            tr("kernel-reported revision"),
        )
        self.topology_stat.set_values(
            str(processor.get("topology") or "Not detected"),
            tr("physical cores / logical threads"),
        )
        self.cache_stat.set_values(
            str(processor.get("cache") or "Not exposed"),
            tr("kernel cache hierarchy"),
        )
        self.features_stat.set_values(
            str(processor.get("features") or "Not exposed"),
            tr("selected acceleration flags"),
        )
        total_usage = _number(processor.get("total_usage_percent"), 0)
        self.total_load_stat.set_values(
            f"{total_usage:.0f} %",
            tr("average across logical threads"),
        )

        core_data = core_unlock.get("cores")
        cores = core_data if isinstance(core_data, list) else []
        by_index = {
            int(_number(item.get("index"), -1)): item
            for item in cores
            if isinstance(item, dict)
        }
        for index, stat in enumerate(self.core_stats):
            item = by_index.get(index)
            if not item:
                stat.set_values(tr("Hidden / offline"), tr("No logical threads exposed"))
                continue
            frequency = _number(item.get("frequency_mhz"), 0)
            usage = _number(item.get("usage_percent"), 0)
            threads = tuple(item.get("threads") or ())
            frequency_text = f"{frequency / 1000:.2f} GHz" if frequency else tr("Not detected")
            value = tr_format("{frequency} · {usage:.0f}%", frequency=frequency_text, usage=usage)
            thread_text = ", ".join(str(thread) for thread in threads) or "--"
            stat.set_values(
                value,
                tr_format("Logical CPUs: {threads}", threads=thread_text),
            )

    def _sync_active_cpu_config(self, persistent: dict) -> None:
        """Initialize controls from the real boot configuration once per change.

        Periodic telemetry refreshes must not undo edits the user is staging.
        A changed configuration signature or an explicit manual refresh does
        resynchronize the page.
        """
        config = _dict(persistent.get("config"))
        valid = bool(config.get("valid"))
        protected = bool(config.get("exists")) and str(config.get("error_kind") or "") == "permission"
        signature = (
            valid,
            protected,
            bool(config.get("exists")),
            int(_number(config.get("frequency"), 0)),
            int(_number(config.get("scale"), 0)),
            int(_number(config.get("max_temperature"), 0)),
            int(_number(config.get("target_vid"), 0)),
            str(config.get("error") or ""),
        )
        if self._cpu_config_initialized and signature == self._active_config_signature:
            return

        self._syncing_active_config = True
        try:
            if valid:
                frequency = int(config["frequency"])
                scale = int(config["scale"])
                temperature = int(config["max_temperature"])
                saved_vid = int(_number(config.get("target_vid"), 0))
                estimated_vid = int(_number(config.get("estimated_vid"), 0))
                vid = saved_vid if CPU_VID_RANGE[0] <= saved_vid <= CPU_VID_RANGE[1] else estimated_vid
                vid = max(CPU_VID_RANGE[0], min(CPU_VID_RANGE[1], vid or CPU_VID_RANGE[0]))

                self.frequency_control.setValue(frequency)
                self.vid_control.setValue(vid)
                self.temperature_control.setValue(temperature)
                self.scale_control.setValue(scale)

                profile = (
                    self._profile_name_for_values(frequency, vid, temperature)
                    if saved_vid
                    else ""
                )
                if profile:
                    self._selected_profile_name = profile
                    self._check_preset_button(profile)
                else:
                    self._selected_profile_name = "Custom"
                    self._clear_preset_checks()
                self.applied_tuning_stat.set_values(
                    tr_format("{frequency} MHz · scale {scale}", frequency=frequency, scale=scale),
                    tr_format(
                        "~{vid} mV estimated · {temperature} °C · boot configuration",
                        vid=estimated_vid or vid,
                        temperature=temperature,
                    ),
                )
                self._update_staged_target()
            elif protected:
                # A root-owned legacy 0600 config is not corrupt; simply leave
                # the user's current controls untouched until install-local
                # normalizes it to root-owned 0644 for read-only validation.
                pass
            else:
                self._select_preset(self.preset_buttons[0])
                if config.get("exists"):
                    self._selected_profile_name = "Custom"
                    self._clear_preset_checks()
        finally:
            self._syncing_active_config = False

        self._active_config_signature = signature
        self._cpu_config_initialized = True
        self.apply_button.setEnabled(True)

    @staticmethod
    def _render_cpu_text(text: CpuText) -> str:
        if getattr(text, "literal", False):
            return text.template
        values = dict(text.values)
        return tr_format(text.template, **values) if values else tr(text.template)

    def _render_cpu_telemetry(self, telemetry: CpuTelemetryPresentation) -> None:
        frequency = self._render_cpu_text(telemetry.frequency_text)
        voltage = self._render_cpu_text(telemetry.voltage_text)
        temperature = self._render_cpu_text(telemetry.temperature_text)
        self.summary_strip.items[1].set_values(frequency, "average across active cores")
        self.summary_strip.items[3].set_values(voltage, "VDDNB / SMU telemetry")
        self.summary_strip.items[4].set_values(temperature, "k10temp Tctl")
        self.frequency_metric.set_values(frequency, tr("Kernel-reported average"))
        self.voltage_metric.set_values(voltage, "VDDNB / SMU telemetry")
        self.temperature_metric.set_values(temperature, "k10temp Tctl")
        self.power_metric.set_label(self._render_cpu_text(telemetry.power_label))
        self.power_metric.set_values(
            self._render_cpu_text(telemetry.power_text),
            self._render_cpu_text(telemetry.power_detail),
        )

    def _apply_refresh_payload(self, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        perf = _dict(data.get("performance"))
        tools = _dict(data.get("tools"))
        persistent = _dict(data.get("persistent"))
        detection = _dict(data.get("detection"))
        scale_live = _dict(data.get("scale_live"))
        quick_access = _dict(data.get("quick_access"))
        core_unlock = _dict(data.get("core_unlock"))
        refresh_errors = _dict(data.get("_errors"))
        self._report_partial_refresh_errors(refresh_errors)
        if "core_unlock" in refresh_errors:
            # Keep the last verified status usable.  Without this, one slow
            # service/Git probe turns the unlock button off until the next
            # successful timer tick, even though nothing changed on the PC.
            core_unlock = dict(self._last_core_unlock_snapshot)
        elif core_unlock:
            self._last_core_unlock_snapshot = dict(core_unlock)
        # Do not overwrite a user's staged CPU values merely because systemd
        # status was temporarily unavailable.  Resynchronise only from a real
        # persistence snapshot.
        if "persistent" not in refresh_errors:
            self._sync_active_cpu_config(persistent)

        telemetry = present_cpu_telemetry(perf)
        self._render_cpu_telemetry(telemetry)

        tool_path = tools.get("bc250_detect") or tools.get("smu_oc_path") or ""
        tool_ready = bool(tools.get("bc250_detect") or tools.get("smu_oc_exists"))

        persistence = present_cpu_persistence(persistent, refresh_errors)
        enabled = persistence.enabled
        active_state = persistence.active_state
        prepared_state = persistence.prepared_state
        config_exists = persistence.config_exists
        config_valid = persistence.config_valid
        config_protected = persistence.config_protected
        boot_config = dict(persistence.boot_config)

        self.current_state = {
            "service_enabled": enabled,
            "active_state": prepared_state,
            "raw_active_state": active_state,
            "config_exists": config_exists,
            "config_valid": config_valid,
            "config_protected": config_protected,
            "tool_path": tool_path,
            "core_unlock_helper_ready": bool(core_unlock.get("helper_ready")),
            "core_unlock_repository_ready": bool(core_unlock.get("repository_ready")),
            "core_unlock_allowed": self._apply_core_unlock_state(core_unlock),
            "live_frequency_mhz": telemetry.live_frequency_mhz,
            "live_temperature_c": telemetry.live_temperature_c,
        }
        self._apply_processor_telemetry(core_unlock)

        self.summary_strip.items[0].set_values(
            self._render_cpu_text(persistence.service_text),
            self._render_cpu_text(persistence.runtime_text),
        )

        tuning = present_cpu_tuning(
            persistent,
            detection,
            scale_live,
            quick_access,
            last_applied_frequency=self._last_applied_frequency,
            scale_override_enabled=self.scale_override_check.isChecked(),
        )
        if "detection" not in refresh_errors:
            self._set_manual_scale_available(
                tuning.detection_recorded
                and tuning.detection_matches
                and tuning.detection_same_boot
                and bool(tuning.detection_snapshot)
            )
        self.detected_scale_stat.set_values(
            self._render_cpu_text(tuning.detection_value),
            self._render_cpu_text(tuning.detection_detail),
        )
        self.live_scale_stat.set_values(
            self._render_cpu_text(tuning.live_value),
            self._render_cpu_text(tuning.live_detail),
        )
        self.applied_tuning_stat.set_values(
            self._render_cpu_text(tuning.applied_value),
            self._render_cpu_text(tuning.applied_detail),
        )

        self.live_telemetry_stat.set_values(
            f"{telemetry.live_temperature_text} | {telemetry.live_frequency_text}",
            tr("current temperature and average frequency"),
        )

        self.persistence_stat.set_values(
            self._render_cpu_text(persistence.status_value),
            self._render_cpu_text(persistence.status_detail),
        )

        self.current_state.update({
            "detection_matches": tuning.detection_matches,
            "detection_same_boot": tuning.detection_same_boot,
            "detection_recorded": tuning.detection_recorded,
            "detection_snapshot": dict(tuning.detection_snapshot),
            "live_scale_matches": tuning.live_matches_detection,
            "active_source_kind": tuning.active_source_kind,
            "live_scale_active_this_session": tuning.live_active_this_session,
            "live_scale_valid_for_persistence": tuning.live_valid_for_persistence,
            "live_scale_test": dict(tuning.live_test),
            "active_scale": tuning.active_scale,
            "active_scale_source": tuning.active_source,
            "boot_config": dict(boot_config),
            "persistence_available": persistence.available,
        })

        if self._last_applied_frequency is None:
            self.last_operation_stat.set_values("None", tr("No CPU frequency has been applied yet"))
        else:
            self.last_operation_stat.set_values(
                f"{self._last_applied_frequency} MHz",
                tr(self._last_operation_summary or "Latest applied CPU frequency"),
            )

        if tuning.override_status is not None and self.scale_override_check.isChecked():
            self.scale_test_status.setText(self._render_cpu_text(tuning.override_status))

        self.command_line.set_values("bc250-detect --keep", tr_format("tool {state}", state=tr("ready" if tool_ready else "missing")))

        self.disable_service_button.setProperty("serviceEnabled", enabled)
        process_running = (
            self._command_build_pending
            or (
                self.process is not None
                and self.process.state() != QProcess.ProcessState.NotRunning
            )
        )
        self.disable_service_button.setEnabled(enabled and not process_running)
        self._set_running(process_running, None)

    def _append_console(self, text: str) -> None:
        if text:
            self.console.appendPlainText(text)
            self.console.ensureCursorVisible()

    def _clear_console(self) -> None:
        self.console.setPlainText("CPU / SMU session console cleared.")

    def _show_info(self, title: str, message: str, *, tone: str = "blue") -> None:
        InfoDialog(
            title,
            message,
            icon_name="warning_orange" if tone in {"orange", "red"} else "info_blue",
            parent=self,
            eyebrow="CPU / SMU",
            button_text="Close",
            notice="No additional hardware command was executed.",
            tone=tone,
        ).exec()
