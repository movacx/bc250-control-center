from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    QThread,
    QTimer,
    pyqtSignal,
)
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
from ..components.page_widgets import (
    ConfirmDialog,
    ControlPageHeader,
    SectionCard,
)
from ..components.responsive import (
    clear_grid,
    configure_responsive_scroll_area,
    effective_viewport_width,
)
from ..components.widgets import (
    IconBadge,
    InfoDialog,
    QuickActionButton,
    apply_shadow,
    icon,
)
from ..core.compute_units_presenter import (
    CuStatePresentation,
    plan_cu_action_availability,
    present_compute_units_state,
)
from ..core.state import state_cache_for
from ..i18n import count_label, localize_widget_tree, tr, tr_format
from ..theme import COLORS, application_stylesheet

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

    def __init__(self, controller, parent: QWidget | None = None, *, activity_service=None):
        super().__init__(parent)
        self.setProperty("computeUnitsPage", True)
        self.controller = controller
        self.activity_service = activity_service
        self.current_state: dict = {}
        self._updates_active = False
        self._state_cache = state_cache_for(controller)
        self._worker: CuTask | None = None
        self._busy = False
        self._workspace_columns = 0
        self._status_columns = 0
        self._session_actions: list[tuple[str, str, str, str]] = []
        self._action_buttons: list[QPushButton] = []
        self._auto_sync_attempted = False
        self._background = BackgroundExecutor(self)
        self._event_sequence = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        self.scroll = scroll
        self.content = QWidget()
        configure_responsive_scroll_area(scroll, self.content)
        # Translated labels can have a large preferred width.  This page owns a
        # local scroller for its genuinely wide WGP matrix, so the outer page
        # must follow the viewport instead of expanding to translated hints.
        self.content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
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
            # Passive QAM snapshot polling must never throw away a WGP table
            # the player is currently assembling in the desktop editor.
            lambda state: self._apply_state(dict(state or {}), preserve_edits=True),
            lambda message: self.setToolTip(message),
        )
        self._passive_refresh_timer = QTimer(self)
        self._passive_refresh_timer.setInterval(2000)
        self._passive_refresh_timer.timeout.connect(self._poll_passive_cu_state)
        self._dependency_completion_timer: QTimer | None = None

    def _build_topology_card(self) -> SectionCard:
        card = SectionCard(
            "WGP / CU topology",
            "Select the WGP pairs to route on each shader-engine row. The table mirrors the official terminal editor while keeping the target visible before applying.",
            icon_name="compute_orange",
            icon_background=COLORS["orange_soft"],
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
        # Keep the complete 7-column routing matrix intact on compact windows,
        # but contain its horizontal overflow inside the matrix itself. Letting
        # the table dictate the page minimum width made every card and action
        # drift off-screen on handheld-sized and highly scaled desktops.
        self.topology_scroll = QScrollArea()
        self.topology_scroll.setObjectName("CuTopologyScroll")
        self.topology_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.topology_scroll.setWidgetResizable(True)
        self.topology_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.topology_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.topology_scroll.setMinimumWidth(0)
        self.topology_scroll.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.topology_scroll.setWidget(self.topology_table)
        table_height = self.topology_table.minimumSizeHint().height()
        scrollbar_height = self.topology_scroll.horizontalScrollBar().sizeHint().height()
        self.topology_scroll.setFixedHeight(table_height + scrollbar_height + 2)
        card.body.addWidget(self.topology_scroll)

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

        self.live_refresh_button = QPushButton(tr("Unlock / Sync"))
        self.live_refresh_button.setProperty("compactAction", True)
        self.live_refresh_button.setMinimumHeight(38)
        self.live_refresh_button.clicked.connect(self.refresh_authorized)

        self.discard_button = QPushButton(tr("Reset selection"))
        self.discard_button.setProperty("compactAction", True)
        self.discard_button.setMinimumHeight(38)
        self.discard_button.clicked.connect(self.discard_selection)
        selection_layout.addWidget(self.discard_button, 1, 1)

        self.apply_live_button = QPushButton(tr("Apply now"))
        self.apply_live_button.setObjectName("PrimaryAction")
        self.apply_live_button.setProperty("cuApplyAction", True)
        self.apply_live_button.setMinimumHeight(38)
        self.apply_live_button.setIcon(icon("rocket_blue"))
        self.apply_live_button.clicked.connect(self.apply_selected_table)
        selection_layout.addWidget(self.live_refresh_button, 1, 0)
        selection_layout.addWidget(self.apply_live_button, 1, 2)
        selection_layout.addWidget(self.selection_copy_widget, 0, 0, 1, 3)
        for column in range(3):
            selection_layout.setColumnStretch(column, 1)
        self._action_buttons.extend([self.live_refresh_button, self.discard_button, self.apply_live_button])
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
        )
        self.profiles_card = profiles
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
            "Save the selected WGP table and control the official systemd restore service without opening the terminal menu.",
            icon_name="app_blue",
            icon_background=COLORS["cyan_soft"],
        )
        self.persistence_card = persistence
        self.persistence_status = persistence.status
        action_grid = QGridLayout()
        self.persistence_actions_grid = action_grid
        action_grid.setContentsMargins(0, 0, 0, 0)
        action_grid.setHorizontalSpacing(8)
        action_grid.setVerticalSpacing(8)

        self.save_boot_button = self._action_button(
            "Save selection", "app_blue", self.save_boot_layout,
            tooltip="Apply the selected WGP table now and save it for boot.",
        )
        self.install_service_button = self._action_button(
            "Install service", "download_blue", self.install_service,
            tooltip="Install and enable the boot restore service.",
        )
        self.apply_saved_button = self._action_button(
            "Apply saved", "rocket_blue", self.apply_saved_layout,
            tooltip="Apply the WGP table already stored for boot; it ignores the current selection.",
        )
        self.remove_service_button = self._action_button(
            "Remove service", "power_gray", self.remove_service,
            danger=True, tooltip="Remove the boot restore service and its saved table.",
        )
        self.restore_factory_button = self._action_button(
            "Restore factory", "refresh_gray", self.restore_factory_now,
            tooltip="Restore the amdgpu factory WGP table now.",
        )
        self.install_umr_button = self._action_button(
            "Install UMR", "compute_blue", self.install_umr,
            tooltip="Install the register-access dependency required by the live manager.",
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
        # Any extra height belongs inside this card, above its action footer.
        # This keeps the right column flush with topology, including when the
        # register diagnostics expand or translated copy wraps onto more lines.
        persistence.body.addStretch(1)
        persistence.body.addLayout(action_grid)
        layout.addWidget(persistence, 1)
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

    def _build_activity_card(self) -> SectionCard:
        card = SectionCard(
            "Recent CU actions",
            "Changes made during this application session.",
            icon_name="activity_purple",
            icon_background=COLORS["purple_soft"],
        )
        self.activity_body = QVBoxLayout()
        card.add_header_button("Raw status", self.show_raw_status)
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
                self.workspace.addWidget(self.topology_card, 0, 0)
                self.workspace.addWidget(self.side_column, 0, 1)
                self.workspace.setColumnStretch(0, 7)
                self.workspace.setColumnStretch(1, 4)
            else:
                self.workspace.addWidget(self.topology_card, 0, 0, Qt.AlignmentFlag.AlignTop)
                self.workspace.addWidget(self.side_column, 1, 0, Qt.AlignmentFlag.AlignTop)
                self.workspace.setColumnStretch(0, 1)

        bottom_columns = 1
        if bottom_columns != self._status_columns or not self.bottom_grid.count():
            self._status_columns = bottom_columns
            self._clear_grid(self.bottom_grid)
            self.bottom_grid.addWidget(self.activity_card, 0, 0)
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
                    self.selection_layout.addWidget(self.selection_copy_widget, 0, 0, 1, 3)
                    self.selection_layout.addWidget(self.live_refresh_button, 1, 0)
                    self.selection_layout.addWidget(self.discard_button, 1, 1)
                    self.selection_layout.addWidget(self.apply_live_button, 1, 2)
                    for column in range(3):
                        self.selection_layout.setColumnStretch(column, 1)
                elif mode == "split":
                    self.selection_layout.addWidget(self.selection_copy_widget, 0, 0, 1, 3)
                    self.selection_layout.addWidget(self.live_refresh_button, 1, 0)
                    self.selection_layout.addWidget(self.discard_button, 1, 1)
                    self.selection_layout.addWidget(self.apply_live_button, 1, 2)
                    for column in range(3):
                        self.selection_layout.setColumnStretch(column, 1)
                else:
                    self.selection_layout.addWidget(self.selection_copy_widget, 0, 0)
                    self.selection_layout.addWidget(self.live_refresh_button, 1, 0)
                    self.selection_layout.addWidget(self.discard_button, 2, 0)
                    self.selection_layout.addWidget(self.apply_live_button, 3, 0)
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
        was_active = self._updates_active
        self._updates_active = bool(active)
        if self._updates_active:
            self._refresher.activate(fresh_for=5.0)
            if not self._passive_refresh_timer.isActive():
                self._passive_refresh_timer.start()
            if not was_active:
                self._auto_sync_attempted = False
                self._auto_initialize_live_state()
        else:
            self._refresher.set_active(False)
            self._passive_refresh_timer.stop()

    def _poll_passive_cu_state(self) -> None:
        """Pick up a new verified QAM snapshot without opening Polkit/UMR."""
        if self._updates_active and not self._busy:
            self._refresher.request()

    def _auto_initialize_live_state(self) -> None:
        """Load only cached state while the external backend is not root-owned."""
        if self._auto_sync_attempted:
            return
        self._auto_sync_attempted = True

        def tools_ready(payload: object) -> None:
            tools = dict(payload or {}) if isinstance(payload, dict) else {}
            if tools.get("cu_privileged_backend_ready"):
                self.current_state["privileged_backend_ready"] = True
            # Opening the page is strictly read-only.  Live routing requires
            # Polkit only after the user explicitly presses Unlock / Sync.
            self.refresh()

        def tools_failed(_message: str) -> None:
            self._auto_sync_attempted = False

        started = self._background.start(
            "compute-units-auto-initialize",
            self.controller.estado_herramientas_bc250,
            tools_ready,
            tools_failed,
        )
        if not started:
            self._auto_sync_attempted = False

    def refresh(self) -> None:
        """Load the last authorized snapshot without opening Polkit."""
        # AsyncRefresh delegates to state_cache.obtener_estado_cu_cache; this
        # passive path never opens an authorization flow.
        self._refresher.request()

    def refresh_authorized(self) -> None:
        if not self.current_state.get("privileged_backend_ready", False):
            reason = str(
                self.current_state.get("privileged_backend_reason")
                or "CU write actions are locked until a verified root-owned backend is installed."
            )
            self._record_action("Operation failed", reason, "red")
            self._show_error("Compute Units operation failed", reason)
            return
        self._run_task(
            "Reading live WGP routing",
            self.controller.obtener_estado_cu,
            success_message="Live CU topology refreshed",
            success_detail="SPI masks and amdgpu driver topology were read successfully.",
        )

    def _apply_state(self, state: dict, *, preserve_edits: bool = False) -> None:
        if not isinstance(state, dict):
            return
        presentation = self._apply_topology_snapshot(state, preserve_edits=preserve_edits)
        self._render_cu_presentation(presentation)
        self._selection_changed(self.topology_table.current_masks())

    def _apply_topology_snapshot(
        self,
        state: dict,
        *,
        preserve_edits: bool,
    ) -> CuStatePresentation:
        previous_target = self.topology_table.current_masks()
        had_pending_edits = self._pending_wgp_count(previous_target) > 0
        self.current_state = dict(state)
        self.topology_table.set_state(self.current_state)
        if preserve_edits and had_pending_edits:
            self.topology_table.set_masks(previous_target, emit=False)
        self.register_panel.set_state(
            self._live_masks(),
            self.topology_table.driver_masks,
            self.topology_table.cc_values,
        )
        if preserve_edits and had_pending_edits:
            self.register_panel.set_target_masks(self.topology_table.current_masks())
        presentation = present_compute_units_state(
            self.current_state,
            live_masks=self._live_masks(),
        )
        if presentation.mask_count_mismatch:
            logger.warning(
                "CU state reported %s active CUs but live masks contain %s CUs; using masks",
                self.current_state.get("active_cus"),
                presentation.active_cus,
            )
            self.current_state["active_cus"] = presentation.active_cus
            self.current_state["routed_wgps"] = presentation.routed_wgps
        return presentation

    def _render_cu_presentation(self, presentation: CuStatePresentation) -> None:
        active = presentation.active_cus
        routed = presentation.routed_wgps
        self.summary_strip.items[0].set_values(f"{active} / 40" if presentation.verified else tr("Not verified"), count_label(routed, "routed WGP") if presentation.verified else tr("Not verified"), progress=active)
        self.summary_strip.items[1].set_values(tr(presentation.mode_short), tr("live SPI table classification"))
        self.summary_strip.items[2].set_values(f"{routed} / 20" if presentation.verified else tr("Not verified"), tr("2 CUs per WGP"))
        service_name = (
            "bc250-cu-live-manager"
            if presentation.init_manager == "openrc"
            else "bc250-cu-live-manager.service"
            if presentation.init_manager == "systemd"
            else tr("No supported persistence backend")
        )
        self.summary_strip.items[3].set_values(
            tr(presentation.service.title()), service_name
        )
        self.summary_strip.items[4].set_values(tr(presentation.boot_sync), tr(presentation.persistence_detail))

        if self.topology_status is not None:
            self.topology_status.setText(tr(presentation.topology_status))
            self.topology_status.set_tone(presentation.topology_tone)
        if self.persistence_status is not None:
            self.persistence_status.setText(tr(presentation.persistence_status))
            self.persistence_status.set_tone(presentation.persistence_tone)

        live_spi = presentation.verified and (
            presentation.fresh or presentation.source_kind == "quick_access"
        )
        self.live_refresh_button.setText(
            tr("Refresh live topology" if live_spi else "Unlock / Sync")
        )
        self.profile_note.setText(tr_format("Current selection: {mode}", mode=tr(presentation.mode)))

    def _selection_changed(self, masks) -> None:
        masks = self.topology_table._normalize_masks(masks, self.topology_table.current_masks())
        self.register_panel.set_target_masks(masks)
        target = self._target_cus_from_masks(masks)
        pending = self._pending_wgp_count(masks)
        state_verified = self._has_authorized_state()
        self.selection_title.setText(tr_format("Target: {count} / 40 CUs", count=target) if state_verified else tr("Target: Not verified"))
        if not state_verified:
            self.selection_detail.setText(tr("Authorize a live refresh before applying WGP changes."))
        elif not self.current_state.get("privileged_backend_ready", False):
            self.selection_detail.setText(
                tr("CU write actions are locked until a verified root-owned backend is installed.")
            )
        elif pending:
            self.selection_detail.setText(tr_format("{pairs} differ from the last authorized live table.", pairs=count_label(pending, "WGP pair")))
        else:
            self.selection_detail.setText(tr("No pending WGP changes."))
        if tuple(masks) == FULL_MASKS:
            self.profile_note.setText(tr("Current selection: Full 40 CUs"))
        elif tuple(masks) == tuple(self.topology_table.driver_masks):
            self.profile_note.setText(tr("Current selection: Factory driver topology"))
        else:
            self.profile_note.setText(tr_format("Current selection: Custom {count} CUs", count=target))
        self._update_action_availability(pending_wgps=pending)

    def _load_layout(self, masks, message: str) -> None:
        self.topology_table.set_masks(masks)
        self._record_action("Layout loaded", message, "blue")

    def load_factory_layout(self) -> None:
        masks = self.topology_table.driver_masks if any(self.topology_table.driver_masks) else list(FACTORY_MASKS)
        self._load_layout(masks, "Factory driver WGP topology loaded for review.")

    def load_custom_layout(self) -> None:
        self.discard_selection(record=False)
        self._record_action("Custom editor ready", "Use the 20 WGP buttons to build a custom live table.", "purple")

    def discard_selection(self, *, record: bool = True) -> None:
        self.topology_table.set_masks(self._live_masks())
        if record:
            self._record_action("Selection reset", "The editor returned to the last verified live WGP table.", "gray")

    def _live_masks(self) -> list[int]:
        return self.topology_table._normalize_masks(self.current_state.get("masks"), self.topology_table.baseline_masks)

    @staticmethod
    def _target_cus_from_masks(masks) -> int:
        return sum(int(mask).bit_count() * 2 for mask in masks)

    def _pending_wgp_count(self, masks=None) -> int:
        target = self.topology_table._normalize_masks(masks or self.topology_table.current_masks(), self.topology_table.current_masks())
        live = self._live_masks()
        return sum((int(target[row]) ^ int(live[row])).bit_count() for row in range(4))

    def apply_selected_table(self) -> None:
        masks = self.topology_table.current_masks()
        pending = self._pending_wgp_count(masks)
        if pending <= 0:
            self._show_info("No pending changes", "The selected WGP table already matches the last authorized live state.")
            return
        target_cus = self._target_cus_from_masks(masks)
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
            "factory_repair",
            "Restore factory 24 CU routing",
            "The live SPI table will be rebuilt from the amdgpu boot CU topology. Any saved Compute Units boot service and its configuration will be removed first, so an obsolete /usr/local/bin service cannot restore a broken layout after reboot.",
            "Restore factory routing",
            tone="orange",
        )

    def save_boot_layout(self) -> None:
        masks = self.topology_table.current_masks()
        target_cus = self._target_cus_from_masks(masks)
        pending = self._pending_wgp_count(masks)
        dialog = ConfirmDialog(
            "Save selected boot table",
            "The selected WGP table will be applied now, verified, and saved to /etc/bc250-cu-live-manager.conf. The boot service is installed separately.",
            summary=(
                ("Target", f"{target_cus} / 40 CUs"),
                ("Changed WGP pairs", str(pending)),
                ("Masks", ", ".join(f"0x{mask:02x}" for mask in masks)),
                ("Boot sync", str(self.current_state.get("boot_sync") or "Unknown")),
            ),
            confirm_text="Save selection",
            tone="orange" if pending else "blue",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_task(
            "Saving selected WGP boot table",
            lambda: self.controller.guardar_tabla_cu(masks),
            success_message="Boot layout saved",
            success_detail=f"Verified and saved target: {target_cus} / 40 CUs.",
            event_action="save_boot",
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
        pending = self._pending_wgp_count(self.topology_table.current_masks())
        if pending > 0:
            self._show_info(
                "Selection has pending changes",
                "Use Apply now or Save selection first, or reset the selection before loading the saved boot table.",
            )
            return
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
            "factory_repair": ("Factory routing restored", "The boot restore service was removed and the live table now follows the amdgpu boot topology."),
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
            lambda: self.controller.instalar_dependencias_bc250(
                components={"cu_manager"}
            ),
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
                # Save/install actions are authoritative even when an older
                # live-manager revision omits persistence metadata from its
                # final dashboard.  Keep the action transition visible so the
                # next step (Install service) is enabled immediately after a
                # successful Save selection.
                result = dict(result)
                if event_action == "save_boot":
                    result.update(boot_sync="Current table saved", boot_sync_key="saved")
                elif event_action == "install_service":
                    result.update(service="Enabled", service_installed=True, service_enabled=True)
                self._apply_state(result, preserve_edits=False)
                self._refresher.adopt_authoritative(dict(result), already_rendered=True)
            elif event_action in {"prepare_tools", "install_umr"}:
                self._watch_dependency_preparation(result)
            self._record_action(success_message, success_detail, "green")
            self._register_event(event_action, success_message, success_detail)

        def failed(message: str) -> None:
            if str(message or "").strip() == "CU_AUTHORIZATION_CANCELLED":
                self._set_busy(False, "")
                self._record_action(
                    "Live refresh canceled",
                    "Administrator authorization was canceled. The last verified CU state remains unchanged.",
                    "blue",
                )
                return
            # Keep the last authorized masks visible, but do not continue to
            # label them as a fresh live read after a failed write/verification.
            self.current_state["fresh"] = False
            self._set_busy(False, "")
            self._record_action("Operation failed", message, "red")
            self._show_error("Compute Units operation failed", message)

        worker.succeeded.connect(complete)
        worker.failed.connect(failed)
        worker.finished.connect(self._worker_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _watch_dependency_preparation(self, result: object) -> None:
        """Refresh the real CU table when the visible installer exits cleanly.

        Terminal preparation is intentionally asynchronous. Its launcher
        returns before the manager exists, which previously left the page with
        only its placeholder state. A successful terminal status triggers one
        authorized read of the current WGP table; it never restores or writes
        any routing on its own.
        """
        status_file = str(getattr(result, "status_file", "") or "")
        if not status_file:
            return
        if self._dependency_completion_timer is not None:
            self._dependency_completion_timer.stop()
            self._dependency_completion_timer.deleteLater()
        timer = QTimer(self)
        timer.setInterval(700)
        started = datetime.now()

        def check_completion() -> None:
            path = Path(status_file)
            if not path.is_file():
                if (datetime.now() - started).total_seconds() > 60 * 60:
                    timer.stop()
                return
            try:
                code = path.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                return
            timer.stop()
            if code == "0":
                self._auto_sync_attempted = True
                self._state_cache.invalidate("tools", "cu_cache")
                self._record_action(
                    "Compute Units prepared",
                    "Live Manager was detected; reading the current WGP topology without changing hardware.",
                    "green",
                )
                try:
                    tools = dict(self.controller.estado_herramientas_bc250() or {})
                except Exception as error:
                    self._record_action(
                        "Operation failed",
                        str(error),
                        "red",
                    )
                    self.refresh()
                    return
                ready = bool(tools.get("cu_privileged_backend_ready"))
                self.current_state["privileged_backend_ready"] = ready
                self.current_state["privileged_backend_reason"] = str(
                    tools.get("cu_privileged_backend_reason") or ""
                )
                if ready:
                    self.refresh_authorized()
                else:
                    self._record_action(
                        "Operation failed",
                        self.current_state["privileged_backend_reason"]
                        or "CU write actions are locked until a verified root-owned backend is installed.",
                        "red",
                    )
                    self.refresh()
            else:
                self._record_action(
                    "Compute Units preparation failed",
                    f"Dependency preparation exited with code {code or 'unknown'}; current WGP selection was not changed.",
                    "red",
                )

        timer.timeout.connect(check_completion)
        self._dependency_completion_timer = timer
        timer.start()

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
                self.topology_status.setText(tr(label) if label else tr("Working"))
                self.topology_status.set_tone("blue")
        else:
            self._apply_state(self.current_state, preserve_edits=True)
        self._selection_changed(self.topology_table.current_masks())
        self._update_action_availability()

    def _update_action_availability(self, *, pending_wgps: int | None = None) -> None:
        pending = (
            self._pending_wgp_count(self.topology_table.current_masks())
            if pending_wgps is None
            else max(0, int(pending_wgps))
        )
        availability = plan_cu_action_availability(
            self.current_state,
            pending_wgps=pending,
            busy=self._busy,
        )
        self.install_umr_button.setEnabled(availability.install_umr)
        self.save_boot_button.setEnabled(availability.save_boot)
        self.install_service_button.setEnabled(availability.install_service)
        self.apply_saved_button.setEnabled(availability.apply_saved)
        self.remove_service_button.setEnabled(availability.remove_service)
        self.restore_factory_button.setEnabled(availability.restore_factory)
        self.discard_button.setEnabled(availability.discard)
        self.apply_live_button.setEnabled(availability.apply_live)

    def _has_authorized_state(self) -> bool:
        masks = self.current_state.get("masks")
        return (
            bool(self.current_state.get("available"))
            and isinstance(masks, (list, tuple))
            and len(masks) == 4
        )

    def _register_event(self, action: str, title: str, detail: str) -> None:
        self._event_sequence += 1
        payload = {
            "accion": action,
            "active_cus": self.current_state.get("active_cus"),
        }

        def operation() -> object:
            if self.activity_service is None:
                raise RuntimeError("ComputeUnitsPage requires an activity service to record events")
            self.activity_service.record(
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
        normalized = str(message or "").lower()
        display_message = message
        if "helper_version_mismatch" in normalized:
            notice = "The installed privileged helper does not match this application build."
        elif "game_mode_context" in normalized:
            notice = "The helper could not verify the Game Mode launch context."
        elif "cu_umr_" in normalized or "game mode was verified" in normalized:
            notice = "Game Mode was verified; the CU-specific UMR backend failed."
        elif "cu_backend_missing" in normalized:
            notice = "A Compute Units dependency is missing or unavailable."
        else:
            notice = "The application did not report this operation as successful."
        stale_service = (
            "bc250-cu-live-manager" in normalized
            and (
                "/usr/local/bin" in normalized
                or "no such file or directory" in normalized
                or "bestand of map bestaat niet" in normalized
            )
        )
        recovery = (
            "sudo /bin/sh -c 'if [ -x /var/lib/bc250-control-center/bc250-cu-live-manager ]; then "
            "exec /var/lib/bc250-control-center/bc250-cu-live-manager --yes uninstall-service; "
            "else exec /usr/libexec/bc250-control-center/bc250-cu-live-manager --yes uninstall-service; fi'"
            if stale_service else ""
        )
        if stale_service:
            display_message = (
                "The installed Compute Units service points to a manager that no longer exists. "
                "The operation was stopped before changing the hardware."
            )
            notice = (
                "A stale Compute Units boot service points to a missing manager. Copy the recovery command, run it in a terminal, then reboot. "
                "You can also use Restore factory: it removes the stale service and restores the 24-CU factory topology."
            )
        InfoDialog(
            title,
            display_message,
            icon_name="warning_orange",
            parent=self,
            eyebrow="COMPUTE UNITS",
            button_text="Close",
            notice=notice,
            tone="red",
            copy_text=recovery,
            copy_button_text="Copy recovery command",
        ).exec()
