"""Standalone widgets and dialogs of the GPU page: summary strip, dependency preparation dialog, safety notice and profile editor."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from bc250cc.infrastructure.bazzite_async_compute import (
    BAZZITE_ASYNC_COMPUTE_REPOSITORY,
)
from bc250cc.infrastructure.radv_async_compute import RADV_ASYNC_REVIEWED_COMMIT

from ..components.buttons import WrappingButton as QPushButton
from ..components.dialogs import enable_adaptive_dialog
from ..components.system_setup_controls import (
    VRAM_SIZE_CHOICES,
    bazzite_ui_preview_enabled,
    is_bazzite_host,
    update_memory_controls,
    vram_size_label,
)
from ..components.wheel_guard import GuardedComboBox
from ..components.widgets import IconBadge, InfoDialog, PillLabel, apply_shadow, icon
from ..core.external_links import open_external_url
from ..core.feature_visibility import (
    GFX1013_FSR4_UI_ENABLED,
    mastag_stack_replaces_gfx1013_card,
)
from ..core.gfx1013_presenter import present_gfx1013
from ..i18n import tr, tr_format
from ..theme import COLORS, application_stylesheet
from .gpu_governor_helpers import _dict, _format_bytes, _integer  # noqa: E402


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
        self.vram_uma_size_mb = 0
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
                "Install or update all required BC250 components. With Cyan selected, its configuration and frequency-reporting fix are prepared now. Prepare does not start the governor: use Start governor afterward to start it now and at every boot."
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
        if is_bazzite_host(self.tools) or bazzite_ui_preview_enabled():
            components_layout.addWidget(self._bazzite_mitigations_card())
        components_layout.addWidget(self._memory_component_card())
        self.section_stack.addWidget(components_page)

        advanced_content = QWidget()
        advanced_layout = QVBoxLayout(advanced_content)
        advanced_layout.setContentsMargins(0, 0, 6, 0)
        advanced_layout.setSpacing(10)
        self.gfx1013_card = self._gfx1013_card()
        gfx_state = _dict(self.tools.get("gfx1013_compute"))
        self.gfx1013_card.setVisible(
            not mastag_stack_replaces_gfx1013_card(self.tools)
            # Debian family on a kernel too old for any route: nothing to offer.
            and not bool(_dict(gfx_state.get("source")).get("hide_offer"))
        )
        advanced_layout.addWidget(self.gfx1013_card)
        kernel_upgrade = _dict(gfx_state.get("kernel_upgrade"))
        self.debian_kernel_card = self._debian_kernel_card(kernel_upgrade)
        self.debian_kernel_card.setVisible(bool(kernel_upgrade.get("offered")))
        advanced_layout.addWidget(self.debian_kernel_card)
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
        self.memory_policy_combo = GuardedComboBox()
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
        self.ttm_limit_combo = GuardedComboBox()
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

        vram_label = QLabel(tr("VRAM size (UMA_SIZE)"))
        vram_label.setProperty("fieldLabel", True)
        controls.addWidget(vram_label, 2, 0)
        self.vram_size_combo = GuardedComboBox()
        self.vram_size_combo.setProperty("settingsCombo", True)
        self.vram_size_combo.addItem(tr("Keep current VRAM size"), 0)
        for target in VRAM_SIZE_CHOICES:
            self.vram_size_combo.addItem(vram_size_label(target), target)
        controls.addWidget(self.vram_size_combo, 2, 1)
        self.vram_apply_button = QPushButton(tr("Apply VRAM"))
        self.vram_apply_button.setObjectName("PrimaryAction")
        self.vram_apply_button.clicked.connect(lambda: self._choose("vram_apply", ""))
        controls.addWidget(self.vram_apply_button, 2, 2)

        controls.setColumnStretch(1, 1)
        layout.addLayout(controls)

        self.memory_policy_combo.currentIndexChanged.connect(
            self._update_memory_apply_availability
        )
        self.ttm_limit_combo.currentIndexChanged.connect(
            self._update_memory_apply_availability
        )
        self.vram_size_combo.currentIndexChanged.connect(
            self._update_memory_apply_availability
        )
        self._update_memory_apply_availability()
        return card

    def _bazzite_mitigations_card(self) -> QFrame:
        actionable = is_bazzite_host(self.tools)
        mitigations = _dict(self.tools.get("bazzite_mitigations"))
        configured = bool(mitigations.get("configured"))
        managed = bool(mitigations.get("managed"))
        available = bool(mitigations.get("available"))
        mitigation_action = "restore" if managed else "disable"

        card = QFrame()
        self.mitigations_card = card
        card.setProperty("dependencyActionTile", True)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(10)

        layout.addWidget(IconBadge("cpu_blue", COLORS["blue_soft"], 30, radius=8))
        copy = QVBoxLayout()
        copy.setSpacing(2)
        title = QLabel(tr("CPU security mitigations"))
        title.setProperty("sectionTitle", True)
        copy.addWidget(title)
        detail = QLabel(
            tr(
                "Disabling CPU security mitigations can improve some workloads but exposes the system to additional CPU vulnerabilities."
            )
        )
        detail.setProperty("sectionSubtitle", True)
        detail.setWordWrap(True)
        copy.addWidget(detail)
        layout.addLayout(copy, 1)

        mitigation_status = (
            tr("Unavailable")
            if not actionable
            else tr("Reboot required")
            if mitigations.get("reboot_required")
            else tr("Disabled")
            if configured
            else tr("Enabled")
            if available
            else tr("Not detected")
        )
        self.mitigations_status = PillLabel(
            mitigation_status,
            "gray"
            if not actionable
            else "orange"
            if configured or mitigations.get("reboot_required")
            else "green",
        )
        self.mitigations_status.setVisible(actionable)
        layout.addWidget(self.mitigations_status)

        self.mitigations_apply_button = QPushButton(
            tr(
                "Managed externally"
                if configured and not managed
                else "Restore mitigations"
                if mitigation_action == "restore"
                else "Disable mitigations"
            )
        )
        self.mitigations_apply_button.setProperty(
            "dangerAction", mitigation_action == "disable"
        )
        self.mitigations_apply_button.clicked.connect(
            lambda: self._choose(f"bazzite_mitigations_{mitigation_action}", "")
        )
        self.mitigations_apply_button.setEnabled(
            actionable and available and (not configured or managed)
        )
        if configured and not managed:
            self.mitigations_apply_button.setToolTip(
                tr(
                    "mitigations=off was configured outside Control Center and is preserved."
                )
            )
        elif not actionable:
            self.mitigations_apply_button.setToolTip(
                tr("This workflow is available only on Bazzite.")
            )
        layout.addWidget(self.mitigations_apply_button)
        return card

    def _update_memory_apply_availability(self) -> None:
        if not hasattr(self, "memory_swap_apply_button"):
            return
        self._update_vram_apply_availability()
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

    def _update_vram_apply_availability(self) -> None:
        """VRAM (UMA_SIZE) is written straight to CMOS; it needs no distro adapter."""
        if not hasattr(self, "vram_apply_button"):
            return
        setup = _dict(self.tools.get("system_setup"))
        vram = _dict(setup.get("vram"))
        supported = bool(setup.get("helper_available") and vram.get("supported"))
        selected = _integer(self.vram_size_combo.currentData(), 0) != 0
        self.vram_apply_button.setEnabled(supported and selected)
        reason = str(setup.get("reason") or vram.get("reason") or "")
        tooltip = (
            tr(reason)
            if reason
            else tr("Written to CMOS immediately; takes effect after the next reboot.")
        )
        self.vram_size_combo.setToolTip(tooltip)
        self.vram_apply_button.setToolTip(tooltip)

    def _quick_access_page(self) -> QScrollArea:
        """Build the explicit, optional SteamOS/Bazzite/CachyOS Decky page.

        Decky is intentionally not represented as a regular preparation
        component: it is a separate third-party root-plugin environment and
        needs a dedicated confirmation path.
        """
        inventory = _dict(self.tools.get("quick_access"))
        ready = bool(inventory.get("ready"))
        decky_detected = bool(inventory.get("decky_detected"))
        decky_frontend_compatible = bool(
            inventory.get("decky_frontend_compatible", True)
        )
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
        elif not decky_frontend_compatible:
            detail_text = "Decky must be updated because this Steam client uses the renamed initialization API."
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
                if decky_detected and decky_frontend_compatible
                else "Install Decky + Quick Access (Beta)"
            )
        )
        install.setObjectName("PrimaryAction")
        install.setToolTip(
            tr(
                "Beta boundary: after your explicit confirmation in this dialog, this workflow downloads the official Decky stable installer and displays its SHA-256. On Steam clients that require the renamed initialization API, it may then use the official Decky prerelease compatibility installer. It finally installs the local BC250 panel and never changes GPU voltage, custom clocks, boot settings or hardware state."
            )
        )
        install.clicked.connect(
            lambda: self._choose(
                "quick_access_plugin"
                if decky_detected and decky_frontend_compatible
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
        presentation = present_gfx1013(
            state, include_fsr4=GFX1013_FSR4_UI_ENABLED
        )

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

        complete_detail = " ".join(
            tr_format(part, **presentation.detail_values) for part in presentation.detail
        )

        card.setToolTip(complete_detail)
        route = presentation.radv_route
        reviewed = tr_format(
            "Reviewed upstream: {version} · {commit}",
            version=(
                f"RADV {route.values.get('version', '')}"
                if route is not None
                else str(state.get("reviewed_version") or "0.2.0-alpha")
            ),
            commit=(
                RADV_ASYNC_REVIEWED_COMMIT
                if route is not None
                else str(state.get("reviewed_commit") or "")
            )[:7],
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
                # Upstream boots the patched entry once; these switch it on.
                patched_boot = bool(state.get("dryhopped_boot_active"))
                boot_action = (
                    "gfx1013_fedora_activate" if patched_boot else "gfx1013_fedora_boot_patched"
                )
                boot = QPushButton(
                    tr("Make the fix the default" if patched_boot else "Boot with the fix")
                )
                boot.setProperty("dependencyGfxAction", True)
                boot.setProperty("dependencyGfxPrimary", True)
                boot.clicked.connect(lambda: self._choose(boot_action, ""))
                actions.addWidget(boot, 1)
                uninstall = QPushButton(tr("Uninstall"))
                uninstall.setProperty("dangerAction", True)
                uninstall.setProperty("dependencyGfxAction", True)
                uninstall.clicked.connect(
                    lambda: self._choose("gfx1013_fedora_uninstall", "")
                )
                actions.addWidget(uninstall, 1)
        if route is not None:
            # Fedora on kernel 7.2+: the patched RADV alone.
            radv_action = (
                "radv_async_install"
                if route.build
                else "radv_async_disable"
                if route.enabled
                else "radv_async_enable"
            )
            primary = QPushButton(tr(
                "Build and install"
                if route.build
                else "Switch off"
                if route.enabled
                else "Switch on"
            ))
            primary.setProperty("dependencyGfxAction", True)
            primary.setProperty("dependencyGfxPrimary", True)
            primary.clicked.connect(lambda: self._choose(radv_action, ""))
            actions.addWidget(primary, 1)
            if route.testable:
                test = QPushButton(tr("Test async compute"))
                test.setProperty("dependencyGfxAction", True)
                test.clicked.connect(lambda: self._choose("radv_async_test", ""))
                actions.addWidget(test, 1)
            if route.installed:
                remove = QPushButton(tr("Remove"))
                remove.setProperty("dangerAction", True)
                remove.setProperty("dependencyGfxAction", True)
                remove.clicked.connect(lambda: self._choose("radv_async_uninstall", ""))
                actions.addWidget(remove, 1)
            if route.remove_fix_action:
                remove_fix = QPushButton(tr("Remove the kernel-side fix"))
                remove_fix.setProperty("dangerAction", True)
                remove_fix.setProperty("dependencyGfxAction", True)
                remove_fix.clicked.connect(
                    lambda: self._choose(route.remove_fix_action, "")
                )
                actions.addWidget(remove_fix, 1)
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

    def _debian_kernel_card(self, upgrade: dict) -> QFrame:
        """Debian 13: the stock kernel and Mesa cannot drive the GPU; backports can."""
        pending_restart = str(upgrade.get("state") or "") == "reboot-required"
        with_kernel = bool(upgrade.get("install_kernel", True))
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
        title = QLabel(tr("Newer kernel and Mesa for the BC-250"))
        title.setProperty("sectionTitle", True)
        subtitle = QLabel(tr("Debian backports · needed for GPU acceleration"))
        subtitle.setProperty("sectionSubtitle", True)
        subtitle.setWordWrap(True)
        copy.addWidget(title)
        copy.addWidget(subtitle)
        header.addLayout(copy, 1)
        header.addWidget(
            PillLabel(
                tr("Restart required") if pending_restart else tr("Recommended"),
                "blue" if pending_restart else "orange",
            )
        )
        layout.addLayout(header)

        warning = QLabel(
            tr(
                "A newer kernel is already installed. Restart to use it, then build the GFX1013 fix."
            )
            if pending_restart
            else (
                tr(
                    "Optional. The Debian kernel and Mesa do not recognize the BC-250 GPU, so the desktop is drawn by the CPU and feels slow. This installs a newer Mesa and kernel from Debian backports; the current kernel stays in the boot menu."
                )
                if with_kernel
                else tr(
                    "Optional. The Mesa that Debian 13 ships does not recognize the BC-250 GPU, so the desktop is drawn by the CPU and feels slow. This installs the newer Mesa from Debian backports."
                )
            )
        )
        warning.setProperty("warningText", True)
        warning.setWordWrap(True)
        layout.addWidget(warning)

        actions = QHBoxLayout()
        actions.addStretch(1)
        install = QPushButton(tr("Install from backports"))
        install.setObjectName("PrimaryAction")
        install.setEnabled(not pending_restart)
        install.clicked.connect(lambda: self._choose("debian_kernel_install", ""))
        actions.addWidget(install)
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
        url = (
            BAZZITE_ASYNC_COMPUTE_REPOSITORY
            if str(state.get("reason_key") or "").startswith("bazzite-release-")
            # Fedora's patched-RADV route builds that project's patches.
            or present_gfx1013(state).radv_route is not None
            else str(
                state.get("upstream_url")
                or "https://github.com/DryhoppedIPA/bc250-gfx1013-fix"
            )
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
        elif action == "vram_apply":
            self.vram_uma_size_mb = _integer(self.vram_size_combo.currentData(), 0)
        if action == "prepare" and hasattr(self, "component_switches"):
            self.selected_components = {
                key
                for key, switch in self.component_switches.items()
                if switch.isChecked()
            }
        self.accept()


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


class GpuProfileEditDialog(QDialog):
    """Rename a Cyan operating profile and pick its safe-point-based range.

    The voltage always comes from the same validated safe-point list the
    rest of this page uses (never a free-typed value), matching the
    conservative "Safe mode" this page advertises everywhere else.
    """

    def __init__(
        self,
        *,
        name: str,
        minimum_mhz: int,
        maximum_mhz: int,
        reference_frequency: int,
        safe_points: list[tuple[int, int]],
        allowed_min: int,
        allowed_max: int,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("InfoDialog")
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(application_stylesheet())
        self.setWindowTitle(tr("Edit profile"))
        enable_adaptive_dialog(
            self, preferred_width=460, preferred_height=440,
            minimum_width=360, minimum_height=380,
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
        heading.addWidget(IconBadge("settings_blue", COLORS["blue_soft"], 40, radius=11))
        heading_copy = QVBoxLayout()
        heading_copy.setSpacing(3)
        title = QLabel(tr("Edit profile"))
        title.setProperty("dialogTitle", True)
        subtitle = QLabel(
            tr("Pick a validated safe-point and set the range this profile applies.")
        )
        subtitle.setProperty("dialogBody", True)
        subtitle.setWordWrap(True)
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

        divider = QFrame()
        divider.setObjectName("CardDivider")
        divider.setFixedHeight(1)
        root.addWidget(divider)

        name_label = QLabel(tr("Profile name"))
        name_label.setProperty("fieldLabel", True)
        root.addWidget(name_label)
        self.name_input = QLineEdit(name)
        self.name_input.setMaxLength(30)
        root.addWidget(self.name_input)

        point_label = QLabel(tr("Reference safe-point (frequency and voltage)"))
        point_label.setProperty("fieldLabel", True)
        root.addWidget(point_label)
        self.point_combo = GuardedComboBox()
        for frequency, voltage in safe_points:
            self.point_combo.addItem(
                f"{frequency} MHz · {voltage} mV" if voltage else f"{frequency} MHz",
                (frequency, voltage),
            )
        preselect = self.point_combo.findData(
            next((pair for pair in safe_points if pair[0] == reference_frequency), None)
        )
        if preselect < 0 and self.point_combo.count():
            preselect = 0
        if preselect >= 0:
            self.point_combo.setCurrentIndex(preselect)
        root.addWidget(self.point_combo)

        self.minimum_field = FrequencyField(
            "Minimum frequency", "Governor floor for this profile.", minimum_mhz
        )
        self.minimum_field.set_limits(allowed_min, allowed_max)
        self.maximum_field = FrequencyField(
            "Maximum frequency", "Governor ceiling for this profile.", maximum_mhz
        )
        self.maximum_field.set_limits(allowed_min, allowed_max)
        root.addWidget(self.minimum_field)
        root.addWidget(self.maximum_field)

        footer = QHBoxLayout()
        footer.addStretch(1)
        cancel = QPushButton(tr("Cancel"))
        cancel.setProperty("compactAction", True)
        cancel.clicked.connect(self.reject)
        save = QPushButton(tr("Save profile"))
        save.setObjectName("DialogPrimary")
        save.setDefault(True)
        save.clicked.connect(self._validate_and_accept)
        footer.addWidget(cancel)
        footer.addWidget(save)
        root.addLayout(footer)

    def _validate_and_accept(self) -> None:
        minimum = self.minimum_field.value()
        maximum = self.maximum_field.value()
        if minimum > maximum:
            minimum, maximum = maximum, minimum
            self.minimum_field.setValue(minimum)
            self.maximum_field.setValue(maximum)
        self.accept()

    def result_profile(self) -> dict:
        frequency, voltage = self.point_combo.currentData() or (0, 0)
        # The source, not its translation: the card translates it when shown.
        name = self.name_input.text().strip() or "Custom"
        return {
            "name": name,
            "min": self.minimum_field.value(),
            "max": self.maximum_field.value(),
            "frequency": int(frequency),
            "voltage": int(voltage),
        }
