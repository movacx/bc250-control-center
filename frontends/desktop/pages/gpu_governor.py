from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bc250cc.application.gpu.diagnostics import (
    DiagnosticText,
    compact_diagnostic_path,
    present_gpu_diagnostics,
)
from bc250cc.application.gpu.range_policy import (
    RangeEvidence,
    RangeNotice,
    high_oc_voltage_gaps,
    validate_gpu_range,
)
from bc250cc.application.gpu.runtime import RuntimeText, present_gpu_runtime
from bc250cc.application.gpu.safe_points import SafePointRow, build_safe_point_plan
from bc250cc.application.gpu.safety import SafetyMessage, present_gpu_safety
from bc250cc.application.gpu.service_action import plan_gpu_service_action
from bc250cc.application.gpu.telemetry import (
    TelemetryText,
    format_bytes,
    present_gpu_telemetry,
)
from bc250cc.application.gpu.voltage_apply import plan_voltage_apply
from bc250cc.application.gpu.voltage_lab_presentation import (
    VoltageLabText,
    present_voltage_lab,
)
from bc250cc.application.gpu.voltage_lab_state import (
    build_voltage_lab_state,
    voltage_for_level,
)
from bc250cc.application.gpu.voltage_table import build_voltage_table_plan
from bc250cc.application.preparation.gpu_dependency_plan import (
    DEFAULT_PREPARATION_COMPONENTS,
    GpuDependencyPlan,
    build_gpu_dependency_plan,
)
from bc250cc.domain.gpu.oberon import OBERON_SAFE_PROFILES
from bc250cc.domain.gpu.profiles import (
    default_cyan_profiles,
    profiles_for_allowed_range,
)
from bc250cc.infrastructure.gpu.governor_toml import (
    CUSTOM_VOLTAGE_MAX_MV,
    CUSTOM_VOLTAGE_MIN_MV,
    GOVERNOR_DEFAULT_VOLTAGES,
    OBERON_SAFE_VOLTAGE_MIN_MV,
    SUPPORTED_VOLTAGE_LEVELS,
    VOLTAGE_BOOST_START_MHZ,
)

from ..components.async_tools import AsyncRefresh, BackgroundExecutor
from ..components.buttons import WrappingButton as QPushButton
from ..components.dialogs import enable_adaptive_dialog
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
from ..components.system_setup_controls import (
    MEMORY_OPTIONS,
    is_bazzite_host,
    update_memory_controls,
)
from ..components.widgets import IconBadge, InfoDialog, PillLabel, apply_shadow, icon
from ..core.action_session import ActionSession
from ..core.external_links import open_external_url, open_local_file
from ..core.gfx1013_presenter import present_gfx1013
from ..core.operation_gate import OperationGate
from ..core.state import state_cache_for
from ..core.voltage_keypad_guard import (
    clear_voltage_keypad_state,
    voltage_keypad_edit_active,
)
from ..i18n import count_label, tr, tr_format
from ..theme import COLORS, application_stylesheet


def _dict(value):
    if hasattr(value, "to_dict"):
        return value.to_dict()
    try:
        return dict(value or {})
    except (TypeError, ValueError):
        return {}


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _integer(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _format_bytes(value) -> str:
    return format_bytes(value)


class GpuSummaryItem(QFrame):
    """One compact value inside the shared GPU telemetry strip."""

    def __init__(
        self,
        label: str,
        value: str,
        detail: str,
        icon_name: str,
        background: str,
        parent=None,
        *,
        compact: bool = False,
    ):
        super().__init__(parent)
        self.setProperty("gpuSummaryItem", True)
        if compact:
            self.setProperty("compactVoltageSummaryItem", True)
        self.setMinimumHeight(56 if compact else 68)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row = QHBoxLayout(self)
        if compact:
            row.setContentsMargins(8, 6, 8, 6)
        else:
            row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(7 if compact else 10)
        row.addWidget(
            IconBadge(
                icon_name, background, 26 if compact else 30, radius=7 if compact else 8
            )
        )
        text = QVBoxLayout()
        text.setSpacing(0)
        self.label = QLabel(tr(label))
        self.label.setWordWrap(True)
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


class GpuSummaryStrip(QFrame):
    """Low-profile GPU summary that expands across the complete viewport."""

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
            GpuSummaryItem(
                "Governor",
                "Checking",
                "service and boot state",
                "settings_blue",
                COLORS["blue_soft"],
            ),
            GpuSummaryItem(
                "GPU SCLK",
                "-- MHz",
                "real-time core clock",
                "gpu_purple",
                COLORS["purple_soft"],
            ),
            GpuSummaryItem(
                "Active range",
                "--",
                "runtime D-Bus target",
                "compute_blue",
                COLORS["blue_soft"],
            ),
            GpuSummaryItem(
                "GPU load",
                "-- %",
                "passive utilization",
                "activity_purple",
                COLORS["purple_soft"],
            ),
            GpuSummaryItem(
                "Temperature",
                "-- °C",
                "GPU edge sensor",
                "warning_orange",
                COLORS["orange_soft"],
            ),
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


class DependencyPreparationDialog(QDialog):
    """Visible, distro-aware setup chooser for both supported governors."""

    def __init__(
        self,
        tools: dict,
        selected_governor: str,
        parent=None,
        *,
        controller=None,
    ):
        super().__init__(parent)
        self.setObjectName("DependencyPreparationDialog")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(application_stylesheet())
        self.setWindowTitle(tr("Prepare BC250 system"))
        self.setModal(True)
        self.action = ""
        self.governor = ""
        self.selected_components: set[str] = set()
        self.memory_policy = "current"
        self.memory_ttm_gib = 0
        self.tools = _dict(tools)
        self.controller = controller
        self.component_capabilities = _dict(self.tools.get("prepare_components"))
        self.governor_states = _dict(self.tools.get("supported_gpu_governors"))
        enable_adaptive_dialog(
            self,
            preferred_width=780,
            preferred_height=610,
            minimum_width=560,
            minimum_height=500,
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        panel = QFrame()
        panel.setObjectName("ControlDialogCard")
        apply_shadow(panel, blur=34, y=10, alpha=55)
        outer.addWidget(panel)

        root = QVBoxLayout(panel)
        root.setContentsMargins(22, 18, 22, 16)
        root.setSpacing(12)

        heading = QHBoxLayout()
        heading.setSpacing(12)
        heading.addWidget(
            IconBadge("download_blue", COLORS["blue_soft"], 40, radius=11)
        )
        heading_copy = QVBoxLayout()
        heading_copy.setSpacing(3)
        title = QLabel(tr("Prepare BC250 system"))
        title.setProperty("dialogTitle", True)
        subtitle = QLabel(
            tr("Install what you need and choose the features you want to use.")
        )
        subtitle.setProperty("dialogBody", True)
        subtitle.setWordWrap(False)
        heading_copy.addWidget(title)
        heading_copy.addWidget(subtitle)
        heading.addLayout(heading_copy, 1)
        close = QPushButton()
        close.setObjectName("DialogClose")
        close.setIcon(icon("close_gray"))
        close.setFixedSize(34, 34)
        close.setToolTip(tr("Close"))
        close.clicked.connect(self.reject)
        heading.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(heading)

        system = QFrame()
        system.setProperty("dependencySystemBar", True)
        system_row = QHBoxLayout(system)
        system_row.setContentsMargins(12, 8, 10, 8)
        system_row.setSpacing(9)
        system_row.addWidget(
            IconBadge("shield_green", COLORS["green_soft"], 26, radius=7)
        )
        distribution = str(self.tools.get("os_label") or tr("Unknown distribution"))
        family = str(self.tools.get("os_family") or tr("Unknown family"))
        system_identity = distribution
        if family.lower() not in distribution.lower():
            system_identity = f"{distribution} · {family}"
        system_text = QLabel(
            tr_format("Detected system: {distribution}", distribution=system_identity)
        )
        system_text.setProperty("dependencySystemText", True)
        system_text.setWordWrap(False)
        system_row.addWidget(system_text, 1)
        system_row.addWidget(
            PillLabel(
                "Immutable" if self.tools.get("os_immutable") else "Detected",
                "orange" if self.tools.get("os_immutable") else "green",
            )
        )
        root.addWidget(system)

        section_nav = QHBoxLayout()
        section_nav.setSpacing(6)
        self.section_buttons = []
        self.section_stack = QStackedWidget()
        section_labels = [
            ("components", "Components"),
            ("compatibility", "Compatibility and governors"),
        ]
        if bool(_dict(self.tools.get("quick_access")).get("supported")):
            section_labels.append(("decky", "Decky Loader"))
        section_labels.append(("drivers", "Drivers"))
        self.section_keys = [key for key, _label in section_labels]
        for index, (_key, label) in enumerate(section_labels):
            display_label = tr(label)
            button = QPushButton(display_label)
            button.setCheckable(True)
            button.setProperty("dependencySectionTab", True)
            button.setToolTip(tr(label))
            button.clicked.connect(
                lambda _checked=False, page=index: self._select_dependency_section(page)
            )
            section_nav.addWidget(button, 1)
            self.section_buttons.append(button)
        root.addLayout(section_nav)
        root.addWidget(self.section_stack, 1)

        components_page = QWidget()
        components_layout = QVBoxLayout(components_page)
        components_layout.setContentsMargins(0, 0, 0, 0)
        components_layout.setSpacing(10)

        automatic = QFrame()
        automatic.setProperty("dependencyActionTile", True)
        automatic.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        automatic_layout = QHBoxLayout(automatic)
        automatic.setProperty("dependencyLeadTile", True)
        automatic_layout.setContentsMargins(14, 11, 12, 11)
        automatic_layout.setSpacing(10)
        automatic_layout.addWidget(
            IconBadge("settings_blue", COLORS["blue_soft"], 34, radius=9)
        )
        automatic_copy = QVBoxLayout()
        automatic_copy.setSpacing(2)
        automatic_title = QLabel(tr("Automatic setup"))
        automatic_title.setProperty("sectionTitle", True)
        detected_family = str(self.tools.get("os_family") or "")
        if detected_family == "steamos":
            automatic_text = tr(
                "Install or update the SteamOS user-space/runtime components, Cyan, UMR and BC-250 tools. The high-impact amdgpu/initramfs compatibility repair stays a separate explicit action."
            )
        elif detected_family in {"debian", "ubuntu"}:
            automatic_text = tr(
                "Prepare the Debian/Ubuntu runtime and selected GPU governor. Optional UMR, 40CU, CPU and PWM tools remain explicit selections below."
            )
        else:
            automatic_text = tr(
                "Install or update all required BC250 components. With Cyan selected, its configuration and frequency-reporting fix are prepared now. Prepare does not start the governor: use Enable service afterward to start it now and at every boot."
            )
        automatic_detail = QLabel(
            "Runtime · GPU"
            if detected_family in {"debian", "ubuntu"}
            else "GPU · CPU · 40CU · PWM"
        )
        automatic_detail.setProperty("sectionSubtitle", True)
        automatic_detail.setWordWrap(False)
        automatic_detail.setToolTip(automatic_text)
        automatic_copy.addWidget(automatic_title)
        automatic_copy.addWidget(automatic_detail)
        automatic_layout.addLayout(automatic_copy, 1)
        auto_button = QPushButton(tr("Prepare selected"))
        auto_button.setObjectName("PrimaryAction")
        auto_button.setProperty("dependencyPrepareButton", True)
        auto_button.clicked.connect(lambda: self._choose("prepare", "auto"))
        self.auto_button = auto_button
        automatic_layout.addWidget(auto_button)
        components_layout.addWidget(automatic)

        self.component_panel = self._component_selector()
        components_layout.addWidget(self.component_panel)
        components_layout.addWidget(self._memory_component_card())
        self.section_stack.addWidget(components_page)

        advanced_content = QWidget()
        advanced_layout = QVBoxLayout(advanced_content)
        advanced_layout.setContentsMargins(0, 0, 6, 0)
        advanced_layout.setSpacing(10)
        advanced_layout.addWidget(self._gfx1013_card())
        advanced_layout.addWidget(
            self._cachyos_kernel_card(
                supported=bool(self.tools.get("masta_bc250_stack_supported"))
            )
        )

        governor_label = QLabel(tr("GPU governor"))
        governor_label.setProperty("sectionTitle", True)
        advanced_layout.addWidget(governor_label)

        governor_grid = QGridLayout()
        governor_grid.setContentsMargins(0, 0, 0, 0)
        governor_grid.setHorizontalSpacing(10)
        governor_grid.setVerticalSpacing(10)
        self.governor_cards = {}
        for column, (identifier, display_name, detail) in enumerate(
            (
                (
                    "cyan-skillfish-governor-smu",
                    "Cyan Skillfish Governor (SMU)",
                    "Recommended backend with D-Bus range control and BC-250 telemetry repair.",
                ),
                (
                    "oberon-governor",
                    "Oberon Governor",
                    "Alternative YAML-based backend. GPU telemetry repair remains a separate compatibility step.",
                ),
            )
        ):
            card = self._governor_card(
                identifier, display_name, detail, identifier == selected_governor
            )
            governor_grid.addWidget(card, 0, column)
            governor_grid.setColumnStretch(column, 1)
            self.governor_cards[identifier] = card
        governor_container = QWidget()
        governor_container.setLayout(governor_grid)
        advanced_layout.addWidget(governor_container)

        governor_container.setToolTip(
            tr(
                "Only one GPU governor can be enabled at a time. Preparing another governor will ask before stopping the active one."
            )
        )
        advanced_layout.addStretch(1)

        advanced_scroll = QScrollArea()
        advanced_scroll.setFrameShape(QFrame.Shape.NoFrame)
        advanced_scroll.setWidgetResizable(True)
        advanced_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        advanced_scroll.setWidget(advanced_content)
        self.section_stack.addWidget(advanced_scroll)
        if bool(_dict(self.tools.get("quick_access")).get("supported")):
            self.section_stack.addWidget(self._quick_access_page())
        self.section_stack.addWidget(self._drivers_page())
        self._select_dependency_section(0)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.addStretch(1)
        cancel = QPushButton(tr("Cancel"))
        cancel.setProperty("compactAction", True)
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        root.addLayout(footer)

    def _select_dependency_section(self, index: int) -> None:
        previous_key = (
            self.section_keys[self.section_stack.currentIndex()]
            if self.section_keys
            and 0 <= self.section_stack.currentIndex() < len(self.section_keys)
            else ""
        )
        self.section_stack.setCurrentIndex(index)
        for button_index, button in enumerate(self.section_buttons):
            button.setChecked(button_index == index)
            button.style().unpolish(button)
            button.style().polish(button)
        if previous_key == "drivers" and hasattr(self, "drivers_page"):
            self.drivers_page.set_updates_active(False)
        if self.section_keys[index] == "drivers" and hasattr(self, "drivers_page"):
            self.drivers_page.set_updates_active(True)

    def _drivers_page(self) -> QWidget:
        """Embed driver inventory where system preparation already lives."""
        if self.controller is None:
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(0, 0, 0, 0)
            note = QLabel(
                tr(
                    "Driver inventory is loaded when this dialog is opened from the application."
                )
            )
            note.setProperty("sectionSubtitle", True)
            note.setWordWrap(True)
            layout.addWidget(note)
            layout.addStretch(1)
            return page
        from .drivers import DriversPage

        self.drivers_page = DriversPage(self.controller, embedded=True)
        return self.drivers_page

    def _component_selector(self) -> QFrame:
        panel = QFrame()
        panel.setProperty("dependencyActionTile", True)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        panel.setStyleSheet(f"""
            QCheckBox[componentSwitch='true'] {{
                min-height: 28px; spacing: 9px; color: {COLORS["text"]};
                font-size: 12px; font-weight: 650;
            }}
            QCheckBox[componentSwitch='true']::indicator {{
                width: 18px; height: 18px; border-radius: 5px;
                border: 1px solid {COLORS["border_strong"]};
                background: {COLORS["control_pressed"]};
            }}
            QCheckBox[componentSwitch='true']::indicator:checked {{
                background: {COLORS["blue"]}; border-color: {COLORS["blue"]};
            }}
            QCheckBox[componentSwitch='true']::indicator:disabled {{ opacity: 0.65; }}
        """)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel(tr("Components to prepare"))
        title.setProperty("sectionTitle", True)
        header.addWidget(title, 1)
        self.component_summary = PillLabel("", "blue")
        header.addWidget(self.component_summary)
        layout.addLayout(header)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(3)
        self.component_switches: dict[str, QCheckBox] = {}
        components = (
            ("runtime", "Base dependencies", True, False),
            ("governor", "Selected GPU governor", True, True),
            ("cpu_oc", "CPU OC tools", True, True),
            ("core_unlock", "CPU Core Unlock source", True, True),
            ("umr", "UMR database", True, True),
            ("cu_manager", "40CU manager", True, True),
            ("fan_pwm", "NCT sensors and PWM", True, True),
        )
        family = str(self.tools.get("os_family") or "")
        debian_family = family in {"debian", "ubuntu"}
        for index, (key, label, checked, enabled) in enumerate(components):
            capability = _dict(self.component_capabilities.get(key))
            available = bool(capability.get("available", True))
            switch_label = tr(label)
            if capability.get("installed"):
                switch_label = tr_format("{component} · Ready", component=switch_label)
            switch = QCheckBox(switch_label)
            switch.setProperty("componentSwitch", True)
            switch.setProperty("componentInstalled", bool(capability.get("installed")))
            # UMR is not packaged by every Debian/Ubuntu release. Its fallback
            # installs LLVM and builds from source, so optional hardware tools
            # must be an explicit selection instead of a surprising default.
            default_checked = checked and (
                not debian_family or key in {"runtime", "governor"}
            )
            switch.setChecked(default_checked and available)
            switch.setEnabled(enabled and available)
            detail_text = tr(str(capability.get("detail") or ""))
            if capability.get("reboot"):
                detail_text = (
                    detail_text + " " + tr("A reboot may be required.")
                ).strip()
            if capability.get("installed"):
                detail_text = (
                    detail_text
                    + " "
                    + tr(
                        "Already prepared; selecting it checks for updates and repairs missing files."
                    )
                ).strip()
            if debian_family and key in {"umr", "cu_manager"}:
                detail_text = (
                    detail_text
                    + " "
                    + tr(
                        "On Debian/Ubuntu, UMR may need a large LLVM toolchain and a source build. Select it only when preparing Compute Units."
                    )
                ).strip()
            if not available:
                detail_text = (
                    detail_text + " " + tr("Unavailable on the detected system.")
                ).strip()
            if detail_text:
                switch.setToolTip(detail_text)
            switch.toggled.connect(self._update_component_summary)
            grid.addWidget(switch, index // 2, index % 2)
            self.component_switches[key] = switch
        self.component_switches["cu_manager"].toggled.connect(
            self._sync_component_dependencies
        )
        self.component_switches["umr"].toggled.connect(
            self._sync_component_dependencies
        )
        layout.addLayout(grid)
        panel.setToolTip(
            tr(
                "Select only the tools this system needs. Dangerous hardware actions remain separate and are never enabled by these switches."
            )
        )
        self._update_component_summary()
        return panel

    def _update_component_summary(self) -> None:
        selected = {
            key for key, switch in self.component_switches.items() if switch.isChecked()
        }
        self.selected_components = selected
        self.component_summary.setText(
            tr_format("{count} selected", count=len(selected))
        )
        if hasattr(self, "auto_button"):
            self.auto_button.setText(
                tr_format("Prepare selected ({count})", count=len(selected))
            )
            runtime_ready = self.component_switches.get("runtime")
            self.auto_button.setEnabled(
                bool(selected) and bool(runtime_ready and runtime_ready.isChecked())
            )

    def _sync_component_dependencies(self) -> None:
        manager = self.component_switches.get("cu_manager")
        umr = self.component_switches.get("umr")
        if manager is None or umr is None:
            return
        sender = self.sender()
        if sender is manager and manager.isChecked() and not umr.isChecked():
            umr.setChecked(True)
        elif sender is umr and not umr.isChecked() and manager.isChecked():
            manager.setChecked(False)
        self._update_component_summary()

    def _memory_component_card(self) -> QFrame:
        """Build the one explicit Bazzite memory and TTM boot workflow."""
        state = _dict(self.tools.get("memory_runtime"))
        self._memory_state = state
        card = QFrame()
        card.setProperty("dependencyActionTile", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(9)
        header.addWidget(IconBadge("memory_green", COLORS["green_soft"], 30, radius=8))
        copy = QVBoxLayout()
        copy.setSpacing(1)
        title = QLabel(tr("Memory & Swap"))
        title.setProperty("sectionTitle", True)
        zram = (
            _format_bytes(state.get("zram_total_bytes"))
            if state.get("zram_active")
            else tr("Disabled")
        )
        zswap = tr("Active") if state.get("zswap_enabled") is True else tr("Disabled")
        backing = (
            _format_bytes(state.get("backing_swap_total_bytes"))
            if state.get("backing_swap_active")
            else tr("None")
        )
        detail = QLabel(
            tr_format(
                "Active now: ZRAM {zram} · disk swap {backing} · ZSWAP {zswap}",
                zram=zram,
                backing=backing,
                zswap=zswap,
            )
        )
        detail.setProperty("sectionSubtitle", True)
        copy.addWidget(title)
        copy.addWidget(detail)
        header.addLayout(copy, 1)
        actionable = is_bazzite_host(self.tools)
        header.addWidget(
            PillLabel(
                tr("Bazzite") if actionable else tr("Testing"),
                "green" if actionable else "gray",
            )
        )
        layout.addLayout(header)

        controls = QGridLayout()
        controls.setContentsMargins(0, 2, 0, 0)
        controls.setHorizontalSpacing(10)
        controls.setVerticalSpacing(8)
        swap_label = QLabel(tr("Swap and compression"))
        swap_label.setProperty("fieldLabel", True)
        controls.addWidget(swap_label, 0, 0)
        self.memory_policy_combo = QComboBox()
        self.memory_policy_combo.setProperty("settingsCombo", True)
        for label, value in (
            ("Keep Bazzite default (ZRAM)", "current"),
            ("Recommended · ZRAM + 16 GiB emergency swap", "zram-swap-16"),
            ("Advanced · ZSWAP + 16 GiB swapfile", "zswap-16"),
            ("Advanced heavy loads · ZSWAP + 32 GiB swapfile", "zswap-32"),
        ):
            self.memory_policy_combo.addItem(tr(label), value)
        controls.addWidget(self.memory_policy_combo, 0, 1)
        self.memory_swap_apply_button = QPushButton(tr("Apply Swap"))
        self.memory_swap_apply_button.setObjectName("PrimaryAction")
        self.memory_swap_apply_button.clicked.connect(
            lambda: self._choose("memory_swap", "")
        )
        controls.addWidget(self.memory_swap_apply_button, 0, 2)

        ttm_label = QLabel(tr("Dynamic GPU Memory Limit (TTM)"))
        ttm_label.setProperty("fieldLabel", True)
        controls.addWidget(ttm_label, 1, 0)
        self.ttm_limit_combo = QComboBox()
        self.ttm_limit_combo.setProperty("settingsCombo", True)
        self.ttm_limit_combo.addItem(tr("Keep current TTM limit"), 0)
        self.ttm_limit_combo.addItem(tr("Kernel default (remove BC250 TTM limit)"), -1)
        current_gib = round(_integer(state.get("ttm_limit_bytes"), 0) / (1024**3))
        for target in (8, 10, 12):
            self.ttm_limit_combo.addItem(
                tr_format("Limit GPU allocations to {size} GiB", size=target), target
            )
        if current_gib in {8, 10, 12}:
            self.ttm_limit_combo.setCurrentIndex((8, 10, 12).index(current_gib) + 2)
        controls.addWidget(self.ttm_limit_combo, 1, 1)
        self.memory_ttm_apply_button = QPushButton(tr("Apply TTM"))
        self.memory_ttm_apply_button.setObjectName("PrimaryAction")
        self.memory_ttm_apply_button.clicked.connect(
            lambda: self._choose("memory_ttm", "")
        )
        controls.addWidget(self.memory_ttm_apply_button, 1, 2)
        controls.setColumnStretch(1, 1)
        layout.addLayout(controls)

        self.memory_policy_combo.currentIndexChanged.connect(
            self._update_memory_apply_availability
        )
        self.ttm_limit_combo.currentIndexChanged.connect(
            self._update_memory_apply_availability
        )
        self._update_memory_apply_availability()
        return card

    def _update_memory_apply_availability(self) -> None:
        if not hasattr(self, "memory_swap_apply_button"):
            return
        if update_memory_controls(self, self.tools):
            return
        actionable = str(self.tools.get("os_family") or "") == "bazzite"
        policy = str(self.memory_policy_combo.currentData() or "current")
        swap_selected = policy != "current"
        if policy == "current":
            swap_selected = bool(
                self._memory_state.get("backing_swap_active")
                or self._memory_state.get("zswap_enabled") is True
            )
        ttm_selected = _integer(self.ttm_limit_combo.currentData(), 0) != 0
        self.memory_swap_apply_button.setEnabled(actionable and swap_selected)
        self.memory_ttm_apply_button.setEnabled(actionable and ttm_selected)
        if not actionable:
            tooltip = tr("This memory workflow is currently validated only on Bazzite.")
            self.memory_swap_apply_button.setToolTip(tooltip)
            self.memory_ttm_apply_button.setToolTip(tooltip)

    def _show_memory_policy_preview(self) -> None:
        selected = str(self.memory_policy_combo.currentData() or "current")
        descriptions = {
            "current": "The current ZRAM, ZSWAP and backing-swap configuration would be preserved.",
            "zram": "ZRAM would remain the compressed in-memory swap device; no disk swapfile would be created.",
            "zram-swap-16": "ZRAM remains primary and a verified 16 GiB disk swapfile is used only as an emergency fallback.",
            "zswap-16": "A verified 16 GiB backing swapfile would be required before enabling ZSWAP and disabling ZRAM.",
            "zswap-32": "A verified 32 GiB backing swapfile would be required before enabling ZSWAP and disabling ZRAM.",
        }
        family = str(self.tools.get("os_family") or "Linux")
        message = (
            tr(descriptions[selected])
            + "\n\n"
            + tr_format(
                "Detected platform: {platform}. The final action remains unavailable until its transactional rollback backend is validated.",
                platform=family,
            )
        )
        InfoDialog(
            "Memory configuration preview",
            message,
            icon_name="memory_green",
            eyebrow="MEMORY AND SWAP",
            notice="No swap, boot or kernel setting will be changed.",
            tone="green",
            parent=self,
        ).exec()

    def _ttm_memory_card(self) -> QFrame:
        """Present reviewed TTM targets beside GPU compatibility controls."""
        state = _dict(self.tools.get("memory_runtime"))
        limit_bytes = max(0, _integer(state.get("ttm_limit_bytes"), 0))
        current_gib = round(limit_bytes / (1024**3)) if limit_bytes else 0
        card = QFrame()
        card.setProperty("dependencyActionTile", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(9)
        header.addWidget(IconBadge("vram_gray", COLORS["purple_soft"], 30, radius=8))
        copy = QVBoxLayout()
        copy.setSpacing(1)
        title = QLabel(tr("GPU memory limit (TTM)"))
        title.setProperty("sectionTitle", True)
        current = tr_format(
            "Current runtime limit: {limit}",
            limit=(f"{current_gib} GiB" if current_gib else "--"),
        )
        detail = QLabel(current)
        detail.setProperty("sectionSubtitle", True)
        detail.setToolTip(
            tr("TTM limits managed GPU pages; it is not a guaranteed VRAM reservation.")
        )
        copy.addWidget(title)
        copy.addWidget(detail)
        header.addLayout(copy, 1)
        header.addWidget(PillLabel(tr("Preview only"), "blue"))
        layout.addLayout(header)

        controls = QHBoxLayout()
        controls.setSpacing(7)
        self.ttm_limit_combo = QComboBox()
        self.ttm_limit_combo.setProperty("settingsCombo", True)
        self.ttm_limit_combo.addItem(tr("Keep current configuration"), 0)
        for target in (8, 10, 12):
            self.ttm_limit_combo.addItem(
                tr_format("{size} GiB TTM limit", size=target), target
            )
        if current_gib in {8, 10, 12}:
            self.ttm_limit_combo.setCurrentIndex((8, 10, 12).index(current_gib) + 1)
        controls.addWidget(self.ttm_limit_combo, 1)
        review = QPushButton(tr("Review requirements"))
        review.setProperty("compactAction", True)
        review.clicked.connect(self._show_ttm_preview)
        controls.addWidget(review)
        layout.addLayout(controls)
        return card

    def _show_ttm_preview(self) -> None:
        target = _integer(self.ttm_limit_combo.currentData(), 0)
        if target:
            pages = target * (1024**3) // 4096
            selection = tr_format(
                "Selected target: {size} GiB ({pages} pages).", size=target, pages=pages
            )
        else:
            selection = tr("The current kernel argument would be preserved.")
        InfoDialog(
            "GPU memory limit preview",
            selection
            + "\n\n"
            + tr(
                "This is a TTM page-management ceiling, not a fixed VRAM allocation. Applying it will require a distribution-specific boot transaction and reboot verification."
            ),
            icon_name="vram_gray",
            eyebrow="GPU MEMORY POLICY",
            notice="No swap, boot or kernel setting will be changed.",
            tone="purple",
            parent=self,
        ).exec()

    def _quick_access_page(self) -> QScrollArea:
        """Build the explicit, optional SteamOS/Bazzite/CachyOS Decky page.

        Decky is intentionally not represented as a regular preparation
        component: it is a separate third-party root-plugin environment and
        needs a dedicated confirmation path.
        """
        inventory = _dict(self.tools.get("quick_access"))
        ready = bool(inventory.get("ready"))
        decky_detected = bool(inventory.get("decky_detected"))
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(12)

        card = QFrame()
        card.setProperty("dependencyActionTile", True)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(10)

        header = QHBoxLayout()
        header.addWidget(IconBadge("compute_blue", COLORS["blue_soft"], 38, radius=10))
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel(tr("Game Mode Quick Access (Beta)"))
        title.setProperty("sectionTitle", True)
        subtitle_text = tr(
            "Optional Game Mode controls for safe live GPU, CU, system-fan and saved CPU-profile actions."
        )
        subtitle = QLabel("GPU · CU · PWM · CPU")
        subtitle.setProperty("sectionSubtitle", True)
        subtitle.setToolTip(subtitle_text)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)
        if ready:
            status = PillLabel(tr("Ready"), "green")
        elif decky_detected:
            status = PillLabel(tr("Decky detected"), "blue")
        else:
            status = PillLabel(tr("Decky not installed"), "orange")
        header.addWidget(status)
        card_layout.addLayout(header)

        if ready:
            detail_text = "Quick Access is ready. Restart Game Mode or reload Decky if the panel is not visible yet."
        elif not decky_detected:
            detail_text = "Decky is optional. It is never installed by generic dependency preparation."
        elif not bool(inventory.get("decky_plugin_root_safe", True)):
            detail_text = "Decky uses a symbolic-link plugin directory. Choose a real plugin directory before installing BC250 Quick Access."
        else:
            detail_text = "Decky is detected, but the BC250 Quick Access plugin or its protected helper needs installation or repair."
        detail = QLabel(tr(detail_text))
        detail.setProperty("warningText" if not ready else "sectionSubtitle", True)
        detail.setWordWrap(True)
        card_layout.addWidget(detail)

        actions = QHBoxLayout()
        actions.addStretch(1)
        install = QPushButton(
            tr(
                "Install / repair BC250 Quick Access"
                if decky_detected
                else "Install Decky + Quick Access (Beta)"
            )
        )
        install.setObjectName("PrimaryAction")
        install.setToolTip(
            tr(
                "Beta boundary: after your explicit confirmation in this dialog, this workflow downloads the official Decky stable installer, displays its SHA-256 in the terminal, then installs the local BC250 panel. It never changes GPU voltage, custom clocks, services, boot settings or hardware state."
            )
        )
        install.clicked.connect(
            lambda: self._choose(
                "quick_access_plugin"
                if decky_detected
                else "quick_access_install_decky",
                "",
            )
        )
        actions.addWidget(install)
        card_layout.addLayout(actions)

        layout.addWidget(card)
        layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll

    def _gfx1013_card(self) -> QFrame:
        state = _dict(self.tools.get("gfx1013_compute"))
        presentation = present_gfx1013(state)

        card = QFrame()
        card.setProperty("dependencyActionTile", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(IconBadge("compute_blue", COLORS["blue_soft"], 34, radius=9))
        title = QLabel(tr("GFX1013 async compute"))
        title.setProperty("sectionTitle", True)
        header.addWidget(title, 1)

        compact_status = {
            "Kernel half ready": "Kernel partial",
        }.get(presentation.status, presentation.status)
        status = PillLabel(tr(compact_status), presentation.tone)
        header.addWidget(status)
        layout.addLayout(header)

        complete_detail = " ".join(tr(part) for part in presentation.detail)

        card.setToolTip(complete_detail)
        reviewed = tr_format(
            "Reviewed upstream: {version} · {commit}",
            version=str(state.get("reviewed_version") or "0.2.0-alpha"),
            commit=str(state.get("reviewed_commit") or "")[:7],
        )
        card.setToolTip(f"{complete_detail}\n{reviewed}".strip())

        actions = QHBoxLayout()
        actions.setSpacing(7)
        if presentation.steamos_actions:
            compatibility = QPushButton(tr(presentation.compatibility_action))
            compatibility.setProperty("dependencyGfxAction", True)
            compatibility.setProperty("dependencyGfxPrimary", True)
            compatibility.clicked.connect(lambda: self._choose("steamos_compat", ""))
            actions.addWidget(compatibility, 1)
            radv = QPushButton(tr("2 · Install / repair Mesa RADV"))
            radv.setProperty("dependencyGfxAction", True)
            radv.setEnabled(bool(state.get("steamos_kernel_ready")))
            radv.clicked.connect(
                lambda: self._choose("steamos_graphics_install", "")
            )
            actions.addWidget(radv, 1)
            status_action = QPushButton(tr("Check full stack"))
            status_action.setProperty("dependencyGfxAction", True)
            status_action.clicked.connect(
                lambda: self._choose("steamos_graphics_status", "")
            )
            actions.addWidget(status_action, 1)
        if presentation.fedora_actions:
            if not bool(state.get("dryhopped_installed")):
                install = QPushButton(tr("Install / update"))
                install.setProperty("dependencyGfxAction", True)
                install.setProperty("dependencyGfxPrimary", True)
                install.clicked.connect(
                    lambda: self._choose("gfx1013_fedora_install", "")
                )
                actions.addWidget(install, 1)
            else:
                uninstall = QPushButton(tr("Uninstall"))
                uninstall.setProperty("dangerAction", True)
                uninstall.setProperty("dependencyGfxAction", True)
                uninstall.clicked.connect(
                    lambda: self._choose("gfx1013_fedora_uninstall", "")
                )
                actions.addWidget(uninstall, 1)
        if presentation.bazzite_actions:
            if not bool(state.get("bazzite_async_installed")):
                install = QPushButton(tr("Install / update"))
                install.setProperty("dependencyGfxAction", True)
                install.setProperty("dependencyGfxPrimary", True)
                install.setEnabled(bool(state.get("direct_installer_allowed")))
                if not install.isEnabled():
                    install.setToolTip(complete_detail)
                install.clicked.connect(
                    lambda: self._choose("gfx1013_bazzite_install", "")
                )
                actions.addWidget(install, 1)
            else:
                repair = QPushButton(tr("Repair / update"))
                repair.setProperty("dependencyGfxAction", True)
                repair.setProperty("dependencyGfxPrimary", True)
                repair.setEnabled(bool(state.get("direct_installer_allowed")))
                repair.clicked.connect(
                    lambda: self._choose("gfx1013_bazzite_install", "")
                )
                actions.addWidget(repair, 1)
                uninstall = QPushButton(tr("Uninstall"))
                uninstall.setProperty("dangerAction", True)
                uninstall.setProperty("dependencyGfxAction", True)
                uninstall.clicked.connect(
                    lambda: self._choose("gfx1013_bazzite_uninstall", "")
                )
                actions.addWidget(uninstall, 1)
                status_action = QPushButton(tr("Check status"))
                status_action.setProperty("dependencyGfxAction", True)
                status_action.clicked.connect(
                    lambda: self._choose("gfx1013_bazzite_status", "")
                )
                actions.addWidget(status_action, 1)
        upstream = QPushButton(tr("Open upstream project"))
        upstream.setProperty("dependencyGfxAction", True)
        upstream.clicked.connect(self._open_gfx1013_upstream)
        actions.addWidget(upstream, 1)
        layout.addLayout(actions)
        return card

    def _cachyos_kernel_card(self, *, supported: bool) -> QFrame:
        """Expose the reviewed external BC-250 kernel as an explicit choice."""
        card = QFrame()
        card.setProperty("dependencyActionTile", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(9)

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(IconBadge("shield_green", COLORS["green_soft"], 34, radius=9))
        copy = QVBoxLayout()
        copy.setSpacing(2)
        title = QLabel(tr("CachyOS BC-250 kernel"))
        title.setProperty("sectionTitle", True)
        subtitle = QLabel(
            tr(
                "MastaG external kernel · telemetry, GFX clock range, NCT and GFX1013 fixes"
            )
        )
        subtitle.setProperty("sectionSubtitle", True)
        subtitle.setWordWrap(True)
        copy.addWidget(title)
        copy.addWidget(subtitle)
        header.addLayout(copy, 1)
        header.addWidget(PillLabel(tr("External / reboot"), "orange"))
        layout.addLayout(header)

        warning = QLabel(
            tr(
                "Optional only. This adds MastaG's unsigned pacman repository (Optional TrustAll) and installs linux-cachyos-bc250 plus headers. Your normal CachyOS kernel is kept as the boot fallback."
            )
        )
        warning.setProperty("warningText", True)
        warning.setWordWrap(True)
        layout.addWidget(warning)

        actions = QHBoxLayout()
        actions.addStretch(1)
        upstream = QPushButton(tr("Open upstream project"))
        upstream.setProperty("dependencyGfxAction", True)
        upstream.clicked.connect(
            lambda: open_external_url("https://github.com/MastaG/linux-cachyos-bc250")
        )
        actions.addWidget(upstream)
        install = QPushButton(tr("Install BC-250 kernel"))
        install.setObjectName("PrimaryAction")
        install.setEnabled(supported)
        if not supported:
            install.setToolTip(
                tr("Available only on plain Arch Linux or CachyOS")
            )
        install.clicked.connect(lambda: self._choose("cachyos_bc250_kernel", ""))
        actions.addWidget(install)
        layout.addLayout(actions)
        return card

    def _open_gfx1013_upstream(self) -> None:
        state = _dict(self.tools.get("gfx1013_compute"))
        url = str(
            state.get("upstream_url")
            or "https://github.com/DryhoppedIPA/bc250-gfx1013-fix"
        )
        opened, _error = open_external_url(url)
        if opened:
            return
        InfoDialog(
            tr("Could not open upstream project"),
            tr(
                "The upstream project link could not be opened by this desktop session."
            ),
            tone="orange",
            parent=self,
        ).exec()

    def _governor_card(
        self, identifier: str, display_name: str, detail: str, selected: bool
    ) -> QFrame:
        state = _dict(self.governor_states.get(identifier))
        detected = bool(state.get("detected"))
        active = bool(state.get("active"))
        enabled = bool(state.get("enabled"))
        card = QFrame()
        card.setProperty("metricTile", True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 13, 14, 13)
        layout.setSpacing(8)
        header = QHBoxLayout()
        name = QLabel(tr(display_name))
        name.setProperty("sectionTitle", True)
        header.addWidget(name, 1)
        if active:
            status = PillLabel("Active", "green")
        elif enabled:
            status = PillLabel("Enabled", "blue")
        elif detected:
            status = PillLabel("Installed", "blue")
        else:
            status = PillLabel("Not installed", "gray")
        header.addWidget(status)
        layout.addLayout(header)
        compact_detail = (
            "D-Bus · BC250 telemetry"
            if identifier == "cyan-skillfish-governor-smu"
            else "YAML · alternative backend"
        )
        description = QLabel(tr(compact_detail))
        description.setProperty("sectionSubtitle", True)
        description.setWordWrap(False)
        description.setToolTip(tr(detail))
        layout.addWidget(description)
        if selected:
            card.setProperty("dependencyGovernorSelected", True)
        layout.addStretch(1)
        actions = QHBoxLayout()
        prepare = QPushButton(tr("Install / update"))
        prepare.setProperty("compactAction", True)
        prepare.setProperty("dependencyGovernorAction", True)
        prepare.clicked.connect(lambda: self._choose("prepare", identifier))
        actions.addWidget(prepare, 1)
        remove = QPushButton(tr("Uninstall"))
        remove.setProperty("dangerAction", True)
        remove.setProperty("dependencyGovernorAction", True)
        remove.setEnabled(detected)
        if not detected:
            remove.setToolTip(tr("Not installed"))
        remove.clicked.connect(lambda: self._choose("remove", identifier))
        actions.addWidget(remove, 1)
        layout.addLayout(actions)
        return card

    def _choose(self, action: str, governor: str) -> None:
        self.action = action
        self.governor = governor
        if action == "memory_swap":
            self.memory_policy = str(
                self.memory_policy_combo.currentData() or "current"
            )
            self.memory_ttm_gib = 0
        elif action == "memory_ttm":
            self.memory_policy = "preserve"
            self.memory_ttm_gib = _integer(self.ttm_limit_combo.currentData(), 0)
        if action == "prepare" and hasattr(self, "component_switches"):
            self.selected_components = {
                key
                for key, switch in self.component_switches.items()
                if switch.isChecked()
            }
        self.accept()


class VoltageLabToolbar(QFrame):
    """Compact laboratory toolbar that stacks controls before they can clip."""

    refresh_requested = pyqtSignal()
    back_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("voltageLabToolbar", True)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._layout_mode = ""

        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(11, 8, 11, 8)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(7)
        self.icon_badge = IconBadge("bolt_blue", COLORS["orange_soft"], 32, radius=9)

        self.copy_host = QWidget()
        self.copy_host.setMinimumWidth(0)
        copy = QVBoxLayout(self.copy_host)
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(0)
        title = QLabel(tr("Voltage laboratory"))
        title.setWordWrap(True)
        title.setProperty("voltageToolbarTitle", True)
        copy.addWidget(title)

        self.status = PillLabel("LIVE HARDWARE", "orange")

        refresh = QPushButton(tr("Refresh"))
        refresh.setProperty("compactAction", True)
        refresh.setProperty("voltageToolbarButton", True)
        refresh.setFixedHeight(36)
        refresh.setMinimumWidth(108)
        refresh.setIcon(icon("refresh_gray"))
        refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh.clicked.connect(self.refresh_requested)
        self.refresh_button = refresh

        back = QPushButton(tr("Return to GPU control"))
        back.setObjectName("PrimaryAction")
        back.setProperty("voltageToolbarButton", True)
        back.setFixedHeight(36)
        back.setMinimumWidth(176)
        back.setIcon(icon("collapse_gray"))
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(self.back_requested)
        self.back_button = back
        self._reflow(force=True)

    def _reflow(self, *, force: bool = False) -> None:
        width = self.width()
        mode = "narrow" if 0 < width < 420 else "compact" if 0 < width < 680 else "wide"
        if mode == self._layout_mode and not force:
            return
        for widget in (
            self.icon_badge,
            self.copy_host,
            self.status,
            self.refresh_button,
            self.back_button,
        ):
            self.grid.removeWidget(widget)
        if mode in {"compact", "narrow"}:
            self.grid.addWidget(self.icon_badge, 0, 0, Qt.AlignmentFlag.AlignTop)
            self.grid.addWidget(self.copy_host, 0, 1)
            self.grid.addWidget(self.status, 1, 0, 1, 2, Qt.AlignmentFlag.AlignLeft)
            if mode == "narrow":
                self.grid.addWidget(self.refresh_button, 2, 0, 1, 2)
                self.grid.addWidget(self.back_button, 3, 0, 1, 2)
            else:
                self.grid.addWidget(self.refresh_button, 2, 0)
                self.grid.addWidget(self.back_button, 2, 1)
            self.refresh_button.setMinimumWidth(0)
            self.back_button.setMinimumWidth(0)
            self.refresh_button.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            self.back_button.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            self.grid.setColumnStretch(0, 1)
            self.grid.setColumnStretch(1, 1)
        else:
            self.grid.addWidget(self.icon_badge, 0, 0)
            self.grid.addWidget(self.copy_host, 0, 1)
            self.grid.addWidget(self.status, 0, 2)
            self.grid.addWidget(self.refresh_button, 0, 3)
            self.grid.addWidget(self.back_button, 0, 4)
            self.refresh_button.setMinimumWidth(108)
            self.back_button.setMinimumWidth(176)
            self.refresh_button.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
            )
            self.back_button.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
            )
            self.grid.setColumnStretch(0, 0)
            self.grid.setColumnStretch(1, 1)
            for column in range(2, 5):
                self.grid.setColumnStretch(column, 0)
        self._layout_mode = mode
        self.updateGeometry()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reflow()


class VoltageSummaryStrip(QFrame):
    """Compute-Units-inspired overview for the voltage workspace."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("gpuSummaryStrip", True)
        self.setProperty("voltageSummaryStrip", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        apply_shadow(self, blur=16, y=3, alpha=10)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(6, 6, 6, 6)
        self.grid.setHorizontalSpacing(6)
        self.grid.setVerticalSpacing(6)
        self.items = [
            GpuSummaryItem(
                "Safe-points",
                "--",
                "active TOML entries",
                "compute_blue",
                COLORS["blue_soft"],
                compact=True,
            ),
            GpuSummaryItem(
                "Active profile",
                "--",
                "closest defined curve",
                "gpu_purple",
                COLORS["purple_soft"],
                compact=True,
            ),
            GpuSummaryItem(
                "Maximum voltage",
                "-- mV",
                "advanced voltage editor range",
                "bolt_blue",
                COLORS["orange_soft"],
                compact=True,
            ),
            GpuSummaryItem(
                "Runtime range",
                "--",
                "restored after restart",
                "settings_blue",
                COLORS["blue_soft"],
                compact=True,
            ),
            GpuSummaryItem(
                "Safety state",
                "Checking",
                "monotonic validation",
                "shield_green",
                COLORS["green_soft"],
                compact=True,
            ),
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


class VoltageProfileButton(QPushButton):
    def __init__(
        self, level: int, title: str, detail: str, tone: str = "blue", parent=None
    ):
        super().__init__(parent)
        self.level = int(level)
        self.setCheckable(True)
        self.setProperty("voltageProfileButton", True)
        self.setProperty("profileTone", tone)
        self.setText(f"{tr(title)}\n{tr(detail)}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(58)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


class VoltageGridHeaderCell(QFrame):
    def __init__(self, title: str, detail: str, parent=None):
        super().__init__(parent)
        self.setProperty("voltageGridHeader", True)
        self.setFixedHeight(46)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(7, 5, 7, 5)
        layout.setSpacing(0)
        title_label = QLabel(tr(title))
        title_label.setProperty("voltageGridHeaderTitle", True)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail_label = QLabel(tr(detail))
        detail_label.setProperty("voltageGridHeaderDetail", True)
        detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        layout.addWidget(detail_label)


class VoltageGridCell(QFrame):
    def __init__(
        self, value: str, detail: str = "", *, role: str = "neutral", parent=None
    ):
        super().__init__(parent)
        self.setProperty("voltageGridCell", True)
        self.setProperty("cellRole", role)
        self.setFixedHeight(52)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(0)
        self.value = QLabel(tr(value))
        self.value.setProperty("voltageGridValue", True)
        self.value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail = QLabel(tr(detail))
        self.detail.setProperty("voltageGridDetail", True)
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail.setWordWrap(True)
        layout.addWidget(self.value)
        if detail:
            layout.addWidget(self.detail)

    def set_values(
        self, value: str, detail: str | None = None, *, role: str | None = None
    ) -> None:
        self.value.setText(tr(value))
        if detail is not None:
            self.detail.setText(tr(detail))
            self.detail.setVisible(bool(detail))
        if role is not None and role != self.property("cellRole"):
            self.setProperty("cellRole", role)
            self.style().unpolish(self)
            self.style().polish(self)
            self.update()


class VoltageCurveGrid(QFrame):
    """A readable safe-point matrix modelled after the Compute Units topology grid."""

    HEADERS = (
        ("Frequency", "safe-point"),
        ("Current", "active TOML"),
        ("Original", "governor default"),
        ("Added voltage", "vs governor default"),
        ("Custom control", "all active points"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("voltageCurveGrid", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(7, 7, 7, 7)
        self.grid.setHorizontalSpacing(5)
        self.grid.setVerticalSpacing(5)
        self.added_cells: dict[int, VoltageGridCell] = {}
        self._reset_headers()

    def _reset_headers(self) -> None:
        for column, (title, detail) in enumerate(self.HEADERS):
            self.grid.addWidget(VoltageGridHeaderCell(title, detail), 0, column)
        stretches = (3, 3, 3, 3, 4)
        for column, stretch in enumerate(stretches):
            self.grid.setColumnStretch(column, stretch)

    def clear_points(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self.added_cells = {}
        self._reset_headers()

    @staticmethod
    def _added_voltage_copy(added: int | None) -> tuple[str, str, str]:
        if added is None:
            return "n/a", "no governor base", "muted"
        if added > 0:
            return f"+{added} mV", "above default", "positive"
        if added < 0:
            return f"{added} mV", "below default", "warning"
        return "0 mV", "governor default", "safe"

    def add_point(
        self,
        row: int,
        *,
        frequency: int,
        current: int,
        original: int | None,
        added: int | None,
        editor: QWidget | None,
        custom_available: bool,
    ) -> None:
        visual_row = int(row) + 1
        frequency_cell = VoltageGridCell(
            f"{frequency} MHz",
            "custom editable" if custom_available else "read only",
            role="frequency",
        )
        current_cell = VoltageGridCell(
            f"{current} mV" if current else "Not set", "current curve", role="neutral"
        )
        original_cell = VoltageGridCell(
            f"{original} mV" if original is not None else "Not available",
            "packaged default" if original is not None else "unknown safe-point",
            role="safe" if original is not None else "muted",
        )
        added_value, added_detail, added_role = self._added_voltage_copy(added)
        added_cell = VoltageGridCell(added_value, added_detail, role=added_role)
        self.grid.addWidget(frequency_cell, visual_row, 0)
        self.grid.addWidget(current_cell, visual_row, 1)
        self.grid.addWidget(original_cell, visual_row, 2)
        self.grid.addWidget(added_cell, visual_row, 3)

        editor_cell = QFrame()
        editor_cell.setProperty("voltageGridCell", True)
        editor_cell.setProperty("cellRole", "custom" if custom_available else "muted")
        editor_cell.setFixedHeight(52)
        editor_layout = QHBoxLayout(editor_cell)
        editor_layout.setContentsMargins(8, 5, 8, 5)
        editor_layout.setSpacing(0)
        if editor is not None:
            editor.setProperty("voltageEditor", True)
            editor.setFixedHeight(34)
            editor.setMinimumWidth(116)
            editor_layout.addWidget(editor, 0, Qt.AlignmentFlag.AlignCenter)
        else:
            locked = QLabel(tr("Locked"))
            locked.setProperty("voltageGridDetail", True)
            locked.setAlignment(Qt.AlignmentFlag.AlignCenter)
            editor_layout.addWidget(locked, 1)
        self.grid.addWidget(editor_cell, visual_row, 4)

        self.added_cells[int(frequency)] = added_cell

    def update_point(self, frequency: int, added: int | None) -> None:
        added_cell = self.added_cells.get(int(frequency))
        if added_cell is not None:
            added_value, added_detail, added_role = self._added_voltage_copy(added)
            added_cell.set_values(added_value, added_detail, role=added_role)


class FrequencyField(QFrame):
    """Direct numeric GPU range field with no slider or increment rail."""

    def __init__(self, label: str, hint: str, value: int, parent=None):
        super().__init__(parent)
        self.setProperty("frequencyField", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.minimum = 0
        self.maximum = 9999
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(10)
        copy = QVBoxLayout()
        copy.setSpacing(1)
        title = QLabel(tr(label))
        title.setProperty("fieldLabel", True)
        title.setWordWrap(True)
        title.setMinimumWidth(0)
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
        unit = QLabel("MHz")
        unit.setProperty("frequencyUnit", True)
        row.addWidget(unit, 0, Qt.AlignmentFlag.AlignVCenter)

    def value(self) -> int:
        return _integer(self.input.text(), 0)

    def setValue(self, value: int) -> None:
        self.input.setText(str(int(value)))

    def set_limits(self, minimum: int, maximum: int) -> None:
        self.minimum = int(minimum)
        self.maximum = max(self.minimum, int(maximum))
        self.input.setValidator(QIntValidator(self.minimum, self.maximum, self.input))


class RuntimeStat(QFrame):
    """Compact status tile used for the runtime state summary."""

    def __init__(self, label: str, value: str, detail: str = "", parent=None):
        super().__init__(parent)
        self.setProperty("runtimeStatCard", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(72)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)
        label_widget = QLabel(tr(label))
        label_widget.setWordWrap(True)
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


class DynamicSafetyNotice(QFrame):
    """Safety banner whose title, message, and tone can change after refresh."""

    def __init__(
        self,
        title: str,
        message: str,
        *,
        tone: str = "blue",
        compact: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._tone = ""
        self._compact = bool(compact)
        if self._compact:
            self.setProperty("compactSafetyNotice", True)
        row = QHBoxLayout(self)
        if self._compact:
            row.setContentsMargins(9, 2, 9, 2)
        else:
            row.setContentsMargins(13, 11, 13, 11)
        row.setSpacing(7 if self._compact else 10)
        # IconBadge has a fixed 8 px inset; below 30 px the actual SVG becomes
        # too small and looks empty. Keep the banner thin while preserving a
        # readable icon.
        badge_size = 30 if self._compact else 34
        self.badge = IconBadge(
            "info_blue",
            COLORS["blue_soft"],
            badge_size,
            radius=8 if self._compact else 10,
        )
        row.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignVCenter)
        text = QVBoxLayout()
        text.setSpacing(1 if self._compact else 2)
        self.title = QLabel(tr(title))
        self.title.setProperty("noticeTitle", True)
        self.title.setWordWrap(True)
        self.title.setMinimumWidth(0)
        self.body = QLabel(tr(message))
        self.body.setProperty("noticeBody", True)
        self.body.setWordWrap(True)
        text.addWidget(self.title)
        text.addWidget(self.body)
        row.addLayout(text, 1)
        self.set_notice(title, message, tone=tone)

    def set_notice(self, title: str, message: str, *, tone: str = "blue") -> None:
        tone = tone if tone in {"blue", "orange", "red"} else "orange"
        self.title.setText(tr(title))
        self.body.setText(tr(message))
        if tone == self._tone:
            return
        self._tone = tone
        self.setProperty("safetyNotice", tone)
        self.badge.setParent(None)
        layout = self.layout()
        success_notice = tone == "blue" and any(
            token in str(title).lower()
            for token in ("safe mode", "profiles ready", "protected")
        )
        self.badge = IconBadge(
            "check_green" if success_notice else "info_blue" if tone == "blue" else "warning_orange",
            COLORS["blue_soft"]
            if tone == "blue"
            else COLORS["red_soft"]
            if tone == "red"
            else COLORS["orange_soft"],
            30 if self._compact else 34,
            radius=8 if self._compact else 10,
        )
        layout.insertWidget(0, self.badge, 0, Qt.AlignmentFlag.AlignVCenter)
        self.badge.show()
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


class GpuGovernorPage(QWidget):
    """Complete GPU control studio using the validated cyan-skillfish governor backend."""

    GOVERNOR_CONFIG_PATH = Path("/etc/cyan-skillfish-governor-smu/config.toml")
    OBERON_CONFIG_PATH = Path("/etc/oberon-config.yaml")
    SELECTED_RANGE_FLOOR = 1000

    CYAN_PROFILE_VALUES = tuple(
        (profile.label, f"{profile.minimum_mhz}–{profile.maximum_mhz} MHz", (profile.minimum_mhz, profile.maximum_mhz))
        for profile in default_cyan_profiles()
    )
    OBERON_PROFILE_VALUES = (
        ("Balanced", "1000–1500 MHz", OBERON_SAFE_PROFILES[0]),
        ("Gaming", "1000–1850 MHz", OBERON_SAFE_PROFILES[1]),
        ("Benchmark", "2000 MHz", OBERON_SAFE_PROFILES[2]),
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
        self.setProperty("gpuGovernorPage", True)
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
        self._voltage_spinboxes: dict[int, QSpinBox] = {}
        self._voltage_editable_frequencies: set[int] = set()
        self._voltage_profile_frequencies: set[int] = set()
        self._voltage_detected_level = 0
        self._last_operation_summary = "No hardware command has been executed."
        self._detailed_diagnostics = False
        self._profile_backend = ""
        self._cyan_compatibility_dirty = False

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

        self.voltage_lab_page = self._build_voltage_lab_page()
        self.page_stack.addWidget(self.voltage_lab_page)

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

    def _build_configuration_card(self) -> SectionCard:
        card = SectionCard(
            "GPU configuration",
            "Select a validated profile or stage an explicit D-Bus range. Every hardware change is reviewed before execution.",
            icon_name="settings_blue",
            icon_background=COLORS["blue_soft"],
            status=("Safe mode", "green"),
        )
        self.configuration_status = card.status

        self.safety_notice = DynamicSafetyNotice(
            "Safe mode enabled",
            "Every active TOML safe-point is visible. Points above 2000 MHz will appear automatically when they are enabled in the TOML.",
            tone="blue",
            compact=True,
        )
        self.safety_notice.setMaximumHeight(64)
        self.safety_notice.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.safety_notice.title.setProperty("prominentNoticeTitle", True)
        self.safety_notice.body.setProperty("prominentNoticeBody", True)
        notice_style = self.safety_notice.title.style()
        notice_style.unpolish(self.safety_notice.title)
        notice_style.polish(self.safety_notice.title)
        body_style = self.safety_notice.body.style()
        body_style.unpolish(self.safety_notice.body)
        body_style.polish(self.safety_notice.body)
        card.body.addWidget(self.safety_notice)

        self.cyan_compatibility_panel = QFrame()
        self.cyan_compatibility_panel.setProperty("compactPanel", True)
        compatibility_layout = QGridLayout(self.cyan_compatibility_panel)
        compatibility_layout.setContentsMargins(12, 10, 12, 10)
        compatibility_layout.setHorizontalSpacing(10)
        compatibility_layout.setVerticalSpacing(8)
        compatibility_title = QLabel(tr("Cyan kernel compatibility"))
        compatibility_title.setWordWrap(True)
        compatibility_title.setProperty("fieldLabel", True)
        compatibility_layout.addWidget(compatibility_title, 0, 0, 1, 2)
        self.cyan_set_method = QComboBox()
        self.cyan_set_method.addItem(tr("Governor method: SMU"), "smu")
        self.cyan_set_method.addItem(tr("Governor method: Kernel"), "kernel")
        self.cyan_usage_method = QComboBox()
        for usage_method in ("busy-flag", "process", "kernel"):
            self.cyan_usage_method.addItem(
                f"gpu-usage.method: {usage_method}", usage_method
            )
        self.cyan_fix_metrics = QCheckBox()
        self.cyan_fix_frequency = QCheckBox()
        self._retranslate_cyan_compatibility_labels()
        self.cyan_set_method.currentIndexChanged.connect(
            lambda _index: setattr(self, "_cyan_compatibility_dirty", True)
        )
        self.cyan_usage_method.currentIndexChanged.connect(
            lambda _index: setattr(self, "_cyan_compatibility_dirty", True)
        )
        self.cyan_fix_metrics.toggled.connect(
            lambda _checked: setattr(self, "_cyan_compatibility_dirty", True)
        )
        self.cyan_fix_frequency.toggled.connect(
            lambda _checked: setattr(self, "_cyan_compatibility_dirty", True)
        )
        compatibility_layout.addWidget(self.cyan_set_method, 1, 0)
        compatibility_layout.addWidget(self.cyan_usage_method, 1, 1)
        compatibility_layout.addWidget(self.cyan_fix_metrics, 2, 0)
        compatibility_layout.addWidget(self.cyan_fix_frequency, 2, 1)
        self.apply_cyan_compatibility = QPushButton(tr("Apply compatibility"))
        self.apply_cyan_compatibility.setProperty("compactAction", True)
        self.apply_cyan_compatibility.clicked.connect(self._request_cyan_compatibility)
        compatibility_layout.addWidget(self.apply_cyan_compatibility, 3, 0, 1, 2)
        compatibility_layout.setColumnStretch(0, 1)
        compatibility_layout.setColumnStretch(1, 1)
        card.body.addWidget(self.cyan_compatibility_panel)

        profile_panel = QFrame()
        profile_panel.setProperty("compactPanel", True)
        profile_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        profile_layout = QVBoxLayout(profile_panel)
        profile_layout.setContentsMargins(12, 10, 12, 10)
        profile_layout.setSpacing(8)
        profile_label = QLabel(tr("Operating profile"))
        profile_label.setProperty("fieldLabel", True)
        profile_layout.addWidget(profile_label)

        self.preset_grid = QGridLayout()
        self.preset_grid.setContentsMargins(0, 0, 0, 0)
        self.preset_grid.setHorizontalSpacing(8)
        self.preset_grid.setVerticalSpacing(6)
        self.preset_group = QButtonGroup(self)
        self.preset_group.setExclusive(True)
        self.preset_buttons: list[PresetButton] = []
        for title, summary, payload in self.PROFILE_VALUES:
            button = PresetButton(title, summary, payload)
            button.setProperty("gpuFrequencyPreset", True)
            button.setMinimumHeight(56)
            button.clicked.connect(
                lambda checked, b=button: self._select_preset(b) if checked else None
            )
            self.preset_group.addButton(button)
            self.preset_buttons.append(button)
        self._reflow_presets(1400)
        profile_layout.addLayout(self.preset_grid)
        card.body.addWidget(profile_panel)

        # Keep the frequency fields visually separated from the profile panel
        # without restoring the large explanatory block removed below.
        card.body.addSpacing(5)
        self.range_fields_grid = QGridLayout()
        self.range_fields_grid.setContentsMargins(0, 0, 0, 0)
        self.range_fields_grid.setHorizontalSpacing(10)
        self.range_fields_grid.setVerticalSpacing(10)
        self.minimum_control = FrequencyField(
            "Minimum frequency",
            "Governor floor applied through the validated D-Bus interface.",
            500,
        )
        self.maximum_control = FrequencyField(
            "Maximum frequency",
            "The ceiling must exist in the active TOML safe-point table.",
            1500,
        )
        self.range_fields = [self.minimum_control, self.maximum_control]
        self.minimum_control.input.textChanged.connect(self._mark_custom_range)
        self.maximum_control.input.textChanged.connect(self._mark_custom_range)
        self._reflow_range_fields(1400)
        card.body.addLayout(self.range_fields_grid)

        # Retain the label as a non-rendered update target for compatibility
        # with the refresh path; the verbose range legend is intentionally not
        # part of the compact configuration card anymore.
        self.range_recommendation = QLabel()
        self.range_recommendation.hide()

        # Anchor the configuration actions to the card's lower edge.  The
        # telemetry card remains untouched; the shared grid row supplies the
        # height, while this stretch absorbs only the configuration column's
        # spare space so both action feet finish on the same baseline.
        card.body.addStretch(1)
        self.range_footer = QFrame()
        self.range_footer.setProperty("configurationFooter", True)
        apply_row = QGridLayout(self.range_footer)
        # Keep the footer baseline aligned with untouched telemetry while
        # lifting the two controls slightly away from the card edge.
        apply_row.setContentsMargins(0, 0, 0, 6)
        apply_row.setSpacing(8)
        self.range_actions_grid = apply_row
        self._range_action_mode = ""
        self.use_active_button = QPushButton(tr("Use active range"))
        self.use_active_button.setProperty("compactAction", True)
        self.use_active_button.clicked.connect(self._use_active_range)
        apply_row.addWidget(self.use_active_button, 0, 0)
        self.apply_range_button = QPushButton(tr("Review and apply range"))
        self.apply_range_button.setObjectName("PrimaryAction")
        self.apply_range_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.apply_range_button.setProperty("gamepadEntry", True)
        self.apply_range_button.clicked.connect(self._request_custom_range)
        for button in (self.use_active_button, self.apply_range_button):
            button.setMinimumHeight(40)
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
        apply_row.addWidget(self.apply_range_button, 0, 2)
        apply_row.setColumnStretch(1, 1)
        card.body.addWidget(self.range_footer)
        return card

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

    def _build_fixed_safe_point_panel(self) -> QFrame:
        """Advanced fixed-frequency controls kept out of the normal GPU workspace."""

        fixed_panel = QFrame()
        fixed_panel.setProperty("compactPanel", True)
        fixed_panel.setProperty("advancedSafePointPanel", True)
        fixed_layout = QVBoxLayout(fixed_panel)
        fixed_layout.setContentsMargins(12, 10, 12, 10)
        fixed_layout.setSpacing(8)
        fixed_header = QHBoxLayout()
        fixed_copy = QVBoxLayout()
        fixed_copy.setSpacing(1)
        fixed_title = QLabel(tr("TOML safe-point laboratory"))
        self.fixed_title = fixed_title
        fixed_title.setProperty("fieldLabel", True)
        fixed_title.setWordWrap(True)
        fixed_hint = QLabel(
            tr(
                "Inspect every active safe-point, including +2000 MHz entries, with conservative voltage validation."
            )
        )
        self.fixed_hint = fixed_hint
        fixed_hint.setProperty("fieldHint", True)
        fixed_hint.setWordWrap(True)
        fixed_copy.addWidget(fixed_title)
        fixed_copy.addWidget(fixed_hint)
        fixed_header.addLayout(fixed_copy, 1)
        fixed_layout.addLayout(fixed_header)

        fixed_actions = QGridLayout()
        self.fixed_actions = fixed_actions
        fixed_actions.setHorizontalSpacing(8)
        fixed_actions.setVerticalSpacing(8)
        fixed_actions.setColumnStretch(0, 1)
        fixed_actions.setColumnStretch(1, 1)

        active_range_label = QLabel(tr("Active range"))
        active_range_label.setProperty("fieldLabel", True)
        active_range_label.setWordWrap(True)
        fixed_actions.addWidget(active_range_label, 0, 0)
        toml_actions_label = QLabel(tr("TOML configuration"))
        self.config_actions_label = toml_actions_label
        toml_actions_label.setProperty("fieldLabel", True)
        toml_actions_label.setWordWrap(True)
        fixed_actions.addWidget(toml_actions_label, 0, 1)

        self.oc_frequency = QComboBox()
        self.oc_frequency.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.oc_frequency.currentIndexChanged.connect(self._update_selected_safe_point)
        fixed_actions.addWidget(self.oc_frequency, 1, 0)
        self.safe_point_detail = QLabel(tr("Refresh to load safe-points."))
        self.safe_point_detail.hide()
        self.high_points_button = QPushButton(tr("Enable +2000 MHz TOML points"))
        self.high_points_button.setProperty("dangerAction", True)
        self.high_points_button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.high_points_button.setToolTip(
            tr(
                "This edits only the TOML safe-point blocks above 2000 MHz and validates the complete file. These frequencies are experimental, are not guaranteed stable, and can crash the display or system. This does not reload Cyan or change the live GPU range; use Apply active range explicitly after selecting a point."
            )
        )
        self.high_points_button.clicked.connect(self._request_high_points_toggle)
        fixed_actions.addWidget(self.high_points_button, 2, 1)
        self.telemetry_guide_button = QPushButton(
            tr("Open Oberon Governor repository")
        )
        self.telemetry_guide_button.setProperty("dangerAction", True)
        self.telemetry_guide_button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.telemetry_guide_button.clicked.connect(self._open_telemetry_guide)
        self.telemetry_guide_button.hide()
        fixed_actions.addWidget(self.telemetry_guide_button, 2, 1)

        self.open_toml_button = QPushButton(tr("Open config.toml"))
        self.open_toml_button.setProperty("compactAction", True)
        self.open_toml_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.open_toml_button.setProperty("gamepadEntry", True)
        self.open_toml_button.setToolTip(
            tr(
                "Open the governor TOML in the system's default text or code editor. "
                "Saving may require administrator privileges."
            )
        )
        self.open_toml_button.clicked.connect(self._open_governor_config)
        fixed_actions.addWidget(self.open_toml_button, 1, 1)

        self.apply_selected_range_button = QPushButton(
            tr("Apply active range · select a ceiling")
        )
        self.apply_selected_range_button.setObjectName("PrimaryAction")
        self.apply_selected_range_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.apply_selected_range_button.setProperty("gamepadEntry", True)
        self.apply_selected_range_button.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.apply_selected_range_button.setEnabled(False)
        self.apply_selected_range_button.clicked.connect(
            self._request_selected_safe_point_range
        )
        fixed_actions.addWidget(self.apply_selected_range_button, 2, 0)
        fixed_layout.addLayout(fixed_actions)
        return fixed_panel

    def _build_metrics_card(self) -> SectionCard:
        card = SectionCard(
            "Live GPU telemetry",
            "Read-only sensor data refreshed from amdgpu, the governor backend, and the existing performance service.",
            icon_name="gpu_purple",
            icon_background=COLORS["purple_soft"],
            status=("Passive", "green"),
        )
        self.metrics_status = card.status

        self.metrics_grid = QGridLayout()
        self.metrics_grid.setContentsMargins(0, 0, 0, 0)
        self.metrics_grid.setHorizontalSpacing(10)
        self.metrics_grid.setVerticalSpacing(10)
        self.sclk_metric = MetricTile(
            "Core clock",
            "-- MHz",
            "",
            icon_name="gpu_purple",
            icon_background=COLORS["purple_soft"],
            compact=True,
        )
        self.voltage_metric = MetricTile(
            "GPU voltage",
            "-- mV",
            "",
            icon_name="bolt_blue",
            icon_background=COLORS["orange_soft"],
            compact=True,
        )
        self.temperature_metric = MetricTile(
            "Temperature",
            "-- °C",
            "",
            icon_name="warning_orange",
            icon_background=COLORS["orange_soft"],
            compact=True,
        )
        self.utilization_metric = MetricTile(
            "GPU load",
            "-- %",
            "",
            icon_name="activity_purple",
            icon_background=COLORS["purple_soft"],
            compact=True,
        )
        self.mclk_metric = MetricTile(
            "Memory clock",
            "-- MHz",
            "",
            icon_name="compute_blue",
            icon_background=COLORS["blue_soft"],
            compact=True,
        )
        self.vram_metric = MetricTile(
            "VRAM usage",
            "--",
            "",
            icon_name="vram_gray",
            icon_background="neutral_soft",
            compact=True,
        )
        self.metric_tiles = [
            self.sclk_metric,
            self.voltage_metric,
            self.temperature_metric,
            self.utilization_metric,
            self.mclk_metric,
            self.vram_metric,
        ]
        for tile in self.metric_tiles:
            tile.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            tile.setMinimumHeight(58)
        self._reflow_metric_tiles(1400)
        card.body.addLayout(self.metrics_grid)

        note = QLabel(tr("Passive readings · hardware changes require confirmation."))
        note.setProperty("fieldHint", True)
        note.setWordWrap(True)
        card.body.addWidget(note)
        return card

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

    def _build_voltage_lab_page(self) -> QWidget:
        page = QWidget()
        page.setProperty("voltageLabPage", True)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        self.voltage_scroll = scroll
        content = QWidget()
        self.voltage_content = content
        configure_responsive_scroll_area(scroll, content)
        content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 6, 12, 14)
        layout.setSpacing(8)
        scroll.setWidget(content)
        page_layout.addWidget(scroll)

        self.voltage_header = VoltageLabToolbar()
        self.voltage_header.refresh_requested.connect(self._refresh_voltage_lab)
        self.voltage_header.back_requested.connect(self._close_voltage_lab)
        layout.addWidget(self.voltage_header)

        self.voltage_notice = DynamicSafetyNotice(
            "Stop every 3D workload before applying",
            "A timestamped backup is created, the governor restarts, and the previous D-Bus range is restored only after confirmation.",
            tone="orange",
            compact=True,
        )
        layout.addWidget(self.voltage_notice)

        self.voltage_summary = VoltageSummaryStrip()
        self.voltage_summary_items = self.voltage_summary.items
        layout.addWidget(self.voltage_summary)

        self.voltage_workspace_host = QWidget()
        self.voltage_workspace = QGridLayout(self.voltage_workspace_host)
        self.voltage_workspace.setContentsMargins(0, 0, 0, 0)
        self.voltage_workspace.setHorizontalSpacing(8)
        self.voltage_workspace.setVerticalSpacing(8)
        layout.addWidget(self.voltage_workspace_host)

        oberon_card = SectionCard(
            "Oberon endpoint diagnostics",
            "Oberon uses exactly two YAML operating points. Their values are shown for diagnosis only.",
            icon_name="shield_green",
            icon_background=COLORS["blue_soft"],
            status=("Read-only", "blue"),
            compact=True,
        )
        self.oberon_voltage_card = oberon_card
        self.oberon_voltage_minimum = StatusLine(
            "Minimum OPP", "--", "YAML endpoint", compact=True
        )
        self.oberon_voltage_maximum = StatusLine(
            "Maximum OPP", "--", "YAML endpoint", compact=True
        )
        self.oberon_voltage_guidance = QLabel(
            tr(
                "These endpoints affect the active Oberon profile. Selecting a different profile restores Oberon's upstream 1000 mV baseline; this page does not offer an unvalidated cross-board voltage curve."
            )
        )
        self.oberon_voltage_guidance.setProperty("fieldHint", True)
        self.oberon_voltage_guidance.setWordWrap(True)
        oberon_card.body.addWidget(self.oberon_voltage_minimum)
        oberon_card.body.addWidget(self.oberon_voltage_maximum)
        oberon_card.body.addWidget(self.oberon_voltage_guidance)
        oberon_card.hide()
        layout.addWidget(oberon_card)

        curve_card = SectionCard(
            "Voltage map",
            "All active TOML safe-points with current, original, added voltage, and custom values.",
            icon_name="compute_blue",
            icon_background=COLORS["blue_soft"],
            status=("Waiting", "gray"),
        )
        curve_card.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.voltage_curve_card = curve_card
        self.voltage_table_status = curve_card.status
        self.voltage_curve_grid = VoltageCurveGrid()
        # Only the five-column voltage matrix is intrinsically wide. Keep its
        # overflow local so the toolbar, safety copy and apply workflow remain
        # visible on compact and translated layouts.
        self.voltage_curve_scroll = QScrollArea()
        self.voltage_curve_scroll.setObjectName("VoltageCurveScroll")
        self.voltage_curve_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.voltage_curve_scroll.setWidgetResizable(True)
        self.voltage_curve_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.voltage_curve_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.voltage_curve_scroll.setMinimumWidth(0)
        self.voltage_curve_scroll.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
        )
        self.voltage_curve_scroll.setWidget(self.voltage_curve_grid)
        self._sync_voltage_curve_scroll_height()
        curve_card.body.addWidget(self.voltage_curve_scroll)

        profiles_card = SectionCard(
            "Voltage profiles",
            "Choose one of three defined voltage levels or unlock every active safe-point for custom editing.",
            icon_name="gpu_purple",
            icon_background=COLORS["purple_soft"],
            status=("Ready", "orange"),
            compact=True,
        )
        profiles_card.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.voltage_controls_card = profiles_card
        self.voltage_controls_status = profiles_card.status

        self.voltage_level_combo = QComboBox()
        self.voltage_level_combo.addItem("Level 0 · governor defaults", 0)
        self.voltage_level_combo.addItem("Level 3 · default +30 mV", 3)
        self.voltage_level_combo.addItem("Level 6 · default +60 mV", 6)
        self.voltage_level_combo.addItem("Custom · all active safe-points", -1)
        self.voltage_level_combo.currentIndexChanged.connect(
            self._voltage_level_changed
        )
        self.voltage_level_combo.hide()

        self.voltage_profile_grid = QGridLayout()
        self.voltage_profile_grid.setContentsMargins(0, 0, 0, 0)
        self.voltage_profile_grid.setHorizontalSpacing(5)
        self.voltage_profile_grid.setVerticalSpacing(5)
        self.voltage_profile_group = QButtonGroup(self)
        self.voltage_profile_group.setExclusive(True)
        profile_specs = [
            (0, "Level 0", "Governor defaults", "green"),
            (3, "Level 3", "+30 mV", "blue"),
            (6, "Level 6", "+60 mV", "orange"),
            (-1, "Custom", "Edit every safe-point", "purple"),
        ]
        self.voltage_profile_buttons: list[VoltageProfileButton] = []
        for level, title, detail, tone in profile_specs:
            button = VoltageProfileButton(level, title, detail, tone)
            button.clicked.connect(
                lambda checked, value=level: (
                    self._select_voltage_profile(value) if checked else None
                )
            )
            self.voltage_profile_group.addButton(button)
            self.voltage_profile_buttons.append(button)
        self._reflow_voltage_profiles(1400)
        profiles_card.body.addLayout(self.voltage_profile_grid)

        self.voltage_level_detail = QLabel(
            "Refresh to compare the selected curve against the active TOML and packaged original voltages."
        )
        self.voltage_level_detail.setProperty("voltageProfileDetail", True)
        self.voltage_level_detail.setWordWrap(True)
        profiles_card.body.addWidget(self.voltage_level_detail)

        workflow_card = SectionCard(
            "Review and apply",
            "Review the selected curve and apply it through the existing validated backend.",
            icon_name="shield_green",
            icon_background=COLORS["green_soft"],
            status=("Armed", "orange"),
            compact=True,
        )
        workflow_card.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.voltage_workflow_card = workflow_card
        self.voltage_workflow_status = workflow_card.status

        workflow_panel = QFrame()
        workflow_panel.setProperty("voltageWorkflowPanel", True)
        workflow_layout = QVBoxLayout(workflow_panel)
        workflow_layout.setContentsMargins(8, 7, 8, 7)
        workflow_layout.setSpacing(6)
        checks = (
            ("1", "Stop games and stress tests"),
            ("2", "Check original voltage and exact added amount"),
            ("3", "Confirm the preserved runtime range"),
        )
        checks_grid = QGridLayout()
        checks_grid.setContentsMargins(0, 0, 0, 0)
        checks_grid.setHorizontalSpacing(5)
        checks_grid.setVerticalSpacing(5)
        for column, (token, copy) in enumerate(checks):
            check_item = QFrame()
            check_item.setProperty("voltageStepItem", True)
            check_item.setFixedHeight(40)
            check_row = QHBoxLayout(check_item)
            check_row.setContentsMargins(6, 5, 6, 5)
            check_row.setSpacing(5)
            badge = QLabel(token)
            badge.setProperty("voltageStepBadge", True)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setFixedSize(22, 22)
            check_label = QLabel(tr(copy))
            check_label.setProperty("voltageStepText", True)
            check_label.setWordWrap(True)
            check_row.addWidget(badge)
            check_row.addWidget(check_label, 1)
            checks_grid.addWidget(check_item, 0, column)
            checks_grid.setColumnStretch(column, 1)
        workflow_layout.addLayout(checks_grid)

        self.voltage_apply_button = QPushButton(tr("Review and apply voltage curve"))
        self.voltage_apply_button.setProperty("dangerAction", True)
        self.voltage_apply_button.setProperty("voltageApplyButton", True)
        self.voltage_apply_button.setProperty("gamepadEntry", True)
        self.voltage_apply_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.voltage_apply_button.setFixedHeight(40)
        self.voltage_apply_button.setIcon(icon("bolt_blue"))
        self.voltage_apply_button.setEnabled(True)
        self.voltage_apply_button.clicked.connect(self._request_apply_voltage_curve)
        workflow_layout.addWidget(self.voltage_apply_button)
        workflow_card.body.addWidget(workflow_panel)

        # Voltage profiles now occupy the former validation-panel position at the bottom.
        layout.addWidget(profiles_card)

        self._reflow_voltage_workspace(1400)
        layout.addStretch(1)
        return page

    def _build_runtime_card(self) -> SectionCard:
        card = SectionCard(
            "Governor runtime",
            "Service state, boot persistence, D-Bus health, active range, and the complete service workflow from the original GUI.",
            icon_name="shield_green",
            icon_background=COLORS["green_soft"],
            status=("Checking", "gray"),
        )

        stats_panel = QFrame()
        self.runtime_stats_panel = stats_panel
        stats_panel.setProperty("compactPanel", True)
        stats_panel_layout = QVBoxLayout(stats_panel)
        stats_panel_layout.setContentsMargins(10, 10, 10, 10)
        stats_panel_layout.setSpacing(0)
        self.runtime_stats_grid = QGridLayout()
        self.runtime_stats_grid.setContentsMargins(0, 0, 0, 0)
        self.runtime_stats_grid.setHorizontalSpacing(10)
        self.runtime_stats_grid.setVerticalSpacing(10)

        self.service_stat = RuntimeStat(
            "Service", "Checking", "cyan-skillfish-governor-smu.service"
        )
        self.boot_stat = RuntimeStat(
            "Boot persistence", "Checking", "systemd UnitFileState"
        )
        self.dbus_stat = RuntimeStat("D-Bus API", "Checking", "runtime range interface")
        self.profile_stat = RuntimeStat("Active range", "--", "current governor target")
        self.points_stat = RuntimeStat(
            "Validated points", "Checking", "active TOML entries"
        )
        self.runtime_stats = [
            self.service_stat,
            self.boot_stat,
            self.dbus_stat,
            self.profile_stat,
            self.points_stat,
        ]
        self._reflow_runtime_stats(1400)
        stats_panel_layout.addLayout(self.runtime_stats_grid)
        card.body.addWidget(stats_panel)

        controls_panel = QFrame()
        self.runtime_controls_panel = controls_panel
        controls_panel.setProperty("compactPanel", True)
        controls_layout = QVBoxLayout(controls_panel)
        controls_layout.setContentsMargins(12, 10, 12, 10)
        controls_layout.setSpacing(8)
        controls_title = QLabel(tr("Governor service actions"))
        controls_title.setWordWrap(True)
        controls_title.setProperty("fieldLabel", True)
        controls_copy = QLabel(
            tr(
                "Enable starts the governor now and at boot. Disable stops it and removes persistence. "
                "Status output is shown inside the application console."
            )
        )
        controls_copy.setProperty("fieldHint", True)
        controls_copy.setWordWrap(True)
        controls_layout.addWidget(controls_title)
        controls_layout.addWidget(controls_copy)

        self.runtime_actions_grid = QGridLayout()
        self.runtime_actions_grid.setContentsMargins(0, 0, 0, 0)
        self.runtime_actions_grid.setHorizontalSpacing(8)
        self.runtime_actions_grid.setVerticalSpacing(8)

        self.enable_button = QPushButton(tr("Enable service"))
        self.enable_button.setProperty("compactAction", True)
        self.enable_button.setIcon(icon("rocket_blue"))
        self.enable_button.clicked.connect(lambda: self._service_action("activar"))

        self.disable_button = QPushButton(tr("Disable service"))
        self.disable_button.setProperty("dangerAction", True)
        self.disable_button.clicked.connect(lambda: self._service_action("desactivar"))

        self.restart_button = QPushButton(tr("Restart service"))
        self.restart_button.setProperty("compactAction", True)
        self.restart_button.setIcon(icon("refresh_gray"))
        self.restart_button.clicked.connect(lambda: self._service_action("reiniciar"))

        self.status_button = QPushButton(tr("View service status"))
        self.status_button.setProperty("compactAction", True)
        self.status_button.clicked.connect(self.read_service_status)

        self.voltage_lab_button = QPushButton(tr("Open voltage lab"))
        self.voltage_lab_button.setProperty("dangerAction", True)
        self.voltage_lab_button.clicked.connect(self.open_voltage_lab)

        self.runtime_action_buttons = [
            self.enable_button,
            self.status_button,
            self.restart_button,
            self.disable_button,
            self.voltage_lab_button,
        ]
        for button in self.runtime_action_buttons:
            button.setMinimumHeight(38)
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
        self._reflow_runtime_actions(1400)
        controls_layout.addLayout(self.runtime_actions_grid)
        card.body.addWidget(controls_panel)
        return card

    def _build_advanced_card(self) -> SectionCard:
        card = SectionCard(
            "Advanced GPU diagnostics",
            "TOML safe-point controls, voltage validation, hardware details, and operation output.",
            icon_name="logs_gray",
            icon_background="neutral_soft",
        )
        card.add_header_button("Clear console", self._clear_console)

        self.advanced_grid = QGridLayout()
        self.advanced_grid.setContentsMargins(0, 0, 0, 0)
        self.advanced_grid.setHorizontalSpacing(12)
        self.advanced_grid.setVerticalSpacing(12)

        self.fixed_safe_point_panel = self._build_fixed_safe_point_panel()

        self.safe_points_panel = QFrame()
        self.safe_points_panel.setProperty("compactPanel", True)
        safe_layout = QVBoxLayout(self.safe_points_panel)
        safe_layout.setContentsMargins(12, 12, 12, 12)
        safe_layout.setSpacing(8)
        safe_header = QLabel(tr("Active TOML safe-points"))
        self.safe_header = safe_header
        safe_header.setProperty("fieldLabel", True)
        safe_header.setWordWrap(True)
        safe_layout.addWidget(safe_header)
        self.points_table = QTableWidget(0, 4)
        self.points_table.setHorizontalHeaderLabels(
            tuple(
                tr(label)
                for label in (
                    "Frequency",
                    "Voltage",
                    "Original voltage",
                    "Role / validation",
                )
            )
        )
        self.points_table.setAlternatingRowColors(True)
        self.points_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.points_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.points_table.verticalHeader().setVisible(False)
        header = self.points_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.points_table.setMinimumHeight(250)
        safe_layout.addWidget(self.points_table, 1)

        self.diagnostics_panel = QFrame()
        self.diagnostics_panel.setProperty("compactPanel", True)
        diagnostics_layout = QVBoxLayout(self.diagnostics_panel)
        diagnostics_layout.setContentsMargins(12, 12, 12, 12)
        diagnostics_layout.setSpacing(8)
        diagnostics_header = QLabel(tr("Governor and hardware contract"))
        diagnostics_header.setProperty("fieldLabel", True)
        diagnostics_header.setWordWrap(True)
        diagnostics_layout.addWidget(diagnostics_header)
        self.device_line = StatusLine("Device", "--", "PCI vendor / device")
        self.driver_line = StatusLine("Driver", "--", "amdgpu path")
        self.config_line = StatusLine("Governor config", "--", "active TOML")
        self.curve_line = StatusLine(
            "Voltage curve", "Checking", "monotonic validation"
        )
        self.missing_line = StatusLine(
            "Missing voltage", "Checking", "safe-points without active voltage"
        )
        self.duplicates_line = StatusLine(
            "Duplicates", "Checking", "duplicate frequency entries"
        )
        self.power_state_line = StatusLine("Power state", "--", "DPM performance level")
        self.last_operation_line = StatusLine(
            "Last operation", "None", self._last_operation_summary
        )
        for line in (
            self.device_line,
            self.driver_line,
            self.config_line,
            self.curve_line,
            self.missing_line,
            self.duplicates_line,
            self.power_state_line,
            self.last_operation_line,
        ):
            diagnostics_layout.addWidget(line)

        self.console_panel = QFrame()
        self.console_panel.setProperty("compactPanel", True)
        console_layout = QVBoxLayout(self.console_panel)
        console_layout.setContentsMargins(12, 12, 12, 12)
        console_layout.setSpacing(8)
        console_header = QLabel(tr("Governor console"))
        console_header.setProperty("fieldLabel", True)
        console_layout.addWidget(console_header)
        self.console = QPlainTextEdit()
        self.console.setObjectName("OperationConsole")
        self.console.setReadOnly(True)
        self.console.setMinimumHeight(230)
        self.console.setPlainText(
            tr("GPU Governor console ready. No hardware command has been executed.")
        )
        console_layout.addWidget(self.console)

        self._reflow_advanced(1400)
        card.body.addLayout(self.advanced_grid)
        self.advanced_status = card.status
        return card

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        active_scroll = (
            self.voltage_scroll
            if self.page_stack.currentWidget() is self.voltage_lab_page
            else self.overview_scroll
        )
        self._reflow(effective_viewport_width(self, active_scroll))

    def _reflow(self, width: int) -> None:
        self._reflow_presets(width)
        self._reflow_range_fields(width)
        self._reflow_range_actions(width)
        self._reflow_metric_tiles(width)
        self._reflow_runtime_stats(width)
        self._reflow_runtime_actions(width)
        self._reflow_advanced(width)
        self._reflow_voltage_summary(width)
        self._reflow_voltage_workspace(width)

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

    def _reflow_presets(self, width: int) -> None:
        if self._profile_backend == "oberon":
            columns = 3 if width >= 620 else 2 if width >= 420 else 1
        else:
            columns = 3 if width >= 620 else 1
        if columns == self._preset_columns and self.preset_grid.count():
            return
        self._preset_columns = columns
        self._clear_grid(self.preset_grid)
        visible_buttons = [
            button for button in self.preset_buttons if not button.isHidden()
        ]
        for index, button in enumerate(visible_buttons):
            self.preset_grid.addWidget(button, index // columns, index % columns)
        for column in range(columns):
            self.preset_grid.setColumnStretch(column, 1)

    def _reflow_range_fields(self, width: int) -> None:
        columns = 2 if width >= 680 else 1
        if columns == self._field_columns and self.range_fields_grid.count():
            return
        self._field_columns = columns
        self._clear_grid(self.range_fields_grid)
        for index, field in enumerate(self.range_fields):
            self.range_fields_grid.addWidget(field, index // columns, index % columns)
        for column in range(columns):
            self.range_fields_grid.setColumnStretch(column, 1)

    def _reflow_range_actions(self, width: int) -> None:
        mode = (
            "oberon"
            if self._profile_backend == "oberon"
            else "wide"
            if width >= 420
            else "stack"
        )
        if mode == self._range_action_mode and self.range_actions_grid.count():
            return
        self._range_action_mode = mode
        self._clear_grid(self.range_actions_grid)
        self.range_actions_grid.setColumnStretch(0, 0)
        self.range_actions_grid.setColumnStretch(1, 0)
        self.range_actions_grid.setColumnStretch(2, 0)
        self.use_active_button.setVisible(mode != "oberon")
        self.apply_range_button.setVisible(True)
        if mode == "oberon":
            self.range_actions_grid.addWidget(self.apply_range_button, 0, 0)
            self.range_actions_grid.setColumnStretch(0, 1)
        elif mode == "wide":
            self.range_actions_grid.addWidget(self.use_active_button, 0, 0)
            self.range_actions_grid.addWidget(self.apply_range_button, 0, 1)
            self.range_actions_grid.setColumnStretch(0, 1)
            self.range_actions_grid.setColumnStretch(1, 1)
        else:
            self.range_actions_grid.addWidget(self.use_active_button, 0, 0)
            self.range_actions_grid.addWidget(self.apply_range_button, 1, 0)
            self.range_actions_grid.setColumnStretch(0, 1)

    def _reflow_metric_tiles(self, width: int) -> None:
        if not hasattr(self, "metrics_grid"):
            return
        columns = 3 if width >= 1080 else 2 if width >= 560 else 1
        if columns == self._metric_columns and self.metrics_grid.count():
            return
        self._metric_columns = columns
        self._clear_grid(self.metrics_grid)
        for row in range(len(self.metric_tiles)):
            self.metrics_grid.setRowStretch(row, 0)
        for index, tile in enumerate(self.metric_tiles):
            self.metrics_grid.addWidget(tile, index // columns, index % columns)
        for column in range(columns):
            self.metrics_grid.setColumnStretch(column, 1)
        rows = (len(self.metric_tiles) + columns - 1) // columns
        for row in range(rows):
            self.metrics_grid.setRowStretch(row, 1)

    def _reflow_voltage_summary(self, width: int) -> None:
        if not hasattr(self, "voltage_summary"):
            return
        columns = (
            5 if width >= 1040 else 3 if width >= 680 else 2 if width >= 420 else 1
        )
        if columns == self._voltage_summary_columns:
            return
        self._voltage_summary_columns = columns
        self.voltage_summary.set_columns(columns)

    def _reflow_voltage_profiles(self, width: int) -> None:
        if not hasattr(self, "voltage_profile_grid") or not hasattr(
            self, "voltage_profile_buttons"
        ):
            return
        columns = 4 if width >= 850 else 2 if width >= 480 else 1
        if (
            columns == self._voltage_profile_columns
            and self.voltage_profile_grid.count()
        ):
            return
        self._voltage_profile_columns = columns
        self._clear_grid(self.voltage_profile_grid)
        for index, button in enumerate(self.voltage_profile_buttons):
            self.voltage_profile_grid.addWidget(
                button, index // columns, index % columns
            )
        for column in range(columns):
            self.voltage_profile_grid.setColumnStretch(column, 1)

    def _reflow_voltage_workspace(self, width: int) -> None:
        if not hasattr(self, "voltage_workspace") or not hasattr(
            self, "voltage_curve_card"
        ):
            return
        self._reflow_voltage_profiles(width)
        columns = 1
        if (
            columns == self._voltage_workspace_columns
            and self.voltage_workspace.count()
        ):
            return
        self._voltage_workspace_columns = columns
        self._clear_grid(self.voltage_workspace)
        self.voltage_workspace.setHorizontalSpacing(0)
        self.voltage_workspace.setVerticalSpacing(8)
        self.voltage_workspace.addWidget(
            self.voltage_curve_card, 0, 0, Qt.AlignmentFlag.AlignTop
        )
        self.voltage_workspace.addWidget(
            self.voltage_workflow_card, 1, 0, Qt.AlignmentFlag.AlignTop
        )
        self.voltage_workspace.setColumnStretch(0, 1)

    def _reflow_runtime_stats(self, width: int) -> None:
        columns = (
            5 if width >= 1260 else 3 if width >= 760 else 2 if width >= 480 else 1
        )
        if columns == self._runtime_columns and self.runtime_stats_grid.count():
            return
        self._runtime_columns = columns
        self._clear_grid(self.runtime_stats_grid)
        for index, stat in enumerate(self.runtime_stats):
            self.runtime_stats_grid.addWidget(stat, index // columns, index % columns)
        for column in range(columns):
            self.runtime_stats_grid.setColumnStretch(column, 1)

    def _reflow_runtime_actions(self, width: int) -> None:
        # Actions form a balanced grid.  The voltage-lab action spans the two
        # remaining cells on wide layouts now that the hide-diagnostics action
        # has been removed.
        columns = 3 if width >= 1080 else 2 if width >= 520 else 1
        if (
            columns == self._runtime_action_columns
            and self.runtime_actions_grid.count()
        ):
            return
        self._runtime_action_columns = columns
        self._clear_grid(self.runtime_actions_grid)
        if columns >= 3:
            for index, button in enumerate(self.runtime_action_buttons[:3]):
                self.runtime_actions_grid.addWidget(button, 0, index)
            self.runtime_actions_grid.addWidget(self.disable_button, 1, 0)
            self.runtime_actions_grid.addWidget(self.voltage_lab_button, 1, 1, 1, 2)
        else:
            for index, button in enumerate(self.runtime_action_buttons):
                self.runtime_actions_grid.addWidget(button, index // columns, index % columns)
        for column in range(columns):
            self.runtime_actions_grid.setColumnStretch(column, 0)

    def _reflow_advanced(self, width: int) -> None:
        columns = 2 if width >= 1080 else 1
        if columns == self._advanced_columns and self.advanced_grid.count():
            return
        self._advanced_columns = columns
        self._clear_grid(self.advanced_grid)
        if columns == 2:
            self.advanced_grid.addWidget(self.fixed_safe_point_panel, 0, 0, 1, 2)
            self.advanced_grid.addWidget(self.safe_points_panel, 1, 0)
            self.advanced_grid.addWidget(self.diagnostics_panel, 1, 1)
            self.advanced_grid.addWidget(self.console_panel, 2, 0, 1, 2)
            self.advanced_grid.setColumnStretch(0, 7)
            self.advanced_grid.setColumnStretch(1, 5)
        else:
            self.advanced_grid.addWidget(self.fixed_safe_point_panel, 0, 0)
            self.advanced_grid.addWidget(self.safe_points_panel, 1, 0)
            self.advanced_grid.addWidget(self.diagnostics_panel, 2, 0)
            self.advanced_grid.addWidget(self.console_panel, 3, 0)
            self.advanced_grid.setColumnStretch(0, 1)

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
        self._range_user_dirty = False
        self._stage_range(
            self.active_min,
            self.active_max,
            preset=self._profile_name(self.active_min, self.active_max),
        )

    def _clear_profile_checks(self) -> None:
        self.preset_group.setExclusive(False)
        for button in self.preset_buttons:
            button.setChecked(False)
        self.preset_group.setExclusive(True)

    def _set_backend_profile_mode(self, is_oberon: bool) -> None:
        backend = "oberon" if is_oberon else "cyan"
        if backend == self._profile_backend:
            return
        self._profile_backend = backend
        self._range_user_dirty = False
        self._controls_initialized = False
        self._active_range_signature = None
        specs = self.OBERON_PROFILE_VALUES if is_oberon else self.CYAN_PROFILE_VALUES
        self._clear_profile_checks()
        for index, button in enumerate(self.preset_buttons):
            if index < len(specs):
                title, summary, payload = specs[index]
                button.payload = payload
                button.setText(f"{tr(title)}\n{tr(summary)}")
                button.show()
            else:
                button.hide()
        for field in self.range_fields:
            field.setVisible(not is_oberon)
        self.use_active_button.setVisible(not is_oberon)
        self.apply_range_button.setText(
            tr(
                "Review and apply Oberon profile"
                if is_oberon
                else "Review and apply range"
            )
        )
        self._preset_columns = 0
        self._range_action_mode = ""
        self._workspace_columns = 0
        self._update_backend_config_copy(is_oberon=is_oberon)
        self._place_runtime_actions(oberon=is_oberon)
        self._reflow(max(1, effective_viewport_width(self, self.overview_scroll)))

    def _update_backend_config_copy(self, *, is_oberon: bool) -> None:
        """Keep configuration labels truthful when switching Cyan ↔ Oberon."""
        if is_oberon:
            self.fixed_title.setText(tr("YAML endpoint laboratory"))
            self.fixed_hint.setText(
                tr("Inspect Oberon YAML endpoints and their protected voltage values.")
            )
            self.config_actions_label.setText(tr("YAML configuration"))
            self.open_toml_button.setText(tr("Open oberon-config.yaml"))
            self.open_toml_button.setToolTip(
                tr("Open /etc/oberon-config.yaml in the system's default editor.")
            )
            self.safe_header.setText(tr("Active YAML endpoints"))
        else:
            self.fixed_title.setText(tr("TOML safe-point laboratory"))
            self.fixed_hint.setText(
                tr(
                    "Inspect every active safe-point, including +2000 MHz entries, with conservative voltage validation."
                )
            )
            self.config_actions_label.setText(tr("TOML configuration"))
            self.open_toml_button.setText(tr("Open config.toml"))
            self.open_toml_button.setToolTip(
                tr(
                    "Open the governor TOML in the system's default text or code editor. Saving may require administrator privileges."
                )
            )
            self.safe_header.setText(tr("Active TOML safe-points"))

    def _run_backend_action(
        self,
        operation,
        on_success,
        error_title: str,
        *,
        controls: tuple[QWidget, ...] = (),
        refresh: bool = True,
        keep_voltage_lab: bool = False,
        error_parent: QWidget | None = None,
    ) -> bool:
        token = self._action_gate.begin()
        if token is None:
            self._show_info(
                "GPU operation in progress",
                "Wait for the current GPU operation to finish.",
                tone="orange",
            )
            return False
        self._action_busy = True
        control_states = tuple((control, control.isEnabled()) for control in controls)
        for control in controls:
            control.setEnabled(False)

        def report_failure(message: str) -> None:
            # This range failure is emitted by the repository with live values.
            # Translate the explanatory shell around those values while keeping
            # the measured backend range intact.
            range_failure = re.search(
                r"Cyan restarted but D-Bus did not expose the requested (\d+)-(\d+) MHz high safe-point range \(allowed (.+?)\)\. The TOML was saved; inspect the governor service status before retrying\.",
                message,
            )
            if range_failure:
                minimum, maximum, allowed = range_failure.groups()
                localized = tr_format(
                    "Cyan could not expose the requested {minimum}-{maximum} MHz range; the active backend allows {allowed}. This is a kernel/driver limit, not a TOML save failure. The TOML was saved; use SMU or a BC-250 patched kernel for a wider range.",
                    minimum=minimum,
                    maximum=maximum,
                    allowed=allowed,
                )
            else:
                localized = tr(message)
            self._show_info(error_title, localized, tone="red", parent=error_parent)
            self._append_console(f"{error_title}: {localized}")

        def callback_error(error: Exception) -> None:
            report_failure(
                tr_format("Result handling failed: {error}", error=str(error))
            )

        def refresh_page() -> None:
            self._action_busy = False
            self.refresh()

        session = ActionSession(
            gate=self._action_gate,
            token=token,
            controls=control_states,
            on_success=on_success,
            on_failure=report_failure,
            on_callback_error=callback_error,
            invalidate=lambda: self._state_cache.invalidate(
                "gpu", "performance", "tools"
            ),
            refresh=refresh_page,
            refresh_enabled=refresh,
            after_success=(
                lambda: (
                    self.page_stack.setCurrentWidget(self.voltage_lab_page)
                    if keep_voltage_lab
                    else None
                )
            ),
        )

        def finished() -> None:
            session.finished()
            if not self._action_gate.busy:
                self._action_busy = False

        start_error: Exception | None = None
        try:
            started = self._background.start(
                "gpu-hardware-action",
                operation,
                session.success,
                session.failure,
                finished,
            )
        except (RuntimeError, TypeError, ValueError) as error:
            started = False
            start_error = error
            self._show_info(error_title, str(error), tone="red", parent=error_parent)
        if not started:
            session.abort()
            self._action_busy = False
            if start_error is None:
                self._show_info(
                    "GPU operation in progress",
                    "Wait for the current GPU operation to finish.",
                    tone="orange",
                )
        return started

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

    def _apply_high_points_toggle_feedback(self, enabled: bool) -> None:
        """Reflect a confirmed TOML edit immediately while the full refresh runs."""

        state = dict(_dict(self.current_state.get("high_frequency_points")))
        frequencies = tuple(state.get("frequencies") or ())
        state["enabled"] = bool(enabled)
        state["enabled_frequencies"] = frequencies if enabled else ()
        self.current_state["high_frequency_points"] = state
        self.high_points_button.setText(
            tr(
                "Disable +2000 MHz TOML points"
                if enabled
                else "Enable +2000 MHz TOML points"
            )
        )
        self._update_safety_notice(self.current_state)

    def _high_oc_voltage_gaps(
        self, maximum: int
    ) -> tuple[tuple[int, int, int | None], ...]:
        """Return high-OC points that do not meet the complete Level 3 curve."""
        return high_oc_voltage_gaps(int(maximum), self._range_evidence())

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
        )

    def execute_dependency_action(
        self,
        *,
        action: str,
        preference: str,
        selected_components: set[str],
        dialog_parent: QWidget | None = None,
        memory_policy: str = "current",
        memory_ttm_gib: int = 0,
    ) -> None:
        """Execute a dialog or dashboard preparation request through one route."""
        tools = _dict(self.current_state.get("tools"))
        if action in {"acpi-install", "acpi-uninstall", "acpi-status"}:
            self._manage_acpi(action, dialog_parent)
            return
        if action in {"memory_swap", "memory_ttm"}:
            self._prepare_bazzite_memory_tuning(
                policy=memory_policy,
                ttm_gib=memory_ttm_gib,
                scope="swap" if action == "memory_swap" else "ttm",
                dialog_parent=dialog_parent,
            )
            return
        if action in {"quick_access_install_decky", "quick_access_plugin"}:
            self._prepare_steamos_quick_access(
                install_decky=action == "quick_access_install_decky",
                dialog_parent=dialog_parent,
            )
            return
        if action in {
            "cachyos_bc250_kernel",
            "cachyos_bc250_mesa",
            "cachyos_bc250_full",
        }:
            self._prepare_cachyos_bc250(
                action.removeprefix("cachyos_bc250_"), dialog_parent=dialog_parent
            )
            return
        if action in {"fsr4_install", "fsr4_uninstall"}:
            self._manage_fsr4_bc250(
                action.removeprefix("fsr4_"), dialog_parent=dialog_parent
            )
            return
        if action == "fsr4_upstream":
            self._open_fsr4_upstream(dialog_parent=dialog_parent)
            return
        if action in {"acpi_upstream", "gfx1013_upstream", "bazzite_image_upstream"}:
            self._open_compatibility_upstream(action, dialog_parent=dialog_parent)
            return
        if action == "steamos_graphics_upstream":
            self._open_steamos_graphics_upstream(dialog_parent=dialog_parent)
            return
        if action.startswith("steamos_graphics_"):
            graphics_action = {
                "steamos_graphics_status": "status",
                "steamos_graphics_install": "install",
                "steamos_graphics_fsr4_install": "install-fsr4",
                "steamos_graphics_uninstall": "uninstall",
                "steamos_graphics_fsr4_uninstall": "uninstall-fsr4",
            }.get(action)
            if graphics_action is None:
                raise ValueError("Unsupported SteamOS graphics action.")
            self._manage_steamos_graphics(
                graphics_action, dialog_parent=dialog_parent
            )
            return
        if action in {"gfx1013_fedora_install", "gfx1013_fedora_uninstall"}:
            self._manage_gfx1013_fedora(
                "install"
                if action.endswith("install") and not action.endswith("uninstall")
                else "uninstall",
                dialog_parent=dialog_parent,
            )
            return
        if action.startswith("gfx1013_bazzite_"):
            self._manage_gfx1013_bazzite(
                action.removeprefix("gfx1013_bazzite_"),
                dialog_parent=dialog_parent,
            )
            return
        plan = build_gpu_dependency_plan(
            tools,
            current_governor=self.current_state.get("governor_backend"),
            action=action,
            preference=preference,
            selected_components=selected_components or DEFAULT_PREPARATION_COMPONENTS,
        )
        route = {
            "compatibility": GpuGovernorPage._prepare_steamos_compatibility,
            "diagnostics": GpuGovernorPage._prepare_steamos_diagnostics,
            "remove": GpuGovernorPage._prepare_governor_removal,
            "shared": GpuGovernorPage._prepare_governor_installation,
            "governor": GpuGovernorPage._prepare_governor_installation,
        }[plan.route]
        route(self, plan, dialog_parent)

    def _prepare_bazzite_memory_tuning(
        self,
        *,
        policy: str,
        ttm_gib: int,
        scope: str,
        dialog_parent: QWidget | None,
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
        summary = (
            (
                (tr("Swap mode"), swap_label),
                (tr("Reboot"), tr("Required to activate the selected configuration" if bazzite else "A reboot may be required.")),
            )
            if scope == "swap"
            else (
                (tr("Dynamic GPU Memory Limit (TTM)"), ttm_label),
                (tr("Reboot"), tr("Required to activate the selected configuration" if bazzite else "Not required")),
            )
        )
        confirmation = ConfirmDialog(
            tr("Apply Swap" if scope == "swap" else "Apply TTM limit"),
            tr("A reboot may be required.") if bazzite else tr("Optional system setup. Disk swap uses up to 32 GiB of storage; existing user swap is preserved. TTM is applied live when supported. ZRAM and deferred restoration require a reboot. Hardware testing is still required."),
            summary=summary,
            confirm_text=tr("Apply Swap" if scope == "swap" else "Apply TTM"),
            tone="orange",
            parent=dialog_parent or self,
        )
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_backend_action(
            lambda: (self.controller.preparar_memoria_bazzite(policy, ttm_gib) if bazzite
                     else self.controller.preparar_memoria(policy, ttm_gib)),
            lambda _result: GpuGovernorPage._record_preparation_result(
                self,
                tr("Memory & Swap"),
                tr("Workflow opened. Check the terminal result before rebooting."),
            ),
            tr("Could not prepare memory setup"),
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
        confirmation = ConfirmDialog(
            tr("CPU power management · ACPI"),
            tr("This changes the default boot entry, not your BIOS. The original boot entry remains available for recovery. Use it if the ACPI entry does not boot. Reboot only after the terminal reports success. This optional integration still requires hardware testing."),
            summary=((tr("Action"), tr("Install correction" if action == "acpi-install" else "Uninstall")),
                     (tr("Version"), "e-tho v1.1.0")),
            confirm_text=tr("Install correction" if action == "acpi-install" else "Uninstall"),
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
                (tr("Reboot"), tr("Required after installation") if action != "mesa" else tr("Recommended after Mesa changes")),
            ),
            confirm_text=tr("Open kernel installation terminal"),
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

    def _prepare_cachyos_bc250_kernel(
        self, *, dialog_parent: QWidget | None
    ) -> None:
        """Compatibility alias for callers that still request kernel only."""
        self._prepare_cachyos_bc250("kernel", dialog_parent=dialog_parent)

    def _manage_fsr4_bc250(
        self, action: str, *, dialog_parent: QWidget | None
    ) -> None:
        install = action == "install"
        fsr4_state = _dict(
            _dict(self.current_state.get("tools")).get("fsr4")
        )
        source_build = bool(fsr4_state.get("source_build_supported"))
        confirmation = ConfirmDialog(
            "Install BC-250 FSR4 V3" if install else "Remove BC-250 FSR4 V3",
            tr(
                "This builds the official FSR4 V3 source in its Fedora 44 container with rootless Podman, validates it on this BC-250, and installs only a per-game Vulkan driver in your user folder. The first build can take several minutes and use substantial disk space. System Mesa is not modified."
                if install and source_build
                else "This optional per-game RADV runtime is experimental. It is installed only in your user data directory and does not replace system Mesa. Games can still hang, crash or reset the GPU."
                if install
                else "This removes only the per-user FSR4 V3 runtime. Remove its VK_DRIVER_FILES Steam launch option to return each game to system RADV."
            ),
            summary=(
                (tr("Source"), "github.com/dmorazasanchez/bc250-fsr4"),
                (tr("Scope"), tr("Per-user, per-game Vulkan ICD")),
                (tr("System Mesa"), tr("Not modified")),
            ),
            confirm_text="Install FSR4 V3" if install else "Remove FSR4 V3",
            tone="orange",
            parent=dialog_parent or self,
        )
        if confirmation.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_backend_action(
            lambda: self.controller.gestionar_fsr4_bc250(action),
            lambda _result: GpuGovernorPage._record_preparation_result(
                self,
                "BC-250 FSR4 V3",
                "Opened the per-game FSR4 V3 workflow. Use the emitted VK_DRIVER_FILES option only for games you want to test.",
            ),
            "Could not manage BC-250 FSR4 V3",
            controls=(),
            error_parent=dialog_parent,
        )

    def _open_fsr4_upstream(self, *, dialog_parent: QWidget | None) -> None:
        """Open the upstream source/Docker guide without running an installer."""
        opened, message = open_external_url(
            "https://github.com/dmorazasanchez/bc250-fsr4"
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
            "bazzite_image_upstream": "https://github.com/62fixolab/Latest-Bazzite-AMD-BC-250-Patched-Images",
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
        detail = " ".join(tr(part) for part in presentation.detail)
        confirmation = ConfirmDialog(
            tr("GFX1013 async compute"),
            detail,
            summary=(
                (tr("System"), "Fedora 43"),
                (tr("Running kernel"), str(state.get("kernel") or tr("Unknown"))),
                (tr("Source"), "DryhoppedIPA/bc250-gfx1013-fix"),
                (tr("Recovery"), tr("Stock boot remains the default")),
                (tr("Reboot"), tr("Required after installation")),
            ),
            confirm_text=tr(
                "Uninstall" if action == "uninstall" else "Install / update"
            ),
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
                ),
                confirm_text="Prepare SteamOS compatibility",
                tone="orange",
                parent=dialog_parent or self,
            )
            if confirmation.exec() != QDialog.DialogCode.Accepted:
                return
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
                "This builds the reviewed Mesa 26.2.0 async-compute runtime for the active verified AMDGPU module. "
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

    def _service_action(self, action: str) -> None:
        tools = _dict(self.current_state.get("tools"))
        plan = plan_gpu_service_action(
            action,
            backend=self.current_state.get("governor_backend"),
            incompatible_governors=tools.get("incompatible_gpu_governors") or (),
        )
        description = tr_format(plan.description, **dict(plan.description_values))
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

        def success(_result: object) -> None:
            self._last_operation_summary = f"Opened service workflow: {plan.label}."
            self.last_operation_line.set_values(
                "Service action", self._last_operation_summary
            )
            self._append_console(self._last_operation_summary)

        self._run_backend_action(
            lambda: self.controller.controlar_governor(
                plan.action, plan.has_conflicts, plan.has_conflicts
            ),
            success,
            "Governor service action failed",
        )

    def read_service_status(self) -> None:
        def success(result: object) -> None:
            text = str(result or "No status output")
            self._last_operation_summary = (
                "Read systemctl status without changing the governor."
            )
            self.last_operation_line.set_values(
                "Read status", self._last_operation_summary
            )
            self._append_console(f"systemctl status\n{text}")

        self._run_backend_action(
            self.controller.status_governor,
            success,
            "Could not read governor status",
            refresh=False,
        )

    def open_voltage_lab(self) -> None:
        self._sync_voltage_lab(self.current_state)
        self.page_stack.setCurrentWidget(self.voltage_lab_page)

    def _close_voltage_lab(self) -> None:
        self.page_stack.setCurrentWidget(self.overview_page)

    def _refresh_voltage_lab(self) -> None:
        self.refresh()
        self.page_stack.setCurrentWidget(self.voltage_lab_page)

    def _voltage_for_level(self, frequency: int, level: int) -> int | None:
        return voltage_for_level(
            frequency,
            level,
            is_oberon=bool(getattr(self, "_is_oberon_backend", False)),
        )

    def _voltage_keypad_edit_active(self) -> bool:
        return voltage_keypad_edit_active(
            getattr(self, "_voltage_spinboxes", {}).values(),
            application=QApplication.instance(),
        )

    def _sync_voltage_lab(self, gpu: dict) -> None:
        if not hasattr(self, "voltage_curve_grid"):
            return
        if self._voltage_keypad_edit_active():
            return
        state = build_voltage_lab_state(
            gpu,
            active_min_default=self.active_min,
            active_max_default=self.active_max,
            levels=self.VOLTAGE_PROFILE_LEVELS,
            lab_frequencies=self.VOLTAGE_LAB_FREQUENCIES,
        )
        self._is_oberon_backend = state.is_oberon
        self._voltage_points = list(state.points)
        self._voltage_current_map = dict(state.current_voltages)
        self._voltage_editable_frequencies = set(state.editable_frequencies)
        self._voltage_profile_frequencies = set(state.profile_frequencies)
        self._voltage_detected_level = state.detected_level

        self.voltage_summary.setVisible(not state.is_oberon)
        self.voltage_workspace_host.setVisible(not state.is_oberon)
        self.voltage_controls_card.setVisible(not state.is_oberon)
        self.oberon_voltage_card.setVisible(state.is_oberon)
        if state.is_oberon:
            endpoint_map = dict(state.current_voltages)
            self.voltage_notice.set_notice(
                "Oberon voltage changes are unavailable",
                "Oberon has two YAML endpoints, not Cyan's multipoint curve. The active profile uses the displayed endpoints; supported profile changes restore the upstream 1000 mV baseline instead of deriving a voltage from Cyan.",
                tone="blue",
            )
            self.oberon_voltage_minimum.set_values(
                f"{state.active_min} MHz · {endpoint_map.get(state.active_min, '--')} mV",
                tr("Configured minimum YAML endpoint"),
            )
            self.oberon_voltage_maximum.set_values(
                f"{state.active_max} MHz · {endpoint_map.get(state.active_max, '--')} mV",
                tr("Configured maximum YAML endpoint"),
            )
        else:
            self.voltage_notice.set_notice(
                "Stop every 3D workload before applying",
                "A timestamped backup is created, the governor restarts, and the previous D-Bus range is restored only after confirmation.",
                tone="orange",
            )

        if not getattr(self, "_voltage_lab_initialized", False):
            index = self.voltage_level_combo.findData(self._voltage_detected_level)
            if index >= 0:
                self.voltage_level_combo.blockSignals(True)
                self.voltage_level_combo.setCurrentIndex(index)
                self.voltage_level_combo.blockSignals(False)
            self._voltage_lab_initialized = True

        for frequency, voltage in state.custom_defaults:
            self._voltage_custom_values.setdefault(frequency, voltage)

        presentation = present_voltage_lab(
            state,
            custom_voltage_maximum=CUSTOM_VOLTAGE_MAX_MV,
        )
        for widget, summary in zip(
            self.voltage_summary_items,
            presentation.summaries,
            strict=True,
        ):
            widget.set_values(
                self._render_voltage_lab_text(summary.value),
                self._render_voltage_lab_text(summary.detail),
            )

        if self.voltage_table_status is not None:
            self.voltage_table_status.setText(
                count_label(presentation.table_count, "point")
            )
            self.voltage_table_status.set_tone(presentation.table_tone)
        if self.voltage_controls_status is not None:
            self.voltage_controls_status.setText(tr(presentation.controls_status))
            self.voltage_controls_status.set_tone(presentation.controls_tone)
        if getattr(self, "voltage_workflow_status", None) is not None:
            self.voltage_workflow_status.setText(tr(presentation.workflow_status))
            self.voltage_workflow_status.set_tone(presentation.workflow_tone)
        # Curve validity remains visible in the summary strip and is rechecked before every apply.
        self._populate_voltage_table()

    @staticmethod
    def _render_voltage_lab_text(value: VoltageLabText) -> str:
        if value.literal:
            return value.template
        return tr_format(value.template, **dict(value.values))

    def _clear_stale_voltage_keypad_state(self) -> None:
        clear_voltage_keypad_state(getattr(self, "_voltage_spinboxes", {}).values())

    def _select_voltage_profile(self, level: int) -> None:
        self._clear_stale_voltage_keypad_state()
        index = self.voltage_level_combo.findData(int(level))
        if index >= 0:
            self.voltage_level_combo.setCurrentIndex(index)
            self._populate_voltage_table()

    def _sync_voltage_profile_buttons(self, level: int) -> None:
        for button in getattr(self, "voltage_profile_buttons", []):
            button.setChecked(button.level == int(level))

    def _voltage_level_changed(self, _index: int = 0) -> None:
        self._sync_voltage_profile_buttons(
            _integer(self.voltage_level_combo.currentData(), 0)
        )
        self._populate_voltage_table()

    def _populate_voltage_table(self) -> None:
        if not hasattr(self, "voltage_curve_grid"):
            return
        if self._voltage_keypad_edit_active():
            return
        points = list(getattr(self, "_voltage_points", []))
        selected_level = _integer(self.voltage_level_combo.currentData(), 0)
        self._sync_voltage_profile_buttons(selected_level)
        plan = build_voltage_table_plan(
            points=points,
            selected_level=selected_level,
            editable_frequencies=self._voltage_editable_frequencies,
            profile_frequencies=self._voltage_profile_frequencies,
            custom_values=self._voltage_custom_values,
            packaged_voltages=self.VOLTAGE_LAB_BASE,
            detected_level=self._voltage_detected_level,
            is_oberon=bool(getattr(self, "_is_oberon_backend", False)),
        )
        self.voltage_apply_button.setEnabled(bool(plan.active_frequencies))
        # Rebuilding this grid destroys and recreates every editor widget. A
        # telemetry refresh arrives frequently, so compare only inputs that
        # change the rendered structure.  Custom spin-box edits update their
        # own row in-place and must not make the curve blink on the next poll.
        signature = (
            tuple(self._voltage_points),
            selected_level,
            tuple(sorted(self._voltage_editable_frequencies)),
            tuple(sorted(self._voltage_profile_frequencies)),
            self._voltage_detected_level,
            bool(getattr(self, "_is_oberon_backend", False)),
        )
        if signature == getattr(self, "_voltage_table_signature", None):
            return
        self._voltage_table_signature = signature
        self.voltage_curve_grid.clear_points()
        self._voltage_spinboxes = {}

        for row, item in enumerate(plan.rows):
            spin = None
            if item.custom_available:
                spin = QSpinBox()
                spin.setRange(
                    OBERON_SAFE_VOLTAGE_MIN_MV
                    if getattr(self, "_is_oberon_backend", False)
                    else CUSTOM_VOLTAGE_MIN_MV,
                    CUSTOM_VOLTAGE_MAX_MV,
                )
                spin.setSingleStep(5)
                spin.setSuffix(" mV")
                spin.setValue(item.editor_value)
                spin.setEnabled(plan.custom_mode)
                spin.valueChanged.connect(
                    lambda value, freq=item.frequency: self._voltage_custom_changed(
                        freq, value
                    )
                )
                self._voltage_spinboxes[item.frequency] = spin

            self.voltage_curve_grid.add_point(
                row,
                frequency=item.frequency,
                current=item.current,
                original=item.original,
                added=item.added,
                editor=spin,
                custom_available=item.custom_available,
            )
        self._sync_voltage_curve_scroll_height()
        QTimer.singleShot(0, self._sync_voltage_curve_scroll_height)
        self.voltage_level_detail.setText(
            tr_format(plan.detail_template, **dict(plan.detail_values))
        )

    def _sync_voltage_curve_scroll_height(self) -> None:
        if not hasattr(self, "voltage_curve_scroll"):
            return
        self.voltage_curve_grid.grid.activate()
        content_height = max(72, self.voltage_curve_grid.minimumSizeHint().height())
        scrollbar_height = (
            self.voltage_curve_scroll.horizontalScrollBar().sizeHint().height()
        )
        self.voltage_curve_scroll.setFixedHeight(content_height + scrollbar_height + 2)

    def _voltage_custom_changed(self, frequency: int, value: int) -> None:
        frequency = int(frequency)
        value = int(value)
        self._voltage_custom_values[frequency] = value
        base = self.VOLTAGE_LAB_BASE.get(frequency)
        added = None if base is None else value - int(base)
        self.voltage_curve_grid.update_point(frequency, added)

    def _request_apply_voltage_curve(self) -> None:
        if bool(getattr(self, "_is_oberon_backend", False)):
            self._show_info(
                "Oberon voltage changes are unavailable",
                "Oberon has only two YAML endpoints, not a validated voltage curve. No voltage was written. Use a protected Oberon frequency profile while the GPU is idle, or switch to Cyan for voltage-curve testing.",
                tone="orange",
            )
            return
        level = _integer(self.voltage_level_combo.currentData(), 0)
        custom_values = (
            {
                frequency: int(self._voltage_spinboxes[frequency].value())
                for frequency in sorted(self._voltage_editable_frequencies)
                if frequency in self._voltage_spinboxes
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
            controls=(self.voltage_apply_button,),
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

    def set_updates_active(self, active: bool) -> None:
        self._updates_active = bool(active)
        if self._updates_active:
            if not self.timer.isActive():
                self.timer.start()
            self._refresher.activate(fresh_for=1.5)
        else:
            self._refresher.set_active(False)
            self.timer.stop()

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

    def _apply_refresh_payload(self, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        gpu = _dict(data.get("gpu"))
        perf = _dict(data.get("performance"))
        self.current_state = gpu
        self.current_perf = perf
        self._apply_state(gpu, perf)

    def _sync_range_state(self, gpu: dict) -> tuple[int, int, int, int]:
        frequency = _integer(gpu.get("sclk_actual"), 0)
        mclk = _integer(gpu.get("mclk_actual"), 0)
        minimum = _integer(gpu.get("current_min"), 0)
        maximum = _integer(gpu.get("current_max"), 0)
        is_oberon = str(gpu.get("governor_backend") or "") == "oberon-governor"
        allowed_min = 1000 if is_oberon else _integer(gpu.get("allowed_min"), 300)
        allowed_max = (
            2000
            if is_oberon
            else _integer(
                gpu.get("allowed_max"),
                gpu.get("config_max_frequency") or maximum or 2000,
            )
        )
        self.allowed_min = max(0, allowed_min)
        self.allowed_max = max(self.allowed_min, allowed_max)
        self.active_min = minimum or self.active_min
        self.active_max = maximum or self.active_max
        self.minimum_control.set_limits(self.allowed_min, self.allowed_max)
        self.maximum_control.set_limits(self.allowed_min, self.allowed_max)

        points = list(
            gpu.get("safe_points_with_voltage") or gpu.get("safe_points") or []
        )
        self._populate_points(points, frequency)
        runtime_signature = (minimum, maximum)
        if not self._controls_initialized or (
            not self._range_user_dirty
            and runtime_signature != self._active_range_signature
        ):
            self._stage_range(
                self.active_min,
                self.active_max,
                preset=self._profile_name(self.active_min, self.active_max),
            )
            self._controls_initialized = True
        self._active_range_signature = runtime_signature
        return frequency, mclk, minimum, maximum

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

    def _update_metric_widgets(
        self,
        telemetry: dict[str, object],
        *,
        frequency: int,
        mclk: int,
        minimum: int,
        maximum: int,
        running: bool,
        active: str,
        enabled: str,
    ) -> None:
        idle_without_sclk = (
            not frequency and running and telemetry.get("utilization") == 0
        )
        frequency_text = (
            f"{frequency} MHz"
            if frequency
            else tr("Not sampled at idle")
            if idle_without_sclk
            else tr("Not detected")
        )
        range_text = (
            f"{minimum}–{maximum} MHz" if minimum or maximum else tr("Not available")
        )
        temperature = _number(telemetry["temperature"], 0)
        self.summary.items[0].set_values(
            tr("Active") if running else tr(active.capitalize()),
            tr_format("boot: {state}", state=tr(enabled.capitalize())),
        )
        self.summary.items[1].set_values(frequency_text, tr("real-time SCLK"))
        self.summary.items[2].set_values(
            range_text,
            tr_format(
                "allowed {minimum}–{maximum}",
                minimum=self.allowed_min,
                maximum=self.allowed_max,
            ),
        )
        self.summary.items[3].set_values(
            str(telemetry["utilization_text"]), tr("current GPU load")
        )
        self.summary.items[4].set_values(
            str(telemetry["temperature_text"]), self._temperature_status(temperature)
        )

        self.sclk_metric.set_values(
            frequency_text,
            tr("AMDGPU did not expose a current SCLK sample.")
            if idle_without_sclk
            else tr("Current SCLK state"),
        )
        self.voltage_metric.set_values(
            str(telemetry["voltage_text"]), tr("OD / SMU telemetry")
        )
        self.temperature_metric.set_values(
            str(telemetry["temperature_text"]), self._temperature_status(temperature)
        )
        self.utilization_metric.set_values(
            str(telemetry["utilization_text"]), tr("amdgpu busy percentage")
        )
        self.mclk_metric.set_values(
            f"{mclk} MHz" if mclk else tr("Not detected"), tr("Current MCLK state")
        )
        self.vram_metric.set_values(
            str(telemetry["vram_value"]), str(telemetry["vram_detail"])
        )
        if self.metrics_status is not None:
            self.metrics_status.setText(tr("Live"))
            self.metrics_status.set_tone("green")

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

    def _update_runtime_status_cards(
        self,
        gpu: dict,
        *,
        is_oberon: bool,
        running: bool,
        enabled_at_boot: bool,
        range_control_ok: bool,
        active: str,
        enabled: str,
        dbus_ok: bool,
        range_text: str,
        profile_name: str,
    ) -> None:
        presentation = present_gpu_runtime(
            gpu,
            is_oberon=is_oberon,
            running=running,
            enabled_at_boot=enabled_at_boot,
            range_control_ok=range_control_ok,
            active=active,
            enabled=enabled,
            dbus_ok=dbus_ok,
            range_text=range_text,
            profile_name=profile_name,
            safe_point_count=len(self.safe_frequencies),
        )
        widgets = (
            self.service_stat,
            self.boot_stat,
            self.dbus_stat,
            self.profile_stat,
            self.points_stat,
        )
        # The presenter retains the timestamp line for API compatibility, but
        # the redundant passive tile is intentionally not rendered in the UI.
        for widget, line in zip(widgets, presentation.lines[: len(widgets)], strict=True):
            widget.set_values(
                self._render_runtime_text(line.value),
                self._render_runtime_text(line.detail),
            )
        if self.runtime_card.status is not None:
            self.runtime_card.status.setText(
                self._render_runtime_text(presentation.card_status)
            )
            self.runtime_card.status.set_tone(presentation.card_tone)

    @staticmethod
    def _render_runtime_text(value: RuntimeText) -> str:
        return (
            value.template
            if value.literal
            else tr_format(value.template, **dict(value.values))
        )

    def _update_governor_action_buttons(
        self,
        gpu: dict,
        *,
        is_oberon: bool,
        running: bool,
        enabled_at_boot: bool,
        range_control_ok: bool,
        conflict_blocked: bool,
    ) -> None:
        self.enable_button.setEnabled(not (running and enabled_at_boot))
        self.disable_button.setEnabled(running or enabled_at_boot)
        self.restart_button.setEnabled(running)
        self.apply_range_button.setEnabled(range_control_ok and not conflict_blocked)
        high_points_state = _dict(gpu.get("high_frequency_points"))
        high_points_enabled = bool(high_points_state.get("enabled"))
        self.high_points_button.setText(
            tr(
                "Disable +2000 MHz TOML points"
                if high_points_enabled
                else "Enable +2000 MHz TOML points"
            )
        )
        self.high_points_button.setEnabled(
            bool(high_points_state.get("available")) and not conflict_blocked
        )
        self.high_points_button.setVisible(not is_oberon)
        self.telemetry_guide_button.setVisible(is_oberon)

    def _update_range_recommendation(
        self,
        frequency_range: dict,
        *,
        is_oberon: bool,
        minimum: int,
        maximum: int,
    ) -> None:
        persistent_text = self._persistent_range_copy(frequency_range)
        template = (
            "Oberon allowed: {allowed_min}–{allowed_max} MHz · configured endpoints: "
            "{minimum}–{maximum} MHz · persistent YAML: {persistent}."
            if is_oberon
            else "D-Bus allowed: {allowed_min}–{allowed_max} MHz · active runtime: "
            "{minimum}–{maximum} MHz · persistent TOML: {persistent}."
        )
        self.range_recommendation.setText(
            tr_format(
                template,
                allowed_min=self.allowed_min,
                allowed_max=self.allowed_max,
                minimum=minimum,
                maximum=maximum,
                persistent=persistent_text,
            )
        )

    def _update_backend_controls(
        self,
        gpu: dict,
        *,
        is_oberon: bool,
        running: bool,
        enabled_at_boot: bool,
        range_control_ok: bool,
        conflict_blocked: bool,
        minimum: int,
        maximum: int,
        active: str,
        enabled: str,
        dbus_ok: bool,
    ) -> None:
        range_text = (
            f"{minimum}–{maximum} MHz" if minimum or maximum else tr("Not available")
        )
        frequency_range = _dict(gpu.get("frequency_range"))
        persistent_custom = bool(
            frequency_range.get("valid") and frequency_range.get("enabled")
        )
        profile_name = (
            tr("Custom persistent range")
            if persistent_custom
            else self._profile_name(minimum, maximum)
        )
        if persistent_custom:
            self._clear_profile_checks()

        self._update_runtime_status_cards(
            gpu,
            is_oberon=is_oberon,
            running=running,
            enabled_at_boot=enabled_at_boot,
            range_control_ok=range_control_ok,
            active=active,
            enabled=enabled,
            dbus_ok=dbus_ok,
            range_text=range_text,
            profile_name=profile_name,
        )
        self._update_governor_action_buttons(
            gpu,
            is_oberon=is_oberon,
            running=running,
            enabled_at_boot=enabled_at_boot,
            range_control_ok=range_control_ok,
            conflict_blocked=conflict_blocked,
        )
        self._update_range_recommendation(
            frequency_range,
            is_oberon=is_oberon,
            minimum=minimum,
            maximum=maximum,
        )

    def _apply_state(self, gpu: dict, perf: dict) -> None:
        governor_backend = str(
            gpu.get("governor_backend") or "cyan-skillfish-governor-smu"
        )
        is_oberon = governor_backend == "oberon-governor"
        self._set_backend_profile_mode(is_oberon)
        self._sync_cyan_compatibility(gpu, is_oberon=is_oberon)
        frequency, mclk, minimum, maximum = self._sync_range_state(gpu)
        telemetry = self._telemetry_copy(gpu, perf)

        active = str(gpu.get("service_active") or "not-found")
        enabled = str(gpu.get("service_enabled") or "not-found")
        dbus_ok = bool(gpu.get("dbus_ok"))
        range_control_ok = bool(gpu.get("range_control_ok", dbus_ok))
        running = active.lower() in {"active", "running"}
        enabled_at_boot = enabled.lower() in {"enabled", "enabled-runtime", "static"}
        governor_conflicts = list(
            _dict(gpu.get("tools")).get("incompatible_gpu_governors") or []
        )
        conflict_blocked = bool(governor_conflicts)
        self._update_metric_widgets(
            telemetry,
            frequency=frequency,
            mclk=mclk,
            minimum=minimum,
            maximum=maximum,
            running=running,
            active=active,
            enabled=enabled,
        )
        self._update_backend_controls(
            gpu,
            is_oberon=is_oberon,
            running=running,
            enabled_at_boot=enabled_at_boot,
            range_control_ok=range_control_ok,
            conflict_blocked=conflict_blocked,
            minimum=minimum,
            maximum=maximum,
            active=active,
            enabled=enabled,
            dbus_ok=dbus_ok,
        )
        self._update_profile_availability()
        self._update_safety_notice(gpu)
        self._update_diagnostics(gpu)
        self._sync_voltage_lab(gpu)

    def _sync_cyan_compatibility(self, gpu: dict, *, is_oberon: bool) -> None:
        self.cyan_compatibility_panel.setVisible(not is_oberon)
        self.apply_cyan_compatibility.setEnabled(not is_oberon)
        if is_oberon or self._cyan_compatibility_dirty:
            return
        state = _dict(gpu.get("cyan_telemetry"))
        set_method = str(state.get("set_method") or "smu")
        usage_method = str(state.get("method") or "busy-flag")
        set_index = self.cyan_set_method.findData(set_method)
        usage_index = self.cyan_usage_method.findData(usage_method)
        widgets = (
            self.cyan_set_method,
            self.cyan_usage_method,
            self.cyan_fix_metrics,
            self.cyan_fix_frequency,
        )
        previous = tuple(widget.blockSignals(True) for widget in widgets)
        try:
            self.cyan_set_method.setCurrentIndex(max(0, set_index))
            self.cyan_usage_method.setCurrentIndex(max(0, usage_index))
            self.cyan_fix_metrics.setChecked(bool(state.get("fix_metrics", True)))
            self.cyan_fix_frequency.setChecked(bool(state.get("fix_frequency", False)))
        finally:
            for widget, blocked in zip(widgets, previous, strict=True):
                widget.blockSignals(blocked)

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

    def _update_safe_points_table(
        self,
        rows: tuple[SafePointRow, ...],
    ) -> None:
        self.points_table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            self.points_table.setItem(row, 0, QTableWidgetItem(f"{item.frequency} MHz"))
            self.points_table.setItem(
                row,
                1,
                QTableWidgetItem(
                    f"{item.voltage} mV" if item.voltage else tr("Not specified")
                ),
            )
            self.points_table.setItem(
                row,
                2,
                QTableWidgetItem(
                    f"{item.original_voltage} mV"
                    if item.original_voltage is not None
                    else "n/a"
                ),
            )
            self.points_table.setItem(row, 3, QTableWidgetItem(tr(item.role)))

    def _sync_safe_point_combo(
        self,
        cleaned: list[tuple[int, int]],
        current: int,
    ) -> None:
        signature = tuple(cleaned)
        if signature == self._safe_point_combo_signature:
            return
        selectable = [frequency for frequency, _voltage in cleaned]
        previous = _integer(self.oc_frequency.currentData(), 0)
        self.oc_frequency.blockSignals(True)
        self.oc_frequency.clear()
        for frequency, voltage in cleaned:
            self.oc_frequency.addItem(
                f"{frequency} MHz · {voltage} mV" if voltage else f"{frequency} MHz",
                frequency,
            )
        desired = (
            previous
            if previous in selectable
            else current
            if current in selectable
            else selectable[0]
            if selectable
            else None
        )
        if desired is not None:
            index = self.oc_frequency.findData(desired)
            if index >= 0:
                self.oc_frequency.setCurrentIndex(index)
        self.oc_frequency.blockSignals(False)
        self._safe_point_combo_signature = signature

    def _safe_point_popup_visible(self) -> bool:
        try:
            return bool(self.oc_frequency.view().isVisible())
        except (RuntimeError, TypeError):
            return False

    def _update_selected_safe_point(self, _index: int = 0) -> None:
        frequency = _integer(self.oc_frequency.currentData(), 0)
        if frequency > 0:
            self.apply_selected_range_button.setText(
                tr_format(
                    "Apply active range · 1000–{maximum} MHz",
                    maximum=frequency,
                )
            )
        else:
            self.apply_selected_range_button.setText(
                tr("Apply active range · select a ceiling")
            )
        tools = _dict(self.current_state.get("tools"))
        conflicts = list(tools.get("incompatible_gpu_governors") or [])
        can_apply = (
            frequency >= self.SELECTED_RANGE_FLOOR
            and frequency in self.safe_frequencies
            and bool(
                self.current_state.get(
                    "range_control_ok", self.current_state.get("dbus_ok")
                )
            )
            and not conflicts
        )
        self.apply_selected_range_button.setEnabled(can_apply)
        if frequency <= 0:
            self.safe_point_detail.setText(tr("No selectable safe-point is available."))
            return
        voltage = self.safe_voltage_map.get(frequency)
        original = self.PACKAGED_DEFAULT_VOLTAGES.get(frequency)
        if original is None:
            status = tr("No packaged original voltage is defined.")
        elif voltage is None:
            status = tr_format(
                "Voltage missing; packaged original {original} mV.", original=original
            )
        elif voltage >= original:
            status = tr_format(
                "TOML {voltage} mV · packaged original {original} mV · baseline check passed.",
                voltage=voltage,
                original=original,
            )
        else:
            status = tr_format(
                "TOML {voltage} mV · packaged original {original} mV · undervolt laboratory condition.",
                voltage=voltage,
                original=original,
            )
        self.safe_point_detail.setText(status)

    def _update_profile_availability(self) -> None:
        safe = set(self.safe_frequencies)
        is_oberon = (
            str(self.current_state.get("governor_backend") or "") == "oberon-governor"
        )
        dynamic_profiles = {}
        if not is_oberon:
            dynamic_profiles = {
                profile.key: profile
                for profile in profiles_for_allowed_range(
                    self.allowed_min, self.allowed_max, governor="cyan"
                )
            }
        for index, button in enumerate(self.preset_buttons):
            if is_oberon:
                preset_minimum, preset_maximum = button.payload
                available = tuple(button.payload) in OBERON_SAFE_PROFILES
            else:
                profile_key = ("balanced", "gaming", "benchmark")[index]
                profile = dynamic_profiles.get(profile_key)
                if profile is None:
                    available = False
                else:
                    button.payload = (profile.minimum_mhz, profile.maximum_mhz)
                    button.setText(
                        f"{tr(profile.label)}\n"
                        f"{profile.minimum_mhz}–{profile.maximum_mhz} MHz"
                    )
                    preset_minimum, preset_maximum = button.payload
                    available = not safe or preset_maximum in safe
            button.setEnabled(available)
            button.setToolTip(
                ""
                if available
                else tr(
                    "This profile ceiling is not available in the active governor safe-point table or D-Bus range."
                )
            )

    def _update_safety_notice(self, gpu: dict) -> None:
        notice = present_gpu_safety(gpu, safe_frequencies=self.safe_frequencies)
        detail = GpuGovernorPage._render_safety_message(notice.message)
        for suffix in notice.suffixes:
            detail += " " + GpuGovernorPage._render_safety_message(suffix)
        self.safety_notice.set_notice(notice.title, detail, tone=notice.tone)
        if self.configuration_status is not None:
            self.configuration_status.setText(tr(notice.status))
            self.configuration_status.set_tone(notice.status_tone)

    @staticmethod
    def _render_safety_message(message: SafetyMessage) -> str:
        if message.literal:
            return message.template
        return tr_format(message.template, **dict(message.values))

    @staticmethod
    def _compact_path(value: str) -> str:
        return compact_diagnostic_path(value)

    def set_detailed_diagnostics(self, enabled: bool) -> None:
        self._detailed_diagnostics = bool(enabled)
        if self.current_state:
            self._update_diagnostics(self.current_state)

    def _update_diagnostics(self, gpu: dict) -> None:
        presentation = present_gpu_diagnostics(
            gpu,
            detailed=self._detailed_diagnostics,
        )
        bindings = (
            (self.device_line, presentation.device),
            (self.driver_line, presentation.driver),
            (self.config_line, presentation.config),
            (self.curve_line, presentation.curve),
            (self.missing_line, presentation.missing),
            (self.duplicates_line, presentation.duplicates),
            (self.power_state_line, presentation.power),
        )
        for widget, line in bindings:
            widget.set_values(
                self._render_diagnostic_text(line.value),
                self._render_diagnostic_text(line.detail),
            )

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
    ) -> None:
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
