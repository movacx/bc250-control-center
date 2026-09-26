"""Firmware (BIOS): turns a USB drive into a BIOS update kit for the BC-250.

Flashing a BC-250 used to start with a list of chores that each stop a
newcomer: find the right image among forks and Discord attachments, find the
flash tool, know the stick must be FAT32, know how to format one on Linux,
know which folder goes where. This page does all of it. The user picks a
firmware and a USB drive; the page downloads the pinned files, checks their
SHA-256, erases the drive through UDisks2, formats it FAT32, copies a kit that
boots into a menu, reads every file back, and ejects it.

The page is laid out the way it is read, in two columns. On the left, the
full height of the page, the images, grouped into modded and stock and
compared on the same four facts and what each offers, so choosing one is
reading down a column rather than parsing a paragraph per card. On the right,
from top to bottom: what to know before starting, then one table of what is
done with the choice: the custom boot logo, the BIOS this board runs now, the
drive, and the preparation with its button. How to boot the stick and flash
lives in the guided tour: the page itself is for doing it. Where every file
comes from is credited in Settings, with the other projects the app uses.

The logo, optional, is a picture of the user's own for the screen the board
starts on. Nothing changes until the USB is prepared; then it goes into the
chosen image, which is checked to differ from the published one in its logo
and nothing else before a byte reaches the drive.

The page never flashes anything itself. The flash happens on the board, from
the USB, after the kit has saved the BIOS it replaces.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from bc250cc.domain.firmware.boot_logo import LOGO_HEIGHT, LOGO_WIDTH
from bc250cc.domain.firmware.catalog import (
    DEFAULT_FAMILY,
    FAMILIES_BY_KEY,
    FIRMWARE_FAMILIES,
    FirmwareFamily,
    FirmwareImage,
    archives_of,
    sources_for,
)
from bc250cc.domain.firmware.usb import UsbDrive, format_size
from bc250cc.domain.firmware.usb_kit import plan_kit
from bc250cc.infrastructure.firmware import lzma1, udisks
from bc250cc.infrastructure.firmware.board import (
    BoardFirmware,
    read_board_firmware,
    record_prepared_kit,
)
from bc250cc.infrastructure.firmware.preparation import STEPS, UsbPreparation, steps_for
from bc250cc.infrastructure.firmware.store import FirmwareStore

from ..components.async_tools import BackgroundExecutor
from ..components.busy_spinner import BusySpinner
from ..components.buttons import WrappingButton as QPushButton
from ..components.dashboard_instruments import HeadingLabel
from ..components.page_widgets import ConfirmDialog, SectionCard, caption
from ..components.widgets import icon
from ..core.boot_logo_image import (
    SIZE_RANGE,
    LogoImageError,
    Picture,
    encode_logo,
    load_picture,
    readable_patterns,
    render_logo,
)
from ..core.error_diagnostics import diagnose_error
from ..core.external_links import open_external_url
from ..core.firmware_session import UsbDriveWatcher, UsbPreparationJob
from ..i18n import tr, tr_format
from ..theme import COLORS

logger = logging.getLogger(__name__)

#: Same breakpoint as the CPU and GPU modules, so the screens reflow together.
STACK_WIDTH = 1180
#: Height of the firmware list when it sits above the rest instead of beside
#: it: enough for two images and the start of a third, so the scroll bar
#: announces that there is more.
STACKED_LIST_HEIGHT = 430
#: Width at which a firmware's four facts stop fitting on one line.
FACTS_ONE_ROW_WIDTH = 520
#: The two columns: the firmware list, and everything done with the choice.
CONTROLS_STRETCH = 11
SIDE_STRETCH = 9
#: Side by side, the columns end this far above the bottom of the page: just
#: above the sidebar's own Firmware button, which the rail keeps 112 px from
#: the bottom of the window whatever its height.
FOOT_CLEARANCE = 124
PAGE_BOTTOM = 24
#: Between two sections of the side table, before it shares out spare height.
SECTION_GAP = 18
#: "Before you start" heads the right column when shown. Hidden, its warning
#: is still given where it is acted on: in the confirmation and the tour.
SAFETY_PANEL_SHOWN = False
STEP_TITLES = {
    "download": "Download and verify the firmware",
    "logo": "Add your boot logo",
    "check": "Check the USB drive",
    "erase": "Erase the USB drive",
    "format": "Format it FAT32",
    "copy": "Copy the update kit",
    "verify": "Read back and verify every file",
    "eject": "Eject the USB drive",
}
#: Each step's share of the whole bar: downloads and copying dominate.
STEP_WEIGHTS = {
    "download": 45, "logo": 4, "check": 2, "erase": 5, "format": 5, "copy": 25, "verify": 15,
    "eject": 3,
}
#: The images, in the two groups the list shows them in.
CATEGORIES = (("modded", "Modded BIOS"), ("stock", "Stock BIOS (ASRock)"))
#: A BC-250's die has eight CPU cores, whatever the firmware leaves running.
DIE_CORES = 8
RECOVERY_GUIDE = "https://elektricm.github.io/amd-bc250-docs/bios/recovery/"
#: Said on the page, in the confirmation and in the tour, because it is the one
#: thing that makes a finished flash look like a dead board.
AFTER_FLASH_WARNING = (
    "After an ASRock image the board shows no picture until the CMOS is cleared: "
    "unplug it and take the coin battery out for a minute. MeiMeiDXE resets its "
    "settings by itself."
)
#: The slider waits this long after its last move before encoding again.
LOGO_SETTLE_MS = 120
LOGO_CODEC_MISSING = (
    "Adding a logo needs liblzma 5.4 or newer, from the xz package, and this "
    "system does not have it."
)
LOGO_NOT_THIS_FIRMWARE = "This firmware cannot take a custom logo. The USB gets it as published."


def _megabytes(size: int) -> str:
    return f"{size / 1000 ** 2:.1f} MB"


def _kilobytes(size: int) -> str:
    return f"{size / 1000:.0f} KB"


def _note(text: str = "", tone: str = "caution") -> QLabel:
    label = QLabel(text)
    label.setProperty("firmwareNote", tone)
    label.setWordWrap(True)
    label.setMinimumWidth(0)
    return label


def _heading(text: str, role: str = "groupTitle") -> HeadingLabel:
    """An upper-case section heading that stays switchable between languages."""
    label = HeadingLabel()
    label.source_text = text
    label.setText(tr(text))
    label.setProperty(role, True)
    label.setMinimumWidth(0)
    return label


def _hairline() -> QFrame:
    line = QFrame()
    line.setProperty("instrumentHairline", True)
    line.setFixedHeight(1)
    return line


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def _enclosing_scroll_area(widget: QWidget) -> QScrollArea | None:
    node = widget.parentWidget()
    while node is not None and not isinstance(node, QScrollArea):
        node = node.parentWidget()
    return node


class _Fact(QFrame):
    """One line of a summary: name on the left, value on the right.

    The dashboard's reading row, minus its unit column: a firmware name has
    no unit, and the reading's habit of lifting a trailing word into one
    would have cut "CachyOS logo" in half.
    """

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("reading", True)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 7, 0, 7)
        row.setSpacing(12)
        self.label = QLabel(tr(label))
        self.label.setProperty("readingLabel", True)
        self.label.setMinimumWidth(0)
        row.addWidget(self.label, 0, Qt.AlignmentFlag.AlignTop)
        self.value = QLabel("--")
        self.value.setProperty("readingValue", True)
        self.value.setProperty("i18nLiteral", True)
        self.value.setWordWrap(True)
        self.value.setMinimumWidth(0)
        self.value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.value, 1)


class _FactList(QWidget):
    """A heading and its facts, separated by hairlines."""

    def __init__(self, title: str, labels: tuple[tuple[str, str], ...], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        self.title = _heading(title)
        box.addWidget(self.title)
        box.addSpacing(4)
        self.facts: dict[str, _Fact] = {}
        for index, (key, label) in enumerate(labels):
            if index:
                box.addWidget(_hairline())
            self.facts[key] = _Fact(label)
            box.addWidget(self.facts[key])

    def set(self, key: str, value: str) -> None:
        self.facts[key].value.setText(value)


class _FactCell(QWidget):
    """One fact of a strip: a small upper-case name over its value."""

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(0)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(4)
        self.label = _heading(label, "firmwareFactLabel")
        box.addWidget(self.label)
        self.value = QLabel("--")
        self.value.setProperty("firmwareFactValue", True)
        self.value.setProperty("i18nLiteral", True)
        self.value.setWordWrap(True)
        self.value.setMinimumWidth(0)
        box.addWidget(self.value)


class _FactStrip(QWidget):
    """A heading and its facts side by side, the way a firmware card shows its
    own: a few short values read across instead of down."""

    def __init__(self, title: str, labels: tuple[tuple[str, str], ...], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)
        self.title = _heading(title)
        box.addWidget(self.title)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(18)
        self.facts: dict[str, _FactCell] = {}
        for key, label in labels:
            self.facts[key] = _FactCell(label)
            row.addWidget(self.facts[key], 1, Qt.AlignmentFlag.AlignTop)
        box.addLayout(row)

    def set(self, key: str, value: str) -> None:
        self.facts[key].value.setText(value)


class _Highlight(QWidget):
    """One thing an image offers: an accent bullet and a short line."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(0)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(7)
        # A glyph rather than a drawn dot: it shares the line's font, so it
        # sits on the first line whatever the text size.
        self.mark = QLabel("•")
        self.mark.setProperty("firmwareHighlightMark", True)
        row.addWidget(self.mark, 0, Qt.AlignmentFlag.AlignTop)
        self.text = QLabel()
        self.text.setProperty("firmwareHighlight", True)
        self.text.setProperty("i18nLiteral", True)
        self.text.setWordWrap(True)
        self.text.setMinimumWidth(0)
        # Beside a line that wraps, a short one keeps to its bullet.
        self.text.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        row.addWidget(self.text, 1)


class _SelectableCard(QFrame):
    """A card a click, Enter, Space or the controller's A button selects."""

    activated = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("profileCard", True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._selected = False

    def set_selected(self, selected: bool) -> None:
        if bool(selected) == self._selected:
            return
        self._selected = bool(selected)
        self.setProperty("selectedProfile", self._selected)
        _repolish(self)

    def gamepad_activate(self) -> None:
        if self.isEnabled():
            self.activated.emit()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.activated.emit()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.gamepad_activate()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().focusInEvent(event)
        # Tab and the controller move focus through a list taller than its
        # box; the list follows, so the focused card is never out of sight.
        area = _enclosing_scroll_area(self)
        if area is not None:
            area.ensureWidgetVisible(self, 0, 12)


class FirmwareCard(_SelectableCard):
    """One firmware image: what it is, and the four facts it is chosen by."""

    variant_changed = pyqtSignal(str)

    #: key, label: the columns every card shares, so a choice is made by
    #: reading down them.
    FACTS = (
        ("vram", "VRAM in the BIOS"),
        ("cores", "CPU cores"),
        ("logo", "Boot logo"),
        ("after", "After flashing"),
    )

    def __init__(self, family: FirmwareFamily, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.family = family
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 13)
        root.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(10)
        self.title = QLabel(family.title)
        self.title.setProperty("profileTitle", True)
        self.title.setProperty("i18nLiteral", True)
        self.title.setWordWrap(True)
        self.title.setMinimumWidth(0)
        head.addWidget(self.title, 1)
        self.status = QLabel()
        self.status.setProperty("fieldHint", True)
        self.status.setProperty("i18nLiteral", True)
        self.status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        head.addWidget(self.status, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(head)

        self.summary = QLabel()
        self.summary.setProperty("profileDescription", True)
        self.summary.setWordWrap(True)
        self.summary.setMinimumWidth(0)
        root.addWidget(self.summary)

        # What the image offers beyond the four facts. Two columns once the
        # facts fit on one row; the second starts where the third fact does.
        self.highlights = QWidget()
        self.highlights_grid = QGridLayout(self.highlights)
        self.highlights_grid.setContentsMargins(0, 2, 0, 0)
        self.highlights_grid.setHorizontalSpacing(18)
        self.highlights_grid.setVerticalSpacing(3)
        self.highlight_rows = [_Highlight() for _line in family.highlights]
        self._highlight_columns = 0
        self.highlights.setVisible(bool(self.highlight_rows))
        root.addWidget(self.highlights)

        self.facts_grid = QGridLayout()
        self.facts_grid.setContentsMargins(0, 6, 0, 0)
        self.facts_grid.setHorizontalSpacing(18)
        self.facts_grid.setVerticalSpacing(8)
        self.fact_labels: dict[str, HeadingLabel] = {}
        self.fact_values: dict[str, QLabel] = {}
        self._fact_columns = 0
        for key, label in self.FACTS:
            self.fact_labels[key] = _heading(label, "firmwareFactLabel")
            value = QLabel()
            value.setProperty("firmwareFactValue", True)
            value.setProperty("i18nLiteral", True)
            value.setWordWrap(True)
            value.setMinimumWidth(0)
            self.fact_values[key] = value
        self._place_facts(4)
        self._place_highlights(2)
        root.addLayout(self.facts_grid)

        self.variant_row = QWidget()
        variant = QHBoxLayout(self.variant_row)
        variant.setContentsMargins(0, 6, 0, 0)
        variant.setSpacing(10)
        self.variant_label = QLabel()
        self.variant_label.setProperty("fieldLabel", True)
        variant.addWidget(self.variant_label, 0)
        self.variant_combo = QComboBox()
        self.variant_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.variant_combo.setMinimumWidth(0)
        for image in family.images:
            self.variant_combo.addItem(tr(image.label), image.key)
        default = family.image().key
        self.variant_combo.setCurrentIndex(max(0, self.variant_combo.findData(default)))
        self.variant_combo.currentIndexChanged.connect(
            lambda _index: self.variant_changed.emit(str(self.variant_combo.currentData()))
        )
        variant.addWidget(self.variant_combo, 0)
        variant.addStretch(1)
        self.variant_row.setVisible(False)
        root.addWidget(self.variant_row)

        # Said once the image is chosen, not on every card: five warnings in
        # a list read as none.
        self.caution = _note()
        self.caution.setVisible(False)
        root.addWidget(self.caution)
        self.retranslate()

    @property
    def image_key(self) -> str:
        return str(self.variant_combo.currentData() or self.family.image().key)

    def set_selected(self, selected: bool) -> None:
        super().set_selected(selected)
        self.variant_row.setVisible(selected and self.family.has_variants)
        self.caution.setVisible(selected and bool(self.family.caution))

    def set_status(self, text: str, tone: str = "") -> None:
        self.status.setText(text)
        self.status.setProperty("firmwareNote", tone or None)
        _repolish(self.status)

    def _place_facts(self, columns: int) -> None:
        if columns == self._fact_columns:
            return
        self._fact_columns = columns
        for key, _label in self.FACTS:
            self.facts_grid.removeWidget(self.fact_labels[key])
            self.facts_grid.removeWidget(self.fact_values[key])
        for index, (key, _label) in enumerate(self.FACTS):
            row, column = divmod(index, columns)
            self.facts_grid.addWidget(self.fact_labels[key], row * 2, column)
            self.facts_grid.addWidget(self.fact_values[key], row * 2 + 1, column)
        for column in range(4):
            self.facts_grid.setColumnStretch(column, 1 if column < columns else 0)

    def _place_highlights(self, columns: int) -> None:
        if columns == self._highlight_columns:
            return
        self._highlight_columns = columns
        for row in self.highlight_rows:
            self.highlights_grid.removeWidget(row)
        for index, row in enumerate(self.highlight_rows):
            self.highlights_grid.addWidget(row, *divmod(index, columns), Qt.AlignmentFlag.AlignTop)
        for column in range(2):
            self.highlights_grid.setColumnStretch(column, 1 if column < columns else 0)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        wide = event.size().width() >= FACTS_ONE_ROW_WIDTH
        self._place_facts(4 if wide else 2)
        self._place_highlights(2 if wide else 1)

    def _set_fact(self, key: str, text: str, tone: str = "") -> None:
        value = self.fact_values[key]
        value.setText(text)
        value.setProperty("tone", tone or None)
        _repolish(value)

    def retranslate(self) -> None:
        family = self.family
        self.summary.setText(tr(family.summary))
        for row, line in zip(self.highlight_rows, family.highlights):
            row.text.setText(tr(line))
        self._set_fact("vram", tr("Yes") if family.vram_menu else tr("No"),
                       "" if family.vram_menu else "muted")
        self._set_fact(
            "cores",
            tr_format("{active} of {total}", active=family.cpu_cores, total=DIE_CORES),
            "" if family.cpu_cores == DIE_CORES else "muted",
        )
        if family.boot_logos:
            self._set_fact("logo", tr_format("{count} to choose from", count=family.boot_logos))
        else:
            self._set_fact("logo", tr("As shipped"), "muted")
        if family.tool.clears_settings:
            self._set_fact("after", tr("Nothing to do"))
        else:
            self._set_fact("after", tr("Clear CMOS"), "caution")
        if family.caution:
            self.caution.setText(tr(family.caution))
        if family.variant_title:
            self.variant_label.setText(tr(family.variant_title))
        for index, image in enumerate(family.images):
            self.variant_combo.setItemText(index, tr(image.label))


class UsbDriveCard(_SelectableCard):
    """One attached USB drive, and whether it can be used."""

    def __init__(self, drive: UsbDrive, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.drive = drive
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 10, 14, 11)
        root.setSpacing(12)
        glyph = QLabel()
        glyph.setPixmap(icon("fw_usb").pixmap(22, 22))
        glyph.setFixedSize(22, 22)
        root.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)
        copy = QVBoxLayout()
        copy.setSpacing(2)
        self.title = QLabel(drive.display_name)
        self.title.setProperty("profileTitle", True)
        self.title.setProperty("i18nLiteral", True)
        self.title.setWordWrap(True)
        self.title.setMinimumWidth(0)
        copy.addWidget(self.title)
        self.detail = QLabel()
        self.detail.setProperty("fieldHint", True)
        self.detail.setProperty("i18nLiteral", True)
        self.detail.setWordWrap(True)
        self.detail.setMinimumWidth(0)
        copy.addWidget(self.detail)
        self.note = _note()
        copy.addWidget(self.note)
        root.addLayout(copy, 1)
        self.setEnabled(drive.eligible)
        self.retranslate()

    def retranslate(self) -> None:
        drive = self.drive
        labels = ", ".join(drive.volume_labels) or tr("No volumes")
        self.detail.setText(f"{drive.path}  ·  {format_size(drive.size)}  ·  {labels}")
        blocker, warning = drive.blocker(), drive.warning()
        self.note.setProperty("firmwareNote", "danger" if blocker else "caution")
        self.note.setText(tr(blocker or warning))
        self.note.setVisible(bool(blocker or warning))
        _repolish(self.note)


class StepRow(QWidget):
    """One preparation step: a state mark, its name and what it is doing."""

    STATE_ICONS = {"pending": "fw_step_pending", "done": "fw_step_done", "failed": "fw_step_failed"}

    def __init__(self, key: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.key = key
        self.state = "pending"
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 3, 0, 3)
        row.setSpacing(10)
        self.mark = QLabel()
        self.mark.setFixedSize(16, 16)
        self.spinner = BusySpinner(14)
        row.addWidget(self.mark, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignVCenter)
        self.title = QLabel(tr(STEP_TITLES[key]))
        self.title.setWordWrap(True)
        self.title.setMinimumWidth(0)
        row.addWidget(self.title, 1)
        self.detail = QLabel()
        self.detail.setProperty("fieldHint", True)
        self.detail.setProperty("i18nLiteral", True)
        self.detail.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.detail.setMinimumWidth(0)
        self.detail.setMaximumWidth(240)
        row.addWidget(self.detail, 0)
        self.set_state("pending")

    def set_state(self, state: str, detail: str = "") -> None:
        self.state = state
        self.title.setProperty("firmwareStepTitle", state)
        _repolish(self.title)
        self.spinner.set_running(state == "active")
        self.mark.setVisible(state != "active")
        self.mark.setPixmap(icon(self.STATE_ICONS.get(state, "fw_step_pending")).pixmap(16, 16))
        metrics = self.detail.fontMetrics()
        self.detail.setText(metrics.elidedText(detail, Qt.TextElideMode.ElideMiddle, 230))
        self.detail.setToolTip(detail)

    def retranslate(self) -> None:
        self.title.setText(tr(STEP_TITLES[self.key]))


class _LogoPreview(QWidget):
    """The logo on the board's black screen, at the logo's own proportions.

    What it draws is the JPEG that goes into the firmware, decoded again, so
    the preview shows what the board will show, compression included.
    """

    #: Beside the picture's facts, the larger share of the width they share;
    #: the real size is in the tooltip and the facts.
    MAX_WIDTH = 440
    MIN_WIDTH = 200
    #: The board's screen is black whatever the theme; so is the placeholder's.
    PLACEHOLDER_INK = QColor(138, 143, 152)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._placeholder = ""
        self.setMinimumWidth(self.MIN_WIDTH)
        self.setMaximumWidth(self.MAX_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(self.MAX_WIDTH * LOGO_HEIGHT // LOGO_WIDTH)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        return QSize(self.MAX_WIDTH, self.MAX_WIDTH * LOGO_HEIGHT // LOGO_WIDTH)

    @property
    def showing_logo(self) -> bool:
        return self._pixmap is not None

    def set_logo(self, image: QImage | None, placeholder: str) -> None:
        self._pixmap = QPixmap.fromImage(image) if image is not None and not image.isNull() else None
        self._placeholder = placeholder
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        # The height follows the width, never the other way round, so this
        # settles on the first pass.
        height = max(1, event.size().width()) * LOGO_HEIGHT // LOGO_WIDTH
        if height != self.height():
            self.setFixedHeight(height)

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API name
        width = min(self.width(), self.height() * LOGO_WIDTH // LOGO_HEIGHT)
        height = width * LOGO_HEIGHT // LOGO_WIDTH
        frame = QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height)
        frame = frame.adjusted(0.5, 0.5, -0.5, -0.5)
        outline = QPainterPath()
        outline.addRoundedRect(frame, 8, 8)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillPath(outline, QColor(0, 0, 0))
        painter.save()
        painter.setClipPath(outline)
        if self._pixmap is not None:
            painter.drawPixmap(frame, self._pixmap, QRectF(self._pixmap.rect()))
        elif self._placeholder:
            painter.setPen(self.PLACEHOLDER_INK)
            painter.drawText(
                frame.adjusted(16, 0, -16, 0),
                int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
                self._placeholder,
            )
        painter.restore()
        painter.setPen(QPen(QColor(COLORS["border_soft"]), 1))
        painter.drawPath(outline)
        painter.end()


class _LogoSection(QWidget):
    """The logo's part of the side table, which sizes its preview by itself.

    The preview takes the larger share of the width, but never so much that
    the picture's facts beside it lose the room their longest line needs.
    """

    GAP = 20
    #: The preview's share of the width, and the least the facts keep.
    PREVIEW_SHARE = 0.58
    FACTS_WIDTH = 300

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.preview: _LogoPreview | None = None

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        if self.preview is not None:
            width = event.size().width() - self.GAP
            share = min(int(width * self.PREVIEW_SHARE), width - self.FACTS_WIDTH)
            self.preview.setMaximumWidth(max(_LogoPreview.MIN_WIDTH, min(_LogoPreview.MAX_WIDTH, share)))


class _FirmwareList(QScrollArea):
    """The images, in a box of their own height with its own scroll bar.

    It asks for a modest height and takes whatever its column gives it:
    beside the other column it runs the full height of the page, stacked
    above it it is capped so the drive and the button stay within reach.
    """

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        return QSize(super().sizeHint().width(), 380)


class FirmwarePage(QWidget):
    """Firmware (BIOS): prepare a USB drive that updates the board's BIOS."""

    def __init__(self, controller=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.setProperty("redesignedModule", True)
        self.store = FirmwareStore()
        self.watcher = UsbDriveWatcher(parent=self)
        self.watcher.drives_changed.connect(self._show_drives)
        self._background = BackgroundExecutor(self)
        self._board = BoardFirmware()
        self._udisks_ready: bool | None = None
        self._family_key = DEFAULT_FAMILY.key
        self._drive_name = ""
        self._job: UsbPreparationJob | None = None
        self._stacked: bool | None = None
        self._run_steps = tuple(step for step in STEPS if step != "logo")
        self._logo_picture: Picture | None = None
        self._logo_jpeg = b""
        self._logo_shown: QImage | None = None
        #: Source text of what went wrong with the picture, or "", and the
        #: file it went wrong with: a failed new file keeps the old picture.
        self._logo_error = ""
        self._logo_error_file = ""
        #: Why logos cannot be built here at all; None until first asked.
        self._logo_codec: str | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(self.scroll)
        content = QWidget()
        content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 12, 16, PAGE_BOTTOM)
        layout.setSpacing(12)
        self.workspace = QGridLayout()
        self.workspace.setContentsMargins(0, 0, 0, 0)
        self.workspace.setHorizontalSpacing(12)
        self.workspace.setVerticalSpacing(12)
        # Side by side, the workspace takes whatever height the window has,
        # so on a tall screen the firmware list shows more images instead of
        # the page ending in a band of nothing. Stacked, the list has a height
        # of its own and the spare height goes below the page instead, never
        # into the cards (see _reflow).
        self.content_layout = layout
        layout.addLayout(self.workspace, 1)
        layout.addStretch(0)

        self.firmware_panel = self._build_firmware_panel()
        self.safety_panel = self._build_safety_panel()
        # Owned by the page even while it is not laid out.
        self.safety_panel.setParent(content)
        self.safety_panel.setVisible(SAFETY_PANEL_SHOWN)
        self.side_panel = self._build_side_panel()
        self._reflow(1400)
        self._select_family(self._family_key)
        self._sync_board()

    # ------------------------------------------------------------ building

    def _build_firmware_panel(self) -> SectionCard:
        card = SectionCard("Firmware")
        card.drop_header()
        card.body.setSpacing(6)
        card.body.addWidget(_heading("Firmware"))
        card.body.addWidget(caption(
            "Every file comes from the project that publishes it and is checked "
            "against its SHA-256 before it reaches the USB."
        ))
        self.firmware_list = _FirmwareList()
        self.firmware_list.setWidgetResizable(True)
        self.firmware_list.setFrameShape(QFrame.Shape.NoFrame)
        self.firmware_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.firmware_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.firmware_list.setMinimumHeight(260)
        holder = QWidget()
        holder.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        rows = QVBoxLayout(holder)
        # The right margin keeps the cards clear of the scroll bar.
        rows.setContentsMargins(0, 4, 10, 4)
        rows.setSpacing(8)
        self.firmware_cards: dict[str, FirmwareCard] = {}
        self.category_headings: dict[str, HeadingLabel] = {}
        for origin, title in CATEGORIES:
            heading = _heading(title, "firmwareCategory")
            if self.category_headings:
                rows.addSpacing(8)
            rows.addWidget(heading)
            self.category_headings[origin] = heading
            for family in FIRMWARE_FAMILIES:
                if family.origin != origin:
                    continue
                firmware_card = FirmwareCard(family)
                firmware_card.activated.connect(lambda key=family.key: self._select_family(key))
                firmware_card.variant_changed.connect(lambda _key: self._sync_selection())
                self.firmware_cards[family.key] = firmware_card
                rows.addWidget(firmware_card)
        rows.addStretch(1)
        self.firmware_list.setWidget(holder)
        card.body.addWidget(self.firmware_list, 1)
        return card

    def _build_side_panel(self) -> SectionCard:
        """Everything done with the chosen image, top to bottom: the logo that
        can go into it, the board it is for, the drive it goes on and the
        button that puts it there."""
        card = SectionCard("Firmware (BIOS)")
        card.drop_header()
        card.body.setSpacing(0)

        # The sections sit at one rhythm; what a tall column has to spare is
        # shared out between them, never left as one gap, and the button
        # stays at the bottom, level with the end of the list.
        self.logo_panel = self._build_logo_section()
        card.body.addWidget(self.logo_panel)
        self._section_gap(card.body)
        card.body.addWidget(_hairline())
        self._section_gap(card.body)

        board = QWidget()
        board_box = QVBoxLayout(board)
        board_box.setContentsMargins(0, 0, 0, 0)
        board_box.setSpacing(6)
        self.board_facts = _FactStrip(
            "INSTALLED BIOS", (("version", "Version"), ("date", "Date"), ("board", "Board"))
        )
        board_box.addWidget(self.board_facts)
        self.board_note = _note(tr(
            "This computer is not a BC-250. The USB can still be prepared here "
            "and used on the board."
        ))
        self.board_note.hide()
        board_box.addWidget(self.board_note)
        card.body.addWidget(board)
        self._section_gap(card.body)

        self.usb_panel = QWidget()
        usb_box = QVBoxLayout(self.usb_panel)
        usb_box.setContentsMargins(0, 0, 0, 0)
        usb_box.setSpacing(8)
        usb_box.addWidget(_heading("USB drive"))
        self.usb_empty = QWidget()
        empty = QHBoxLayout(self.usb_empty)
        empty.setContentsMargins(0, 6, 0, 6)
        empty.setSpacing(9)
        self.usb_spinner = BusySpinner(14)
        empty.addWidget(self.usb_spinner, 0, Qt.AlignmentFlag.AlignVCenter)
        self.usb_empty_label = QLabel(tr("Looking for USB drives…"))
        self.usb_empty_label.setProperty("fieldHint", True)
        self.usb_empty_label.setWordWrap(True)
        empty.addWidget(self.usb_empty_label, 1)
        usb_box.addWidget(self.usb_empty)
        self.usb_list = QVBoxLayout()
        self.usb_list.setContentsMargins(0, 0, 0, 0)
        self.usb_list.setSpacing(8)
        usb_box.addLayout(self.usb_list)
        usb_box.addWidget(caption(
            "Plug in a USB drive of at least 1 GB and it shows up here by itself. "
            "Everything on it will be erased."
        ))
        self.usb_cards: dict[str, UsbDriveCard] = {}
        card.body.addWidget(self.usb_panel)
        self._section_gap(card.body)

        self.prepare_panel = QWidget()
        prepare_box = QVBoxLayout(self.prepare_panel)
        prepare_box.setContentsMargins(0, 0, 0, 0)
        prepare_box.setSpacing(10)
        self.plan_facts = _FactList(
            "Preparation",
            (("firmware", "Firmware"), ("drive", "USB drive"), ("download", "Download")),
        )
        prepare_box.addWidget(self.plan_facts)
        self.udisks_note = _note(
            tr(
                "Preparing a USB needs UDisks2, the service desktop disk tools "
                "use, and busctl. They did not answer on this system."
            ),
            "danger",
        )
        self.udisks_note.hide()
        prepare_box.addWidget(self.udisks_note)

        self.steps_host = QWidget()
        steps = QVBoxLayout(self.steps_host)
        steps.setContentsMargins(0, 2, 0, 2)
        steps.setSpacing(1)
        self.step_rows = {key: StepRow(key) for key in STEPS}
        for row in self.step_rows.values():
            steps.addWidget(row)
        steps.addSpacing(6)
        self.progress = QProgressBar()
        self.progress.setProperty("firmwareProgress", True)
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        steps.addWidget(self.progress)
        self.steps_host.hide()
        prepare_box.addWidget(self.steps_host)

        self.result = QFrame()
        self.result.setProperty("firmwareResult", "neutral")
        result = QVBoxLayout(self.result)
        result.setContentsMargins(12, 10, 12, 10)
        self.result_text = QLabel()
        self.result_text.setWordWrap(True)
        self.result_text.setProperty("i18nLiteral", True)
        result.addWidget(self.result_text)
        self.result.hide()
        prepare_box.addWidget(self.result)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.cancel_button = QPushButton(tr("Cancel"))
        self.cancel_button.setProperty("ghostButton", True)
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.clicked.connect(self._cancel)
        self.cancel_button.hide()
        actions.addWidget(self.cancel_button, 0)
        self.prepare_button = QPushButton(tr("Prepare USB"))
        self.prepare_button.setObjectName("PrimaryAction")
        self.prepare_button.setProperty("primaryAction", True)
        self.prepare_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prepare_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.prepare_button.clicked.connect(self._prepare)
        actions.addWidget(self.prepare_button, 1)
        prepare_box.addLayout(actions)
        card.body.addWidget(self.prepare_panel)
        return card

    @staticmethod
    def _section_gap(box: QVBoxLayout) -> None:
        """The space between two sections of the side table: at least
        SECTION_GAP, and an equal share of whatever the column has to spare."""
        box.addSpacing(SECTION_GAP)
        box.addStretch(1)

    def _build_safety_panel(self) -> SectionCard:
        """What to know before flashing, first in the column it applies to."""
        card = SectionCard("Before you start")
        card.drop_header()
        card.body.setSpacing(8)
        card.body.addWidget(_heading("Before you start"))
        # The one thing that makes a finished flash look like a dead board,
        # in a box of its own so it is read before the rest.
        callout = QFrame()
        callout.setProperty("firmwareCallout", "caution")
        callout_box = QVBoxLayout(callout)
        callout_box.setContentsMargins(12, 9, 12, 10)
        self.after_flash_note = _note(tr(AFTER_FLASH_WARNING))
        callout_box.addWidget(self.after_flash_note)
        card.body.addWidget(callout)
        self.safety_notes: list[_Highlight] = []
        for text in (
            "Keep the power steady. A power cut during the flash is the one thing "
            "that can leave the board unable to start.",
            "If something goes wrong, the same USB puts your previous BIOS back: "
            "type restore.",
            "A board that no longer starts at all can still be recovered with an "
            "SPI programmer such as a CH347.",
        ):
            note = _Highlight()
            note.text.setProperty("firmwareHighlight", "muted")
            note.text.setProperty("i18nLiteral", False)
            note.text.setText(tr(text))
            self.safety_notes.append(note)
            card.body.addWidget(note)
        recovery = QPushButton(tr("BIOS recovery guide"))
        recovery.setProperty("linkButton", True)
        recovery.setProperty("flushLeft", True)
        recovery.setIcon(icon("external_gray"))
        recovery.setCursor(Qt.CursorShape.PointingHandCursor)
        recovery.clicked.connect(lambda: open_external_url(RECOVERY_GUIDE))
        card.body.addWidget(recovery, 0, Qt.AlignmentFlag.AlignLeft)
        return card

    def _build_logo_section(self) -> QWidget:
        """The custom boot logo: the picture as the board will show it and
        what it is, side by side, with what to know underneath."""
        section = _LogoSection()
        box = QVBoxLayout(section)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)
        box.addWidget(_heading("Custom boot logo"))
        box.addWidget(caption(
            "Put your own picture on the screen the board shows while it starts. It "
            "goes into the chosen firmware when the USB is prepared, and nothing "
            "else in that firmware changes."
        ))

        self.logo_picture = QWidget()
        picture = QHBoxLayout(self.logo_picture)
        picture.setContentsMargins(0, 6, 0, 0)
        picture.setSpacing(_LogoSection.GAP)
        self.logo_preview = _LogoPreview()
        section.preview = self.logo_preview
        self.logo_preview.setToolTip(tr(
            "Black is the board's own screen. The picture is drawn at 672 × 378 "
            "pixels, in the middle."
        ))
        picture.addWidget(self.logo_preview, 0, Qt.AlignmentFlag.AlignTop)
        beside = QVBoxLayout()
        beside.setContentsMargins(0, 0, 0, 0)
        beside.setSpacing(10)
        self.logo_facts = _FactList(
            "Picture",
            (
                ("file", "File name"),
                ("source", "Original size"),
                ("stored", "In the firmware"),
            ),
        )
        beside.addWidget(self.logo_facts)
        beside.addStretch(1)
        picture.addLayout(beside, 1)
        box.addWidget(self.logo_picture)

        # What changes the picture sits with the facts it changes.
        scale = QHBoxLayout()
        scale.setSpacing(12)
        scale_label = QLabel(tr("Size"))
        scale_label.setProperty("fieldLabel", True)
        scale.addWidget(scale_label, 0)
        self.logo_scale = QSlider(Qt.Orientation.Horizontal)
        self.logo_scale.setProperty("logoScale", True)
        self.logo_scale.setRange(*SIZE_RANGE)
        self.logo_scale.setSingleStep(5)
        self.logo_scale.setPageStep(10)
        self.logo_scale.setValue(SIZE_RANGE[1])
        self.logo_scale.valueChanged.connect(self._logo_scale_moved)
        scale.addWidget(self.logo_scale, 1)
        self.logo_scale_value = QLabel(f"{SIZE_RANGE[1]} %")
        self.logo_scale_value.setProperty("fieldHint", True)
        self.logo_scale_value.setProperty("i18nLiteral", True)
        self.logo_scale_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.logo_scale_value.setMinimumWidth(44)
        scale.addWidget(self.logo_scale_value, 0)
        beside.addLayout(scale)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.logo_choose = QPushButton(tr("Choose picture…"))
        self.logo_choose.setProperty("ghostButton", True)
        self.logo_choose.setIcon(icon("fw_logo"))
        self.logo_choose.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logo_choose.clicked.connect(self._choose_logo)
        actions.addWidget(self.logo_choose, 0)
        self.logo_remove = QPushButton(tr("Remove"))
        self.logo_remove.setProperty("ghostButton", True)
        self.logo_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logo_remove.clicked.connect(self._remove_logo)
        actions.addWidget(self.logo_remove, 0)
        actions.addStretch(1)
        beside.addLayout(actions)

        # Under both: what went wrong with a picture, and what to know first.
        self.logo_controls = QWidget()
        controls = QVBoxLayout(self.logo_controls)
        controls.setContentsMargins(0, 4, 0, 0)
        controls.setSpacing(10)
        self.logo_note = _note()
        self.logo_note.hide()
        controls.addWidget(self.logo_note)
        controls.addWidget(caption(
            "Before the USB is written, the new firmware is read back and compared "
            "with the published one: only the logo may differ. Custom logos have been "
            "tested on real boards with P2.00, P3.00, P5.00 and MeiMeiDXE v3. As with "
            "any BIOS change, an SPI programmer at hand is the way back."
        ))
        box.addWidget(self.logo_controls)

        self._logo_settle = QTimer(self)
        self._logo_settle.setSingleShot(True)
        self._logo_settle.setInterval(LOGO_SETTLE_MS)
        self._logo_settle.timeout.connect(self._render_logo)
        return section

    # ------------------------------------------------------------- layout

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._reflow(event.size().width())

    def _reflow(self, width: int) -> None:
        stacked = width < STACK_WIDTH
        if stacked == self._stacked:
            return
        self._stacked = stacked
        for panel in (self.firmware_panel, self.safety_panel, self.side_panel):
            self.workspace.removeWidget(panel)
        # The right column, top to bottom: what to know first, when shown,
        # then the table of what is done with the choice.
        column = [self.safety_panel, self.side_panel] if SAFETY_PANEL_SHOWN else [self.side_panel]
        for row in range(3):
            self.workspace.setRowStretch(row, 0)
        if stacked:
            # In reading order: what goes on the USB, then the rest.
            for row, panel in enumerate([self.firmware_panel, *column]):
                self.workspace.addWidget(panel, row, 0)
            self.workspace.setColumnStretch(0, 1)
            self.workspace.setColumnStretch(1, 0)
            self.content_layout.setContentsMargins(16, 12, 16, PAGE_BOTTOM)
            self.content_layout.setStretch(0, 0)
            self.content_layout.setStretch(1, 1)
            self.firmware_list.setMaximumHeight(STACKED_LIST_HEIGHT)
        else:
            # The list runs the full height of the page, beside the right
            # column. No alignment: it takes the height of every row, which
            # that column decides, and the spare height of a tall window goes
            # to the side table, spread between its sections. Both end just
            # above the sidebar's Firmware button.
            self.workspace.addWidget(self.firmware_panel, 0, 0, len(column), 1)
            for row, panel in enumerate(column):
                self.workspace.addWidget(panel, row, 1)
            self.workspace.setRowStretch(len(column) - 1, 1)
            self.workspace.setColumnStretch(0, CONTROLS_STRETCH)
            self.workspace.setColumnStretch(1, SIDE_STRETCH)
            self.content_layout.setContentsMargins(16, 12, 16, FOOT_CLEARANCE)
            self.content_layout.setStretch(0, 1)
            self.content_layout.setStretch(1, 0)
            self.firmware_list.setMaximumHeight(16777215)

    # ------------------------------------------------------------ activity

    def set_updates_active(self, active: bool) -> None:
        """Watch for USB drives only while the page is on screen."""
        if active:
            self.watcher.start()
            self._refresh_board()
            self._refresh_cache_status()
            if self._udisks_ready is None:
                self._background.start("udisks-available", udisks.available, self._udisks_answer)
        elif not self.busy:
            self.watcher.stop()

    @property
    def busy(self) -> bool:
        # From the moment a preparation is set up until it has finished, not
        # only while its thread runs: the controls are disabled right before
        # the thread starts, and they must stay disabled.
        return self._job is not None

    def close_blocker(self) -> str:
        """Why the window must not close now, or ""."""
        if self._job is not None and self._job.isRunning() and not self._job.can_cancel:
            return (
                "A USB drive is being written. Closing now would leave it unusable. "
                "Wait until it is ready; it takes about a minute."
            )
        return ""

    def stop_for_close(self) -> None:
        """Cancel a preparation that has not touched the drive yet."""
        if self._job is not None and self._job.isRunning():
            self._job.cancel()
            self._job.wait(5000)

    def _udisks_answer(self, ready: object) -> None:
        self._udisks_ready = bool(ready)
        self._sync_selection()

    def _refresh_board(self) -> None:
        self._board = read_board_firmware()
        self._sync_board()

    def _sync_board(self) -> None:
        board = self._board
        self.board_facts.set("version", board.version or "--")
        self.board_facts.set("date", board.date or "--")
        self.board_facts.set("board", board.board or "--")
        self.board_facts.facts["board"].value.setToolTip(board.vendor)
        # Only once DMI has been read: before that nothing is known either way.
        self.board_note.setVisible(bool(board.board or board.version) and not board.is_bc250)

    def _refresh_cache_status(self) -> None:
        for firmware_card in self.firmware_cards.values():
            family = firmware_card.family
            image = family.image(firmware_card.image_key)
            firmware_card.set_status(*self._cache_status(family, image))

    def _missing_bytes(self, family: FirmwareFamily, image: FirmwareImage) -> int:
        pending: dict[str, int] = {}
        for source in sources_for(family, image):
            if not self.store.is_cached(source):
                archive = archives_of(source)
                pending[archive.sha256] = archive.size
        return sum(pending.values())

    def _cache_status(self, family: FirmwareFamily, image: FirmwareImage) -> tuple[str, str]:
        """What the card says about its files, and in which tone."""
        if not self.store.can_unpack(image.rom):
            return tr("Needs 7-Zip or bsdtar to unpack."), "caution"
        missing = self._missing_bytes(family, image)
        if not missing:
            return tr("Already downloaded"), ""
        return tr_format("{size} to download.", size=_megabytes(missing)), ""

    # ----------------------------------------------------------- selection

    def selected_family(self) -> FirmwareFamily:
        return FAMILIES_BY_KEY[self._family_key]

    def selected_image(self) -> FirmwareImage:
        return self.selected_family().image(self.firmware_cards[self._family_key].image_key)

    def selected_drive(self) -> UsbDrive | None:
        for drive in self.watcher.drives:
            if drive.name == self._drive_name and drive.eligible:
                return drive
        return None

    def _select_family(self, key: str) -> None:
        if self.busy or key not in self.firmware_cards:
            return
        self._family_key = key
        for family_key, firmware_card in self.firmware_cards.items():
            firmware_card.set_selected(family_key == key)
        self._sync_selection()

    def _select_drive(self, name: str) -> None:
        if self.busy:
            return
        self._drive_name = name
        for drive_name, drive_card in self.usb_cards.items():
            drive_card.set_selected(drive_name == name)
        self._sync_selection()

    def _show_drives(self, drives: object) -> None:
        drives = tuple(drives or ())
        wanted = {drive.name: drive for drive in drives}
        for name in list(self.usb_cards):
            drive_card = self.usb_cards[name]
            if name not in wanted or wanted[name] != drive_card.drive:
                self.usb_list.removeWidget(drive_card)
                drive_card.deleteLater()
                del self.usb_cards[name]
        for index, drive in enumerate(drives):
            if drive.name in self.usb_cards:
                continue
            drive_card = UsbDriveCard(drive)
            drive_card.activated.connect(lambda name=drive.name: self._select_drive(name))
            self.usb_cards[drive.name] = drive_card
            self.usb_list.insertWidget(index, drive_card)
        eligible = [drive for drive in drives if drive.eligible]
        if self._drive_name not in {drive.name for drive in eligible}:
            # The chosen stick left, or none was chosen: one eligible stick is
            # an obvious choice; two or more are the user's to make.
            self._drive_name = eligible[0].name if len(eligible) == 1 else ""
        for name, drive_card in self.usb_cards.items():
            drive_card.set_selected(name == self._drive_name)
        self.usb_empty.setVisible(not drives)
        self.usb_spinner.set_running(not drives)
        self.usb_empty_label.setText(tr(
            "Waiting for a USB drive…" if self.watcher.known else "Looking for USB drives…"
        ))
        self._sync_selection()

    def _image_title(self, family: FirmwareFamily, image: FirmwareImage) -> str:
        return f"{family.title} — {tr(image.label)}" if family.has_variants else family.title

    def _plan_title(self, family: FirmwareFamily, image: FirmwareImage) -> str:
        if self._logo_for_plan() is not None:
            return tr_format("{firmware}, with your boot logo", firmware=family.title)
        return self._image_title(family, image)

    def _sync_selection(self) -> None:
        family, image = self.selected_family(), self.selected_image()
        drive = self.selected_drive()
        self.firmware_cards[family.key].set_status(*self._cache_status(family, image))
        self.plan_facts.set("firmware", self._plan_title(family, image))
        self.plan_facts.set(
            "drive",
            f"{drive.display_name} · {format_size(drive.size)}" if drive is not None
            else tr("Choose a USB drive"),
        )
        missing = self._missing_bytes(family, image)
        self.plan_facts.set(
            "download", _megabytes(missing) if missing else tr("Already downloaded")
        )
        self.udisks_note.setVisible(self._udisks_ready is False)
        ready = (
            drive is not None
            and self._udisks_ready is not False
            and self.store.can_unpack(image.rom)
            and not self.busy
        )
        self.prepare_button.setEnabled(ready)
        self._sync_logo()

    # ----------------------------------------------------------- boot logo

    def _logo_unavailable(self, family: FirmwareFamily) -> str:
        """Why no logo can go into ``family`` now, or ""."""
        if self._logo_codec is None:
            self._logo_codec = lzma1.available()
        if self._logo_codec:
            return LOGO_CODEC_MISSING
        if not family.logo_replaceable:
            return LOGO_NOT_THIS_FIRMWARE
        return ""

    def _logo_for_plan(self) -> bytes | None:
        """The JPEG the next USB gets as its logo, or None for the published image."""
        if self._logo_jpeg and not self._logo_unavailable(self.selected_family()):
            return self._logo_jpeg
        return None

    def _choose_logo(self) -> None:
        if self.busy or self._background.is_running("boot-logo"):
            return
        path, _pattern = QFileDialog.getOpenFileName(
            self,
            tr("Choose a boot logo"),
            str(Path.home()),
            f"{tr('Pictures')} ({readable_patterns()})",
        )
        if not path:
            return
        self._logo_error, self._logo_error_file = "", Path(path).name
        self._background.start(
            "boot-logo",
            lambda: load_picture(path),
            self._logo_loaded,
            self._logo_failed,
            self._sync_logo,
        )
        self._sync_logo()

    def _logo_loaded(self, picture: object) -> None:
        if not isinstance(picture, Picture):
            self._logo_failed("The file is not a picture this system can read.")
            return
        self._logo_picture = picture
        self._render_logo()

    def _logo_failed(self, message: str) -> None:
        self._logo_error = message or "The file is not a picture this system can read."
        self._sync_logo()

    def _logo_scale_moved(self, value: int) -> None:
        self.logo_scale_value.setText(f"{value} %")
        if self._logo_picture is not None:
            self._logo_settle.start()

    def _render_logo(self) -> None:
        picture = self._logo_picture
        if picture is None:
            return
        try:
            jpeg = encode_logo(render_logo(picture, self.logo_scale.value()))
        except LogoImageError as error:
            self._logo_jpeg, self._logo_shown, self._logo_error = b"", None, str(error)
            self._logo_error_file = picture.name
        else:
            self._logo_jpeg, self._logo_error = jpeg, ""
            self._logo_shown = QImage.fromData(jpeg, "JPEG")
        self._sync_selection()

    def _remove_logo(self) -> None:
        if self.busy:
            return
        self._logo_settle.stop()
        self._logo_picture, self._logo_jpeg, self._logo_shown, self._logo_error = None, b"", None, ""
        self._logo_error_file = ""
        self.logo_scale.setValue(SIZE_RANGE[1])
        self._sync_selection()

    def _sync_logo(self) -> None:
        family = self.selected_family()
        picture = self._logo_picture
        unavailable = self._logo_unavailable(family)
        self.logo_facts.set("file", picture.name if picture is not None else "--")
        self.logo_facts.set(
            "source", f"{picture.width} × {picture.height} px" if picture is not None else "--"
        )
        self.logo_facts.set(
            "stored",
            f"{LOGO_WIDTH} × {LOGO_HEIGHT} px · JPEG · {_kilobytes(len(self._logo_jpeg))}"
            if self._logo_jpeg else "--",
        )
        if self._logo_error:
            message, tone = tr(self._logo_error), "danger"
            if self._logo_error_file:
                message = f"{self._logo_error_file} — {message}"
        elif unavailable and (picture is not None or unavailable == LOGO_CODEC_MISSING):
            message, tone = tr(unavailable), "caution"
        else:
            message, tone = "", "caution"
        self.logo_note.setText(message)
        self.logo_note.setProperty("firmwareNote", tone)
        _repolish(self.logo_note)
        self.logo_note.setVisible(bool(message))
        self.logo_preview.set_logo(self._logo_shown, tr("Your picture shows here"))
        loading = self._background.is_running("boot-logo")
        self.logo_choose.setEnabled(not self.busy and not loading and self._logo_codec == "")
        self.logo_remove.setEnabled(not self.busy and not loading and picture is not None)
        self.logo_scale.setEnabled(not self.busy and not loading and picture is not None)

    # ------------------------------------------------------------- prepare

    def _prepare(self) -> None:
        drive = self.selected_drive()
        if drive is None or self.busy:
            return
        family, image = self.selected_family(), self.selected_image()
        missing = self._missing_bytes(family, image)
        if self._logo_settle.isActive():
            # The slider moved a moment ago: the USB gets the size it shows.
            self._logo_settle.stop()
            self._render_logo()
        logo = self._logo_for_plan()
        summary = [
            ("USB drive", f"{drive.display_name} · {format_size(drive.size)}"),
            ("Device", drive.path),
            ("Contains", ", ".join(drive.volume_labels) or tr("No volumes")),
            ("Firmware", self._plan_title(family, image)),
            (
                "Download",
                tr_format("{size}, checked by SHA-256", size=_megabytes(missing))
                if missing
                else tr("Already downloaded"),
            ),
        ]
        if logo is not None and self._logo_picture is not None:
            summary.append(("Boot logo", self._logo_picture.name))
        dialog = ConfirmDialog(
            "Erase this USB drive?",
            "Everything on it will be erased and replaced by the BIOS update kit. "
            "This cannot be undone.",
            summary=tuple(summary),
            notice="" if family.tool.clears_settings else AFTER_FLASH_WARNING,
            confirm_text="Erase and prepare",
            eyebrow="ERASE USB DRIVE",
            tone="red",
            parent=self,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        plan = plan_kit(family, image, prepared=f"{stamp}, BC250 Control Center", logo=logo)
        self._run_steps = steps_for(plan)
        preparation = UsbPreparation(self.store, udisks.UDisksClient())
        self._job = UsbPreparationJob(preparation, plan, drive, self)
        self._job.progressed.connect(self._on_progress)
        self._job.succeeded.connect(self._on_success)
        self._job.failed.connect(self._on_failure)
        self._job.stopped.connect(self._on_stopped)
        self._job.finished.connect(self._on_finished)
        for key, row in self.step_rows.items():
            row.set_state("pending")
            row.setVisible(key in self._run_steps)
        self.progress.setValue(0)
        self.steps_host.show()
        self.result.hide()
        self.cancel_button.setEnabled(True)
        self.cancel_button.show()
        self._set_controls_enabled(False)
        self._job.start()

    def _set_controls_enabled(self, enabled: bool) -> None:
        for firmware_card in self.firmware_cards.values():
            firmware_card.setEnabled(enabled)
        for drive_card in self.usb_cards.values():
            drive_card.setEnabled(enabled and drive_card.drive.eligible)
        self._sync_selection()

    def _cancel(self) -> None:
        if self._job is not None and self._job.can_cancel:
            self._job.cancel()
            self.cancel_button.setEnabled(False)

    def _on_progress(self, step: str, fraction: float, detail: str) -> None:
        steps = self._run_steps
        if step not in steps:
            return
        index = steps.index(step)
        for position, key in enumerate(steps):
            row = self.step_rows[key]
            if position < index and row.state != "done":
                row.set_state("done")
        self.step_rows[step].set_state("done" if fraction >= 1.0 else "active", detail)
        done = sum(STEP_WEIGHTS[key] for key in steps[:index])
        total = sum(STEP_WEIGHTS[key] for key in steps)
        overall = (done + STEP_WEIGHTS[step] * max(0.0, min(1.0, fraction))) / total
        self.progress.setValue(int(overall * 1000))
        # Once the drive is being changed there is no clean way back.
        if self._job is not None and not self._job.can_cancel:
            self.cancel_button.setEnabled(False)

    def _show_result(self, tone: str, text: str) -> None:
        self.result.setProperty("firmwareResult", tone)
        _repolish(self.result)
        self.result_text.setText(text)
        self.result.show()

    def _on_success(self, report: object) -> None:
        for key, row in self.step_rows.items():
            if key in self._run_steps:
                row.set_state("done")
        self.progress.setValue(1000)
        ejected = bool(getattr(report, "ejected", False))
        lines = [tr(
            "The USB is ready and ejected. Switch the BC-250 off, unplug its "
            "drives, start it from this USB and type flash."
            if ejected
            else "The USB is ready and unmounted. Switch the BC-250 off, unplug "
            "its drives, start it from this USB and type flash."
        )]
        if not self.selected_family().tool.clears_settings:
            lines.append(tr(AFTER_FLASH_WARNING))
        self._show_result("success", "\n".join(lines))
        self._refresh_cache_status()
        # The dashboard names the installed BIOS. DMI reports the same
        # "P3.00" for three images; which one this USB carried, and the
        # version the board reported before it, is what tells them apart.
        family = self.selected_family()
        try:
            record_prepared_kit(family.key, family.version, self._board.version)
        except OSError:
            logger.debug("Could not note the prepared firmware kit", exc_info=True)

    def _on_failure(self, step: str, message: str) -> None:
        if step in self.step_rows:
            self.step_rows[step].set_state("failed")
        diagnosis = diagnose_error(message, context="firmware usb")
        lines = [tr(diagnosis.summary)]
        if step in {"erase", "format", "copy", "verify"}:
            lines.append(tr(
                "The USB was erased but is not a working kit. Prepare it again, or "
                "format it to use it for something else."
            ))
        lines.append(tr(diagnosis.action))
        lines.append(f"{tr('Technical detail')}: {message}  [{diagnosis.code}]")
        self._show_result("danger", "\n".join(lines))
        self._refresh_cache_status()

    def _on_stopped(self) -> None:
        for row in self.step_rows.values():
            if row.state == "active":
                row.set_state("pending")
        self._show_result("neutral", tr("Cancelled. The USB drive was not touched."))
        self._refresh_cache_status()

    def _on_finished(self) -> None:
        self.cancel_button.hide()
        self._job = None
        self._set_controls_enabled(True)
        # The stick was just rewritten or ejected: read the drives again.
        self.watcher.refresh()
        if not self.isVisible():
            self.watcher.stop()

    # -------------------------------------------------------- translation

    def retranslate_dynamic_copy(self) -> None:
        for firmware_card in self.firmware_cards.values():
            firmware_card.retranslate()
        for drive_card in self.usb_cards.values():
            drive_card.retranslate()
        for row in self.step_rows.values():
            row.retranslate()
        self._sync_board()
        self._refresh_cache_status()
        self._sync_selection()


def confirm_close_while_writing(parent: QWidget, message: str) -> None:
    """Tell the user why the window stays open."""
    QMessageBox.information(parent, tr("Firmware (BIOS)"), tr(message))
