"""Power delivery readings: what they need, and the I2C modification with photos.

One window, two panels. The left one says what this board needs (the message
depends on the kernel and on whether the service already runs), the wiring
and how to check it; the right one walks through the modification with the
photos. Owners asked for those pictures before touching the board.

The photos, wiring and research are BC250-Telemetry's (``hardware.md``, MIT,
by onlinermm and fansteori); the pinout comes from the AMD BC-250
Documentation project. They ship with the app, stripped of camera metadata,
so the guide works offline, and the footer links to the original.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core.external_links import open_external_url
from ..i18n import localize_widget_tree, tr, tr_format
from ..theme import application_stylesheet
from .buttons import WrappingButton as QPushButton
from .dialogs import center_dialog, enable_adaptive_dialog
from .widgets import dialog_card, icon

IMAGES = Path(__file__).resolve().parents[3] / "assets" / "telemetry-i2c"
GUIDE_URL = "https://github.com/onlinermm/BC250-Telemetry/blob/main/hardware.md"
CREDIT = (
    "Photos, wiring and research: BC250-Telemetry by onlinermm and fansteori (MIT license). "
    "Pinout: AMD BC-250 Documentation (elektricM), from mothenjoyer69's reverse engineering."
)
#: The two wires: header pin, TPMS1 pin, signal.
WIRING = (
    ("SCL (red)", "Pin 4", "SMB_CLK_MAIN"),
    ("SDA (blue)", "Pin 6", "SMB_DATA_MAIN"),
)
PHOTO_WIDTH = 600


class _Photo(QLabel):
    """A photo scaled to the panel; a click opens it full size."""

    def __init__(self, name: str, caption: str, width: int = PHOTO_WIDTH):
        super().__init__()
        self.path = IMAGES / name
        self.caption = caption
        pixmap = QPixmap(str(self.path))
        self.setObjectName("GuidePhoto")
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        if pixmap.isNull():
            self.setText(tr_format("Photo not found: {name}", name=name))
        else:
            self.setPixmap(pixmap.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation))
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setToolTip(tr("Click to see it full size"))
        self.setAccessibleName(tr(caption))

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().mouseReleaseEvent(event)
        if self.pixmap() is not None and not self.pixmap().isNull():
            _PhotoViewer(self.path, self.caption, self.window()).exec()


class _PhotoViewer(QDialog):
    def __init__(self, path: Path, caption: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr(caption))
        self.setStyleSheet(application_stylesheet())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        screen = self.screen().availableGeometry() if self.screen() is not None else None
        width = min(1280, (screen.width() - 120) if screen else 1100)
        height = min(960, (screen.height() - 160) if screen else 800)
        photo = QLabel()
        photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        photo.setPixmap(QPixmap(str(path)).scaled(
            width, height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        ))
        layout.addWidget(photo, 1)
        close = QPushButton(tr("Close"))
        close.setObjectName("DialogPrimary")
        close.clicked.connect(self.accept)
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)


def _text(text: str, name: str = "DialogBody") -> QLabel:
    label = QLabel(tr(text))
    label.setObjectName(name)
    label.setWordWrap(True)
    label.setProperty("naturalHeight", True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _heading(text: str, number: int = 0) -> QLabel:
    label = QLabel(f"{number}. {tr(text)}" if number else tr(text))
    label.setObjectName("GuideStep")
    return label


def _rule() -> QFrame:
    rule = QFrame()
    rule.setObjectName("GuideRule")
    rule.setFixedHeight(1)
    return rule


def _panel() -> tuple[QFrame, QVBoxLayout]:
    """One of the two boxes, scrolling on its own."""
    frame = QFrame()
    frame.setObjectName("GuidePanel")
    outer = QVBoxLayout(frame)
    outer.setContentsMargins(1, 1, 1, 1)
    content = QWidget()
    content.setObjectName("GuidePanelContent")
    column = QVBoxLayout(content)
    column.setContentsMargins(20, 18, 20, 20)
    column.setSpacing(14)
    scroll = QScrollArea()
    scroll.setObjectName("DialogContentScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
    scroll.setWidget(content)
    outer.addWidget(scroll)
    return frame, column


class I2cGuideDialog(QDialog):
    """What the power delivery readings need, beside the photo guide."""

    TELEMETRY = 2
    INSTALL = 3

    def __init__(self, parent: QWidget | None = None, *, message: str = "", can_install: bool = False):
        super().__init__(parent)
        self.setObjectName("InfoDialog")
        self.setModal(True)
        self.setWindowTitle(tr("Show the power delivery readings"))
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(application_stylesheet())
        # Photos of pins need room: wide, and nearly the screen's height.
        enable_adaptive_dialog(self, preferred_width=1120, preferred_height=900, minimum_width=760, minimum_height=480)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        card = dialog_card(self)
        outer.addWidget(card)
        frame = QVBoxLayout(card)
        frame.setContentsMargins(0, 0, 0, 0)
        frame.setSpacing(0)
        # No header: the photos and the steps get the whole height; Close is in the footer.

        body = QHBoxLayout()
        body.setContentsMargins(18, 16, 18, 16)
        body.setSpacing(14)
        left, left_column = _panel()
        right, right_column = _panel()
        left.setFixedWidth(380)
        body.addWidget(left)
        body.addWidget(right, 1)
        holder = QWidget()
        holder.setLayout(body)
        frame.addWidget(holder, 1)

        self._fill_status(left_column, message)
        self._fill_steps(right_column)

        footer_frame = QFrame()
        footer_frame.setObjectName("DialogFooter")
        footer = QHBoxLayout(footer_frame)
        footer.setContentsMargins(22, 12, 22, 12)
        footer.setSpacing(8)
        source = QPushButton(tr("Open BC250-Telemetry"))
        source.setObjectName("DialogSecondary")
        source.setIcon(icon("external_gray"))
        source.setCursor(Qt.CursorShape.PointingHandCursor)
        source.clicked.connect(lambda: open_external_url(GUIDE_URL))
        self.source_button = source
        footer.addWidget(source)
        footer.addStretch(1)
        close = QPushButton(tr("Close"))
        close.setObjectName("DialogSecondary")
        close.clicked.connect(self.reject)
        settings = QPushButton(tr("Open Telemetry settings"))
        settings.setObjectName("DialogSecondary" if can_install else "DialogPrimary")
        settings.clicked.connect(lambda: self.done(self.TELEMETRY))
        footer.addWidget(close)
        footer.addWidget(settings)
        # The same install as Settings › Telemetry, one step closer: only
        # offered while no kernel driver or running service already reads it.
        self.install_button = QPushButton(tr("Install the service"))
        self.install_button.setObjectName("DialogPrimary")
        self.install_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.install_button.clicked.connect(lambda: self.done(self.INSTALL))
        self.install_button.setVisible(can_install)
        footer.addWidget(self.install_button)
        (self.install_button if can_install else settings).setDefault(True)
        frame.addWidget(footer_frame)
        localize_widget_tree(self)

    # --- Panel 1: this board ---------------------------------------------------

    def _fill_status(self, column: QVBoxLayout, message: str) -> None:
        if message:
            column.addWidget(_text(message))
        column.addWidget(_text(
            "On a stock BC-250, I2C_HEADER1 and TPMS1 are not connected. Two wires between them put the "
            "board's voltage regulator (PMIC) on a bus Linux can read. No soldering is needed: the wires "
            "plug onto the pins."
        ))
        warning = QHBoxLayout()
        warning.setSpacing(9)
        glyph = QLabel()
        glyph.setPixmap(icon("warning_orange").pixmap(16, 16))
        glyph.setFixedSize(16, 18)
        warning.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)
        warning.addWidget(_text(
            "Work with the board switched off and the power supply unplugged. This is a community "
            "modification with no warranty: check every pin before powering on.",
            "GuideWarning",
        ), 1)
        column.addLayout(warning)
        column.addWidget(_rule())

        column.addWidget(_heading("Wiring"))
        table = QGridLayout()
        table.setHorizontalSpacing(18)
        table.setVerticalSpacing(7)
        for col, title in enumerate(("I2C_HEADER1", "TPMS1", "Signal")):
            head = QLabel(tr(title))
            head.setObjectName("GuideTableHead")
            table.addWidget(head, 0, col)
        for row, (source, pin, signal) in enumerate(WIRING, start=1):
            for col, value in enumerate((tr(source), tr(pin), signal)):
                cell = QLabel(value)
                cell.setObjectName("DialogIdentityValue")
                table.addWidget(cell, row, col)
        table.setColumnStretch(3, 1)
        column.addLayout(table)
        column.addWidget(_text("No ground wire: both headers already share the board's ground.", "GuideCaption"))
        column.addWidget(_rule())

        column.addWidget(_heading("Check it"))
        column.addWidget(_text(
            "Power on, then open Settings › Telemetry and install the BC250-Telemetry service under Power "
            "delivery (I2C mod). To check the bus by hand, this should show a device at 0x60:"
        ))
        command_box = QFrame()
        command_box.setObjectName("DialogDetail")
        box = QVBoxLayout(command_box)
        box.setContentsMargins(12, 9, 12, 9)
        box.addWidget(_text("sudo i2cdetect -y 4", "DialogDetailText"))
        column.addWidget(command_box)
        column.addWidget(_text(
            "Nothing on the bus? SCL and SDA swapped (check this first), a loose connector on TPMS1, or, "
            "rarely, a board revision without shared ground.",
            "GuideCaption",
        ))
        column.addStretch(1)
        column.addWidget(_rule())
        column.addWidget(_text(CREDIT, "GuideCaption"))

    # --- Panel 2: the modification, with photos --------------------------------

    def _fill_steps(self, column: QVBoxLayout) -> None:
        column.addWidget(_heading("Find I2C_HEADER1", 1))
        column.addWidget(_text(
            "I2C_HEADER1, beside the heatsink. Red is SCL (middle pin), blue is SDA (the pin closer to "
            "the power connectors)."
        ))
        column.addWidget(_Photo("i2c-header1-pins.jpg", "Find I2C_HEADER1"))
        column.addWidget(_rule())

        column.addWidget(_heading("Find TPMS1", 2))
        column.addWidget(_text(
            "TPMS1: 18 pins, 2.0 mm apart. The triangle marks pin 1 (bottom row, left). Pin 4 (red, to SCL) "
            "and pin 6 (blue, to SDA) are the second and third pins of the top row."
        ))
        column.addWidget(_Photo("tpms1-pins.jpg", "Find TPMS1"))
        column.addWidget(_rule())

        column.addWidget(_heading("Connect the two wires", 3))
        column.addWidget(_text(
            "SCL to pin 4 and SDA to pin 6. Swapping them damages nothing, but the bus stays silent. The "
            "2-pin cable of an old PC case's power or reset button fits well. Standard Dupont connectors are "
            "2.54 mm and sit loose on TPMS1, so give that end a 2.0 mm connector."
        ))
        pair = QHBoxLayout()
        pair.setSpacing(10)
        for name, caption in (
            ("tpms1-connected.jpg", "TPMS1 with the connector on pins 4 and 6."),
            ("i2c-header1-connected.jpg", "I2C_HEADER1 with the wires routed through the heatsink."),
        ):
            holder = QVBoxLayout()
            holder.setSpacing(6)
            holder.addWidget(_Photo(name, caption, width=(PHOTO_WIDTH - 10) // 2))
            holder.addWidget(_text(caption, "GuideCaption"))
            pair.addLayout(holder, 1)
        column.addLayout(pair)
        column.addStretch(1)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().showEvent(event)
        center_dialog(self)
