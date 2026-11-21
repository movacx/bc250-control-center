"""The GPU screen as it was before the 2026-11-14 formal redesign.

Settings › Appearance › Interface style › Original brings it back. Only the
page layout lives here: the widgets, the state it reads and every signal are
the ones in ``gpu_governor_view``, so both layouts drive the same backend
through ``gpu_governor_integration``. Taken from commit 85a696e^; the one
change since is the voltage curve handed to each profile card.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..components.busy_spinner import BusyBadge
from ..components.buttons import WrappingButton as QPushButton
from ..components.page_widgets import (
    ConfirmDialog,
    MetricTile,
    SectionCard,
    caption,
)
from ..components.picker_row import PickerRow
from ..components.resize_grip import SideGrip
from ..components.style_state import set_style_properties
from ..components.widgets import icon
from ..core.temperature_unit import format_temperature
from ..i18n import governor_fix_label, tr, tr_format
from .gpu_governor_view import (  # noqa: F401 (shared with the modern layout)
    ABSOLUTE_CEILING,
    ALL_POINTS,
    BC250_KERNEL_CYAN,
    DEFAULT_PROFILES,
    EXTRA_POINTS,
    FLOOR,
    SAFE_CEILING,
    SAFE_POINTS,
    VOLTAGE_MAP,
    CheckRow,
    ContractPanel,
    FrequencyField,
    GpuProfile,
    GpuViewState,
    ProfileCardEditable,
    SafePointRail,
    SafePointTable,
    _accent_soft,
    _caption,
    _ContractLine,
    _qcolor,
    _running_bc250_kernel,
    _SafePointRow,
    _subpanel,
    backend_voltage_for,
    ceiling_for,
    curve_voltage,
    gpu_profile_name,
    offered_points,
    snap_to_point,
    voltage_for,
)

#: The layout's two columns, and the monitoring column's stored width.
CONTROLS_STRETCH = 18
TELEMETRY_STRETCH = 12
STACK_WIDTH = 1280
SIDE_WIDTH_KEY = "layout/gpu_side_width"
SIDE_MIN_WIDTH = 320
CONTROLS_MIN_WIDTH = 640


def temperature_detail(value: float) -> str:
    """Tile caption for the temperature reading.

    The mockup labels it ``Normal · hwmon``.  The bands are the ones the legacy
    screen already uses (``_temperature_status``) so the two never disagree.
    Whole phrases are translated rather than the bare adjective: "Normal" alone
    is already catalogued for an unrelated, differently-inflected context.
    """
    if value <= 0:
        return tr("hwmon")
    if value < 75:
        return tr("Normal · hwmon")
    if value < 85:
        return tr("Warm · hwmon")
    return tr("High · hwmon")


@dataclass

# ─────────────────────────────────────────────────────────────────────────────
# Metric tile grid — the mockup's ``auto-fit, minmax(140px, 1fr)``
# ─────────────────────────────────────────────────────────────────────────────

class ResponsiveTileGrid(QWidget):
    """Metric tiles that pick their column count from the width they are given.

    Three columns, so the six readings read as a block instead of a single
    thin strip.  Narrower panels drop to two and then one column, which is the
    only point where the count moves.
    """

    MINIMUM_TILE = 140
    COLUMNS = 3

    def __init__(self, tiles, parent: QWidget | None = None):
        super().__init__(parent)
        self._tiles = list(tiles)
        self._columns = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(10)
        self._grid.setVerticalSpacing(10)
        self._apply_columns(self.COLUMNS)

    def _apply_columns(self, columns: int) -> None:
        columns = max(1, min(self.COLUMNS, int(columns)))
        if columns == self._columns:
            return
        self._columns = columns
        for tile in self._tiles:
            self._grid.removeWidget(tile)
        for index, tile in enumerate(self._tiles):
            self._grid.addWidget(tile, index // columns, index % columns)
        for column in range(self.COLUMNS):
            self._grid.setColumnStretch(column, 1 if column < columns else 0)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().resizeEvent(event)
        spacing = self._grid.horizontalSpacing()
        self._apply_columns((self.width() + spacing) // (self.MINIMUM_TILE + spacing))



# ─────────────────────────────────────────────────────────────────────────────
# The screen
# ─────────────────────────────────────────────────────────────────────────────

class GpuGovernorView(QWidget):
    """Redesigned GPU module — presentation only.

    Signals towards the backend::

        range_apply_requested(int minimum, int maximum)
        range_startup_requested(int minimum, int maximum)
        profile_changed(object GpuProfile)
        service_action_requested(str)      # 'status' | 'restart' | 'disable'
        compatibility_apply_requested(dict)
        high_points_toggle_requested(bool)
        voltage_lab_requested()
        config_open_requested()

    Inputs::

        apply_state(GpuViewState)
        set_profiles(profiles)
    """

    range_apply_requested = pyqtSignal(int, int)
    range_startup_requested = pyqtSignal(int, int)
    profile_changed = pyqtSignal(object)
    export_to_decky_requested = pyqtSignal()
    service_action_requested = pyqtSignal(str)
    compatibility_apply_requested = pyqtSignal(dict)
    high_points_toggle_requested = pyqtSignal(bool)
    voltage_lab_requested = pyqtSignal()
    config_open_requested = pyqtSignal()
    #: The foot-of-page Modern | Classic buttons ("modern" or "original").
    interface_style_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("redesignedModule", True)
        self._state = GpuViewState(
            core_clock=1000,
            voltage=930,
            temperature=53.0,
            load=1,
            memory_clock=450,
            active_minimum=1000,
            active_maximum=1850,
            service_running=True,
            service_persistent=True,
            dbus_connected=True,
        )
        self._selected_minimum = 1000
        self._selected_maximum = 1850
        self._selected_profile = "gaming"
        self._compatibility_dirty = False
        #: Cyan unless told otherwise, so its behaviour is untouched by the
        #: Oberon adaptation below.
        self._oberon_mode = False
        # Telemetry refreshes must not yank a range the user is staging; the
        # selection re-syncs with the hardware when the screen is entered
        # again, not on every poll.
        self._follow_hardware = True

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 12, 16, 24)
        layout.setSpacing(12)

        self._workspace = QGridLayout()
        self._workspace.setContentsMargins(0, 0, 0, 0)
        self._workspace.setHorizontalSpacing(0)
        self._workspace.setVerticalSpacing(12)
        layout.addLayout(self._workspace)

        self._configuration = self._build_configuration_card()
        self._telemetry = self._build_telemetry_card()
        # Between the columns, a bar to drag sideways, as on the CPU screen.
        self._side_grip = SideGrip()
        self._side_grip.pressed.connect(self._side_drag_started)
        self._side_grip.dragged.connect(self._side_dragged)
        self._side_grip.released.connect(self._side_drag_finished)
        self._side_grip.double_clicked.connect(self.reset_side_width)
        self._side_width = self._stored_side_width()
        self._side_press_width = 0
        self._workspace.addWidget(self._configuration, 0, 0)
        self._workspace.addWidget(self._side_grip, 0, 1)
        self._workspace.addWidget(self._telemetry, 0, 2)
        self._workspace.setColumnStretch(0, CONTROLS_STRETCH)
        self._workspace.setColumnStretch(2, TELEMETRY_STRETCH)
        self._apply_side_width()

        layout.addWidget(self._build_advanced_card())
        layout.addStretch(1)
        from ..components.interface_style_switch import InterfaceStyleSwitch

        self.interface_switch = InterfaceStyleSwitch("original")
        self.interface_switch.chosen.connect(self.interface_style_requested)
        layout.addWidget(self.interface_switch)
        self.apply_state(self._state)

    # ── GPU configuration ──────────────────────────────────────────────────
    def _build_configuration_card(self) -> SectionCard:
        card = SectionCard(
            "GPU configuration",
            "Select a validated profile or stage an explicit D-Bus range. Every "
            "hardware change is reviewed before execution.",
            icon_name="gpu_purple",
            icon_background=_accent_soft(),
            status=("Safe mode", "green"),
        )
        # The same composition as the CPU workspace: no title row, since the
        # page already says where it is. The range state it carried moves to
        # the Cyan compatibility heading below, with the ring that stands in
        # for it while hardware work runs.
        self._safe_pill = card.drop_header()
        if self._safe_pill is not None:
            self._safe_pill.set_plain()
        self._busy_badge = BusyBadge()
        self._operation_busy = False

        profiles_panel, profiles_box = _subpanel("")
        self.profiles_panel = profiles_panel
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        profiles_title = QLabel(tr("Operating profile"))
        profiles_title.setProperty("cardTitle", True)
        profiles_title.setWordWrap(True)
        title_row.addWidget(profiles_title, 0)
        title_row.addStretch(1)
        self._profiles_title_row = title_row
        self._export_decky_button = QPushButton(tr("Export to Decky"))
        self._export_decky_button.setIcon(icon("gamepad_menu"))
        self._export_decky_button.setProperty("compactAction", True)
        self._export_decky_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._export_decky_button.setToolTip(
            tr("Send these three profile cards to the Decky Quick Access panel.")
        )
        self._export_decky_button.clicked.connect(self.export_to_decky_requested.emit)
        title_row.addWidget(self._export_decky_button, 0)
        title_row.setAlignment(self._export_decky_button, Qt.AlignmentFlag.AlignBottom)
        profiles_box.addLayout(title_row)
        profiles_box.addWidget(
            caption("One click sets the range. The pencil changes name and frequencies.")
        )
        self._profiles_grid = QGridLayout()
        self._profiles_grid.setContentsMargins(0, 0, 0, 0)
        self._profiles_grid.setHorizontalSpacing(8)
        self._profiles_grid.setVerticalSpacing(8)
        profiles_box.addLayout(self._profiles_grid)

        self._profile_cards: list[ProfileCardEditable] = []
        for column, profile in enumerate(DEFAULT_PROFILES):
            profile_card = ProfileCardEditable(replace(profile))
            profile_card.selected.connect(self._on_profile_selected)
            profile_card.changed.connect(self._on_profile_changed)
            self._profiles_grid.addWidget(profile_card, 0, column)
            self._profiles_grid.setColumnStretch(column, 1)
            self._profile_cards.append(profile_card)
        card.body.addWidget(profiles_panel)

        range_panel, range_box = _subpanel("Frequency range")
        self._range_panel = range_panel
        # One row: the subtitle on the left, the locked-points notice on the
        # right. The range itself is already in the two fields below the rail.
        header = QHBoxLayout()
        header.setSpacing(12)
        self._range_subtitle = _caption("")
        header.addWidget(self._range_subtitle, 1)
        self._locked_label = QLabel("")
        self._locked_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._locked_label.setProperty("railLegend", True)
        header.addWidget(self._locked_label, 0, Qt.AlignmentFlag.AlignVCenter)
        range_box.addLayout(header)
        # A kernel-imposed ceiling (the SteamOS BC-250 module) is a sentence,
        # not a legend: on the header row it took the whole width and squeezed
        # the subtitle into a one-word column. It gets its own wrapped line.
        self._ceiling_notice = QLabel("")
        self._ceiling_notice.setProperty("railLegend", True)
        self._ceiling_notice.setWordWrap(True)
        self._ceiling_notice.setVisible(False)
        range_box.addWidget(self._ceiling_notice)

        self._rail = SafePointRail()
        self._rail.range_changed.connect(self._on_rail_changed)
        range_box.addWidget(self._rail)

        fields = QHBoxLayout()
        fields.setSpacing(12)
        self._minimum_line = FrequencyField(
            "Minimum frequency",
            "Governor floor applied through the validated D-Bus interface.",
        )
        self._maximum_line = FrequencyField("Maximum frequency", "", accent=True)
        fields.addWidget(self._minimum_line, 1)
        fields.addWidget(self._maximum_line, 1)
        range_box.addLayout(fields)
        card.body.addWidget(range_panel)

        compat_panel, compat_box = _subpanel()
        self._compat_panel = compat_panel
        compat_title_row = QHBoxLayout()
        compat_title_row.setContentsMargins(0, 0, 0, 0)
        compat_title_row.setSpacing(8)
        compat_title = QLabel(tr("Cyan kernel compatibility"))
        compat_title.setProperty("cardTitle", True)
        compat_title.setWordWrap(True)
        compat_title_row.addWidget(compat_title, 1)
        # What Cyan is running under (the safe or the extended range) and,
        # while the governor is being changed, the ring that says so.
        if self._safe_pill is not None:
            compat_title_row.addWidget(self._safe_pill, 0, Qt.AlignmentFlag.AlignVCenter)
        compat_title_row.addWidget(self._busy_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        compat_box.addLayout(compat_title_row)
        self._compat_title_row = compat_title_row
        compat_box.addWidget(caption("Only touch this if the readings above look wrong."))
        # The legacy screen is hidden while this view is mounted, so the two
        # method selectors have to live here or they become unreachable.
        methods = QHBoxLayout()
        methods.setSpacing(10)
        self.set_method_combo = PickerRow("Governor method")
        self.set_method_combo.addItem("SMU", "smu")
        self.set_method_combo.addItem("Kernel", "kernel")
        self.usage_method_combo = PickerRow("Usage reading")
        for usage_method in ("busy-flag", "process", "kernel"):
            self.usage_method_combo.addItem(usage_method, usage_method)
        # gpu-usage.temp-read: the same sensor through the DRM ioctl or hwmon
        # in sysfs; sysfs keeps no DRM client open just for the temperature.
        self.temp_read_combo = PickerRow("Temperature reading")
        self.temp_read_combo.addItem("DRM", "drm")
        self.temp_read_combo.addItem("sysfs", "sysfs")
        for picker in (self.set_method_combo, self.usage_method_combo, self.temp_read_combo):
            picker.currentIndexChanged.connect(self._mark_compatibility_dirty)
            methods.addWidget(picker, 1)
        compat_box.addLayout(methods)
        # "process" looks like one more option, and it is the one that stops
        # Cyan from answering whenever a game is open.
        self._process_method_warning = QLabel(
            tr(
                "The process reading goes through every open file of every program. With a "
                "game open, Cyan stops answering: the range, the +2000 MHz points and the "
                "voltage lab stop working until the game closes. busy-flag is the default."
            )
        )
        self._process_method_warning.setWordWrap(True)
        self._process_method_warning.setProperty("gpuBusNotice", True)
        compat_box.addWidget(self._process_method_warning)
        self.usage_method_combo.currentIndexChanged.connect(self._sync_process_method_warning)
        self._sync_process_method_warning()

        # On MastaG's kernel the recommended settings differ from the stock ones.
        self._bc250_kernel_row = QWidget()
        kernel_row = QHBoxLayout(self._bc250_kernel_row)
        kernel_row.setContentsMargins(0, 0, 0, 0)
        kernel_row.setSpacing(10)
        kernel_note = caption(
            "The BC-250 kernel already fixes this telemetry. Its recommended settings: kernel method, "
            "kernel usage reading, sysfs temperature, both fixes off."
        )
        kernel_row.addWidget(kernel_note, 1)
        self._bc250_kernel_button = QPushButton(tr("Use the BC-250 kernel settings"))
        self._bc250_kernel_button.setProperty("ghostButton", True)
        self._bc250_kernel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._bc250_kernel_button.clicked.connect(self._stage_bc250_kernel_settings)
        kernel_row.addWidget(self._bc250_kernel_button, 0)
        self._bc250_kernel_row.hide()
        compat_box.addWidget(self._bc250_kernel_row)

        toggles = QHBoxLayout()
        toggles.setSpacing(16)
        # The mockup uses check boxes here, not chips: these two are settings
        # staged for "Apply compatibility", not actions that fire on click.
        self._metrics_toggle = CheckRow(governor_fix_label("metrics"))
        self._frequencies_toggle = CheckRow(governor_fix_label("frequency"))
        for box in (self._metrics_toggle, self._frequencies_toggle):
            box.setChecked(True)
            box.setCursor(Qt.CursorShape.PointingHandCursor)
            box.toggled.connect(self._mark_compatibility_dirty)
            toggles.addWidget(box, 0)
        toggles.addStretch(1)
        apply_compat = QPushButton(tr("Apply compatibility"))
        apply_compat.setProperty("ghostButton", True)
        apply_compat.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_compat.clicked.connect(
            lambda: self.compatibility_apply_requested.emit(self.compatibility_options())
        )
        toggles.addWidget(apply_compat, 0)
        compat_box.addLayout(toggles)
        card.body.addWidget(compat_panel)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.startup_button = QPushButton(tr("Save for startup"))
        self.startup_button.setProperty("ghostButton", True)
        self.startup_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.startup_button.clicked.connect(
            lambda: self.range_startup_requested.emit(
                self._selected_minimum, self._selected_maximum
            )
        )
        actions.addWidget(self.startup_button, 1)
        self.apply_button = QPushButton(tr("Review and apply range"))
        self.apply_button.setObjectName("PrimaryAction")
        self.apply_button.setProperty("primaryAction", True)
        self.apply_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_button.clicked.connect(self._confirm_and_apply)
        actions.addWidget(self.apply_button, 2)
        # Beside "Save for startup", so it takes that button's measurements:
        # the regular primary padding left it a few pixels taller.
        self.apply_button.setProperty("ghostSized", True)
        card.body.addLayout(actions)
        card.body.addStretch(1)
        return card

    # ── Live telemetry ─────────────────────────────────────────────────────
    def _build_telemetry_card(self) -> SectionCard:
        card = SectionCard(
            "Live GPU telemetry",
            "Read-only sensor data refreshed from amdgpu, the governor backend, "
            "and the existing performance service.",
            icon_name="metrics_blue",
            icon_background=_accent_soft(),
            status=("Live", "green"),
        )
        # No title row and no "Live" pill, as on the CPU workspace; the tiles
        # below are read by their labels, without a badge each.
        card.drop_header()

        self._tiles: dict[str, MetricTile] = {
            "core": MetricTile("Core clock", "--", "Current SCLK state", icon_name="", compact=True),
            "voltage": MetricTile("GPU voltage", "--", "OD / SMU telemetry", icon_name="", compact=True),
            "temperature": MetricTile("Temperature", "--", "hwmon", icon_name="", compact=True),
            "load": MetricTile("GPU load", "--", "amdgpu activity", icon_name="", compact=True),
            "memory": MetricTile("Memory clock", "--", "Current MCLK state", icon_name="", compact=True),
            "range": MetricTile("Active range", "--", "Persisted on hardware", icon_name="", compact=True),
        }
        card.body.addWidget(ResponsiveTileGrid(self._tiles.values()))
        card.body.addWidget(
            _caption("Passive readings · hardware changes require confirmation.")
        )
        # Says why the range and the D-Bus actions fail while Cyan is running
        # but not answering, instead of an error on every click.
        self._bus_notice = QLabel()
        self._bus_notice.setWordWrap(True)
        self._bus_notice.setProperty("gpuBusNotice", True)
        self._bus_notice.hide()
        card.body.addWidget(self._bus_notice)

        service_panel, service_box = _subpanel("Governor service")
        # "Enable" is systemd's word for "start at boot", so it named only half
        # of what this button does; a tester read it as "save for startup".
        # The button says what happens now, the caption what happens at boot.
        service_box.addWidget(
            _caption(
                "Start governor runs it now and saves it for startup (enables "
                "the service). Stop governor stops it and removes it from "
                "startup (disables the service)."
            )
        )
        service_actions = QHBoxLayout()
        service_actions.setSpacing(8)
        # Kept addressable so a test can check every one of these names is
        # something the backend planner actually accepts.
        self.service_buttons: dict[str, QPushButton] = {}
        for label, action in (("View status", "status"), ("Restart", "restart")):
            button = QPushButton(tr(label))
            self.service_buttons[action] = button
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setProperty("ghostButton", True)
            button.clicked.connect(
                lambda _checked=False, name=action: self.service_action_requested.emit(name)
            )
            service_actions.addWidget(button, 1)

        # One button for both directions: red "Disable" while the service runs,
        # green "Enable" while it does not.  ``_sync_service_toggle`` owns both
        # the label and which action it emits.
        self._service_toggle_action = "disable"
        self.service_toggle = QPushButton("")
        self.service_buttons["disable"] = self.service_toggle
        self.service_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.service_toggle.clicked.connect(
            lambda: self.service_action_requested.emit(self._service_toggle_action)
        )
        service_actions.addWidget(self.service_toggle, 1)
        self._sync_service_toggle(running=True)
        service_box.addLayout(service_actions)
        card.body.addWidget(service_panel)

        lab_panel, lab_box = _subpanel("")
        self.lab_panel = lab_panel
        lab_head = QHBoxLayout()
        lab_head.setSpacing(10)
        self._lab_title = lab_title = QLabel(tr("Voltage laboratory"))
        lab_title.setProperty("cardTitle", True)
        lab_head.addWidget(lab_title, 1)
        self._lab_point = QLabel("")
        self._lab_point.setProperty("rangeReadout", True)
        lab_head.addWidget(self._lab_point, 0, Qt.AlignmentFlag.AlignRight)
        lab_box.addLayout(lab_head)
        lab_box.addWidget(
            _caption("Point-by-point conservative validation of the selected range.")
        )
        lab_actions = QHBoxLayout()
        lab_actions.setSpacing(8)
        open_lab = QPushButton(tr("Open laboratory"))
        open_lab.setProperty("accentAction", True)
        open_lab.setCursor(Qt.CursorShape.PointingHandCursor)
        open_lab.clicked.connect(self.voltage_lab_requested)
        lab_actions.addWidget(open_lab, 1)
        self._open_config_button = open_config = QPushButton(tr("Open config.toml"))
        open_config.setProperty("ghostButton", True)
        open_config.setCursor(Qt.CursorShape.PointingHandCursor)
        open_config.clicked.connect(self.config_open_requested)
        lab_actions.addWidget(open_config, 1)
        lab_box.addLayout(lab_actions)
        card.body.addWidget(lab_panel)

        risk_panel, risk_box = _subpanel("")
        self._risk_panel = risk_panel
        risk_panel.setProperty("riskPanel", True)
        risk_head = QHBoxLayout()
        risk_head.setSpacing(7)
        risk_glyph = QLabel()
        risk_glyph.setPixmap(icon("warning_orange").pixmap(QSize(14, 14)))
        risk_glyph.setFixedSize(14, 16)
        risk_head.addWidget(risk_glyph, 0)
        eyebrow = QLabel(tr("DANGER ZONE"))
        eyebrow.setProperty("eyebrow", True)
        eyebrow.setProperty("danger", True)
        risk_head.addWidget(eyebrow, 1)
        self._unlock_state = _caption("")
        risk_head.addWidget(self._unlock_state, 0)
        risk_box.addLayout(risk_head)

        risk_title = QLabel(tr("TOML points above 2000 MHz"))
        risk_title.setProperty("panelHeadline", True)
        risk_title.setWordWrap(True)
        risk_box.addWidget(risk_title)
        # Interpolated, so localize_widget_tree() cannot map it back to a source
        # string: retranslate_dynamic_copy() rebuilds it on a language change.
        self._risk_caption = _caption("")
        self._refresh_risk_caption()
        risk_box.addWidget(self._risk_caption)
        self.unlock_button = QPushButton("")
        self.unlock_button.setProperty("dangerAction", True)
        self.unlock_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.unlock_button.clicked.connect(
            lambda: self.high_points_toggle_requested.emit(not self._state.unlocked)
        )
        risk_box.addWidget(self.unlock_button)
        # The mockup leaves more air above the danger zone than between the
        # neutral panels, so it reads as a separate class of control.
        card.body.addSpacing(10)
        card.body.addWidget(risk_panel)
        card.body.addStretch(1)
        return card

    # ── Advanced diagnostics ───────────────────────────────────────────────
    def _build_advanced_card(self) -> SectionCard:
        card = SectionCard(
            "Advanced GPU diagnostics",
            "TOML safe-point controls, voltage validation and hardware details.",
            icon_name="",
        )
        # add_header_button keeps SectionCard's own bookkeeping in sync; adding
        # the widget straight into header_actions leaves the host hidden.
        self._advanced_toggle = card.add_header_button(
            "Show", lambda: None, width=104
        )
        self._advanced_toggle.setCheckable(True)
        self._advanced_toggle.setProperty("compactAction", False)
        self._advanced_toggle.setProperty("linkButton", True)
        self._advanced_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._advanced_toggle.setIcon(icon("chevron_right_gray"))
        self._advanced_toggle.setIconSize(QSize(14, 14))
        self._advanced_toggle.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._advanced_toggle.toggled.connect(self._toggle_advanced)

        self._advanced_body = QWidget()
        body = QGridLayout(self._advanced_body)
        self._advanced_grid = body
        body.setContentsMargins(0, 0, 0, 0)
        body.setHorizontalSpacing(12)
        body.setVerticalSpacing(12)

        left = QWidget()
        left_box = QVBoxLayout(left)
        left_box.setContentsMargins(0, 0, 0, 0)
        left_box.setSpacing(12)
        self._safe_point_table = SafePointTable()
        self._contract = ContractPanel()
        left_box.addWidget(self._safe_point_table)
        left_box.addWidget(self._contract)
        left_box.addStretch(1)
        # Service output runs in the application's terminal: the table and
        # the contract take the card's whole width.
        body.addWidget(left, 0, 0)
        self._advanced_body.setVisible(False)
        card.root.addWidget(self._advanced_body)
        return card

    # ── live language change ───────────────────────────────────────────────
    def _refresh_risk_caption(self) -> None:
        self._risk_caption.setText(
            tr_format(
                "Uncomment the {extra_low}–{extra_high} MHz safe-points in "
                "config.toml (up to {voltage} mV). It can hang the board or "
                "corrupt the SMU state.",
                extra_low=EXTRA_POINTS[0][0],
                extra_high=ABSOLUTE_CEILING,
                voltage=EXTRA_POINTS[-1][1],
            )
        )

    def follow_hardware_again(self) -> None:
        """Called once a staged range has actually been applied."""
        self._follow_hardware = True

    def retranslate_dynamic_copy(self) -> None:
        """Re-applies the copy that ``localize_widget_tree`` cannot recover.

        Two kinds: strings already interpolated at build time (no source to map
        back to) and the fix-labels, which live in their own catalogue.
        """
        self.interface_switch.retranslate()
        self._metrics_toggle.setText(governor_fix_label("metrics"))
        self._frequencies_toggle.setText(governor_fix_label("frequency"))
        self.set_method_combo.retranslate()
        self.usage_method_combo.retranslate()
        self.temp_read_combo.retranslate()
        self._refresh_risk_caption()
        self._busy_badge.retranslate()
        self._advanced_toggle.setText(
            tr("Hide") if self._advanced_toggle.isChecked() else tr("Show")
        )
        for profile_card in self._profile_cards:
            profile_card.retranslate()
        self.apply_state(self._state)

    def _sync_service_toggle(self, *, running: bool) -> None:
        """The toggle names the action it performs, and is coloured to match."""
        self._service_toggle_action = "disable" if running else "enable"
        self.service_toggle.setText(
            tr("Stop governor") if running else tr("Start governor")
        )
        set_style_properties(
            self.service_toggle, {"dangerAction": running, "successAction": not running}
        )

    # ── safe mode banner ───────────────────────────────────────────────────
    def _sync_safe_mode(self, state: "GpuViewState") -> None:
        """Three states, in order of what the user most needs to know.

        A stopped governor comes first: no range applies at all while it is
        down, so saying "safe mode" there would be misleading. Then the
        uncommented +2000 MHz points, then the ordinary safe state. The pill
        carries all of it, since the banner that used to repeat it was cut.
        """
        unlocked = state.unlocked
        if self._safe_pill is not None and not state.service_running:
            self._safe_pill.setText("Governor stopped — press Start governor")
            self._safe_pill.set_tone("orange")
            return
        if self._safe_pill is not None:
            self._safe_pill.setText("Extended range" if unlocked else "Safe mode")
            self._safe_pill.set_tone("red" if unlocked else "green")

    # ── Cyan compatibility ─────────────────────────────────────────────────
    def _sync_process_method_warning(self, *_args) -> None:
        self._process_method_warning.setVisible(
            self.usage_method_combo.currentData() == "process"
        )

    def _bc250_kernel_settings_differ(self) -> bool:
        wanted = dict(BC250_KERNEL_CYAN)
        if self.temp_read_combo.isEnabled() is False:
            wanted.pop("temp_read")
        current = {
            "set_method": self.set_method_combo.currentData(),
            "usage_method": self.usage_method_combo.currentData(),
            "temp_read": self.temp_read_combo.currentData(),
            "fix_metrics": self._metrics_toggle.isChecked(),
            "fix_frequency": self._frequencies_toggle.isChecked(),
        }
        return any(current[key] != value for key, value in wanted.items())

    def _stage_bc250_kernel_settings(self) -> None:
        """Set the pickers to the kernel's recommendation; Apply compatibility sends them."""
        settings = BC250_KERNEL_CYAN
        for combo, value in (
            (self.set_method_combo, settings["set_method"]),
            (self.usage_method_combo, settings["usage_method"]),
            (self.temp_read_combo, settings["temp_read"]),
        ):
            if combo is self.temp_read_combo and not combo.isEnabled():
                continue
            combo.setCurrentIndex(max(0, combo.findData(value)))
        self._metrics_toggle.setChecked(settings["fix_metrics"])
        self._frequencies_toggle.setChecked(settings["fix_frequency"])
        self._mark_compatibility_dirty()
        self._bc250_kernel_row.setVisible(False)

    def _mark_compatibility_dirty(self, *_args) -> None:
        """Stops refresh() from overwriting a choice the user just made.

        Cleared by ``compatibility_options()`` once the choice is applied, and
        by ``showEvent`` when the screen is entered again — otherwise a staged
        edit that is never applied leaves the panel permanently disagreeing
        with config.toml.
        """
        self._compatibility_dirty = True

    def compatibility_options(self) -> dict:
        self._compatibility_dirty = False
        return {
            "set_method": str(self.set_method_combo.currentData() or "smu"),
            "usage_method": str(self.usage_method_combo.currentData() or "busy-flag"),
            "metrics": self._metrics_toggle.isChecked(),
            "frequencies": self._frequencies_toggle.isChecked(),
            # Only for a Cyan that reads it; otherwise the line stays as is.
            "temp_read": (
                str(self.temp_read_combo.currentData() or "drm")
                if self.temp_read_combo.isEnabled()
                else None
            ),
        }

    def _sync_compatibility(self, state: "GpuViewState") -> None:
        if self._compatibility_dirty:
            return
        widgets = (
            self.set_method_combo,
            self.usage_method_combo,
            self.temp_read_combo,
            self._metrics_toggle,
            self._frequencies_toggle,
        )
        blocked = tuple(widget.blockSignals(True) for widget in widgets)
        try:
            set_index = self.set_method_combo.findData(state.set_method)
            usage_index = self.usage_method_combo.findData(state.usage_method)
            self.set_method_combo.setCurrentIndex(max(0, set_index))
            self.usage_method_combo.setCurrentIndex(max(0, usage_index))
            self.temp_read_combo.setCurrentIndex(max(0, self.temp_read_combo.findData(state.temp_read)))
            self._metrics_toggle.setChecked(state.fix_metrics)
            self._frequencies_toggle.setChecked(state.fix_frequency)
        finally:
            for widget, previous in zip(widgets, blocked, strict=True):
                widget.blockSignals(previous)
        self._sync_process_method_warning()
        self._bc250_kernel_row.setVisible(
            bool(state.bc250_kernel) and state.backend == "cyan-skillfish-governor-smu"
            and self._bc250_kernel_settings_differ()
        )
        # An older Cyan ignores temp-read: shown, so the option is known, but
        # not sent. Unknown (no binary found) is left usable.
        supported = state.temp_read_supported is not False
        self.temp_read_combo.setEnabled(supported)
        self.temp_read_combo.setToolTip(
            tr(
                "Where Cyan reads the GPU temperature. Both give the same value; "
                "sysfs keeps no GPU device open just for it. DRM is the default."
            )
            if supported
            else tr("This Cyan version does not read this setting. Update it from Prepare dependencies.")
        )

    # ── interaction ────────────────────────────────────────────────────────
    def _toggle_advanced(self, checked: bool) -> None:
        self._advanced_body.setVisible(checked)
        self._advanced_toggle.setText(tr("Hide") if checked else tr("Show"))

    def _on_profile_selected(self, profile: GpuProfile) -> None:
        # Same staging protection as the rail: otherwise the next telemetry
        # refresh calls sync_active_range() and snaps the card back to
        # whatever the hardware still reports, before the user gets to Apply.
        self._follow_hardware = False
        self._selected_profile = profile.key
        self._selected_minimum = profile.minimum
        self._selected_maximum = profile.maximum
        self._sync_selection()

    def _on_profile_changed(self, profile: GpuProfile) -> None:
        if profile.key == self._selected_profile:
            self._selected_minimum = profile.minimum
            self._selected_maximum = profile.maximum
        self._sync_selection()
        self.profile_changed.emit(profile)

    def _on_rail_changed(self, minimum: int, maximum: int) -> None:
        self._follow_hardware = False
        self._selected_minimum, self._selected_maximum = minimum, maximum
        self._selected_profile = self._profile_key_for(minimum, maximum)
        self._sync_selection()

    def _profile_key_for(self, minimum: int, maximum: int) -> str:
        for profile_card in self._profile_cards:
            profile = profile_card.profile
            if (profile.minimum, profile.maximum) == (minimum, maximum):
                return profile.key
        return "custom"

    def _selected_profile_name(self) -> str:
        for profile_card in self._profile_cards:
            if profile_card.profile.key == self._selected_profile:
                return profile_card.profile.name
        return tr("Custom")

    def _confirm_and_apply(self) -> None:
        minimum, maximum = self._selected_minimum, self._selected_maximum
        risky = maximum > SAFE_CEILING
        message = tr(
            "The governor rewrites the range over D-Bus and saves persistence. "
            "If the board hangs, it reverts to the last valid range on reboot."
        )
        if risky:
            message += "\n\n" + tr_format(
                "You are above the safe ceiling ({ceiling} MHz). The board may "
                "hang and need a cold reboot.",
                ceiling=SAFE_CEILING,
            )
            if self._state.set_method == "kernel":
                # amdgpu publishes an OD_RANGE the kernel path cannot exceed
                # (2000 MHz on a stock BC-250 driver), so the request would be
                # refused after the TOML had already been written.
                message += "\n\n" + tr(
                    "The Kernel method cannot go past 2000 MHz on a stock "
                    "BC-250 driver. Switch the governor method to SMU, or use "
                    "a patched kernel."
                )
        dialog = ConfirmDialog(
            tr_format("Apply {minimum} – {maximum} MHz", minimum=minimum, maximum=maximum),
            message,
            summary=(
                ("Profile", self._selected_profile_name()),
                ("Voltage", f"{backend_voltage_for(maximum, is_oberon=self._oberon_mode)} mV"),
                # Named explicitly: this is the TOML's ceiling, not the range
                # being applied, and reading it as the latter is confusing.
                ("TOML ceiling", f"{ceiling_for(unlocked=self._state.unlocked)} MHz"),
            ),
            confirm_text="Apply now",
            eyebrow="CONFIRM HARDWARE ACTION",
            tone="red" if risky else "blue",
            parent=self,
        )
        if dialog.exec():
            self.range_apply_requested.emit(minimum, maximum)

    # ── backend inputs ─────────────────────────────────────────────────────
    def set_profiles(self, profiles: Sequence[GpuProfile]) -> None:
        """Applies profiles saved by the user, in order."""
        for profile_card, profile in zip(self._profile_cards, profiles):
            profile_card.set_profile(profile)
        self._sync_selection()

    def set_oberon_mode(self, is_oberon: bool) -> None:
        """Dress this same screen for the Oberon backend.

        Oberon is not a reduced Cyan: it has two YAML endpoints instead of a
        multi-point TOML curve, no kernel compatibility switches, and no
        commented-out points to uncomment. So the panels that only describe
        Cyan's model are hidden rather than shown empty or, worse, shown with
        Cyan's numbers over an Oberon board.

        Everything the two backends genuinely share — profiles, telemetry, the
        service controls, the voltage laboratory — keeps the same layout and
        the same button positions, which is the point of reusing this view.
        """
        is_oberon = bool(is_oberon)
        if is_oberon == self._oberon_mode:
            return
        self._oberon_mode = is_oberon

        # Cyan's frequency model, in three panels that Oberon has no analogue for.
        self._range_panel.setVisible(not is_oberon)
        self._compat_panel.setVisible(not is_oberon)
        self._risk_panel.setVisible(not is_oberon)
        # The range state and the busy ring live in the Cyan compatibility
        # heading; with that panel gone they go up beside the profiles.
        self._place_status(self._profiles_title_row if is_oberon else self._compat_title_row)

        for profile_card in self._profile_cards:
            profile_card.set_editable(not is_oberon)
        # Oberon's three profiles are fixed by the shared contract and Decky
        # already ships the matching oberon-1500/1850/2000 buttons; there is
        # nothing user-edited here to export.
        self._export_decky_button.setVisible(not is_oberon)

        # The backend refuses startup persistence for Oberon outright
        # (``guardar_rango_gpu_arranque`` raises), so offering it would be a
        # button whose only outcome is an error.
        self.startup_button.setVisible(not is_oberon)
        self.apply_button.setText(
            tr("Review and apply Oberon profile") if is_oberon
            else tr("Review and apply range")
        )
        self._lab_title.setText(
            tr("YAML endpoint laboratory") if is_oberon else tr("Voltage laboratory")
        )
        self._open_config_button.setText(
            tr("Open oberon-config.yaml") if is_oberon else tr("Open config.toml")
        )

    def _place_status(self, row: QHBoxLayout) -> None:
        widgets = [w for w in (self._safe_pill, self._busy_badge) if w is not None]
        for widget in widgets:
            for layout in (self._profiles_title_row, self._compat_title_row):
                layout.removeWidget(widget)
        # After the heading and its stretch, ahead of any action on the row.
        position = 2 if row is self._profiles_title_row else 1
        for offset, widget in enumerate(widgets):
            row.insertWidget(position + offset, widget, 0, Qt.AlignmentFlag.AlignVCenter)
        # A widget handed to another parent comes back hidden; restore the
        # one of the two that should be showing.
        busy = self._operation_busy
        self._busy_badge.setVisible(busy)
        if self._safe_pill is not None:
            self._safe_pill.setVisible(not busy)

    def profiles(self) -> tuple[GpuProfile, ...]:
        return tuple(profile_card.profile for profile_card in self._profile_cards)

    def selected_range(self) -> tuple[int, int]:
        return self._selected_minimum, self._selected_maximum

    def set_operation_busy(self, active: bool, text: str) -> None:
        """A small ring in the status pill's place while hardware work runs."""
        self._operation_busy = bool(active)
        self._busy_badge.set_text(text)
        self._busy_badge.set_running(active)
        if self._safe_pill is not None:
            self._safe_pill.setVisible(not active)

    def apply_state(self, state: GpuViewState) -> None:
        self._state = state
        unlocked = state.unlocked

        self._tiles["core"].set_values(f"{state.core_clock} MHz")
        self._tiles["voltage"].set_values(f"{state.voltage} mV")
        self._tiles["temperature"].set_values(
            format_temperature(state.temperature),
            temperature_detail(state.temperature),
        )
        self._tiles["load"].set_values(f"{state.load} %")
        self._tiles["memory"].set_values(f"{state.memory_clock} MHz")
        range_known = state.active_minimum > 0 and state.active_maximum > 0
        stalled = state.dbus_responsive is False
        # 0–0 MHz read as a real range; it only ever meant "not read".
        self._tiles["range"].set_values(
            f"{state.active_minimum}–{state.active_maximum} MHz" if range_known else "--",
            "Cyan is not answering" if stalled and not range_known else "Persisted on hardware",
        )
        if stalled:
            self._bus_notice.setText(
                tr(
                    "Cyan is running but not answering. Its usage reading is set to process, "
                    "which reads every open file of every program; a Proton game keeps tens of "
                    "thousands open. Choose busy-flag in Cyan kernel compatibility and apply."
                )
                if state.usage_method == "process"
                else tr(
                    "Cyan is running but not answering on D-Bus, so its range cannot be read or "
                    "changed right now. Restart the governor if it does not recover."
                )
            )
        self._bus_notice.setVisible(stalled)

        self._sync_service_toggle(running=state.service_running)

        self._unlock_state.setText(tr("Enabled") if unlocked else tr("Locked"))
        self.unlock_button.setText(
            tr("Re-comment the +2000 MHz points")
            if unlocked
            else tr("Uncomment +2000 MHz points")
        )
        ceiling_notice = (
            tr_format(
                "{reason} Maximum selectable frequency: {ceiling} MHz.",
                reason=state.frequency_ceiling_reason,
                ceiling=state.frequency_ceiling_mhz,
            )
            if state.frequency_ceiling_mhz is not None
            else ""
        )
        self._ceiling_notice.setText(ceiling_notice)
        self._ceiling_notice.setVisible(bool(ceiling_notice))
        self._locked_label.setText(
            ""
            if ceiling_notice or unlocked
            else tr_format(
                "{minimum}–{maximum} MHz COMMENTED IN THE TOML",
                minimum=EXTRA_POINTS[0][0],
                maximum=ABSOLUTE_CEILING,
            )
        )

        self._sync_safe_mode(state)
        self._sync_compatibility(state)
        self._rail.set_unlocked(unlocked)
        self._rail.set_maximum_mhz(state.frequency_ceiling_mhz)
        curve = dict(state.safe_points)
        for profile_card in self._profile_cards:
            profile_card.set_unlocked(unlocked)
            profile_card.set_maximum_mhz(state.frequency_ceiling_mhz)
            profile_card.set_voltage_curve(curve)
        self._sync_selection()

    def sync_active_range(self, minimum: int, maximum: int) -> None:
        """Aligns the selection with the range the hardware reports.

        Ignored while the user is staging a range of their own — otherwise the
        next refresh would snap the rail back to the active range mid-edit.
        Re-entering the screen (``showEvent``) resumes following the hardware.
        """
        if not self._follow_hardware:
            return
        if minimum and maximum:
            self._selected_minimum, self._selected_maximum = minimum, maximum
            self._selected_profile = self._profile_key_for(minimum, maximum)
            self._sync_selection()

    def _sync_selection(self) -> None:
        unlocked = self._state.unlocked
        ceiling = min(
            ceiling_for(unlocked=unlocked),
            self._state.frequency_ceiling_mhz or ABSOLUTE_CEILING,
        )
        self._selected_maximum = min(self._selected_maximum, ceiling)
        self._selected_minimum = min(self._selected_minimum, self._selected_maximum)

        self._rail.set_range(self._selected_minimum, self._selected_maximum)
        subtitle = tr_format(
            "Fine-tune over the TOML points · current ceiling {ceiling} MHz.",
            ceiling=ceiling,
        )
        # The ceiling's reason is on its own line (``_ceiling_notice``).
        self._range_subtitle.setText(subtitle)
        self._minimum_line.set_values(str(self._selected_minimum))
        self._maximum_line.set_values(
            str(self._selected_maximum),
            tr_format("Current ceiling {ceiling} MHz per config.toml.", ceiling=ceiling),
        )
        self._lab_point.setText(
            f"{self._selected_maximum} MHz · "
            f"{backend_voltage_for(self._selected_maximum, is_oberon=self._oberon_mode)} mV"
        )

        for profile_card in self._profile_cards:
            profile_card.set_active(profile_card.profile.key == self._selected_profile)

        self._safe_point_table.refresh(
            self._selected_minimum,
            self._selected_maximum,
            unlocked=unlocked,
            points=self._state.safe_points,
        )
        active = sum(
            1 for frequency, _v in self._state.safe_points if frequency <= ceiling
        )
        self._contract.set_rows(
            (
                ("Device", self._state.device),
                ("Governor", self._state.backend),
                ("Accepted range", f"{self._selected_minimum} – {self._selected_maximum} MHz"),
                ("Allowed ceiling", f"{ceiling} MHz"),
                (
                    "Active points",
                    tr_format(
                        "{active} of {total} in config.toml",
                        active=active,
                        total=len(self._state.safe_points),
                    ),
                ),
                (
                    "D-Bus API",
                    tr("Connected · range running")
                    if self._state.dbus_connected
                    else tr("Not connected"),
                ),
                ("Configuration", self._state.config_path),
            )
        )

    # ── lifecycle ──────────────────────────────────────────────────────────
    def showEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().showEvent(event)
        # Coming back to the screen is the moment to trust the hardware again —
        # for the rail and for the compatibility controls alike. Without this,
        # one click on a check box latched _compatibility_dirty forever and the
        # panel kept showing values config.toml no longer had.
        self._follow_hardware = True
        self._compatibility_dirty = False
        self.sync_active_range(self._state.active_minimum, self._state.active_maximum)
        self._sync_compatibility(self._state)

    # ── reflow ─────────────────────────────────────────────────────────────
    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().resizeEvent(event)
        self._reflow(self.width())

    # ── monitoring column width (same rules as the CPU screen) ────────────
    @staticmethod
    def _layout_settings():
        from ..core.preferences import application_settings

        return application_settings()

    def _stored_side_width(self) -> int:
        try:
            value = int(self._layout_settings().value(SIDE_WIDTH_KEY, 0) or 0)
        except (TypeError, ValueError):
            return 0
        return value if value >= SIDE_MIN_WIDTH else 0

    def _side_bounds(self) -> tuple[int, int]:
        available = max(self.width(), STACK_WIDTH)
        return SIDE_MIN_WIDTH, max(SIDE_MIN_WIDTH, available - CONTROLS_MIN_WIDTH - self._side_grip.width())

    def _apply_side_width(self) -> None:
        stacked = self._workspace.itemAtPosition(1, 0) is not None
        if self._side_width and not stacked:
            low, high = self._side_bounds()
            self._telemetry.setFixedWidth(max(low, min(high, self._side_width)))
            self._workspace.setColumnStretch(2, 0)
        else:
            self._telemetry.setMinimumWidth(0)
            self._telemetry.setMaximumWidth(16777215)
            if not stacked:
                self._workspace.setColumnStretch(2, TELEMETRY_STRETCH)

    def _side_drag_started(self) -> None:
        self._side_press_width = self._telemetry.width()

    def _side_dragged(self, delta: int) -> None:
        low, high = self._side_bounds()
        self._side_width = max(low, min(high, self._side_press_width - delta))
        self._apply_side_width()

    def _side_drag_finished(self) -> None:
        if self._side_width:
            self._layout_settings().setValue(SIDE_WIDTH_KEY, int(self._side_width))

    def reset_side_width(self) -> None:
        self._side_width = 0
        self._layout_settings().remove(SIDE_WIDTH_KEY)
        self._apply_side_width()

    def side_width(self) -> int:
        return self._side_width

    def _reflow(self, width: int) -> None:
        # At the default window (1460 px) the page is about 1200 px wide: too
        # narrow for the range slider beside the telemetry, so it stacks, as
        # the CPU page does.
        stacked = width < STACK_WIDTH
        telemetry_stacked = self._workspace.itemAtPosition(1, 0) is not None
        if stacked and not telemetry_stacked:
            self._workspace.removeWidget(self._telemetry)
            self._workspace.addWidget(self._telemetry, 1, 0, 1, 3)
            self._workspace.setColumnStretch(2, 0)
            self._side_grip.hide()
            self._apply_side_width()
        elif not stacked and telemetry_stacked:
            self._workspace.removeWidget(self._telemetry)
            self._workspace.addWidget(self._telemetry, 0, 2)
            self._workspace.setColumnStretch(2, TELEMETRY_STRETCH)
            self._side_grip.show()
            self._apply_side_width()
        elif not stacked and self._side_width:
            self._apply_side_width()  # keep the stored width inside the new window

        columns = 1 if width < 700 else 3
        current = 1 if self._profiles_grid.itemAtPosition(1, 0) is not None else 3
        if columns != current:
            for index, profile_card in enumerate(self._profile_cards):
                self._profiles_grid.removeWidget(profile_card)
                row, column = (index, 0) if columns == 1 else (0, index)
                self._profiles_grid.addWidget(profile_card, row, column)


