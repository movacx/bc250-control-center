"""Compact voltage-curve drawer for the desktop GPU page.

A narrow side panel in the module language used everywhere else: a summary of
the pending change read like the dashboard's readings, the curve boost levels,
and the frequency/voltage table where custom values are edited. The V/F chart
it used to carry was dropped: it repeated the table in a form that could not
be read to the millivolt, at the cost of half the panel's height and width.
"""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtWidgets import (
    QPushButton as NativePushButton,
)

from bc250cc.application.gpu.voltage_table import VoltageTableRow
from bc250cc.domain.gpu.voltage_profiles import (
    CUSTOM_VOLTAGE_MAX_MV,
    CUSTOM_VOLTAGE_MIN_MV,
)

from ..i18n import tr
from .buttons import WrappingButton as QPushButton
from .widgets import icon

#: Table columns, shared by the header row and every data row so the numbers
#: line up under their titles at any drawer width.
COLUMN_FREQUENCY = 84
COLUMN_CURRENT = 64
COLUMN_SELECTED = 96
COLUMN_DELTA = 44
#: Narrow enough to leave the GPU page readable beside it.
DRAWER_WIDTH = (420, 500)


class _SummaryValue(QWidget):
    """One figure of the pending change: caption above, value below."""

    def __init__(self, caption: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(1)
        self.caption = QLabel(tr(caption))
        self.caption.setProperty("voltageDrawerStatCaption", True)
        self.value = QLabel("--")
        self.value.setProperty("voltageDrawerStatValue", True)
        box.addWidget(self.caption)
        box.addWidget(self.value)


def _separator(parent: QWidget | None = None) -> QFrame:
    line = QFrame(parent)
    line.setFrameShape(QFrame.Shape.NoFrame)
    line.setFixedHeight(1)
    line.setProperty("voltageDrawerSeparator", True)
    return line


class _VoltageSpinBox(QSpinBox):
    """A voltage field the mouse wheel only changes once it has been chosen.

    The table scrolls under the pointer; a wheel turn that happened to pass
    over a field used to change that point's voltage instead of scrolling.
    """

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if not self.hasFocus():
            event.ignore()
            return
        super().wheelEvent(event)


class _DrawerCurveRow(QFrame):
    voltage_changed = pyqtSignal(int, int)

    def __init__(
        self,
        row: VoltageTableRow,
        *,
        custom_mode: bool,
        read_only: bool,
        first: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.frequency = int(row.frequency)
        self.original = row.original
        self.setProperty("voltageDrawerCurveRow", True)
        self.setProperty("rowFirst", bool(first))
        self.setMinimumHeight(36)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(10)

        frequency = QLabel(f"{row.frequency} MHz")
        frequency.setProperty("voltageDrawerFrequency", True)
        frequency.setMinimumWidth(COLUMN_FREQUENCY)
        layout.addWidget(frequency, 1)

        current = QLabel(self._current_text(row))
        current.setProperty("voltageDrawerCurrent", True)
        current.setFixedWidth(COLUMN_CURRENT)
        current.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(current)
        self.current_label = current
        self.read_only = bool(read_only)

        self.editor: QSpinBox | None = None
        self.proposed_label: QLabel | None = None
        if custom_mode and row.custom_available:
            editor = _VoltageSpinBox()
            editor.setProperty("voltageDrawerEditor", True)
            editor.setRange(CUSTOM_VOLTAGE_MIN_MV, CUSTOM_VOLTAGE_MAX_MV)
            editor.setSingleStep(5)
            editor.setSuffix(" mV")
            editor.setValue(int(row.editor_value))
            editor.setFixedWidth(COLUMN_SELECTED)
            editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
            editor.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            editor.valueChanged.connect(self._editor_changed)
            self.editor = editor
            layout.addWidget(editor)
        else:
            proposed = QLabel(self._proposed_text(row))
            proposed.setProperty("voltageDrawerTarget", True)
            proposed.setFixedWidth(COLUMN_SELECTED)
            proposed.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            layout.addWidget(proposed)
            self.proposed_label = proposed

        self.delta = QLabel(tr("Read only") if read_only else self._delta_text(row.added))
        self.delta.setProperty("voltageDrawerDelta", True)
        self.delta.setProperty("deltaTone", self._delta_tone(row.added))
        self.delta.setFixedWidth(COLUMN_DELTA)
        self.delta.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        layout.addWidget(self.delta)

    @staticmethod
    def _current_text(row: VoltageTableRow) -> str:
        return f"{row.current} mV" if row.current else tr("Not set")

    @staticmethod
    def _proposed_text(row: VoltageTableRow) -> str:
        return f"{row.proposed} mV" if row.proposed is not None else tr("Unchanged")

    def update_row(self, row: VoltageTableRow) -> None:
        """Show new values without replacing any widget.

        A refresh arrives every few seconds. Rebuilding the row took the spin
        box being edited away from under the user, with its focus and any
        half-typed value; a field that has the focus keeps what it shows.
        """
        self.original = row.original
        self.current_label.setText(self._current_text(row))
        if self.editor is not None:
            if self.editor.value() != int(row.editor_value) and not self.editor.hasFocus():
                self.editor.blockSignals(True)
                self.editor.setValue(int(row.editor_value))
                self.editor.blockSignals(False)
            added = None if self.original is None else int(self.editor.value()) - int(self.original)
        else:
            if self.proposed_label is not None:
                self.proposed_label.setText(self._proposed_text(row))
            added = row.added
        if not self.read_only:
            self._show_delta(added)

    def _show_delta(self, added: int | None) -> None:
        self.delta.setText(self._delta_text(added))
        self.delta.setProperty("deltaTone", self._delta_tone(added))
        self.delta.style().unpolish(self.delta)
        self.delta.style().polish(self.delta)

    @staticmethod
    def _delta_text(value: int | None) -> str:
        if value is None:
            return "—"
        if value > 0:
            return f"+{value}"
        if value < 0:
            return str(value)
        return "—"

    @staticmethod
    def _delta_tone(value: int | None) -> str:
        if value is None:
            return "muted"
        if value > 0:
            return "raised"
        if value < 0:
            return "lowered"
        return "default"

    def _editor_changed(self, value: int) -> None:
        added = None if self.original is None else int(value) - int(self.original)
        self._show_delta(added)
        self.voltage_changed.emit(self.frequency, int(value))


class VoltageLabDrawer(QWidget):
    """Right-side laboratory surface; it delegates every write to the GPU page."""

    close_requested = pyqtSignal()
    profile_requested = pyqtSignal(int)
    custom_voltage_changed = pyqtSignal(int, int)
    apply_requested = pyqtSignal()
    restore_requested = pyqtSignal()

    PROFILE_LEVELS = (1, 2, 3, -1)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("VoltageLabDrawerOverlay")
        self.setProperty("voltageLabDrawerOverlay", True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.hide()
        self._last_focus: QWidget | None = None
        self._selected_level = 1
        self._editors: dict[int, QSpinBox] = {}
        self._curve_signature: tuple | None = None
        self._profile_columns = 0
        self._footer_horizontal: bool | None = None

        self.drawer = QFrame(self)
        self.drawer.setObjectName("VoltageLabDrawer")
        self.drawer.setProperty("voltageLabDrawer", True)
        root = QVBoxLayout(self.drawer)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- header ----------------------------------------------------
        header = QHBoxLayout()
        header.setContentsMargins(18, 15, 18, 15)
        header.setSpacing(12)
        self.close_button = QPushButton("")
        self.close_button.setObjectName("VoltageDrawerClose")
        self.close_button.setProperty("voltageDrawerClose", True)
        self.close_button.setProperty("gamepadEntry", True)
        self.close_button.setProperty("gamepadCancel", True)
        self.close_button.setAccessibleName(tr("Close GPU voltage curve"))
        self.close_button.setIcon(icon("collapse_gray"))
        self.close_button.setFixedSize(32, 32)
        self.close_button.clicked.connect(self.close_animated)
        header.addWidget(self.close_button)
        title_host = QWidget()
        title_layout = QVBoxLayout(title_host)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(1)
        title = QLabel(tr("GPU voltage curve"))
        title.setProperty("voltageDrawerTitle", True)
        subtitle = QLabel(tr("Choose a safe boost or edit the active points"))
        subtitle.setWordWrap(True)
        subtitle.setProperty("voltageDrawerSubtitle", True)
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        header.addWidget(title_host, 1)
        root.addLayout(header)
        root.addWidget(_separator())

        # --- compatibility note (Oberon only) --------------------------
        self.compatibility_note = QFrame()
        self.compatibility_note.setProperty("voltageDrawerCompatibility", True)
        compatibility_layout = QVBoxLayout(self.compatibility_note)
        compatibility_layout.setContentsMargins(18, 12, 18, 12)
        compatibility_layout.setSpacing(3)
        compatibility_title = QLabel(tr("Oberon compatibility mode"))
        compatibility_title.setProperty("voltageDrawerCompatibilityTitle", True)
        compatibility_text = QLabel(
            tr(
                "Oberon uses two YAML endpoints. They are shown below for reference; "
                "curve editing is unavailable for this governor."
            )
        )
        compatibility_text.setProperty("voltageDrawerCompatibilityText", True)
        compatibility_text.setWordWrap(True)
        compatibility_layout.addWidget(compatibility_title)
        compatibility_layout.addWidget(compatibility_text)
        self.compatibility_note.hide()
        root.addWidget(self.compatibility_note)

        # --- summary --------------------------------------------------
        # What will change if this is applied, before any table row is read.
        summary = QWidget()
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(18, 12, 18, 12)
        summary_layout.setSpacing(12)
        self.summary_changed = _SummaryValue("Points changed")
        self.summary_peak = _SummaryValue("Highest voltage")
        self.summary_added = _SummaryValue("Above governor default")
        for item in (self.summary_changed, self.summary_peak, self.summary_added):
            summary_layout.addWidget(item, 1)
        root.addWidget(summary)
        root.addWidget(_separator())

        # --- presets ---------------------------------------------------
        self.profiles_card = QWidget()
        profiles_layout = QVBoxLayout(self.profiles_card)
        profiles_layout.setContentsMargins(18, 14, 18, 14)
        profiles_layout.setSpacing(8)
        profiles_title = QLabel(tr("Curve boost"))
        profiles_title.setProperty("voltageDrawerSectionTitle", True)
        profiles_layout.addWidget(profiles_title)
        self.profile_grid = QGridLayout()
        self.profile_grid.setContentsMargins(0, 0, 0, 0)
        self.profile_grid.setHorizontalSpacing(7)
        self.profile_grid.setVerticalSpacing(7)
        self.profile_group = QButtonGroup(self)
        self.profile_group.setExclusive(True)
        self.profile_buttons: dict[int, NativePushButton] = {}
        for level in self.PROFILE_LEVELS:
            custom = level == -1
            descriptions = {1: "Gentle", 2: "Moderate", 3: "High"}
            button = NativePushButton(
                tr("Custom\nEdit active points")
                if custom
                else f"+{level * 10} mV\n{tr(descriptions[level])}"
            )
            button.setCheckable(True)
            button.setFixedHeight(46)
            button.setProperty("voltageDrawerProfile", True)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.clicked.connect(
                lambda checked, value=level: self._choose_profile(value) if checked else None
            )
            self.profile_group.addButton(button)
            self.profile_buttons[level] = button
        profiles_layout.addLayout(self.profile_grid)
        self.profile_detail = QLabel(
            tr("Select a level to preview the exact curve before applying.")
        )
        self.profile_detail.setProperty("voltageDrawerDetail", True)
        self.profile_detail.setWordWrap(True)
        profiles_layout.addWidget(self.profile_detail)
        root.addWidget(self.profiles_card)
        self.profiles_separator = _separator()
        root.addWidget(self.profiles_separator)

        # --- voltage table ---------------------------------------------
        table_host = QWidget()
        table_layout = QVBoxLayout(table_host)
        table_layout.setContentsMargins(18, 12, 18, 0)
        table_layout.setSpacing(0)
        columns = QHBoxLayout()
        columns.setContentsMargins(4, 0, 7, 6)
        columns.setSpacing(10)
        frequency_column = QLabel(tr("Frequency"))
        frequency_column.setProperty("voltageDrawerColumn", True)
        frequency_column.setMinimumWidth(COLUMN_FREQUENCY)
        columns.addWidget(frequency_column, 1)
        current_column = QLabel(tr("Current"))
        current_column.setProperty("voltageDrawerColumn", True)
        current_column.setFixedWidth(COLUMN_CURRENT)
        current_column.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        columns.addWidget(current_column)
        self.selected_column = QLabel(tr("Selected"))
        self.selected_column.setProperty("voltageDrawerColumn", True)
        self.selected_column.setFixedWidth(COLUMN_SELECTED)
        self.selected_column.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        columns.addWidget(self.selected_column)
        delta_column = QLabel("Δ")
        delta_column.setProperty("voltageDrawerColumn", True)
        delta_column.setFixedWidth(COLUMN_DELTA)
        delta_column.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        columns.addWidget(delta_column)
        table_layout.addLayout(columns)

        scroll = QScrollArea()
        scroll.setObjectName("VoltageLabDrawerScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("VoltageLabDrawerBody")
        self.curve_rows = QVBoxLayout(body)
        self.curve_rows.setContentsMargins(0, 0, 3, 0)
        self.curve_rows.setSpacing(0)
        self.curve_rows.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(body)
        table_layout.addWidget(scroll, 1)
        root.addWidget(table_host, 1)
        root.addWidget(_separator())

        # --- footer ------------------------------------------------------
        self.footer = QWidget()
        self.footer_layout = QGridLayout(self.footer)
        self.footer_layout.setContentsMargins(18, 12, 18, 14)
        self.footer_layout.setHorizontalSpacing(10)
        self.footer_layout.setVerticalSpacing(8)
        # The one-line summary is kept as data for tests and accessibility;
        # the figures above show the same thing in a readable form.
        self.footer_summary = QLabel("")
        self.footer_summary.setProperty("voltageDrawerSummary", True)
        self.footer_summary.hide()
        self.restore_button = QPushButton(tr("Restore governor defaults"))
        self.restore_button.setProperty("voltageDrawerSecondary", True)
        self.restore_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.restore_button.clicked.connect(self.restore_requested)
        self.apply_button = QPushButton(tr("Review and apply"))
        self.apply_button.setObjectName("VoltageDrawerApply")
        self.apply_button.setProperty("voltageDrawerApply", True)
        self.apply_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.apply_button.setIcon(icon("bolt_blue"))
        self.apply_button.clicked.connect(self.apply_requested)
        root.addWidget(self.footer)

        self._animation = QPropertyAnimation(self.drawer, b"geometry", self)
        self._animation.setDuration(170)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._reflow_controls(self._drawer_rect().width())
        self.set_profile(1)

    # ------------------------------------------------------------------
    def set_profile(self, level: int) -> None:
        level = int(level)
        if level not in self.profile_buttons:
            level = 1
        self._selected_level = level
        for value, button in self.profile_buttons.items():
            button.setChecked(value == level)

    def selected_level(self) -> int:
        return self._selected_level

    def set_oberon_mode(self, enabled: bool) -> None:
        read_only = bool(enabled)
        self.compatibility_note.setVisible(read_only)
        self.profiles_card.setVisible(not read_only)
        self.profiles_separator.setVisible(not read_only)
        self.footer.setVisible(not read_only)
        self.selected_column.setText(tr("Configured" if read_only else "Selected"))

    def _choose_profile(self, level: int) -> None:
        self._selected_level = int(level)
        self.set_profile(self._selected_level)
        self.profile_requested.emit(self._selected_level)

    def set_curve(
        self,
        rows: Sequence[VoltageTableRow],
        *,
        custom_mode: bool,
        detail: str,
        apply_enabled: bool,
        read_only: bool = False,
    ) -> None:
        # Rows are rebuilt only when the table itself changes: other points,
        # or a switch into or out of custom editing. New values are written
        # into the rows already there.
        signature = (
            tuple((int(row.frequency), bool(row.custom_available)) for row in rows),
            bool(custom_mode),
            bool(read_only),
        )
        if signature == self._curve_signature:
            for index, row in enumerate(rows):
                widget = self.curve_rows.itemAt(index).widget()
                if isinstance(widget, _DrawerCurveRow):
                    widget.update_row(row)
        else:
            while self.curve_rows.count():
                item = self.curve_rows.takeAt(0)
                if item.widget() is not None:
                    item.widget().deleteLater()
            self._editors = {}
            for index, row in enumerate(rows):
                widget = _DrawerCurveRow(
                    row,
                    custom_mode=custom_mode,
                    read_only=read_only,
                    first=index == 0,
                )
                widget.voltage_changed.connect(self.custom_voltage_changed)
                self.curve_rows.addWidget(widget)
                if widget.editor is not None:
                    self._editors[int(row.frequency)] = widget.editor
            self._curve_signature = signature
        self.profile_detail.setText(str(detail))
        self.apply_button.setEnabled(bool(apply_enabled))
        self._refresh_summary(rows)

    def _refresh_summary(self, rows: Sequence[VoltageTableRow]) -> None:
        proposed = [row.proposed for row in rows if row.proposed is not None]
        changed = sum(
            1
            for row in rows
            if row.proposed is not None and row.current and int(row.proposed) != int(row.current)
        )
        added = [row.added for row in rows if row.added is not None]
        parts = [
            tr("{count} points changed").format(count=changed)
            if changed != 1
            else tr("1 point changed")
        ]
        if proposed:
            parts.append(tr("peak {value} mV").format(value=max(proposed)))
        if added:
            top = max(added)
            parts.append(tr("max {value} mV").format(value=f"+{top}" if top > 0 else top))
        self.footer_summary.setText(" · ".join(parts))
        self.summary_changed.value.setText(str(changed))
        self.summary_peak.value.setText(f"{max(proposed)} mV" if proposed else "--")
        if added:
            top = max(added)
            self.summary_added.value.setText(f"+{top} mV" if top > 0 else f"{top} mV")
        else:
            self.summary_added.value.setText("--")

    def custom_values(self) -> dict[int, int]:
        return {
            frequency: int(editor.value())
            for frequency, editor in self._editors.items()
        }

    def editors(self) -> tuple[QSpinBox, ...]:
        return tuple(self._editors.values())

    def is_open(self) -> bool:
        return self.isVisible()

    # ------------------------------------------------------------------
    def show_animated(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self._last_focus = QApplication.focusWidget()
        self.setGeometry(parent.rect())
        self.show()
        self.raise_()
        end = self._drawer_rect()
        self._reflow_controls(end.width())
        start = end.translated(end.width(), 0)
        self._animation.stop()
        try:
            self._animation.finished.disconnect(self._finish_close)
        except TypeError:
            pass
        self._animation.setStartValue(start)
        self._animation.setEndValue(end)
        self._animation.start()
        QTimer.singleShot(self._animation.duration() + 20, self._focus_close_button)

    def _focus_close_button(self) -> None:
        try:
            self.close_button.setFocus(Qt.FocusReason.OtherFocusReason)
        except RuntimeError:
            # The delayed callback can outlive a drawer destroyed by a page
            # refresh or application shutdown.
            pass

    def close_animated(self) -> None:
        if not self.isVisible():
            return
        start = self.drawer.geometry()
        end = start.translated(start.width(), 0)
        self._animation.stop()
        self._animation.setStartValue(start)
        self._animation.setEndValue(end)
        try:
            self._animation.finished.disconnect()
        except TypeError:
            pass
        self._animation.finished.connect(self._finish_close)
        self._animation.start()

    def _finish_close(self) -> None:
        self.hide()
        focus = self._last_focus
        if isinstance(focus, QWidget):
            try:
                focus.setFocus(Qt.FocusReason.OtherFocusReason)
            except RuntimeError:
                pass
        self.close_requested.emit()

    def _bottom_reserve(self) -> int:
        """Room for the controller legend, which floats over the window bottom.

        The drawer's own buttons sit at its bottom edge; with a controller
        connected the legend covered them.
        """
        window = self.window()
        if window is None:
            return 0
        bar = window.findChild(QFrame, "GamepadHintBar")
        if bar is None or not bar.isVisible():
            return 0
        return bar.height() + 12

    def _drawer_rect(self) -> QRect:
        horizontal_margin = 3
        top_margin = 8
        bottom_margin = self._bottom_reserve()
        available = max(0, self.width() - (horizontal_margin * 2))
        narrow, wide = DRAWER_WIDTH
        if self.width() <= narrow + 120:
            width = available
        else:
            width = min(wide, max(narrow, round(self.width() * 0.36)))
        right_offset = 2
        return QRect(
            max(horizontal_margin, self.width() - horizontal_margin - width) + right_offset,
            top_margin,
            width,
            max(0, self.height() - top_margin - bottom_margin),
        )

    def _reflow_controls(self, width: int) -> None:
        profile_columns = 4 if int(width) >= 640 else (2 if int(width) >= 300 else 1)
        if profile_columns != self._profile_columns:
            self._profile_columns = profile_columns
            while self.profile_grid.count():
                self.profile_grid.takeAt(0)
            for index, button in enumerate(self.profile_buttons.values()):
                row, column = divmod(index, profile_columns)
                button.setProperty("gamepadHorizontalGroup", f"voltage-level-{row}")
                button.setProperty("gamepadHorizontalIndex", column)
                self.profile_grid.addWidget(button, row, column)
            for column in range(4):
                self.profile_grid.setColumnStretch(
                    column, 1 if column < profile_columns else 0
                )

        footer_horizontal = int(width) >= 380
        if footer_horizontal != self._footer_horizontal:
            self._footer_horizontal = footer_horizontal
            while self.footer_layout.count():
                self.footer_layout.takeAt(0)
            if footer_horizontal:
                self.footer_layout.addWidget(self.restore_button, 0, 0)
                self.footer_layout.addWidget(self.apply_button, 0, 1)
            else:
                self.footer_layout.addWidget(self.restore_button, 0, 0)
                self.footer_layout.addWidget(self.apply_button, 1, 0)
            self.footer_layout.setColumnStretch(0, 1)
            self.footer_layout.setColumnStretch(1, 1 if footer_horizontal else 0)
            self.footer_layout.setColumnStretch(2, 0)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        target = self._drawer_rect()
        self._reflow_controls(target.width())
        if self._animation.state() != QPropertyAnimation.State.Running:
            self.drawer.setGeometry(target)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if not self.drawer.geometry().contains(event.position().toPoint()):
            self.close_animated()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.key() in {Qt.Key.Key_Escape, Qt.Key.Key_Back}:
            self.close_animated()
            event.accept()
            return
        super().keyPressEvent(event)
