from __future__ import annotations

import time
from datetime import datetime

from PyQt6.QtCore import QProcess, QTimer, Qt
from PyQt6.QtGui import QIntValidator, QTextCursor
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..components.page_widgets import (
    ControlPageHeader,
    MetricTile,
    ConfirmDialog,
    PresetButton,
    SectionCard,
    StatusLine,
)
from ..components.responsive import clear_grid, configure_responsive_scroll_area, effective_viewport_width
from ..components.async_tools import AsyncRefresh, BackgroundExecutor
from ..i18n import tr, tr_format
from ..core.state import state_cache_for
from ..theme import COLORS
from ..components.widgets import IconBadge, InfoDialog, apply_shadow, icon


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


CPU_FREQUENCY_RANGE = (3000, 4200)
CPU_VID_RANGE = (900, 1375)
CPU_TEMPERATURE_RANGE = (70, 90)
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

    def __init__(self, label: str, value: str, detail: str = "", parent=None):
        super().__init__(parent)
        self.setProperty("runtimeStatCard", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(72)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)
        label_widget = QLabel(tr(label))
        label_widget.setProperty("runtimeStatLabel", True)
        self.value = QLabel(tr(value))
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
    ):
        super().__init__(parent)
        self.minimum = int(minimum)
        self.maximum = int(maximum)
        self.unit = unit
        self.setProperty("frequencyField", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(10)

        copy = QVBoxLayout()
        copy.setSpacing(1)
        title = QLabel(tr(label))
        title.setProperty("fieldLabel", True)
        detail = QLabel(tr(hint))
        detail.setProperty("fieldHint", True)
        detail.setWordWrap(True)
        copy.addWidget(title)
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

    def __init__(self, controller, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("cpuSmuPage", True)
        self.controller = controller
        self.process: QProcess | None = None
        self._updates_active = False
        self._state_cache = state_cache_for(controller)
        self._background = BackgroundExecutor(self)
        self.current_state: dict = {}
        self._operation = ""
        self._last_operation_summary = "No hardware command has been executed."
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
        self._selected_profile_name = self.PROFILE_VALUES[0][0]

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        self.scroll = scroll
        self.content = QWidget()
        configure_responsive_scroll_area(scroll, self.content)
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(18, 8, 18, 24)
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

        self.configuration_card = self._build_configuration_card()
        self.metrics_card = self._build_metrics_card()
        self.processor_card = self._build_processor_card()
        self.cores_card = self._build_cores_card()
        self.runtime_card = self._build_runtime_card()
        self.core_unlock_card = self._build_core_unlock_card()
        for paired_card in (
            self.configuration_card,
            self.metrics_card,
            self.processor_card,
            self.core_unlock_card,
        ):
            paired_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.advanced_card = self._build_advanced_card()
        self.advanced_toggle.setText(tr("Hide advanced details"))
        if self.advanced_card.status is not None:
            self.advanced_card.status.setText(tr("Visible"))
            self.advanced_card.status.set_tone("gray")

        self.workspace_tabs = QFrame()
        self.workspace_tabs.setProperty("cpuWorkspaceTabs", True)
        tabs_layout = QHBoxLayout(self.workspace_tabs)
        tabs_layout.setContentsMargins(5, 5, 5, 5)
        tabs_layout.setSpacing(5)
        self.workspace_tab_group = QButtonGroup(self)
        self.workspace_tab_group.setExclusive(True)
        self.workspace_tab_buttons: dict[str, QPushButton] = {}
        tab_specs = (
            (
                "overview",
                "Overview and live monitoring",
                "Processor overview, live cores, and hidden-core unlock.",
                "cpu_blue",
            ),
            (
                "configuration",
                "CPU configuration",
                "Profiles, temporary tuning, persistence, and advanced details.",
                "settings_blue",
            ),
        )
        for key, text, tooltip, icon_name in tab_specs:
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
            tabs_layout.addWidget(button, 1)
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

        self._select_preset(self.preset_buttons[0])
        self._select_workspace("overview")
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

    def _select_workspace(self, name: str) -> None:
        key = "configuration" if name == "configuration" else "overview"
        index = 1 if key == "configuration" else 0
        self.workspace_stack.setCurrentIndex(index)
        self.workspace_tab_buttons[key].setChecked(True)
        self.scroll.verticalScrollBar().setValue(0)

    def _build_configuration_card(self) -> SectionCard:
        card = SectionCard(
            "CPU configuration",
            "Choose one of the validated UI presets or enter your own frequency, VID, and temperature cap.",
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
            "Target frequency",
            "Temporary session target routed to bc250-detect --keep.",
            *CPU_FREQUENCY_RANGE,
            3550,
            "MHz",
        )
        self.vid_control = CpuValueField(
            "Target VID",
            "The validated backend rejects values above 1375 mV.",
            *CPU_VID_RANGE,
            1050,
            "mV",
        )
        self.temperature_control = CpuValueField(
            "Temperature limit",
            "The UI keeps the CPU session ceiling at a maximum of 90 °C.",
            *CPU_TEMPERATURE_RANGE,
            90,
            "°C",
        )
        self.parameter_fields = [self.frequency_control, self.vid_control, self.temperature_control]
        for field in self.parameter_fields:
            field.input.textChanged.connect(self._on_parameter_changed)
        self._reflow_parameter_fields(1400)
        card.body.addLayout(self.parameter_grid)

        self.range_note = QLabel(
            "Validated UI range: 3000–4200 MHz · 900–1375 mV · temperature cap up to 90 °C."
        )
        self.range_note.setProperty("fieldHint", True)
        self.range_note.setWordWrap(True)
        card.body.addWidget(self.range_note)

        apply_row = QHBoxLayout()
        apply_row.setSpacing(8)
        selection_hint = QLabel(
            "Selected values stay editable so you can still enter your own custom session values before applying."
        )
        selection_hint.setProperty("sectionSubtitle", True)
        selection_hint.setWordWrap(True)
        apply_row.addWidget(selection_hint, 1)
        self.apply_button = QPushButton("Review and apply session")
        self.apply_button.setObjectName("PrimaryAction")
        self.apply_button.clicked.connect(self._apply_custom)
        apply_row.addWidget(self.apply_button)
        card.body.addLayout(apply_row)
        return card

    def _build_metrics_card(self) -> SectionCard:
        card = SectionCard(
            "Live metrics",
            "Passive CPU telemetry aligned with the governor page layout and refreshed from the validated backend.",
            icon_name="cpu_blue",
            icon_background=COLORS["blue_soft"],
            status=("Passive", "green"),
        )

        self.metrics_grid = QGridLayout()
        self.metrics_grid.setContentsMargins(0, 0, 0, 0)
        self.metrics_grid.setHorizontalSpacing(10)
        self.metrics_grid.setVerticalSpacing(10)
        self.frequency_metric = MetricTile(
            "Average frequency", "Not detected", "Kernel-reported average", icon_name="cpu_blue", icon_background=COLORS["blue_soft"]
        )
        self.voltage_metric = MetricTile(
            "Voltage sensor", "Not detected", "VDDNB / SMU telemetry", icon_name="power_gray", icon_background=COLORS["orange_soft"]
        )
        self.temperature_metric = MetricTile(
            "Temperature", "Not detected", "k10temp Tctl", icon_name="warning_orange", icon_background=COLORS["orange_soft"]
        )
        self.power_metric = MetricTile(
            "SoC package power", "Not detected", "AMDGPU hwmon sensor", icon_name="power_gray", icon_background="neutral_soft"
        )
        self.metric_tiles = [
            self.frequency_metric,
            self.voltage_metric,
            self.temperature_metric,
            self.power_metric,
        ]
        self._reflow_metric_tiles(1400)
        card.body.addLayout(self.metrics_grid)

        note = QLabel(
            "Metrics are read-only. Frequency, VID, and the temperature cap are only changed after the review dialog is confirmed."
        )
        note.setProperty("fieldHint", True)
        note.setWordWrap(True)
        card.body.addWidget(note)
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
            "All eight BC-250 core positions remain visible. Frequency and utilization are averaged across each core's logical threads.",
            icon_name="compute_blue",
            icon_background=COLORS["blue_soft"],
            status=("Passive", "green"),
        )
        self.cores_grid = QGridLayout()
        self.cores_grid.setContentsMargins(0, 0, 0, 0)
        self.cores_grid.setHorizontalSpacing(10)
        self.cores_grid.setVerticalSpacing(10)
        self.core_stats = [
            RuntimeStat(
                tr_format("Core {index}", index=index),
                "Checking",
                "logical threads",
            )
            for index in range(8)
        ]
        self._reflow_core_stats(1400)
        card.body.addLayout(self.cores_grid)
        return card

    def _build_runtime_card(self) -> SectionCard:
        card = SectionCard(
            "Runtime status",
            "Service status, validated tool availability, and the currently staged CPU session target.",
            icon_name="shield_green",
            icon_background=COLORS["green_soft"],
            status=("Session only", "green"),
        )

        stats_panel = QFrame()
        stats_panel.setProperty("compactPanel", True)
        stats_panel_layout = QVBoxLayout(stats_panel)
        stats_panel_layout.setContentsMargins(10, 10, 10, 10)
        stats_panel_layout.setSpacing(0)
        self.runtime_stats_grid = QGridLayout()
        self.runtime_stats_grid.setContentsMargins(0, 0, 0, 0)
        self.runtime_stats_grid.setHorizontalSpacing(10)
        self.runtime_stats_grid.setVerticalSpacing(10)

        self.service_stat = RuntimeStat("Service", "Checking", "bc250-smu-oc.service")
        self.state_stat = RuntimeStat("Runtime state", "Not detected", "systemd state")
        self.profile_stat = RuntimeStat("Target", "3550 MHz / 1050 mV", "Placa media · 90 °C")
        self.tool_stat = RuntimeStat("Tool", "Checking", "bc250-detect / bc250_smu_oc")
        self.config_stat = RuntimeStat("Config", "Checking", "/etc/bc250-smu-oc.conf")
        self.updated_stat = RuntimeStat("Updated", "--:--:--", "passive refresh")
        self.runtime_stats = [
            self.service_stat,
            self.state_stat,
            self.profile_stat,
            self.tool_stat,
            self.config_stat,
            self.updated_stat,
        ]
        self._reflow_runtime_stats(1400)
        stats_panel_layout.addLayout(self.runtime_stats_grid)
        card.body.addWidget(stats_panel)

        controls_panel = QFrame()
        controls_panel.setProperty("compactPanel", True)
        controls_layout = QVBoxLayout(controls_panel)
        controls_layout.setContentsMargins(12, 10, 12, 10)
        controls_layout.setSpacing(8)
        controls_copy = QLabel(
            "CPU runtime actions keep the temporary workflow visible while exposing boot-service status and the validated controller entry points."
        )
        controls_copy.setProperty("fieldHint", True)
        controls_copy.setWordWrap(True)
        controls_layout.addWidget(controls_copy)

        self.runtime_actions_grid = QGridLayout()
        self.runtime_actions_grid.setContentsMargins(0, 0, 0, 0)
        self.runtime_actions_grid.setHorizontalSpacing(8)
        self.runtime_actions_grid.setVerticalSpacing(8)
        self.prepare_tools_button = QPushButton("Prepare tools")
        self.prepare_tools_button.setProperty("compactAction", True)
        self.prepare_tools_button.setIcon(icon("download_blue"))
        self.prepare_tools_button.clicked.connect(self.prepare_tools)

        self.persistence_status_button = QPushButton("View persistence status")
        self.persistence_status_button.setProperty("compactAction", True)
        self.persistence_status_button.clicked.connect(self.show_persistence_status)

        self.enable_persistence_button = QPushButton("Enable / update persistence")
        self.enable_persistence_button.setProperty("dangerAction", True)
        self.enable_persistence_button.clicked.connect(self.enable_persistence)

        self.disable_service_button = QPushButton("Disable persistence")
        self.disable_service_button.setProperty("dangerAction", True)
        self.disable_service_button.clicked.connect(self.disable_persistence)
        self.disable_service_button.setEnabled(False)

        self.details_button = QPushButton("Read details")
        self.details_button.setProperty("compactAction", True)
        self.details_button.clicked.connect(self._show_runtime_details)

        self.advanced_toggle = QPushButton("Advanced details")
        self.advanced_toggle.setProperty("compactAction", True)
        self.advanced_toggle.clicked.connect(self._toggle_advanced)

        self.runtime_action_buttons = [
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
            "proceeding, because a restart is required to apply the changes."
        )
        warning.setProperty("warningText", True)
        warning.setWordWrap(True)
        card.body.addWidget(warning)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_row.addStretch(1)
        self.core_unlock_button = QPushButton("Unlock cores and restart")
        self.core_unlock_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.core_unlock_button.setProperty("dangerAction", True)
        self.core_unlock_button.clicked.connect(self._request_core_unlock)
        action_row.addWidget(self.core_unlock_button)
        card.body.addLayout(action_row)
        return card

    def _build_advanced_card(self) -> SectionCard:
        card = SectionCard(
            "Advanced details",
            "Validated command context and the embedded CPU session console.",
            icon_name="logs_gray",
            icon_background="neutral_soft",
            status=("Hidden", "gray"),
        )
        card.add_header_button("Clear console", self._clear_console)

        self.details_grid = QGridLayout()
        self.details_grid.setContentsMargins(0, 0, 0, 0)
        self.details_grid.setHorizontalSpacing(12)
        self.details_grid.setVerticalSpacing(12)

        contract_panel = QFrame()
        contract_panel.setProperty("compactPanel", True)
        contract_layout = QVBoxLayout(contract_panel)
        contract_layout.setContentsMargins(12, 12, 12, 12)
        contract_layout.setSpacing(8)
        self.command_line = StatusLine("Command", "bc250-detect --keep", "Temporary CPU session action")
        self.limits_line = StatusLine("UI limits", "3000–4200 MHz", "900–1375 mV · up to 90 °C")
        self.persistence_line = StatusLine(
            "Persistence",
            "Disabled",
            "Use Enable / update persistence only after validating a stable temporary profile",
        )
        self.last_operation_line = StatusLine("Last operation", "None", self._last_operation_summary)
        for line in (self.command_line, self.limits_line, self.persistence_line, self.last_operation_line):
            contract_layout.addWidget(line)

        console_panel = QFrame()
        console_panel.setProperty("compactPanel", True)
        console_layout = QVBoxLayout(console_panel)
        console_layout.setContentsMargins(12, 12, 12, 12)
        console_layout.setSpacing(8)
        console_header = QLabel("Session console")
        console_header.setProperty("fieldLabel", True)
        console_layout.addWidget(console_header)
        self.console = QPlainTextEdit()
        self.console.setObjectName("OperationConsole")
        self.console.setReadOnly(True)
        self.console.setMinimumHeight(210)
        self.console.setPlainText("CPU / SMU session console ready. No hardware command has been executed.")
        console_layout.addWidget(self.console)

        self.detail_panels = [contract_panel, console_panel]
        self._reflow_advanced_details(1400)
        card.body.addLayout(self.details_grid)
        self.console_status = card.status
        return card

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reflow(effective_viewport_width(self, self.scroll))

    def _reflow(self, width: int) -> None:
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
        self._reflow_advanced_details(width)

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
                self.configuration_workspace.addWidget(self.configuration_card, 0, 0)
                self.configuration_workspace.addWidget(self.runtime_card, 0, 1)
                self.configuration_workspace.addWidget(
                    self.advanced_card,
                    1,
                    0,
                    1,
                    2,
                )
                self.configuration_workspace.setColumnStretch(0, 1)
                self.configuration_workspace.setColumnStretch(1, 1)
                self.configuration_workspace.setRowStretch(2, 1)
            else:
                self.configuration_workspace.addWidget(
                    self.configuration_card,
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
        columns = 3 if width >= 1180 else 2 if width >= 680 else 1
        if columns == self._field_columns and self.parameter_grid.count():
            return
        self._field_columns = columns
        self._clear_grid(self.parameter_grid)
        for index, field in enumerate(self.parameter_fields):
            self.parameter_grid.addWidget(field, index // columns, index % columns)
        for column in range(columns):
            self.parameter_grid.setColumnStretch(column, 1)

    def _reflow_metric_tiles(self, width: int) -> None:
        columns = 4 if width >= 1100 else 2 if width >= 620 else 1
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
        columns = 8 if width >= 1260 else 4 if width >= 720 else 2 if width >= 420 else 1
        if columns == self._core_columns and self.cores_grid.count():
            return
        self._core_columns = columns
        self._clear_grid(self.cores_grid)
        for index, stat in enumerate(self.core_stats):
            self.cores_grid.addWidget(stat, index // columns, index % columns)
        for column in range(columns):
            self.cores_grid.setColumnStretch(column, 1)

    def _reflow_runtime_stats(self, width: int) -> None:
        columns = 6 if width >= 1260 else 3 if width >= 900 else 2 if width >= 480 else 1
        if columns == self._runtime_columns and self.runtime_stats_grid.count():
            return
        self._runtime_columns = columns
        self._clear_grid(self.runtime_stats_grid)
        for index, stat in enumerate(self.runtime_stats):
            self.runtime_stats_grid.addWidget(stat, index // columns, index % columns)
        for column in range(columns):
            self.runtime_stats_grid.setColumnStretch(column, 1)

    def _reflow_runtime_actions(self, width: int) -> None:
        columns = 6 if width >= 1260 else 3 if width >= 900 else 2 if width >= 520 else 1
        if columns == self._runtime_action_columns and self.runtime_actions_grid.count():
            return
        self._runtime_action_columns = columns
        self._clear_grid(self.runtime_actions_grid)
        for index, button in enumerate(self.runtime_action_buttons):
            self.runtime_actions_grid.addWidget(button, index // columns, index % columns)
        for column in range(columns):
            self.runtime_actions_grid.setColumnStretch(column, 1)

    def _reflow_advanced_details(self, width: int) -> None:
        columns = 2 if width >= 960 else 1
        if columns == self._detail_columns and self.details_grid.count():
            return
        self._detail_columns = columns
        self._clear_grid(self.details_grid)
        for index, panel in enumerate(self.detail_panels):
            self.details_grid.addWidget(panel, index // columns, index % columns)
        for column in range(columns):
            self.details_grid.setColumnStretch(column, 1)

    @staticmethod
    def _clear_grid(layout: QGridLayout) -> None:
        clear_grid(layout)

    @staticmethod
    def _reset_row_stretches(layout: QGridLayout, count: int) -> None:
        for row in range(count):
            layout.setRowStretch(row, 0)

    def _on_parameter_changed(self) -> None:
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
        target_detail = tr_format("{profile} · {temperature} °C cap", profile=self._selected_profile_name, temperature=temperature)
        self.summary_strip.items[2].set_values(target_value, tr_format("temperature cap {temperature} °C", temperature=temperature))
        self.profile_stat.set_values(target_value, target_detail)

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
        if not (CPU_VID_RANGE[0] <= vid <= CPU_VID_RANGE[1]):
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
        self._request_apply(frequency, vid, temperature)

    def _build_and_start_process(self, operation, label: str, error_title: str) -> None:
        self._set_running(True)

        def success(payload: object) -> None:
            command = list(payload or [])
            if not command:
                self._set_running(False, success=False)
                self._show_info(error_title, "The controller returned an empty command.", tone="red")
                return
            self._start_process(command, label)

        def failure(message: str) -> None:
            self._set_running(False, success=False)
            self._show_info(error_title, message, tone="red")

        if not self._background.start("cpu-command-build", operation, success, failure):
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
        self._build_and_start_process(
            lambda: self.controller.comando_cpu_oc_temporal_embebido(frequency, vid, temperature),
            f"CPU {frequency} MHz / {vid} mV / {temperature} °C",
            "CPU profile rejected",
        )

    def prepare_tools(self) -> None:
        self.prepare_tools_button.setEnabled(False)

        def success(result: object) -> None:
            self._append_console(
                tr("bc250_smu_oc is already available." if result is True else "Opened the existing R64 CPU tool preparation workflow.")
            )
            self._last_operation_summary = "CPU tool preparation workflow completed."
            self.last_operation_line.set_values("Prepare CPU tools", self._last_operation_summary)
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
            self._select_workspace("configuration")
            if self.advanced_card.isHidden():
                self._toggle_advanced()
            self._append_console(f"\n[{datetime.now().strftime('%H:%M:%S')}] Persistence status")
            self._append_console(tr_format("Service: {value}", value=service))
            self._append_console(tr_format("Enabled: {value}", value=enabled))
            self._append_console(tr_format("Active: {active} ({sub_state})", active=active, sub_state=sub_state))
            self._append_console(tr_format("Result: {value}", value=result))
            self._append_console(tr_format("Config: {value}", value=config))
            self._append_console("\n--- systemctl status ---")
            self._append_console(status_text)
            self._last_operation_summary = "Persistence status read without changing the service."
            self.last_operation_line.set_values("Read persistence status", self._last_operation_summary)
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
        dialog = ConfirmDialog(
            "Enable persistent CPU overclock",
            "This installs the last overclock.conf generated by bc250-detect and enables it at boot. "
            "Only continue after the exact profile has completed stability testing; an unstable boot profile can freeze the board or leave it without video output.",
            summary=(
                ("Source", "Latest tested overclock.conf"),
                ("Service", "bc250-smu-oc.service"),
                ("Boot behavior", "Apply automatically at startup"),
            ),
            confirm_text="Install and enable persistence",
            tone="red",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._build_and_start_process(
            self.controller.comando_cpu_oc_persistente_embebido,
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
        if self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning:
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
            "cyan-skillfish-governor-smu will be stopped and disabled before that restart.",
            summary=(
                ("Restart", "Required immediately"),
                ("CPU after restart", "Expected: 8 cores / 16 threads"),
                ("GPU governor", "Disabled for the next startup"),
                ("Reactivate later", "GPU → Activate service"),
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

    def _show_runtime_details(self) -> None:
        frequency = self.frequency_control.value()
        vid = self.vid_control.value()
        temperature = self.temperature_control.value()
        enabled = self.current_state.get("service_enabled", False)
        active_state = self.current_state.get("active_state", "unknown")
        config_state = "Present" if self.current_state.get("config_exists") else "Not installed"
        tool_path = self.current_state.get("tool_path") or "Use Prepare CPU tools"
        message = "\n".join((
            tr_format("Staged target: {frequency} MHz / {vid} mV / {temperature} °C", frequency=frequency, vid=vid, temperature=temperature),
            tr_format("Profile: {profile}", profile=self._selected_profile_name),
            "",
            tr_format("Service: {value}", value=tr("Enabled" if enabled else "Disabled")),
            tr_format("Runtime state: {value}", value=tr(str(active_state).capitalize())),
            tr_format("Config: {value}", value=tr(config_state)),
            tr_format("Tool path: {value}", value=tool_path),
            "",
            tr("Validated CPU workflow: temporary bc250-detect --keep sessions, with explicit reviewed controls to inspect, enable/update, or disable boot persistence."),
        ))
        InfoDialog(
            "CPU runtime details",
            message,
            icon_name="info_blue",
            parent=self,
            eyebrow="CPU / SMU",
            button_text="Close",
            notice="This view is informational only. No new hardware command was executed.",
            tone="blue",
        ).exec()

    def _toggle_advanced(self) -> None:
        visible = self.advanced_card.isHidden()
        if visible:
            self._select_workspace("configuration")
        self.advanced_card.setVisible(visible)
        self.advanced_toggle.setText(tr("Hide advanced details" if visible else "Advanced details"))
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
        self._operation = operation
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self.process.readyReadStandardOutput.connect(self._read_stdout)
        self.process.readyReadStandardError.connect(self._read_stderr)
        self.process.finished.connect(self._process_finished)
        self.process.errorOccurred.connect(self._process_error)
        self._set_running(True)
        self._last_operation_summary = tr_format("Started at {time}", time=datetime.now().strftime("%H:%M:%S"))
        self.last_operation_line.set_values(operation, self._last_operation_summary)
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
            self._append_console(data.rstrip())

    def _process_finished(self, exit_code: int, _status) -> None:
        self._append_console(tr_format("[{time}] Finished with exit code {code}.", time=datetime.now().strftime("%H:%M:%S"), code=exit_code))
        self._last_operation_summary = tr_format("Finished with exit code {code} at {time}", code=exit_code, time=datetime.now().strftime("%H:%M:%S"))
        self.last_operation_line.set_values(self._operation or "CPU operation", self._last_operation_summary)
        self._set_running(False, success=exit_code == 0)
        if exit_code == 0:
            operation_name = self._operation

            def register_event() -> object:
                self.controller.registrar_evento("cpu", "success", operation_name, "CPU / SMU operation completed")
                return True

            self._background.start(
                f"cpu-event:{time.monotonic_ns()}",
                register_event,
            )
        self._state_cache.invalidate("performance", "tools", "cpu_persistence")
        self.refresh()

    def _process_error(self, error) -> None:
        if self.process is not None:
            self._append_console(tr_format("Process error: {message} ({code})", message=self.process.errorString(), code=error))
        self._last_operation_summary = tr("Process error occurred. Review the session console output.")
        self.last_operation_line.set_values(self._operation or "CPU operation", self._last_operation_summary)
        self._set_running(False, success=False)

    def _set_running(self, running: bool, success: bool | None = None) -> None:
        self.apply_button.setEnabled(not running)
        self.prepare_tools_button.setEnabled(not running)
        self.persistence_status_button.setEnabled(not running)
        self.enable_persistence_button.setEnabled(not running)
        self.core_unlock_button.setEnabled(not running and self.current_state.get("core_unlock_allowed", False))
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
        return {
            "performance": self._state_cache.performance(),
            "tools": self._state_cache.tools(),
            "persistent": self._state_cache.cpu_persistence(),
            "core_unlock": self.controller.estado_desbloqueo_nucleos_cpu(),
        }

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
                else "Restart is required and the cyan GPU governor will be disabled."
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

    def _apply_refresh_payload(self, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        perf = _dict(data.get("performance"))
        tools = _dict(data.get("tools"))
        persistent = _dict(data.get("persistent"))
        core_unlock = _dict(data.get("core_unlock"))
        tools_available = bool(tools)
        persistent_available = bool(persistent)

        frequency = _number(perf.get("cpu_freq"), 0)
        voltage = _number(perf.get("cpu_voltage"), 0)
        if 0 < voltage < 10:
            voltage *= 1000
        temperature = _number(perf.get("cpu_temp"), 0)
        power = _number(perf.get("power_w"), 0)
        power_label = str(perf.get("power_label") or "Power sensor unavailable")
        power_detail = (
            "Dedicated total-board power sensor"
            if bool(perf.get("power_is_total"))
            else "AMDGPU SoC power sensor; total board power unavailable"
            if str(perf.get("power_scope") or "") == "gpu_soc"
            else "No live power sensor exposed"
        )

        frequency_text = f"{frequency / 1000:.2f} GHz" if frequency else "Not detected"
        voltage_text = f"{voltage / 1000:.3f} V" if voltage else "Not exposed"
        temperature_text = f"{temperature:.1f} °C" if temperature else "Not detected"
        power_text = f"{power:.0f} W" if power else "Not detected"

        self.summary_strip.items[1].set_values(frequency_text, "average across active cores")
        self.summary_strip.items[3].set_values(voltage_text, "VDDNB / SMU telemetry")
        self.summary_strip.items[4].set_values(temperature_text, "k10temp Tctl")
        self.frequency_metric.set_values(frequency_text, tr("Kernel-reported average"))
        self.voltage_metric.set_values(voltage_text, "VDDNB / SMU telemetry")
        self.temperature_metric.set_values(temperature_text, "k10temp Tctl")
        self.power_metric.set_label(power_label)
        self.power_metric.set_values(power_text, tr(power_detail))

        tool_path = tools.get("bc250_detect") or tools.get("smu_oc_path") or ""
        tool_ready = bool(tools.get("bc250_detect") or tools.get("smu_oc_exists"))

        enabled = persistent_available and str(persistent.get("enabled") or "").lower() == "enabled"
        active_state = str(persistent.get("active_state") or persistent.get("active") or "unknown")
        config_exists = persistent_available and bool(persistent.get("config_exists"))

        self.current_state = {
            "service_enabled": enabled,
            "active_state": active_state,
            "config_exists": config_exists,
            "tool_path": tool_path,
            "core_unlock_helper_ready": bool(core_unlock.get("helper_ready")),
            "core_unlock_repository_ready": bool(core_unlock.get("repository_ready")),
            "core_unlock_allowed": self._apply_core_unlock_state(core_unlock),
        }
        self._apply_processor_telemetry(core_unlock)

        service_text = tr("Enabled" if enabled else "Disabled") if persistent_available else tr("Not detected")
        runtime_text = tr(str(active_state).capitalize()) if persistent_available else tr("Not detected")
        tool_text = tr("Ready" if tool_ready else "Missing") if tools_available else tr("Not detected")
        config_text = tr("Present" if config_exists else "Not installed") if persistent_available else tr("Not detected")
        self.summary_strip.items[0].set_values(service_text, runtime_text)
        self.service_stat.set_values(service_text, "bc250-smu-oc.service")
        self.state_stat.set_values(runtime_text, tr("systemd state"))
        self.tool_stat.set_values(tool_text, str(tool_path or tr("Use Prepare CPU tools")))
        self.config_stat.set_values(config_text, "/etc/bc250-smu-oc.conf")
        self.updated_stat.set_values(datetime.now().strftime("%H:%M:%S"), tr("passive refresh"))
        self.command_line.set_values("bc250-detect --keep", tr_format("tool {state}", state=tr("ready" if tool_ready else "missing")))
        self.persistence_line.set_values(
            tr("Enabled at boot" if enabled else "Disabled") if persistent_available else tr("Not detected"),
            tr_format("{state} · config {config}", state=runtime_text, config=tr("present" if config_exists else "not installed")) if persistent_available else tr("Not detected"),
        )

        self.disable_service_button.setProperty("serviceEnabled", enabled)
        process_running = self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning
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
