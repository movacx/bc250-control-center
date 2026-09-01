"""Compact voltage-curve drawer for the desktop GPU page."""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton as NativePushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from bc250cc.application.gpu.voltage_table import VoltageTableRow
from bc250cc.domain.gpu.voltage_profiles import (
    CUSTOM_VOLTAGE_MAX_MV,
    CUSTOM_VOLTAGE_MIN_MV,
)

from ..i18n import tr
from .buttons import WrappingButton as QPushButton
from .widgets import icon


class _DrawerCurveRow(QFrame):
    voltage_changed = pyqtSignal(int, int)

    def __init__(
        self,
        row: VoltageTableRow,
        *,
        custom_mode: bool,
        read_only: bool,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.frequency = int(row.frequency)
        self.original = row.original
        self.setProperty("voltageDrawerCurveRow", True)
        grid = QGridLayout(self)
        grid.setContentsMargins(9, 6, 9, 6)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(1)

        frequency = QLabel(f"{row.frequency} MHz")
        frequency.setProperty("voltageDrawerFrequency", True)
        current = QLabel(f"{row.current} mV" if row.current else tr("Not set"))
        current.setProperty("voltageDrawerCurrent", True)
        grid.addWidget(frequency, 0, 0)
        grid.addWidget(current, 0, 1)

        self.editor: QSpinBox | None = None
        if custom_mode and row.custom_available:
            editor = QSpinBox()
            editor.setProperty("voltageDrawerEditor", True)
            editor.setRange(CUSTOM_VOLTAGE_MIN_MV, CUSTOM_VOLTAGE_MAX_MV)
            editor.setSingleStep(5)
            editor.setSuffix(" mV")
            editor.setValue(int(row.editor_value))
            editor.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            editor.valueChanged.connect(self._editor_changed)
            self.editor = editor
            grid.addWidget(editor, 0, 2)
        else:
            proposed = QLabel(
                f"{row.proposed} mV" if row.proposed is not None else tr("Unchanged")
            )
            proposed.setProperty("voltageDrawerTarget", True)
            proposed.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(proposed, 0, 2)

        self.delta = QLabel(tr("Read only") if read_only else self._delta_text(row.added))
        self.delta.setProperty("voltageDrawerDelta", True)
        self.delta.setProperty("deltaTone", self._delta_tone(row.added))
        self.delta.setAlignment(Qt.AlignmentFlag.AlignRight)
        grid.addWidget(self.delta, 1, 2)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 3)

    @staticmethod
    def _delta_text(value: int | None) -> str:
        if value is None:
            return tr("No baseline")
        if value > 0:
            return f"+{value} mV"
        if value < 0:
            return f"{value} mV"
        return tr("Governor default")

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
        self.delta.setText(self._delta_text(added))
        self.delta.setProperty("deltaTone", self._delta_tone(added))
        self.delta.style().unpolish(self.delta)
        self.delta.style().polish(self.delta)
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
        root.setContentsMargins(14, 14, 14, 12)
        root.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(10)
        self.close_button = QPushButton("‹")
        self.close_button.setObjectName("VoltageDrawerClose")
        self.close_button.setProperty("voltageDrawerClose", True)
        self.close_button.setProperty("gamepadEntry", True)
        self.close_button.setProperty("gamepadCancel", True)
        self.close_button.setAccessibleName(tr("Close GPU voltage curve"))
        self.close_button.setFixedSize(38, 38)
        self.close_button.clicked.connect(self.close_animated)
        header.addWidget(self.close_button)
        title_host = QWidget()
        title_layout = QVBoxLayout(title_host)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(0)
        title = QLabel(tr("GPU voltage curve"))
        title.setProperty("voltageDrawerTitle", True)
        subtitle = QLabel(tr("Choose a safe preset or edit the active points"))
        subtitle.setProperty("voltageDrawerSubtitle", True)
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        header.addWidget(title_host, 1)
        root.addLayout(header)

        scroll = QScrollArea()
        scroll.setObjectName("VoltageLabDrawerScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("VoltageLabDrawerBody")
        content = QVBoxLayout(body)
        content.setContentsMargins(0, 0, 3, 3)
        content.setSpacing(10)

        self.safety_notice = QFrame()
        self.safety_notice.setProperty("voltageDrawerNotice", True)
        notice_layout = QHBoxLayout(self.safety_notice)
        notice_layout.setContentsMargins(10, 8, 10, 8)
        notice_layout.setSpacing(0)
        notice_text = QLabel(
            tr("Stop games and 3D workloads. A backup is created before the governor restarts.")
        )
        notice_text.setProperty("voltageDrawerNoticeText", True)
        notice_text.setWordWrap(True)
        notice_layout.addWidget(notice_text, 1)
        content.addWidget(self.safety_notice)

        self.compatibility_note = QFrame()
        self.compatibility_note.setProperty("voltageDrawerCompatibility", True)
        compatibility_layout = QVBoxLayout(self.compatibility_note)
        compatibility_layout.setContentsMargins(11, 10, 11, 10)
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
        content.addWidget(self.compatibility_note)

        self.profiles_card = QFrame()
        self.profiles_card.setProperty("voltageDrawerCard", True)
        profiles_layout = QVBoxLayout(self.profiles_card)
        profiles_layout.setContentsMargins(11, 10, 11, 11)
        profiles_layout.setSpacing(7)
        profiles_layout.addLayout(self._section_header("Curve boost"))
        self.profile_grid = QGridLayout()
        self.profile_grid.setContentsMargins(0, 0, 0, 0)
        self.profile_grid.setHorizontalSpacing(6)
        self.profile_grid.setVerticalSpacing(6)
        self.profile_group = QButtonGroup(self)
        self.profile_group.setExclusive(True)
        self.profile_buttons: dict[int, NativePushButton] = {}
        for index, level in enumerate(self.PROFILE_LEVELS):
            custom = level == -1
            descriptions = {1: "Gentle", 2: "Moderate", 3: "High"}
            button = NativePushButton(
                tr("Custom\nEdit active points")
                if custom
                else f"+{level * 10} mV\n{tr(descriptions[level])}"
            )
            button.setCheckable(True)
            button.setFixedHeight(54)
            button.setProperty("voltageDrawerProfile", True)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.clicked.connect(
                lambda checked, value=level: self._choose_profile(value) if checked else None
            )
            self.profile_group.addButton(button)
            self.profile_buttons[level] = button
        profiles_layout.addLayout(self.profile_grid)
        self.profile_detail = QLabel(tr("Select a level to preview the exact curve before applying."))
        self.profile_detail.setProperty("voltageDrawerDetail", True)
        self.profile_detail.setWordWrap(True)
        profiles_layout.addWidget(self.profile_detail)
        content.addWidget(self.profiles_card)

        curve = QFrame()
        curve.setProperty("voltageDrawerCard", True)
        curve_layout = QVBoxLayout(curve)
        curve_layout.setContentsMargins(11, 10, 11, 11)
        curve_layout.setSpacing(6)
        curve_layout.addLayout(self._section_header("Voltage map"))
        labels = QGridLayout()
        labels.setContentsMargins(9, 0, 9, 0)
        labels.setHorizontalSpacing(8)
        for column, text in enumerate(("Frequency", "Current", "Selected")):
            label = QLabel(tr(text))
            label.setProperty("voltageDrawerColumn", True)
            if column == 2:
                label.setAlignment(Qt.AlignmentFlag.AlignRight)
                self.selected_column = label
            labels.addWidget(label, 0, column)
        labels.setColumnStretch(0, 3)
        labels.setColumnStretch(1, 2)
        labels.setColumnStretch(2, 3)
        curve_layout.addLayout(labels)
        self.curve_rows = QVBoxLayout()
        self.curve_rows.setContentsMargins(0, 0, 0, 0)
        self.curve_rows.setSpacing(5)
        curve_layout.addLayout(self.curve_rows)
        content.addWidget(curve)
        content.addStretch(1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        self.footer = QFrame()
        self.footer.setProperty("voltageDrawerFooter", True)
        self.footer_layout = QGridLayout(self.footer)
        self.footer_layout.setContentsMargins(9, 9, 9, 9)
        self.footer_layout.setHorizontalSpacing(7)
        self.footer_layout.setVerticalSpacing(7)
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

    @staticmethod
    def _section_header(title: str) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        title_label = QLabel(tr(title))
        title_label.setProperty("voltageDrawerSectionTitle", True)
        layout.addWidget(title_label, 1)
        return layout

    def set_profile(self, level: int) -> None:
        level = int(level)
        if level not in self.profile_buttons:
            level = 1
        self._selected_level = level
        for value, button in self.profile_buttons.items():
            button.setChecked(value == level)

    def selected_level(self) -> int:
        return self._selected_level

    def set_profiles_enabled(self, enabled: bool) -> None:
        for button in self.profile_buttons.values():
            button.setEnabled(bool(enabled))
        self.restore_button.setEnabled(bool(enabled))

    def set_oberon_mode(self, enabled: bool) -> None:
        read_only = bool(enabled)
        self.safety_notice.setVisible(not read_only)
        self.compatibility_note.setVisible(read_only)
        self.profiles_card.setVisible(not read_only)
        self.footer.setVisible(not read_only)
        self.selected_column.setText(tr("Configured" if read_only else "Selected"))

    def _choose_profile(self, level: int) -> None:
        self._selected_level = int(level)
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
        signature = (tuple(rows), bool(custom_mode), bool(read_only))
        if signature != self._curve_signature:
            while self.curve_rows.count():
                item = self.curve_rows.takeAt(0)
                if item.widget() is not None:
                    item.widget().deleteLater()
            self._editors = {}
            for row in rows:
                widget = _DrawerCurveRow(
                    row,
                    custom_mode=custom_mode,
                    read_only=read_only,
                )
                widget.voltage_changed.connect(self.custom_voltage_changed)
                self.curve_rows.addWidget(widget)
                if widget.editor is not None:
                    self._editors[int(row.frequency)] = widget.editor
            self._curve_signature = signature
        self.profile_detail.setText(str(detail))
        self.apply_button.setEnabled(bool(apply_enabled))

    def custom_values(self) -> dict[int, int]:
        return {
            frequency: int(editor.value())
            for frequency, editor in self._editors.items()
        }

    def editors(self) -> tuple[QSpinBox, ...]:
        return tuple(self._editors.values())

    def is_open(self) -> bool:
        return self.isVisible()

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
        QTimer.singleShot(
            self._animation.duration() + 20,
            lambda: self.close_button.setFocus(Qt.FocusReason.OtherFocusReason),
        )

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

    def _drawer_rect(self) -> QRect:
        horizontal_margin = 3
        top_margin = 8
        bottom_margin = 0
        available = max(0, self.width() - (horizontal_margin * 2))
        if self.width() <= 760:
            width = available
        else:
            width = min(760, max(580, round(self.width() * 0.53)))
        return QRect(
            max(horizontal_margin, self.width() - horizontal_margin - width),
            top_margin,
            width,
            max(0, self.height() - top_margin - bottom_margin),
        )

    def _reflow_controls(self, width: int) -> None:
        profile_columns = 2 if int(width) >= 540 else 1
        if profile_columns != self._profile_columns:
            self._profile_columns = profile_columns
            while self.profile_grid.count():
                self.profile_grid.takeAt(0)
            for index, button in enumerate(self.profile_buttons.values()):
                row, column = divmod(index, profile_columns)
                button.setProperty("gamepadHorizontalGroup", f"voltage-level-{row}")
                button.setProperty("gamepadHorizontalIndex", column)
                self.profile_grid.addWidget(button, row, column)
            for column in range(2):
                self.profile_grid.setColumnStretch(
                    column, 1 if column < profile_columns else 0
                )

        footer_horizontal = int(width) >= 520
        if footer_horizontal != self._footer_horizontal:
            self._footer_horizontal = footer_horizontal
            while self.footer_layout.count():
                self.footer_layout.takeAt(0)
            if footer_horizontal:
                self.footer_layout.addWidget(self.restore_button, 0, 0)
                self.footer_layout.addWidget(self.apply_button, 0, 1)
                self.footer_layout.setColumnStretch(0, 2)
                self.footer_layout.setColumnStretch(1, 3)
            else:
                self.footer_layout.addWidget(self.restore_button, 0, 0)
                self.footer_layout.addWidget(self.apply_button, 1, 0)
                self.footer_layout.setColumnStretch(0, 1)
                self.footer_layout.setColumnStretch(1, 0)

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
