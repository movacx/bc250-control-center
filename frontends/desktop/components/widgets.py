from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import theme as theme_module
from ..core.error_diagnostics import format_error_for_user
from ..i18n import localize_widget_tree, tr
from ..theme import COLORS, application_stylesheet, palette_color, semantic_color_key
from .busy_spinner import BusySpinner
from .buttons import WrappingButton as QPushButton
from .dialogs import center_dialog, enable_adaptive_dialog

ICON_DIR = Path(__file__).resolve().parents[1] / "theme" / "icons"


def icon(name: str) -> QIcon:
    return QIcon(str(ICON_DIR / f"{name}.svg"))


def readable_text_on(color: QColor) -> QColor:
    """Near-black or white, whichever reads better on ``color`` (a chart tag's fill)."""

    def channel(value: int) -> float:
        value /= 255.0
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    luminance = 0.2126 * channel(color.red()) + 0.7152 * channel(color.green()) + 0.0722 * channel(color.blue())
    return QColor("#111111") if luminance > 0.2 else QColor("#FFFFFF")


def apply_shadow(widget: QWidget, *, blur: int = 26, y: int = 6, alpha: int = 18) -> None:
    """Apply one restrained enterprise-style elevation effect."""
    if theme_module.ACTIVE_STYLE == "formal":
        # The formal style lays cards flat on their hairline: a trace of
        # depth, not a lift.
        blur, y, alpha = max(6, blur // 3), min(y, 1), max(6, alpha // 2)
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, y)
    shadow.setColor(QColor(0, 0, 0, min(90, alpha * 2) if theme_module.ACTIVE_MODE == "dark" else alpha))
    widget.setGraphicsEffect(shadow)


class IconBadge(QFrame):
    def __init__(
        self,
        icon_name: str,
        background: str,
        size: int = 42,
        parent: QWidget | None = None,
        *,
        radius: int | None = None,
    ):
        super().__init__(parent)
        self._icon_name = icon_name
        self._background_source = background
        self._preferred_color = self._infer_color_key(icon_name, background)
        self._corner_radius = size // 2 if radius is None else radius
        self.setFixedSize(size, size)
        layout = QHBoxLayout(self)
        inset = max(8, round(size * 0.22))
        layout.setContentsMargins(inset, inset, inset, inset)
        self.icon_label = QLabel()
        self.icon_label.setPixmap(icon(icon_name).pixmap(size - (inset * 2), size - (inset * 2)))
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label)
        self._refresh_palette()

    @staticmethod
    def _infer_color_key(icon_name: str, background: object) -> str:
        explicit = semantic_color_key(background)
        if explicit and explicit.endswith("_soft"):
            return explicit
        name = str(icon_name or "").lower()
        for tone in ("purple", "orange", "green", "cyan", "red", "blue"):
            if tone in name:
                return f"{tone}_soft"
        if any(token in name for token in ("gray", "grey", "vram", "power", "refresh", "logs")):
            return "neutral_soft"
        return explicit or "blue_soft"

    def _refresh_palette(self) -> None:
        background = palette_color(self._background_source, self._preferred_color)
        self.setStyleSheet(
            f"background:{background}; border:1px solid {COLORS['icon_border']}; "
            f"border-radius:{self._corner_radius}px;"
        )


class PillLabel(QLabel):
    def __init__(self, text: str, tone: str = "green", parent: QWidget | None = None):
        super().__init__(tr(text), parent)
        self._tone = tone
        self.setProperty("pill", True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._refresh_palette()

    def setText(self, text: str) -> None:  # noqa: N802 - Qt API name
        super().setText(tr(text))

    def set_tone(self, tone: str) -> None:
        if tone == self._tone:
            return
        self._tone = tone
        self._refresh_palette()

    def _refresh_palette(self) -> None:
        tone = self._tone if self._tone in {"green", "blue", "purple", "orange", "red", "cyan"} else "gray"
        if tone == "gray":
            foreground, background, border = COLORS["muted"], COLORS["neutral_soft"], COLORS["neutral_border"]
        else:
            foreground = COLORS[tone]
            background = COLORS[f"{tone}_soft"]
            border = COLORS[f"{tone}_border"]
        # Selector-scoped: a bare declaration list also reaches child windows,
        # and this pill's tooltip is one — it took on the pill's colours.
        self.setStyleSheet(
            f"PillLabel {{ color:{foreground}; background:{background}; border:1px solid {border}; }}"
        )


class SummaryMetric(QWidget):
    """One compact item in the Dashboard hardware summary bar."""

    def __init__(self, icon_name: str, label: str, value: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 6, 10, 6)
        row.setSpacing(12)
        row.addWidget(IconBadge(icon_name, "neutral_soft", 36, radius=10))

        text_box = QVBoxLayout()
        text_box.setSpacing(1)
        self.label = QLabel(tr(label))
        self.label.setObjectName("SummaryLabel")
        self.label.setWordWrap(True)
        self.label.setMinimumWidth(0)
        self.value = QLabel(tr(value))
        self.value.setObjectName("SummaryValue")
        self.value.setWordWrap(True)
        self.value.setMinimumWidth(0)
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text_box.addWidget(self.label)
        text_box.addWidget(self.value)
        row.addLayout(text_box, 1)

    def set_value(self, value: str) -> None:
        self.value.setText(tr(value))

    def set_label(self, label: str) -> None:
        self.label.setText(tr(label))


class SystemSummaryBar(QFrame):
    """Hardware summary strip that reflows from four columns down to one."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("SystemSummaryBar")
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        apply_shadow(self, blur=18, y=3, alpha=14)

        self.layout_grid = QGridLayout(self)
        self.layout_grid.setContentsMargins(16, 10, 16, 10)
        self.layout_grid.setHorizontalSpacing(10)
        self.layout_grid.setVerticalSpacing(8)

        self.gpu = SummaryMetric("gpu_gray", "GPU", "BC250")
        self.vram = SummaryMetric("vram_gray", "VRAM", "Not detected")
        self.power = SummaryMetric("power_gray", "Board power", "Not detected")
        self.uptime = SummaryMetric("uptime_gray", "Uptime", "Not detected")
        self.items = [self.gpu, self.vram, self.power, self.uptime]
        self._columns = 0
        self._reflow(1200)

    def _reflow(self, width: int) -> None:
        columns = 4 if width >= 980 else 2 if width >= 520 else 1
        if columns == self._columns and self.layout_grid.count():
            return
        self._columns = columns
        while self.layout_grid.count():
            # Preserve parentage so the metrics do not blink while moving to a
            # new row during a live window resize.
            self.layout_grid.takeAt(0)
        for index, item in enumerate(self.items):
            self.layout_grid.addWidget(item, index // columns, index % columns)
        for column in range(4):
            self.layout_grid.setColumnStretch(column, 1 if column < columns else 0)
        self.updateGeometry()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._reflow(event.size().width())

    def set_values(
        self,
        *,
        gpu: str,
        vram: str,
        power: str,
        uptime: str,
        power_label: str = "SoC package power",
        power_tooltip: str = "",
    ) -> None:
        self.gpu.set_value(gpu)
        self.vram.set_value(vram)
        self.power.set_label(power_label)
        self.power.set_value(power)
        self.power.setToolTip(tr(power_tooltip) if power_tooltip else "")
        self.uptime.set_value(uptime)


class InfoDialog(QDialog):
    """Compact frameless modal used by the control center.

    The dialog deliberately avoids the native KDE title bar and the nested
    panel-within-a-window appearance.
    """

    def __init__(
        self,
        title: str,
        message: str,
        icon_name: str = "info_blue",
        parent: QWidget | None = None,
        *,
        eyebrow: str = "CONTROL CENTER",
        button_text: str = "Close",
        notice: str = "No hardware changes will be made.",
        tone: str = "blue",
        copy_text: str = "",
        copy_button_text: str = "Copy command",
        busy: bool = False,
    ):
        raw_title = str(title)
        raw_eyebrow = str(eyebrow)
        if tone == "red":
            message = format_error_for_user(
                message,
                context=f"{raw_eyebrow} {raw_title}",
                translate=tr,
            )
        title = tr(title)
        message = tr(message)
        eyebrow = tr(eyebrow)
        button_text = tr(button_text)
        notice = tr(notice)
        copy_button_text = tr(copy_button_text)
        super().__init__(parent)
        self.setObjectName("InfoDialog")
        self.setModal(True)
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(application_stylesheet())
        enable_adaptive_dialog(self, preferred_width=560, minimum_width=380, minimum_height=220)

        tones = {
            "blue": (COLORS["blue"], COLORS["blue_soft"]),
            "purple": (COLORS["purple"], COLORS["purple_soft"]),
            "orange": (COLORS["orange"], COLORS["orange_soft"]),
            "green": (COLORS["green"], COLORS["green_soft"]),
            "red": (COLORS["red"], COLORS["red_soft"]),
            "gray": (COLORS["muted"], COLORS["neutral_soft"]),
        }
        accent, soft = tones.get(tone, tones["blue"])

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
        layout.setSpacing(18)

        header = QHBoxLayout()
        header.setSpacing(13)
        header.addWidget(IconBadge(icon_name, soft, 44))

        heading = QVBoxLayout()
        heading.setSpacing(2)
        eyebrow_label = QLabel(eyebrow)
        eyebrow_label.setObjectName("DialogEyebrow")
        eyebrow_label.setWordWrap(True)
        eyebrow_label.setStyleSheet(f".QLabel {{ color:{accent}; }}")
        title_label = QLabel(tr(title))
        title_label.setObjectName("DialogTitle")
        title_label.setWordWrap(True)
        heading.addWidget(eyebrow_label)
        heading.addWidget(title_label)
        header.addLayout(heading, 1)

        close_button = QPushButton()
        close_button.setObjectName("DialogClose")
        close_button.setIcon(icon("close_gray"))
        close_button.setFixedSize(34, 34)
        close_button.setToolTip(tr("Close"))
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.clicked.connect(self.reject)
        header.addWidget(close_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background:{COLORS['border_soft']}; border:none;")
        layout.addWidget(divider)

        content_scroll = QScrollArea()
        content_scroll.setObjectName("DialogContentScroll")
        content_scroll.setWidgetResizable(True)
        content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        content_scroll.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        content_scroll.setMinimumHeight(84)
        content_scroll.setMaximumHeight(420)
        content = QWidget()
        content.setObjectName("DialogContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        body = QLabel(message)
        body.setObjectName("DialogBody")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.spinner: BusySpinner | None = None
        if busy:
            # Something is still running: the ring says so, and whoever opened
            # the dialog closes it the moment that work ends.
            busy_row = QHBoxLayout()
            busy_row.setContentsMargins(0, 0, 0, 0)
            busy_row.setSpacing(10)
            self.spinner = BusySpinner(18, "cyan" if tone != "red" else "red")
            busy_row.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignVCenter)
            busy_row.addWidget(body, 1)
            content_layout.addLayout(busy_row)
            self.spinner.start()
        else:
            content_layout.addWidget(body)

        if copy_text:
            copy_frame = QFrame()
            copy_frame.setObjectName("DialogNotice")
            copy_layout = QVBoxLayout(copy_frame)
            copy_layout.setContentsMargins(12, 10, 12, 10)
            copy_layout.setSpacing(7)
            command = QLabel(str(copy_text))
            command.setObjectName("DialogNoticeText")
            command.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            command.setWordWrap(True)
            copy_layout.addWidget(command)
            copy_button = QPushButton(copy_button_text)
            copy_button.setProperty("compactAction", True)
            copy_button.setCursor(Qt.CursorShape.PointingHandCursor)

            def copy_to_clipboard() -> None:
                clipboard = QApplication.clipboard()
                if clipboard is not None:
                    clipboard.setText(str(copy_text))
                copy_button.setText(tr("Copied"))

            copy_button.clicked.connect(copy_to_clipboard)
            copy_layout.addWidget(copy_button, 0, Qt.AlignmentFlag.AlignRight)
            content_layout.addWidget(copy_frame)

        if notice:
            notice_frame = QFrame()
            notice_frame.setObjectName("DialogNotice")
            notice_layout = QHBoxLayout(notice_frame)
            notice_layout.setContentsMargins(12, 10, 12, 10)
            notice_layout.setSpacing(9)
            notice_icon = QLabel()
            notice_icon.setPixmap(icon("info_blue").pixmap(18, 18))
            notice_text = QLabel(notice)
            notice_text.setObjectName("DialogNoticeText")
            notice_text.setWordWrap(True)
            notice_layout.addWidget(notice_icon, 0, Qt.AlignmentFlag.AlignTop)
            notice_layout.addWidget(notice_text, 1)
            content_layout.addWidget(notice_frame)

        content_scroll.setWidget(content)
        layout.addWidget(content_scroll)

        footer = QHBoxLayout()
        footer.addStretch(1)
        primary = QPushButton(button_text)
        primary.setObjectName("DialogPrimary")
        primary.setMinimumWidth(132)
        primary.setDefault(True)
        primary.setAutoDefault(True)
        primary.setCursor(Qt.CursorShape.PointingHandCursor)
        primary.clicked.connect(self.accept)
        footer.addWidget(primary)
        layout.addLayout(footer)

        localize_widget_tree(self)
        self.fit_to_content()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().showEvent(event)
        self.fit_to_content()
        center_dialog(self)
