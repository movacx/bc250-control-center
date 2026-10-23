"""The pages and panels the preparation sidebar builds."""

from __future__ import annotations

from collections.abc import Mapping

from PyQt6.QtCore import (
    Qt,
)
from PyQt6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtWidgets import QPushButton as IconButton

from bc250cc.infrastructure.bazzite_async_compute import BAZZITE_ASYNC_COMPUTE_ICD
from bc250cc.infrastructure.system_setup import CU_UNLOCK_THERMAL_NOTE

from ..core.feature_visibility import (
    FSR4_UI_ENABLED,
    GFX1013_FSR4_UI_ENABLED,
    HELIXSR_UI_ENABLED,
)
from ..i18n import tr, tr_format
from .buttons import WrappingButton as QPushButton
from .dashboard_widgets import (  # noqa: E402
    PreparationComponentCard,
    PreparationInfoCard,
    _AllocationTimeline,
    _FittedLineEdit,
    _HelixSRSettings,
    _label,
    _mapping,
    _MemoryOptionRow,
    _UpscalerSection,
    _UpscalingGames,
)
from .system_setup_controls import (
    VRAM_SIZE_CHOICES,
    is_bazzite_host,
    is_steamos_host,
    vram_size_label,
)
from .wheel_guard import GuardedComboBox
from .widgets import IconBadge, PillLabel, icon


class PreparationPagesMixin:
    """Methods of ``PreparationSidebar`` split out of ``dashboard_widgets``."""

    def _components_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(10)

        self.components_host = QWidget()
        self.components_grid = QGridLayout(self.components_host)
        self.components_grid.setContentsMargins(0, 0, 0, 0)
        self.components_grid.setHorizontalSpacing(8)
        self.components_grid.setVerticalSpacing(8)
        self.component_cards: dict[str, PreparationComponentCard] = {}
        for index, (key, title, detail) in enumerate(self.COMPONENTS):
            card = PreparationComponentCard(key, title, detail)
            card.setProperty("gamepadHorizontalIndex", index)
            card.checkbox.toggled.connect(self._sync_components)
            self.component_cards[key] = card
        # Mitigations, read-only mode and kernel options are not dependency
        # preparation. They live on Additional settings > Compatibility; the
        # Dashboard keeps the panels built (their state is still written) but
        # inside a holder that is never shown.
        self._boot_panels = (
            self._bazzite_mitigations_panel(),
            self._steamos_readonly_panel(),
            self._kernel_options_panel(),
        )
        self._boot_holder = QWidget()
        holder_layout = QVBoxLayout(self._boot_holder)
        holder_layout.setContentsMargins(0, 0, 0, 0)
        holder_layout.setSpacing(8)
        for boot_panel in self._boot_panels:
            holder_layout.addWidget(boot_panel)
        self._boot_holder.hide()
        if not self._standalone:
            layout.addWidget(self._boot_holder)
        layout.addWidget(self.components_host)
        layout.addStretch(1)
        return page

    def _memory_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(8)
        layout.addWidget(self._build_memory_panel())
        layout.addStretch(1)
        return page

    def _build_memory_panel(self) -> QFrame:
        self.memory_panel = QFrame()
        memory_layout = QVBoxLayout(self.memory_panel)
        memory_layout.setContentsMargins(0, 0, 0, 0)
        memory_layout.setSpacing(16)

        panel_header = QHBoxLayout()
        panel_header.setSpacing(10)
        header_copy = QVBoxLayout()
        header_copy.setSpacing(3)
        header_copy.addWidget(_label("Memory & Swap", "dashboardCardTitle"))
        self.memory_detail = _label("Not detected", "dashboardCardSubtitle")
        header_copy.addWidget(self.memory_detail)
        panel_header.addLayout(header_copy, 1)
        self.memory_status_button = QPushButton(tr("View detailed status"))
        self.memory_status_button.setProperty("dashboardCardAction", True)
        self.memory_status_button.setIcon(icon("terminal_blue"))
        self.memory_status_button.setToolTip(
            tr("Opens a full technical report of the current memory and swap state in the built-in terminal.")
        )
        self.memory_status_button.clicked.connect(self._show_memory_status_report)
        panel_header.addWidget(self.memory_status_button, 0, Qt.AlignmentFlag.AlignTop)
        memory_layout.addLayout(panel_header)

        summary = QGridLayout()
        summary.setContentsMargins(0, 0, 0, 0)
        summary.setHorizontalSpacing(10)
        summary.setVerticalSpacing(10)
        self.memory_ram_tile = self._memory_summary_tile("Physical RAM", "—")
        self.memory_zram_tile = self._memory_summary_tile("ZRAM", "—")
        self.memory_backing_tile = self._memory_summary_tile("Disk swap", "—")
        self.memory_zswap_tile = self._memory_summary_tile("ZSWAP", "—")
        for column, tile in enumerate(
            (
                self.memory_ram_tile,
                self.memory_zram_tile,
                self.memory_backing_tile,
                self.memory_zswap_tile,
            )
        ):
            summary.addWidget(tile, 0, column)
            summary.setColumnStretch(column, 1)
        memory_layout.addLayout(summary)

        # ---- Swap and compression ----
        swap_card, swap_layout, swap_header = self._memory_card(
            "memory_green", "green_soft", "Swap and compression"
        )
        self.memory_swap_card = swap_card
        self.memory_scope = PillLabel("Bazzite only", "gray")
        swap_header.addWidget(self.memory_scope)

        self.memory_option_rows_host = QWidget()
        self.memory_option_rows_layout = QVBoxLayout(self.memory_option_rows_host)
        self.memory_option_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.memory_option_rows_layout.setSpacing(8)
        self.memory_option_rows: list[_MemoryOptionRow] = []
        swap_layout.addWidget(self.memory_option_rows_host)

        self.memory_swap_target_label = _label(
            "Swapfile location", "dashboardMemoryControlLabel"
        )
        self.memory_swap_target_combo = GuardedComboBox()
        self.memory_swap_target_combo.setProperty("dashboardMemoryCombo", True)
        self.memory_swap_target_combo.addItem(tr("Default (/var/lib)"), "")
        swap_layout.addWidget(self.memory_swap_target_label)
        swap_layout.addWidget(self.memory_swap_target_combo)
        self.memory_swap_target_label.hide()
        self.memory_swap_target_combo.hide()

        self.memory_zram_warning_frame = QFrame()
        self.memory_zram_warning_frame.setProperty("dashboardMemoryNote", True)
        self.memory_zram_warning_frame.setProperty("tone", "orange")
        warning_row = QHBoxLayout(self.memory_zram_warning_frame)
        warning_row.setContentsMargins(10, 8, 10, 8)
        warning_row.setSpacing(8)
        warning_row.addWidget(IconBadge("warning_orange", "orange_soft", 32))
        self.memory_zram_warning = _label("", "dashboardMemoryWarning")
        self.memory_zram_warning.setWordWrap(True)
        warning_row.addWidget(self.memory_zram_warning, 1)
        self.memory_zram_warning_frame.hide()
        swap_layout.addWidget(self.memory_zram_warning_frame)

        usage_row = QHBoxLayout()
        usage_row.setSpacing(8)
        self.memory_swap_usage_bar = QProgressBar()
        self.memory_swap_usage_bar.setProperty("dashboardMemoryUsage", True)
        self.memory_swap_usage_bar.setTextVisible(False)
        self.memory_swap_usage_bar.setRange(0, 100)
        self.memory_swap_usage_bar.setFixedHeight(6)
        usage_row.addWidget(self.memory_swap_usage_bar, 1)
        self.memory_swap_usage_label = _label("", "dashboardMemoryDetail", wrap=False)
        usage_row.addWidget(self.memory_swap_usage_label)
        self.memory_usage_row = usage_row
        self.memory_swap_usage_bar.hide()
        self.memory_swap_usage_label.hide()
        swap_layout.addLayout(usage_row)

        self.memory_policy_combo = GuardedComboBox()
        self.memory_policy_combo.setProperty("dashboardMemoryCombo", True)
        for label, value in (
            ("Keep Bazzite default (ZRAM)", "current"),
            ("Recommended · ZRAM + 16 GiB emergency swap", "zram-swap-16"),
            ("Advanced · ZSWAP + 16 GiB swapfile", "zswap-16"),
            ("Advanced heavy loads · ZSWAP + 32 GiB swapfile", "zswap-32"),
        ):
            self.memory_policy_combo.addItem(tr(label), value)
        # The combo stays the real, tested source of truth for the selected
        # policy; _MemoryOptionRow is only its on-screen presentation.
        self.memory_policy_combo.hide()
        swap_actions = QHBoxLayout()
        swap_actions.addStretch(1)
        self.memory_swap_apply_button = QPushButton(tr("Apply Swap"))
        self.memory_swap_apply_button.setProperty("dashboardCardAction", True)
        self.memory_swap_apply_button.clicked.connect(self._request_memory_swap)
        swap_actions.addWidget(self.memory_swap_apply_button)
        swap_layout.addLayout(swap_actions)
        memory_layout.addWidget(swap_card)

        # ---- TTM + VRAM ----
        gpu_row = QGridLayout()
        gpu_row.setHorizontalSpacing(16)
        gpu_row.setVerticalSpacing(16)
        gpu_row.setColumnStretch(0, 1)
        gpu_row.setColumnStretch(1, 1)

        ttm_card, ttm_layout, _ttm_header = self._memory_card(
            "gpu_purple", "purple_soft", "Dynamic GPU Memory Limit (TTM)"
        )
        self.memory_ttm_card = ttm_card
        self.memory_ttm_readout = _label("—", "metricTileValue", wrap=False)
        ttm_layout.addWidget(self.memory_ttm_readout)
        # What the next boot will use, from the state Game Mode shares.
        self.memory_ttm_state = _label("", "dashboardMemoryDetail")
        ttm_layout.addWidget(self.memory_ttm_state)
        self.ttm_limit_combo = GuardedComboBox()
        self.ttm_limit_combo.setProperty("dashboardMemoryCombo", True)
        self.ttm_limit_combo.addItem(tr("Keep current TTM limit"), 0)
        self.ttm_limit_combo.addItem(tr("Kernel default (remove BC250 TTM limit)"), -1)
        for target in (8, 10, 12):
            self.ttm_limit_combo.addItem(
                tr_format("Limit GPU allocations to {size} GiB", size=target), target
            )
        self.ttm_limit_combo.hide()
        self.ttm_limit_combo.currentIndexChanged.connect(self._update_ttm_readout)
        self.memory_ttm_timeline = _AllocationTimeline(self.ttm_limit_combo)
        ttm_layout.addWidget(self.memory_ttm_timeline)
        ttm_layout.addWidget(
            _label(
                "TTM limits managed GPU pages; it is not a guaranteed VRAM reservation.",
                "dashboardMemoryDetail",
            )
        )
        self.memory_ttm_apply_button = QPushButton(tr("Apply TTM"))
        self.memory_ttm_apply_button.setProperty("dashboardCardAction", True)
        self.memory_ttm_apply_button.clicked.connect(self._request_memory_ttm)
        ttm_layout.addWidget(self.memory_ttm_apply_button)
        gpu_row.addWidget(ttm_card, 0, 0)

        vram_card, vram_layout, _vram_header = self._memory_card(
            "vram_gray", "cyan_soft", "VRAM size (UMA_SIZE)"
        )
        self.memory_vram_card = vram_card
        self.memory_vram_readout = _label("—", "metricTileValue", wrap=False)
        vram_layout.addWidget(self.memory_vram_readout)
        self._tools_snapshot: Mapping[str, object] = {}
        self.vram_size_combo = GuardedComboBox()
        self.vram_size_combo.setProperty("dashboardMemoryCombo", True)
        self.vram_size_combo.addItem(tr("Keep current VRAM size"), 0)
        for target in VRAM_SIZE_CHOICES:
            self.vram_size_combo.addItem(vram_size_label(target), target)
        self.vram_size_combo.hide()
        self.vram_size_combo.currentIndexChanged.connect(self._update_vram_control)
        self.memory_vram_timeline = _AllocationTimeline(self.vram_size_combo)
        vram_layout.addWidget(self.memory_vram_timeline)
        self.vram_apply_button = QPushButton(tr("Apply VRAM"))
        self.vram_apply_button.setProperty("dashboardCardAction", True)
        self.vram_apply_button.clicked.connect(self._request_vram_apply)
        vram_layout.addWidget(self.vram_apply_button)
        gpu_row.addWidget(vram_card, 0, 1)
        memory_layout.addLayout(gpu_row)

        self._sync_memory_option_rows()
        self._update_ttm_readout()
        self._update_vram_readout()
        return self.memory_panel

    def _build_memory_status_report(self) -> str:
        """Compose the human-readable report shown in the embedded terminal.

        Pulled entirely from the state already cached for the on-screen
        tiles/combos, so opening it never waits on the privileged helper or
        touches the system — it is read-only by construction.
        """
        tools = _mapping(self._tools_snapshot) or _mapping(self._tools)
        setup = _mapping(tools.get("system_setup"))
        memory = _mapping(setup.get("memory"))
        runtime = _mapping(tools.get("memory_runtime"))
        host_label = (
            "Bazzite" if is_bazzite_host(tools)
            else "SteamOS" if is_steamos_host(tools)
            else tr("Generic Linux host")
        )

        physical = self._report_gib(runtime.get("physical_ram_bytes"), default=tr("unknown"))
        zram_active = bool(runtime.get("zram_active"))
        zram_line = (
            self._report_gib(runtime.get("zram_total_bytes"), default=tr("unknown"))
            if zram_active else tr("Disabled")
        )
        backing_line = tr("Active") if runtime.get("backing_swap_active") else tr("None")
        zswap_line = tr("Active") if runtime.get("zswap_enabled") is True else tr("Disabled")
        # Which compressor each one really uses, read from the kernel.
        zram_algorithms = [str(name) for name in runtime.get("zram_algorithms") or () if name]
        if zram_active and zram_algorithms:
            zram_line = f"{zram_line} · {', '.join(zram_algorithms)}"
        zswap_compressor = str(runtime.get("zswap_compressor") or "")
        if runtime.get("zswap_enabled") is True and zswap_compressor:
            zswap_line = f"{zswap_line} · {zswap_compressor}"
        ttm_bytes = runtime.get("ttm_limit_bytes")
        ttm_line = (
            self._report_gib(ttm_bytes, default=tr("unknown"))
            if isinstance(ttm_bytes, (int, float)) and ttm_bytes
            else tr("Kernel default (no BC250 limit set)")
        )

        used_bytes = memory.get("swap_used_bytes")
        swap_active = bool(memory.get("swap_active"))
        usage_line = (
            tr_format(
                "{used} in use",
                used=self._report_gib(used_bytes, default=tr("unknown")),
            )
            if swap_active and isinstance(used_bytes, (int, float))
            else tr("Not in use right now")
        )
        configured_id = str(memory.get("configured_policy") or "")
        # The policy's own label from the list ("Advanced · ZSWAP + 32 GiB
        # swapfile"), not its id; the id when the list does not offer it.
        policy_combo, ttm_combo = self.memory_policy_combo, self.ttm_limit_combo
        find = getattr(policy_combo, "findData", None)
        index = find(configured_id) if configured_id and find else -1
        configured_policy = (
            self.memory_policy_combo.itemText(index) if index >= 0 and configured_id != "preserve"
            else configured_id or tr("none applied yet")
        )
        reboot_pending = any(
            memory.get(key)
            for key in ("restore_pending", "zram_pending", "zram_restore_pending", "zswap_pending")
        )

        selected_policy = self.memory_policy_combo.currentText()
        selected_ttm = self.ttm_limit_combo.currentText()
        # "Keep current" says what is kept, so a choice just applied does not
        # read as if nothing had been picked.
        policy_data = getattr(policy_combo, "currentData", lambda: None)()
        ttm_data = getattr(ttm_combo, "currentData", lambda: None)()
        if policy_data == "preserve" and configured_id not in {"", "preserve"}:
            selected_policy = f"{selected_policy} ({configured_policy})"
        if ttm_data == 0 and isinstance(ttm_bytes, (int, float)) and ttm_bytes:
            selected_ttm = f"{selected_ttm} ({ttm_line})"
        selected_vram = self.vram_size_combo.currentText()

        lines: list[str] = []
        lines += self._report_banner(tr("BC250 CONTROL CENTER - MEMORY & SWAP STATUS"))

        lines += self._report_heading(tr("Current state"))
        lines.append(self._report_field(tr("Detected system"), host_label))
        lines.append(self._report_field(tr("Physical RAM"), physical))
        lines.append("")
        lines.append(self._report_field(tr("ZRAM (compressed RAM swap)"), zram_line))
        lines.append(self._report_field(tr("Disk swap (swapfile on disk)"), backing_line))
        lines.append(self._report_field(tr("ZSWAP (compressed cache before swap)"), zswap_line))
        lines.append(self._report_field(tr("Swap usage right now"), usage_line))
        lines.append("")
        lines.append(self._report_field(tr("Active swap policy"), tr(configured_policy)))
        lines.append(self._report_field(tr("GPU memory limit (TTM) applied"), ttm_line))
        if reboot_pending:
            lines.append("")
            lines += self._report_paragraph(
                tr("[!] A change is saved but needs a REBOOT before it takes full effect.")
            )

        lines += self._report_heading(tr("Selected in the UI (not applied yet)"))
        lines.append(self._report_field(tr("Swap option"), selected_policy))
        lines.append(self._report_field(tr("TTM limit"), selected_ttm))
        lines.append(self._report_field(tr("VRAM size"), selected_vram))
        lines.append("")
        lines += self._report_paragraph(
            tr(
                "Nothing above changes anything by itself: press \"Apply Swap\", "
                "\"Apply TTM\" or \"Apply VRAM\" in the dashboard to actually apply it."
            )
        )
        return "\n".join(lines)

    def _kernel_options_panel(self) -> QFrame:
        """mitigations=off, nosmt and the kernel's CU unlock for mutable distributions.

        Bazzite keeps its own mitigations card, so this panel only appears
        where the protected helper reports a Limine, GRUB, grubby or SteamOS
        boot configuration it can manage. SteamOS has no CU unlock row.
        """
        panel = QFrame()
        self.kernel_options_panel = panel
        panel.setProperty("dashboardMemoryPanel", True)
        panel.setProperty("dashboardBootPanel", True)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        root = QVBoxLayout(panel)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)
        root.addWidget(_label("Kernel boot options", "dashboardComponentTitle", wrap=False))
        detail = _label(
            "Both apply at the next boot and can be restored here. Disabling mitigations exposes the system to CPU vulnerabilities; disabling SMT leaves one thread per core.",
            "dashboardMemoryDetail",
        )
        detail.setWordWrap(True)
        root.addWidget(detail)
        self.kernel_option_controls: dict[str, tuple[QLabel, PillLabel, QPushButton]] = {}
        # Each option is one row: its name, then its state and its action side
        # by side in two columns of fixed width, so the eye does not cross the
        # whole panel to connect a state with the button that changes it.
        grid = QGridLayout()
        grid.setContentsMargins(0, 2, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(0)
        grid.setColumnStretch(0, 1)
        root.addLayout(grid)
        self.kernel_option_grid = grid
        self.kernel_option_rows: dict[str, int] = {}
        self.kernel_option_rules: dict[str, QFrame] = {}
        for index, (option, title, _disable, _restore) in enumerate(self.KERNEL_OPTION_ROWS):
            row = index * 2
            if index:
                rule = QFrame()
                rule.setObjectName("ListDivider")
                rule.setFixedHeight(1)
                grid.addWidget(rule, row - 1, 0, 1, 3)
                self.kernel_option_rules[option] = rule
            name = _label(title, "dashboardComponentTitle", wrap=False)
            pill = PillLabel("Checking", "gray")
            pill.setMinimumWidth(self._KERNEL_STATE_WIDTH)
            button = QPushButton(tr(_disable))
            button.setProperty("dashboardCardAction", True)
            button.setMinimumWidth(self._KERNEL_ACTION_WIDTH)
            button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda _checked=False, value=option: self._request_kernel_option(value))
            grid.addWidget(name, row, 0, Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(pill, row, 1, Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(button, row, 2, Qt.AlignmentFlag.AlignVCenter)
            grid.setRowMinimumHeight(row, self._KERNEL_ROW_HEIGHT)
            self.kernel_option_rows[option] = row
            self.kernel_option_controls[option] = (name, pill, button)
        # Said once, under the rows, and only while the unlock row is shown.
        self.kernel_cu_note = _label(
            "The kernel unlocks the compute units itself, so umr and the CU live manager are not needed: turn the live manager's boot service off so only one of them sets the CUs. If your board has a damaged CU pair, not all 40 will work; mask the pair with amdgpu.disable_cu (see the linux-cachyos-bc250 README). Applies at the next boot.",
            "dashboardMemoryDetail",
        )
        self.kernel_cu_note.setWordWrap(True)
        self.kernel_cu_note.hide()
        root.addWidget(self.kernel_cu_note)
        # Power and heat are the real cost of the extra units, so they are said
        # next to the unlock and not only when it is confirmed.
        self.kernel_cu_heat = _label(CU_UNLOCK_THERMAL_NOTE, "dashboardMemoryDetail")
        self.kernel_cu_heat.setWordWrap(True)
        self.kernel_cu_heat.hide()
        root.addWidget(self.kernel_cu_heat)
        # SMT can also be switched while the system runs: now, and not kept.
        self.smt_live_rule = QFrame()
        self.smt_live_rule.setObjectName("ListDivider")
        self.smt_live_rule.setFixedHeight(1)
        root.addWidget(self.smt_live_rule)
        self.smt_live_row = QWidget()
        live = QHBoxLayout(self.smt_live_row)
        live.setContentsMargins(0, 0, 0, 0)
        live.setSpacing(8)
        live.addWidget(_label("SMT right now", "dashboardComponentTitle", wrap=False), 1)
        self.smt_live_pill = PillLabel("Checking", "gray")
        self.smt_live_pill.setMinimumWidth(self._KERNEL_STATE_WIDTH)
        live.addWidget(self.smt_live_pill)
        self.smt_live_button = QPushButton(tr("Turn SMT off now"))
        self.smt_live_button.setProperty("dashboardCardAction", True)
        self.smt_live_button.setMinimumWidth(self._KERNEL_ACTION_WIDTH)
        self.smt_live_button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.smt_live_button.clicked.connect(self._request_smt_live)
        live.addWidget(self.smt_live_button)
        root.addWidget(self.smt_live_row)
        self._smt_live_target = "off"
        self.smt_live_rule.hide()
        self.smt_live_row.hide()
        self._kernel_options_state: dict[str, object] = {}
        panel.hide()
        return panel

    def _compatibility_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(8)

        self.compatibility_filter_panel = QFrame()
        self.compatibility_filter_panel.setProperty(
            "dashboardCompatibilityFilter", True
        )
        filter_layout = QHBoxLayout(self.compatibility_filter_panel)
        filter_layout.setContentsMargins(12, 8, 12, 8)
        filter_layout.setSpacing(8)
        filter_layout.addWidget(
            _label("Show compatibility for", "dashboardCompatibilityLabel", wrap=False)
        )
        self.compatibility_filter = GuardedComboBox()
        self.compatibility_filter.setProperty("dashboardMemoryCombo", True)
        self.compatibility_filter.setProperty("gamepadEntry", True)
        self.compatibility_filter.setMinimumWidth(0)
        self.compatibility_filter.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.compatibility_filter.setAccessibleName(
            tr("Compatibility distribution filter")
        )
        self.compatibility_filter.setToolTip(
            tr(
                "The detected distribution is selected by default. Your last filter is remembered."
            )
        )
        self.compatibility_filter_entries = (
            ("Detected system", "detected"),
            ("All distributions", "all"),
            ("SteamOS", "steamos"),
            ("Bazzite", "bazzite"),
            ("Arch Linux / CachyOS / Manjaro", "arch"),
            ("Fedora", "fedora"),
            ("Ubuntu / Debian", "debian"),
            ("Other distributions", "other"),
        )
        for label, identifier in self.compatibility_filter_entries:
            self.compatibility_filter.addItem(tr(label), identifier)
        stored_filter = str(
            self._settings.value("compatibility/distribution_filter", "detected")
            or "detected"
        )
        selected_index = self.compatibility_filter.findData(stored_filter)
        self.compatibility_filter.setCurrentIndex(max(0, selected_index))
        self.compatibility_filter.currentIndexChanged.connect(
            self._compatibility_filter_changed
        )
        filter_layout.addWidget(self.compatibility_filter, 1)
        layout.addWidget(self.compatibility_filter_panel)
        # The distribution filter stays wired (settings, tests, and the
        # "detected" default all still go through it) but is not shown: it
        # sat above every card fighting for attention, and "detected" is
        # already the right choice for the one system this window is on.
        self.compatibility_filter_panel.hide()
        self.acpi_card = PreparationInfoCard(
            "CPU power management · ACPI",
            "Upstream CPU idle and frequency tables. The original boot entry remains available for recovery.",
            scope_text="Validated · Arch / CachyOS / Manjaro",
            status_text="Not installed",
        )
        self.acpi_card.action_requested.connect(self._forward_dependency_action)
        self.acpi_detail = self.acpi_card.detail
        self.acpi_status = self.acpi_card.status
        self.acpi_install_button = self.acpi_card.add_action(
            "Install correction", {"action": "acpi-install"}
        )
        self.acpi_update_button = self.acpi_card.add_action(
            "Update correction", {"action": "acpi-update"}
        )
        self.acpi_remove_button = self.acpi_card.add_action(
            "Uninstall", {"action": "acpi-uninstall"}, danger=True
        )
        self.acpi_check_button = self.acpi_card.add_action(
            "Check status", {"action": "acpi-status"}
        )
        self.acpi_upstream_button = self.acpi_card.add_action(
            "Open upstream project", {"action": "acpi_upstream"}
        )
        self.acpi_install_button.setEnabled(False)
        self.acpi_update_button.setEnabled(False)
        self.acpi_update_button.setVisible(False)
        self.acpi_remove_button.setEnabled(False)
        layout.addWidget(self.acpi_card)
        self.cyan_card = PreparationInfoCard(
            "Cyan Skillfish Governor",
            "Recommended GPU governor. Supports SMU or patched-kernel controls, selectable load monitoring and D-Bus ranges.",
            action_text="Install / update",
            payload={"action": "prepare", "governor": "cyan-skillfish-governor-smu"},
            secondary_action_text="Uninstall",
            secondary_payload={
                "action": "remove",
                "governor": "cyan-skillfish-governor-smu",
            },
            scope_text="Arch · Fedora · Debian/Ubuntu · Bazzite",
            status_text="Not installed",
        )
        self.oberon_card = PreparationInfoCard(
            "Oberon Governor",
            "Alternative YAML-based backend. GPU telemetry repair remains a separate compatibility step.",
            action_text="Install / update",
            payload={"action": "prepare", "governor": "oberon-governor"},
            secondary_action_text="Uninstall",
            secondary_payload={"action": "remove", "governor": "oberon-governor"},
            scope_text="Alternative backend",
            status_text="Not installed",
        )
        for card in (self.cyan_card, self.oberon_card):
            card.action_requested.connect(self._forward_dependency_action)
            layout.addWidget(card)
        self.gfx_card = PreparationInfoCard(
            "GFX1013 async compute",
            "Kernel and Mesa must be matched. The interface enables installation only on a reviewed distribution path.",
            scope_text="Detecting distribution",
            status_text="Checking",
        )
        self.gfx_primary_button = self.gfx_card.add_action(
            "Open upstream project", {"action": "gfx1013_upstream", "governor": ""}
        )
        self.gfx_secondary_button = self.gfx_card.add_action(
            "Open upstream project", {"action": "gfx1013_upstream", "governor": ""}
        )
        self.gfx_tertiary_button = self.gfx_card.add_action(
            "Open upstream project", {"action": "gfx1013_upstream", "governor": ""}
        )
        self.gfx_quaternary_button = self.gfx_card.add_action(
            "Open upstream project", {"action": "gfx1013_upstream", "governor": ""}
        )
        self.gfx_quinary_button = self.gfx_card.add_action(
            "Open upstream project",
            {"action": "gfx1013_upstream", "governor": ""},
            danger=True,
        )
        self.gfx_secondary_button.hide()
        self.gfx_tertiary_button.hide()
        self.gfx_tertiary_button.setEnabled(GFX1013_FSR4_UI_ENABLED)
        self.gfx_quaternary_button.hide()
        self.gfx_quinary_button.hide()
        self.gfx_card.primary_button = self.gfx_primary_button
        self.gfx_card.secondary_button = self.gfx_secondary_button
        self.gfx_card.action_requested.connect(self._forward_dependency_action)
        self.steamos_graphics_state = QFrame()
        self.steamos_graphics_state.setProperty("dashboardCompatibilityState", True)
        steamos_state_layout = QHBoxLayout(self.steamos_graphics_state)
        steamos_state_layout.setContentsMargins(9, 6, 9, 6)
        steamos_state_layout.setSpacing(8)
        self.steamos_kernel_status = PillLabel("Not installed", "gray")
        self.steamos_radv_status = PillLabel("Not installed", "gray")
        self.steamos_fsr4_status = PillLabel("Not installed", "gray")
        steamos_graphics_rows = [
            ("Kernel / AMDGPU", self.steamos_kernel_status),
            ("Mesa / RADV", self.steamos_radv_status),
        ]
        if GFX1013_FSR4_UI_ENABLED:
            steamos_graphics_rows.append(
                ("FSR4 per game", self.steamos_fsr4_status)
            )
        for label, pill in steamos_graphics_rows:
            steamos_state_layout.addWidget(
                _label(label, "dashboardCompatibilityLabel", wrap=False)
            )
            steamos_state_layout.addWidget(pill)
        steamos_state_layout.addStretch(1)
        self.gfx_card.layout().insertWidget(2, self.steamos_graphics_state)
        self.steamos_graphics_state.hide()
        self.steamos_fsr4_launch_row = QFrame()
        self.steamos_fsr4_launch_row.setProperty("fsr4LaunchOption", True)
        steamos_fsr4_launch_layout = QHBoxLayout(self.steamos_fsr4_launch_row)
        steamos_fsr4_launch_layout.setContentsMargins(8, 5, 6, 5)
        steamos_fsr4_launch_layout.setSpacing(7)
        steamos_fsr4_launch_layout.addWidget(
            _label("Steam launch option", "dashboardCompatibilityLabel", wrap=False)
        )
        steamos_fsr4_launch_layout.addStretch(1)
        self.steamos_fsr4_copy_button = IconButton("⧉")
        self.steamos_fsr4_copy_button.setProperty("fsr4LaunchCopy", True)
        self.steamos_fsr4_copy_button.setFixedSize(30, 30)
        self.steamos_fsr4_copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.steamos_fsr4_copy_button.setAccessibleName(
            tr("Copy Steam launch option")
        )
        self.steamos_fsr4_copy_button.setToolTip(tr("Copy Steam launch option"))
        self.steamos_fsr4_copy_button.clicked.connect(
            self._copy_steamos_fsr4_launch_option
        )
        steamos_fsr4_launch_layout.addWidget(self.steamos_fsr4_copy_button)
        if GFX1013_FSR4_UI_ENABLED:
            self.gfx_card.layout().insertWidget(3, self.steamos_fsr4_launch_row)
        self.steamos_fsr4_launch_row.hide()
        self._steamos_fsr4_launch_option = ""
        # Always-on is off by default after install: without it, async compute
        # only applies to processes launched with VK_DRIVER_FILES set, so the
        # enable command and the per-game launch option both need a quick copy.
        # The value is upstream's own driver_files(): the patched 64-bit ICD,
        # the stock 32-bit one for Proton's helpers, and llvmpipe as the only
        # Vulkan left should amdgpu ever fail to load.
        self._bazzite_async_enable_command = "sudo bc250-async-compute always enable"
        self._bazzite_async_launch_option = (
            f"VK_DRIVER_FILES={BAZZITE_ASYNC_COMPUTE_ICD}:"
            "/usr/share/vulkan/icd.d/radeon_icd.i686.json:"
            "/usr/share/vulkan/icd.d/lvp_icd.x86_64.json %command%"
        )
        self.bazzite_enable_row, self.bazzite_enable_copy_button = self._copy_row(
            "Always-on enable command", "Copy enable command",
            lambda: self._bazzite_async_enable_command,
        )
        self.bazzite_launch_row, self.bazzite_launch_copy_button = self._copy_row(
            "Per-game launch option", "Copy launch option",
            lambda: self._bazzite_async_launch_option,
        )
        # Above the action buttons, whichever optional rows came before.
        gfx_layout = self.gfx_card.layout()
        actions_index = gfx_layout.indexOf(self.gfx_card.actions_panel)
        gfx_layout.insertWidget(actions_index, self.bazzite_launch_row)
        gfx_layout.insertWidget(actions_index, self.bazzite_enable_row)
        layout.addWidget(self.gfx_card)
        self.cachyos_stack_card = PreparationInfoCard(
            "Arch / CachyOS BC-250 graphics stack · includes GFX1013 fix",
            "MastaG's matched kernel and Mesa/RADV include the GFX1013 async-compute fix. They can be installed separately or together; the current kernel stays as a boot fallback.",
            scope_text="Arch Linux · CachyOS",
            status_text="Checking",
        )
        cachyos_state = QFrame()
        cachyos_state.setProperty("dashboardCompatibilityState", True)
        cachyos_state_layout = QHBoxLayout(cachyos_state)
        cachyos_state_layout.setContentsMargins(9, 6, 9, 6)
        cachyos_state_layout.setSpacing(10)
        cachyos_state_layout.addWidget(
            _label("Kernel", "dashboardCompatibilityLabel", wrap=False)
        )
        self.cachyos_kernel_status = PillLabel("Not installed", "gray")
        cachyos_state_layout.addWidget(self.cachyos_kernel_status)
        cachyos_state_layout.addSpacing(8)
        cachyos_state_layout.addWidget(
            _label("Mesa / RADV", "dashboardCompatibilityLabel", wrap=False)
        )
        self.cachyos_mesa_status = PillLabel("Not installed", "gray")
        cachyos_state_layout.addWidget(self.cachyos_mesa_status)
        cachyos_state_layout.addStretch(1)
        self.cachyos_stack_card.layout().insertWidget(2, cachyos_state)
        self.cachyos_kernel_button = self.cachyos_stack_card.add_action(
            "Install kernel", {"action": "cachyos_bc250_kernel", "governor": ""}
        )
        self.cachyos_mesa_button = self.cachyos_stack_card.add_action(
            "Install Mesa", {"action": "cachyos_bc250_mesa", "governor": ""}
        )
        self.cachyos_full_button = self.cachyos_stack_card.add_action(
            "Install kernel + Mesa", {"action": "cachyos_bc250_full", "governor": ""}
        )
        self.cachyos_stack_card.primary_button = self.cachyos_kernel_button
        self.cachyos_stack_card.secondary_button = self.cachyos_mesa_button
        self.cachyos_stack_card.action_requested.connect(
            self._forward_dependency_action
        )
        # Compatibility aliases for callers that previously addressed three cards.
        self.cachyos_kernel_card = self.cachyos_stack_card
        self.cachyos_mesa_card = self.cachyos_stack_card
        self.cachyos_full_card = self.cachyos_stack_card

        # FSR4 INT8 through the BC250 build of OptiScaler Client
        # (daniel-h-0/bc250-fsr4-fork). It patches games with OptiScaler and
        # the optimised DLL, keeps its own backups, and needs no kernel, Mesa
        # or root -- so one workflow serves every distribution.
        self.fsr4_card = PreparationInfoCard(
            "FSR4 INT8 · OptiScaler Client",
            "Installs OptiScaler and the BC250 FSR4 DLL into the games you choose, with a backup of every file it replaces. Your driver and Proton stay as they are.",
            scope_text="All distributions · per game · no root",
            status_text="Checking",
        )
        self._fsr4_launch_option = ""
        self.fsr4_install_button = self.fsr4_card.add_action(
            "Install FSR4", {"action": "fsr4_install", "governor": ""}
        )
        self.fsr4_launch_button = self.fsr4_card.add_action(
            "Open OptiScaler Client", {"action": "fsr4_launch", "governor": ""}
        )
        self.fsr4_steam_all_button = self.fsr4_card.add_action(
            "Add to every Steam game", {"action": "fsr4_steam_option_all", "governor": ""}
        )
        self.fsr4_remove_button = self.fsr4_card.add_action(
            "Remove",
            {"action": "fsr4_uninstall", "governor": ""},
            danger=True,
        )
        self.fsr4_legacy_button = self.fsr4_card.add_action(
            "Remove old FSR4 V3 runtime",
            {"action": "fsr4_legacy_uninstall", "governor": ""},
            danger=True,
        )
        self.fsr4_upstream_button = self.fsr4_card.add_action(
            "Step-by-step guide", {"action": "fsr4_upstream", "governor": ""}
        )
        self.fsr4_card.action_requested.connect(self._forward_dependency_action)
        self.fsr4_card.setEnabled(FSR4_UI_ENABLED)
        self.cachyos_cards = (self.cachyos_stack_card,)
        self._build_helixsr_card()
        for card in self.cachyos_cards:
            layout.addWidget(card)
        self._build_mesa_card()
        layout.addWidget(self.mesa_card)
        self._build_vaapi_card()
        layout.addWidget(self.vaapi_card)
        layout.addStretch(1)
        if self._standalone:
            self._organise_compatibility(layout)
        return page

    def _build_mesa_card(self) -> None:
        """Mesa older than 26.1: Vulkan runs on the GPU but the desktop is drawn by the CPU."""
        self.mesa_card = PreparationInfoCard(
            "Desktop graphics · Mesa",
            "The Mesa of this system does not draw the desktop on the BC-250 GPU, so windows are drawn by the CPU and feel slow, although games using Vulkan already run on the GPU. Mesa 26.1 or newer fixes it. This adds the kisak-mesa PPA, a third-party source, and updates Mesa from it.",
            status_text="Mesa too old for the desktop",
        )
        self.mesa_card.action_requested.connect(self._forward_dependency_action)
        self.mesa_button = self.mesa_card.add_action(
            "Update Mesa", {"action": "mesa_ppa_install", "governor": ""}
        )
        self.mesa_card.setVisible(False)

    def _build_vaapi_card(self) -> None:
        """simpmix's VA-API driver: the video block the BC-250 does not have."""
        self.vaapi_card = PreparationInfoCard(
            "Hardware video · VA-API",
            "The BC-250 has no working video block, so programs fall back to software video. This driver encodes H.264 on the GPU and HEVC mostly on the CPU, and decodes both, for Sunshine, OBS, Steam Remote Play, ffmpeg and browsers.",
            scope_text="Beta",
            status_text="Not installed",
        )
        self.vaapi_card.action_requested.connect(self._forward_dependency_action)
        self.vaapi_install_button = self.vaapi_card.add_action(
            "Install", {"action": "vaapi_install", "governor": ""}
        )
        self.vaapi_test_button = self.vaapi_card.add_action(
            "Test", {"action": "vaapi_test", "governor": ""}
        )
        self.vaapi_flatpak_button = self.vaapi_card.add_action(
            "Allow Flatpak apps", {"action": "vaapi_flatpak", "governor": ""}
        )
        self.vaapi_32_button = self.vaapi_card.add_action(
            "Add 32-bit driver", {"action": "vaapi_install32", "governor": ""}
        )
        self.vaapi_remove_button = self.vaapi_card.add_action(
            "Remove", {"action": "vaapi_uninstall", "governor": ""}, danger=True
        )
        self.vaapi_upstream_button = self.vaapi_card.add_action(
            "Open upstream project", {"action": "vaapi_upstream", "governor": ""}
        )

    def _build_helixsr_card(self) -> None:
        """HelixSR (lonewolf0622/HelixSR): DLSS Model E behind an FSR 3.1 DLL.

        The card owns HelixSR's actions and their state; the Upscaling tab
        lays them out in its own section (see ``_upscaling_page``).
        """
        self.helixsr_card = PreparationInfoCard(
            "HelixSR",
            "DLSS's neural network running on this GPU, in place of a game's FSR 3.1 upscaler.",
            status_text="Checking",
        )
        self.helixsr_scan_button = self.helixsr_card.add_action(
            "Find FSR 3.1 games", {"action": "helixsr_scan", "governor": ""}
        )
        self.helixsr_network_button = self.helixsr_card.add_action(
            "Build network files", {"action": "helixsr_network", "governor": ""}
        )
        self.helixsr_install_button = self.helixsr_card.add_action(
            "Install HelixSR", {"action": "helixsr_install", "governor": ""}
        )
        # HelixSR 2.0 on: DLSS frame generation, for games with HelixSR Scaler.
        self.helixsr_fg_button = self.helixsr_card.add_action(
            "Build frame generation", {"action": "helixsr_fg", "governor": ""}
        )
        self.helixsr_remove_button = self.helixsr_card.add_action(
            "Remove",
            {"action": "helixsr_uninstall", "governor": ""},
            danger=True,
        )
        self.helixsr_upstream_button = self.helixsr_card.add_action(
            "Open upstream project", {"action": "helixsr_upstream", "governor": ""}
        )
        self.helixsr_card.action_requested.connect(self._forward_dependency_action)
        self.helixsr_card.setEnabled(HELIXSR_UI_ENABLED)
        self.helixsr_card.setVisible(HELIXSR_UI_ENABLED)

    def _upscaling_page(self) -> QWidget:
        """Additional settings > Upscaling, in the GPU page's style.

        One page card per upscaler, side by side: its state as readings,
        its games, and a footer with the next step as the blue button on
        the right. The FSR4 and HelixSR cards stay the owners of every
        action button (text, state, payload); they are only kept out of
        sight while their buttons sit in these sections.
        """
        page = QWidget()
        page.setProperty("upscalingPage", True)
        page.setProperty("redesignedModule", True)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(0)
        self.upscaling_sources = QWidget(page)
        sources = QVBoxLayout(self.upscaling_sources)
        for card in (self.fsr4_card, self.helixsr_card):
            sources.addWidget(card)
        self.upscaling_sources.hide()

        self.fsr4_section = _UpscalerSection(
            "FSR4 INT8", "AMD's FSR 4 in INT8, installed per game by OptiScaler Client.", "fsr4"
        )
        self.fsr4_guide_button = self.fsr4_section.add_header_button(
            "Guide", lambda: self.fsr4_upstream_button.click()
        )
        self._as_guide_link(self.fsr4_guide_button)
        self.fsr4_guide_button.setToolTip(tr(
            "Step by step on GitHub (daniel-h-0/bc250-fsr4-fork): installing OptiScaler in a game, the Steam launch option and undoing it."
        ))
        # The Steam launch option: always in view at the head of the games
        # table, where each game says whether it has it, with a copy.
        # The client build Install or Update brings in, as for HelixSR: the
        # recommended one unless the user picks another from GitHub's list.
        self.fsr4_version_combo = GuardedComboBox()
        self.fsr4_version_combo.setAccessibleName(tr("OptiScaler Client version"))
        self.fsr4_version_combo.setToolTip(tr(
            "The OptiScaler Client build Install or Update brings in. The recommended one is the build this version of Control Center was checked with."
        ))
        self.fsr4_version_combo.activated.connect(self._select_fsr4_release)
        self.fsr4_releases_button = self._releases_button(
            "Checks GitHub for newer OptiScaler Client builds. Control Center also checks on its own twice a day.",
            "fsr4_releases",
        )
        # The Steam launch option: what loads OptiScaler, so it serves every
        # game that has one (OptiScaler Client's, HelixSR Scaler, one put in
        # by hand). A strip at the head of the games table, with a copy.
        self.fsr4_launch_panel = QFrame()
        self.fsr4_launch_panel.setProperty("launchStrip", True)
        launch_row = QHBoxLayout(self.fsr4_launch_panel)
        launch_row.setContentsMargins(12, 6, 6, 6)
        launch_row.setSpacing(8)
        launch_text = QVBoxLayout()
        launch_text.setSpacing(0)
        launch_text.addWidget(_label("Steam launch option", "readingLabel", wrap=False))
        launch_text.addWidget(_label("For games with OptiScaler or HelixSR Scaler", "settingHint", wrap=False))
        launch_row.addLayout(launch_text)
        launch_row.addStretch(1)
        self.fsr4_launch_field = _FittedLineEdit()
        self.fsr4_launch_field.setAccessibleName(tr("Steam launch option"))
        self.fsr4_launch_field.setToolTip(
            tr("Steam loads OptiScaler only with this option. Close Steam before adding it.")
        )
        self.fsr4_launch_field.setReadOnly(True)
        self.fsr4_launch_field.setProperty("i18nLiteral", True)
        self.fsr4_launch_field.setProperty("launchOption", True)
        self.fsr4_launch_field.setMinimumWidth(320)
        launch_row.addWidget(self.fsr4_launch_field)
        self.fsr4_copy_button = QPushButton("")
        self.fsr4_copy_button.setIcon(icon("copy_gray"))
        self.fsr4_copy_button.setProperty("compactAction", True)
        self.fsr4_copy_button.setProperty("iconAction", True)
        self.fsr4_copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fsr4_copy_button.setToolTip(tr("Copy Steam launch option"))
        self.fsr4_copy_button.setAccessibleName(tr("Copy Steam launch option"))
        self.fsr4_copy_button.clicked.connect(self._copy_fsr4_launch_option)
        launch_row.addWidget(self.fsr4_copy_button)
        # Into every Steam game at once, while a game still lacks it.
        launch_row.addWidget(self.fsr4_steam_all_button)
        self.fsr4_section.set_header_control(
            self._version_control(self.fsr4_version_combo, self.fsr4_releases_button)
        )
        self.fsr4_upgrade_button = QPushButton("")
        self.fsr4_upgrade_button.clicked.connect(
            lambda: self._forward_dependency_action(
                {"action": f"fsr4_upgrade:{self.fsr4_upgrade_button.property('releaseTag') or ''}", "governor": ""}
            )
        )

        self.helixsr_section = _UpscalerSection(
            "HelixSR",
            "DLSS's neural network on this GPU, installed per game in place of FSR 3.1.",
            "helixsr",
        )
        self.helixsr_guide_button = self.helixsr_section.add_header_button(
            "Guide", lambda: self.helixsr_upstream_button.click()
        )
        self._as_guide_link(self.helixsr_guide_button)
        self.helixsr_guide_button.setToolTip(tr(
            "HelixSR's own guide on GitHub (lonewolf0622/HelixSR): its network files, each game, OptiScaler and every helixsr.ini setting."
        ))
        # The release Install or Update brings in: the recommended one unless
        # the user picks an older one or a pre-release.
        self.helixsr_version_combo = GuardedComboBox()
        self.helixsr_version_combo.setAccessibleName(tr("HelixSR version"))
        self.helixsr_version_combo.setToolTip(tr(
            "The HelixSR release Install or Update brings in. The recommended one is the release this version of Control Center was checked with."
        ))
        self.helixsr_version_combo.activated.connect(self._select_helixsr_release)
        self.helixsr_releases_button = self._releases_button(
            "Checks GitHub for newer HelixSR releases and pre-releases. Control Center also checks on its own twice a day.",
            "helixsr_releases",
        )
        self.helixsr_section.set_header_control(
            self._version_control(self.helixsr_version_combo, self.helixsr_releases_button)
        )
        self.helixsr_upgrade_button = QPushButton("")
        self.helixsr_upgrade_button.clicked.connect(
            lambda: self._forward_dependency_action(
                {"action": f"helixsr_upgrade:{self.helixsr_upgrade_button.property('releaseTag') or ''}", "governor": ""}
            )
        )
        # Every game against both upscalers, across the page.
        self.upscaling_games = _UpscalingGames()
        self.upscaling_games.action_requested.connect(self._forward_dependency_action)
        self.upscaling_games.body.insertWidget(0, self.fsr4_launch_panel)
        # Every game with another HelixSR release than the installed one.
        self.helixsr_update_all_button = self.upscaling_games.add_header_button(
            "Update all games",
            lambda: self._forward_dependency_action({"action": "helixsr_update_all", "governor": ""}),
        )
        self.helixsr_update_all_button.setToolTip(tr(
            "Gives every game the installed HelixSR release. A game that is open is skipped."
        ))
        # Games Steam does not know: the user points at the game's folder.
        self.helixsr_folder_button = QPushButton(tr("Add game folder"))
        self.helixsr_folder_button.clicked.connect(
            lambda: self._forward_dependency_action(
                {"action": "helixsr_add_folder", "governor": ""}
            ),
        )
        self.helixsr_folder_button.setToolTip(
            tr("For games outside Steam, choose the game's folder.")
        )
        # OptiScaler put in a game by hand, not by OptiScaler Client.
        self.helixsr_opti_folder_button = QPushButton(tr("Add OptiScaler game"))
        self.helixsr_opti_folder_button.clicked.connect(
            lambda: self._forward_dependency_action(
                {"action": "helixsr_add_opti_folder", "governor": ""}
            ),
        )
        self.helixsr_opti_folder_button.setToolTip(
            tr("For a game where you installed OptiScaler yourself: choose the game's folder and HelixSR can upscale through it.")
        )
        # Both ways to add a game, behind one button.
        self.upscaling_add_button = self.upscaling_games.add_header_button(
            "Add game", self._open_add_game_menu,
        )
        self.upscaling_add_button.setProperty("menuAction", True)
        self.upscaling_add_button.setIcon(icon("chevron_down_gray"))
        self.upscaling_add_button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._add_game_holder = QWidget(self.upscaling_games)
        self._add_game_holder.hide()
        for button in (self.helixsr_folder_button, self.helixsr_opti_folder_button):
            button.setParent(self._add_game_holder)
        self.upscaling_games._layout_header(force=True)
        for button in (
            self.fsr4_install_button, self.fsr4_launch_button, self.fsr4_remove_button,
            self.fsr4_steam_all_button,
            self.fsr4_legacy_button, self.helixsr_install_button, self.helixsr_network_button,
            self.helixsr_scan_button, self.helixsr_remove_button,
            self.fsr4_upgrade_button, self.helixsr_upgrade_button,
        ):
            self._adopt(button, "compactAction")

        self.upscaling_row = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.upscaling_row.setSpacing(14)
        self.upscaling_row.addWidget(self.fsr4_section, 1)
        self.upscaling_row.addWidget(self.helixsr_section, 1)
        layout.addLayout(self.upscaling_row)
        layout.addSpacing(14)
        layout.addWidget(self.upscaling_games)
        layout.addSpacing(14)
        # helixsr.ini, once for every game.
        self.helixsr_settings = _HelixSRSettings()
        self.helixsr_settings.save_requested.connect(
            lambda values: self._forward_dependency_action(
                {"action": "helixsr_settings", "helixsr_settings": values, "governor": ""}
            )
        )
        if hasattr(self, "_helixsr_settings_state"):
            self.helixsr_settings.set_int8_supported(getattr(self, "_helixsr_int8", True))
            self.helixsr_settings.set_fast_output_supported(getattr(self, "_helixsr_fast_output", True))
            self.helixsr_settings.set_release_settings(
                *getattr(self, "_helixsr_release_settings", ([], [])),
                scaler_games=getattr(self, "_helixsr_scaler_count", 0),
            )
            self.helixsr_settings.set_settings(*self._helixsr_settings_state)
            self.helixsr_settings.set_game_count(getattr(self, "_helixsr_game_count", 0))
        layout.addWidget(self.helixsr_settings)
        layout.addStretch(1)
        self._render_upscaling()
        return page

    @staticmethod
    def _as_guide_link(button: QPushButton) -> None:
        """The guide opens a web page: a quiet link with the external mark."""
        button.setProperty("compactAction", False)
        button.setProperty("guideLink", True)
        button.setIcon(icon("external_gray"))
        button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        button.style().unpolish(button)
        button.style().polish(button)

    def _releases_button(self, tooltip: str, action: str) -> QPushButton:
        """A small square button beside a version picker: read GitHub's list now."""
        button = QPushButton("")
        button.setIcon(icon("refresh_gray"))
        button.setProperty("compactAction", True)
        button.setProperty("iconAction", True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolTip(tr(tooltip))
        button.setAccessibleName(tr("Check for new releases"))
        button.clicked.connect(lambda: self._forward_dependency_action({"action": action, "governor": ""}))
        return button

    @staticmethod
    def _version_control(combo, button) -> QWidget:
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        combo.setSizeAdjustPolicy(GuardedComboBox.SizeAdjustPolicy.AdjustToContents)
        combo.setMinimumWidth(150)
        row.addWidget(combo)
        row.addWidget(button)
        return host

    def _open_add_game_menu(self) -> None:
        """Add game: a folder outside Steam, or a game with OptiScaler put in by hand."""
        menu = QMenu(self.upscaling_add_button)
        menu.setProperty("upscalingMenu", True)
        for button in (self.helixsr_folder_button, self.helixsr_opti_folder_button):
            if button.isHidden():
                continue
            action = menu.addAction(button.text())
            action.setToolTip(button.toolTip())
            action.triggered.connect(lambda _checked=False, source=button: source.click())
        if not menu.isEmpty():
            self._add_game_menu = menu
            menu.popup(self.upscaling_add_button.mapToGlobal(self.upscaling_add_button.rect().bottomLeft()))

    def _decky_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(8)
        self.decky_card = PreparationInfoCard(
            "Game Mode Quick Access (Beta)",
            "Decky is optional. It is never installed by generic dependency preparation.",
            action_text="Install Decky + Quick Access (Beta)",
            payload={"action": "quick_access_install_decky", "governor": ""},
        )
        self.decky_preview_button = self.decky_card.add_action(
            "Preview", {"action": "decky_preview", "governor": ""}
        )
        self.decky_card.action_requested.connect(self._handle_decky_action)
        layout.addWidget(self.decky_card)
        layout.addStretch(1)
        return page

    def _drivers_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)
        self.network_driver_card = PreparationInfoCard(
            "Wi-Fi and Bluetooth support",
            # Keep this source aligned with the complete driver catalog so the
            # Wi-Fi and Bluetooth preparation copy is available in every locale.
            "Active kernel drivers and official firmware packages.",
            action_text="Install support",
        )
        self.network_driver_card.action_requested.connect(
            lambda _payload: self.driver_support_requested.emit("connectivity")
        )
        self.printing_driver_card = PreparationInfoCard(
            "Printing support",
            "Driverless printing with CUPS, IPP and IPP-over-USB. Existing queues are preserved.",
            action_text="Install support",
        )
        self.printing_driver_card.action_requested.connect(
            lambda _payload: self.driver_support_requested.emit("printing")
        )
        layout.addWidget(self.network_driver_card)
        layout.addWidget(self.printing_driver_card)
        self._build_accessory_cards(layout)
        layout.addWidget(
            PreparationInfoCard(
                "External drivers",
                "Device-specific kernel modules are not generic driver packs.",
            )
        )
        layout.addStretch(1)
        return page

    def _build_accessory_cards(self, layout: QVBoxLayout) -> None:
        """Hardware a BC-250 case may carry beside the board.

        Neither card touches the board itself: one drives a cooler's LCD, the
        other a Corsair hub. Both install a pinned release and keep running
        through a user service, so they work in Desktop and Game Mode alike.
        """
        self.thermalright_card = PreparationInfoCard(
            "Thermalright cooler display",
            "TRCC Linux drives the LCD on Thermalright coolers. After you save a theme once, "
            "it plays in Desktop and Game Mode without any window open.",
            scope_text="Case accessory",
            status_text="Checking",
        )
        self.corsair_card = PreparationInfoCard(
            "Corsair fans and RGB",
            "OpenLinkHub replaces iCUE on Linux for Corsair hubs, AIOs, fans and lighting, "
            "with its own control panel. The NexGen3D Steam Machine PRO case uses it for its Commander Duo.",
            scope_text="Case accessory",
            status_text="Checking",
        )
        # The receiver and the TV: neither needs a program window, both are
        # settings of the sound server and of a daemon SteamOS already runs.
        self.hdmi_ac3_card = PreparationInfoCard(
            "HDMI audio · Dolby Digital 5.1",
            "Encodes 5.1 sound to AC-3 in real time for receivers and soundbars that only take "
            "Dolby Digital over HDMI, with PipeWire's own AC-3 profile and ALSA's a52 encoder.",
            scope_text="Audio and TV",
            status_text="Checking",
        )
        self.hdmi_cec_card = PreparationInfoCard(
            "TV control · HDMI-CEC",
            "Valve's cecd, the CEC daemon SteamOS uses: the TV turns on when the BC-250 wakes and "
            "sleeps when it suspends, and its remote works as input. Needs a DisplayPort-to-HDMI "
            "adapter that passes CEC.",
            scope_text="Audio and TV",
            status_text="Checking",
        )
        self.accessory_buttons: dict[str, dict[str, QPushButton]] = {}
        # One line under the description for what the current state asks of
        # the owner (restart, log out, plug the device in). Empty most of the time.
        self._accessory_notes: dict[str, QLabel] = {}
        self._accessory_cards = {
            "thermalright": self.thermalright_card,
            "corsair": self.corsair_card,
            "hdmi_ac3": self.hdmi_ac3_card,
            "hdmi_cec": self.hdmi_cec_card,
        }
        for key, card, configure_text in (
            ("thermalright", self.thermalright_card, "Open configuration"),
            ("corsair", self.corsair_card, "Open control panel"),
            ("hdmi_ac3", self.hdmi_ac3_card, "Open configuration"),
            ("hdmi_cec", self.hdmi_cec_card, "Open TV control"),
        ):
            buttons = {
                "install": card.add_action("Install", {"accessory": key, "op": "install"}),
                "configure": card.add_action(configure_text, {"accessory": key, "op": "configure"}),
                "remove": card.add_action("Remove", {"accessory": key, "op": "remove"}, danger=True),
                "upstream": card.add_action("Open upstream project", {"accessory": key, "op": "upstream"}),
            }
            self.accessory_buttons[key] = buttons
            note = _label("", "dashboardComponentDetail")
            note.setProperty("accessoryNote", True)
            note.hide()
            card.layout().insertWidget(2, note)
            self._accessory_notes[key] = note
            card.action_requested.connect(self._forward_accessory_action)
            layout.addWidget(card)
