from __future__ import annotations

from datetime import datetime
import logging
from typing import Callable

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..components.async_tools import AsyncRefresh, BackgroundExecutor
from ..components.dialogs import enable_adaptive_dialog
from ..components.page_widgets import ControlPageHeader, ConfirmDialog, SectionCard, StatusLine
from ..components.responsive import clear_grid, configure_responsive_scroll_area, effective_viewport_width
from ..i18n import count_label, localize_widget_tree, tr, tr_format
from ..core.state import state_cache_for
from ..theme import COLORS, application_stylesheet
from ..components.widgets import IconBadge, InfoDialog, QuickActionButton, apply_shadow, icon


logger = logging.getLogger(__name__)


ROW_NAMES = ("SE0.SH0", "SE0.SH1", "SE1.SH0", "SE1.SH1")
WGP_CU_PAIRS = ("0–1", "2–3", "4–5", "6–7", "8–9")
FACTORY_MASKS = (0x07, 0x07, 0x07, 0x07)
FULL_MASKS = (0x1F, 0x1F, 0x1F, 0x1F)
UNKNOWN_MASKS = (0x00, 0x00, 0x00, 0x00)


class CuTask(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, operation: Callable[[], object], parent: QWidget | None = None):
        super().__init__(parent)
        self.operation = operation

    def run(self) -> None:
        try:
            self.succeeded.emit(self.operation())
        except Exception as error:  # pragma: no cover - exercised on hardware
            self.failed.emit(str(error))


class CuSummaryItem(QFrame):
    def __init__(
        self,
        label: str,
        value: str,
        detail: str,
        icon_name: str,
        background: str,
        *,
        progress: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setProperty("gpuSummaryItem", True)
        self.setMinimumHeight(88)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(10)
        row.addWidget(IconBadge(icon_name, background, 32, radius=9), 0, Qt.AlignmentFlag.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(1)
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
        self.progress: QProgressBar | None = None
        if progress:
            self.progress = QProgressBar()
            self.progress.setProperty("cuProgress", True)
            self.progress.setRange(0, 40)
            self.progress.setValue(0)
            self.progress.setTextVisible(False)
            text.addWidget(self.progress)
        row.addLayout(text, 1)

    def set_values(self, value: str, detail: str | None = None, progress: int | None = None) -> None:
        self.value.setText(tr(value))
        if detail is not None:
            self.detail.setText(tr(detail))
        if self.progress is not None and progress is not None:
            self.progress.setValue(max(0, min(40, int(progress))))


class CuSummaryStrip(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("gpuSummaryStrip", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        apply_shadow(self, blur=16, y=3, alpha=10)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(8, 8, 8, 8)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(8)
        self.items = [
            CuSummaryItem(
                "Active CUs", "Not verified", "Not verified", "compute_orange", COLORS["orange_soft"], progress=True
            ),
            CuSummaryItem("Current mode", "Not verified", "driver boot topology", "gpu_purple", COLORS["purple_soft"]),
            CuSummaryItem("Routed WGPs", "Not verified", "2 CUs per WGP", "compute_blue", COLORS["blue_soft"]),
            CuSummaryItem("Service", "Not verified", "optional boot restore", "shield_green", COLORS["green_soft"]),
            CuSummaryItem("Persistence", "Not verified", "live changes reset at boot", "app_blue", COLORS["cyan_soft"]),
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


class WgpToggleButton(QPushButton):
    def __init__(self, row_index: int, wgp_index: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.row_index = row_index
        self.wgp_index = wgp_index
        self.driver_on = False
        self.setCheckable(True)
        self.setProperty("wgpToggle", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(76, 58)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.toggled.connect(self._refresh_visual)
        self._refresh_visual(False)

    def set_route(self, enabled: bool, driver_on: bool) -> None:
        self.driver_on = bool(driver_on)
        previous = self.blockSignals(True)
        self.setChecked(bool(enabled))
        self.blockSignals(previous)
        self._refresh_visual(bool(enabled))

    def token(self) -> str:
        if self.isChecked() and self.driver_on:
            return "D+"
        if self.isChecked():
            return "S+"
        if self.driver_on:
            return "D!"
        return "--"

    def _refresh_visual(self, checked: bool) -> None:
        if checked and self.driver_on:
            state, token, sub = "driver_on", "D+", "ROUTED"
            meaning = "Enabled in the amdgpu boot topology and routed now."
        elif checked:
            state, token, sub = "extra_on", "S+", "ROUTED"
            meaning = "Enabled through the live SPI routing table."
        elif self.driver_on:
            state, token, sub = "driver_off", "D!", "BLOCKED"
            meaning = "Present in the driver topology but disabled in current SPI routing."
        else:
            state, token, sub = "off", "--", "OFF"
            meaning = "This WGP pair is not routed."
        self.setProperty("routeState", state)
        self.setText(f"{token}\n{tr(sub)}")
        pair = WGP_CU_PAIRS[self.wgp_index]
        self.setToolTip(f"WGP{self.wgp_index} · CU{pair}\n{tr(meaning)}")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


class CuTableHeaderCell(QFrame):
    def __init__(self, title: str, detail: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("cuTableHeaderCell", True)
        self.setFixedHeight(54)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 7, 6, 6)
        layout.setSpacing(1)
        title_label = QLabel(tr(title))
        title_label.setProperty("cuTableHeaderTitle", True)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail_label = QLabel(tr(detail))
        detail_label.setProperty("cuTableHeaderDetail", True)
        detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        layout.addWidget(detail_label)


class CuRegisterDiagnostics(QFrame):
    """Compact register view kept outside the primary WGP selection table."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("cuAdvancedRegisters", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.live_masks = list(UNKNOWN_MASKS)
        self.target_masks = list(UNKNOWN_MASKS)
        self.driver_masks = list(UNKNOWN_MASKS)
        self.cc_values = ["--"] * 4

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 13, 14, 14)
        root.setSpacing(10)

        heading = QHBoxLayout()
        heading.setSpacing(8)
        title = QLabel(tr("Register diagnostics"))
        title.setProperty("cuAdvancedTitle", True)
        subtitle = QLabel(tr("Read-only register values and the pending SPI target."))
        subtitle.setProperty("cuAdvancedSubtitle", True)
        subtitle.setWordWrap(True)
        heading.addWidget(title)
        heading.addWidget(subtitle, 1)
        root.addLayout(heading)

        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(7)
        self.grid.setVerticalSpacing(7)
        headers = ("Shader row", "Live SPI", "Target SPI", "Driver map", "CC harvest")
        for column, text in enumerate(headers):
            label = QLabel(tr(text))
            label.setProperty("cuAdvancedHeader", True)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setFixedHeight(30)
            self.grid.addWidget(label, 0, column)

        self.live_labels: list[QLabel] = []
        self.target_labels: list[QLabel] = []
        self.driver_labels: list[QLabel] = []
        self.cc_labels: list[QLabel] = []
        for row_index, row_name in enumerate(ROW_NAMES):
            visual_row = row_index + 1
            row_label = QLabel(row_name)
            row_label.setProperty("cuAdvancedRow", True)
            row_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row_label.setFixedHeight(34)
            self.grid.addWidget(row_label, visual_row, 0)

            groups = (self.live_labels, self.target_labels, self.driver_labels, self.cc_labels)
            initial_values = ("--", "--", "--", "--")
            for column, (group, value) in enumerate(zip(groups, initial_values), start=1):
                label = QLabel(value)
                label.setProperty("cuAdvancedValue", True)
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                label.setFixedHeight(34)
                group.append(label)
                self.grid.addWidget(label, visual_row, column)

        self.grid.setColumnStretch(0, 2)
        self.grid.setColumnStretch(1, 2)
        self.grid.setColumnStretch(2, 2)
        self.grid.setColumnStretch(3, 2)
        self.grid.setColumnStretch(4, 3)
        root.addLayout(self.grid)
        self._refresh()

    def set_state(self, live_masks, driver_masks, cc_values) -> None:
        self.live_masks = self._normalize_masks(live_masks, UNKNOWN_MASKS)
        self.target_masks = list(self.live_masks)
        self.driver_masks = self._normalize_masks(driver_masks, UNKNOWN_MASKS)
        values = list(cc_values or [])
        self.cc_values = [str(values[index]) if index < len(values) else "--" for index in range(4)]
        self._refresh()

    def set_target_masks(self, masks) -> None:
        self.target_masks = self._normalize_masks(masks, self.live_masks)
        self._refresh()

    @staticmethod
    def _normalize_masks(value, fallback) -> list[int]:
        try:
            masks = [max(0, min(0x1F, int(item))) for item in list(value)]
            if len(masks) == 4:
                return masks
        except (TypeError, ValueError):
            logger.debug("Invalid CU mask payload; using the last known safe mask", exc_info=True)
        return list(fallback)

    def _refresh(self) -> None:
        for row_index in range(4):
            live = self.live_masks[row_index]
            target = self.target_masks[row_index]
            driver = self.driver_masks[row_index]
            self.live_labels[row_index].setText(f"0x{live:02x}")
            self.target_labels[row_index].setText(f"0x{target:02x}")
            self.driver_labels[row_index].setText(f"0x{driver:02x}")
            self.cc_labels[row_index].setText(self.cc_values[row_index])
            changed = target != live
            self.target_labels[row_index].setProperty("pending", changed)
            self.target_labels[row_index].style().unpolish(self.target_labels[row_index])
            self.target_labels[row_index].style().polish(self.target_labels[row_index])


class ExpandableRegisterPanel(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.diagnostics = CuRegisterDiagnostics()
        layout.addWidget(self.diagnostics)
        self._expanded = False
        self.setMaximumHeight(0)
        self.setVisible(False)
        self.animation = QPropertyAnimation(self, b"maximumHeight", self)
        self.animation.setDuration(180)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def is_expanded(self) -> bool:
        return self._expanded

    def set_expanded(self, expanded: bool, *, animate: bool = True) -> None:
        expanded = bool(expanded)
        self._expanded = expanded
        self.animation.stop()
        target = self.diagnostics.sizeHint().height() + 2
        if not animate:
            self.setVisible(expanded)
            self.setMaximumHeight(target if expanded else 0)
            return
        if expanded:
            self.setVisible(True)
            self.animation.setStartValue(max(0, self.height()))
            self.animation.setEndValue(target)
        else:
            self.animation.setStartValue(max(0, self.height()))
            self.animation.setEndValue(0)
            self.animation.finished.connect(self._hide_after_collapse)
        self.animation.start()

    def _hide_after_collapse(self) -> None:
        try:
            self.animation.finished.disconnect(self._hide_after_collapse)
        except TypeError:
            logger.debug("Register-panel animation callback was already disconnected")
        if not self._expanded:
            self.setVisible(False)

    def set_state(self, live_masks, driver_masks, cc_values) -> None:
        self.diagnostics.set_state(live_masks, driver_masks, cc_values)

    def set_target_masks(self, masks) -> None:
        self.diagnostics.set_target_masks(masks)


class CuTopologyTable(QFrame):
    selection_changed = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("cuTopologyTable", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._updating = False
        self.baseline_masks = list(UNKNOWN_MASKS)
        self.driver_masks = list(UNKNOWN_MASKS)
        self.cc_values = ["--"] * 4

        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(10, 10, 10, 10)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(8)

        headers = (
            ("Shader row", "SE / SH"),
            ("WGP0", "CU 0–1"),
            ("WGP1", "CU 2–3"),
            ("WGP2", "CU 4–5"),
            ("WGP3", "CU 6–7"),
            ("WGP4", "CU 8–9"),
            ("CUs", "active / 10"),
        )
        for column, (title, detail) in enumerate(headers):
            self.grid.addWidget(CuTableHeaderCell(title, detail), 0, column)

        self.buttons: dict[tuple[int, int], WgpToggleButton] = {}
        self.count_labels: list[QLabel] = []
        for row_index, name in enumerate(ROW_NAMES):
            visual_row = row_index + 1
            row_label = QLabel(name)
            row_label.setProperty("cuTableRowLabel", True)
            row_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row_label.setFixedHeight(58)
            self.grid.addWidget(row_label, visual_row, 0)

            for wgp_index in range(5):
                button = WgpToggleButton(row_index, wgp_index)
                button.toggled.connect(lambda _checked, row=row_index: self._row_changed(row))
                self.buttons[(row_index, wgp_index)] = button
                self.grid.addWidget(button, visual_row, wgp_index + 1)

            count = QLabel("0 / 10")
            count.setProperty("cuCountValue", True)
            count.setAlignment(Qt.AlignmentFlag.AlignCenter)
            count.setFixedHeight(58)
            self.count_labels.append(count)
            self.grid.addWidget(count, visual_row, 6)

        self.grid.setColumnMinimumWidth(0, 92)
        self.grid.setColumnStretch(0, 2)
        for column in range(1, 6):
            self.grid.setColumnMinimumWidth(column, 76)
            self.grid.setColumnStretch(column, 3)
        self.grid.setColumnMinimumWidth(6, 76)
        self.grid.setColumnStretch(6, 2)
        self.set_state({"masks": list(UNKNOWN_MASKS), "driver_masks": list(UNKNOWN_MASKS), "rows": []})

    def set_state(self, state: dict) -> None:
        masks = self._normalize_masks(state.get("masks"), UNKNOWN_MASKS)
        drivers = self._normalize_masks(state.get("driver_masks"), UNKNOWN_MASKS)
        rows = list(state.get("rows") or [])
        cc_values = []
        for index in range(4):
            row = rows[index] if index < len(rows) and isinstance(rows[index], dict) else {}
            cc_values.append(str(row.get("cc") or "--"))
        self.baseline_masks = list(masks)
        self.driver_masks = list(drivers)
        self.cc_values = cc_values
        self.set_masks(masks, emit=False)

    @staticmethod
    def _normalize_masks(value, fallback) -> list[int]:
        try:
            masks = [max(0, min(0x1F, int(item))) for item in list(value)]
            if len(masks) == 4:
                return masks
        except (TypeError, ValueError):
            logger.debug("Invalid CU mask payload; using the last known safe mask", exc_info=True)
        return list(fallback)

    def set_masks(self, masks, *, emit: bool = True) -> None:
        masks = self._normalize_masks(masks, self.baseline_masks)
        self._updating = True
        try:
            for row_index, mask in enumerate(masks):
                for wgp_index in range(5):
                    button = self.buttons[(row_index, wgp_index)]
                    button.set_route(bool(mask & (1 << wgp_index)), bool(self.driver_masks[row_index] & (1 << wgp_index)))
                self._update_row_labels(row_index)
        finally:
            self._updating = False
        if emit:
            self.selection_changed.emit(self.current_masks())

    def reset_to_live(self) -> None:
        self.set_masks(self.baseline_masks)

    def current_masks(self) -> list[int]:
        masks = []
        for row_index in range(4):
            mask = 0
            for wgp_index in range(5):
                if self.buttons[(row_index, wgp_index)].isChecked():
                    mask |= 1 << wgp_index
            masks.append(mask)
        return masks

    def pending_count(self) -> int:
        total = 0
        current = self.current_masks()
        for row_index in range(4):
            total += (current[row_index] ^ self.baseline_masks[row_index]).bit_count()
        return total

    def target_cus(self) -> int:
        return sum(mask.bit_count() * 2 for mask in self.current_masks())

    def _row_changed(self, row_index: int) -> None:
        if self._updating:
            return
        self._update_row_labels(row_index)
        self.selection_changed.emit(self.current_masks())

    def _update_row_labels(self, row_index: int) -> None:
        mask = self.current_masks()[row_index]
        cus = mask.bit_count() * 2
        self.count_labels[row_index].setText(f"{cus} / 10")


class SessionActionRow(QWidget):
    def __init__(self, title: str, detail: str, when: str, tone: str = "green", parent: QWidget | None = None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 7, 0, 7)
        row.setSpacing(10)
        marker = QFrame()
        marker.setProperty("cuActivityDot", True)
        marker.setProperty("tone", tone)
        marker.setFixedSize(9, 9)
        row.addWidget(marker)
        copy = QVBoxLayout()
        copy.setSpacing(1)
        title_label = QLabel(tr(title))
        title_label.setProperty("cuActivityTitle", True)
        detail_label = QLabel(tr(detail))
        detail_label.setProperty("cuActivityDetail", True)
        detail_label.setWordWrap(True)
        copy.addWidget(title_label)
        copy.addWidget(detail_label)
        row.addLayout(copy, 1)
        time_label = QLabel(tr(when))
        time_label.setProperty("activityTime", True)
        row.addWidget(time_label, 0, Qt.AlignmentFlag.AlignTop)


class ComputeUnitsPage(QWidget):
    """Graphical WGP table backed by WinnieLV/bc250-cu-live-manager."""

    def __init__(self, controller, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("computeUnitsPage", True)
        self.controller = controller
        self.current_state: dict = {}
        self._updates_active = False
        self._state_cache = state_cache_for(controller)
        self._worker: CuTask | None = None
        self._busy = False
        self._workspace_columns = 0
        self._status_columns = 0
        self._session_actions: list[tuple[str, str, str, str]] = []
        self._action_buttons: list[QPushButton] = []
        self._background = BackgroundExecutor(self)
        self._event_sequence = 0

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
            "COMPUTE UNITS / LIVE ROUTING",
            "Compute Units",
            "Graphical WGP routing for the AMD BC250. Each table button controls one WGP pair, equivalent to two compute units.",
            mode_text="● LIVE SESSION",
            action_text="Prepare CU tools",
            action_icon="download_blue",
        )
        self.header.refresh_requested.connect(self.refresh_authorized)
        self.header.action_requested.connect(self.prepare_tools)
        layout.addWidget(self.header)
        # The large introductory banner is intentionally hidden. Its object stays
        # alive for the existing refresh/prepare state handling, while the summary
        # strip moves to the top of the visible Compute Units page.
        self.header.hide()

        self.summary_strip = CuSummaryStrip()
        layout.addWidget(self.summary_strip)

        self.workspace = QGridLayout()
        self.workspace.setContentsMargins(0, 0, 0, 0)
        self.workspace.setHorizontalSpacing(14)
        self.workspace.setVerticalSpacing(14)
        layout.addLayout(self.workspace)

        self.topology_card = self._build_topology_card()
        self.side_column = self._build_side_column()
        self.status_card = self._build_status_card()
        self.activity_card = self._build_activity_card()
        self.bottom_grid = QGridLayout()
        self.bottom_grid.setContentsMargins(0, 0, 0, 0)
        self.bottom_grid.setHorizontalSpacing(14)
        self.bottom_grid.setVerticalSpacing(14)
        layout.addLayout(self.bottom_grid)
        layout.addStretch(1)

        self._reflow(1400)
        self._refresher = AsyncRefresh(
            self,
            "compute-units-cache-refresh",
            self._state_cache.cu_cache,
            lambda state: self._apply_state(dict(state or {}), preserve_edits=False),
            lambda message: self.setToolTip(message),
        )

    def _build_topology_card(self) -> SectionCard:
        card = SectionCard(
            "WGP / CU topology",
            "Select the WGP pairs to route on each shader-engine row. The table mirrors the official terminal editor while keeping the target visible before applying.",
            icon_name="compute_orange",
            icon_background=COLORS["orange_soft"],
            status=("Authorized cache", "gray"),
        )
        self.topology_status = card.status

        self.register_toggle = card.add_header_button("Show registers", self.toggle_register_diagnostics)
        self.register_toggle.setProperty("registerToggle", True)
        self.register_toggle.setIcon(icon("expand_gray"))

        legend_frame = QFrame()
        legend_frame.setProperty("cuLegendBar", True)
        legend = QGridLayout(legend_frame)
        legend.setContentsMargins(8, 7, 8, 7)
        legend.setHorizontalSpacing(8)
        legend.setVerticalSpacing(8)
        legend_items = (
            ("D+", "Driver + routed", "driver_on"),
            ("S+", "Live unlock", "extra_on"),
            ("D!", "Driver blocked", "driver_off"),
            ("--", "Not routed", "off"),
        )
        self.legend_grid = legend
        self.legend_items = [self._legend_item(token, label, state) for token, label, state in legend_items]
        for index, item in enumerate(self.legend_items):
            legend.addWidget(item, 0, index)
            legend.setColumnStretch(index, 1)
        card.body.addWidget(legend_frame)

        self.topology_table = CuTopologyTable()
        self.topology_table.selection_changed.connect(self._selection_changed)
        card.body.addWidget(self.topology_table)

        self.register_panel = ExpandableRegisterPanel()
        self.register_panel.set_state(
            self.topology_table.baseline_masks,
            self.topology_table.driver_masks,
            self.topology_table.cc_values,
        )
        card.body.addWidget(self.register_panel)

        selection_panel = QFrame()
        selection_panel.setProperty("cuSelectionPanel", True)
        selection_layout = QGridLayout(selection_panel)
        selection_layout.setContentsMargins(13, 10, 13, 10)
        selection_layout.setHorizontalSpacing(10)
        selection_layout.setVerticalSpacing(8)
        self.selection_layout = selection_layout
        self.selection_copy_widget = QWidget()
        self.selection_copy_widget.setMinimumWidth(0)
        self.selection_copy_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        selection_copy = QVBoxLayout(self.selection_copy_widget)
        selection_copy.setContentsMargins(0, 0, 0, 0)
        selection_copy.setSpacing(1)
        self.selection_title = QLabel(tr("Target: Not verified"))
        self.selection_title.setProperty("cuSelectionTitle", True)
        self.selection_detail = QLabel(tr("No pending WGP changes."))
        self.selection_detail.setProperty("cuSelectionDetail", True)
        self.selection_detail.setWordWrap(True)
        self.selection_detail.setMinimumWidth(0)
        selection_copy.addWidget(self.selection_title)
        selection_copy.addWidget(self.selection_detail)

        self.discard_button = QPushButton(tr("Discard edits"))
        self.discard_button.setProperty("compactAction", True)
        self.discard_button.setMinimumSize(132, 38)
        self.discard_button.clicked.connect(self.topology_table.reset_to_live)
        selection_layout.addWidget(self.discard_button, 0, 1)

        self.apply_live_button = QPushButton(tr("Review and apply live"))
        self.apply_live_button.setObjectName("PrimaryAction")
        self.apply_live_button.setMinimumSize(166, 38)
        self.apply_live_button.setIcon(icon("rocket_blue"))
        self.apply_live_button.clicked.connect(self.apply_selected_table)
        selection_layout.addWidget(self.apply_live_button, 0, 2)
        selection_layout.addWidget(self.selection_copy_widget, 0, 0)
        selection_layout.setColumnStretch(0, 1)
        self._action_buttons.extend([self.discard_button, self.apply_live_button])
        card.body.addWidget(selection_panel)

        note = QLabel(tr(
            "Live routing is temporary until the current table is saved and the boot service is installed. One WGP always represents two CUs; individual CUs cannot be toggled separately."
        ))
        note.setProperty("fieldHint", True)
        note.setWordWrap(True)
        card.body.addWidget(note)
        return card

    def _legend_item(self, token: str, text: str, state: str) -> QWidget:
        item = QWidget()
        item.setProperty("cuLegendItem", True)
        item.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row = QHBoxLayout(item)
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(6)
        marker = QLabel(token)
        marker.setProperty("cuLegendToken", True)
        marker.setProperty("routeState", state)
        marker.setAlignment(Qt.AlignmentFlag.AlignCenter)
        marker.setFixedWidth(31)
        copy = QLabel(tr(text))
        copy.setProperty("cuLegendText", True)
        copy.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(marker)
        row.addWidget(copy, 1)
        return item

    def toggle_register_diagnostics(self) -> None:
        expanded = not self.register_panel.is_expanded()
        self.register_panel.set_expanded(expanded)
        self.register_toggle.setText(tr("Hide registers" if expanded else "Show registers"))
        self.register_toggle.setIcon(icon("collapse_gray" if expanded else "expand_gray"))

    def _build_side_column(self) -> QWidget:
        column = QWidget()
        column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        profiles = SectionCard(
            "Quick layouts",
            "Load a safe starting table, inspect every row, then apply it live from the topology panel.",
            icon_name="bolt_blue",
            icon_background=COLORS["blue_soft"],
            status=("Editable", "blue"),
        )
        factory = QuickActionButton("Factory 24 CUs", "Use the amdgpu boot WGP topology", "shield_green", "blue")
        full = QuickActionButton("Full 40 CUs", "Route all 20 WGP pairs", "rocket_blue", "blue")
        custom = QuickActionButton("Custom layout", "Start from the current live table", "settings_blue", "gray")
        factory.clicked.connect(self.load_factory_layout)
        full.clicked.connect(lambda: self._load_layout(FULL_MASKS, "Full 40 CU target loaded"))
        custom.clicked.connect(self.load_custom_layout)
        profiles.body.addWidget(factory)
        profiles.body.addWidget(full)
        profiles.body.addWidget(custom)
        self.profile_note = QLabel(tr("Current selection: Not verified"))
        self.profile_note.setProperty("cuProfileNote", True)
        profiles.body.addWidget(self.profile_note)
        layout.addWidget(profiles)

        persistence = SectionCard(
            "Boot persistence",
            "Save the current live table and control the official systemd restore service without opening the terminal menu.",
            icon_name="app_blue",
            icon_background=COLORS["cyan_soft"],
            status=("Optional", "gray"),
        )
        self.persistence_status = persistence.status
        action_grid = QGridLayout()
        self.persistence_actions_grid = action_grid
        action_grid.setContentsMargins(0, 0, 0, 0)
        action_grid.setHorizontalSpacing(8)
        action_grid.setVerticalSpacing(8)

        # Keep these operation names in English on purpose. They mirror the
        # upstream terminal vocabulary users already recognize; the surrounding
        # descriptions, tooltips, confirmations, and results remain localized.
        self.save_boot_button = self._action_button(
            "Write table", "app_blue", self.save_boot_layout,
            literal_english=True, tooltip="Terminal action: [w] Write table",
        )
        self.install_service_button = self._action_button(
            "Install service", "download_blue", self.install_service,
            literal_english=True, tooltip="Terminal action: [i] Install service",
        )
        self.apply_saved_button = self._action_button(
            "Apply saved layout", "rocket_blue", self.apply_saved_layout,
            literal_english=True, tooltip="Apply the WGP table stored for boot.",
        )
        self.remove_service_button = self._action_button(
            "Uninstall service", "power_gray", self.remove_service,
            danger=True, literal_english=True, tooltip="Terminal action: [u] Uninstall service",
        )
        self.restore_factory_button = self._action_button(
            "Enable default CUs", "refresh_gray", self.restore_factory_now,
            literal_english=True, tooltip="Terminal action: [t] Enable default CUs",
        )
        self.install_umr_button = self._action_button(
            "Install UMR", "compute_blue", self.install_umr,
            literal_english=True, tooltip="Install the register-access dependency required by the live manager.",
        )
        buttons = [
            self.save_boot_button,
            self.install_service_button,
            self.apply_saved_button,
            self.remove_service_button,
            self.restore_factory_button,
            self.install_umr_button,
        ]
        self.persistence_action_buttons = buttons
        for index, button in enumerate(buttons):
            action_grid.addWidget(button, index // 2, index % 2)
        action_grid.setColumnStretch(0, 1)
        action_grid.setColumnStretch(1, 1)
        persistence.body.addLayout(action_grid)
        layout.addWidget(persistence)
        layout.addStretch(1)
        return column

    def _action_button(
        self,
        text: str,
        icon_name: str,
        callback,
        *,
        danger: bool = False,
        literal_english: bool = False,
        tooltip: str = "",
    ) -> QPushButton:
        button = QPushButton(tr(text))
        if literal_english:
            button.setText(text)
            button.setProperty("i18nLiteral", True)
        if tooltip:
            button.setToolTip(tr(tooltip))
        button.setProperty("dangerAction" if danger else "compactAction", True)
        button.setIcon(icon(icon_name))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(39)
        button.clicked.connect(callback)
        self._action_buttons.append(button)
        return button

    def _build_status_card(self) -> SectionCard:
        card = SectionCard(
            "Status overview",
            "Readiness and source information for the current WGP table.",
            icon_name="shield_green",
            icon_background=COLORS["green_soft"],
            status=("Passive", "green"),
        )
        card.add_header_button("Raw status", self.show_raw_status)
        self.umr_line = StatusLine("UMR availability", "Unknown", "Register access backend")
        self.driver_line = StatusLine("Driver topology", "Unknown", "amdgpu boot CU map")
        self.source_line = StatusLine("Routing source", "Cache", "SPI dispatch masks")
        self.asic_line = StatusLine("ASIC selector", "cyan_skillfish.gfx1013", "BC250 gfx1013")
        self.refresh_line = StatusLine("Last authorized refresh", "--:--:--", "No automatic authentication prompts")
        self.status_lines = [self.umr_line, self.driver_line, self.source_line, self.asic_line, self.refresh_line]
        for line in self.status_lines:
            card.body.addWidget(line)
        return card

    def _build_activity_card(self) -> SectionCard:
        card = SectionCard(
            "Recent CU actions",
            "Changes made during this application session.",
            icon_name="activity_purple",
            icon_background=COLORS["purple_soft"],
            status=("Session", "purple"),
        )
        self.activity_body = QVBoxLayout()
        self.activity_body.setContentsMargins(0, 0, 0, 0)
        self.activity_body.setSpacing(0)
        card.body.addLayout(self.activity_body)
        self._record_action("Compute Units workspace ready", "No hardware command has been executed.", "gray")
        return card

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._reflow(effective_viewport_width(self, self.scroll))

    def _reflow(self, width: int) -> None:
        self.summary_strip.set_columns(5 if width >= 1120 else 3 if width >= 680 else 2 if width >= 440 else 1)
        self._reflow_topology_controls(width)
        columns = 2 if width >= 1080 else 1
        if columns != self._workspace_columns or not self.workspace.count():
            self._workspace_columns = columns
            self._clear_grid(self.workspace)
            if columns == 2:
                self.workspace.addWidget(self.topology_card, 0, 0, Qt.AlignmentFlag.AlignTop)
                self.workspace.addWidget(self.side_column, 0, 1, Qt.AlignmentFlag.AlignTop)
                self.workspace.setColumnStretch(0, 7)
                self.workspace.setColumnStretch(1, 4)
            else:
                self.workspace.addWidget(self.topology_card, 0, 0, Qt.AlignmentFlag.AlignTop)
                self.workspace.addWidget(self.side_column, 1, 0, Qt.AlignmentFlag.AlignTop)
                self.workspace.setColumnStretch(0, 1)

        bottom_columns = 2 if width >= 900 else 1
        if bottom_columns != self._status_columns or not self.bottom_grid.count():
            self._status_columns = bottom_columns
            self._clear_grid(self.bottom_grid)
            if bottom_columns == 2:
                # Do not apply AlignTop here: alignment constrains each card to
                # its own sizeHint and produces mismatched lower edges. Let the
                # grid fill both widgets into the same row geometry instead.
                self.bottom_grid.addWidget(self.status_card, 0, 0)
                self.bottom_grid.addWidget(self.activity_card, 0, 1)
                self.bottom_grid.setColumnStretch(0, 1)
                self.bottom_grid.setColumnStretch(1, 1)
            else:
                self.bottom_grid.addWidget(self.status_card, 0, 0, Qt.AlignmentFlag.AlignTop)
                self.bottom_grid.addWidget(self.activity_card, 1, 0, Qt.AlignmentFlag.AlignTop)
                self.bottom_grid.setColumnStretch(0, 1)

    def _reflow_topology_controls(self, width: int) -> None:
        if hasattr(self, "legend_grid"):
            columns = 4 if width >= 900 else 2 if width >= 500 else 1
            if getattr(self, "_legend_columns", 0) != columns:
                self._legend_columns = columns
                clear_grid(self.legend_grid)
                for index, item in enumerate(self.legend_items):
                    self.legend_grid.addWidget(item, index // columns, index % columns)
                for column in range(columns):
                    self.legend_grid.setColumnStretch(column, 1)

        if hasattr(self, "selection_layout"):
            mode = "wide" if width >= 760 else "split" if width >= 500 else "stack"
            if getattr(self, "_selection_mode", "") != mode:
                self._selection_mode = mode
                clear_grid(self.selection_layout)
                if mode == "wide":
                    self.selection_layout.addWidget(self.selection_copy_widget, 0, 0)
                    self.selection_layout.addWidget(self.discard_button, 0, 1)
                    self.selection_layout.addWidget(self.apply_live_button, 0, 2)
                    self.selection_layout.setColumnStretch(0, 1)
                elif mode == "split":
                    self.selection_layout.addWidget(self.selection_copy_widget, 0, 0, 1, 2)
                    self.selection_layout.addWidget(self.discard_button, 1, 0)
                    self.selection_layout.addWidget(self.apply_live_button, 1, 1)
                    self.selection_layout.setColumnStretch(0, 1)
                    self.selection_layout.setColumnStretch(1, 1)
                else:
                    self.selection_layout.addWidget(self.selection_copy_widget, 0, 0)
                    self.selection_layout.addWidget(self.discard_button, 1, 0)
                    self.selection_layout.addWidget(self.apply_live_button, 2, 0)
                    self.selection_layout.setColumnStretch(0, 1)

        if hasattr(self, "persistence_actions_grid"):
            columns = 2 if width >= 540 else 1
            if getattr(self, "_persistence_action_columns", 0) != columns:
                self._persistence_action_columns = columns
                clear_grid(self.persistence_actions_grid)
                for index, button in enumerate(self.persistence_action_buttons):
                    button.setMinimumWidth(0)
                    button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                    self.persistence_actions_grid.addWidget(button, index // columns, index % columns)
                for column in range(columns):
                    self.persistence_actions_grid.setColumnStretch(column, 1)

    @staticmethod
    def _clear_grid(grid: QGridLayout) -> None:
        clear_grid(grid)

    def set_updates_active(self, active: bool) -> None:
        self._updates_active = bool(active)
        if self._updates_active:
            self._refresher.activate(fresh_for=5.0)
        else:
            self._refresher.set_active(False)

    def refresh(self) -> None:
        """Load the last authorized snapshot without opening Polkit."""
        # AsyncRefresh delegates to state_cache.obtener_estado_cu_cache; this
        # passive path never opens an authorization flow.
        self._refresher.request()

    def refresh_authorized(self) -> None:
        self._run_task(
            "Reading live WGP routing",
            self.controller.obtener_estado_cu,
            success_message="Live CU topology refreshed",
            success_detail="SPI masks and amdgpu driver topology were read successfully.",
        )

    def _apply_state(self, state: dict, *, preserve_edits: bool = False) -> None:
        if not isinstance(state, dict):
            return
        self.current_state = dict(state)
        if not preserve_edits:
            self.topology_table.set_state(self.current_state)
        self.register_panel.set_state(
            self.topology_table.baseline_masks,
            self.topology_table.driver_masks,
            self.topology_table.cc_values,
        )
        if preserve_edits:
            self.register_panel.set_target_masks(self.topology_table.current_masks())
        state_verified = self._has_authorized_state()
        active = int(self.current_state.get("active_cus") or 0)
        routed = int(self.current_state.get("routed_wgps") or active // 2)
        mode = str(self.current_state.get("mode") or "Not verified")
        mode_short = mode.replace(" CUs", "")
        service = str(self.current_state.get("service") or "Not verified")
        boot_sync = str(self.current_state.get("boot_sync") or "Not verified")
        source = str(self.current_state.get("source") or "Not verified")
        fresh = bool(self.current_state.get("fresh"))

        self.summary_strip.items[0].set_values(f"{active} / 40" if state_verified else tr("Not verified"), count_label(routed, "routed WGP") if state_verified else tr("Not verified"), progress=active)
        self.summary_strip.items[1].set_values(tr(mode_short), tr("live SPI table classification"))
        self.summary_strip.items[2].set_values(f"{routed} / 20" if state_verified else tr("Not verified"), tr("2 CUs per WGP"))
        self.summary_strip.items[3].set_values(tr(service.title()), "bc250-cu-live-manager.service")
        persistence_detail = tr("boot table matches live state" if self.current_state.get("boot_sync_key") == "saved" else "live changes may reset at boot")
        self.summary_strip.items[4].set_values(tr(boot_sync), persistence_detail)

        if self.topology_status is not None:
            self.topology_status.setText(tr("Live verified" if fresh else "Authorized cache" if state_verified else "Not verified"))
            self.topology_status.set_tone("green" if fresh else "gray")
        if self.persistence_status is not None:
            key = self.current_state.get("boot_sync_key")
            if key == "saved":
                self.persistence_status.setText(tr("Saved"))
                self.persistence_status.set_tone("green")
            elif key == "pending":
                self.persistence_status.setText(tr("Pending"))
                self.persistence_status.set_tone("orange")
            else:
                self.persistence_status.setText(tr("Not saved"))
                self.persistence_status.set_tone("gray")

        umr = str(self.current_state.get("umr") or "")
        self.umr_line.set_values(tr("Available" if umr else "Not verified"), umr or tr("Install UMR or authorize a live refresh"))
        driver_ready = bool(self.current_state.get("driver_topology_available"))
        driver_masks = self.current_state.get("driver_masks") or []
        driver_cus = sum(int(mask).bit_count() * 2 for mask in driver_masks) if driver_masks else 0
        self.driver_line.set_values(tr("Available" if driver_ready else "Unavailable"), tr_format("amdgpu boot map · {count} CUs", count=driver_cus or "--"))
        self.source_line.set_values(tr("Live SPI masks" if fresh else "Authorized cache"), tr(source))
        self.asic_line.set_values(str(self.current_state.get("asic") or tr("Not verified")), tr("UMR ASIC selector"))
        self.refresh_line.set_values(str(self.current_state.get("updated_at") or "--:--:--"), tr("Manual authorization only"))
        self.profile_note.setText(tr_format("Current selection: {mode}", mode=tr(mode)))
        self._selection_changed(self.topology_table.current_masks())
        self._update_action_availability()

    def _selection_changed(self, masks) -> None:
        self.register_panel.set_target_masks(masks)
        target = self.topology_table.target_cus()
        pending = self.topology_table.pending_count()
        state_verified = self._has_authorized_state()
        self.selection_title.setText(tr_format("Target: {count} / 40 CUs", count=target) if state_verified else tr("Target: Not verified"))
        if not state_verified:
            self.selection_detail.setText(tr("Authorize a live refresh before applying WGP changes."))
        elif pending:
            self.selection_detail.setText(tr_format("{pairs} differ from the last authorized live table.", pairs=count_label(pending, "WGP pair")))
        else:
            self.selection_detail.setText(tr("No pending WGP changes."))
        self.discard_button.setEnabled(pending > 0 and not self._busy)
        self.apply_live_button.setEnabled(state_verified and pending > 0 and not self._busy)
        if tuple(masks) == FULL_MASKS:
            self.profile_note.setText(tr("Current selection: Full 40 CUs"))
        elif tuple(masks) == tuple(self.topology_table.driver_masks):
            self.profile_note.setText(tr("Current selection: Factory driver topology"))
        else:
            self.profile_note.setText(tr_format("Current selection: Custom {count} CUs", count=target))

    def _load_layout(self, masks, message: str) -> None:
        self.topology_table.set_masks(masks)
        self._record_action("Layout loaded", message, "blue")

    def load_factory_layout(self) -> None:
        masks = self.topology_table.driver_masks if any(self.topology_table.driver_masks) else list(FACTORY_MASKS)
        self._load_layout(masks, "Factory driver WGP topology loaded for review.")

    def load_custom_layout(self) -> None:
        self.topology_table.reset_to_live()
        self._record_action("Custom editor ready", "Use the 20 WGP buttons to build a custom live table.", "purple")

    def apply_selected_table(self) -> None:
        masks = self.topology_table.current_masks()
        pending = self.topology_table.pending_count()
        if pending <= 0:
            self._show_info("No pending changes", "The selected WGP table already matches the last authorized live state.")
            return
        target_cus = self.topology_table.target_cus()
        tone = "red" if target_cus == 0 else "orange" if target_cus < 24 or target_cus > 32 else "blue"
        dialog = ConfirmDialog(
            "Apply WGP routing table",
            "The selected WGP pairs will be written through the official live manager. The application will verify the resulting SPI table before reporting success.",
            summary=(
                ("Target", f"{target_cus} / 40 CUs"),
                ("Changed WGP pairs", str(pending)),
                ("Persistence", "Live only until saved"),
                ("Masks", ", ".join(f"0x{mask:02x}" for mask in masks)),
            ),
            confirm_text="Apply live table",
            tone=tone,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_task(
            "Applying graphical WGP table",
            lambda: self.controller.aplicar_tabla_cu(masks),
            success_message="Custom WGP table applied",
            success_detail=f"Verified target: {target_cus} / 40 CUs.",
            event_action="custom",
        )

    def restore_factory_now(self) -> None:
        self._run_confirmed_action(
            "factory",
            "Restore factory 24 CU routing",
            "The live SPI table will be rebuilt from the amdgpu boot CU topology. A saved boot service is not removed automatically.",
            "Restore factory routing",
            tone="orange",
        )

    def save_boot_layout(self) -> None:
        self._run_confirmed_action(
            "save_boot",
            "Save current boot layout",
            "The currently verified live WGP table will be written to /etc/bc250-cu-live-manager.conf. This does not install the service by itself.",
            "Save current table",
        )

    def install_service(self) -> None:
        self._run_confirmed_action(
            "install_service",
            "Install boot restore service",
            "The official systemd service will be installed and enabled. Save the intended live table first so the correct layout is restored after reboot.",
            "Install and enable service",
            tone="orange",
        )

    def apply_saved_layout(self) -> None:
        self._run_confirmed_action(
            "apply_saved",
            "Apply saved boot layout now",
            "The WGP masks stored in /etc/bc250-cu-live-manager.conf will replace the current live routing table.",
            "Apply saved layout",
            tone="orange",
        )

    def remove_service(self) -> None:
        self._run_confirmed_action(
            "remove_service",
            "Remove boot restore service",
            "The service and its saved configuration will be removed. The current live WGP routing remains active until reboot or another live action changes it.",
            "Remove service",
            tone="red",
        )

    def _run_confirmed_action(
        self,
        action: str,
        title: str,
        message: str,
        confirm_text: str,
        *,
        tone: str = "blue",
    ) -> None:
        dialog = ConfirmDialog(
            title,
            message,
            summary=(
                ("Backend", "bc250-cu-live-manager"),
                ("Current live table", f"{self.current_state.get('active_cus')} / 40 CUs" if self._has_authorized_state() else "Not verified"),
                ("Boot sync", str(self.current_state.get("boot_sync") or "Unknown")),
            ),
            confirm_text=confirm_text,
            tone=tone,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        labels = {
            "factory": ("Factory routing restored", "The live table now follows the amdgpu boot topology."),
            "save_boot": ("Boot layout saved", "The current live table was written to the service configuration."),
            "install_service": ("Boot service installed", "The saved WGP table can now be restored during boot."),
            "apply_saved": ("Saved layout applied", "The configured boot table was applied and verified live."),
            "remove_service": ("Boot service removed", "Automatic WGP restore was disabled and its configuration removed."),
        }
        success_message, success_detail = labels[action]
        self._run_task(
            title,
            lambda: self.controller.ejecutar_accion_cu_grafica(action),
            success_message=success_message,
            success_detail=success_detail,
            event_action=action,
        )

    def prepare_tools(self) -> None:
        dialog = ConfirmDialog(
            "Prepare Compute Units tools",
            "The existing distribution-specific dependency workflow will prepare UMR and bc250-cu-live-manager. Package installation may open a visible terminal and request administrator authentication.",
            summary=(("Scope", "UMR + live manager"), ("Hardware writes", "None during preparation")),
            confirm_text="Open preparation workflow",
            tone="blue",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_task(
            "Preparing Compute Units tools",
            self.controller.instalar_dependencias_bc250,
            success_message="Dependency workflow opened",
            success_detail="Prepare dependencies was started using the existing R64 backend.",
            event_action="prepare_tools",
        )

    def install_umr(self) -> None:
        dialog = ConfirmDialog(
            "Install UMR",
            "UMR is required to read and write the BC250 registers used by the WGP table. The distribution-specific installer may open a terminal and request administrator authentication.",
            summary=(("Package", "UMR"), ("Purpose", "AMDGPU register access")),
            confirm_text="Open UMR installer",
            tone="blue",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_task(
            "Installing UMR",
            self.controller.instalar_umr,
            success_message="UMR installer opened",
            success_detail="The existing distribution-specific UMR workflow was started.",
            event_action="install_umr",
        )

    def _run_task(
        self,
        label: str,
        operation: Callable[[], object],
        *,
        success_message: str,
        success_detail: str,
        event_action: str = "refresh",
    ) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self._set_busy(True, label)
        worker = CuTask(operation, self)
        self._worker = worker

        def complete(result) -> None:
            self._set_busy(False, "")
            invalidation_keys = ["cu_cache"]
            if event_action in {"prepare_tools", "install_umr"}:
                invalidation_keys.append("tools")
            self._state_cache.invalidate(*invalidation_keys)
            if isinstance(result, dict):
                self._apply_state(result, preserve_edits=False)
            self._record_action(success_message, success_detail, "green")
            self._register_event(event_action, success_message, success_detail)

        def failed(message: str) -> None:
            self._set_busy(False, "")
            self._record_action("Operation failed", message, "red")
            self._show_error("Compute Units operation failed", message)

        worker.succeeded.connect(complete)
        worker.failed.connect(failed)
        worker.finished.connect(self._worker_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _worker_finished(self) -> None:
        self._worker = None

    def _set_busy(self, busy: bool, label: str) -> None:
        self._busy = bool(busy)
        for button in self._action_buttons:
            button.setEnabled(not busy)
        self.topology_table.setEnabled(not busy)
        if self.header.action_button is not None:
            self.header.action_button.setEnabled(not busy)
            self.header.action_button.setText(tr(label) if busy else tr("Prepare CU tools"))
        if busy:
            if self.topology_status is not None:
                self.topology_status.setText(tr("Working"))
                self.topology_status.set_tone("blue")
        else:
            self._apply_state(self.current_state, preserve_edits=True)
        self._selection_changed(self.topology_table.current_masks())
        self._update_action_availability()

    def _update_action_availability(self) -> None:
        enabled = not self._busy
        state_verified = self._has_authorized_state()
        for button in (
        self.save_boot_button,
            self.install_service_button,
            self.apply_saved_button,
            self.restore_factory_button,
            self.install_umr_button,
        ):
            button.setEnabled(enabled)
        self.save_boot_button.setEnabled(enabled and state_verified)
        self.remove_service_button.setEnabled(enabled and bool(self.current_state.get("service_installed")))
        self.discard_button.setEnabled(enabled and self.topology_table.pending_count() > 0)
        self.apply_live_button.setEnabled(enabled and state_verified and self.topology_table.pending_count() > 0)

    def _has_authorized_state(self) -> bool:
        masks = self.current_state.get("masks")
        return isinstance(masks, (list, tuple)) and len(masks) == 4

    def _register_event(self, action: str, title: str, detail: str) -> None:
        self._event_sequence += 1
        payload = {
            "accion": action,
            "active_cus": self.current_state.get("active_cus"),
        }

        def operation() -> object:
            self.controller.registrar_evento(
                "40cu",
                "info" if action in {"refresh", "save_boot", "install_service"} else "warning",
                title,
                detail,
                payload,
            )
            return True

        self._background.start(
            f"cu-event:{self._event_sequence}",
            operation,
        )

    def _record_action(self, title: str, detail: str, tone: str) -> None:
        self._session_actions.insert(0, (title, detail, datetime.now().strftime("%H:%M:%S"), tone))
        self._session_actions = self._session_actions[:5]
        while self.activity_body.count():
            item = self.activity_body.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for index, entry in enumerate(self._session_actions):
            if index:
                divider = QFrame()
                divider.setObjectName("ListDivider")
                divider.setFixedHeight(1)
                self.activity_body.addWidget(divider)
            self.activity_body.addWidget(SessionActionRow(*entry))
        # Keep the activity rows anchored to the top when the paired status
        # card is taller. This preserves a shared bottom edge without
        # stretching the individual rows or their separators.
        self.activity_body.addStretch(1)

    def show_raw_status(self) -> None:
        raw = str(self.current_state.get("raw") or "No authorized raw CU status is available yet.")
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Compute Units raw status"))
        dialog.setStyleSheet(application_stylesheet())
        enable_adaptive_dialog(
            dialog,
            preferred_width=820,
            preferred_height=560,
            minimum_width=480,
            minimum_height=360,
        )
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        text = QPlainTextEdit()
        text.setObjectName("OperationConsole")
        text.setReadOnly(True)
        text.setPlainText(raw)
        layout.addWidget(text, 1)
        close = QPushButton(tr("Close"))
        close.setProperty("compactAction", True)
        close.clicked.connect(dialog.accept)
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        localize_widget_tree(dialog)
        dialog.exec()

    def _show_info(self, title: str, message: str) -> None:
        InfoDialog(
            title,
            message,
            icon_name="info_blue",
            parent=self,
            eyebrow="COMPUTE UNITS",
            button_text="Close",
            notice="The current live table was not changed.",
            tone="blue",
        ).exec()

    def _show_error(self, title: str, message: str) -> None:
        InfoDialog(
            title,
            message,
            icon_name="warning_orange",
            parent=self,
            eyebrow="COMPUTE UNITS",
            button_text="Close",
            notice="The application did not report this operation as successful.",
            tone="red",
        ).exec()
