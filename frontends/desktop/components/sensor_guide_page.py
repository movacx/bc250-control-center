"""Settings › Telemetry › Board sensors guide.

The power delivery guide used to be a window of its own, opened from the
dashboard. It now lives inside Settings, next to the rows that install what
it describes, and the dashboard's "How to enable" opens it here.

Three tabs, one per way to get the readings:

* I2C modification: what you need, the three steps with BC250-Telemetry's
  photos, installing the service, checking it, and what to look at when the
  bus stays silent.
* bc250-vrm and bc250-memory: Hexxeh's kernel drivers, with this board's
  state and the one action it allows (install, update or remove).

Photos, wiring and most of the text are the original guide's
(``i2c_guide``), so they stay translated and credited the same way.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.external_links import open_external_url
from ..i18n import tr, tr_format
from .i2c_guide import (
    CREDIT,
    DRIVER_STATES,
    GUIDE_URL,
    VRAM_URL,
    VRM_URL,
    WIRING,
    _heading,
    _Photo,
    _rule,
    _tab_stylesheet,
    _text,
)
from .widgets import command_box, icon

#: Tab key, label. The project names are not translated.
TABS = (
    ("i2c", "I2C modification"),
    ("vrm", "bc250-vrm"),
    ("vram", "bc250-memory"),
)
PHOTO_WIDTH = 560

NEEDS = (
    "Two wires with a 2-pin connector. The cable of an old PC case's power or reset button works well.",
    "A 2.0 mm connector for the TPMS1 end: standard 2.54 mm Dupont plugs sit loose on it.",
    "Nothing to solder and no ground wire: both headers already share the board's ground.",
    "The board switched off, with the power supply unplugged.",
)
TROUBLESHOOTING = (
    "SCL and SDA swapped. It damages nothing, but the bus stays silent: swap them and try again.",
    "A loose connector on TPMS1. A 2.54 mm plug moves on 2.0 mm pins.",
    "The wrong pins on TPMS1. Count from the triangle: pin 1 is bottom left, pins 4 and 6 are the second and third of the top row.",
    "A kernel that reads the regulator itself (bc250_vrm). It keeps the bus to itself; use the bc250-vrm tab instead.",
)


def _bullets(items) -> QWidget:
    host = QWidget()
    column = QVBoxLayout(host)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(6)
    for item in items:
        row = QHBoxLayout()
        row.setSpacing(8)
        dot = QLabel("•")
        dot.setObjectName("DialogBody")
        dot.setProperty("i18nLiteral", True)
        row.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(_text(item), 1)
        column.addLayout(row)
    return host


def _warning(text: str) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(9)
    glyph = QLabel()
    glyph.setPixmap(icon("warning_orange").pixmap(16, 16))
    glyph.setFixedSize(16, 18)
    row.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)
    row.addWidget(_text(text, "GuideWarning"), 1)
    return row


def _action_row(label: QLabel, button: QPushButton) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(12)
    row.addWidget(label, 1)
    row.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
    return row


def _small_button(text: str) -> QPushButton:
    button = QPushButton(tr(text))
    button.setProperty("toolbarAction", True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return button


def _command(text: str) -> QFrame:
    """The shared command box, its copy button sized like the page's others."""
    frame = command_box(text)
    for button in frame.findChildren(QPushButton):
        button.setObjectName("")
        button.setProperty("toolbarAction", True)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return frame


def _link(text: str, url: str) -> QPushButton:
    button = QPushButton(text + "  ↗")
    button.setProperty("footerLink", True)
    button.setProperty("i18nLiteral", True)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.clicked.connect(lambda: open_external_url(url))
    return button


class SensorGuidePage(QWidget):
    """The guide as a Settings page; Settings owns what its buttons start."""

    install_service_requested = pyqtSignal()
    #: "vrm_sensor:install" / "vram_sensor:remove", as the Compatibility cards send.
    driver_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setStyleSheet(_tab_stylesheet())
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        rail = QFrame()
        rail.setProperty("guideTabRail", True)
        tabs = QHBoxLayout(rail)
        tabs.setContentsMargins(0, 4, 0, 0)
        tabs.setSpacing(22)
        group = QButtonGroup(self)
        group.setExclusive(True)
        self.tab_buttons: dict[str, QPushButton] = {}
        for key, label in TABS:
            button = QPushButton(tr(label))
            button.setProperty("guideTab", True)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, name=key: self.select_tab(name))
            group.addButton(button)
            tabs.addWidget(button)
            self.tab_buttons[key] = button
        tabs.addStretch(1)
        root.addWidget(rail)

        self.pages = QStackedWidget()
        self.page_index = {
            "i2c": self.pages.addWidget(self._i2c_page()),
            "vrm": self.pages.addWidget(self._driver_page("vrm")),
            "vram": self.pages.addWidget(self._driver_page("vram")),
        }
        root.addWidget(self.pages)
        self.current_tab = ""
        self.select_tab("i2c")

    def select_tab(self, key: str) -> None:
        key = key if key in self.page_index else "i2c"
        self.current_tab = key
        self.pages.setCurrentIndex(self.page_index[key])
        # Only the shown tab counts for the height: otherwise a short tab is
        # stretched to the photo tab's length, with gaps between its lines.
        for index in range(self.pages.count()):
            policy = QSizePolicy.Policy.Preferred if index == self.page_index[key] else QSizePolicy.Policy.Ignored
            self.pages.widget(index).setSizePolicy(QSizePolicy.Policy.Preferred, policy)
        self.pages.adjustSize()
        self.pages.updateGeometry()
        for name, button in self.tab_buttons.items():
            button.setChecked(name == key)

    # --- state ------------------------------------------------------------------

    def set_state(self, *, status: str, service: dict, drivers: dict) -> None:
        """What this board has now: the status line, the service and both drivers."""
        self.status_label.setText(tr(status) if status else "")
        self.status_box.setVisible(bool(status))
        managed = bool(service.get("managed"))
        kind = str(service.get("state") or "")
        self.service_button.setToolTip("")
        if kind == "external":
            self.service_label.setText(tr("Installed with BC250-Telemetry's own installer, so Control Center leaves it alone."))
            self.service_button.setText(tr("Installed separately"))
            self.service_button.setEnabled(False)
        elif managed:
            self.service_label.setText(tr("Running" if kind == "publishing" else "Installed"))
            self.service_button.setText(tr("Remove service"))
            self.service_button.setEnabled(True)
        else:
            supported = bool(service.get("supported"))
            # The service module states it in English: shown through the catalog.
            reason = tr(str(service.get("blocked_reason") or ""))
            self.service_label.setText(tr("Not installed") if supported else (reason or tr("Not available here")))
            self.service_button.setText(tr("Install service"))
            self.service_button.setEnabled(supported)
            self.service_button.setToolTip(reason)
        for key, driver in (("vrm", "vrm_sensor"), ("vram", "vram_sensor")):
            self._fill_driver(key, dict(drivers.get(driver) or {}))

    def _fill_driver(self, key: str, info: dict) -> None:
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
        self.driver_labels[key].setText(text)
        button = self.driver_buttons[key]
        action = (
            "remove" if state in {"active", "installed"}
            else "install" if state in {"not-installed", "update-available"} else ""
        )
        button.setVisible(bool(action))
        button.setProperty("guideAction", action)
        if action:
            button.setText(tr(
                "Remove" if action == "remove" else "Update" if state == "update-available" else "Compile and install"
            ))

    def _driver_clicked(self, key: str) -> None:
        action = str(self.driver_buttons[key].property("guideAction") or "")
        if action:
            self.driver_requested.emit(f"{'vrm_sensor' if key == 'vrm' else 'vram_sensor'}:{action}")

    # --- the I2C modification ---------------------------------------------------

    def _column(self) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 18, 0, 8)
        column.setSpacing(12)
        return page, column

    def _i2c_page(self) -> QWidget:
        page, column = self._column()
        column.addWidget(_text(
            "Two wires between I2C_HEADER1 and TPMS1 let Linux read the board's voltage regulator: the 12 V "
            "input, the CPU and GPU rails, their current and power, and the VRM temperatures. The "
            "BC250-Telemetry service then publishes them for the dashboard."
        ))
        self.status_box = QFrame()
        self.status_box.setObjectName("DialogNotice")
        box = QVBoxLayout(self.status_box)
        box.setContentsMargins(14, 10, 14, 10)
        self.status_label = _text("", "DialogNoticeText")
        box.addWidget(self.status_label)
        column.addWidget(self.status_box)

        column.addWidget(_heading("What you need"))
        column.addWidget(_bullets(NEEDS))
        column.addLayout(_warning(
            "Work with the board switched off and the power supply unplugged. This is a community "
            "modification with no warranty: check every pin before powering on."
        ))
        column.addWidget(_rule())

        column.addWidget(_heading("Find I2C_HEADER1", 1))
        column.addWidget(_text(
            "I2C_HEADER1, beside the heatsink. Red is SCL (middle pin), blue is SDA (the pin closer to "
            "the power connectors)."
        ))
        column.addWidget(_Photo("i2c-header1-pins.jpg", "Find I2C_HEADER1", width=PHOTO_WIDTH))
        column.addWidget(_rule())

        column.addWidget(_heading("Find TPMS1", 2))
        column.addWidget(_text(
            "TPMS1: 18 pins, 2.0 mm apart. The triangle marks pin 1 (bottom row, left). Pin 4 (red, to SCL) "
            "and pin 6 (blue, to SDA) are the second and third pins of the top row."
        ))
        column.addWidget(_Photo("tpms1-pins.jpg", "Find TPMS1", width=PHOTO_WIDTH))
        column.addWidget(_rule())

        column.addWidget(_heading("Connect the two wires", 3))
        column.addWidget(_text(
            "SCL to pin 4 and SDA to pin 6. Swapping them damages nothing, but the bus stays silent. The "
            "2-pin cable of an old PC case's power or reset button fits well. Standard Dupont connectors are "
            "2.54 mm and sit loose on TPMS1, so give that end a 2.0 mm connector."
        ))
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
            pair.addLayout(holder)
        pair.addStretch(1)
        column.addLayout(pair)
        column.addWidget(_rule())

        column.addWidget(_heading("Install the service", 4))
        column.addWidget(_text(
            "Power the board on. Control Center builds BC250-Telemetry from its reviewed source and installs "
            "only the service that reads the regulator; it asks for your password once."
        ))
        self.service_label = _text("")
        self.service_button = _small_button("Install service")
        self.service_button.clicked.connect(self.install_service_requested)
        column.addLayout(_action_row(self.service_label, self.service_button))
        column.addWidget(_rule())

        column.addWidget(_heading("Check it", 5))
        column.addWidget(_text(
            "The readings appear on the dashboard within a few seconds, and Telemetry › Detection says the "
            "regulator answers. To check the bus by hand, this should show a device at 0x60:"
        ))
        column.addWidget(_command("sudo i2cdetect -y 4"))
        column.addWidget(_heading("If nothing shows up"))
        column.addWidget(_bullets(TROUBLESHOOTING))
        column.addWidget(_rule())
        column.addWidget(_text(CREDIT, "GuideCaption"))
        column.addWidget(_link("BC250-Telemetry", GUIDE_URL), 0, Qt.AlignmentFlag.AlignLeft)
        column.addStretch(1)
        return page

    # --- the kernel drivers -----------------------------------------------------

    def _driver_page(self, key: str) -> QWidget:
        if not hasattr(self, "driver_labels"):
            self.driver_labels: dict[str, QLabel] = {}
            self.driver_buttons: dict[str, QPushButton] = {}
        page, column = self._column()
        vrm = key == "vrm"
        column.addWidget(_text(
            "bc250-vrm is a kernel driver by Liam McLoughlin (Hexxeh). It reads the board's voltage regulator "
            "through the fan chip, so it needs none of the I2C wiring: the 12 V input, the CPU and GPU rails "
            "and the VRM temperatures show up on the Dashboard and in sensors."
            if vrm else
            "bc250-memory is the same author's driver for the video memory. It reads the temperature of the "
            "eight GDDR6 chips through the SMU and shows it as a normal sensor: the hottest chip, the average "
            "and each chip."
        ))
        column.addWidget(_heading("This board"))
        label = _text("")
        label.setProperty("i18nLiteral", True)
        button = _small_button("Compile and install")
        button.clicked.connect(lambda _checked=False, name=key: self._driver_clicked(name))
        self.driver_labels[key] = label
        self.driver_buttons[key] = button
        column.addLayout(_action_row(label, button))
        column.addWidget(_rule())
        column.addWidget(_heading("How it is installed"))
        column.addWidget(_text(
            "Control Center downloads the reviewed source, builds it with DKMS for your kernel and loads it. "
            "When the kernel updates, DKMS builds it again by itself. It needs Arch, CachyOS, Manjaro or "
            "another Arch-based system; MastaG's BC-250 kernels already include it."
        ))
        column.addLayout(_warning(
            "Use one way, not both: if you already have the I2C wires with the BC250-Telemetry service, "
            "remove the service first. Two readers on the same regulator mix up each other's readings."
            if vrm else
            "On a BIOS that keeps the SMU locked (stock P3.00), the driver waits until the SMU is patched. "
            "Press Monitor live on the dashboard once after each power-on: Control Center patches the SMU "
            "and the driver reads from then on."
        ))
        column.addWidget(_rule())
        column.addWidget(_heading("Check it"))
        column.addWidget(_text("Once it is installed, this lists the driver's readings:"))
        column.addWidget(_command("sensors 'bc250_vrm-*'" if vrm else "sensors 'bc250_memory-*'"))
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
        column.addWidget(_link("bc250-vrm" if vrm else "bc250-memory", VRM_URL if vrm else VRAM_URL), 0,
                         Qt.AlignmentFlag.AlignLeft)
        column.addStretch(1)
        return page
