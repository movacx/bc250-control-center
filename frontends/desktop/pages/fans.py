"""Fans: every header on the board, what it follows, and its editor.

Rebuilt from scratch (docs/FAN_PAGE_REDESIGN.md) in the language of the
Sensors, Processes and Black Box pages: one panel, underlined text tabs, a
dense table with small uppercase headings and right-aligned figures, flat text
buttons, a muted footer. No icon badges, no eyebrow kickers, no cards inside
cards.

Every change goes through ``FanChannelsService`` (saved config) and, when the
root service is on, ``_sync_system_fan_policy`` (root policy). The page writes a
PWM register itself only for an immediate Fixed or Firmware change while the
root service is off, through the same verified pkexec path as before.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QBoxLayout,
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLayout,
    QLineEdit,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from bc250cc.application.fan import board_view
from bc250cc.application.fan.calibration import CalibrationResult, calibrate
from bc250cc.application.fan.channels import ChannelBoard, FanChannelsService
from bc250cc.domain.fan import engine
from bc250cc.domain.fan.channels import (
    BUILTIN_MODE_NAMES,
    LABEL_MAX_LENGTH,
    MODE_NAME_MAX_LENGTH,
)
from bc250cc.domain.fan.headers import BC250_FAN_HEADERS
from bc250cc.domain.fan.profile_exchange import (
    MAX_DOCUMENT_BYTES,
    channel_profiles_document,
    decky_fan_profiles,
    decky_fan_raised,
    imported_profile_updates,
    parse_channel_profiles_document,
)
from bc250cc.infrastructure.system_fan_control import (
    build_system_fan_policy,
    policy_digest,
    policy_overview,
    system_fan_control_owns_fan,
)

from ..components.async_tools import AsyncRefresh, BackgroundExecutor
from ..components.buttons import WrappingButton as QPushButton
from ..components.dialogs import enable_adaptive_dialog
from ..components.page_widgets import ConfirmDialog, SectionCard
from ..components.responsive import configure_responsive_scroll_area
from ..components.toast import show_toast
from ..components.toggle_switch import ToggleSwitch
from ..components.wheel_guard import GuardedComboBox
from ..components.widgets import InfoDialog
from ..core.decky_export_feedback import (
    export_and_check_plugin,
    export_message,
    export_tone,
    fan_export_notes,
)
from ..core.state import state_cache_for
from ..i18n import shipped_name, tr, tr_format
from ..theme import COLORS, scale_stylesheet
from .fans_helpers import (  # noqa: F401  (re-exported: other modules and tests import them from here)
    _dict,
    _finite_number,
    _integer,
    _percent_to_pwm,
    _pwm_to_percent,
)
from .fans_widgets import (  # noqa: F401  (re-exported: other modules and tests import them from here)
    DEFAULT_FAN_PROFILES,
    FanCurvePlot,
    FanModeStack,
    FanTask,
    PwmPathsDialog,
    load_fan_profiles,
    save_fan_profile,
)

#: The five fan signals of a BC-250 (J4003 F1..F5 / CPU_FAN1) are always
#: listed: 0 RPM does not prove a header is empty (a stopped fan, a pump with
#: no tach wire). Other NCT channels show only once they are used.
BOARD_CHANNELS = board_view.BOARD_CHANNELS
#: Kept for callers of the previous page.
VISIBLE_PWM_ORDER = (2, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)
#: exec() result of a ConfirmDialog's secondary button (fixed at import, so a
#: test double of the dialog does not need to carry it).
DIALOG_SECONDARY = ConfirmDialog.SECONDARY
#: Below this duty a manual speed asks before it is written.
LOW_DUTY_CONFIRM_PERCENT = 30
#: Every form in the editor shares this label column, so its rows line up.
LABEL_COLUMN_WIDTH = 92
#: Under this page width the header rows break in two and the table keeps
#: only the columns that say what each fan does.
NARROW_BREAKPOINT = 700
#: Under this page width the editor goes below the table.
STACK_BREAKPOINT = 1060

MODE_LABELS = (("firmware", "Firmware"), ("fixed", "Fixed"), ("curve", "Curve"), ("mix", "Mix"))
ROLE_LABELS = (("fan", "Fan"), ("pump", "Pump"))
SOURCE_LABELS = (
    ("hottest", "Hottest chip"), ("gpu", "GPU"), ("cpu", "CPU"), ("vrm", "VRM"), ("board", "Board"),
)
DEFAULT_CURVE = [[40, 30], [60, 50], [72, 75], [82, 100]]

COLUMNS = (
    # (heading, right-aligned)
    ("Fan", False),
    ("BIOS", True),
    ("Mode", False),
    ("Follows", False),
    ("°C", True),
    ("PWM %", True),
    ("RPM", True),
    ("State", False),
)
CHANNEL, BIOS, MODE, FOLLOWS, TEMPERATURE, DUTY, RPM, STATE = range(len(COLUMNS))


def fans_stylesheet() -> str:
    c = COLORS
    return scale_stylesheet(f"""
QWidget[fansPage='true'] QSplitter#fanSplitter::handle {{ background: transparent; }}
QWidget[fansPage='true'] QScrollArea#fanEditorScroll {{ background: transparent; border: none; }}
QWidget[fansPage='true'] QScrollArea#fanEditorScroll > QWidget > QWidget {{ background: transparent; }}
QWidget[fansPage='true'] QPushButton[fanButton='secondary'],
QWidget[fansPage='true'] QPushButton[fanButton='primary'],
QWidget[fansPage='true'] QPushButton[fanButton='danger'] {{
    background: transparent; color: {c['text']}; border: 1px solid {c['border']};
    border-radius: 8px; min-height: 0px; padding: 6px 14px; font-size: 11px; font-weight: 650;
}}
QWidget[fansPage='true'] QPushButton[fanButton='secondary']:hover {{
    background: {c['control_hover']}; border-color: {c['border_strong']};
}}
QWidget[fansPage='true'] QPushButton[fanButton='primary'] {{
    color: {c['blue']}; border-color: {c['blue_border']};
}}
QWidget[fansPage='true'] QPushButton[fanButton='primary']:hover {{ background: {c['blue_soft']}; }}
QWidget[fansPage='true'] QPushButton[fanButton='danger'] {{ color: {c['red']}; border-color: {c['red_border']}; }}
QWidget[fansPage='true'] QPushButton[fanButton='danger']:hover {{ background: {c['red_soft']}; }}
QWidget[fansPage='true'] QPushButton[fanButton]:focus {{ border-color: {c['blue']}; }}
QWidget[fansPage='true'] QPushButton[fanButton]:checked {{
    background: {c['blue_soft']}; border-color: {c['blue_border']};
}}
QWidget[fansPage='true'] QPushButton[fanButton]:disabled {{
    color: {c['disabled_text']}; border-color: {c['border_soft']}; background: transparent;
}}
QWidget[fansPage='true'] QPushButton[fanButton]::menu-indicator {{ width: 0px; }}
QWidget[fansPage='true'] QTableView#fanTable {{
    background: {c['panel']}; alternate-background-color: {c['panel_alt']};
    border: 1px solid {c['border_soft']}; border-radius: 8px;
    font-size: 11px; color: {c['text']}; gridline-color: transparent;
    selection-background-color: {c['blue_soft']}; selection-color: {c['text']};
    outline: 0;
}}
QWidget[fansPage='true'] QTableView#fanTable::item {{ padding: 0px 8px; border: none; }}
QWidget[fansPage='true'] QTableView#fanTable QHeaderView::section {{
    background: {c['panel_alt']}; color: {c['muted']}; font-size: 9px; font-weight: 820;
    border: none; border-bottom: 1px solid {c['border']}; padding: 6px 8px;
}}
QWidget[fansPage='true'] QFrame[fanEditor='true'] {{
    background: {c['panel_alt']}; border: 1px solid {c['border_soft']}; border-radius: 8px;
}}
QWidget[fansPage='true'] QLabel[fanEditorTitle='true'] {{
    color: {c['text']}; font-size: 14px; font-weight: 800;
}}
QWidget[fansPage='true'] QLabel[fanMuted='true'] {{ color: {c['muted']}; font-size: 10px; }}
QWidget[fansPage='true'] QLabel[fanFieldLabel='true'] {{ color: {c['muted']}; font-size: 11px; font-weight: 620; }}
QWidget[fansPage='true'] QLabel[fanFieldValue='true'] {{ color: {c['text']}; font-size: 11px; font-weight: 700; }}
QWidget[fansPage='true'] QLabel[fanSection='true'] {{
    color: {c['muted']}; font-size: 9px; font-weight: 820; letter-spacing: 0.6px;
}}
QWidget[fansPage='true'] QFrame[fanRule='true'] {{
    background: {c['border_soft']}; border: none; min-height: 1px; max-height: 1px;
}}
QWidget[fansPage='true'] QLabel[fanFooter='true'] {{ color: {c['subtle']}; font-size: 9px; font-weight: 630; }}
QWidget[fansPage='true'] QLabel[fanStatus='true'] {{ color: {c['muted']}; font-size: 11px; font-weight: 600; }}
QWidget[fansPage='true'] QLabel[fanStatus='true'][tone='green'] {{ color: {c['green']}; }}
QWidget[fansPage='true'] QLabel[fanStatus='true'][tone='orange'] {{ color: {c['orange']}; }}
QWidget[fansPage='true'] QLabel[fanStatus='true'][tone='red'] {{ color: {c['red']}; }}
QWidget[fansPage='true'] QLabel[fanStatus='true'][tone='blue'] {{ color: {c['blue']}; }}
QWidget[fansPage='true'] QLabel[fanSwitchLabel='true'] {{ color: {c['text']}; font-size: 11px; font-weight: 650; }}
QWidget[fansPage='true'] QLineEdit[fanField='true'],
QWidget[fansPage='true'] QSpinBox[fanField='true'],
QWidget[fansPage='true'] QDoubleSpinBox[fanField='true'],
QWidget[fansPage='true'] QComboBox[fanField='true'] {{
    min-height: 0px; padding: 3px 8px; font-size: 11px; border-radius: 7px;
}}
QWidget[fansPage='true'] QLabel[fanError='true'] {{ color: {c['red']}; font-size: 10px; font-weight: 600; }}
""")


# -------------------------------------------------------------------- helpers


def _header_text(pwm: int) -> str:
    header = BC250_FAN_HEADERS.get(pwm)
    return header.header if header else f"PWM {pwm}"


def _short_header(pwm: int) -> str:
    """``J4003 F1`` for the table; the editor and tooltip name it in full."""
    header = BC250_FAN_HEADERS.get(pwm)
    if header is None:
        return f"PWM {pwm}"
    return header.header.split("/")[-1].strip().replace("J4003 Fan ", "J4003 F")


def _bios_text(pwm: int) -> str:
    header = BC250_FAN_HEADERS.get(pwm)
    return tr_format("BIOS Fan {number}", number=header.bios_number) if header else ""


def _label_for(mapping, key: str) -> str:
    return tr(dict(mapping).get(key, key))


def _rule() -> QFrame:
    line = QFrame()
    line.setProperty("fanRule", True)
    return line


def _button(text: str, kind: str = "secondary") -> QPushButton:
    button = QPushButton(tr(text))
    button.setProperty("fanButton", kind)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def _field(widget):
    widget.setProperty("fanField", True)
    return widget


def _combo(options) -> GuardedComboBox:
    combo = GuardedComboBox()
    _field(combo)
    for key, label in options:
        combo.addItem(tr(label), key)
    return combo


def _set_combo(combo, key) -> None:
    index = combo.findData(key)
    if index >= 0:
        combo.setCurrentIndex(index)


def _restyle(widget: QWidget, name: str, value) -> None:
    if widget.property(name) == value:
        return
    widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def _read_int(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return None


def _hottest_temperature(base: Path = Path("/sys/class/hwmon")) -> float | None:
    """Read APU and board/VRM temperatures directly, even while UI refresh is paused.

    At least one APU sensor must be available; board readings alone cannot
    prove that it is safe to slow the APU fan.
    """
    values = []
    apu_available = False
    for hwmon in sorted(base.glob("hwmon*")):
        try:
            name = (hwmon / "name").read_text(encoding="utf-8").strip()
        except OSError:
            continue
        apu = name in {"k10temp", "zenpower", "amdgpu"}
        if not apu and not name.startswith("nct"):
            continue
        for temp in hwmon.glob("temp*_input"):
            value = _read_int(temp)
            if value is not None and 0 < value <= 130000:
                values.append(value / 1000.0)
                apu_available = apu_available or apu
    return max(values) if values and apu_available else None


def _wait(seconds: float, cancel: threading.Event) -> None:
    deadline = time.monotonic() + seconds
    while not cancel.is_set() and time.monotonic() < deadline:
        time.sleep(0.1)


def _alignment(right: bool) -> int:
    horizontal = Qt.AlignmentFlag.AlignRight if right else Qt.AlignmentFlag.AlignLeft
    return int(horizontal | Qt.AlignmentFlag.AlignVCenter)


# ------------------------------------------------------------------ the table


class ChannelTableModel(QAbstractTableModel):
    """One row per channel, updated in place by PWM number so the selection
    and the editor's draft survive every refresh."""

    #: The name typed in the Fan column (double click or F2): pwm, name.
    renamed = pyqtSignal(int, str)
    #: The raw duty, for the bar the delegate draws under the figure.
    DUTY_ROLE = Qt.ItemDataRole.UserRole + 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: list[dict] = []

    def set_rows(self, rows: list[dict]) -> None:
        if [row["pwm"] for row in rows] != [row["pwm"] for row in self.rows]:
            self.beginResetModel()
            self.rows = rows
            self.endResetModel()
            return
        self.rows = rows
        if rows:
            self.dataChanged.emit(self.index(0, 0), self.index(len(rows) - 1, len(COLUMNS) - 1))

    def row_for(self, pwm: int) -> int:
        return next((index for index, row in enumerate(self.rows) if row["pwm"] == pwm), -1)

    def pwm_at(self, row: int) -> int | None:
        return self.rows[row]["pwm"] if 0 <= row < len(self.rows) else None

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return tr(COLUMNS[section][0]).upper()
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return _alignment(COLUMNS[section][1])
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        column = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return row["cells"][column]
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return _alignment(COLUMNS[column][1])
        if role == Qt.ItemDataRole.ForegroundRole and column == STATE:
            from PyQt6.QtGui import QColor

            tone = row.get("tone") or ""
            return QColor(COLORS[tone]) if tone in {"green", "orange", "red", "blue"} else None
        if role == Qt.ItemDataRole.ToolTipRole:
            return row.get("tooltip") or None
        if role == Qt.ItemDataRole.EditRole and column == CHANNEL:
            return row.get("label") or ""
        if role == self.DUTY_ROLE and column == DUTY:
            return row.get("duty")
        return None

    def flags(self, index):
        flags = super().flags(index)
        if index.isValid() and index.column() == CHANNEL:
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole) -> bool:  # noqa: N802
        if not index.isValid() or index.column() != CHANNEL or role != Qt.ItemDataRole.EditRole:
            return False
        self.renamed.emit(self.rows[index.row()]["pwm"], " ".join(str(value or "").split()))
        return True


class DutyDelegate(QStyledItemDelegate):
    """PWM % as a small meter: a bar on the left, the figure on the right, so
    a glance down the column tells which fans work hardest."""

    FIGURE_WIDTH = 30

    def paint(self, painter: QPainter, option, index) -> None:
        duty = index.data(ChannelTableModel.DUTY_ROLE)
        if duty is None:
            super().paint(painter, option, index)
            return
        # Selection and alternate background exactly as the other cells.
        background = QStyleOptionViewItem(option)
        self.initStyleOption(background, index)
        background.text = ""
        widget = option.widget
        style = widget.style() if widget is not None else None
        if style is not None:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, background, painter, widget)
        value = max(0, min(100, int(duty)))
        rect = option.rect.adjusted(10, 0, -8, 0)
        figure = rect.adjusted(rect.width() - self.FIGURE_WIDTH, 0, 0, 0)
        bar_width = max(0, rect.width() - self.FIGURE_WIDTH - 8)
        track = rect.adjusted(0, rect.height() // 2 - 2, -(rect.width() - bar_width), 0)
        track.setHeight(4)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(COLORS["progress_track"]))
        painter.drawRoundedRect(track, 2, 2)
        fill = track.adjusted(0, 0, -round(track.width() * (100 - value) / 100), 0)
        painter.setBrush(QColor(COLORS["orange"] if value >= 85 else COLORS["blue"]))
        painter.drawRoundedRect(fill, 2, 2)
        painter.setPen(QColor(COLORS["text"]))
        painter.setFont(option.font)
        painter.drawText(figure, int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), str(value))
        painter.restore()


def _table(model, name: str) -> QTableView:
    view = QTableView()
    view.setObjectName(name)
    view.setModel(model)
    view.setAlternatingRowColors(True)
    view.setShowGrid(False)
    view.setWordWrap(False)
    view.setCornerButtonEnabled(False)
    view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    view.setEditTriggers(
        QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed
    )
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    view.verticalHeader().hide()
    view.verticalHeader().setDefaultSectionSize(30)
    view.horizontalHeader().setHighlightSections(False)
    view.horizontalHeader().setMinimumSectionSize(56)
    return view


# ----------------------------------------------------------------- the editor


class ProfileNameDialog(QInputDialog):
    """QInputDialog creates its fixed-size layout lazily, when shown."""

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().showEvent(event)
        layout = self.layout()
        if layout is not None:
            layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        field = self.findChild(QLineEdit)
        if field is not None:
            field.setMaxLength(MODE_NAME_MAX_LENGTH)
        self.fit_to_content()


class PointsEditor(QWidget):
    """A curve's points as a two-column list: temperature and PWM."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[tuple[QSpinBox, QSpinBox, QPushButton]] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)
        heading = QGridLayout()
        heading.setHorizontalSpacing(8)
        for column, text in enumerate(("Temperature °C", "PWM %")):
            label = QLabel(tr(text).upper())
            label.setProperty("fanSection", True)
            heading.addWidget(label, 0, column)
        heading.setColumnStretch(0, 1)
        heading.setColumnStretch(1, 1)
        heading.setColumnMinimumWidth(2, 80)
        root.addLayout(heading)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(4)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
        self.grid.setColumnMinimumWidth(2, 80)
        root.addLayout(self.grid)
        self.add_button = _button("Add point")
        self.add_button.clicked.connect(self._add)
        root.addWidget(self.add_button, 0, Qt.AlignmentFlag.AlignLeft)

    def set_points(self, points) -> None:
        while self._rows:
            for widget in self._rows.pop():
                self.grid.removeWidget(widget)
                widget.deleteLater()
        for temperature, speed in points:
            self._append(int(temperature), int(speed))
        self._sync()

    def points(self) -> list[list[int]]:
        return [[temperature.value(), speed.value()] for temperature, speed, _remove in self._rows]

    def set_point(self, index: int, temperature: int, speed: int) -> None:
        """A point moved on the chart: show it here, and say so once."""
        if not 0 <= index < len(self._rows):
            return
        temp, duty, _remove = self._rows[index]
        for widget, value in ((temp, temperature), (duty, speed)):
            widget.blockSignals(True)
            widget.setValue(int(value))
            widget.blockSignals(False)
        self.changed.emit()

    def _append(self, temperature: int, speed: int) -> None:
        row = len(self._rows)
        temp = _field(QSpinBox())
        temp.setRange(0, 120)
        temp.setSuffix(" °C")
        temp.setValue(temperature)
        duty = _field(QSpinBox())
        duty.setRange(0, 100)
        duty.setSuffix(" %")
        duty.setValue(speed)
        remove = _button("Remove")
        remove.setAccessibleName(tr_format("Remove point {number}", number=row + 1))
        for widget in (temp, duty):
            widget.valueChanged.connect(lambda _value: self.changed.emit())
        remove.clicked.connect(lambda _checked=False, target=remove: self._remove(target))
        self.grid.addWidget(temp, row, 0)
        self.grid.addWidget(duty, row, 1)
        self.grid.addWidget(remove, row, 2)
        self._rows.append((temp, duty, remove))

    def _add(self) -> None:
        points = self.points()
        if len(points) >= engine.CURVE_MAX_POINTS:
            return
        last_t, last_s = points[-1] if points else (40, 30)
        self._append(min(120, last_t + 5), min(100, last_s + 10))
        self._sync()
        self.changed.emit()

    def _remove(self, target: QPushButton) -> None:
        if len(self._rows) <= engine.CURVE_MIN_POINTS:
            return
        points = [
            [temperature.value(), speed.value()]
            for temperature, speed, remove in self._rows if remove is not target
        ]
        self.set_points(points)
        self.changed.emit()

    def _sync(self) -> None:
        self.add_button.setEnabled(len(self._rows) < engine.CURVE_MAX_POINTS)
        for _temperature, _speed, remove in self._rows:
            remove.setEnabled(len(self._rows) > engine.CURVE_MIN_POINTS)


class ChannelEditor(QFrame):
    """The selected channel: its name, mode and the controls that mode needs.

    Edits are a draft until Apply; a refresh only updates the live readings.
    """

    apply_requested = pyqtSignal(int, object)   # pwm, engine channel (None: firmware)
    rename_requested = pyqtSignal(int, str)
    calibrate_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("fanEditor", True)
        self.setObjectName("fanEditor")
        self.pwm: int | None = None
        self._saved: dict = {"mode": "firmware"}
        self._loading = False
        self.dirty = False
        self.retry = False
        self.resume = False
        self._mix_members: list[dict] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        title_row = QHBoxLayout()
        self.title = QLabel(tr("No channel"))
        self.title.setProperty("fanEditorTitle", True)
        title_row.addWidget(self.title, 1)
        self.live = QLabel("")
        self.live.setProperty("fanFieldValue", True)
        self.live.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(self.live)
        root.addLayout(title_row)
        self.subtitle = QLabel("")
        self.subtitle.setProperty("fanMuted", True)
        root.addWidget(self.subtitle)
        root.addWidget(_rule())

        self.form = self._grid()
        self.name = _field(QLineEdit())
        self.name.setMaxLength(LABEL_MAX_LENGTH)
        self.name.setPlaceholderText(tr("Name this fan"))
        self.name.editingFinished.connect(self._rename)
        self.mode = _combo(MODE_LABELS)
        self.role = _combo(ROLE_LABELS)
        self._form_row(0, "Name", self.name)
        self._form_row(1, "Mode", self.mode)
        self.role_caption = self._form_row(2, "Function", self.role)
        root.addLayout(self.form)

        self.pages = FanModeStack()
        self.pages.page_height_changed.connect(self._fit_pages)
        self.pages.addWidget(self._firmware_page())
        self.pages.addWidget(self._fixed_page())
        self.pages.addWidget(self._curve_page())
        self.pages.addWidget(self._mix_page())
        root.addWidget(self.pages)

        tools = QHBoxLayout()
        tools.setSpacing(8)
        self.advanced_toggle = _button("Advanced")
        self.advanced_toggle.setCheckable(True)
        tools.addWidget(self.advanced_toggle)
        self.calibrate_button = _button("Calibrate")
        self.calibrate_button.setToolTip(tr(
            "Measures the lowest PWM at which this fan keeps turning and the one at which it starts, "
            "and proposes them as its minimum and spin-up kick."
        ))
        self.calibrate_button.clicked.connect(
            lambda: self.calibrate_requested.emit(self.pwm) if self.pwm is not None else None
        )
        tools.addWidget(self.calibrate_button)
        tools.addStretch(1)
        root.addLayout(tools)
        self.advanced = self._advanced_page()
        self.advanced.hide()
        self.advanced_toggle.toggled.connect(self.advanced.setVisible)
        root.addWidget(self.advanced)

        root.addStretch(1)
        self.feedback = QWidget()
        feedback = QVBoxLayout(self.feedback)
        feedback.setContentsMargins(12, 8, 12, 8)
        self.error = QLabel("")
        self.error.setProperty("fanError", True)
        self.error.setWordWrap(True)
        self.error.hide()
        feedback.addWidget(self.error)
        self.note = QLabel("")
        self.note.setProperty("fanMuted", True)
        self.note.setWordWrap(True)
        self.note.hide()
        feedback.addWidget(self.note)
        actions = QHBoxLayout()
        actions.addStretch(1)
        self.revert_button = _button("Revert")
        self.apply_button = _button("Apply", "primary")
        actions.addWidget(self.revert_button)
        actions.addWidget(self.apply_button)
        feedback.addLayout(actions)
        root.addWidget(self.feedback)

        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.role.currentIndexChanged.connect(self._mode_changed)
        self.revert_button.clicked.connect(self.revert)
        self.apply_button.clicked.connect(self.apply)
        self._sync_actions()
        self.setEnabled(False)

    # ---------------------------------------------------------------- layout

    def _form_row(self, row: int, label: str, widget: QWidget, layout: QGridLayout | None = None) -> QLabel:
        caption = QLabel(tr(label))
        caption.setProperty("fanFieldLabel", True)
        target = layout if layout is not None else self.form
        target.addWidget(caption, row, 0)
        target.addWidget(widget, row, 1)
        return caption

    @staticmethod
    def _grid() -> QGridLayout:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        grid.setColumnMinimumWidth(0, LABEL_COLUMN_WIDTH)
        return grid

    def _firmware_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        text = QLabel(tr("The BIOS fan curve drives this header. BC250 Control Center does not write to it."))
        text.setProperty("fanMuted", True)
        text.setWordWrap(True)
        layout.addWidget(text)
        return page

    def _fixed_page(self) -> QWidget:
        page = QWidget()
        layout = self._grid()
        page.setLayout(layout)
        self.fixed_slider = QSlider(Qt.Orientation.Horizontal)
        self.fixed_slider.setRange(0, 100)
        self.fixed_spin = _field(QSpinBox())
        self.fixed_spin.setRange(0, 100)
        self.fixed_spin.setSuffix(" %")
        self.fixed_slider.valueChanged.connect(self.fixed_spin.setValue)
        self.fixed_spin.valueChanged.connect(self.fixed_slider.setValue)
        self.fixed_spin.valueChanged.connect(self._changed)
        holder = QWidget()
        speed = QHBoxLayout(holder)
        speed.setContentsMargins(0, 0, 0, 0)
        speed.addWidget(self.fixed_slider, 1)
        speed.addWidget(self.fixed_spin)
        self._form_row(0, "Speed", holder, layout)
        preset_holder = QWidget()
        presets = QHBoxLayout(preset_holder)
        presets.setContentsMargins(0, 0, 0, 0)
        self.preset_buttons: list[QPushButton] = []
        for profile in load_fan_profiles():
            button = _button(f"{profile.percent} %")
            button.setToolTip(tr(profile.name))
            button.setAccessibleName(f"{tr(profile.name)} {profile.percent} %")
            button.setProperty("fanPercent", profile.percent)
            button.clicked.connect(lambda _c=False, button=button: self.fixed_spin.setValue(int(button.property("fanPercent"))))
            presets.addWidget(button)
            self.preset_buttons.append(button)
        presets.addStretch(1)
        self._form_row(1, "Presets", preset_holder, layout)
        return page

    def refresh_presets(self) -> None:
        for button, profile in zip(self.preset_buttons, load_fan_profiles()):
            button.setText(f"{profile.percent} %")
            button.setProperty("fanPercent", profile.percent)
            button.setToolTip(tr(profile.name))
            button.setAccessibleName(f"{tr(profile.name)} {profile.percent} %")

    def _curve_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        grid = self._grid()
        self.source = _combo(SOURCE_LABELS)
        self.source.currentIndexChanged.connect(self._changed)
        self._form_row(0, "Follows", self.source, grid)
        layout.addLayout(grid)
        self.plot = FanCurvePlot()
        self.plot.set_compact(True)
        self.plot.setFixedHeight(240)
        self.plot.set_editable(True)
        self.plot.setToolTip(tr("Drag a point to move it."))
        layout.addWidget(self.plot)
        self.points = PointsEditor()
        self.points.changed.connect(self._changed)
        self.plot.point_moved.connect(self.points.set_point)
        layout.addWidget(self.points)
        return page

    def _mix_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        explain = QLabel(tr("The fan takes the highest PWM of these curves, each on its own sensor."))
        explain.setProperty("fanMuted", True)
        explain.setWordWrap(True)
        layout.addWidget(explain)
        bar = QHBoxLayout()
        self.member = _combo(())
        self.member.currentIndexChanged.connect(self._member_changed)
        bar.addWidget(self.member, 1)
        self.member_add = _button("Add curve")
        self.member_remove = _button("Remove curve")
        self.member_add.clicked.connect(self._add_member)
        self.member_remove.clicked.connect(self._remove_member)
        bar.addWidget(self.member_add)
        bar.addWidget(self.member_remove)
        layout.addLayout(bar)
        grid = self._grid()
        self.member_source = _combo(SOURCE_LABELS)
        self.member_source.currentIndexChanged.connect(self._member_edited)
        self._form_row(0, "Follows", self.member_source, grid)
        layout.addLayout(grid)
        self.mix_plot = FanCurvePlot()
        self.mix_plot.set_compact(True)
        self.mix_plot.setFixedHeight(240)
        self.mix_plot.set_editable(True)
        self.mix_plot.setToolTip(tr("Drag a point to move it."))
        layout.addWidget(self.mix_plot)
        self.member_points = PointsEditor()
        self.member_points.changed.connect(self._member_edited)
        self.mix_plot.point_moved.connect(self.member_points.set_point)
        layout.addWidget(self.member_points)
        return page

    def _advanced_page(self) -> QWidget:
        page = QWidget()
        grid = self._grid()
        grid.setVerticalSpacing(6)
        page.setLayout(grid)

        def spin(low, high, suffix, decimals=0):
            box = _field(QDoubleSpinBox() if decimals else QSpinBox())
            if decimals:
                box.setDecimals(decimals)
                box.setSingleStep(0.5)
            box.setRange(low, high)
            box.setSuffix(suffix)
            box.valueChanged.connect(self._changed)
            return box

        self.min_percent = spin(0, 100, " %")
        self.max_percent = spin(0, 100, " %")
        self.hysteresis = spin(0, 10, " °C", 1)
        self.delay = spin(0, 30, " s", 1)
        self.up_step = spin(1, 100, " %")
        self.down_step = spin(1, 100, " %")
        self.start_percent = spin(0, 100, " %")
        self.stall = QCheckBox(tr("Warn when the fan stops while it should turn"))
        self.stall.toggled.connect(self._changed)
        rows = (
            ("Minimum PWM", self.min_percent), ("Maximum PWM", self.max_percent),
            ("Hysteresis", self.hysteresis), ("Response delay", self.delay),
            ("Largest step up", self.up_step), ("Largest step down", self.down_step),
            ("Spin-up kick", self.start_percent),
        )
        self._advanced_curve_rows = []
        for row, (label, widget) in enumerate(rows):
            self._advanced_curve_rows.append((self._form_row(row, label, widget, grid), widget))
        grid.addWidget(self.stall, len(rows), 0, 1, 2)
        return page

    # -------------------------------------------------------------- state io

    def load(self, pwm: int, entry: dict | None, label: str) -> None:
        """Show ``pwm``'s saved setting. A draft of the same channel survives."""
        if self.dirty and pwm == self.pwm:
            return
        self._loading = True
        self.setEnabled(True)
        self.pwm = pwm
        self._saved = dict(entry or {"mode": "firmware"})
        saved = self._saved
        self.title.setText(label or f"PWM {pwm}")
        self.subtitle.setText(" · ".join(part for part in (f"PWM {pwm}", _header_text(pwm), _bios_text(pwm)) if part))
        self.name.setText(label if label and label != _header_text(pwm) else "")
        _set_combo(self.mode, saved.get("mode", "firmware"))
        _set_combo(self.role, saved.get("role", "fan"))
        self.fixed_spin.setValue(int(saved.get("percent", 60)))
        _set_combo(self.source, saved.get("source", "hottest"))
        self.points.set_points(saved.get("points") or DEFAULT_CURVE)
        self.plot.set_curve([tuple(point) for point in saved.get("points") or DEFAULT_CURVE])
        self.plot.set_target(pwm)
        self._mix_members = [dict(member) for member in saved.get("mix") or []] or [
            {"source": "gpu", "points": [list(p) for p in DEFAULT_CURVE]},
            {"source": "vrm", "points": [[70, 30], [95, 100]]},
        ]
        self._fill_members(0)
        pump = saved.get("role") == "pump"
        self.min_percent.setValue(int(saved.get("min_percent", engine.PUMP_DEFAULT_MIN_PERCENT if pump else 0)))
        self.max_percent.setValue(int(saved.get("max_percent", 100)))
        self.hysteresis.setValue(float(saved.get("hysteresis_c", 1.0)))
        self.delay.setValue(float(saved.get("response_delay_seconds", 0.0)))
        self.up_step.setValue(int(saved.get("max_up_step_percent", 100)))
        self.down_step.setValue(int(saved.get("max_down_step_percent", 10)))
        self.start_percent.setValue(int(saved.get("start_percent", 0)))
        self.stall.setChecked(bool(saved.get("stall_detect", True)))
        self._loading = False
        self._mode_changed()
        self.dirty = False
        self._sync_actions()

    def set_live(self, row: dict, status: dict) -> None:
        """Readings only; never touches the draft."""
        rpm = row.get("rpm")
        duty = _pwm_to_percent(row.get("pwm")) if row.get("pwm") is not None else None
        parts = []
        if rpm is not None:
            parts.append(f"{_integer(rpm)} RPM")
        if duty is not None:
            parts.append(f"{duty} %")
        self.live.setText(" · ".join(parts))
        temperature = _finite_number(status.get("temperature"))
        for plot in (self.plot, self.mix_plot):
            plot.set_live(temperature, status.get("percent"), str(status.get("sensor") or ""))
            plot.set_enabled(True)

    def set_note(self, text: str) -> None:
        self.note.setText(text)
        self.note.setVisible(bool(text))

    def entry(self) -> dict:
        mode = self.mode.currentData()
        if mode == "firmware":
            return {"mode": "firmware"}
        entry: dict = {"mode": mode, "role": self.role.currentData()}
        if mode == "fixed":
            entry["percent"] = self.fixed_spin.value()
            entry["preset"] = ""
        else:
            if mode == "curve":
                entry["source"] = self.source.currentData()
                entry["points"] = self.points.points()
            else:
                self._store_member()
                entry["mix"] = [dict(member) for member in self._mix_members]
            entry.update({
                "min_percent": self.min_percent.value(),
                "max_percent": self.max_percent.value(),
                "hysteresis_c": float(self.hysteresis.value()),
                "response_delay_seconds": float(self.delay.value()),
                "max_up_step_percent": self.up_step.value(),
                "max_down_step_percent": self.down_step.value(),
                "start_percent": self.start_percent.value(),
                "deadband_percent": self._saved.get("deadband_percent", 2),
            })
        entry["stall_detect"] = self.stall.isChecked()
        return entry

    def validation_error(self) -> str:
        if self.pwm is None:
            return ""
        try:
            engine.validate_policy({"schema": 2, "channels": {str(self.pwm): self.entry()}})
        except ValueError as error:
            return tr(str(error))
        return ""

    # ---------------------------------------------------------------- events

    def _fit_pages(self) -> None:
        page = self.pages.currentWidget()
        if page is not None:
            self.pages.setFixedHeight(max(page.minimumSizeHint().height(), page.sizeHint().height()))

    def _mode_changed(self, *_args) -> None:
        mode = self.mode.currentData() or "firmware"
        self.pages.setCurrentIndex([key for key, _label in MODE_LABELS].index(mode))
        self._fit_pages()
        tunable = mode in {"curve", "mix"}
        self.role.setVisible(mode != "firmware")
        self.role_caption.setVisible(mode != "firmware")
        self.advanced_toggle.setVisible(mode != "firmware")
        self.calibrate_button.setVisible(tunable and self.role.currentData() != "pump")
        for caption, widget in self._advanced_curve_rows:
            caption.setVisible(tunable)
            widget.setVisible(tunable)
        if mode == "firmware":
            self.advanced_toggle.setChecked(False)
        self._changed()

    def _changed(self, *_args) -> None:
        if self._loading:
            return
        self.dirty = self._normalized(self.entry()) != self._normalized(self._saved)
        if self.mode.currentData() == "curve":
            self.plot.set_curve([tuple(point) for point in self.points.points()])
        error = self.validation_error()
        self.error.setText(error)
        self.error.setVisible(bool(error))
        self._sync_actions()

    def _normalized(self, entry: dict) -> dict:
        if self.pwm is None:
            return dict(entry)
        if entry.get("mode", "firmware") == "firmware":
            return {"mode": "firmware"}
        try:
            policy = engine.validate_policy({"schema": 2, "channels": {str(self.pwm): entry}})
        except ValueError:
            return dict(entry)
        return policy["channels"][str(self.pwm)]

    def _sync_actions(self) -> None:
        self.revert_button.setEnabled(self.dirty)
        self.apply_button.setText(tr("Resume" if self.resume and not self.dirty else "Retry" if self.retry and not self.dirty else "Apply"))
        self.apply_button.setEnabled((self.dirty or self.retry or self.resume) and not self.error.text())

    def revert(self) -> None:
        if self.pwm is None:
            return
        self.dirty = False
        self.load(self.pwm, self._saved, self.title.text())

    def apply(self) -> None:
        if self.pwm is None or self.validation_error():
            return
        entry = self._normalized(self.entry())
        self.apply_requested.emit(self.pwm, None if entry.get("mode") == "firmware" else entry)

    def propose_calibration(self, result: CalibrationResult) -> None:
        """Put measured limits in the draft; Apply makes them the setting."""
        self.min_percent.setValue(result.proposed_min)
        self.start_percent.setValue(result.proposed_start)
        self.advanced_toggle.setChecked(True)
        self._changed()

    def accept_saved(self, entry: dict | None) -> None:
        """The page saved the draft: it is the new baseline."""
        self._saved = dict(entry or {"mode": "firmware"})
        self.dirty = False
        self._sync_actions()

    def _rename(self) -> None:
        if self.pwm is not None:
            self.rename_requested.emit(self.pwm, self.name.text().strip())

    # ------------------------------------------------------------------ mix

    def _fill_members(self, current: int) -> None:
        self.member.blockSignals(True)
        self.member.clear()
        for index in range(len(self._mix_members)):
            self.member.addItem(tr_format("Curve {number}", number=index + 1), index)
        self.member.setCurrentIndex(max(0, min(current, len(self._mix_members) - 1)))
        self.member.blockSignals(False)
        self._show_member()

    def _show_member(self) -> None:
        index = self.member.currentIndex()
        if not 0 <= index < len(self._mix_members):
            return
        member = self._mix_members[index]
        was = self._loading
        self._loading = True
        _set_combo(self.member_source, member.get("source", "hottest"))
        self.member_points.set_points(member.get("points") or DEFAULT_CURVE)
        self.mix_plot.set_curve([tuple(point) for point in member.get("points") or DEFAULT_CURVE])
        self._loading = was
        self.member_add.setEnabled(len(self._mix_members) < engine.MIX_MAX_MEMBERS)
        self.member_remove.setEnabled(len(self._mix_members) > 2)

    def _store_member(self) -> None:
        index = self.member.currentIndex()
        if 0 <= index < len(self._mix_members):
            self._mix_members[index] = {
                "source": self.member_source.currentData(),
                "points": self.member_points.points(),
            }

    def _member_changed(self, *_args) -> None:
        self._show_member()

    def _member_edited(self, *_args) -> None:
        if self._loading:
            return
        self._store_member()
        self.mix_plot.set_curve([tuple(point) for point in self.member_points.points()])
        self._changed()

    def _add_member(self) -> None:
        self._store_member()
        if len(self._mix_members) < engine.MIX_MAX_MEMBERS:
            self._mix_members.append({"source": "hottest", "points": [list(p) for p in DEFAULT_CURVE]})
            self._fill_members(len(self._mix_members) - 1)
            self._changed()

    def _remove_member(self) -> None:
        if len(self._mix_members) > 2:
            del self._mix_members[self.member.currentIndex()]
            self._fill_members(0)
            self._changed()


# ---------------------------------------------------------------- the page


class FansPage(QWidget):
    """The Fans module."""

    #: Ask the window to open Settings on a page (the daemon's options).
    settings_requested = pyqtSignal(str)

    def __init__(self, controller, parent: QWidget | None = None, *, activity_service=None, settings_service=None):
        super().__init__(parent)
        self.controller = controller
        self.activity_service = activity_service
        self.settings_service = settings_service
        self.current_state: dict = {}
        self.performance_state: dict = {}
        self.gpu_state: dict = {}
        self._system_fan_control: dict = {}
        self._system_fan_busy = False
        self._system_fan_sync_error = ""
        self._fan_sync_pending = False
        self._fan_sync_pending_notice = ""
        self._pending_channels: set[int] = set()
        self._verified_channels: set[int] = set()
        self._profile_selection_pending = False
        self._fan_root_config: dict = {}
        self._busy = False
        self._worker = None
        self._updates_active = False
        self._event_sequence = 0
        self._selected_pwm: int | None = None
        self._config_loaded = False
        self._state_cache = state_cache_for(controller)
        self._background = BackgroundExecutor(self)
        self._channels_service = (
            FanChannelsService(settings_service)
            if callable(getattr(settings_service, "read_local_config", None)) else None
        )
        self._board: ChannelBoard | None = None

        self.setProperty("fansPage", True)
        self.setStyleSheet(fans_stylesheet())
        # The same shell as Processes and Black box: one page card inside the
        # standard content margins, so the page lines up with every other one.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll = QScrollArea()
        self.content = QWidget()
        configure_responsive_scroll_area(self.scroll, self.content)
        self.content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.content.setProperty("redesignedModule", True)
        self.content.setProperty("fansPage", True)
        root = QVBoxLayout(self.content)
        root.setContentsMargins(18, 8, 18, 20)
        root.setSpacing(14)
        self.scroll.setWidget(self.content)
        outer.addWidget(self.scroll)

        self.panel = SectionCard("Fans", "", icon_name="")
        self.panel.drop_header()
        self.panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self.panel, 1)
        panel = self.panel.body
        panel.setSpacing(12)

        # The toolbar: the profile on the left, control from boot and More on
        # the right. Narrow pages stack the two groups.
        self.toolbar_box = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.toolbar_box.setSpacing(14)

        profile_row = QHBoxLayout()
        profile_row.setSpacing(8)
        self.profile_label = QLabel(tr("Profile"))
        self.profile_label.setProperty("fanFieldLabel", True)
        profile_row.addWidget(self.profile_label)
        self.profile_combo = _combo(())
        self.profile_combo.setSizeAdjustPolicy(
            GuardedComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.profile_combo.setMinimumContentsLength(8)
        self.profile_combo.currentIndexChanged.connect(self._profile_choice_changed)
        profile_row.addWidget(self.profile_combo, 1)
        self.profile_apply = _button("Apply profile", "primary")
        self.profile_apply.clicked.connect(self._apply_profile)
        profile_row.addWidget(self.profile_apply)
        self.profile_save = _button("Save as…")
        self.profile_save.clicked.connect(self._save_profile)
        profile_row.addWidget(self.profile_save)
        self.toolbar_box.addLayout(profile_row, 0)
        self.toolbar_box.addStretch(1)

        boot_row = QHBoxLayout()
        boot_row.setSpacing(10)
        self.boot_switch = ToggleSwitch()
        self.boot_switch.setAccessibleName(tr("Control from boot"))
        self.boot_switch.clicked.connect(lambda _checked=False: self._toggle_system_control())
        self.boot_label = QLabel(tr("Control from boot"))
        self.boot_label.setProperty("fanSwitchLabel", True)
        boot_row.addWidget(self.boot_switch, 0, Qt.AlignmentFlag.AlignVCenter)
        boot_row.addWidget(self.boot_label, 0, Qt.AlignmentFlag.AlignVCenter)
        boot_row.addSpacing(6)
        self.more_button = _button("More")
        self.more_menu = QMenu(self.more_button)
        # popup(), not setMenu(): a menu attached to a button opens through
        # QMenu.exec, a nested event loop that blocks whoever clicked it.
        self.more_button.clicked.connect(self._show_more_menu)
        boot_row.addWidget(self.more_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.toolbar_box.addLayout(boot_row, 0)
        panel.addLayout(self.toolbar_box)
        panel.addWidget(_rule())

        # Who drives the fans now, in one line under the toolbar.
        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        self.status_line = QLabel(tr("Checking the system fan service…"))
        self.status_line.setProperty("fanStatus", True)
        self.status_line.setWordWrap(True)
        status_row.addWidget(self.status_line, 1)
        self.sync_button = _button("Sync now", "primary")
        self.sync_button.clicked.connect(lambda: self._sync_system_fan_policy(force=True))
        self.sync_button.hide()
        status_row.addWidget(self.sync_button)
        panel.addLayout(status_row)

        self.driver_notice = QFrame()
        notice_row = QHBoxLayout(self.driver_notice)
        notice_row.setContentsMargins(0, 0, 0, 0)
        self.driver_text = QLabel("")
        self.driver_text.setProperty("fanStatus", True)
        self.driver_text.setProperty("tone", "orange")
        self.driver_text.setWordWrap(True)
        notice_row.addWidget(self.driver_text, 1)
        self.driver_button = _button("Prepare PWM driver", "primary")
        self.driver_button.clicked.connect(lambda: self.prepare_pwm_driver())
        notice_row.addWidget(self.driver_button)
        self.driver_notice.hide()
        panel.addWidget(self.driver_notice)

        self.model = ChannelTableModel(self)
        self.table = _table(self.model, "fanTable")
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(CHANNEL, QHeaderView.ResizeMode.Stretch)
        header.setMinimumSectionSize(48)
        for column, width in ((BIOS, 40), (MODE, 76), (FOLLOWS, 126), (TEMPERATURE, 48),
                              (DUTY, 92), (RPM, 56), (STATE, 80)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(column, width)
        self.table.selectionModel().currentRowChanged.connect(self._row_changed)
        self.table.setItemDelegateForColumn(DUTY, DutyDelegate(self.table))
        self.model.renamed.connect(self._rename_channel)
        self.editor = ChannelEditor()
        self.editor.apply_requested.connect(self._apply_channel)
        self.editor.rename_requested.connect(self._rename_channel)
        self.editor.calibrate_requested.connect(self._calibrate_channel)
        self._calibration_cancel = threading.Event()
        editor_scroll = QScrollArea()
        editor_scroll.setObjectName("fanEditorScroll")
        editor_scroll.setWidgetResizable(True)
        editor_scroll.setFrameShape(QFrame.Shape.NoFrame)
        editor_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        editor_scroll.setWidget(self.editor)
        editor_scroll.viewport().setAutoFillBackground(False)
        self.editor_scroll = editor_scroll
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setObjectName("fanSplitter")
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(14)
        self.splitter.addWidget(self.table)
        editor_column = QWidget()
        editor_layout = QVBoxLayout(editor_column)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(0)
        editor_layout.addWidget(editor_scroll, 1)
        editor_layout.addWidget(self.editor.feedback)
        self.splitter.addWidget(editor_column)
        self.splitter.setStretchFactor(0, 13)
        self.splitter.setStretchFactor(1, 8)
        # No minimum widths here: the breakpoint decides the orientation, and a
        # minimum would keep the page from ever getting narrow enough to flip.
        panel.addWidget(self.splitter, 1)

        self.footer = QLabel("")
        self.footer.setProperty("fanFooter", True)
        self.footer.setProperty("i18nLiteral", True)
        self.footer.setWordWrap(True)
        panel.addWidget(self.footer)

        self._render_profiles()
        self.timer = QTimer(self)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(self.refresh)
        self._refresher = AsyncRefresh(
            self, "fans-refresh", self._fetch_refresh_payload,
            self._apply_refresh_payload, self._refresh_failed,
        )

    # ----------------------------------------------------------- app hooks

    def apply_appearance(self) -> None:
        self.setStyleSheet(fans_stylesheet())

    def retranslate_dynamic_copy(self) -> None:
        self._render()

    def set_updates_active(self, active: bool) -> None:
        self._updates_active = bool(active)
        if self._updates_active:
            self._load_config()
            if not self.timer.isActive():
                self.timer.start()
            self._refresher.activate(fresh_for=1.5)
        else:
            self._refresher.set_active(False)
            self.timer.stop()

    def refresh(self) -> None:
        if self._busy:
            return
        self._refresher.request()

    def _set_control_mode(self, mode: str) -> None:
        """Dashboard shortcuts: open a channel on Fixed ("manual") or Curve."""
        if self.editor.pwm is None and self.model.rowCount():
            self.table.selectRow(0)
        if self.editor.pwm is not None:
            _set_combo(self.editor.mode, "fixed" if mode == "manual" else "curve")
        self.editor.mode.setFocus()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        narrow = self.width() < NARROW_BREAKPOINT
        direction = QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight
        if self.toolbar_box.direction() != direction:
            self.toolbar_box.setDirection(direction)
        for column in (BIOS, FOLLOWS, TEMPERATURE):
            self.table.setColumnHidden(column, narrow)
        self.profile_label.setVisible(not narrow)
        self.profile_save.setVisible(not narrow)  # also in More
        self.boot_label.setWordWrap(narrow)
        vertical = self.width() < STACK_BREAKPOINT
        orientation = Qt.Orientation.Vertical if vertical else Qt.Orientation.Horizontal
        if self.splitter.orientation() != orientation:
            self.splitter.setOrientation(orientation)
            self.table.setMinimumHeight(220 if vertical else 0)
            self.editor_scroll.setMinimumHeight(420 if vertical else 0)
            total = self.splitter.height() if vertical else self.splitter.width()
            first = 240 if vertical else int(total * 0.62)
            self.splitter.setSizes([first, max(1, total - first)])

    # ------------------------------------------------------------- refresh

    def _load_config(self) -> None:
        if self._config_loaded:
            return
        self._config_loaded = True
        self._reload_fan_config()

    def _read_config(self) -> dict:
        try:
            return _dict(self.settings_service.read_local_config()) if self.settings_service else {}
        except Exception:
            return {}

    def _reload_fan_config(self) -> None:
        self._fan_root_config = self._read_config()
        if self._channels_service is not None:
            try:
                self._board = self._channels_service.board()
            except Exception:
                self._board = None
        self._render()

    def _manual_refresh(self) -> None:
        self._state_cache.invalidate("fans", "performance", "gpu")
        self.refresh()

    def _fetch_refresh_payload(self) -> dict[str, dict]:
        system = {}
        reader = getattr(self.controller, "estado_control_fan_sistema", None)
        if callable(reader):
            try:
                system = reader()
            except Exception:  # a missing service is a state, never a refresh failure
                system = {}
        return {
            "fans": self._state_cache.fans(),
            "performance": self._state_cache.performance(),
            "gpu": self._state_cache.gpu(),
            "system": system if isinstance(system, dict) else {},
        }

    def _refresh_failed(self, message: str) -> None:
        self.footer.setText(str(message or tr("Read error")))

    def _apply_refresh_payload(self, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        self.current_state = _dict(data.get("fans"))
        self.performance_state = _dict(data.get("performance"))
        self.gpu_state = _dict(data.get("gpu"))
        self._system_fan_control = _dict(data.get("system"))
        self._render()

    # ------------------------------------------------------------- reading

    def _fan_rows(self) -> dict[int, dict]:
        sensors = _dict(self.current_state.get("sensores"))
        rows = {}
        for fan in sensors.get("fans") or []:
            if isinstance(fan, dict):
                rows[_integer(fan.get("index"), -1)] = fan
        return rows

    def _visible_fans(self) -> list[dict]:
        rows = self._fan_rows()
        return [rows[pwm] for pwm in sorted(rows) if rows[pwm].get("pwm_path")]

    def _fan_control_available(self) -> bool:
        return bool(self.current_state.get("driver_control")) and any(
            fan.get("pwm_writable") or fan.get("pwm_root_writable") for fan in self._visible_fans()
        )

    def _fan_external(self) -> bool:
        return bool(self._system_fan_control.get("external"))

    def _fan_managers(self) -> list[str]:
        managers = self._system_fan_control.get("managers")
        return [str(item) for item in managers] if isinstance(managers, list) else []

    def _system_fan_owned(self) -> bool:
        return system_fan_control_owns_fan(self._system_fan_control)

    def _service_status(self) -> dict:
        return _dict(self._system_fan_control.get("status"))

    def _desktop_fan_policy(self) -> dict | None:
        return build_system_fan_policy(self._fan_root_config)

    def _channel_numbers(self) -> list[int]:
        return board_view.channel_numbers(self._fan_rows(), self._board.channels if self._board else {})

    def _row(self, pwm: int) -> dict:
        board = self._board
        entry = (board.channels.get(str(pwm)) if board else None) or {"mode": "firmware"}
        label = (board.labels.get(str(pwm)) if board else "") or ""
        fan = self._fan_rows().get(pwm, {})
        status = self._channel_status(pwm)
        mode = entry.get("mode", "firmware")
        mode_text = tr(dict(MODE_LABELS)[mode])
        if entry.get("role") == "pump" and mode != "firmware":
            mode_text = f"{mode_text} · {tr('Pump')}"
        if mode == "curve":
            follows = _label_for(SOURCE_LABELS, entry.get("source", "hottest"))
        elif mode == "mix":
            follows = tr_format("{count} curves", count=len(entry.get("mix") or []))
        else:
            follows = "—"
        temperature = _finite_number(status.get("temperature"))
        rpm = fan.get("rpm")
        duty = _pwm_to_percent(fan.get("pwm")) if fan.get("pwm") is not None else None
        state, tone = self._row_state(mode, fan, status, pwm=pwm)
        identity = " · ".join(part for part in (_header_text(pwm), _bios_text(pwm)) if part)
        return {
            "pwm": pwm,
            "entry": entry,
            "label": label,
            "fan": fan,
            "status": status,
            "tone": tone,
            "tooltip": f"PWM {pwm} · {identity}",
            "duty": duty,
            "cells": (
                label or _short_header(pwm),
                str(BC250_FAN_HEADERS[pwm].bios_number) if pwm in BC250_FAN_HEADERS else "—",
                mode_text,
                follows,
                f"{temperature:.1f}" if temperature is not None else "—",
                str(duty) if duty is not None else "—",
                str(_integer(rpm)) if rpm is not None else "—",
                state,
            ),
        }

    def _channel_status(self, pwm: int) -> dict:
        """The service's view of one channel (shared with the web and the TUI)."""
        return board_view.channel_status(self._system_fan_control, pwm)

    def _row_state(self, mode: str, fan: dict, status: dict, *, pwm: int | None = None) -> tuple[str, str]:
        text, tone = board_view.row_state(
            mode, fan, status, external=self._fan_external(),
            service_enabled=bool(self._system_fan_control.get("enabled")),
            pending=pwm in self._pending_channels, verified=pwm in self._verified_channels,
        )
        return tr(text), tone

    # ------------------------------------------------------------- render

    def _render(self) -> None:
        rows = [self._row(pwm) for pwm in self._channel_numbers()]
        self.model.set_rows(rows)
        if rows:
            selected = self._selected_pwm
            target = selected if selected is not None and self.model.row_for(selected) >= 0 else rows[0]["pwm"]
            row_index = self.model.row_for(target)
            if self.table.currentIndex().row() != row_index:
                self.table.selectRow(row_index)
            else:
                self._load_editor(target)
        self._render_status()
        self._render_driver_notice()
        self._render_profiles()
        self._render_footer(rows)

    def _confirm_draft(self, *, discard_only: bool = False) -> bool:
        if not self.editor.dirty:
            return True
        dialog = ConfirmDialog(
            "Unapplied changes", "The changes to this fan were not applied.",
            confirm_text="Discard" if discard_only else "Apply",
            secondary_text="" if discard_only else "Discard", eyebrow="Fans", tone="blue", parent=self,
        )
        answer = dialog.exec()
        if answer == DIALOG_SECONDARY or (discard_only and answer == QDialog.DialogCode.Accepted):
            self.editor.dirty = False
            return True
        if answer != QDialog.DialogCode.Accepted or self.editor.validation_error():
            return False
        entry = self.editor._normalized(self.editor.entry())
        return self._apply_channel(self.editor.pwm, None if entry.get("mode") == "firmware" else entry)

    def _row_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        pwm = self.model.pwm_at(current.row())
        if pwm is None:
            return
        if self.editor.pwm not in (None, pwm) and self.editor.dirty:
            previous = self.editor.pwm
            if not self._confirm_draft():
                self.table.selectionModel().blockSignals(True)
                self.table.selectRow(self.model.row_for(previous))
                self.table.selectionModel().blockSignals(False)
                return
            self.editor.dirty = False
        self._selected_pwm = pwm
        self.table.selectionModel().blockSignals(True)
        self.table.selectRow(self.model.row_for(pwm))
        self.table.selectionModel().blockSignals(False)
        self._load_editor(pwm)

    def _load_editor(self, pwm: int) -> None:
        index = self.model.row_for(pwm)
        if index < 0:
            return
        row = self.model.rows[index]
        self.editor.load(pwm, row["entry"], row["label"] or _header_text(pwm))
        self.editor.set_live(row["fan"], row["status"])
        writable = bool(row["fan"].get("pwm_writable") or row["fan"].get("pwm_root_writable"))
        editable = not self._fan_external() and self._channels_service is not None
        self.editor.setEnabled(editable)
        self.editor.feedback.setEnabled(editable and not self._busy)
        self.editor.retry = pwm in self._pending_channels
        self.editor.resume = row["status"].get("state") == "override"
        self.editor._sync_actions()
        if self._fan_external():
            note = tr("The fan is handed to another program. Take control back on the Fans page first.")
        elif not writable:
            note = tr("This channel is read-only until the PWM driver is prepared.")
        elif not self._system_fan_control.get("enabled") and self.editor.mode.currentData() in {"curve", "mix"}:
            note = tr("Curves are followed by control from boot. Without it, only the desktop follows one curve, after you log in.")
        else:
            note = ""
        self.editor.set_note(note)

    def _render_status(self) -> None:
        snapshot = self._system_fan_control or {}
        enabled = bool(snapshot.get("enabled"))
        available = bool(snapshot.get("available"))
        state = str(snapshot.get("state") or "")
        desktop = self._desktop_fan_policy()
        out_of_date = board_view.service_out_of_date(snapshot, desktop)
        if self._busy:
            text, tone = tr("Applying selected action…"), "blue"
        elif self._system_fan_busy:
            text, tone = tr("Waiting for the administrator password…"), "blue"
        elif self._background.is_running("fan-system-sync"):
            text, tone = tr("Applying selected action…"), "blue"
        else:
            template, values, tone = board_view.service_summary(
                snapshot, desktop, sync_error=self._system_fan_sync_error)
            text = tr_format(template, **values) if values else tr(template)
        self.status_line.setText(text)
        _restyle(self.status_line, "tone", tone)
        self.sync_button.setVisible(enabled and (out_of_date or state == "override" or bool(self._system_fan_sync_error)) and not self._system_fan_busy)
        self.boot_switch.blockSignals(True)
        self.boot_switch.setChecked(enabled)
        self.boot_switch.blockSignals(False)
        self.boot_switch.setEnabled(
            not self._system_fan_busy and (enabled or available) and not snapshot.get("external")
        )

    def _render_driver_notice(self) -> None:
        if not self.current_state:
            self.driver_notice.hide()
            return
        sensors = _dict(self.current_state.get("sensores"))
        if not sensors.get("chip"):
            text = tr("No NCT fan controller was found. Prepare the PWM driver to read and control the fans.")
        elif not self._fan_control_available():
            text = tr("The fans are shown read-only. Prepare the nct6687 PWM driver to control them.")
        else:
            self.driver_notice.hide()
            return
        self.driver_text.setText(text)
        self.driver_button.setEnabled(not self._busy)
        self.driver_notice.show()

    def _render_footer(self, rows: list[dict]) -> None:
        sensors = _dict(self.current_state.get("sensores"))
        controlled = sum(1 for row in rows if row["entry"].get("mode") != "firmware")
        spinning = sum(1 for row in rows if _integer(row["fan"].get("rpm")) > 0)
        parts = [
            tr_format("{count} channels", count=len(rows)),
            tr_format("{count} turning", count=spinning),
            tr_format("{count} controlled", count=controlled),
        ]
        if sensors.get("chip"):
            modules = _dict(self.current_state.get("modulos"))
            driver = "nct6687" if modules.get("nct6687") else "nct6683" if modules.get("nct6683") else ""
            parts.append(" ".join(part for part in (str(sensors.get("chip")), driver) if part))
        self.footer.setText(" · ".join(parts))

    def _profile_choice_changed(self, _index) -> None:
        self._profile_selection_pending = True
        self.profile_apply.setEnabled(bool(self.profile_combo.currentData()) and self._channels_service is not None and not self._fan_external())

    def _render_profiles(self) -> None:
        board = self._board
        current = self.profile_combo.currentData()
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        custom = bool(board and board.channels and not board.active_mode)
        if custom:
            self.profile_combo.addItem(tr("Custom"), "")
        for label in BUILTIN_MODE_NAMES.values():
            self.profile_combo.addItem(tr(label), label)
        for mode in (board.modes if board else []):
            self.profile_combo.addItem(mode["name"], mode["name"])
        active = board.active_mode if board else ""
        selected = current if self._profile_selection_pending else active or ("" if custom else "Balanced")
        _set_combo(self.profile_combo, selected or ("" if custom else "Balanced"))
        self.profile_combo.blockSignals(False)
        usable = self._channels_service is not None and not self._fan_external() and not self._busy
        for widget in (self.profile_combo, self.profile_apply, self.profile_save):
            widget.setEnabled(usable)
        self.profile_apply.setEnabled(usable and bool(self.profile_combo.currentData()))

    # ----------------------------------------------------------- changes

    def _needs_service_notice(self) -> str:
        return ("Several fans need control from boot" if self._board and self._board.needs_root_service
                else "Only the desktop follows the curve, and only after you log in.")

    def _policy_supported(self, policy: dict | None) -> bool:
        if board_view.policy_supported(self._system_fan_control, policy):
            return True
        self._show_info("PWM control is not ready", "Update fan helper", tone="orange")
        return False

    def _apply_channel(self, pwm: int, entry: dict | None) -> bool:
        if self._busy or self._channels_service is None or self._fan_external():
            return False
        service_on = bool(self._system_fan_control.get("enabled"))
        mode = (entry or {}).get("mode", "firmware")
        if not service_on and mode in {"fixed", "firmware"}:
            # Written right now, through the helper: only on a header that is
            # there and writable (Codex review of the redesign).
            fan = self._fan_rows().get(pwm, {})
            writable = bool(fan.get("pwm_writable") or fan.get("pwm_root_writable"))
            if not self.current_state.get("driver_control") or not fan.get("pwm_path") or not writable:
                self.editor.set_note(tr("This channel is read-only until the PWM driver is prepared."))
                return False
        if not service_on and mode == "fixed" and entry["percent"] < LOW_DUTY_CONFIRM_PERCENT:
            dialog = ConfirmDialog(
                "Apply a low fan speed",
                "A fan this slow can let the board overheat under load.",
                confirm_text="Apply",
                tone="orange",
                parent=self,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return False
        try:
            if service_on and not self._policy_supported(self._channels_service.preview_channel(pwm, entry)):
                return False
            self._board = self._channels_service.set_channel(pwm, entry)
        except ValueError as error:
            self._show_error("Could not save fan curve", str(error))
            return False
        self._profile_selection_pending = False
        self.editor.accept_saved(entry)
        self._fan_root_config = self._read_config()
        self._record_event("info", "Fan setting saved", f"PWM {pwm}: {mode}")
        if service_on:
            self._sync_system_fan_policy(force=True, clear=self._desktop_fan_policy() is None, notify=tr_format("PWM {pwm}", pwm=pwm))
        elif mode == "fixed":
            self._write_now(pwm, entry["percent"])
        elif mode == "firmware":
            self._restore_now(pwm)
        else:
            self._show_info("Saved", self._needs_service_notice(), tone="orange")
        self._render()
        return True

    def _rename_channel(self, pwm: int, label: str) -> None:
        if self._channels_service is None:
            return
        current = self._board.labels.get(str(pwm), "") if self._board else ""
        if label == current:
            return
        self._board = self._channels_service.set_label(pwm, label)
        self._render()

    def _apply_profile(self) -> None:
        name = self.profile_combo.currentData()
        if not name or self._channels_service is None:
            return
        if not self._confirm_draft(discard_only=True):
            return
        targets = self._profile_targets()
        try:
            if self._system_fan_control.get("enabled") and not self._policy_supported(self._channels_service.preview_mode(str(name), targets)):
                return
            self._board = self._channels_service.apply_mode(str(name), targets)
        except ValueError as error:
            # A profile with nothing to drive is a choice still to make, not a
            # hardware failure: a plain notice, never the BC250-FAN-001 dialog.
            if not targets and not (self._board and self._board.channels):
                self._show_info("No PWM channel", "Select a detected PWM channel first.", tone="orange")
            else:
                self._show_info("Could not save fan curve", tr(str(error)), tone="orange")
            return
        self.editor.dirty = False
        self._profile_selection_pending = False
        self._fan_root_config = self._read_config()
        if self._system_fan_control.get("enabled"):
            self._sync_system_fan_policy(force=True, clear=self._desktop_fan_policy() is None, notify=str(name))
        else:
            self._show_info("Saved", self._needs_service_notice(), tone="orange")
        self._render()

    def _profile_targets(self) -> list[int]:
        """Where a built-in profile goes when no channel is configured yet:
        the writable headers with a fan turning, else the selected one."""
        selected = self.editor.pwm if self.editor.pwm is not None else self._selected_pwm
        return board_view.profile_targets(self._fan_rows(), self._channel_numbers(), selected)

    def _save_profile(self) -> None:
        if self._channels_service is None:
            return
        dialog = ProfileNameDialog(self)
        dialog.setWindowTitle(tr("Save as…"))
        dialog.setLabelText(tr("Profile"))
        dialog.setInputMode(QInputDialog.InputMode.TextInput)
        enable_adaptive_dialog(dialog, preferred_width=440, minimum_width=360)
        dialog.setOkButtonText(tr("Save"))
        dialog.setCancelButtonText(tr("Cancel"))
        field = dialog.findChild(QLineEdit)
        if field is not None:
            field.setMaxLength(MODE_NAME_MAX_LENGTH)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name = " ".join(dialog.textValue().split())
        if not name.strip():
            return
        if name.strip().casefold() in {tr(label).casefold() for label in BUILTIN_MODE_NAMES.values()}:
            self._show_info("Could not save fan curve", "Reserved profile name", tone="orange")
            return
        snapshot = None
        if self.editor.dirty:
            if self.editor.validation_error():
                self._show_info("Could not save fan curve", self.editor.validation_error(), tone="orange")
                return
            snapshot = dict(self._board.channels if self._board else {})
            entry = self.editor._normalized(self.editor.entry())
            if entry.get("mode") == "firmware":
                snapshot.pop(str(self.editor.pwm), None)
            else:
                snapshot[str(self.editor.pwm)] = entry
        if self._board and any(m["name"].casefold() == name.strip().casefold() for m in self._board.modes):
            if ConfirmDialog("Save as…", "Replace fan profile?", confirm_text="Save", parent=self).exec() != QDialog.DialogCode.Accepted:
                return
        try:
            self._board = self._channels_service.save_mode(name, channels=snapshot)
        except ValueError as error:
            self._show_error("Could not save fan curve", str(error))
            return
        self._render()
        _set_combo(self.profile_combo, name.strip())
        self._profile_selection_pending = True
        self._show_info("Saved", name.strip(), tone="green")

    def _delete_profile(self) -> None:
        name = self.profile_combo.currentData()
        if not name or self._channels_service is None or name in BUILTIN_MODE_NAMES.values():
            return
        self._board = self._channels_service.delete_mode(str(name))
        self._render()

    # ------------------------------------------------------- calibration

    @staticmethod
    def _calibration_reason(message: str) -> str:
        """Translate fixed calibration copy before inserting error details."""
        head, separator, tail = message.partition("; final write of 100 percent failed: ")
        if separator:
            return (f"{FansPage._calibration_reason(head)}; "
                    f"{FansPage._calibration_reason('final write of 100 percent failed: ' + tail)}")
        for prefix, template in (
            ("calibration failed: ", "calibration failed: {error}"),
            ("final write of 100 percent failed: ", "final write of 100 percent failed: {error}"),
        ):
            if message.startswith(prefix):
                return tr_format(template, error=tr(message[len(prefix):]))
        prefix = "overheating: temperature at or above "
        if message.startswith(prefix) and message.endswith(" C"):
            return tr_format("overheating: temperature at or above {temperature} C",
                             temperature=message[len(prefix):-2])
        return tr(message)

    def _calibrate_channel(self, pwm: int) -> None:
        if self._busy:
            self._calibration_cancel.set()  # the button reads Cancel while it runs
            return
        if self._fan_external() or self._channels_service is None:
            return
        saved = self._board.channels.get(str(pwm), {}) if self._board else {}
        if saved.get("role") == "pump" or (self.editor.pwm == pwm and self.editor.role.currentData() == "pump"):
            self._show_info("Calibration stopped", "pumps are not calibrated: stopping a pump is unsafe", tone="orange")
            return
        fan = self._fan_rows().get(pwm, {})
        hwmon = str(_dict(self.current_state.get("sensores")).get("path") or "")
        if not (fan.get("pwm_writable") or fan.get("pwm_root_writable")) or not hwmon:
            self._show_info("PWM control is not ready",
                            "This channel is read-only until the PWM driver is prepared.", tone="orange")
            return
        dialog = ConfirmDialog(
            "Calibrate this fan",
            "The fan goes to full speed, then down step by step until it stops, then up until it starts "
            "again. It takes one to two minutes and stops at once if the board reaches 80 °C. "
            "It ends at full speed; nothing is saved until you press Apply.",
            summary=(("Channel", f"PWM {pwm} · {_header_text(pwm)}"), ("Hottest allowed", "80 °C")),
            confirm_text="Calibrate",
            tone="orange",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        controller = self.controller
        cancel = self._calibration_cancel
        cancel.clear()

        def write(percent: int) -> None:
            raw = _percent_to_pwm(percent)
            error = self._verify(controller.aplicar_pwm_fan(pwm, raw), pwm=pwm, raw=raw)
            if error:
                raise RuntimeError(error)

        def operation() -> object:
            return calibrate(
                write=write,
                read_rpm=lambda: _read_int(Path(hwmon) / f"fan{pwm}_input"),
                hottest_c=_hottest_temperature,
                sleep=lambda seconds: _wait(seconds, cancel),
                cancelled=cancel.is_set,
            )

        self._busy = True
        self.editor.calibrate_button.setText(tr("Cancel"))
        self.editor.calibrate_button.setToolTip(tr("Cancel calibration"))
        worker = FanTask(operation, self)
        self._worker = worker

        def complete(result) -> None:
            self._finish_calibration()
            if not isinstance(result, CalibrationResult):
                failed(tr("The calibration returned no result."))
                return
            self._record_event("info", "Fan calibrated", f"PWM {pwm}: {result}")
            if result.aborted:
                self._show_info("Calibration stopped", self._calibration_reason(result.aborted), tone="orange")
                return
            if self.editor.pwm == pwm:
                self.editor.propose_calibration(result)
            stop = "—" if result.stop_percent is None else f"{result.stop_percent} %"
            start = "—" if result.start_percent is None else f"{result.start_percent} %"
            self._show_info(
                "Calibration finished",
                tr_format("Keeps turning down to {stop}, starts at {start}. Review the proposal and press Apply.",
                          stop=stop, start=start),
                tone="orange",
            )

        def failed(message: str) -> None:
            self._finish_calibration()
            self._show_error("Calibration stopped", message)

        worker.succeeded.connect(complete)
        worker.failed.connect(failed)
        worker.finished.connect(self._worker_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _finish_calibration(self) -> None:
        self._busy = False
        self.editor.calibrate_button.setText(tr("Calibrate"))
        self.editor.calibrate_button.setToolTip(tr(
            "Measures the lowest PWM at which this fan keeps turning and the one at which it starts, "
            "and proposes them as its minimum and spin-up kick."
        ))
        self._state_cache.invalidate("fans")
        self.refresh()

    def _write_now(self, pwm: int, percent: int) -> None:
        """Service off: write a fixed duty now, through the verified helper."""
        raw = _percent_to_pwm(percent)
        self._run_task(
            lambda: self.controller.aplicar_pwm_fan(pwm, raw),
            lambda result: self._verify(result, pwm=pwm, raw=raw),
            "Fan speed applied", tr_format("PWM {pwm} · {percent}%", pwm=pwm, percent=percent), pwm=pwm,
        )

    def _restore_now(self, pwm: int) -> None:
        self._run_task(
            lambda: self.controller.restaurar_pwm_automatico(pwm),
            lambda result: self._verify(result, pwm=pwm, automatic=True),
            "Automatic fan control restored", tr_format("PWM {pwm}", pwm=pwm), pwm=pwm,
        )

    def _run_task(self, operation, verify, title: str, detail: str, *, pwm: int | None = None) -> None:
        if self._busy:
            return
        self._busy = True
        worker = FanTask(operation, self)
        self._worker = worker

        def complete(result) -> None:
            error = verify(result)
            if error:
                failed(error)
                return
            self._busy = False
            if pwm is not None:
                self._pending_channels.discard(pwm)
                self._verified_channels.add(pwm)
            self._render()
            self._record_event("info", title, detail)
            self._state_cache.invalidate("fans")
            self.refresh()
            self._show_info(title, detail, tone="blue")

        def failed(message: str) -> None:
            self._busy = False
            if pwm is not None:
                self._pending_channels.add(pwm)
                self._verified_channels.discard(pwm)
            self._render()
            self._record_event("error", "Fan PWM operation failed", message)
            self._show_error("Fan PWM operation failed", message)

        worker.succeeded.connect(complete)
        worker.failed.connect(failed)
        worker.finished.connect(self._worker_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _worker_finished(self) -> None:
        self._worker = None

    @staticmethod
    def _verify(result: object, *, pwm: int, raw: int | None = None, automatic: bool = False) -> str:
        """A helper acknowledgement without the promised read-back is a failure."""
        template, values = board_view.verify_pwm_result(result, pwm=pwm, raw=raw, automatic=automatic)
        return tr_format(template, **values) if template else ""

    # ------------------------------------------------- root service policy

    def _toggle_system_control(self) -> None:
        if self._system_fan_busy:
            self._render_status()
            return
        enabled = bool(self._system_fan_control.get("enabled"))
        if enabled:
            dialog = ConfirmDialog(
                "Turn off control from boot",
                "The system service stops and the fan returns to firmware control. The desktop daemon follows the curve again after login, and may ask for a password once per session.",
                confirm_text="Turn off",
                tone="orange",
                parent=self,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                self._render_status()
                return
            operation = self.controller.desactivar_control_fan_sistema
            done = ("Control from boot is off",
                    "The fan is back under firmware control until the desktop applies the curve.")
        else:
            policy = self._desktop_fan_policy()
            if policy is None:
                self._show_info(
                    "Choose a curve or a preset first",
                    "Enable the automatic curve or apply a named preset, then turn on control from boot.",
                    tone="orange",
                )
                self._render_status()
                return
            if not self._policy_supported(policy):
                self._render_status()
                return
            overview = policy_overview(policy)
            follows = (tr_format("Curve with {count} points", count=overview["points"])
                       if overview["mode"] in ("curve", "mix")
                       else tr_format("Preset · {percent}%", percent=overview["percent"]))
            dialog = ConfirmDialog(
                "Turn on control from boot",
                "A root service installed by BC250 Control Center will follow this setting from every boot. The administrator password is asked once now.",
                summary=(
                    ("Channel", overview["channels_text"]),
                    ("Follows", follows),
                    ("Critical response", tr_format("{percent}% duty", percent=100)),
                ),
                confirm_text="Turn on",
                tone="blue",
                parent=self,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                self._render_status()
                return

            def operation() -> object:
                return self.controller.activar_control_fan_sistema(policy)

            done = ("Control from boot is on",
                    "The system service now follows this setting and will do so from the next boot, without asking for a password.")
        self._system_fan_busy = True
        self._system_fan_sync_error = ""
        self._render_status()

        def success(_result: object) -> None:
            self._system_fan_busy = False
            self._record_event("info", *done)
            self.refresh()
            self._show_info(*done, tone="blue")

        def failure(message: str) -> None:
            self._system_fan_busy = False
            self._render_status()
            self._record_event("error", "System fan control failed", message)
            self._show_error("System fan control failed", message)

        self._background.start("fan-system-control", operation, success, failure)

    def _sync_system_fan_policy(self, *, force: bool = False, clear: bool = False, notify: str = "") -> None:
        """Hand the saved channels to the root service, when it is on."""
        if not self._system_fan_control.get("enabled") or self._system_fan_busy or self._fan_external():
            return
        policy = None if clear else self._desktop_fan_policy()
        if policy is None and not clear:
            return
        if (
            not force and policy is not None
            and self._system_fan_control.get("policy_digest") == policy_digest(policy)
            and self._system_fan_control.get("state") != "override"
        ):
            return
        if self._background.is_running("fan-system-sync"):
            # A newer change arrived while the last one is on its way: send
            # the newest policy as soon as that one is done.
            self._fan_sync_pending = True
            self._fan_sync_pending_notice = notify
            return

        def operation() -> object:
            return self.controller.sincronizar_control_fan_sistema(policy)

        def resend_if_pending() -> None:
            if self._fan_sync_pending:
                self._fan_sync_pending = False
                notice, self._fan_sync_pending_notice = self._fan_sync_pending_notice, ""
                self._sync_system_fan_policy(force=True, clear=self._desktop_fan_policy() is None, notify=notice)

        def success(_result: object) -> None:
            self._system_fan_sync_error = ""
            self._pending_channels.clear()
            self._render()
            if notify and not self._fan_sync_pending:
                self._show_info("Saved", notify, tone="blue")
            self.refresh()

        def failure(message: str) -> None:
            self._system_fan_sync_error = tr(str(message))
            if policy:
                self._pending_channels.update(engine.controlled_channels(policy))
            self._render()

        def finished() -> None:
            resend_if_pending()
            self._render()

        self._background.start("fan-system-sync", operation, success, failure, finished)

    # -------------------------------------------------------- hand-off

    def _toggle_external_control(self) -> None:
        if self._busy or self._system_fan_busy:
            return
        external = self._fan_external()
        managers = self._fan_managers()
        program = ", ".join(managers) if managers else tr("the other program")
        if external:
            flag = False
            done = ("BC250 Control Center controls the fan again",
                    "The fan keeps the speed the other program left. Apply a speed, a curve "
                    "or Return to BIOS control when you want to change it. Stop the other "
                    "program first, or the two will fight over the fan.")
        else:
            dialog = ConfirmDialog(
                "Hand off the fan",
                "BC250 Control Center stops writing to the fan: no speed, curve, preset, "
                "Quick Access change or control from boot, and nothing at the next boot. "
                "The fan driver stays loaded, so the other program keeps working. "
                "Speeds and temperatures are still shown here.",
                summary=(("Other program", program), ("Fan right now", tr("Unchanged"))),
                confirm_text="Hand off",
                tone="blue",
                parent=self,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            flag = True
            done = ("The fan is handed to another program",
                    tr_format("{program} controls the fan now. BC250 Control Center only reads its speed and temperatures.",
                              program=program))
        settings = self.settings_service
        channels = dict(self._fan_root_config.get("fan_channels") or {})
        curve = {**_dict(self._fan_root_config.get("fan_curve")), "enabled": False}
        preset = {**_dict(self._fan_root_config.get("fan_preset")), "enabled": False}

        def operation() -> object:
            result = self.controller.ceder_fan_a_otro_programa(flag)
            if flag and settings is not None:
                # Nothing may re-apply these when the fan is taken back; they
                # stay recoverable under fan_channels_before_handoff.
                updates = {"fan_curve": curve, "fan_preset": preset}
                if channels:
                    updates.update({"fan_channels": {}, "fan_active_mode": "",
                                    "fan_channels_before_handoff": channels})
                settings.save_local_config(updates)
            return result

        self._system_fan_busy = True
        self._render_status()

        def success(_result: object) -> None:
            self._system_fan_busy = False
            self._system_fan_control = {**self._system_fan_control, "external": flag}
            self._reload_fan_config()
            self._record_event("info", done[0], done[1])
            self._state_cache.invalidate("fans", "config")
            self.refresh()
            self._show_info(done[0], done[1], tone="blue")

        def failure(message: str) -> None:
            self._system_fan_busy = False
            self._render_status()
            self._record_event("error", "Fan hand-off failed", message)
            self._show_error("Fan hand-off failed", message)

        if not self._background.start("fan-external-control", operation, success, failure):
            self._system_fan_busy = False
            self._render_status()

    # ------------------------------------------------------------ More

    def _show_more_menu(self) -> None:
        self._fill_more_menu()
        self.more_menu.popup(self.more_button.mapToGlobal(self.more_button.rect().bottomLeft()))

    def _fill_more_menu(self) -> None:
        menu = self.more_menu
        menu.clear()
        menu.addAction(tr("Export fan profiles"), self.export_profiles_to_file)
        menu.addAction(tr("Import fan profiles"), self.import_profiles_from_file)
        menu.addAction(tr("Export to Decky"), self.export_profiles_to_decky)
        saved = self.profile_combo.currentData()
        if self.profile_save.isHidden():
            menu.addAction(tr("Save as…"), self._save_profile)
        delete = menu.addAction(tr("Delete"), self._delete_profile)
        delete.setEnabled(bool(saved) and saved not in BUILTIN_MODE_NAMES.values())
        menu.addSeparator()
        diagnostics = menu.addMenu(tr("Diagnostics"))
        diagnostics.addAction(tr("Prepare PWM driver"), lambda: self.prepare_pwm_driver())
        diagnostics.addAction(tr("Enable read-only NCT monitoring"), self.enable_read_only)
        diagnostics.addAction(tr("Disable nct6687 PWM setup"), self.disable_pwm_setup)
        diagnostics.addAction(tr("PWM paths"), self.show_pwm_paths)
        diagnostics.addAction(tr("NCT fan controller status"), self.show_raw_status)
        menu.addSeparator()
        menu.addAction(
            tr("Take control back" if self._fan_external() else "Hand off the fan"),
            self._toggle_external_control,
        )

    def _profiles_for_exchange(self) -> list[dict]:
        return [
            {"key": profile.key, "name": profile.name, "percent": int(profile.percent)}
            for profile in load_fan_profiles()
        ]

    def export_profiles_to_decky(self) -> None:
        """Publish the three fixed profiles as Decky's Quiet/Balanced/Boost presets."""
        profiles = self._profiles_for_exchange()
        payload = decky_fan_profiles(profiles)
        raised = [(tr(name), requested, published) for name, requested, published in decky_fan_raised(profiles)]

        def done(plugin_installed: object) -> None:
            self._record_event("info", "Fan profiles exported to Decky", ", ".join(
                f"{entry['name']} {entry['percent']}%" for entry in payload
            ))
            installed = plugin_installed if isinstance(plugin_installed, bool) else None
            self._show_info(tr("Export to Decky"), export_message(installed, fan_export_notes(raised)),
                            tone=export_tone(installed))

        def failed(message: str) -> None:
            self._show_error("Could not export profiles to Decky", message)

        self._background.start(
            "fan-export-decky",
            lambda: export_and_check_plugin(
                self.controller, lambda: self.controller.exportar_perfiles_fan_decky(payload)
            ),
            done,
            failed,
        )

    def export_profiles_to_file(self) -> None:
        path, _pattern = QFileDialog.getSaveFileName(
            self, tr("Export fan profiles"), str(Path.home() / "bc250-fan-profiles.json"),
            tr("Fan profiles (*.json)"),
        )
        if not path:
            return
        document = channel_profiles_document(self._profiles_for_exchange(), self._read_config())
        try:
            Path(path).write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except OSError as error:
            self._show_error("Could not export fan profiles", str(error))
            return
        self._show_info("Fan profiles exported", Path(path).name, tone="green")

    def import_profiles_from_file(self) -> None:
        path, _pattern = QFileDialog.getOpenFileName(
            self, tr("Import fan profiles"), str(Path.home()), tr("Fan profiles (*.json)"),
        )
        if path:
            self._import_profiles(Path(path))

    def _import_profiles(self, path: Path) -> None:
        """Import snapshots and speed slots without changing the active policy."""
        try:
            with path.open("rb") as stream:
                raw = stream.read(MAX_DOCUMENT_BYTES + 1)
            if len(raw) > MAX_DOCUMENT_BYTES:
                raise ValueError(tr("This file is too large to be a fan profile export."))
            bundle = parse_channel_profiles_document(json.loads(raw.decode("utf-8")))
            updates = imported_profile_updates(self._read_config(), bundle, snapshot_name=tr("Imported configuration"))
        except (OSError, UnicodeError, ValueError) as error:
            self._show_error("Could not import fan profiles", tr(str(error)))
            return
        reserved = {tr(label).casefold() for label in BUILTIN_MODE_NAMES.values()}
        if any(m["name"].casefold() in reserved for m in updates["fan_modes"]):
            self._show_info("Could not import fan profiles", "Reserved profile name", tone="orange")
            return
        existing = {m["name"].casefold(): m for m in (self._board.modes if self._board else [])}
        if any(m["name"].casefold() in existing and m != existing[m["name"].casefold()] for m in updates["fan_modes"]):
            if ConfirmDialog("Import fan profiles", "Replace fan profile?", confirm_text="Confirm", parent=self).exec() != QDialog.DialogCode.Accepted:
                return
        if self.settings_service is not None:
            self.settings_service.save_local_config(updates)
        by_key = {entry["key"]: entry for entry in bundle["profiles"]}
        for index, profile in enumerate(load_fan_profiles()):
            entry = by_key.get(profile.key)
            if entry is None:
                continue
            name = shipped_name(entry["name"], DEFAULT_FAN_PROFILES[index].name)
            save_fan_profile(index, type(profile)(profile.key, name, int(entry["percent"])))
        self.editor.refresh_presets()
        self._reload_fan_config()
        self._record_event("info", "Fan profiles imported", path.name)
        self._show_info(
            "Fan profiles imported",
            "Nothing was applied to the fan. Choose a profile or turn on the curve to use them.",
            tone="green",
        )

    # --------------------------------------------------------- driver

    def _run_driver_action(self, operation, on_success, error_title: str, *, error_parent=None) -> None:
        self._busy = True
        self.driver_button.setEnabled(False)

        def success(result: object) -> None:
            on_success(result)
            self._state_cache.invalidate("fans", "tools", "config")
            self.refresh()

        def failure(message: str) -> None:
            self._show_error(error_title, message, parent=error_parent)

        def finished() -> None:
            self._busy = False
            self.driver_button.setEnabled(True)

        if not self._background.start("fan-driver-action", operation, success, failure, finished):
            finished()

    def prepare_pwm_driver(self, *, dialog_parent: QWidget | None = None) -> None:
        dialog = ConfirmDialog(
            "Prepare nct6687 PWM control",
            "The distribution-specific workflow checks that the installed kernel headers match the active kernel before compiling nct6687. It may try to install the exact headers package, but it will stop safely if only headers for another kernel are available. A reboot may be required after a system or kernel update.",
            summary=(
                ("Purpose", "Writable NCT PWM channels"),
                ("Kernel/header safety", "Exact match with uname -r required"),
                ("Authentication", "Visible terminal and sudo, once"),
                ("Monitoring fallback", "nct6683 remains available as read-only mode"),
                ("Boot behavior", "The last PWM duty is restored automatically, no password"),
            ),
            confirm_text="Open preparation workflow",
            tone="orange",
            parent=dialog_parent or self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def success(_result: object) -> None:
            self._record_event("warning", "Fan PWM setup opened", "Distribution-specific nct6687 preparation workflow started.")
            self._show_info(
                "PWM preparation opened",
                "Complete the visible terminal workflow. Reboot if requested, then return here and refresh the fan page.",
                tone="orange", parent=dialog_parent, modal=False,
            )

        self._run_driver_action(self.controller.preparar_nct6687_control_pwm, success,
                                "PWM preparation failed", error_parent=dialog_parent)

    def enable_read_only(self) -> None:
        dialog = ConfirmDialog(
            "Enable read-only NCT monitoring",
            "The application will configure nct6683 for temperatures and RPM monitoring only. Writable PWM control will not be available in this mode.",
            summary=(("Module", "nct6683 force=true"), ("Capability", "Sensors and fan RPM"), ("PWM writes", "Disabled")),
            confirm_text="Open read-only setup",
            tone="blue",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_driver_action(
            self.controller.cargar_nct6683_solo_lectura,
            lambda _r: self._record_event("info", "Fan read-only setup opened", "nct6683 monitoring workflow started."),
            "Read-only setup failed",
        )

    def disable_pwm_setup(self) -> None:
        dialog = ConfirmDialog(
            "Disable nct6687 PWM setup",
            "Boot preference files and the nct6687 load service will be removed, then the system will return to nct6683 read-only monitoring. The installed package is not uninstalled.",
            summary=(("PWM control", "Disabled"), ("Read-only monitoring", "Restored"),
                     ("Package files", "Retained"), ("Reboot", "May be required")),
            confirm_text="Disable PWM setup",
            tone="red",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_driver_action(
            self.controller.desactivar_nct6687_control_pwm,
            lambda _r: self._record_event("warning", "Fan PWM setup disabled", "nct6687 boot preference removal workflow started."),
            "Could not disable PWM setup",
        )

    def show_pwm_paths(self) -> None:
        PwmPathsDialog(self.current_state, self).exec()

    def show_raw_status(self) -> None:
        sensors = _dict(self.current_state.get("sensores"))
        modules = _dict(self.current_state.get("modulos"))
        lines = "\n".join(
            f"PWM {fan.get('index')}: {fan.get('label')} · {fan.get('rpm') or '--'} RPM · {fan.get('pwm_path') or '--'}"
            for fan in self._visible_fans()
        ) or "No visible channels detected."
        text = (
            f"Chip: {sensors.get('chip') or '--'}\n"
            f"Hwmon: {sensors.get('path') or '--'}\n"
            f"Modules: nct6683={bool(modules.get('nct6683'))} · nct6687={bool(modules.get('nct6687'))}\n"
            f"PWM control: {'available' if self._fan_control_available() else 'read only / unavailable'}\n\n"
            f"{lines}\n\n{self.current_state.get('resumen') or 'No repository summary available.'}"
        )
        self._show_info("NCT fan controller status", text, tone="blue", modal=True)

    # -------------------------------------------------------- feedback

    def _record_event(self, level: str, title: str, detail: str) -> None:
        self._event_sequence += 1
        service = self.activity_service

        def operation() -> object:
            if service is None:
                raise RuntimeError("FansPage requires an activity service to record events")
            service.record("fan", level, title, detail, {})
            return True

        self._background.start(f"fan-event:{self._event_sequence}", operation)

    def _show_info(self, title: str, message: str, *, tone: str = "blue",
                   parent: QWidget | None = None, modal: bool | None = None) -> None:
        if not (tone in {"orange", "red"} if modal is None else modal):
            show_toast(parent or self, title, message, tone=tone)
            return
        InfoDialog(
            title, message,
            icon_name="warning_orange" if tone in {"orange", "red"} else "info_blue",
            parent=parent or self,
            button_text="Close",
            tone=tone,
        ).exec()

    def _show_error(self, title: str, message: str, *, parent: QWidget | None = None) -> None:
        self._show_info(title, message, tone="red", parent=parent)
