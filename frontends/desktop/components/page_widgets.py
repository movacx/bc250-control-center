from __future__ import annotations

from typing import Iterable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..i18n import localize_widget_tree, tr
from ..theme import COLORS, application_stylesheet
from .buttons import WrappingButton as QPushButton
from .dialogs import center_dialog, enable_adaptive_dialog
from .widgets import IconBadge, PillLabel, apply_shadow, icon


class MetricTile(QFrame):
    def __init__(
        self,
        label: str,
        value: str = "--",
        detail: str = "",
        *,
        icon_name: str = "info_blue",
        icon_background: str = "neutral_soft",
        compact: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setProperty("metricTile", True)
        if compact:
            self.setProperty("compactMetricTile", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QHBoxLayout(self)
        if compact:
            layout.setContentsMargins(11, 9, 11, 9)
            layout.setSpacing(9)
            icon_size = 30
            radius = 9
        else:
            layout.setContentsMargins(14, 12, 14, 12)
            layout.setSpacing(11)
            icon_size = 36
            radius = 10
        layout.addWidget(IconBadge(icon_name, icon_background, icon_size, radius=radius))

        text = QVBoxLayout()
        text.setSpacing(1)
        self.label = QLabel(tr(label))
        self.label.setProperty("metricTileLabel", True)
        self.value = QLabel(tr(value))
        self.value.setProperty("metricTileValue", True)
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail = QLabel(tr(detail))
        self.detail.setProperty("metricTileDetail", True)
        self.detail.setWordWrap(True)
        self.detail.setVisible(bool(detail))
        text.addWidget(self.label)
        text.addWidget(self.value)
        text.addWidget(self.detail)
        layout.addLayout(text, 1)

    def set_values(self, value: str, detail: str | None = None) -> None:
        self.value.setText(tr(value))
        if detail is not None:
            self.detail.setText(tr(detail))
            self.detail.setVisible(bool(detail))

    def set_label(self, label: str) -> None:
        self.label.setText(tr(label))


class SectionCard(QFrame):
    def __init__(
        self,
        title: str,
        subtitle: str = "",
        *,
        icon_name: str = "info_blue",
        icon_background: str | None = None,
        status: tuple[str, str] | None = None,
        compact: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setProperty("pageCard", True)
        if compact:
            self.setProperty("compactPageCard", True)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        apply_shadow(self, blur=20, y=4, alpha=14)
        self.root = QVBoxLayout(self)
        if compact:
            self.root.setContentsMargins(14, 12, 14, 12)
        else:
            self.root.setContentsMargins(20, 18, 20, 18)
        self.root.setSpacing(9 if compact else 14)

        self._header_grid = QGridLayout()
        self._header_grid.setContentsMargins(0, 0, 0, 0)
        self._header_grid.setHorizontalSpacing(8 if compact else 11)
        self._header_grid.setVerticalSpacing(6)
        icon_size = 32 if compact else 40
        self._header_icon = IconBadge(
            icon_name,
            icon_background or COLORS["blue_soft"],
            icon_size,
            radius=9 if compact else 11,
        )
        self._title_host = QWidget()
        self._title_host.setMinimumWidth(0)
        self._title_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        title_box = QVBoxLayout(self._title_host)
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(0 if compact else 1)
        title_label = QLabel(tr(title))
        title_label.setProperty("cardTitle", True)
        title_label.setWordWrap(True)
        subtitle_label = QLabel(tr(subtitle))
        subtitle_label.setProperty("sectionSubtitle", True)
        subtitle_label.setWordWrap(True)
        subtitle_label.setMinimumWidth(0)
        title_box.addWidget(title_label)
        if subtitle:
            title_box.addWidget(subtitle_label)

        self.status: PillLabel | None = None
        if status:
            self.status = PillLabel(tr(status[0]), status[1])

        self._header_actions_host = QWidget()
        self._header_actions_host.setMinimumWidth(0)
        self.header_actions = QGridLayout(self._header_actions_host)
        self.header_actions.setContentsMargins(0, 0, 0, 0)
        self.header_actions.setHorizontalSpacing(5 if compact else 7)
        self.header_actions.setVerticalSpacing(5)
        self._header_buttons: list[QPushButton] = []
        self._header_compact = False
        self._layout_header(force=True)
        self.root.addLayout(self._header_grid, 0)

        divider = QFrame()
        divider.setObjectName("CardDivider")
        divider.setFixedHeight(1)
        self.root.addWidget(divider, 0)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(8 if compact else 12)
        self.root.addLayout(self.body, 1)

    def _layout_header(self, *, force: bool = False) -> None:
        compact = 0 < self.width() < 560
        if compact == self._header_compact and not force:
            self._layout_header_buttons(compact)
            return
        for widget in (self._header_icon, self._title_host, self.status, self._header_actions_host):
            if widget is not None:
                self._header_grid.removeWidget(widget)
        if compact:
            self._header_grid.addWidget(self._header_icon, 0, 0, Qt.AlignmentFlag.AlignTop)
            self._header_grid.addWidget(self._title_host, 0, 1)
            if self.status is not None:
                self._header_grid.addWidget(self.status, 1, 0, 1, 2, Qt.AlignmentFlag.AlignLeft)
            if self._header_buttons:
                row = 2 if self.status is not None else 1
                self._header_grid.addWidget(self._header_actions_host, row, 0, 1, 2)
            self._header_grid.setColumnStretch(0, 0)
            self._header_grid.setColumnStretch(1, 1)
        else:
            self._header_grid.addWidget(self._header_icon, 0, 0, Qt.AlignmentFlag.AlignTop)
            self._header_grid.addWidget(self._title_host, 0, 1)
            if self.status is not None:
                self._header_grid.addWidget(self.status, 0, 2, Qt.AlignmentFlag.AlignTop)
            if self._header_buttons:
                self._header_grid.addWidget(self._header_actions_host, 0, 3, Qt.AlignmentFlag.AlignTop)
            self._header_grid.setColumnStretch(0, 0)
            self._header_grid.setColumnStretch(1, 1)
            self._header_grid.setColumnStretch(2, 0)
            self._header_grid.setColumnStretch(3, 0)
        self._header_compact = compact
        self._layout_header_buttons(compact)
        self.updateGeometry()

    def _layout_header_buttons(self, compact: bool) -> None:
        while self.header_actions.count():
            self.header_actions.takeAt(0)
        columns = 1 if compact else max(1, len(self._header_buttons))
        for index, button in enumerate(self._header_buttons):
            preferred_width = int(button.property("headerActionWidth") or 0)
            button.setMinimumWidth(0 if compact else preferred_width)
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding if compact else QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Fixed,
            )
            self.header_actions.addWidget(button, index // columns, index % columns)
        for column in range(max(1, columns)):
            self.header_actions.setColumnStretch(column, 1 if compact else 0)
        self._header_actions_host.setVisible(bool(self._header_buttons))

    def add_header_button(
        self,
        text: str,
        callback,
        *,
        primary: bool = False,
        danger: bool = False,
        width: int = 0,
    ) -> QPushButton:
        button = QPushButton(tr(text))
        button.setProperty("dangerAction" if danger else "primaryAction" if primary else "compactAction", True)
        button.setProperty("headerActionWidth", max(0, int(width)))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(callback)
        self._header_buttons.append(button)
        self._layout_header(force=True)
        return button

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._layout_header()




class ControlPageHeader(QWidget):
    """Compact control-page heading that moves actions below copy when narrow."""

    refresh_requested = pyqtSignal()
    action_requested = pyqtSignal()

    def __init__(
        self,
        eyebrow: str,
        title: str,
        subtitle: str,
        *,
        mode_text: str = "",
        action_text: str = "",
        action_icon: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._compact = False
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(14)
        self._grid.setVerticalSpacing(8)

        self.title_host = QWidget()
        self.title_host.setMinimumWidth(0)
        self.title_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        title_box = QVBoxLayout(self.title_host)
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(4)
        top_line = QHBoxLayout()
        top_line.setSpacing(12)
        eyebrow_label = QLabel(tr(eyebrow))
        eyebrow_label.setObjectName("PageEyebrow")
        eyebrow_label.setWordWrap(True)
        eyebrow_label.setMinimumWidth(0)
        top_line.addWidget(eyebrow_label)
        if mode_text:
            mode = QLabel(tr(mode_text))
            mode.setProperty("pageMode", True)
            mode.setWordWrap(True)
            mode.setMinimumWidth(0)
            top_line.addWidget(mode)
        top_line.addStretch(1)
        title_label = QLabel(tr(title))
        title_label.setObjectName("PageTitle")
        title_label.setWordWrap(True)
        subtitle_label = QLabel(tr(subtitle))
        subtitle_label.setObjectName("PageSubtitle")
        subtitle_label.setWordWrap(True)
        subtitle_label.setMinimumWidth(0)
        title_box.addLayout(top_line)
        title_box.addWidget(title_label)
        title_box.addWidget(subtitle_label)

        self.refresh_button = QPushButton(tr("Refresh"))
        self.refresh_button.setObjectName("RefreshButton")
        self.refresh_button.setIcon(icon("refresh_gray"))
        self.refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_button.clicked.connect(self.refresh_requested)

        self.action_button: QPushButton | None = None
        if action_text:
            self.action_button = QPushButton(tr(action_text))
            self.action_button.setObjectName("PrimaryAction")
            if action_icon:
                self.action_button.setIcon(icon(action_icon))
            self.action_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.action_button.clicked.connect(self.action_requested)
        self._reflow(force=True)

    def _reflow(self, *, force: bool = False) -> None:
        compact = 0 < self.width() < 680
        if compact == self._compact and not force:
            return
        for widget in (self.title_host, self.refresh_button, self.action_button):
            if widget is not None:
                self._grid.removeWidget(widget)
        if compact:
            self._grid.addWidget(self.title_host, 0, 0, 1, 2)
            self._grid.addWidget(self.refresh_button, 1, 0)
            self.refresh_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            if self.action_button is not None:
                self._grid.addWidget(self.action_button, 1, 1)
                self.action_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._grid.setColumnStretch(0, 1)
            self._grid.setColumnStretch(1, 1)
        else:
            self._grid.addWidget(self.title_host, 0, 0)
            self._grid.addWidget(self.refresh_button, 0, 1, Qt.AlignmentFlag.AlignTop)
            self.refresh_button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            if self.action_button is not None:
                self._grid.addWidget(self.action_button, 0, 2, Qt.AlignmentFlag.AlignTop)
                self.action_button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            self._grid.setColumnStretch(0, 1)
            self._grid.setColumnStretch(1, 0)
            self._grid.setColumnStretch(2, 0)
        self._compact = compact
        self.updateGeometry()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._reflow()


class SliderControl(QFrame):
    """Synchronized slider/spinbox control for a single hardware value."""

    value_changed = pyqtSignal(int)

    def __init__(
        self,
        label: str,
        minimum: int,
        maximum: int,
        value: int,
        *,
        suffix: str = "",
        step: int = 1,
        hint: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setProperty("sliderControl", True)
        root = QVBoxLayout(self)
        root.setContentsMargins(13, 11, 13, 11)
        root.setSpacing(8)
        header = QHBoxLayout()
        title = QLabel(tr(label))
        title.setProperty("sliderLabel", True)
        title.setWordWrap(True)
        title.setMinimumWidth(0)
        header.addWidget(title)
        header.addStretch(1)
        self.spin = QSpinBox()
        self.spin.setRange(minimum, maximum)
        self.spin.setSingleStep(step)
        self.spin.setSuffix(suffix)
        self.spin.setValue(value)
        self.spin.setMinimumWidth(96)
        self.spin.setMaximumWidth(148)
        self.spin.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        header.addWidget(self.spin)
        root.addLayout(header)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(minimum, maximum)
        self.slider.setSingleStep(step)
        self.slider.setPageStep(max(step, (maximum - minimum) // 10))
        self.slider.setValue(value)
        root.addWidget(self.slider)
        limits = QHBoxLayout()
        low = QLabel(f"{minimum}{suffix}")
        high = QLabel(f"{maximum}{suffix}")
        low.setProperty("sliderLimit", True)
        high.setProperty("sliderLimit", True)
        limits.addWidget(low)
        limits.addStretch(1)
        limits.addWidget(high)
        root.addLayout(limits)
        if hint:
            hint_label = QLabel(tr(hint))
            hint_label.setProperty("fieldHint", True)
            hint_label.setWordWrap(True)
            root.addWidget(hint_label)
        self.slider.valueChanged.connect(self.spin.setValue)
        self.spin.valueChanged.connect(self.slider.setValue)
        self.spin.valueChanged.connect(self.value_changed)

    def value(self) -> int:
        return self.spin.value()

    def setValue(self, value: int) -> None:
        self.spin.setValue(value)

    def setRange(self, minimum: int, maximum: int) -> None:
        self.spin.setRange(minimum, maximum)
        self.slider.setRange(minimum, maximum)


class PresetButton(QPushButton):
    """Checkable two-line preset selector used by CPU and GPU pages."""

    def __init__(self, title: str, summary: str, payload: object, parent: QWidget | None = None):
        super().__init__(parent)
        self.payload = payload
        self.setCheckable(True)
        self.setProperty("presetButton", True)
        self.setText(f"{tr(title)}\n{tr(summary)}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(68)


class StatusLine(QFrame):
    def __init__(
        self,
        label: str,
        value: str = "--",
        detail: str = "",
        parent: QWidget | None = None,
        *,
        compact: bool = False,
    ):
        super().__init__(parent)
        self.setProperty("statusLine", True)
        if compact:
            self.setProperty("compactStatusLine", True)
        row = QHBoxLayout(self)
        if compact:
            row.setContentsMargins(8, 6, 8, 6)
        else:
            row.setContentsMargins(11, 9, 11, 9)
        row.setSpacing(7 if compact else 10)
        text = QVBoxLayout()
        text.setSpacing(1)
        label_widget = QLabel(tr(label))
        label_widget.setProperty("statusLineLabel", True)
        label_widget.setWordWrap(True)
        label_widget.setMinimumWidth(0)
        self.detail = QLabel(tr(detail))
        self.detail.setProperty("statusLineDetail", True)
        self.detail.setWordWrap(True)
        text.addWidget(label_widget)
        text.addWidget(self.detail)
        row.addLayout(text, 1)
        self.value = QLabel(tr(value))
        self.value.setProperty("statusLineValue", True)
        self.value.setWordWrap(True)
        self.value.setMinimumWidth(0)
        self.value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.value)

    def set_values(self, value: str, detail: str | None = None) -> None:
        self.value.setText(tr(value))
        if detail is not None:
            self.detail.setText(tr(detail))


class ConfirmDialog(QDialog):
    """Frameless confirmation used before hardware-changing operations."""

    def __init__(
        self,
        title: str,
        message: str,
        *,
        summary: Iterable[tuple[str, str]] = (),
        confirm_text: str = "Continue",
        eyebrow: str = "CONFIRM HARDWARE ACTION",
        tone: str = "blue",
        parent: QWidget | None = None,
    ):
        title = tr(title)
        message = tr(message)
        confirm_text = tr(confirm_text)
        eyebrow = tr(eyebrow)
        summary = tuple((tr(label), tr(value)) for label, value in summary)
        super().__init__(parent)
        self.setObjectName("InfoDialog")
        self.setModal(True)
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(application_stylesheet())
        enable_adaptive_dialog(self, preferred_width=580, minimum_width=400, minimum_height=240)

        accent = COLORS["red"] if tone == "red" else COLORS["orange"] if tone == "orange" else COLORS["blue"]
        soft = COLORS["red_soft"] if tone == "red" else COLORS["orange_soft"] if tone == "orange" else COLORS["blue_soft"]

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        card = QFrame()
        card.setObjectName("ControlDialogCard")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(20, 33, 61, 55))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(17)
        header = QHBoxLayout()
        header.setSpacing(13)
        header.addWidget(IconBadge("warning_orange" if tone != "blue" else "info_blue", soft, 44))
        heading = QVBoxLayout()
        heading.setSpacing(2)
        eyebrow_label = QLabel(eyebrow)
        eyebrow_label.setObjectName("DialogEyebrow")
        eyebrow_label.setWordWrap(True)
        eyebrow_label.setStyleSheet(f"color:{accent};")
        title_label = QLabel(tr(title))
        title_label.setObjectName("DialogTitle")
        title_label.setWordWrap(True)
        heading.addWidget(eyebrow_label)
        heading.addWidget(title_label)
        header.addLayout(heading, 1)
        close = QPushButton()
        close.setObjectName("DialogClose")
        close.setIcon(icon("close_gray"))
        close.setFixedSize(34, 34)
        close.setToolTip(tr("Close"))
        close.clicked.connect(self.reject)
        header.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        divider = QFrame()
        divider.setObjectName("CardDivider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)

        content_scroll = QScrollArea()
        content_scroll.setObjectName("DialogContentScroll")
        content_scroll.setWidgetResizable(True)
        content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        content_scroll.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        content_scroll.setMinimumHeight(84)
        content_scroll.setMaximumHeight(440)
        content = QWidget()
        content.setObjectName("DialogContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        body = QLabel(tr(message))
        body.setObjectName("DialogBody")
        body.setWordWrap(True)
        content_layout.addWidget(body)

        values = list(summary)
        if values:
            summary_frame = QFrame()
            summary_frame.setProperty("confirmSummary", True)
            grid = QGridLayout(summary_frame)
            grid.setContentsMargins(12, 10, 12, 10)
            grid.setHorizontalSpacing(18)
            grid.setVerticalSpacing(7)
            for index, (label, value) in enumerate(values):
                name = QLabel(tr(label))
                name.setProperty("confirmLabel", True)
                name.setWordWrap(True)
                data = QLabel(tr(value))
                data.setProperty("confirmValue", True)
                data.setWordWrap(True)
                data.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                grid.addWidget(name, index, 0)
                grid.addWidget(data, index, 1)
            grid.setColumnStretch(1, 1)
            content_layout.addWidget(summary_frame)

        content_scroll.setWidget(content)
        layout.addWidget(content_scroll)

        footer = QHBoxLayout()
        footer.addStretch(1)
        cancel = QPushButton(tr("Cancel"))
        cancel.setProperty("compactAction", True)
        cancel.setProperty("gamepadCancel", True)
        cancel.setProperty("gamepadEntry", True)
        cancel.clicked.connect(self.reject)
        confirm = QPushButton(confirm_text)
        confirm.setObjectName("DialogDanger" if tone in {"orange", "red"} else "DialogPrimary")
        confirm.setDefault(True)
        confirm.clicked.connect(self.accept)
        footer.addWidget(cancel)
        footer.addWidget(confirm)
        layout.addLayout(footer)
        localize_widget_tree(self)
        self.fit_to_content()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.fit_to_content()
        center_dialog(self)
