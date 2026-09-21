"""Unified CPU module — presentation layer (PyQt6).

Destination: ``frontends/desktop/pages/cpu_control_view.py``

One screen, not two. The CPU page used to split itself into a *CPU
configuration* tab and an *Overview and live monitoring* tab, so reading a
temperature and changing a frequency were never visible at the same time —
which is precisely when you want both. This rebuilds them as the single
workspace the redesigned Cyan GPU module already uses:

    ┌ CPU configuration ────────┐ ┌ Live metrics ──────────────────┐
    │ operating profile (3)     │ │ 6 sensor tiles                 │
    │ temporary apply mode      │ │ per-core monitor (8 slots)     │
    │ Apply                     │ │ runtime status (6 readings)    │
    └───────────────────────────┘ │ boot persistence + actions     │
                                  │ danger zone (hidden CPU cores) │
                                  └────────────────────────────────┘
    ┌ Session console ──────────────────────────────────────────────┐
    │ command output                                                 │
    │ processor identity, CPU-Z style (same card, always shown)     │
    └─────────────────────────────────────────────────────────────┘

There is no separate parameter panel. The three profile cards *are* the
inputs: click one to select it, use the pencil to change its frequency, VID
and temperature cap. A panel repeating the same three numbers underneath them
was two controls for one value.

The danger zone is the hidden-core unlock. It is the one CPU action that
survives a reboot and cannot be undone from this screen, so it gets the same
red treatment the GPU module gives its commented-out TOML points.

Command output does not live here. The application has one embedded terminal
(``frontends/desktop/console``) and every workflow draws into it, so a second
read-only console inside this page would have been a second place to look.

Does not talk to the controller, Polkit or the SMU: it exposes signals and
receives a :class:`CpuControlState`. The wiring lives in
``cpu_control_integration.py``.

Every row is built once and told what it is, never rebuilt per refresh —
``tests/desktop/architecture/test_refreshes_update_instead_of_rebuild.py``
fixes that for this module too.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Sequence

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from bc250cc.shared.contract import (
    CPU_FREQUENCY_RANGE,
    CPU_FREQUENCY_STEP_MHZ,
    CPU_SCALE_RANGE,
    CPU_TEMPERATURE_RANGE,
    CPU_VID_RANGE,
    CPU_VID_STEP_MV,
)

from ..components.buttons import WrappingButton as QPushButton
from ..components.core_monitor import CoreGrid, CoreReading
from ..components.page_widgets import SectionCard, caption, subpanel
from ..components.widgets import PillLabel, icon
from ..i18n import tr, tr_format
from ..theme import COLORS

#: The BC-250 exposes eight physical core positions, so the strip is
#: fixed-size and its rows can be built once. The GDDR6 rail has its own
#: count in ``components.dashboard_widgets``, which owns that strip.

#: Width below which the two workspace columns stack. Same breakpoint the GPU
#: module uses, so the two screens never reflow at different moments.
STACK_WIDTH = 1180

#: Width below which the three profile cards stack into one column.
PROFILE_STACK_WIDTH = 700


# ─────────────────────────────────────────────────────────────────────────────
# State — everything the view draws, and nothing it fetches
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CoreUnlockState:
    detected_shape: str = ""
    source_ready: bool = False
    helper_ready: bool = False
    governor_state: str = ""
    unlock_allowed: bool = False
    unlocked: bool = False


@dataclass(frozen=True)
class RuntimeReading:
    """One ``value`` over ``detail`` reading of the runtime status block."""

    value: str = "--"
    detail: str = ""


@dataclass(frozen=True)
class CpuTuningState:
    """What the hardware is running and what the session may still do."""

    frequency_mhz: int = 0
    vid_mv: int = 0
    temperature_c: int = 0
    scale: int | None = None
    manual_scale_available: bool = False
    applying: bool = False
    persistence_enabled: bool = False

    #: The six runtime readings, keyed by ``CpuControlView.RUNTIME_ROWS``.
    runtime: dict[str, RuntimeReading] = field(default_factory=dict)


@dataclass(frozen=True)
class CpuControlState:
    model_name: str = ""
    architecture: str = ""
    vendor: str = ""
    platform_process: str = ""
    microcode: str = ""
    topology: str = ""
    cache: str = ""
    features: str = ""
    total_usage_percent: float = 0.0

    cores: tuple[CoreReading, ...] = ()
    core_unlock: CoreUnlockState = field(default_factory=CoreUnlockState)
    tuning: CpuTuningState = field(default_factory=CpuTuningState)


@dataclass(frozen=True)
class CpuTuningRequest:
    """What ``Apply`` asks the backend for."""

    frequency_mhz: int
    vid_mv: int
    temperature_c: int
    manual_scale: bool = False
    scale: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# Operating profiles
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CpuProfile:
    """Editable operating profile: name + the three detector inputs."""

    key: str
    name: str
    frequency_mhz: int
    vid_mv: int
    temperature_c: int

    def summary(self) -> str:
        return f"{self.frequency_mhz} MHz"

    def detail(self) -> str:
        return f"{self.vid_mv} mV · {self.temperature_c} °C"

    def values(self) -> tuple[int, int, int]:
        return (self.frequency_mhz, self.vid_mv, self.temperature_c)


#: The three tiers this project has always shipped. The fourth entry the old
#: list carried sat 150 MHz from its neighbour at the same VID, so it read as
#: a slider with an arbitrary notch in it rather than as a choice.
DEFAULT_CPU_PROFILES: tuple[CpuProfile, ...] = (
    CpuProfile("board_average", "Placa media", 3550, 1050, 90),
    CpuProfile("mid_point", "Punto medio", 3850, 1150, 90),
    CpuProfile("safe_maximum", "Max seguro", 4000, 1275, 90),
)


# ─────────────────────────────────────────────────────────────────────────────
# Identity rows — label left, value right, hairline between
# ─────────────────────────────────────────────────────────────────────────────

class IdentityRow(QFrame):
    """One ``label ......... value`` line of an identity panel."""

    def __init__(self, label: str, parent: QWidget | None = None, *, compact: bool = False):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._first = False
        row = QHBoxLayout(self)
        vertical = 5 if compact else 7
        row.setContentsMargins(0, vertical, 0, vertical)
        row.setSpacing(12)
        self.label = QLabel(tr(label))
        self.label.setWordWrap(True)
        row.addWidget(self.label, 1)
        self.value = QLabel("--")
        self.value.setWordWrap(True)
        self.value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(self.value, 2)
        self._refresh_palette()

    def set_first(self, first: bool) -> None:
        if first == self._first:
            return
        self._first = first
        self._refresh_palette()

    def set_value(self, value: str) -> None:
        self.value.setText(value or "--")

    def set_label(self, label: str) -> None:
        self.label.setText(tr(label))

    def _refresh_palette(self) -> None:
        border = (
            "border:none;" if self._first
            else f"border:none; border-top:1px solid {COLORS['border_soft']};"
        )
        self.setStyleSheet(f"QFrame {{ background:transparent; {border} }}")
        self.label.setStyleSheet(
            f"color:{COLORS['muted']}; background:transparent; border:none;"
        )
        self.value.setStyleSheet(
            f"color:{COLORS['text']}; font-weight:700;"
            " background:transparent; border:none;"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Runtime status — one compact card per reading
# ─────────────────────────────────────────────────────────────────────────────

class StatCard(QFrame):
    """``label`` over a prominent ``value`` over a muted ``detail``.

    Uses the style the runtime tiles have always used, so this block and the
    legacy card it replaces cannot drift into two different looks.
    """

    def __init__(self, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("runtimeStatCard", True)
        self.setProperty("compactRuntimeStatCard", True)
        # A wrapped detail line does not reach the parent grid through
        # sizeHint, so the card has to reserve the two lines the longest
        # reading needs; without it "Detection reference" lost its last word.
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding
        )
        self.setMinimumHeight(78)
        box = QVBoxLayout(self)
        box.setContentsMargins(10, 8, 10, 9)
        box.setSpacing(1)
        self.label = QLabel(tr(label))
        self.label.setWordWrap(True)
        self.label.setProperty("runtimeStatLabel", True)
        self.value = QLabel("--")
        self.value.setWordWrap(True)
        self.value.setProperty("runtimeStatValue", True)
        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.detail.setProperty("runtimeStatDetail", True)
        for widget in (self.label, self.value, self.detail):
            box.addWidget(widget)

    def set_values(self, value: str, detail: str = "") -> None:
        self.value.setText(value or "--")
        self.detail.setText(detail)

    def set_label(self, label: str) -> None:
        self.label.setText(tr(label))


# ─────────────────────────────────────────────────────────────────────────────
# Per-core monitor
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Responsive grid — shared by the sensor tiles and the runtime block
# ─────────────────────────────────────────────────────────────────────────────

class ResponsiveGrid(QWidget):
    """Equal-width children that pick their column count from their width."""

    def __init__(
        self,
        widgets,
        *,
        minimum: int = 150,
        columns: int = 3,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._widgets = list(widgets)
        self._minimum = int(minimum)
        self._maximum_columns = int(columns)
        self._columns = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(10)
        self._grid.setVerticalSpacing(10)
        self._apply_columns(self._maximum_columns)

    def _apply_columns(self, columns: int) -> None:
        columns = max(1, min(self._maximum_columns, int(columns)))
        if columns == self._columns:
            return
        self._columns = columns
        for widget in self._widgets:
            self._grid.removeWidget(widget)
        for index, widget in enumerate(self._widgets):
            self._grid.addWidget(widget, index // columns, index % columns)
        for column in range(self._maximum_columns):
            self._grid.setColumnStretch(column, 1 if column < columns else 0)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().resizeEvent(event)
        spacing = self._grid.horizontalSpacing()
        self._apply_columns((self.width() + spacing) // (self._minimum + spacing))



class ToggleRow(QFrame):
    """One switch: the control on the left, what it does next to it.

    The same shape as :class:`ValueField`, so an option and a number read as
    the same kind of row instead of a stray checkbox above a framed field. An
    optional trailing widget (e.g. a value field the switch unlocks) can sit
    at the far right of the same row.
    """

    def __init__(
        self,
        label: str,
        hint: QLabel,
        control: QCheckBox,
        trailing: QWidget | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setProperty("subPanel", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row = QHBoxLayout(self)
        row.setContentsMargins(13, 10, 13, 10)
        row.setSpacing(10)

        row.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)

        text = QVBoxLayout()
        text.setSpacing(2)
        title = QLabel(tr(label))
        title.setProperty("fieldLabel", True)
        title.setWordWrap(True)
        text.addWidget(title)
        text.addWidget(hint)
        row.addLayout(text, 1)

        if trailing is not None:
            row.addWidget(trailing, 0, Qt.AlignmentFlag.AlignVCenter)


# ─────────────────────────────────────────────────────────────────────────────
# Profile card — click selects, pencil edits
# ─────────────────────────────────────────────────────────────────────────────

class CpuProfileCard(QFrame):
    """A click selects the profile; the pencil edits its name and values."""

    selected = pyqtSignal(object)   # CpuProfile
    changed = pyqtSignal(object)    # CpuProfile

    def __init__(self, profile: CpuProfile, parent: QWidget | None = None):
        super().__init__(parent)
        self._profile = profile
        self._default = replace(profile)
        self.setProperty("profileCard", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        root = QVBoxLayout(self)
        root.setContentsMargins(11, 10, 11, 11)
        root.setSpacing(0)

        # ── view ────────────────────────────────────────────────────────────
        self._view = QWidget()
        view = QVBoxLayout(self._view)
        view.setContentsMargins(0, 0, 0, 0)
        view.setSpacing(5)

        head = QHBoxLayout()
        head.setSpacing(6)
        self._name_label = QLabel(tr(profile.name))
        self._name_label.setProperty("profileTitle", True)
        self._name_label.setMinimumWidth(0)
        head.addWidget(self._name_label, 1)
        self._active_pill = PillLabel(tr("Active"), "blue")
        self._active_pill.setVisible(False)
        head.addWidget(self._active_pill, 0)
        self._edit_button = QPushButton()
        self._edit_button.setIcon(icon("edit_gray"))
        self._edit_button.setFixedSize(24, 24)
        self._edit_button.setToolTip(tr("Edit profile"))
        self._edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_button.setProperty("iconOnlyButton", True)
        self._edit_button.clicked.connect(self.begin_edit)
        head.addWidget(self._edit_button, 0)
        view.addLayout(head)

        self._value_label = QLabel(profile.summary())
        self._value_label.setProperty("rangeReadout", True)
        view.addWidget(self._value_label)

        self._detail_label = caption("")
        view.addWidget(self._detail_label)
        root.addWidget(self._view)

        # ── editor ──────────────────────────────────────────────────────────
        self._editor = QWidget()
        editor = QVBoxLayout(self._editor)
        editor.setContentsMargins(0, 0, 0, 0)
        editor.setSpacing(8)

        editor_head = QHBoxLayout()
        eyebrow = QLabel(tr("EDITING PROFILE"))
        eyebrow.setProperty("eyebrow", True)
        editor_head.addWidget(eyebrow, 1)
        reset = QPushButton(tr("Reset"))
        reset.setProperty("linkButton", True)
        reset.setProperty("quiet", True)
        reset.setCursor(Qt.CursorShape.PointingHandCursor)
        reset.clicked.connect(self._restore_default)
        editor_head.addWidget(reset, 0)
        editor.addLayout(editor_head)

        self._name_edit = QLineEdit(profile.name)
        self._name_edit.setPlaceholderText(tr("Profile name"))
        self._name_edit.setMaxLength(28)
        editor.addWidget(self._name_edit)

        spins = QGridLayout()
        spins.setContentsMargins(0, 0, 0, 0)
        spins.setHorizontalSpacing(8)
        spins.setVerticalSpacing(7)
        self._frequency_spin = self._build_spin(
            *CPU_FREQUENCY_RANGE, CPU_FREQUENCY_STEP_MHZ, profile.frequency_mhz
        )
        self._vid_spin = self._build_spin(
            *CPU_VID_RANGE, CPU_VID_STEP_MV, profile.vid_mv
        )
        self._temperature_spin = self._build_spin(
            *CPU_TEMPERATURE_RANGE, 1, profile.temperature_c
        )
        spins.addWidget(self._labelled(tr("CPU frequency"), self._frequency_spin), 0, 0)
        spins.addWidget(self._labelled(tr("VID limit"), self._vid_spin), 0, 1)
        spins.addWidget(
            self._labelled(tr("Temperature cap"), self._temperature_spin), 1, 0, 1, 2
        )
        spins.setColumnStretch(0, 1)
        spins.setColumnStretch(1, 1)
        editor.addLayout(spins)

        self._hint = caption("")
        self._refresh_hint()
        editor.addWidget(self._hint)

        save = QPushButton(tr("Save profile"))
        save.setProperty("cardAction", True)
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.clicked.connect(self._commit)
        editor.addWidget(save)

        self._editor.setVisible(False)
        root.addWidget(self._editor)
        self._sync_view()

    # -- construction ---------------------------------------------------------
    @staticmethod
    def _build_spin(minimum: int, maximum: int, step: int, value: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setValue(value)
        spin.setMinimumWidth(70)
        return spin

    @staticmethod
    def _labelled(text: str, control: QWidget) -> QWidget:
        host = QWidget()
        box = QVBoxLayout(host)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(3)
        label = QLabel(text)
        label.setProperty("fieldLabel", True)
        box.addWidget(label)
        box.addWidget(control)
        return host

    # -- API ------------------------------------------------------------------
    @property
    def profile(self) -> CpuProfile:
        return self._profile

    def set_profile(self, profile: CpuProfile) -> None:
        """Loads a profile already saved by the user (settings override)."""
        self._profile = profile
        self._sync_view()

    def set_active(self, active: bool) -> None:
        self._active_pill.setVisible(active)
        self.setProperty("selectedProfile", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def begin_edit(self) -> None:
        self._name_edit.setText(self._profile.name)
        self._frequency_spin.setValue(self._profile.frequency_mhz)
        self._vid_spin.setValue(self._profile.vid_mv)
        self._temperature_spin.setValue(self._profile.temperature_c)
        self._refresh_hint()
        self._view.setVisible(False)
        self._editor.setVisible(True)
        self._name_edit.setFocus()
        self._name_edit.selectAll()

    def cancel_edit(self) -> None:
        self._editor.setVisible(False)
        self._view.setVisible(True)

    def retranslate(self) -> None:
        """Rebuilds the interpolated hint after a live language change."""
        self._refresh_hint()
        self._sync_view()

    # -- internal -------------------------------------------------------------
    def _restore_default(self) -> None:
        self._name_edit.setText(self._default.name)
        self._frequency_spin.setValue(self._default.frequency_mhz)
        self._vid_spin.setValue(self._default.vid_mv)
        self._temperature_spin.setValue(self._default.temperature_c)

    def _refresh_hint(self) -> None:
        self._hint.setText(
            tr_format(
                "Enter a value between {minimum} and {maximum} MHz.",
                minimum=CPU_FREQUENCY_RANGE[0],
                maximum=CPU_FREQUENCY_RANGE[1],
            )
        )

    def _commit(self) -> None:
        name = self._name_edit.text().strip() or self._default.name
        self._profile = replace(
            self._profile,
            name=name,
            frequency_mhz=self._frequency_spin.value(),
            vid_mv=self._vid_spin.value(),
            temperature_c=self._temperature_spin.value(),
        )
        self.cancel_edit()
        self._sync_view()
        self.changed.emit(self._profile)

    def _sync_view(self) -> None:
        profile = self._profile
        self._name_label.setText(tr(profile.name))
        self._value_label.setText(profile.summary())
        self._detail_label.setText(profile.detail())

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().mouseReleaseEvent(event)
        if self._editor.isVisible():
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self._profile)


# ─────────────────────────────────────────────────────────────────────────────
# The module
# ─────────────────────────────────────────────────────────────────────────────

class CpuControlView(QWidget):
    """Unified CPU workspace — presentation only.

    Signals towards the backend::

        apply_requested(object CpuTuningRequest)
        profile_changed(object CpuProfile)
        persistence_requested(str)     # 'save' | 'remove' | 'review'
        unlock_cores_requested()
        firmware_persistence_requested()

    Inputs::

        apply_state(CpuControlState)
        set_profiles(profiles)
    """

    apply_requested = pyqtSignal(object)
    profile_changed = pyqtSignal(object)
    persistence_requested = pyqtSignal(str)
    unlock_cores_requested = pyqtSignal()
    firmware_persistence_requested = pyqtSignal()
    export_to_decky_requested = pyqtSignal()

    IDENTITY_ROWS = (
        ("model", "Processor"),
        ("architecture", "Architecture"),
        ("topology", "Topology"),
        ("platform", "Platform / process"),
        ("microcode", "Microcode"),
        ("cache", "Cache hierarchy"),
        ("features", "Instruction features"),
        ("load", "Total CPU load"),
    )

    #: The runtime block, in the order it is read.
    RUNTIME_ROWS = (
        ("persistence", "Boot persistence"),
        ("last_operation", "Last operation"),
        ("applied", "Applied tuning"),
        ("detection", "Detection reference"),
        ("scale", "Active scale"),
        ("live", "Live CPU status"),
    )

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        # Opts into the shared redesigned-module stylesheet block.
        self.setProperty("redesignedModule", True)
        self.setProperty("cpuControlPage", True)
        self._state = CpuControlState()
        self._selected_profile_key = DEFAULT_CPU_PROFILES[0].key
        # A refresh must never move a profile the user just picked. Selection
        # re-syncs with the hardware when the screen is entered again, not on
        # every four-second poll.
        self._follow_hardware = True

        # No scroll area of its own: the page that hosts this view already
        # scrolls, and nesting a second one both doubled the page padding and
        # reserved a scrollbar gutter on the right, so the screen sat 34 px
        # from the left edge and 43 px from the right. The host's margins are
        # the only ones now, which is what the GPU workspace does too.
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self._workspace = QGridLayout()
        self._workspace.setContentsMargins(0, 0, 0, 0)
        self._workspace.setHorizontalSpacing(12)
        self._workspace.setVerticalSpacing(12)
        layout.addLayout(self._workspace)

        self._configuration = self._build_configuration_card()
        self._telemetry = self._build_telemetry_card()

        # The identity table belongs under the controls, not across the foot of
        # the page: it gives the configuration column real content to end with,
        # so both columns finish on the same line.
        self._left_column = QWidget()
        left = QVBoxLayout(self._left_column)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(12)
        left.addWidget(self._configuration, 0)
        self._console_card = self._build_console_card()
        left.addWidget(self._console_card, 0)
        self._left_spacer = QSpacerItem(
            0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding
        )
        left.addItem(self._left_spacer)
        self._left_column_box = left

        self._workspace.addWidget(self._left_column, 0, 0)
        self._workspace.addWidget(self._telemetry, 0, 1)
        # The same 18:12 split the GPU workspace uses, so the two hardware
        # screens read as one family: controls lead, monitoring reports.
        self._workspace.setColumnStretch(0, 18)
        self._workspace.setColumnStretch(1, 12)

        layout.addStretch(1)
        self.apply_state(self._state)

    # ── CPU configuration ──────────────────────────────────────────────────
    def _build_configuration_card(self) -> SectionCard:
        card = SectionCard(
            "CPU configuration",
            "Choose a preset or enter the CPU frequency, VID limit, and "
            "temperature cap you want to test.",
            icon_name="cpu_blue",
            icon_background=COLORS["blue_soft"],
            status=("Temporary", "green"),
        )
        # The card title only repeated the page title, and its subtitle
        # repeated the panel headings underneath. The pill is the part that
        # carried information, so it moves next to the runtime readings.
        self._configuration_status = card.drop_header()

        profiles_panel, profiles_box = subpanel("")
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        profiles_title = QLabel(tr("Operating profile"))
        profiles_title.setProperty("cardTitle", True)
        profiles_title.setWordWrap(True)
        title_row.addWidget(profiles_title, 0)
        title_row.addStretch(1)
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

        self._profile_cards: list[CpuProfileCard] = []
        for column, profile in enumerate(DEFAULT_CPU_PROFILES):
            profile_card = CpuProfileCard(replace(profile))
            profile_card.selected.connect(self._on_profile_selected)
            profile_card.changed.connect(self._on_profile_changed)
            self._profiles_grid.addWidget(profile_card, 0, column)
            self._profiles_grid.setColumnStretch(column, 1)
            self._profile_cards.append(profile_card)
        card.body.addWidget(profiles_panel)

        # The heading stays; its old subtitle does not. That sentence now works
        # as the legend of the switch it describes, which is one row saved.
        mode_panel, mode_box = subpanel("Live scale test")
        self.manual_scale_check = QCheckBox()
        self.manual_scale_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.manual_scale_check.setEnabled(False)
        self.manual_scale_check.toggled.connect(self._on_manual_scale_toggled)

        self.scale_field = QSpinBox()
        self.scale_field.setRange(*CPU_SCALE_RANGE)
        self.scale_field.setSingleStep(1)
        self.scale_field.setValue(-34)
        self.scale_field.setSuffix(" scale")
        self.scale_field.setMinimumWidth(104)
        self.scale_field.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.scale_field.setEnabled(False)
        self.scale_field.valueChanged.connect(self._on_scale_field_changed)

        mode_box.addWidget(
            ToggleRow(
                "Use manual scale",
                caption(
                    "Detect a scale automatically first. Then, only if you "
                    "want, compare another manual scale live."
                ),
                self.manual_scale_check,
                trailing=self.scale_field,
            )
        )

        # Shown only while the field is locked; once manual scale is available
        # the switch above already says what it is for.
        self._scale_lock = caption(
            "Apply an automatic live configuration first to unlock manual scale."
        )
        mode_box.addWidget(self._scale_lock)
        card.body.addWidget(mode_panel)

        self.apply_button = QPushButton(tr("Apply configuration + automatic scale"))
        self.apply_button.setObjectName("PrimaryAction")
        self.apply_button.setProperty("primaryAction", True)
        self.apply_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_button.clicked.connect(self._request_apply)
        card.body.addWidget(self.apply_button)
        return card

    def _build_persistence_panel(self) -> QFrame:
        """Boot persistence, under the readings that say what is persisted."""
        persistence_panel, persistence_box = subpanel("Boot persistence")
        persistence_actions = QGridLayout()
        persistence_actions.setContentsMargins(0, 0, 0, 0)
        persistence_actions.setHorizontalSpacing(8)
        persistence_actions.setVerticalSpacing(8)
        self.review_persistence_button = QPushButton(tr("Review persistence"))
        self.review_persistence_button.setProperty("ghostButton", True)
        self.review_persistence_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.review_persistence_button.clicked.connect(
            lambda: self.persistence_requested.emit("review")
        )
        self.save_boot_button = QPushButton(tr("Save for boot"))
        self.save_boot_button.setProperty("accentAction", True)
        self.save_boot_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_boot_button.clicked.connect(
            lambda: self.persistence_requested.emit("save")
        )
        self.remove_boot_button = QPushButton(tr("Remove from boot"))
        self.remove_boot_button.setProperty("dangerAction", True)
        self.remove_boot_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove_boot_button.setEnabled(False)
        self.remove_boot_button.clicked.connect(
            lambda: self.persistence_requested.emit("remove")
        )
        # Saving is the action this panel exists for, so it leads; reviewing
        # sits between the two writes it reports on.
        for column, button in enumerate((
            self.save_boot_button,
            self.review_persistence_button,
            self.remove_boot_button,
        )):
            persistence_actions.addWidget(button, 0, column)
            persistence_actions.setColumnStretch(column, 1)
        persistence_box.addLayout(persistence_actions)
        return persistence_panel

    def _build_console_card(self) -> SectionCard:
        """Session console, with processor identity underneath in the same card.

        The page has always had this console; the redesign left it behind in
        the hidden legacy screen. It is the same widget, adopted rather than
        rebuilt, so every line the page already writes lands here. Processor
        identity used to sit in its own bordered box right below; now it
        shares this one, so the column reads as a single block instead of
        two stacked boxes.
        """
        card = SectionCard("Session console", compact=True)
        card.drop_header()
        card.root.setContentsMargins(14, 14, 14, 14)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # The console draws its own frame, so no panel wraps it: three nested
        # borders around one text area is all border and no room.
        self._console_box = card.body

        identity_heading = QLabel(tr("Processor overview"))
        identity_heading.setProperty("cardTitle", True)
        identity_heading.setWordWrap(True)
        card.body.addSpacing(2)
        card.body.addWidget(identity_heading)

        # Two columns instead of one long list: with eight rows, a single
        # column ran the panel far taller than the console above it needed.
        identity_columns = 2
        identity_grid = QGridLayout()
        identity_grid.setContentsMargins(0, 0, 0, 0)
        identity_grid.setHorizontalSpacing(16)
        identity_grid.setVerticalSpacing(0)
        for column in range(identity_columns):
            identity_grid.setColumnStretch(column, 1)

        self.identity_rows: dict[str, IdentityRow] = {}
        for position, (key, label) in enumerate(self.IDENTITY_ROWS):
            row = IdentityRow(label, card, compact=True)
            row.set_first(position < identity_columns)
            self.identity_rows[key] = row
            identity_grid.addWidget(row, position // identity_columns, position % identity_columns)
        card.body.addLayout(identity_grid)

        # Nothing to show until a host hands its console over: a standalone
        # view must not draw an empty black rectangle.
        card.setVisible(False)
        return card

    def mount_console(self, console: QWidget) -> None:
        """Adopt the host page's session console into this workspace."""
        console.setParent(None)
        console.setMinimumHeight(120)
        console.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Inserted ahead of the processor-identity rows already in this box,
        # so the console stays on top of them.
        self._console_box.insertWidget(0, console, 1)
        self._console_card.setVisible(True)
        # The console is what absorbs the leftover height now, so the spacer
        # that used to hold the two columns level steps aside.
        self._left_column_box.removeItem(self._left_spacer)
        self._left_column_box.setStretch(
            self._left_column_box.indexOf(self._console_card), 1
        )
        self._console_card.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

    # ── Live metrics ───────────────────────────────────────────────────────
    def _build_telemetry_card(self) -> SectionCard:
        card = SectionCard(
            "Live metrics",
            "",
            icon_name="metrics_blue",
            icon_background=COLORS["blue_soft"],
            status=("Live", "green"),
        )
        card.drop_header()

        # What the session is actually doing comes first. The six sensor tiles
        # that used to open this card duplicated the dashboard's own strip and
        # pushed the readings that decide whether a change can be saved below
        # the fold; "Live CPU status" carries the temperature and clock that
        # belonged to this page.
        runtime_panel, runtime_box = subpanel()
        runtime_head = QHBoxLayout()
        runtime_head.setSpacing(8)
        runtime_title = QLabel(tr("Runtime status"))
        runtime_title.setProperty("cardTitle", True)
        # Long translations of this heading have to wrap beside the pill; a
        # 360 px Polish window is where it first refuses to.
        runtime_title.setWordWrap(True)
        runtime_title.setMinimumWidth(0)
        runtime_head.addWidget(runtime_title, 1)
        if self._configuration_status is not None:
            runtime_head.addWidget(
                self._configuration_status, 0, Qt.AlignmentFlag.AlignVCenter
            )
        runtime_box.addLayout(runtime_head)
        runtime_box.addWidget(
            caption(
                "What will be used for this session and what will happen at "
                "the next boot."
            )
        )
        self.runtime_cards: dict[str, StatCard] = {
            key: StatCard(label) for key, label in self.RUNTIME_ROWS
        }
        runtime_box.addWidget(
            ResponsiveGrid(self.runtime_cards.values(), minimum=160, columns=3)
        )
        card.body.addWidget(runtime_panel)

        cores_panel, cores_box = subpanel("Live core monitor")
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(caption("Detected by the OS"), 1)
        self._core_shape = QLabel("--")
        self._core_shape.setProperty("rangeReadout", True)
        head.addWidget(self._core_shape, 0, Qt.AlignmentFlag.AlignRight)
        cores_box.addLayout(head)
        self.core_grid = CoreGrid()
        cores_box.addWidget(self.core_grid)
        card.body.addWidget(cores_panel)
        card.body.addWidget(self._build_persistence_panel())


        # ── danger zone ────────────────────────────────────────────────────
        risk_panel, risk_box = subpanel("")
        self._risk_panel = risk_panel
        risk_panel.setProperty("riskPanel", True)
        # Tighter than the default subpanel: this box was leaving visible air
        # between its own text and buttons instead of using it as margin.
        risk_box.setContentsMargins(14, 10, 14, 10)
        risk_box.setSpacing(5)
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
        risk_box.addLayout(risk_head)

        risk_title = QLabel(tr("Unlock hidden CPU cores"))
        risk_title.setProperty("panelHeadline", True)
        risk_title.setWordWrap(True)
        risk_box.addWidget(risk_title)
        risk_box.addWidget(
            caption(
                "Experimental, restart-required action for supported BC-250 boards."
            )
        )

        # The detected shape, the upstream tool and the governor line all
        # repeated something already on screen: the core monitor above says
        # the shape, and the button's own state says whether the workflow can
        # run. Only the gate that decides that is kept.
        self.unlock_support_row = IdentityRow("Unlock support", risk_panel, compact=True)
        self.unlock_support_row.set_first(True)
        risk_box.addWidget(self.unlock_support_row)

        self.firmware_button = QPushButton(tr("Firmware persistence guide"))
        self.firmware_button.setProperty("linkButton", True)
        self.firmware_button.setProperty("flushLeft", True)
        self.firmware_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.firmware_button.clicked.connect(self.firmware_persistence_requested)
        risk_box.addWidget(self.firmware_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.unlock_button = QPushButton(tr("Unlock cores and restart"))
        self.unlock_button.setProperty("dangerAction", True)
        self.unlock_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.unlock_button.setEnabled(False)
        self.unlock_button.clicked.connect(self.unlock_cores_requested)
        risk_box.addWidget(self.unlock_button)

        # The GPU module leaves more air above its danger zone than between the
        # neutral panels, so it reads as a separate class of control. The
        # stretch has to stay *after* the panel: without any stretch here,
        # this card's leftover height (it matches the taller left column)
        # spread into the widgets above instead, inflating the runtime tiles.
        # Keeping the stretch below the panel absorbs that space where it is
        # invisible, while the panel itself sits right after boot persistence
        # with no gap in between.
        card.body.addSpacing(10)
        card.body.addWidget(risk_panel)
        card.body.addStretch(1)
        return card

    # ── interaction ────────────────────────────────────────────────────────
    def _on_profile_selected(self, profile: CpuProfile) -> None:
        self._follow_hardware = False
        self._selected_profile_key = profile.key
        self._sync_selection()

    def _on_profile_changed(self, profile: CpuProfile) -> None:
        self.profile_changed.emit(profile)
        # Editing a profile is also a way of choosing it: the numbers the user
        # just typed are the ones Apply should send.
        self._follow_hardware = False
        self._selected_profile_key = profile.key
        self._sync_selection()

    def _on_scale_field_changed(self, _value: int) -> None:
        # Only user input reaches here: the periodic hardware sync in
        # _apply_tuning() wraps its own setValue() in blockSignals(). Without
        # this, the next refresh tick (every few seconds) overwrote whatever
        # scale the user had just picked, making the field feel unresponsive.
        self._follow_hardware = False

    def _on_manual_scale_toggled(self, checked: bool) -> None:
        self.scale_field.setEnabled(bool(checked))
        if checked:
            self.apply_button.setText(tr("Apply temporary OC + manual scale"))
        else:
            self.apply_button.setText(tr("Apply configuration + automatic scale"))

    def _request_apply(self) -> None:
        """The page owns the confirmation dialogs; this only states intent."""
        self.apply_requested.emit(self.staged_request())

    # ── backend inputs ─────────────────────────────────────────────────────
    def selected_profile(self) -> CpuProfile:
        for profile_card in self._profile_cards:
            if profile_card.profile.key == self._selected_profile_key:
                return profile_card.profile
        return self._profile_cards[0].profile

    def staged_request(self) -> CpuTuningRequest:
        profile = self.selected_profile()
        return CpuTuningRequest(
            frequency_mhz=profile.frequency_mhz,
            vid_mv=profile.vid_mv,
            temperature_c=profile.temperature_c,
            manual_scale=self.manual_scale_check.isChecked(),
            scale=self.scale_field.value(),
        )

    def set_profiles(self, profiles: Sequence[CpuProfile]) -> None:
        """Applies profiles saved by the user, in order."""
        for profile_card, profile in zip(self._profile_cards, profiles):
            profile_card.set_profile(profile)
        self._sync_selection()

    def profiles(self) -> tuple[CpuProfile, ...]:
        return tuple(card.profile for card in self._profile_cards)

    def follow_hardware_again(self) -> None:
        self._follow_hardware = True

    def reveal_danger_zone(self) -> None:
        """Bring the hidden-core controls into view.

        The dashboard's "Unlock cores" shortcut used to open a tab that showed
        nothing else. On one screen it has to say where it landed, or it reads
        as a button that did not work.
        """
        scroll = self._host_scroll()
        if scroll is not None:
            scroll.ensureWidgetVisible(self._risk_panel, 0, 24)

    def _host_scroll(self) -> QScrollArea | None:
        """The scroll area this view was mounted into, if any."""
        parent = self.parentWidget()
        while parent is not None:
            if isinstance(parent, QScrollArea):
                return parent
            parent = parent.parentWidget()
        return None

    def scroll_to_top(self) -> None:
        """Return to the configuration half of the screen."""
        scroll = self._host_scroll()
        if scroll is not None:
            scroll.verticalScrollBar().setValue(0)

    def apply_state(self, state: CpuControlState) -> None:
        self._state = state
        self._apply_identity(state)
        self._apply_cores(state)
        self._apply_tuning(state.tuning)
        self._apply_unlock(state.core_unlock)
        self._sync_selection()

    # ── state application ──────────────────────────────────────────────────
    def _apply_identity(self, state: CpuControlState) -> None:
        rows = self.identity_rows
        rows["model"].set_value(state.model_name or tr("Not detected"))
        rows["architecture"].set_value(state.architecture or tr("Not exposed"))
        rows["topology"].set_value(state.topology or tr("Not detected"))
        rows["platform"].set_value(state.platform_process or tr("Not exposed"))
        rows["microcode"].set_value(state.microcode or tr("Not exposed"))
        rows["cache"].set_value(state.cache or tr("Not exposed"))
        rows["features"].set_value(state.features or tr("Not exposed"))
        rows["load"].set_value(f"{state.total_usage_percent:.0f} %")

    def _apply_cores(self, state: CpuControlState) -> None:
        self.core_grid.set_readings(state.cores)
        # ``topology`` arrives from the backend already formatted in English;
        # the shape the unlock workflow composes is the translated one.
        self._core_shape.setText(
            state.core_unlock.detected_shape or state.topology or tr("Not detected")
        )

    def _apply_tuning(self, tuning: CpuTuningState) -> None:
        for key, _label in self.RUNTIME_ROWS:
            reading = tuning.runtime.get(key) or RuntimeReading()
            self.runtime_cards[key].set_values(reading.value, reading.detail)

        if tuning.scale is not None and self._follow_hardware:
            blocked = self.scale_field.blockSignals(True)
            try:
                self.scale_field.setValue(int(tuning.scale))
            finally:
                self.scale_field.blockSignals(blocked)
        if self._follow_hardware and tuning.frequency_mhz:
            self._select_profile_matching(
                tuning.frequency_mhz, tuning.vid_mv, tuning.temperature_c
            )

        available = bool(tuning.manual_scale_available)
        self._scale_lock.setVisible(not available)
        if self.manual_scale_check.isEnabled() != available:
            self.manual_scale_check.setEnabled(available)
        if not available and self.manual_scale_check.isChecked():
            self.manual_scale_check.setChecked(False)
        self.manual_scale_check.setToolTip(
            tr(
                "Automatic live configuration verified. You can now test an "
                "exact manual scale for this session."
            )
            if available
            else tr(
                "Run a verified automatic live configuration first. Manual "
                "scale unlocks only for that detection session."
            )
        )

        self.apply_button.setEnabled(not tuning.applying)
        self.save_boot_button.setEnabled(not tuning.applying)
        self.review_persistence_button.setEnabled(not tuning.applying)
        self.remove_boot_button.setEnabled(
            bool(tuning.persistence_enabled) and not tuning.applying
        )
        if self._configuration_status is not None:
            if tuning.applying:
                self._configuration_status.setText(tr("Checking"))
                self._configuration_status.set_tone("orange")
            elif tuning.persistence_enabled:
                self._configuration_status.setText(tr("Persistence"))
                self._configuration_status.set_tone("blue")
            else:
                self._configuration_status.setText(tr("Temporary"))
                self._configuration_status.set_tone("green")

    def _apply_unlock(self, unlock: CoreUnlockState) -> None:
        self.unlock_support_row.set_value(
            tr("Ready") if unlock.helper_ready else tr("Not installed")
        )
        self.unlock_button.setEnabled(bool(unlock.unlock_allowed))

    def _select_profile_matching(
        self, frequency: int, vid: int, temperature: int
    ) -> None:
        for profile_card in self._profile_cards:
            if profile_card.profile.values() == (frequency, vid, temperature):
                self._selected_profile_key = profile_card.profile.key
                return

    def _sync_selection(self) -> None:
        keys = [card.profile.key for card in self._profile_cards]
        if self._selected_profile_key not in keys and keys:
            self._selected_profile_key = keys[0]
        for profile_card in self._profile_cards:
            profile_card.set_active(
                profile_card.profile.key == self._selected_profile_key
            )

    def retranslate_dynamic_copy(self) -> None:
        """Re-render the copy ``localize_widget_tree`` cannot recover itself."""
        for key, label in self.IDENTITY_ROWS:
            self.identity_rows[key].set_label(label)
        for key, label in self.RUNTIME_ROWS:
            self.runtime_cards[key].set_label(label)
        self.unlock_support_row.set_label("Unlock support")
        for profile_card in self._profile_cards:
            profile_card.retranslate()
        self._apply_unlock(self._state.core_unlock)

    # ── lifecycle ──────────────────────────────────────────────────────────
    def showEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().showEvent(event)
        # Coming back to the screen is the moment to trust the hardware again.
        self._follow_hardware = True
        self._apply_tuning(self._state.tuning)
        self._sync_selection()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().resizeEvent(event)
        self._reflow(self.width())

    def _reflow(self, width: int) -> None:
        stacked = width < STACK_WIDTH
        telemetry_stacked = self._workspace.itemAtPosition(1, 0) is not None
        if stacked and not telemetry_stacked:
            self._workspace.removeWidget(self._telemetry)
            self._workspace.addWidget(self._telemetry, 1, 0)
            self._workspace.setColumnStretch(1, 0)
        elif not stacked and telemetry_stacked:
            self._workspace.removeWidget(self._telemetry)
            self._workspace.addWidget(self._telemetry, 0, 1)
            self._workspace.setColumnStretch(1, 1)

        columns = 1 if width < PROFILE_STACK_WIDTH else 3
        current = 1 if self._profiles_grid.itemAtPosition(1, 0) is not None else 3
        if columns != current:
            for index, profile_card in enumerate(self._profile_cards):
                self._profiles_grid.removeWidget(profile_card)
                row, column = (index, 0) if columns == 1 else (0, index)
                self._profiles_grid.addWidget(profile_card, row, column)
