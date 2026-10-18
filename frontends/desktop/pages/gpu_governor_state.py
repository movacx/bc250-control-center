"""Building, refreshing and laying out the GPU page."""

from __future__ import annotations

import re
import time
from dataclasses import replace

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bc250cc.application.gpu.diagnostics import (
    present_gpu_diagnostics,
)
from bc250cc.application.gpu.runtime import present_gpu_runtime
from bc250cc.application.gpu.safe_points import SafePointRow
from bc250cc.application.gpu.safety import present_gpu_safety
from bc250cc.application.gpu.voltage_lab_state import (
    build_voltage_lab_state,
)
from bc250cc.application.gpu.voltage_table import build_voltage_table_plan
from bc250cc.application.preparation.gpu_dependency_plan import (
    DEFAULT_PREPARATION_COMPONENTS,
    build_gpu_dependency_plan,
)
from bc250cc.domain.gpu.oberon import OBERON_SAFE_PROFILES
from bc250cc.domain.gpu.profiles import (
    profiles_for_allowed_range,
)
from bc250cc.infrastructure.gpu.governor_toml import (
    VOLTAGE_BOOST_START_MHZ,
)

from ..components.buttons import WrappingButton as QPushButton
from ..components.page_widgets import (
    MetricTile,
    PresetButton,
    SectionCard,
    StatusLine,
)
from ..components.responsive import (
    effective_viewport_width,
)
from ..components.wheel_guard import GuardedComboBox
from ..components.widgets import icon
from ..core.action_session import ActionSession
from ..core.feature_visibility import (
    GPU_REFERENCE_PANELS_ENABLED,
)
from ..i18n import tr, tr_format
from ..theme import COLORS
from .gpu_governor_helpers import _dict, _integer, _number
from .gpu_governor_widgets import (  # noqa: F401  (re-exported: other modules and tests import them from here)
    DependencyPreparationDialog,
    DynamicSafetyNotice,
    FrequencyField,
    GpuProfileEditDialog,
    GpuSummaryItem,
    GpuSummaryStrip,
    RuntimeStat,
)


def _page_class():
    """``GpuGovernorPage``, looked up late: the page module imports this one."""
    from .gpu_governor import GpuGovernorPage

    return GpuGovernorPage


class GpuGovernorStateMixin:
    """Methods of ``GpuGovernorPage`` split out of ``gpu_governor``."""

    def _build_configuration_card(self) -> SectionCard:
        card = SectionCard(
            "GPU configuration",
            "Select a validated profile or stage an explicit D-Bus range. Every hardware change is reviewed before execution.",
            icon_name="settings_blue",
            icon_background=COLORS["blue_soft"],
            status=None,
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
        self.cyan_set_method = GuardedComboBox()
        self.cyan_set_method.addItem(tr("Governor method: SMU"), "smu")
        self.cyan_set_method.addItem(tr("Governor method: Kernel"), "kernel")
        self.cyan_usage_method = GuardedComboBox()
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

        # Quick access to the same validated safe-point list the advanced
        # TOML laboratory uses, without leaving the main configuration card.
        # Selecting a point here and in the advanced panel stays in sync
        # (see _sync_paired_safe_point_combo), and "Apply selected range"
        # reuses the exact same validated apply path.
        self.quick_range_panel = QFrame()
        self.quick_range_panel.setProperty("compactPanel", True)
        quick_range_layout = QVBoxLayout(self.quick_range_panel)
        quick_range_layout.setContentsMargins(12, 10, 12, 10)
        quick_range_layout.setSpacing(8)
        quick_range_title = QLabel(tr("Validated frequency points"))
        quick_range_title.setProperty("fieldLabel", True)
        quick_range_title.setWordWrap(True)
        quick_range_hint = QLabel(
            tr("Pick an already-tested frequency and voltage point. No manual typing needed.")
        )
        quick_range_hint.setProperty("fieldHint", True)
        quick_range_hint.setWordWrap(True)
        quick_range_layout.addWidget(quick_range_title)
        quick_range_layout.addWidget(quick_range_hint)
        self.quick_safe_point_combo = GuardedComboBox()
        self.quick_safe_point_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.quick_safe_point_combo.currentIndexChanged.connect(
            self._quick_safe_point_changed
        )
        quick_range_layout.addWidget(self.quick_safe_point_combo)
        quick_range_actions = QGridLayout()
        quick_range_actions.setHorizontalSpacing(8)
        quick_range_actions.setVerticalSpacing(8)
        quick_range_actions.setColumnStretch(0, 1)
        quick_range_actions.setColumnStretch(1, 1)
        self.quick_apply_button = QPushButton(tr("Apply active range · select a ceiling"))
        self.quick_apply_button.setObjectName("PrimaryAction")
        self.quick_apply_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.quick_apply_button.setProperty("gamepadEntry", True)
        self.quick_apply_button.setEnabled(False)
        self.quick_apply_button.clicked.connect(self._request_selected_safe_point_range)
        self.quick_save_button = QPushButton(tr("Save active range for startup"))
        self.quick_save_button.setProperty("compactAction", True)
        self.quick_save_button.clicked.connect(self._use_active_range)
        quick_range_actions.addWidget(self.quick_apply_button, 0, 0)
        quick_range_actions.addWidget(self.quick_save_button, 0, 1)
        quick_range_layout.addLayout(quick_range_actions)
        card.body.addWidget(self.quick_range_panel)

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
        self.preset_tiles: list[QFrame] = []
        self.preset_edit_buttons: list[QPushButton] = []
        for slot_index, (title, summary, payload) in enumerate(self.PROFILE_VALUES):
            button = PresetButton(title, summary, payload)
            button.setProperty("gpuFrequencyPreset", True)
            button.setMinimumHeight(56)
            button.clicked.connect(
                lambda checked, b=button: self._select_preset(b) if checked else None
            )
            self.preset_group.addButton(button)
            self.preset_buttons.append(button)

            tile = QFrame()
            tile_layout = QHBoxLayout(tile)
            tile_layout.setContentsMargins(0, 0, 0, 0)
            tile_layout.setSpacing(4)
            tile_layout.addWidget(button, 1)
            edit_button = QPushButton()
            edit_button.setIcon(icon("edit_gray"))
            edit_button.setFixedSize(28, 28)
            edit_button.setProperty("compactAction", True)
            edit_button.setToolTip(tr("Rename this profile and change its range"))
            edit_button.clicked.connect(
                lambda _checked=False, i=slot_index: self._edit_profile(i)
            )
            tile_layout.addWidget(edit_button, 0, Qt.AlignmentFlag.AlignTop)
            self.preset_edit_buttons.append(edit_button)
            self.preset_tiles.append(tile)
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
        self.use_active_button = QPushButton(tr("Save active range for startup"))
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

        self.oc_frequency = GuardedComboBox()
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
        # Cyan exposes a validated D-Bus range API that Oberon does not, so
        # these two live in the same tile slots the core clock and VRAM
        # tiles use for Oberon, instead of adding a 7th/8th slot -- they
        # carry the same information the runtime status row below used to
        # show as small text pills (see runtime_stats_panel), just promoted
        # into the main telemetry grid where it is easier to notice.
        self.dbus_metric = MetricTile(
            "D-Bus API",
            "--",
            "",
            icon_name="app_blue",
            icon_background=COLORS["blue_soft"],
            compact=True,
        )
        self.active_range_metric = MetricTile(
            "Active range",
            "--",
            "",
            icon_name="compute_blue",
            icon_background=COLORS["blue_soft"],
            compact=True,
        )
        self.metric_tiles_oberon = [
            self.sclk_metric,
            self.voltage_metric,
            self.temperature_metric,
            self.utilization_metric,
            self.mclk_metric,
            self.vram_metric,
        ]
        self.metric_tiles_cyan = [
            self.dbus_metric,
            self.voltage_metric,
            self.temperature_metric,
            self.utilization_metric,
            self.mclk_metric,
            self.active_range_metric,
        ]
        # Oberon is the historical default here; _set_backend_profile_mode
        # corrects this to whichever backend is actually detected as soon as
        # the first refresh completes.
        self.metric_tiles = self.metric_tiles_oberon
        self.dbus_metric.hide()
        self.active_range_metric.hide()
        for tile in (*self.metric_tiles_oberon, *self.metric_tiles_cyan):
            tile.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            tile.setMinimumHeight(58)
        self._reflow_metric_tiles(1400)
        card.body.addLayout(self.metrics_grid)
        self.memory_clocks_line = QLabel()
        self.memory_clocks_line.setWordWrap(True)
        self.memory_clocks_line.setProperty("fieldHint", True)
        card.body.addWidget(self.memory_clocks_line)

        note = QLabel(tr("Passive readings · hardware changes require confirmation."))
        note.setProperty("fieldHint", True)
        note.setWordWrap(True)
        card.body.addWidget(note)
        return card

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

        self.enable_button = QPushButton(tr("Start governor"))
        self.enable_button.setProperty("compactAction", True)
        self.enable_button.setIcon(icon("rocket_blue"))
        self.enable_button.clicked.connect(lambda: self._service_action("activar"))

        self.disable_button = QPushButton(tr("Stop governor"))
        self.disable_button.setProperty("dangerAction", True)
        self.disable_button.clicked.connect(lambda: self._service_action("desactivar"))

        self.restart_button = QPushButton(tr("Restart service"))
        self.restart_button.setProperty("compactAction", True)
        self.restart_button.setIcon(icon("refresh_gray"))
        self.restart_button.clicked.connect(lambda: self._service_action("reiniciar"))

        self.status_button = QPushButton(tr("View service status"))
        self.status_button.setProperty("compactAction", True)
        self.status_button.clicked.connect(self.read_service_status)

        self.voltage_lab_button = QPushButton(tr("Open voltage laboratory"))
        self.voltage_lab_button.setProperty("compactAction", True)
        self.voltage_lab_button.setProperty("voltageLabLauncher", True)
        self.voltage_lab_button.setIcon(icon("bolt_blue"))
        self.voltage_lab_button.setToolTip(
            tr("Open the compact voltage curve laboratory without leaving GPU control.")
        )
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
        card.add_header_button("Copy diagnostics", self._copy_apu_diagnostics)

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

        self.safe_points_panel.setVisible(GPU_REFERENCE_PANELS_ENABLED)
        self.diagnostics_panel.setVisible(GPU_REFERENCE_PANELS_ENABLED)

        self.console_panel = QFrame()
        self.console_panel.setProperty("compactPanel", True)
        self.console_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        console_layout = QVBoxLayout(self.console_panel)
        console_layout.setContentsMargins(12, 12, 12, 12)
        console_layout.setSpacing(8)
        console_header = QLabel(tr("Governor console"))
        console_header.setProperty("fieldLabel", True)
        console_layout.addWidget(console_header)
        self.console = QPlainTextEdit()
        self.console.setObjectName("OperationConsole")
        self.console.setReadOnly(True)
        self.console.setMinimumHeight(330)
        self.console.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.console.setPlainText(
            tr("GPU Governor console ready. No hardware command has been executed.")
        )
        console_layout.addWidget(self.console)

        self._reflow_advanced(1400)
        card.body.addLayout(self.advanced_grid)
        self.advanced_status = card.status
        return card

    def _reflow_presets(self, width: int) -> None:
        if self._profile_backend == "oberon":
            columns = 3 if width >= 620 else 2 if width >= 420 else 1
        else:
            columns = 3 if width >= 620 else 1
        if columns == self._preset_columns and self.preset_grid.count():
            return
        self._preset_columns = columns
        self._clear_grid(self.preset_grid)
        visible_tiles = [
            tile
            for tile, button in zip(self.preset_tiles, self.preset_buttons, strict=True)
            if not button.isHidden()
        ]
        for index, tile in enumerate(visible_tiles):
            self.preset_grid.addWidget(tile, index // columns, index % columns)
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
            next_row = 1
            if GPU_REFERENCE_PANELS_ENABLED:
                self.advanced_grid.addWidget(self.safe_points_panel, next_row, 0)
                self.advanced_grid.addWidget(self.diagnostics_panel, next_row, 1)
                next_row += 1
            self.advanced_grid.addWidget(self.console_panel, next_row, 0, 1, 2)
            self.advanced_grid.setRowStretch(next_row, 1)
            self.advanced_grid.setColumnStretch(0, 7)
            self.advanced_grid.setColumnStretch(1, 5)
        else:
            self.advanced_grid.addWidget(self.fixed_safe_point_panel, 0, 0)
            next_row = 1
            if GPU_REFERENCE_PANELS_ENABLED:
                self.advanced_grid.addWidget(self.safe_points_panel, next_row, 0)
                self.advanced_grid.addWidget(self.diagnostics_panel, next_row + 1, 0)
                next_row += 2
            self.advanced_grid.addWidget(self.console_panel, next_row, 0)
            self.advanced_grid.setRowStretch(next_row, 1)
            self.advanced_grid.setColumnStretch(0, 1)

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
                self.preset_tiles[index].show()
                self.preset_edit_buttons[index].setVisible(not is_oberon)
            else:
                button.hide()
                self.preset_tiles[index].hide()
        self._apply_profile_overrides()
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
        # The quick frequency picker and its buttons duplicate part of the
        # advanced TOML laboratory; Oberon does not use TOML safe-points at
        # all, so this panel (and the now-empty runtime status row it frees
        # up space from) only makes sense for Cyan. Oberon keeps its original
        # five-pill runtime status row exactly as before.
        self.quick_range_panel.setVisible(not is_oberon)
        self.runtime_stats_panel.setVisible(is_oberon)
        self.metric_tiles = (
            self.metric_tiles_oberon if is_oberon else self.metric_tiles_cyan
        )
        for tile in self.metric_tiles_oberon:
            tile.setVisible(is_oberon)
        for tile in self.metric_tiles_cyan:
            tile.setVisible(not is_oberon)
        self._metric_columns = 0
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
            self._show_operation_in_progress()
            return False
        self._action_busy = True
        self._set_operation_busy(True)
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
                    self.voltage_lab_drawer.raise_()
                    if keep_voltage_lab
                    and getattr(self, "voltage_lab_drawer", None) is not None
                    and self.voltage_lab_drawer.is_open()
                    else None
                )
            ),
        )

        def finished() -> None:
            session.finished()
            if not self._action_gate.busy:
                self._action_busy = False
                self._set_operation_busy(False)

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
            self._set_operation_busy(False)
            if start_error is None:
                self._show_operation_in_progress()
        return started

    def _set_operation_busy(self, active: bool) -> None:
        """Show the small progress ring only while an operation is pending."""
        text = "GPU operation in progress"
        self.configuration_card.set_busy(active, text)
        view = getattr(self, "_redesigned_gpu_view", None)
        if view is not None:
            view.set_operation_busy(active, text)
        self.operation_busy_changed.emit(bool(active))

    def _apply_high_points_toggle_feedback(self, enabled: bool) -> None:
        """Reflect a confirmed TOML edit immediately while the full refresh runs."""

        state = dict(_dict(self.current_state.get("high_frequency_points")))
        # Under a kernel clock limit only the points within it are enabled.
        frequencies = tuple(
            state.get("allowed_frequencies") or state.get("frequencies") or ()
        )
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

    def execute_dependency_action(
        self,
        *,
        action: str,
        preference: str,
        selected_components: set[str],
        dialog_parent: QWidget | None = None,
        memory_policy: str = "current",
        memory_ttm_gib: int = 0,
        memory_takeover_zram: bool = False,
        memory_target_mount: str = "",
        vram_uma_size_mb: int = 0,
        kernel_options: tuple[str, ...] = (),
        kernel_option_changed: str = "",
        helixsr_settings: dict | None = None,
        smt_mode: str = "",
    ) -> None:
        """Execute a dialog or dashboard preparation request through one route."""
        tools = _dict(self.current_state.get("tools"))
        if action == "helixsr_settings":
            self._save_helixsr_settings(dict(helixsr_settings or {}), dialog_parent=dialog_parent)
            return
        if action in {"acpi-install", "acpi-update", "acpi-uninstall", "acpi-status"}:
            self._manage_acpi(action, dialog_parent)
            return
        if action in {"memory_swap", "memory_ttm"}:
            self._prepare_bazzite_memory_tuning(
                policy=memory_policy,
                ttm_gib=memory_ttm_gib,
                scope="swap" if action == "memory_swap" else "ttm",
                takeover_zram=memory_takeover_zram,
                target_mount=memory_target_mount,
                dialog_parent=dialog_parent,
            )
            return
        if action == "vram_apply":
            self._prepare_vram(uma_size_mb=vram_uma_size_mb, dialog_parent=dialog_parent)
            return
        if action.startswith("bazzite_mitigations_"):
            self._prepare_bazzite_mitigations(
                action.removeprefix("bazzite_mitigations_"),
                dialog_parent=dialog_parent,
            )
            return
        if action == "smt_live":
            self._manage_smt_live(smt_mode, dialog_parent=dialog_parent)
            return
        if action == "kernel_options_set":
            self._manage_kernel_options(
                kernel_options, changed=kernel_option_changed, dialog_parent=dialog_parent
            )
            return
        if action.startswith("steamos_readonly_"):
            self._manage_steamos_readonly(
                action.removeprefix("steamos_readonly_"),
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
        if action == "fsr4_steam_option_all":
            self._add_fsr4_steam_option_to_library(dialog_parent=dialog_parent)
            return
        if action.startswith("fsr4_steam_option:"):
            self._add_fsr4_steam_option(
                action.partition(":")[2], dialog_parent=dialog_parent
            )
            return
        if action in {
            "fsr4_install", "fsr4_uninstall", "fsr4_legacy_uninstall", "fsr4_launch",
            "fsr4_releases",
        } or action.startswith("fsr4_select:"):
            self._manage_fsr4_bc250(
                action.removeprefix("fsr4_"), dialog_parent=dialog_parent
            )
            return
        if action == "fsr4_upstream":
            self._open_fsr4_upstream(dialog_parent=dialog_parent)
            return
        if action.startswith("helixsr_") and action != "helixsr_upstream":
            self._manage_helixsr(
                action.removeprefix("helixsr_"), dialog_parent=dialog_parent
            )
            return
        if action in {
            "acpi_upstream",
            "helixsr_upstream",
            "vaapi_upstream",
            "gfx1013_upstream",
            "bazzite_async_upstream",
            "bazzite_image_upstream",
        }:
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
        if action.startswith("gfx1013_source_"):
            self._manage_gfx1013_source(
                action.removeprefix("gfx1013_source_"), dialog_parent=dialog_parent
            )
            return
        if action == "debian_kernel_install":
            self._manage_debian_kernel(dialog_parent=dialog_parent)
            return
        if action == "mesa_ppa_install":
            self._manage_mesa_ppa(dialog_parent=dialog_parent)
            return
        if action.startswith("vaapi_"):
            self._manage_vaapi(action.removeprefix("vaapi_"), dialog_parent=dialog_parent)
            return
        if action.startswith("radv_async_"):
            self._manage_radv_async(
                action.removeprefix("radv_async_"), dialog_parent=dialog_parent
            )
            return
        if action in {
            "gfx1013_fedora_install",
            "gfx1013_fedora_uninstall",
            "gfx1013_fedora_boot_patched",
            "gfx1013_fedora_activate",
        }:
            self._manage_gfx1013_fedora(
                action.removeprefix("gfx1013_fedora_").replace("_", "-"),
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
            "compatibility": _page_class()._prepare_steamos_compatibility,
            "diagnostics": _page_class()._prepare_steamos_diagnostics,
            "remove": _page_class()._prepare_governor_removal,
            "shared": _page_class()._prepare_governor_installation,
            "governor": _page_class()._prepare_governor_installation,
        }[plan.route]
        route(self, plan, dialog_parent)

    def _run_service_plan(self, plan, *, reset_cyan_fix_flags: bool = False) -> None:
        def success(_result: object) -> None:
            self._last_operation_summary = f"Opened service workflow: {plan.label}."
            self.last_operation_line.set_values(
                "Service action", self._last_operation_summary
            )
            self._append_console(self._last_operation_summary)

        self._run_backend_action(
            lambda: self.controller.controlar_governor(
                plan.action,
                plan.has_conflicts,
                plan.has_conflicts,
                reset_cyan_fix_flags=reset_cyan_fix_flags,
            ),
            success,
            "Governor service action failed",
        )

    def _sync_voltage_lab(self, gpu: dict) -> None:
        # The guard used to ask whether the page's curve grid had been built.
        # The drawer is the surface now, and an in-progress keypad edit still
        # owns the values: refreshing over it would discard what is being typed.
        if getattr(self, "voltage_lab_drawer", None) is None:
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
        self._voltage_applied_level = state.applied_level

        # The custom editor starts from the curve on disk and follows it: a
        # value set once used to stay forever, so after another level was
        # applied, Custom offered the old curve and applying it undid the
        # level without saying so. Only points typed and not applied keep
        # what was typed.
        edited = {
            frequency: voltage
            for frequency, voltage in self._voltage_custom_values.items()
            if frequency in self._voltage_custom_edited
        }
        self._voltage_custom_values = {
            frequency: edited.get(frequency, voltage)
            for frequency, voltage in state.custom_defaults
        }
        self._voltage_custom_edited &= set(self._voltage_custom_values)
        self._voltage_lab_initialized = True

        # The drawer is the only voltage surface. The page this method used to
        # feed as well was never reachable: ``open_voltage_lab`` returns the
        # stack to the overview and opens the drawer instead.
        self._sync_voltage_drawer()

    def _sync_voltage_drawer(self) -> None:
        drawer = getattr(self, "voltage_lab_drawer", None)
        if drawer is None or not hasattr(self, "_voltage_points"):
            return
        selected_level = int(drawer.selected_level())
        plan = build_voltage_table_plan(
            points=list(self._voltage_points),
            selected_level=selected_level,
            editable_frequencies=self._voltage_editable_frequencies,
            profile_frequencies=self._voltage_profile_frequencies,
            custom_values=self._voltage_custom_values,
            packaged_voltages=self.VOLTAGE_LAB_BASE,
            detected_level=self._voltage_detected_level,
            is_oberon=bool(getattr(self, "_is_oberon_backend", False)),
        )
        is_oberon = bool(getattr(self, "_is_oberon_backend", False))
        drawer.set_oberon_mode(is_oberon)
        rows = plan.rows
        if is_oberon:
            rows = tuple(
                replace(
                    row,
                    original=None,
                    proposed=row.current or None,
                    added=None,
                    custom_available=False,
                    editor_value=row.current,
                )
                for row in plan.rows
            )
            detail = tr(
                "Oberon uses two YAML endpoints. They are shown below for reference; "
                "curve editing is unavailable for this governor."
            )
        elif plan.custom_mode:
            detail = tr(
                "Adjust the safe points currently active in the governor configuration."
            )
        else:
            detail = tr_format(
                "+{added} mV is added only to the high-frequency curve from "
                "{start} MHz. Lower-frequency values return to governor defaults.",
                added=selected_level * 10,
                start=VOLTAGE_BOOST_START_MHZ,
            )
        drawer.set_curve(
            rows,
            custom_mode=plan.custom_mode and not is_oberon,
            detail=detail,
            apply_enabled=bool(plan.active_frequencies) and not is_oberon,
            read_only=is_oberon,
        )

    def set_updates_active(self, active: bool) -> None:
        self._updates_active = bool(active)
        if self._updates_active:
            if not self.timer.isActive():
                self.timer.start()
            self._refresher.activate(fresh_for=1.5)
        else:
            self._refresher.set_active(False)
            self.timer.stop()

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
            str(telemetry["voltage_text"]), tr("AMDGPU hwmon sensor")
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
        diagnostic = _dict(self.current_state.get("apu_telemetry"))
        readings = _dict(diagnostic.get("metrics"))
        sampled_at = _number(diagnostic.get("sampled_at_monotonic"), 0)
        age = time.monotonic() - sampled_at
        stale = bool(diagnostic) and (sampled_at <= 0 or age < 0 or age > 6)
        clock_parts = []
        for name in ("mclk", "fclk", "uclk"):
            item = _dict(readings.get(name))
            value = item.get("value") if item.get("status") == "valid" and not stale else None
            clock_parts.append(
                f"{name.upper()}: {value} MHz" if value is not None
                else f"{name.upper()}: {tr('Not available')}"
            )
        self.memory_clocks_line.setText(" · ".join(clock_parts))
        self.memory_clocks_line.setToolTip(tr("Independent memory clocks require a verified source."))
        for name, widget in (
            ("sclk", self.sclk_metric), ("voltage", self.voltage_metric),
            ("temperature", self.temperature_metric), ("mclk", self.mclk_metric),
        ):
            item = _dict(readings.get(name))
            if stale or item.get("status") == "invalid":
                widget.set_values(tr("Stale" if stale else "Invalid"), tr("Advanced GPU diagnostics"))
            widget.setToolTip(str(item.get("source") or ""))
        if self.metrics_status is not None:
            degraded = stale or diagnostic.get("status") in {"invalid", "unavailable"}
            self.metrics_status.setText(tr("Warning" if degraded else "Live"))
            self.metrics_status.set_tone("orange" if degraded else "green")
            self.metrics_status.setToolTip(tr("Advanced GPU diagnostics") if diagnostic.get("layout_mismatch_suspected") else "")

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
        # Cyan shows this same D-Bus/active-range information promoted into
        # the main telemetry grid instead of the pill row above (see
        # metric_tiles_cyan); keep both tiles fed regardless of backend since
        # they simply stay hidden and unused for Oberon.
        self.dbus_metric.set_values(
            self._render_runtime_text(presentation.lines[2].value),
            self._render_runtime_text(presentation.lines[2].detail),
        )
        self.active_range_metric.set_values(
            self._render_runtime_text(presentation.lines[3].value),
            self._render_runtime_text(presentation.lines[3].detail),
        )
        if self.runtime_card.status is not None:
            self.runtime_card.status.setText(
                self._render_runtime_text(presentation.card_status)
            )
            self.runtime_card.status.set_tone(presentation.card_tone)

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
        self.use_active_button.setText(tr("Save active range for startup"))
        self.use_active_button.setToolTip(
            tr(
                "Write the live Cyan range to [frequency-range] for the next startup."
            )
        )
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
        combos = [self.oc_frequency]
        if hasattr(self, "quick_safe_point_combo"):
            combos.append(self.quick_safe_point_combo)
        for combo in combos:
            previous = _integer(combo.currentData(), 0)
            combo.blockSignals(True)
            combo.clear()
            for frequency, voltage in cleaned:
                combo.addItem(
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
                index = combo.findData(desired)
                if index >= 0:
                    combo.setCurrentIndex(index)
            combo.blockSignals(False)
        self._safe_point_combo_signature = signature

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
        self._sync_quick_safe_point_selection(frequency, can_apply)
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

    def _sync_quick_safe_point_selection(self, frequency: int, can_apply: bool) -> None:
        """Mirror the advanced safe-point pick into the quick range panel."""
        if not hasattr(self, "quick_safe_point_combo"):
            return
        index = self.quick_safe_point_combo.findData(frequency) if frequency > 0 else -1
        if index >= 0 and self.quick_safe_point_combo.currentIndex() != index:
            self.quick_safe_point_combo.blockSignals(True)
            self.quick_safe_point_combo.setCurrentIndex(index)
            self.quick_safe_point_combo.blockSignals(False)
        self.quick_apply_button.setText(self.apply_selected_range_button.text())
        self.quick_apply_button.setEnabled(can_apply)

    def _apply_profile_overrides(self) -> None:
        """Re-apply saved custom names/ranges on top of the default specs.

        _set_backend_profile_mode always resets the three preset buttons to
        their default title/range first (Cyan defaults or Oberon's fixed
        pair), so this runs right after it to restore whatever the user
        renamed/edited, without touching Oberon (which is never editable).
        """
        if self._profile_backend == "oberon":
            return
        for index, button in enumerate(self.preset_buttons):
            override = self._custom_profile_overrides.get(index)
            if override is None:
                continue
            button.payload = (override["min"], override["max"])
            reference = (
                f"{override['frequency']} MHz · {override['voltage']} mV\n"
                if override.get("frequency")
                else ""
            )
            button.setText(
                f"{tr(override['name'])}\n{reference}{override['min']}–{override['max']} MHz"
            )

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
            override = None if is_oberon else self._custom_profile_overrides.get(index)
            if is_oberon:
                preset_minimum, preset_maximum = button.payload
                available = tuple(button.payload) in OBERON_SAFE_PROFILES
            elif override is not None:
                # A renamed/edited profile keeps the range the user picked in
                # the editor instead of the dynamically computed Balanced /
                # Gaming / Benchmark defaults below.
                preset_minimum, preset_maximum = button.payload
                available = not safe or preset_maximum in safe
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
        detail = _page_class()._render_safety_message(notice.message)
        for suffix in notice.suffixes:
            detail += " " + _page_class()._render_safety_message(suffix)
        self.safety_notice.set_notice(notice.title, detail, tone=notice.tone)
        if self.configuration_status is not None:
            self.configuration_status.setText(tr(notice.status))
            self.configuration_status.set_tone(notice.status_tone)

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
