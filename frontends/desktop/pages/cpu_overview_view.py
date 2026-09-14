"""Redesigned CPU module — presentation layer (PyQt6).

Destination: ``frontends/desktop/pages/cpu_overview_view.py``

Rebuilds the CPU page's *Overview and live monitoring* workspace in the same
visual language as the redesigned Cyan GPU module, with the hierarchy:

    ┌ Processor ──────────────────┐ ┌ Hidden CPU cores ─────────┐
    │ identity, two dense columns │ │ readiness + one action    │
    └─────────────────────────────┘ └───────────────────────────┘
    ┌ Live metrics ────────────────────────────────────────────┐
    │ 6 read-only tiles, then the eight-slot core strip        │
    └──────────────────────────────────────────────────────────┘

The GDDR6 memory readings are *not* here. They belong to the board rather
than to the processor, and live monitoring is driven from the dashboard's own
strip; this page only mirrors the average in one telemetry tile.

Does not talk to the controller, Polkit or the SMU: it exposes signals and
receives a :class:`CpuOverviewState`. The wiring lives in
``cpu_overview_integration.py``.

Every row is built once and told what it is, never rebuilt per refresh —
``tests/desktop/architecture/test_refreshes_update_instead_of_rebuild.py``
fixes that for this module too.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ..components.buttons import WrappingButton as QPushButton
from ..components.dashboard_widgets import DashboardCoreSummary
from ..components.page_widgets import MetricTile, SectionCard, subpanel
from ..components.widgets import icon

# One definition of the GDDR6 reading, owned by the engine that produces it.
# Re-exported under the name this module has always used.
from ..core.gddr6_monitor import Gddr6Reading as Gddr6State
from ..i18n import tr, tr_format
from ..theme import COLORS

#: The BC-250 carries eight GDDR6 devices and exposes eight physical cores;
#: both rails are fixed-size, so their rows can be built once.
CHIP_COUNT = 8
CORE_COUNT = 8


def _temperature_text(value: float | None) -> str:
    return "--" if value is None else f"{value:.1f} °C"


# ─────────────────────────────────────────────────────────────────────────────
# State — everything the view draws, and nothing it fetches
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CoreReading:
    index: int
    frequency_mhz: float = 0.0
    usage_percent: float = 0.0
    threads: str = ""
    online: bool = False


@dataclass(frozen=True)
class CoreUnlockState:
    detected_shape: str = ""
    source_ready: bool = False
    helper_ready: bool = False
    governor_state: str = ""
    unlock_allowed: bool = False
    unlocked: bool = False


@dataclass(frozen=True)
class CpuOverviewState:
    model_name: str = ""
    architecture: str = ""
    vendor: str = ""
    platform_process: str = ""
    microcode: str = ""
    topology: str = ""
    cache: str = ""
    features: str = ""
    total_usage_percent: float = 0.0

    frequency_text: str = "--"
    voltage_text: str = "--"
    temperature_text: str = "--"
    power_text: str = "--"
    power_label: str = "SoC package power"
    power_detail: str = ""
    vrm_temperature_c: float | None = None

    cores: tuple[CoreReading, ...] = ()
    core_unlock: CoreUnlockState = field(default_factory=CoreUnlockState)
    gddr6: Gddr6State = field(default_factory=Gddr6State)


# ─────────────────────────────────────────────────────────────────────────────
# Identity rows — label left, value right, hairline between
# ─────────────────────────────────────────────────────────────────────────────

class _IdentityRow(QFrame):
    """One ``label ......... value`` line of the processor panel."""

    def __init__(self, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._first = False
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 7, 0, 7)
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
# Tile grid — same column behaviour as the GPU module's telemetry block
# ─────────────────────────────────────────────────────────────────────────────

class TileGrid(QWidget):
    """Metric tiles that pick their column count from the width they are given."""

    MINIMUM_TILE = 150
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
# The module
# ─────────────────────────────────────────────────────────────────────────────

class CpuOverviewView(QWidget):
    """Presentation only: emits intent, receives :class:`CpuOverviewState`."""

    unlock_cores_requested = pyqtSignal()
    firmware_persistence_requested = pyqtSignal()

    IDENTITY_ROWS = (
        ("model", "Processor"),
        ("topology", "Topology"),
        ("platform", "Platform / process"),
        ("microcode", "Microcode"),
        ("cache", "Cache hierarchy"),
        ("features", "Instruction features"),
        ("load", "Total CPU load"),
    )

    #: Kept in step with ``cpu_overview_integration.LIVE_INTERVAL_MS`` so the
    #: cadence the panel advertises is the one it actually uses.
    live_interval_seconds = 5

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        self.top_row = QGridLayout()
        self.top_row.setContentsMargins(0, 0, 0, 0)
        self.top_row.setHorizontalSpacing(14)
        self.top_row.setVerticalSpacing(14)
        self.processor_card = self._build_processor_card()
        self.unlock_card = self._build_unlock_card()
        self.top_row.addWidget(self.processor_card, 0, 0)
        self.top_row.addWidget(self.unlock_card, 0, 1)
        self.top_row.setColumnStretch(0, 1)
        self.top_row.setColumnStretch(1, 1)
        root.addLayout(self.top_row)

        root.addWidget(self._build_telemetry_card())
        root.addStretch(1)

    # ------------------------------------------------------------ construction

    def _build_processor_card(self) -> SectionCard:
        card = SectionCard(
            "Processor overview",
            "CPU-Z-style identification read directly from Linux kernel interfaces, without changing hardware state.",
            icon_name="cpu_blue",
            icon_background=COLORS["blue_soft"],
            status=("Live", "green"),
        )
        panel, box = subpanel()
        box.setContentsMargins(14, 4, 14, 6)
        box.setSpacing(0)
        self.identity_rows: dict[str, _IdentityRow] = {}
        for position, (key, label) in enumerate(self.IDENTITY_ROWS):
            row = _IdentityRow(label, panel)
            row.set_first(position == 0)
            self.identity_rows[key] = row
            box.addWidget(row)
        card.body.addWidget(panel)
        return card

    def _build_unlock_card(self) -> SectionCard:
        card = SectionCard(
            "Unlock hidden CPU cores",
            "Experimental, restart-required action for supported BC-250 boards.",
            icon_name="compute_blue",
            icon_background=COLORS["blue_soft"],
            status=("Checking", "gray"),
        )
        self.unlock_status_card = card

        panel, box = subpanel()
        box.setContentsMargins(14, 4, 14, 6)
        box.setSpacing(0)
        self.unlock_rows: dict[str, _IdentityRow] = {}
        for position, (key, label) in enumerate((
            ("shape", "Detected CPU"),
            ("source", "Upstream tool"),
            ("helper", "Unlock support"),
            ("governor", "Governor compatibility"),
        )):
            row = _IdentityRow(label, panel)
            row.set_first(position == 0)
            self.unlock_rows[key] = row
            box.addWidget(row)
        card.body.addWidget(panel)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(9)
        self.firmware_button = QPushButton(tr("Firmware persistence guide"))
        self.firmware_button.setProperty("compactAction", True)
        self.firmware_button.setIcon(icon("info_blue"))
        self.firmware_button.clicked.connect(self.firmware_persistence_requested)
        actions.addWidget(self.firmware_button, 1)
        self.unlock_button = QPushButton(tr("Unlock cores and restart"))
        self.unlock_button.setProperty("dangerAction", True)
        self.unlock_button.clicked.connect(self.unlock_cores_requested)
        actions.addWidget(self.unlock_button, 1)
        card.body.addLayout(actions)
        return card

    def _build_telemetry_card(self) -> SectionCard:
        card = SectionCard(
            "Live metrics",
            "",
            icon_name="metrics_blue",
            icon_background=COLORS["blue_soft"],
            status=("Passive", "green"),
            compact=True,
        )
        self.frequency_tile = MetricTile(
            "Average frequency", "--", "Kernel-reported average",
            icon_name="cpu_blue", icon_background=COLORS["blue_soft"], compact=True,
        )
        self.voltage_tile = MetricTile(
            "Voltage sensor", "--", "VDDNB / SMU telemetry",
            icon_name="bolt_blue", icon_background=COLORS["blue_soft"], compact=True,
        )
        self.temperature_tile = MetricTile(
            "Temperature", "--", "k10temp Tctl",
            icon_name="warning_orange", icon_background=COLORS["orange_soft"], compact=True,
        )
        self.power_tile = MetricTile(
            "SoC package power", "--", "AMDGPU hwmon sensor",
            icon_name="power_gray", icon_background="neutral_soft", compact=True,
        )
        self.vrm_tile = MetricTile(
            "VRM temperature", "--", "External telemetry daemon",
            icon_name="activity_purple", icon_background=COLORS["purple_soft"], compact=True,
        )
        self.memory_tile = MetricTile(
            "GDDR6 memory", "--", "Average across 8 chips",
            icon_name="memory_green", icon_background=COLORS["green_soft"], compact=True,
        )
        self.tiles = TileGrid((
            self.frequency_tile,
            self.voltage_tile,
            self.temperature_tile,
            self.power_tile,
            self.vrm_tile,
            self.memory_tile,
        ))
        card.body.addWidget(self.tiles)

        # The eight cores belong to the same reading as the six tiles above:
        # one card, one glance. A hairline separates the aggregate numbers
        # from the per-core detail without starting a second card for it.
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background:{COLORS['border_soft']}; border:none;")
        card.body.addSpacing(3)
        card.body.addWidget(divider)
        card.body.addSpacing(3)
        # The dashboard already owns this strip, and its styling lives in the
        # global theme rather than in the dashboard page, so reusing it keeps
        # both places reading the same way instead of inventing a second
        # vocabulary for the same eight cores.
        self.core_summary = DashboardCoreSummary()
        card.body.addWidget(self.core_summary)
        return card

    # ------------------------------------------------------------ interaction

    def apply_state(self, state: CpuOverviewState) -> None:
        self._apply_identity(state)
        self._apply_telemetry(state)
        self._apply_cores(state)
        self._apply_unlock(state.core_unlock)

    def _apply_identity(self, state: CpuOverviewState) -> None:
        rows = self.identity_rows
        rows["model"].set_value(state.model_name or tr("Not detected"))
        rows["topology"].set_value(state.topology or tr("Not detected"))
        rows["platform"].set_value(state.platform_process or tr("Not exposed"))
        rows["microcode"].set_value(state.microcode or tr("Not exposed"))
        rows["cache"].set_value(state.cache or tr("Not exposed"))
        rows["features"].set_value(state.features or tr("Not exposed"))
        rows["load"].set_value(f"{state.total_usage_percent:.0f} %")

    def _apply_cores(self, state: CpuOverviewState) -> None:
        """Feed the eight physical slots, online ones first.

        The strip decides for itself which trailing slots read as hidden: it
        marks every position past the last measured one, so passing only the
        cores the kernel exposes is what makes N7/N8 say so on a stock board.
        """
        online = sorted(
            (core for core in state.cores if core.online), key=lambda core: core.index
        )
        self.core_summary.set_core_count(CORE_COUNT)
        # ``topology`` arrives from the backend already formatted in English;
        # the shape composed for the unlock card is the translated one.
        self.core_summary.set_value(
            state.core_unlock.detected_shape or state.topology or tr("Not detected")
        )
        self.core_summary.set_core_metrics(
            [core.frequency_mhz for core in online],
            [core.usage_percent for core in online],
        )

    def _apply_telemetry(self, state: CpuOverviewState) -> None:
        self.frequency_tile.set_values(state.frequency_text)
        self.voltage_tile.set_values(state.voltage_text)
        self.temperature_tile.set_values(state.temperature_text)
        self.power_tile.set_label(state.power_label)
        self.power_tile.set_values(state.power_text, state.power_detail or None)
        self.vrm_tile.set_values(
            _temperature_text(state.vrm_temperature_c)
            if state.vrm_temperature_c is not None else tr("Not detected")
        )
        gddr6 = state.gddr6
        self.memory_tile.set_values(
            _temperature_text(gddr6.average_c)
            if gddr6.average_c is not None else tr("Waiting for sample"),
            tr_format("Hotspot {value}", value=_temperature_text(gddr6.hotspot_c))
            if gddr6.hotspot_c is not None else "Average across 8 chips",
        )

    def _apply_unlock(self, unlock: CoreUnlockState) -> None:
        rows = self.unlock_rows
        rows["shape"].set_value(unlock.detected_shape or tr("Checking"))
        rows["source"].set_value(tr("Ready") if unlock.source_ready else tr("Not prepared"))
        rows["helper"].set_value(tr("Ready") if unlock.helper_ready else tr("Not installed"))
        rows["governor"].set_value(unlock.governor_state or tr("Unknown"))
        self.unlock_button.setEnabled(bool(unlock.unlock_allowed))
        status = self.unlock_status_card.status
        if status is not None:
            if unlock.unlocked:
                status.setText(tr("Unlocked"))
                status.set_tone("green")
            elif unlock.unlock_allowed:
                status.setText(tr("Ready"))
                status.set_tone("orange")
            else:
                status.setText(tr("Not available"))
                status.set_tone("gray")

    def retranslate_dynamic_copy(self) -> None:
        """Re-render the copy ``localize_widget_tree`` cannot recover itself."""
        for key, label in self.IDENTITY_ROWS:
            self.identity_rows[key].set_label(label)
