"""Power delivery readings: the three ways to get them, one tab each.

* BC250-Telemetry (I2C): the community modification, two wires and a
  service. Two panels: what this board needs, the wiring and how to check it
  beside the photo walk-through owners asked for before touching the board.
* bc250-vrm: Hexxeh's kernel driver reads the same regulator through the fan
  chip, without wires. A short guide and a button that builds it with DKMS.
* bc250-memory: the same author's driver for the VRAM (GDDR6) temperature.

The tabs are the Processes page's: words underlined, no boxes.

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
    QButtonGroup,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.external_links import open_external_url
from ..i18n import localize_widget_tree, tr, tr_format
from ..theme import COLORS, application_stylesheet
from .buttons import WrappingButton as QPushButton
from .dialogs import center_dialog, enable_adaptive_dialog
from .widgets import command_box, dialog_card, icon

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

VRM_URL = "https://github.com/Hexxeh/bc250-vrm-dkms"
VRAM_URL = "https://github.com/Hexxeh/bc250-memory-dkms"
#: Tab key, label, the link the footer opens, and its button text.
#: Project names, not translated.
TABS = (
    ("i2c", "BC250-Telemetry (I2C)", GUIDE_URL, "BC250-Telemetry"),
    ("vrm", "bc250-vrm", VRM_URL, "bc250-vrm"),
    ("vram", "bc250-memory (VRAM)", VRAM_URL, "bc250-memory"),
)
#: What each driver's state says in its tab; ``{value}`` is its live reading.
#: The unsupported, built-in and silent cases reuse the cards' own notes.
DRIVER_STATES = {
    "vrm": {
        "unsupported": "Builds on Arch-based systems (Arch, CachyOS, Manjaro) on a BC-250.",
        "managed-elsewhere": "Your kernel already includes this driver (MastaG's BC-250 kernels do), so there is nothing to build.",
        "installed": "Installed, but the regulator does not answer through the fan chip. Run sudo dmesg | grep bc250_vrm to see why.",
        "update-available": "This copy was built by an earlier version of Control Center. Press Update to build it again with the current fixes.",
    },
    "vram": {
        "unsupported": "Needs an Arch-based system (Arch, CachyOS, Manjaro) on a BC-250 with BIOS P3.00: the driver patches the SMU at addresses reviewed for that BIOS only.",
        "managed-elsewhere": "Your kernel already includes this driver (MastaG's BC-250 kernels do), so there is nothing to build.",
        "installed": "Installed, but not reading. It needs a BIOS that allows SMU access; run sudo dmesg | grep bc250_memory to see why.",
        "update-available": "This copy was built by an earlier version of Control Center. Press Update to build it again with the current fixes.",
    },
}


def _tab_stylesheet() -> str:
    """The Processes page's tabs, for this window."""
    c = COLORS
    return f"""
QFrame[guideTabRail='true'] {{
    background: transparent; border: none; border-bottom: 1px solid {c['border_soft']};
}}
QPushButton[guideTab='true'] {{
    background: transparent; border: none; border-bottom: 2px solid transparent;
    border-radius: 0px; min-height: 0px; padding: 8px 2px 7px 2px;
    color: {c['muted']}; font-size: 12px; font-weight: 700;
}}
QPushButton[guideTab='true']:hover {{ color: {c['text']}; }}
QPushButton[guideTab='true']:checked {{
    color: {c['text']}; border-bottom: 2px solid {c['blue']}; font-weight: 780;
}}
"""


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
    """The three ways to read the board's power delivery, one tab each."""

    TELEMETRY = 2
    INSTALL = 3
    BUILD_VRM = 4
    BUILD_VRAM = 5

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        message: str = "",
        can_install: bool = False,
        drivers: dict | None = None,
        tab: str = "i2c",
    ):
        super().__init__(parent)
        self.setObjectName("InfoDialog")
        self.setModal(True)
        self.setWindowTitle(tr("Show the power delivery readings"))
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(application_stylesheet() + _tab_stylesheet())
        # Photos of pins need room: wide, and nearly the screen's height.
        enable_adaptive_dialog(self, preferred_width=1120, preferred_height=900, minimum_width=760, minimum_height=480)
        self._can_install = can_install
        self._drivers = dict(drivers or {})

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        card = dialog_card(self)
        outer.addWidget(card)
        frame = QVBoxLayout(card)
        frame.setContentsMargins(0, 0, 0, 0)
        frame.setSpacing(0)
        # No header: the tabs, then the guide with the whole height; Close is in the footer.

        rail = QFrame()
        rail.setProperty("guideTabRail", True)
        tabs = QHBoxLayout(rail)
        tabs.setContentsMargins(22, 10, 22, 0)
        tabs.setSpacing(22)
        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)
        self.tab_buttons: dict[str, QPushButton] = {}
        for key, label, _url, _link in TABS:
            button = QPushButton(label)
            button.setProperty("i18nLiteral", True)
            button.setProperty("guideTab", True)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, name=key: self.select_tab(name))
            self.tab_group.addButton(button)
            tabs.addWidget(button)
            self.tab_buttons[key] = button
        tabs.addStretch(1)
        frame.addWidget(rail)

        self.pages = QStackedWidget()
        self.page_index: dict[str, int] = {}
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
        self._fill_status(left_column, message)
        self._fill_steps(right_column)
        self.page_index["i2c"] = self.pages.addWidget(holder)
        self.page_index["vrm"] = self.pages.addWidget(self._driver_page("vrm"))
        self.page_index["vram"] = self.pages.addWidget(self._driver_page("vram"))
        frame.addWidget(self.pages, 1)

        footer_frame = QFrame()
        footer_frame.setObjectName("DialogFooter")
        footer = QHBoxLayout(footer_frame)
        footer.setContentsMargins(22, 12, 22, 12)
        footer.setSpacing(8)
        source = QPushButton(tr("Open BC250-Telemetry"))
        source.setObjectName("DialogSecondary")
        source.setIcon(icon("external_gray"))
        source.setCursor(Qt.CursorShape.PointingHandCursor)
        source.clicked.connect(lambda: open_external_url(self._link))
        self.source_button = source
        self._link = GUIDE_URL
        footer.addWidget(source)
        footer.addStretch(1)
        close = QPushButton(tr("Close"))
        close.setObjectName("DialogSecondary")
        close.clicked.connect(self.reject)
        self.settings_button = QPushButton(tr("Open Telemetry settings"))
        self.settings_button.setObjectName("DialogSecondary" if can_install else "DialogPrimary")
        self.settings_button.clicked.connect(lambda: self.done(self.TELEMETRY))
        footer.addWidget(close)
        footer.addWidget(self.settings_button)
        # The same install as Settings › Telemetry, one step closer: only
        # offered while no kernel driver or running service already reads it.
        self.install_button = QPushButton(tr("Install the service"))
        self.install_button.setObjectName("DialogPrimary")
        self.install_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.install_button.clicked.connect(lambda: self.done(self.INSTALL))
        footer.addWidget(self.install_button)
        # The kernel tabs' one action: build the driver in the terminal.
        self.build_button = QPushButton(tr("Compile and install"))
        self.build_button.setObjectName("DialogPrimary")
        self.build_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.build_button.clicked.connect(
            lambda: self.done(self.BUILD_VRM if self.current_tab == "vrm" else self.BUILD_VRAM)
        )
        footer.addWidget(self.build_button)
        frame.addWidget(footer_frame)
        self.current_tab = ""
        self.select_tab(tab if tab in self.page_index else "i2c")
        localize_widget_tree(self)

    def _driver_state(self, key: str) -> str:
        info = self._drivers.get("vrm_sensor" if key == "vrm" else "vram_sensor") or {}
        return str(info.get("state") or "")

    def select_tab(self, key: str) -> None:
        """Show one way; the footer offers that way's link and action."""
        self.current_tab = key
        self.pages.setCurrentIndex(self.page_index[key])
        for name, button in self.tab_buttons.items():
            button.setChecked(name == key)
        _key, _label, url, link = next(item for item in TABS if item[0] == key)
        self._link = url
        self.source_button.setText(
            tr("Open BC250-Telemetry") if key == "i2c" else tr_format("Open {project}", project=link)
        )
        i2c = key == "i2c"
        self.settings_button.setVisible(i2c)
        self.install_button.setVisible(i2c and self._can_install)
        driver_state = self._driver_state(key)
        buildable = not i2c and driver_state in {"not-installed", "installed", "update-available"}
        self.build_button.setVisible(buildable)
        self.build_button.setText(tr(
            "Update" if driver_state == "update-available"
            else "Compile again" if driver_state == "installed" else "Compile and install"
        ))
        default = self.build_button if buildable else self.install_button if i2c and self._can_install else (
            self.settings_button if i2c else None
        )
        for button in (self.settings_button, self.install_button, self.build_button):
            button.setDefault(button is default)

    # --- The kernel drivers ------------------------------------------------------

    def _driver_page(self, key: str) -> QWidget:
        frame, column = _panel()
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.addWidget(frame)
        frame.setMaximumWidth(860)
        vrm = key == "vrm"
        column.addWidget(_heading("Power delivery without the I2C wires" if vrm else "VRAM temperature"))
        column.addWidget(_text(
            "bc250-vrm is a kernel driver by Liam McLoughlin (Hexxeh). It reads the board's voltage regulator "
            "through the fan chip, so it needs none of the I2C wiring: the 12 V input, the CPU and GPU rails "
            "and the VRM temperatures show up on the Dashboard and in sensors."
            if vrm else
            "bc250-memory is the same author's driver for the video memory. It reads the temperature of the "
            "eight GDDR6 chips through the SMU and shows it as a normal sensor: the hottest chip, the average "
            "and each chip."
        ))
        column.addWidget(_rule())
        column.addWidget(_heading("This board"))
        self._fill_driver_state(column, key)
        column.addWidget(_rule())
        column.addWidget(_heading("How it is installed"))
        column.addWidget(_text(
            "Control Center downloads the reviewed source, builds it with DKMS for your kernel and loads it. "
            "When the kernel updates, DKMS builds it again by itself. It needs Arch, CachyOS, Manjaro or "
            "another Arch-based system; MastaG's BC-250 kernels already include it."
        ))
        warning = QHBoxLayout()
        warning.setSpacing(9)
        glyph = QLabel()
        glyph.setPixmap(icon("warning_orange").pixmap(16, 16))
        glyph.setFixedSize(16, 18)
        warning.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)
        warning.addWidget(_text(
            "Use one way, not both: if you already have the I2C wires with the BC250-Telemetry service, "
            "remove the service first. Two readers on the same regulator mix up each other's readings."
            if vrm else
            "When it loads, the driver patches the SMU firmware in memory. That patch was checked for BIOS "
            "P3.00 with SMU access unlocked; on any other BIOS Control Center does not install it.",
            "GuideWarning",
        ), 1)
        column.addLayout(warning)
        column.addWidget(_rule())
        column.addWidget(_heading("Check it"))
        column.addWidget(_text(
            "Once it is installed, this lists the driver's readings:"
        ))
        column.addWidget(command_box("sensors 'bc250_vrm-*'" if vrm else "sensors 'bc250_memory-*'"))
        column.addStretch(1)
        column.addWidget(_rule())
        credit = QLabel(
            "bc250-vrm-dkms · Liam McLoughlin (Hexxeh) · GPL-2.0"
            if vrm else
            "bc250-memory-dkms · Liam McLoughlin (Hexxeh) · GPL-2.0 · SMU payload: pan-Rijovich (MIT)"
        )
        credit.setObjectName("GuideCaption")
        credit.setProperty("i18nLiteral", True)
        credit.setWordWrap(True)
        column.addWidget(credit)
        return page

    def _fill_driver_state(self, column: QVBoxLayout, key: str) -> None:
        info = self._drivers.get("vrm_sensor" if key == "vrm" else "vram_sensor") or {}
        state = str(info.get("state") or "")
        reading = info.get("reading")
        value = f"{reading:.0f} °C" if isinstance(reading, (int, float)) else ""
        if state == "active":
            text = tr_format("Installed and reading: {value}.", value=value)
        elif state == "not-installed":
            text = tr("Not installed yet. Compile and install builds it in a terminal; it asks for your password.")
        elif state in DRIVER_STATES[key]:
            text = tr(DRIVER_STATES[key][state])
            if state == "managed-elsewhere" and value:
                text += " " + tr_format("Reading now: {value}.", value=value)
        else:
            text = tr("Could not check this board yet.")
        label = QLabel(text)
        label.setObjectName("DialogBody")
        label.setWordWrap(True)
        label.setProperty("naturalHeight", True)
        label.setProperty("i18nLiteral", True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        column.addWidget(label)

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
