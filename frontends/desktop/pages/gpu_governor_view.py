"""Redesigned GPU module — presentation layer (PyQt6).

Destination: ``frontends/desktop/pages/gpu_governor_view.py``

Rebuilds the governor screen with the approved mockup hierarchy:

    ┌ GPU configuration ─────────────────┐ ┌ Live telemetry ─────────┐
    │ safe-mode notice                   │ │ 6 read-only tiles       │
    │ operating profile (3 cards)        │ │ Governor service        │
    │ frequency range (safe-points)      │ │ Voltage laboratory      │
    │ Cyan kernel compatibility          │ │ Danger zone (+2000)     │
    │ Review and apply range             │ └─────────────────────────┘
    └─────────────────────────────────────┘
    ┌ Advanced GPU diagnostics (collapsible) ────────────────────────┐
    │ safe-point table + contract       │  console (tall column)     │
    └───────────────────────────────────────────────────────────────┘

Does not talk to D-Bus or the controller: it exposes signals and receives
state. The wiring lives in ``gpu_governor_integration.py``.

Only mounted for the Cyan backend; an Oberon board keeps the original
screen (``gpu_governor.py``) untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable, Sequence

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from bc250cc.domain.gpu.oberon import OBERON_REFERENCE_VOLTAGE_MV

from ..components.busy_spinner import BusyBadge
from ..components.buttons import WrappingButton as QPushButton
from ..components.card_navigation import EditableCardNavigation
from ..components.page_widgets import (
    ConfirmDialog,
    MetricTile,
    SectionCard,
    caption,
    subpanel,
)
from ..components.widgets import PillLabel, icon
from ..i18n import governor_fix_label, tr, tr_format
from ..theme import COLORS

# ─────────────────────────────────────────────────────────────────────────────
# Safe-points — mirrors /etc/cyan-skillfish-governor-smu/config.toml
# ─────────────────────────────────────────────────────────────────────────────

#: ``[[safe-points]]`` blocks active in the factory TOML.
SAFE_POINTS: tuple[tuple[int, int], ...] = (
    (500, 700),
    (1000, 800),
    (1175, 850),
    (1500, 900),
    (1600, 910),
    (1700, 920),
    (1850, 930),
    (2000, 960),
)

#: Commented-out blocks. ``alternar_puntos_gpu_altos(True)`` uncomments them.
EXTRA_POINTS: tuple[tuple[int, int], ...] = (
    (2050, 980),
    (2100, 1000),
    (2125, 1020),
    (2150, 1035),
    (2200, 1050),
    (2230, 1085),
    (2300, 1110),
    (2350, 1130),
    (2400, 1150),
)

SAFE_CEILING = SAFE_POINTS[-1][0]        # 2000 — ceiling with the factory TOML
ABSOLUTE_CEILING = EXTRA_POINTS[-1][0]   # 2400 — ceiling with points uncommented
FLOOR = SAFE_POINTS[0][0]                # 500

ALL_POINTS: tuple[int, ...] = tuple(
    frequency for frequency, _voltage in SAFE_POINTS + EXTRA_POINTS
)
VOLTAGE_MAP: dict[int, int] = dict(SAFE_POINTS + EXTRA_POINTS)


def ceiling_for(*, unlocked: bool) -> int:
    return ABSOLUTE_CEILING if unlocked else SAFE_CEILING


def offered_points(*, unlocked: bool) -> list[int]:
    return [point for point in ALL_POINTS if point <= ceiling_for(unlocked=unlocked)]


def voltage_for(frequency: int) -> int:
    """Voltage of the nearest safe-point."""
    nearest = min(VOLTAGE_MAP, key=lambda point: abs(point - frequency))
    return VOLTAGE_MAP[nearest]


def backend_voltage_for(frequency: int, *, is_oberon: bool = False) -> int:
    """Oberon's endpoints are flat; only Cyan has a per-frequency curve.

    Deriving an Oberon voltage from Cyan's multipoint TOML would print a
    number this board never uses — the exact mistake ``domain/gpu/oberon.py``
    exists to prevent.
    """
    return OBERON_REFERENCE_VOLTAGE_MV if is_oberon else voltage_for(frequency)


def snap_to_point(frequency: int, *, unlocked: bool = False) -> int:
    pool = offered_points(unlocked=unlocked)
    return min(pool, key=lambda point: abs(point - frequency))


def temperature_detail(value: float) -> str:
    """Tile caption for the temperature reading.

    The mockup labels it ``Normal · hwmon``.  The bands are the ones the legacy
    screen already uses (``_temperature_status``) so the two never disagree.
    Whole phrases are translated rather than the bare adjective: "Normal" alone
    is already catalogued for an unrelated, differently-inflected context.
    """
    if value <= 0:
        return tr("hwmon")
    if value < 75:
        return tr("Normal · hwmon")
    if value < 85:
        return tr("Warm · hwmon")
    return tr("High · hwmon")


@dataclass
class GpuProfile:
    """Editable operating profile: name + range."""

    key: str
    name: str
    minimum: int
    maximum: int

    #: Set for Oberon profiles, whose endpoints share one flat voltage.
    fixed_voltage: int | None = None

    @property
    def voltage(self) -> int:
        if self.fixed_voltage is not None:
            return int(self.fixed_voltage)
        return voltage_for(self.maximum)

    def is_risky(self) -> bool:
        return self.maximum > SAFE_CEILING

    def summary(self) -> str:
        return f"{self.minimum} – {self.maximum} MHz"


DEFAULT_PROFILES: tuple[GpuProfile, ...] = (
    GpuProfile("balanced", "Balanced", 500, 1500),
    GpuProfile("gaming", "Gaming", 1000, 1850),
    GpuProfile("benchmark", "Benchmark", 1000, 2000),
)


# ─────────────────────────────────────────────────────────────────────────────
# Style helpers — everything from theme.COLORS
# ─────────────────────────────────────────────────────────────────────────────

def _accent_soft() -> str:
    return COLORS["blue_soft"]


def _qcolor(key: str, alpha: int = 255) -> QColor:
    color = QColor(COLORS[key])
    color.setAlpha(alpha)
    return color


#: Both redesigned modules draw the same panels, so the primitives live in
#: ``components.page_widgets``. These aliases keep this file's call sites.
_caption = caption
_subpanel = subpanel


# ─────────────────────────────────────────────────────────────────────────────
# Check row — drawn here so light and dark builds stay identical
# ─────────────────────────────────────────────────────────────────────────────

class CheckRow(QAbstractButton):
    """A check box painted by the widget itself.

    ``QCheckBox::indicator`` is rendered by the platform style, so on some
    desktops the box borrows the system theme instead of the application's and
    light and dark builds stop matching.  A stylesheet fill fixes the colour
    but leaves a flat square with no tick.  Painting it here settles both: one
    look in every theme, and a tick that follows the active accent.
    """

    BOX = 16
    GAP = 9

    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setText(text)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt)
        metrics = self.fontMetrics()
        return QSize(
            self.BOX + self.GAP + metrics.horizontalAdvance(self.text()) + 2,
            max(self.BOX + 4, metrics.height() + 6),
        )

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(0.5, (self.height() - self.BOX) / 2.0, self.BOX, self.BOX)

        if self.isChecked():
            painter.setPen(QPen(_qcolor("blue"), 1.4))
            painter.setBrush(_qcolor("blue"))
        else:
            painter.setPen(QPen(_qcolor("border_strong"), 1.4))
            painter.setBrush(
                _qcolor("control_hover") if self.underMouse() else _qcolor("control")
            )
        painter.drawRoundedRect(box, 5, 5)

        if self.isChecked():
            tick = QPainterPath()
            tick.moveTo(box.left() + box.width() * 0.26, box.top() + box.height() * 0.52)
            tick.lineTo(box.left() + box.width() * 0.43, box.top() + box.height() * 0.70)
            tick.lineTo(box.left() + box.width() * 0.76, box.top() + box.height() * 0.32)
            pen = QPen(_qcolor("on_blue"), 2.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(tick)

        painter.setPen(_qcolor("text"))
        left = self.BOX + self.GAP
        painter.drawText(
            QRectF(left, 0, max(1.0, self.width() - left), self.height()),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            self.text(),
        )
        painter.end()

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().leaveEvent(event)
        self.update()


# ─────────────────────────────────────────────────────────────────────────────
# Picker row — the mockup's boxed ``caption ......... value`` selector
# ─────────────────────────────────────────────────────────────────────────────

class PickerRow(QFrame):
    """A boxed row that reads ``caption ... value`` and opens its options.

    The mockup draws these two selectors with the caption on the left and the
    current value on the right, without a drop-down arrow.  A ``QComboBox``
    cannot render two independently styled halves, so this reimplements just
    enough of its API (``addItem``/``findData``/``setCurrentIndex``/
    ``currentData``/``currentIndexChanged``) for the existing wiring to keep
    working unchanged.
    """

    currentIndexChanged = pyqtSignal(int)  # noqa: N815 (QComboBox-compatible)

    def __init__(self, caption: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._caption_source = caption
        self._items: list[tuple[str, str]] = []
        self._index = -1
        self.setProperty("pickerRow", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 9, 12, 9)
        row.setSpacing(10)
        self._caption = QLabel(tr(caption))
        self._caption.setProperty("pickerCaption", True)
        self._caption.setMinimumWidth(0)
        row.addWidget(self._caption, 1)
        self._value = QLabel("")
        self._value.setProperty("pickerValue", True)
        self._value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        row.addWidget(self._value, 0)

    # -- QComboBox-compatible surface ---------------------------------------
    def addItem(self, text: str, data: str) -> None:  # noqa: N802 (Qt naming)
        self._items.append((text, data))
        if self._index < 0:
            self.setCurrentIndex(0)

    def findData(self, data: object) -> int:  # noqa: N802 (Qt naming)
        for index, (_text, value) in enumerate(self._items):
            if value == data:
                return index
        return -1

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802 (Qt naming)
        if not self._items:
            return
        index = max(0, min(len(self._items) - 1, int(index)))
        changed = index != self._index
        self._index = index
        self._value.setText(self._items[index][0])
        if changed and not self.signalsBlocked():
            self.currentIndexChanged.emit(index)

    def currentData(self) -> object:  # noqa: N802 (Qt naming)
        if 0 <= self._index < len(self._items):
            return self._items[self._index][1]
        return None

    def retranslate(self) -> None:
        self._caption.setText(tr(self._caption_source))

    # -- interaction ---------------------------------------------------------
    def open_options(self) -> None:
        """Show the choices. Reached by a click, a controller, or Enter."""
        if not self._items:
            return
        menu = QMenu(self)
        for index, (text, _data) in enumerate(self._items):
            action = menu.addAction(text)
            action.setCheckable(True)
            action.setChecked(index == self._index)
            action.triggered.connect(
                lambda _checked=False, position=index: self.setCurrentIndex(position)
            )
        menu.exec(self.mapToGlobal(self.rect().bottomLeft()))

    def gamepad_activate(self) -> None:
        """A controller press must reach the same list.

        Without this the row was a focus stop that answered nothing: it is not
        a QComboBox, so the navigation's fallback of opening a popup never
        applied to it. Written as a method rather than bound to
        ``open_options`` at class level, so that replacing one replaces both.
        """
        self.open_options()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.open_options()

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt)
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.open_options()
            event.accept()
            return
        super().keyPressEvent(event)


# ─────────────────────────────────────────────────────────────────────────────
# Metric tile grid — the mockup's ``auto-fit, minmax(140px, 1fr)``
# ─────────────────────────────────────────────────────────────────────────────

class ResponsiveTileGrid(QWidget):
    """Metric tiles that pick their column count from the width they are given.

    Three columns, so the six readings read as a block instead of a single
    thin strip.  Narrower panels drop to two and then one column, which is the
    only point where the count moves.
    """

    MINIMUM_TILE = 140
    COLUMNS = 3

    def __init__(self, tiles, parent: QWidget | None = None):
        super().__init__(parent)
        self._tiles = list(tiles)
        self._columns = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(10)
        self._grid.setVerticalSpacing(10)
        self._apply_columns(self.COLUMNS)

    def _apply_columns(self, columns: int) -> None:
        columns = max(1, min(self.COLUMNS, int(columns)))
        if columns == self._columns:
            return
        self._columns = columns
        for tile in self._tiles:
            self._grid.removeWidget(tile)
        for index, tile in enumerate(self._tiles):
            self._grid.addWidget(tile, index // columns, index % columns)
        for column in range(self.COLUMNS):
            self._grid.setColumnStretch(column, 1 if column < columns else 0)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().resizeEvent(event)
        spacing = self._grid.horizontalSpacing()
        self._apply_columns((self.width() + spacing) // (self.MINIMUM_TILE + spacing))


# ─────────────────────────────────────────────────────────────────────────────
# Frequency field — label + caption on the left, boxed value chip on the right
# ─────────────────────────────────────────────────────────────────────────────

class FrequencyField(QFrame):
    """Read-only frequency readout drawn the way the mockup draws it.

    ``StatusLine`` renders its value as bare 9px text, which loses the boxed
    chip the design uses to mark these two numbers as the outcome of the rail.
    """

    def __init__(
        self,
        label: str,
        detail: str = "",
        *,
        accent: bool = False,
        unit: str = "MHz",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setProperty("frequencyField", True)
        # A readout, not a control: landing here with a controller is a dead
        # end that costs two presses to leave.
        self.setProperty("gamepadSkip", True)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(9)

        text = QVBoxLayout()
        text.setSpacing(2)
        heading = QLabel(tr(label))
        heading.setProperty("frequencyFieldLabel", True)
        heading.setWordWrap(True)
        heading.setMinimumWidth(0)
        self.detail = _caption(detail)
        text.addWidget(heading)
        text.addWidget(self.detail)
        row.addLayout(text, 1)

        self.value = QLabel("--")
        self.value.setProperty("frequencyChip", True)
        if accent:
            self.value.setProperty("chipAccent", True)
        self.value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        row.addWidget(self.value, 0)

        self._unit = QLabel(tr(unit))
        self._unit.setProperty("frequencyUnit", True)
        row.addWidget(self._unit, 0)

    def set_values(self, value: str, detail: str | None = None) -> None:
        self.value.setText(value)
        if detail is not None:
            self.detail.setText(tr(detail))
            self.detail.setVisible(bool(detail))


# ─────────────────────────────────────────────────────────────────────────────
# Operating profile card — compact: name, range, voltage, pencil
# ─────────────────────────────────────────────────────────────────────────────

class ProfileCardEditable(EditableCardNavigation, QFrame):
    """A click selects the profile; the pencil edits name and frequencies."""

    selected = pyqtSignal(object)   # GpuProfile
    changed = pyqtSignal(object)    # GpuProfile

    def __init__(self, profile: GpuProfile, parent: QWidget | None = None):
        super().__init__(parent)
        self._profile = profile
        self._default = replace(profile)
        self._unlocked = False
        self.setProperty("profileCard", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        root = QVBoxLayout(self)
        root.setContentsMargins(11, 10, 11, 11)
        root.setSpacing(0)

        # ── view ────────────────────────────────────────────────────────────
        self._view = QWidget()
        view = QVBoxLayout(self._view)
        view.setContentsMargins(0, 0, 0, 0)
        view.setSpacing(5)

        head = QHBoxLayout()
        head.setSpacing(6)
        self._name_label = QLabel(tr(profile.name))
        self._name_label.setProperty("profileTitle", True)
        self._name_label.setMinimumWidth(0)
        head.addWidget(self._name_label, 1)
        self._active_pill = PillLabel(tr("Active"), "blue")
        self._active_pill.setVisible(False)
        head.addWidget(self._active_pill, 0)
        self._edit_button = QPushButton()
        self._edit_button.setIcon(icon("edit_gray"))
        self._edit_button.setFixedSize(24, 24)
        self._edit_button.setToolTip(tr("Edit profile"))
        self._edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_button.setProperty("iconOnlyButton", True)
        self._edit_button.clicked.connect(self.begin_edit)
        head.addWidget(self._edit_button, 0)
        view.addLayout(head)
        self._install_card_navigation(self._edit_button)

        self._range_label = QLabel(profile.summary())
        self._range_label.setProperty("rangeReadout", True)
        view.addWidget(self._range_label)

        self._voltage_label = _caption("")
        view.addWidget(self._voltage_label)
        root.addWidget(self._view)

        # ── editor ──────────────────────────────────────────────────────────
        self._editor = QWidget()
        editor = QVBoxLayout(self._editor)
        editor.setContentsMargins(0, 0, 0, 0)
        editor.setSpacing(8)

        editor_head = QHBoxLayout()
        eyebrow = QLabel(tr("EDITING PROFILE"))
        eyebrow.setProperty("eyebrow", True)
        editor_head.addWidget(eyebrow, 1)
        reset = QPushButton(tr("Reset"))
        reset.setProperty("linkButton", True)
        reset.setProperty("quiet", True)
        reset.setCursor(Qt.CursorShape.PointingHandCursor)
        reset.clicked.connect(self._restore_default)
        editor_head.addWidget(reset, 0)
        editor.addLayout(editor_head)

        self._name_edit = QLineEdit(profile.name)
        self._name_edit.setPlaceholderText(tr("Profile name"))
        self._name_edit.setMaxLength(28)
        editor.addWidget(self._name_edit)

        spins = QHBoxLayout()
        spins.setSpacing(8)
        self._minimum_spin = self._build_spin(profile.minimum)
        self._maximum_spin = self._build_spin(profile.maximum)
        spins.addWidget(self._labelled(tr("Min. MHz"), self._minimum_spin), 1)
        spins.addWidget(self._labelled(tr("Max. MHz"), self._maximum_spin), 1)
        editor.addLayout(spins)

        self._hint = _caption("")
        editor.addWidget(self._hint)

        save = QPushButton(tr("Save profile"))
        save.setProperty("cardAction", True)
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.clicked.connect(self._commit)
        editor.addWidget(save)

        self._editor.setVisible(False)
        root.addWidget(self._editor)

        self._maximum_spin.valueChanged.connect(self._refresh_hint)
        self._sync_view()

    # -- construction ---------------------------------------------------------
    @staticmethod
    def _build_spin(value: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(FLOOR, ABSOLUTE_CEILING)
        spin.setSingleStep(25)
        spin.setValue(value)
        spin.setMinimumWidth(74)
        return spin

    @staticmethod
    def _labelled(text: str, control: QWidget) -> QWidget:
        host = QWidget()
        box = QVBoxLayout(host)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(3)
        label = QLabel(text)
        label.setProperty("fieldLabel", True)
        box.addWidget(label)
        box.addWidget(control)
        return host

    # -- API --------------------------------------------------------------
    @property
    def profile(self) -> GpuProfile:
        return self._profile

    def set_editable(self, editable: bool) -> None:
        """Oberon's three profiles come from the contract and are not editable."""
        self._edit_button.setVisible(bool(editable))

    def set_profile(self, profile: GpuProfile) -> None:
        """Loads a profile already saved by the user (settings override)."""
        self._profile = profile
        self._sync_view()

    def set_active(self, active: bool) -> None:
        self._active_pill.setVisible(active)
        self.setProperty("selectedProfile", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def set_unlocked(self, unlocked: bool) -> None:
        self._unlocked = unlocked
        self._sync_view()

    def is_blocked(self) -> bool:
        """Asks for more than the TOML currently allows."""
        return self._profile.is_risky() and not self._unlocked

    def begin_edit(self) -> None:
        self._name_edit.setText(self._profile.name)
        self._minimum_spin.setValue(self._profile.minimum)
        self._maximum_spin.setValue(self._profile.maximum)
        self._refresh_hint()
        self._view.setVisible(False)
        self._editor.setVisible(True)
        self._card_enter_edit()
        self._name_edit.setFocus()
        self._name_edit.selectAll()

    def cancel_edit(self) -> None:
        self._editor.setVisible(False)
        self._view.setVisible(True)
        self._card_leave_edit()

    def retranslate(self) -> None:
        """Rebuilds the interpolated hint after a live language change."""
        self._refresh_hint()
        self._sync_view()

    # -- internal -----------------------------------------------------------
    def _restore_default(self) -> None:
        self._name_edit.setText(self._default.name)
        self._minimum_spin.setValue(self._default.minimum)
        self._maximum_spin.setValue(self._default.maximum)

    def _refresh_hint(self) -> None:
        if self._maximum_spin.value() > SAFE_CEILING:
            self._hint.setText(
                tr_format(
                    "Above {ceiling} MHz you need to uncomment the +2000 points "
                    "in the Danger zone.",
                    ceiling=SAFE_CEILING,
                )
            )
        else:
            self._hint.setText(
                tr_format(
                    "The maximum should match a TOML point ({floor} – {ceiling} MHz).",
                    floor=FLOOR,
                    ceiling=SAFE_CEILING,
                )
            )

    def _commit(self) -> None:
        minimum = self._minimum_spin.value()
        maximum = max(self._maximum_spin.value(), minimum)
        name = self._name_edit.text().strip() or self._default.name
        self._profile = replace(self._profile, name=name, minimum=minimum, maximum=maximum)
        self.cancel_edit()
        self._sync_view()
        self.changed.emit(self._profile)

    def _sync_view(self) -> None:
        profile = self._profile
        self._name_label.setText(tr(profile.name))
        self._range_label.setText(profile.summary())
        self._voltage_label.setText(f"{profile.voltage} mV")
        blocked = self.is_blocked()
        self._range_label.setProperty("danger", blocked)
        self.setProperty("blockedProfile", blocked)
        for widget in (self._range_label, self):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.setToolTip(
            tr("Uncomment the +2000 MHz points to use this profile")
            if self.is_blocked()
            else ""
        )

    def _card_selectable(self) -> bool:
        return not self._card_editing() and not self.is_blocked()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().mouseReleaseEvent(event)
        if self._editor.isVisible() or self.is_blocked():
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self._profile)


# ─────────────────────────────────────────────────────────────────────────────
# Safe-point rail
# ─────────────────────────────────────────────────────────────────────────────

class SafePointRail(QWidget):
    """Safe-point selector.

    Each point occupies the same width (position by index, not by MHz): the
    2050–2400 points are 25–50 MHz apart from each other and would overlap
    with a linear scale. The ones commented out in the TOML are drawn dimmed
    and non-clickable, so it is visible that they exist and are closed.
    """

    range_changed = pyqtSignal(int, int)

    _TICK_TOP = 4
    _TICK_TALL = 17
    _TICK_SHORT = 12
    _RAIL_Y = 19
    _LABEL_ROW_A = 35          # below the handle's bottom edge (31)
    _LABEL_ROW_B = 51
    _LABEL_HEIGHT = 15
    _MARGIN = 26

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._unlocked = False
        self._minimum = 1000
        self._maximum = 1850
        self._dragging = ""
        # Which handle the arrow keys and the controller move. A pointer picks
        # a handle by being near it; a D-pad has no position, so the rail has
        # to remember one and show which it is.
        self._active = "maximum"
        self.setMinimumHeight(self._LABEL_ROW_B + self._LABEL_HEIGHT + 6)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # -- API --------------------------------------------------------------
    def set_unlocked(self, unlocked: bool) -> None:
        self._unlocked = unlocked
        if not unlocked:
            self._maximum = min(self._maximum, SAFE_CEILING)
            self._minimum = min(self._minimum, self._maximum)
        self.update()

    def set_range(self, minimum: int, maximum: int) -> None:
        self._minimum, self._maximum = minimum, maximum
        self.update()

    def range(self) -> tuple[int, int]:
        return self._minimum, self._maximum

    # -- controller and keyboard -------------------------------------------
    def active_handle(self) -> str:
        return self._active

    def set_active_handle(self, handle: str) -> None:
        if handle in ("minimum", "maximum") and handle != self._active:
            self._active = handle
            self.update()

    def gamepad_activate(self) -> None:
        """A swaps which end of the range the arrows move.

        One rail carries two values, and a controller has one cursor. Rather
        than inventing a second focus stop for the same widget, the accept
        button toggles which end is being edited.
        """
        self.set_active_handle("minimum" if self._active == "maximum" else "maximum")

    def gamepad_direction(self, direction: str) -> bool:
        """Left/right move the active handle; up/down leave the rail.

        The rail already did this for the keyboard, but the controller never
        sent it arrow keys: left/right jumped to the neighbouring control
        instead of moving the frequency.
        """
        if direction not in {"left", "right"}:
            return False
        # Consumed even at an end of the range: a press that silently left
        # the rail would be read as the rail having moved.
        self.step_active_handle(-1 if direction == "left" else 1)
        return True

    def step_active_handle(self, delta: int) -> None:
        """Move the active handle by whole safe-points, never between them."""
        points = offered_points(unlocked=self._unlocked)
        if not points:
            return
        current = self._minimum if self._active == "minimum" else self._maximum
        nearest = min(range(len(points)), key=lambda i: abs(points[i] - current))
        target = points[max(0, min(len(points) - 1, nearest + delta))]
        if self._active == "minimum":
            self._minimum = min(target, self._maximum)
        else:
            self._maximum = max(target, self._minimum)
        self.update()
        self.range_changed.emit(self._minimum, self._maximum)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt)
        key = event.key()
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self.step_active_handle(-1 if key == Qt.Key.Key_Left else 1)
            event.accept()
            return
        if key in (Qt.Key.Key_Home, Qt.Key.Key_End):
            points = offered_points(unlocked=self._unlocked)
            if points:
                self.step_active_handle(-len(points) if key == Qt.Key.Key_Home else len(points))
            event.accept()
            return
        if key in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.gamepad_activate()
            event.accept()
            return
        # Up and Down are left alone so the controller can still leave the rail.
        super().keyPressEvent(event)

    # -- geometry -----------------------------------------------------------
    def _x_for(self, frequency: int) -> float:
        """Position by index, interpolated when the frequency is not a point."""
        usable = max(1, self.width() - self._MARGIN * 2)
        last = len(ALL_POINTS) - 1
        if frequency in ALL_POINTS:
            fraction = ALL_POINTS.index(frequency) / last
        else:
            lower = 0
            for index, point in enumerate(ALL_POINTS):
                if point <= frequency:
                    lower = index
            upper = min(lower + 1, last)
            span = ALL_POINTS[upper] - ALL_POINTS[lower] or 1
            offset = max(0.0, min(1.0, (frequency - ALL_POINTS[lower]) / span))
            fraction = (lower + offset) / last
        return self._MARGIN + usable * fraction

    def _frequency_at(self, x: float) -> int:
        return min(offered_points(unlocked=self._unlocked),
                   key=lambda point: abs(self._x_for(point) - x))

    # -- interaction --------------------------------------------------------
    def _handle_at(self, x: float) -> str:
        """Nearest handle, so the floor is as reachable as the ceiling."""
        low, high = self._x_for(self._minimum), self._x_for(self._maximum)
        distance_low, distance_high = abs(x - low), abs(x - high)
        if distance_low == distance_high:
            # Both handles sit on the same point: the side of the click decides.
            return "maximum" if x > low else "minimum"
        return "minimum" if distance_low < distance_high else "maximum"

    def _move_handle(self, handle: str, x: float) -> None:
        frequency = self._frequency_at(x)
        if handle == "minimum":
            self._minimum = min(frequency, self._maximum)
        else:
            self._maximum = max(frequency, self._minimum)
        self.update()
        self.range_changed.emit(self._minimum, self._maximum)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._dragging = self._handle_at(event.position().x())
        self.set_active_handle(self._dragging)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self._move_handle(self._dragging, event.position().x())

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt)
        if self._dragging:
            self._move_handle(self._dragging, event.position().x())

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt)
        self._dragging = ""

    # -- painting -------------------------------------------------------------
    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        left, right = self._x_for(FLOOR), self._x_for(ABSOLUTE_CEILING)
        painter.setBrush(_qcolor("progress_track"))
        painter.drawRoundedRect(QRectF(left, self._RAIL_Y, right - left, 4), 2, 2)

        # Segment closed by the TOML.
        if not self._unlocked:
            locked_x = self._x_for(SAFE_CEILING)
            painter.setBrush(_qcolor("red", 60))
            painter.drawRoundedRect(
                QRectF(locked_x, self._RAIL_Y, right - locked_x, 4), 2, 2
            )

        # Selection: one accent-coloured line across the range, as the mockup
        # draws it.  Points past 2000 MHz keep their red ticks and labels.
        low, high = self._x_for(self._minimum), self._x_for(self._maximum)
        painter.setBrush(_qcolor("blue"))
        painter.drawRoundedRect(QRectF(low, self._RAIL_Y, max(high - low, 3), 4), 2, 2)

        font = painter.font()
        font.setPointSizeF(max(7.0, font.pointSizeF() - 1.5))
        painter.setFont(font)

        for index, frequency in enumerate(ALL_POINTS):
            x = self._x_for(frequency)
            blocked = frequency > SAFE_CEILING and not self._unlocked
            inside = self._minimum <= frequency <= self._maximum
            risky = frequency > SAFE_CEILING
            staggered = index % 2 == 1

            if blocked:
                tick, text = _qcolor("red", 70), _qcolor("red", 140)
            elif inside:
                tick = text = _qcolor("red") if risky else _qcolor("blue")
                if not risky:
                    text = _qcolor("text")
            elif risky:
                tick, text = _qcolor("red", 115), _qcolor("red", 200)
            else:
                tick, text = _qcolor("border_strong"), _qcolor("subtle")

            painter.setBrush(tick)
            height = self._TICK_SHORT if staggered else self._TICK_TALL
            painter.drawRoundedRect(QRectF(x - 1, self._TICK_TOP, 2, height), 1, 1)

            painter.setPen(text)
            label_y = self._LABEL_ROW_B if staggered else self._LABEL_ROW_A
            painter.drawText(
                QRectF(x - 26, label_y, 52, self._LABEL_HEIGHT),
                Qt.AlignmentFlag.AlignCenter,
                str(frequency),
            )
            painter.setPen(Qt.PenStyle.NoPen)

        # Handles: band 12–31, above the two label rows.
        focused = self.hasFocus()
        for name, frequency, filled in (
            ("minimum", self._minimum, False),
            ("maximum", self._maximum, True),
        ):
            x = self._x_for(frequency)
            handle = QRectF(x - 6.5, self._RAIL_Y - 7, 13, 18)
            if focused and name == self._active:
                # Arrow keys and a D-pad move one end at a time. Without a mark
                # the rail answers a key press by changing a number somewhere
                # else on screen, and nothing says which one it will be.
                painter.setPen(QPen(_qcolor("focus"), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(handle.adjusted(-3.5, -3.5, 3.5, 3.5), 7, 7)
            painter.setPen(_qcolor("blue"))
            painter.setBrush(_qcolor("blue") if filled else _qcolor("panel"))
            painter.drawRoundedRect(handle, 5, 5)
            painter.setPen(Qt.PenStyle.NoPen)
        painter.end()

    def focusInEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().focusOutEvent(event)
        self.update()


# ─────────────────────────────────────────────────────────────────────────────
# Console, point table and contract
# ─────────────────────────────────────────────────────────────────────────────

class OperationsConsole(QFrame):
    """Console that fills the full height of its column."""

    cleared = pyqtSignal()
    copy_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("subPanel", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        head = QWidget()
        # Scoped to the header itself: a bare declaration also underlined every
        # label inside it and restyled their tooltips.
        head.setObjectName("gpuPanelHead")
        head.setStyleSheet(
            f"QWidget#gpuPanelHead {{ border-bottom:1px solid {COLORS['border_soft']}; }}"
        )
        head_row = QHBoxLayout(head)
        head_row.setContentsMargins(14, 11, 14, 11)
        head_row.setSpacing(10)
        title = QLabel(tr("Operations console"))
        title.setProperty("cardTitle", True)
        head_row.addWidget(title, 1)
        copy_button = QPushButton(tr("Copy diagnostics"))
        copy_button.setProperty("linkButton", True)
        copy_button.setProperty("quiet", True)
        copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_button.clicked.connect(self.copy_requested)
        head_row.addWidget(copy_button)
        clear_button = QPushButton(tr("Clear"))
        clear_button.setProperty("linkButton", True)
        clear_button.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_button.clicked.connect(self._clear)
        head_row.addWidget(clear_button)
        root.addWidget(head)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setFrameShape(QFrame.Shape.NoFrame)
        self.output.setMinimumHeight(300)
        self.output.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.output.setStyleSheet(
            f"QPlainTextEdit {{ background:{COLORS['console_bg']};"
            f" color:{COLORS['console_text']}; border:none; padding:10px 13px;"
            " border-bottom-left-radius:12px; border-bottom-right-radius:12px;"
            " font-family:'JetBrains Mono','DejaVu Sans Mono',monospace; font-size:12px; }"
        )
        root.addWidget(self.output, 1)

    def append(self, line: str) -> None:
        self.output.appendPlainText(line)

    def set_lines(self, lines: Iterable[str]) -> None:
        self.output.setPlainText("\n".join(lines))

    def text(self) -> str:
        return self.output.toPlainText()

    def _clear(self) -> None:
        self.output.clear()
        self.cleared.emit()


class _SafePointRow(QFrame):
    """One frequency/voltage entry of the safe-point table.

    The table itself is a constant. What changes is which entry falls inside
    the selected range and which is commented out, and that was recomputed by
    destroying seventeen rows and building them again on every three-second
    governor tick — around a hundred stylesheet applications each time, every
    one of them invalidating the style cache of its whole subtree.

    So the row is built once and told what it is. Colours are only re-applied
    when the look actually changed, following ``PillLabel.set_tone``; the
    unconditional ``_refresh_palette`` is what the application-wide theme
    change calls.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._look: tuple[bool, bool, bool] | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 7, 14, 7)
        layout.setSpacing(10)
        self.frequency = QLabel()
        layout.addWidget(self.frequency, 1)
        self.voltage = QLabel()
        layout.addWidget(self.voltage, 1)
        self.source = QLabel()
        layout.addWidget(self.source, 2)
        self.badge = QLabel()
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignRight)

    def set_values(
        self,
        frequency: int,
        voltage: int,
        *,
        commented: bool,
        in_range: bool,
        first: bool,
    ) -> None:
        self.frequency.setText(f"{frequency} MHz")
        self.voltage.setText(f"{voltage} mV")
        self.source.setText(
            tr("commented in config.toml") if commented else tr("active in config.toml")
        )
        self.badge.setText(
            tr("COMMENTED") if commented else tr("IN RANGE") if in_range else tr("VALIDATED")
        )
        look = (bool(commented), bool(in_range), bool(first))
        if look == self._look:
            return
        self._look = look
        self._refresh_palette()

    def _refresh_palette(self) -> None:
        commented, in_range, first = self._look or (False, False, True)
        # The separator lives on the row rather than between rows: half the
        # widgets, and a pool that does not have to interleave two kinds.
        border = (
            "border:none;" if first
            else f"border:none; border-top:1px solid {COLORS['border_soft']};"
        )
        background = _accent_soft() if in_range else "transparent"
        self.setStyleSheet(f"QFrame {{ background:{background}; {border} }}")
        self.frequency.setStyleSheet(
            f"color:{COLORS['disabled_text'] if commented else COLORS['text']};"
            " font-weight:700; background:transparent; border:none;"
        )
        self.voltage.setStyleSheet(
            f"color:{COLORS['muted']}; background:transparent; border:none;"
        )
        self.source.setStyleSheet(
            f"color:{COLORS['subtle']}; background:transparent; border:none;"
        )
        if commented:
            color, badge_background = COLORS["red"], COLORS["red_soft"]
        elif in_range:
            color, badge_background = COLORS["blue"], COLORS["blue_soft"]
        else:
            color, badge_background = COLORS["muted"], COLORS["neutral_soft"]
        self.badge.setStyleSheet(
            f"QLabel {{ color:{color}; background:{badge_background};"
            " border:none; border-radius:5px; padding:2px 7px; font-size:10px;"
            " font-weight:700; }"
        )


class SafePointTable(QFrame):
    """One row per safe-point: frequency, voltage and its status in the TOML."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("subPanel", True)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        head = QWidget()
        # Scoped to the header itself: a bare declaration also underlined every
        # label inside it and restyled their tooltips.
        head.setObjectName("gpuPanelHead")
        head.setStyleSheet(
            f"QWidget#gpuPanelHead {{ border-bottom:1px solid {COLORS['border_soft']}; }}"
        )
        head_row = QHBoxLayout(head)
        head_row.setContentsMargins(14, 11, 14, 11)
        title = QLabel(tr("Active TOML safe-points"))
        title.setProperty("cardTitle", True)
        head_row.addWidget(title, 1)
        self._count = _caption("")
        head_row.addWidget(self._count, 0)
        root.addWidget(head)

        self._rows_host = QWidget()
        self._rows = QVBoxLayout(self._rows_host)
        self._rows.setContentsMargins(0, 0, 0, 6)
        self._rows.setSpacing(0)
        root.addWidget(self._rows_host)

        self.refresh(1000, 1850, unlocked=False)

    def refresh(
        self,
        minimum: int,
        maximum: int,
        *,
        unlocked: bool,
        points: Sequence[tuple[int, int]] | None = None,
    ) -> None:
        """``points`` allows using the real table reported by the backend."""
        table = tuple(points) if points else SAFE_POINTS + EXTRA_POINTS
        active = sum(
            1 for frequency, _v in table if frequency <= ceiling_for(unlocked=unlocked)
        )
        self._count.setText(
            tr_format("{active} of {total} entries", active=active, total=len(table))
        )

        for index, (frequency, voltage) in enumerate(table):
            item = self._rows.itemAt(index)
            row = item.widget() if item is not None else None
            if not isinstance(row, _SafePointRow):
                row = _SafePointRow(self._rows_host)
                self._rows.insertWidget(index, row)
            row.set_values(
                frequency,
                voltage,
                commented=frequency > SAFE_CEILING and not unlocked,
                in_range=minimum <= frequency <= maximum,
                first=index == 0,
            )
        while self._rows.count() > len(table):
            item = self._rows.takeAt(self._rows.count() - 1)
            widget = item.widget()
            if widget is not None:
                # setParent(None) first: deleteLater() alone keeps the widget in
                # the tree until the event loop runs, and two refreshes in the
                # same tick would paint the stale rows over the new ones.
                widget.setParent(None)
                widget.deleteLater()


class _ContractLine(QFrame):
    """One ``label: value`` line of the contract panel."""

    def __init__(self, *, first: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._first = bool(first)
        line = QHBoxLayout(self)
        line.setContentsMargins(0, 7, 0, 7)
        line.setSpacing(14)
        self.key = QLabel()
        self.key.setWordWrap(True)
        self.key.setMinimumWidth(0)
        line.addWidget(self.key, 1)
        self.reading = QLabel()
        self.reading.setWordWrap(True)
        self.reading.setMinimumWidth(0)
        self.reading.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        line.addWidget(self.reading, 1)
        self._refresh_palette()

    def set_values(self, label: str, value: str) -> None:
        self.key.source_text = label
        self.key.setText(tr(label))
        self.reading.source_text = value
        self.reading.setText(tr(value))

    def _refresh_palette(self) -> None:
        border = (
            "border:none;" if self._first
            else f"border:none; border-top:1px solid {COLORS['border_soft']};"
        )
        self.setStyleSheet(f"QFrame {{ background:transparent; {border} }}")
        self.key.setStyleSheet(
            f"QLabel {{ color:{COLORS['muted']}; font-size:12px;"
            " background:transparent; border:none; }"
        )
        self.reading.setStyleSheet(
            f"QLabel {{ color:{COLORS['text']}; font-size:12px;"
            " font-weight:700; background:transparent; border:none; }"
        )


class ContractPanel(QWidget):
    """Governor / hardware contract."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._frame, self._box = _subpanel("Governor and hardware contract")
        self._box.setSpacing(0)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._frame)
        self._lines: list[_ContractLine] = []

    def set_rows(self, rows: Sequence[tuple[str, str]]) -> None:
        """Seven labels, refreshed every three seconds.

        They used to be seven rebuilt frames with three stylesheet
        applications each. The contract does change — that is the point of the
        panel — but what changes is the text, not the layout.
        """
        for index, (label, value) in enumerate(rows):
            if index < len(self._lines):
                line = self._lines[index]
            else:
                line = _ContractLine(first=index == 0, parent=self._frame)
                self._lines.append(line)
                self._box.addWidget(line)
            line.set_values(label, value)
        while len(self._lines) > len(rows):
            line = self._lines.pop()
            self._box.removeWidget(line)
            line.setParent(None)
            line.deleteLater()


# ─────────────────────────────────────────────────────────────────────────────
# State that drives the screen
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GpuViewState:
    core_clock: int = 0
    voltage: int = 0
    temperature: float = 0.0
    load: int = 0
    memory_clock: int = 0
    active_minimum: int = 0
    active_maximum: int = 0
    service_running: bool = False
    service_persistent: bool = False
    dbus_connected: bool = False
    # False: Cyan runs but its D-Bus timed out. None: not asked or not Cyan.
    dbus_responsive: bool | None = None
    unlocked: bool = False
    backend: str = "cyan-skillfish-governor-smu"
    device: str = "AMD BC-250 · 0x1002 / 0x13fe"
    config_path: str = "/etc/cyan-skillfish-governor-smu/config.toml"
    safe_points: tuple[tuple[int, int], ...] = field(default=SAFE_POINTS + EXTRA_POINTS)
    set_method: str = "smu"
    usage_method: str = "busy-flag"
    fix_metrics: bool = True
    fix_frequency: bool = False

    @classmethod
    def from_backend(cls, gpu: dict, telemetry: dict | None = None) -> "GpuViewState":
        """Builds the state from the controller's ``gpu`` dict.

        Keys it consumes (the same ones ``GpuGovernorPage`` uses):
        ``sclk_actual``, ``mclk_actual``, ``current_min``, ``current_max``,
        ``service_active``, ``dbus_connected``, ``governor_backend``,
        ``config_path``, ``high_frequency_points.enabled``,
        ``safe_points_with_voltage`` / ``safe_points``.
        """
        telemetry = telemetry or {}

        def integer(value, fallback: int = 0) -> int:
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return fallback

        high_points = gpu.get("high_frequency_points") or {}
        cyan = gpu.get("cyan_telemetry")
        cyan = cyan if isinstance(cyan, dict) else {}
        raw_points = gpu.get("safe_points_with_voltage") or gpu.get("safe_points") or ()
        points: list[tuple[int, int]] = []
        for entry in raw_points:
            if isinstance(entry, dict):
                frequency = integer(entry.get("frequency"))
                voltage = integer(entry.get("voltage"), voltage_for(frequency))
            elif isinstance(entry, (tuple, list)) and len(entry) >= 2:
                frequency, voltage = integer(entry[0]), integer(entry[1])
            else:
                frequency, voltage = integer(entry), 0
                voltage = voltage or voltage_for(frequency)
            if frequency:
                points.append((frequency, voltage))

        return cls(
            core_clock=integer(gpu.get("sclk_actual")),
            voltage=integer(gpu.get("voltage_actual"), voltage_for(integer(gpu.get("current_max"), SAFE_CEILING))),
            temperature=float(telemetry.get("temperature") or gpu.get("temperature") or 0.0),
            load=integer(telemetry.get("utilization") or gpu.get("gpu_busy_percent")),
            memory_clock=integer(gpu.get("mclk_actual")),
            active_minimum=integer(gpu.get("current_min")),
            active_maximum=integer(gpu.get("current_max")),
            service_running=str(gpu.get("service_active") or "").lower() == "active",
            service_persistent=bool(gpu.get("service_enabled", True)),
            dbus_connected=bool(gpu.get("dbus_connected", True)),
            dbus_responsive=(
                None if gpu.get("dbus_responsive") is None else bool(gpu.get("dbus_responsive"))
            ),
            unlocked=bool(high_points.get("enabled")),
            backend=str(gpu.get("governor_backend") or "cyan-skillfish-governor-smu"),
            config_path=str(
                gpu.get("config_path") or "/etc/cyan-skillfish-governor-smu/config.toml"
            ),
            safe_points=tuple(points) or SAFE_POINTS + EXTRA_POINTS,
            set_method=str(cyan.get("set_method") or "smu"),
            usage_method=str(cyan.get("method") or "busy-flag"),
            fix_metrics=bool(cyan.get("fix_metrics", True)),
            fix_frequency=bool(cyan.get("fix_frequency", False)),
        )


# ─────────────────────────────────────────────────────────────────────────────
# The screen
# ─────────────────────────────────────────────────────────────────────────────

class GpuGovernorView(QWidget):
    """Redesigned GPU module — presentation only.

    Signals towards the backend::

        range_apply_requested(int minimum, int maximum)
        range_startup_requested(int minimum, int maximum)
        profile_changed(object GpuProfile)
        service_action_requested(str)      # 'status' | 'restart' | 'disable'
        compatibility_apply_requested(dict)
        high_points_toggle_requested(bool)
        voltage_lab_requested()
        config_open_requested()
        diagnostics_copy_requested()

    Inputs::

        apply_state(GpuViewState)
        set_profiles(profiles)
        set_console_lines(lines) / append_console_line(line)
    """

    range_apply_requested = pyqtSignal(int, int)
    range_startup_requested = pyqtSignal(int, int)
    profile_changed = pyqtSignal(object)
    export_to_decky_requested = pyqtSignal()
    service_action_requested = pyqtSignal(str)
    compatibility_apply_requested = pyqtSignal(dict)
    high_points_toggle_requested = pyqtSignal(bool)
    voltage_lab_requested = pyqtSignal()
    config_open_requested = pyqtSignal()
    diagnostics_copy_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("redesignedModule", True)
        self._state = GpuViewState(
            core_clock=1000,
            voltage=930,
            temperature=53.0,
            load=1,
            memory_clock=450,
            active_minimum=1000,
            active_maximum=1850,
            service_running=True,
            service_persistent=True,
            dbus_connected=True,
        )
        self._selected_minimum = 1000
        self._selected_maximum = 1850
        self._selected_profile = "gaming"
        self._compatibility_dirty = False
        #: Cyan unless told otherwise, so its behaviour is untouched by the
        #: Oberon adaptation below.
        self._oberon_mode = False
        # Telemetry refreshes must not yank a range the user is staging; the
        # selection re-syncs with the hardware when the screen is entered
        # again, not on every poll.
        self._follow_hardware = True

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 12, 16, 24)
        layout.setSpacing(12)

        self._workspace = QGridLayout()
        self._workspace.setContentsMargins(0, 0, 0, 0)
        self._workspace.setHorizontalSpacing(12)
        self._workspace.setVerticalSpacing(12)
        layout.addLayout(self._workspace)

        self._configuration = self._build_configuration_card()
        self._telemetry = self._build_telemetry_card()
        self._workspace.addWidget(self._configuration, 0, 0)
        self._workspace.addWidget(self._telemetry, 0, 1)
        self._workspace.setColumnStretch(0, 18)
        self._workspace.setColumnStretch(1, 12)

        layout.addWidget(self._build_advanced_card())
        layout.addStretch(1)
        self.apply_state(self._state)

    # ── GPU configuration ──────────────────────────────────────────────────
    def _build_configuration_card(self) -> SectionCard:
        card = SectionCard(
            "GPU configuration",
            "Select a validated profile or stage an explicit D-Bus range. Every "
            "hardware change is reviewed before execution.",
            icon_name="gpu_purple",
            icon_background=_accent_soft(),
            status=("Safe mode", "green"),
        )
        # The same composition as the CPU workspace: no title row, since the
        # page already says where it is. The range state it carried moves to
        # the Cyan compatibility heading below, with the ring that stands in
        # for it while hardware work runs.
        self._safe_pill = card.drop_header()
        self._busy_badge = BusyBadge()
        self._operation_busy = False

        profiles_panel, profiles_box = _subpanel("")
        self.profiles_panel = profiles_panel
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        profiles_title = QLabel(tr("Operating profile"))
        profiles_title.setProperty("cardTitle", True)
        profiles_title.setWordWrap(True)
        title_row.addWidget(profiles_title, 0)
        title_row.addStretch(1)
        self._profiles_title_row = title_row
        self._export_decky_button = QPushButton(tr("Export to Decky"))
        self._export_decky_button.setIcon(icon("gamepad_menu"))
        self._export_decky_button.setProperty("compactAction", True)
        self._export_decky_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._export_decky_button.setToolTip(
            tr("Send these three profile cards to the Decky Quick Access panel.")
        )
        self._export_decky_button.clicked.connect(self.export_to_decky_requested.emit)
        title_row.addWidget(self._export_decky_button, 0)
        title_row.setAlignment(self._export_decky_button, Qt.AlignmentFlag.AlignBottom)
        profiles_box.addLayout(title_row)
        profiles_box.addWidget(
            caption("One click sets the range. The pencil changes name and frequencies.")
        )
        self._profiles_grid = QGridLayout()
        self._profiles_grid.setContentsMargins(0, 0, 0, 0)
        self._profiles_grid.setHorizontalSpacing(8)
        self._profiles_grid.setVerticalSpacing(8)
        profiles_box.addLayout(self._profiles_grid)

        self._profile_cards: list[ProfileCardEditable] = []
        for column, profile in enumerate(DEFAULT_PROFILES):
            profile_card = ProfileCardEditable(replace(profile))
            profile_card.selected.connect(self._on_profile_selected)
            profile_card.changed.connect(self._on_profile_changed)
            self._profiles_grid.addWidget(profile_card, 0, column)
            self._profiles_grid.setColumnStretch(column, 1)
            self._profile_cards.append(profile_card)
        card.body.addWidget(profiles_panel)

        range_panel, range_box = _subpanel("Frequency range")
        self._range_panel = range_panel
        header = QHBoxLayout()
        self._range_subtitle = _caption("")
        header.addWidget(self._range_subtitle, 1)
        self._range_readout = QLabel("")
        self._range_readout.setProperty("bigReadout", True)
        header.addWidget(self._range_readout, 0, Qt.AlignmentFlag.AlignRight)
        range_box.addLayout(header)

        self._locked_label = QLabel("")
        self._locked_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._locked_label.setProperty("railLegend", True)
        range_box.addWidget(self._locked_label)

        self._rail = SafePointRail()
        self._rail.range_changed.connect(self._on_rail_changed)
        range_box.addWidget(self._rail)

        fields = QHBoxLayout()
        fields.setSpacing(12)
        self._minimum_line = FrequencyField(
            "Minimum frequency",
            "Governor floor applied through the validated D-Bus interface.",
        )
        self._maximum_line = FrequencyField("Maximum frequency", "", accent=True)
        fields.addWidget(self._minimum_line, 1)
        fields.addWidget(self._maximum_line, 1)
        range_box.addLayout(fields)
        card.body.addWidget(range_panel)

        compat_panel, compat_box = _subpanel()
        self._compat_panel = compat_panel
        compat_title_row = QHBoxLayout()
        compat_title_row.setContentsMargins(0, 0, 0, 0)
        compat_title_row.setSpacing(8)
        compat_title = QLabel(tr("Cyan kernel compatibility"))
        compat_title.setProperty("cardTitle", True)
        compat_title.setWordWrap(True)
        compat_title_row.addWidget(compat_title, 1)
        # What Cyan is running under (the safe or the extended range) and,
        # while the governor is being changed, the ring that says so.
        if self._safe_pill is not None:
            compat_title_row.addWidget(self._safe_pill, 0, Qt.AlignmentFlag.AlignVCenter)
        compat_title_row.addWidget(self._busy_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        compat_box.addLayout(compat_title_row)
        self._compat_title_row = compat_title_row
        compat_box.addWidget(caption("Only touch this if the readings above look wrong."))
        # The legacy screen is hidden while this view is mounted, so the two
        # method selectors have to live here or they become unreachable.
        methods = QHBoxLayout()
        methods.setSpacing(10)
        self.set_method_combo = PickerRow("Governor method")
        self.set_method_combo.addItem("SMU", "smu")
        self.set_method_combo.addItem("Kernel", "kernel")
        self.usage_method_combo = PickerRow("Usage reading")
        for usage_method in ("busy-flag", "process", "kernel"):
            self.usage_method_combo.addItem(usage_method, usage_method)
        for picker in (self.set_method_combo, self.usage_method_combo):
            picker.currentIndexChanged.connect(self._mark_compatibility_dirty)
            methods.addWidget(picker, 1)
        compat_box.addLayout(methods)
        # "process" looks like one more option, and it is the one that stops
        # Cyan from answering whenever a game is open.
        self._process_method_warning = QLabel(
            tr(
                "The process reading goes through every open file of every program. With a "
                "game open, Cyan stops answering: the range, the +2000 MHz points and the "
                "voltage lab stop working until the game closes. busy-flag is the default."
            )
        )
        self._process_method_warning.setWordWrap(True)
        self._process_method_warning.setProperty("gpuBusNotice", True)
        compat_box.addWidget(self._process_method_warning)
        self.usage_method_combo.currentIndexChanged.connect(self._sync_process_method_warning)
        self._sync_process_method_warning()

        toggles = QHBoxLayout()
        toggles.setSpacing(16)
        # The mockup uses check boxes here, not chips: these two are settings
        # staged for "Apply compatibility", not actions that fire on click.
        self._metrics_toggle = CheckRow(governor_fix_label("metrics"))
        self._frequencies_toggle = CheckRow(governor_fix_label("frequency"))
        for box in (self._metrics_toggle, self._frequencies_toggle):
            box.setChecked(True)
            box.setCursor(Qt.CursorShape.PointingHandCursor)
            box.toggled.connect(self._mark_compatibility_dirty)
            toggles.addWidget(box, 0)
        toggles.addStretch(1)
        apply_compat = QPushButton(tr("Apply compatibility"))
        apply_compat.setProperty("ghostButton", True)
        apply_compat.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_compat.clicked.connect(
            lambda: self.compatibility_apply_requested.emit(self.compatibility_options())
        )
        toggles.addWidget(apply_compat, 0)
        compat_box.addLayout(toggles)
        card.body.addWidget(compat_panel)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.startup_button = QPushButton(tr("Save for startup"))
        self.startup_button.setProperty("ghostButton", True)
        self.startup_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.startup_button.clicked.connect(
            lambda: self.range_startup_requested.emit(
                self._selected_minimum, self._selected_maximum
            )
        )
        actions.addWidget(self.startup_button, 1)
        self.apply_button = QPushButton(tr("Review and apply range"))
        self.apply_button.setObjectName("PrimaryAction")
        self.apply_button.setProperty("primaryAction", True)
        self.apply_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_button.clicked.connect(self._confirm_and_apply)
        actions.addWidget(self.apply_button, 2)
        card.body.addLayout(actions)
        card.body.addStretch(1)
        return card

    # ── Live telemetry ─────────────────────────────────────────────────────
    def _build_telemetry_card(self) -> SectionCard:
        card = SectionCard(
            "Live GPU telemetry",
            "Read-only sensor data refreshed from amdgpu, the governor backend, "
            "and the existing performance service.",
            icon_name="metrics_blue",
            icon_background=_accent_soft(),
            status=("Live", "green"),
        )
        # No title row and no "Live" pill, as on the CPU workspace; the tiles
        # below are read by their labels, without a badge each.
        card.drop_header()

        self._tiles: dict[str, MetricTile] = {
            "core": MetricTile("Core clock", "--", "Current SCLK state", icon_name="", compact=True),
            "voltage": MetricTile("GPU voltage", "--", "OD / SMU telemetry", icon_name="", compact=True),
            "temperature": MetricTile("Temperature", "--", "hwmon", icon_name="", compact=True),
            "load": MetricTile("GPU load", "--", "amdgpu activity", icon_name="", compact=True),
            "memory": MetricTile("Memory clock", "--", "Current MCLK state", icon_name="", compact=True),
            "range": MetricTile("Active range", "--", "Persisted on hardware", icon_name="", compact=True),
        }
        card.body.addWidget(ResponsiveTileGrid(self._tiles.values()))
        card.body.addWidget(
            _caption("Passive readings · hardware changes require confirmation.")
        )
        # Says why the range and the D-Bus actions fail while Cyan is running
        # but not answering, instead of an error on every click.
        self._bus_notice = QLabel()
        self._bus_notice.setWordWrap(True)
        self._bus_notice.setProperty("gpuBusNotice", True)
        self._bus_notice.hide()
        card.body.addWidget(self._bus_notice)

        service_panel, service_box = _subpanel("Governor service")
        # "Enable" is systemd's word for "start at boot", so it named only half
        # of what this button does; a tester read it as "save for startup".
        # The button says what happens now, the caption what happens at boot.
        service_box.addWidget(
            _caption(
                "Start governor runs it now and saves it for startup (enables "
                "the service). Stop governor stops it and removes it from "
                "startup (disables the service)."
            )
        )
        service_actions = QHBoxLayout()
        service_actions.setSpacing(8)
        # Kept addressable so a test can check every one of these names is
        # something the backend planner actually accepts.
        self.service_buttons: dict[str, QPushButton] = {}
        for label, action in (("View status", "status"), ("Restart", "restart")):
            button = QPushButton(tr(label))
            self.service_buttons[action] = button
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setProperty("ghostButton", True)
            button.clicked.connect(
                lambda _checked=False, name=action: self.service_action_requested.emit(name)
            )
            service_actions.addWidget(button, 1)

        # One button for both directions: red "Disable" while the service runs,
        # green "Enable" while it does not.  ``_sync_service_toggle`` owns both
        # the label and which action it emits.
        self._service_toggle_action = "disable"
        self.service_toggle = QPushButton("")
        self.service_buttons["disable"] = self.service_toggle
        self.service_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.service_toggle.clicked.connect(
            lambda: self.service_action_requested.emit(self._service_toggle_action)
        )
        service_actions.addWidget(self.service_toggle, 1)
        self._sync_service_toggle(running=True)
        service_box.addLayout(service_actions)
        card.body.addWidget(service_panel)

        lab_panel, lab_box = _subpanel("")
        self.lab_panel = lab_panel
        lab_head = QHBoxLayout()
        lab_head.setSpacing(10)
        self._lab_title = lab_title = QLabel(tr("Voltage laboratory"))
        lab_title.setProperty("cardTitle", True)
        lab_head.addWidget(lab_title, 1)
        self._lab_point = QLabel("")
        self._lab_point.setProperty("rangeReadout", True)
        lab_head.addWidget(self._lab_point, 0, Qt.AlignmentFlag.AlignRight)
        lab_box.addLayout(lab_head)
        lab_box.addWidget(
            _caption("Point-by-point conservative validation of the selected range.")
        )
        lab_actions = QHBoxLayout()
        lab_actions.setSpacing(8)
        open_lab = QPushButton(tr("Open laboratory"))
        open_lab.setProperty("accentAction", True)
        open_lab.setCursor(Qt.CursorShape.PointingHandCursor)
        open_lab.clicked.connect(self.voltage_lab_requested)
        lab_actions.addWidget(open_lab, 1)
        self._open_config_button = open_config = QPushButton(tr("Open config.toml"))
        open_config.setProperty("ghostButton", True)
        open_config.setCursor(Qt.CursorShape.PointingHandCursor)
        open_config.clicked.connect(self.config_open_requested)
        lab_actions.addWidget(open_config, 1)
        lab_box.addLayout(lab_actions)
        card.body.addWidget(lab_panel)

        risk_panel, risk_box = _subpanel("")
        self._risk_panel = risk_panel
        risk_panel.setProperty("riskPanel", True)
        risk_head = QHBoxLayout()
        risk_head.setSpacing(7)
        risk_glyph = QLabel()
        risk_glyph.setPixmap(icon("warning_orange").pixmap(QSize(14, 14)))
        risk_glyph.setFixedSize(14, 16)
        risk_head.addWidget(risk_glyph, 0)
        eyebrow = QLabel(tr("DANGER ZONE"))
        eyebrow.setProperty("eyebrow", True)
        eyebrow.setProperty("danger", True)
        risk_head.addWidget(eyebrow, 1)
        self._unlock_state = _caption("")
        risk_head.addWidget(self._unlock_state, 0)
        risk_box.addLayout(risk_head)

        risk_title = QLabel(tr("TOML points above 2000 MHz"))
        risk_title.setProperty("panelHeadline", True)
        risk_title.setWordWrap(True)
        risk_box.addWidget(risk_title)
        # Interpolated, so localize_widget_tree() cannot map it back to a source
        # string: retranslate_dynamic_copy() rebuilds it on a language change.
        self._risk_caption = _caption("")
        self._refresh_risk_caption()
        risk_box.addWidget(self._risk_caption)
        self.unlock_button = QPushButton("")
        self.unlock_button.setProperty("dangerAction", True)
        self.unlock_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.unlock_button.clicked.connect(
            lambda: self.high_points_toggle_requested.emit(not self._state.unlocked)
        )
        risk_box.addWidget(self.unlock_button)
        # The mockup leaves more air above the danger zone than between the
        # neutral panels, so it reads as a separate class of control.
        card.body.addSpacing(10)
        card.body.addWidget(risk_panel)
        card.body.addStretch(1)
        return card

    # ── Advanced diagnostics ───────────────────────────────────────────────
    def _build_advanced_card(self) -> SectionCard:
        card = SectionCard(
            "Advanced GPU diagnostics",
            "TOML safe-point controls, voltage validation, hardware details, "
            "and operation output.",
            icon_name="",
        )
        # add_header_button keeps SectionCard's own bookkeeping in sync; adding
        # the widget straight into header_actions leaves the host hidden.
        self._advanced_toggle = card.add_header_button(
            "Show", lambda: None, width=104
        )
        self._advanced_toggle.setCheckable(True)
        self._advanced_toggle.setProperty("compactAction", False)
        self._advanced_toggle.setProperty("linkButton", True)
        self._advanced_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._advanced_toggle.setIcon(icon("chevron_right_gray"))
        self._advanced_toggle.setIconSize(QSize(14, 14))
        self._advanced_toggle.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._advanced_toggle.toggled.connect(self._toggle_advanced)

        self._advanced_body = QWidget()
        body = QGridLayout(self._advanced_body)
        self._advanced_grid = body
        body.setContentsMargins(0, 0, 0, 0)
        body.setHorizontalSpacing(12)
        body.setVerticalSpacing(12)

        left = QWidget()
        left_box = QVBoxLayout(left)
        left_box.setContentsMargins(0, 0, 0, 0)
        left_box.setSpacing(12)
        self._safe_point_table = SafePointTable()
        self._contract = ContractPanel()
        left_box.addWidget(self._safe_point_table)
        left_box.addWidget(self._contract)
        left_box.addStretch(1)

        self.console = OperationsConsole()
        self.console.copy_requested.connect(self.diagnostics_copy_requested)

        body.addWidget(left, 0, 0)
        body.addWidget(self.console, 0, 1)
        body.setColumnStretch(0, 13)
        body.setColumnStretch(1, 10)
        self._advanced_body.setVisible(False)
        card.root.addWidget(self._advanced_body)
        return card

    # ── live language change ───────────────────────────────────────────────
    def _refresh_risk_caption(self) -> None:
        self._risk_caption.setText(
            tr_format(
                "Uncomment the {extra_low}–{extra_high} MHz safe-points in "
                "config.toml (up to {voltage} mV). It can hang the board or "
                "corrupt the SMU state.",
                extra_low=EXTRA_POINTS[0][0],
                extra_high=ABSOLUTE_CEILING,
                voltage=EXTRA_POINTS[-1][1],
            )
        )

    def follow_hardware_again(self) -> None:
        """Called once a staged range has actually been applied."""
        self._follow_hardware = True

    def retranslate_dynamic_copy(self) -> None:
        """Re-applies the copy that ``localize_widget_tree`` cannot recover.

        Two kinds: strings already interpolated at build time (no source to map
        back to) and the fix-labels, which live in their own catalogue.
        """
        self._metrics_toggle.setText(governor_fix_label("metrics"))
        self._frequencies_toggle.setText(governor_fix_label("frequency"))
        self.set_method_combo.retranslate()
        self.usage_method_combo.retranslate()
        self._refresh_risk_caption()
        self._busy_badge.retranslate()
        self._advanced_toggle.setText(
            tr("Hide") if self._advanced_toggle.isChecked() else tr("Show")
        )
        for profile_card in self._profile_cards:
            profile_card.retranslate()
        self.apply_state(self._state)

    def _sync_service_toggle(self, *, running: bool) -> None:
        """The toggle names the action it performs, and is coloured to match."""
        self._service_toggle_action = "disable" if running else "enable"
        self.service_toggle.setText(
            tr("Stop governor") if running else tr("Start governor")
        )
        self.service_toggle.setProperty("dangerAction", running)
        self.service_toggle.setProperty("successAction", not running)
        self.service_toggle.style().unpolish(self.service_toggle)
        self.service_toggle.style().polish(self.service_toggle)

    # ── safe mode banner ───────────────────────────────────────────────────
    def _sync_safe_mode(self, state: "GpuViewState") -> None:
        """Three states, in order of what the user most needs to know.

        A stopped governor comes first: no range applies at all while it is
        down, so saying "safe mode" there would be misleading. Then the
        uncommented +2000 MHz points, then the ordinary safe state. The pill
        carries all of it, since the banner that used to repeat it was cut.
        """
        unlocked = state.unlocked
        if self._safe_pill is not None and not state.service_running:
            self._safe_pill.setText("Governor stopped — press Start governor")
            self._safe_pill.set_tone("orange")
            return
        if self._safe_pill is not None:
            self._safe_pill.setText("Extended range" if unlocked else "Safe mode")
            self._safe_pill.set_tone("red" if unlocked else "green")

    # ── Cyan compatibility ─────────────────────────────────────────────────
    def _sync_process_method_warning(self, *_args) -> None:
        self._process_method_warning.setVisible(
            self.usage_method_combo.currentData() == "process"
        )

    def _mark_compatibility_dirty(self, *_args) -> None:
        """Stops refresh() from overwriting a choice the user just made.

        Cleared by ``compatibility_options()`` once the choice is applied, and
        by ``showEvent`` when the screen is entered again — otherwise a staged
        edit that is never applied leaves the panel permanently disagreeing
        with config.toml.
        """
        self._compatibility_dirty = True

    def compatibility_options(self) -> dict:
        self._compatibility_dirty = False
        return {
            "set_method": str(self.set_method_combo.currentData() or "smu"),
            "usage_method": str(self.usage_method_combo.currentData() or "busy-flag"),
            "metrics": self._metrics_toggle.isChecked(),
            "frequencies": self._frequencies_toggle.isChecked(),
        }

    def _sync_compatibility(self, state: "GpuViewState") -> None:
        if self._compatibility_dirty:
            return
        widgets = (
            self.set_method_combo,
            self.usage_method_combo,
            self._metrics_toggle,
            self._frequencies_toggle,
        )
        blocked = tuple(widget.blockSignals(True) for widget in widgets)
        try:
            set_index = self.set_method_combo.findData(state.set_method)
            usage_index = self.usage_method_combo.findData(state.usage_method)
            self.set_method_combo.setCurrentIndex(max(0, set_index))
            self.usage_method_combo.setCurrentIndex(max(0, usage_index))
            self._metrics_toggle.setChecked(state.fix_metrics)
            self._frequencies_toggle.setChecked(state.fix_frequency)
        finally:
            for widget, previous in zip(widgets, blocked, strict=True):
                widget.blockSignals(previous)
        self._sync_process_method_warning()

    # ── interaction ────────────────────────────────────────────────────────
    def _toggle_advanced(self, checked: bool) -> None:
        self._advanced_body.setVisible(checked)
        self._advanced_toggle.setText(tr("Hide") if checked else tr("Show"))

    def _on_profile_selected(self, profile: GpuProfile) -> None:
        # Same staging protection as the rail: otherwise the next telemetry
        # refresh calls sync_active_range() and snaps the card back to
        # whatever the hardware still reports, before the user gets to Apply.
        self._follow_hardware = False
        self._selected_profile = profile.key
        self._selected_minimum = profile.minimum
        self._selected_maximum = profile.maximum
        self._sync_selection()

    def _on_profile_changed(self, profile: GpuProfile) -> None:
        if profile.key == self._selected_profile:
            self._selected_minimum = profile.minimum
            self._selected_maximum = profile.maximum
        self._sync_selection()
        self.profile_changed.emit(profile)

    def _on_rail_changed(self, minimum: int, maximum: int) -> None:
        self._follow_hardware = False
        self._selected_minimum, self._selected_maximum = minimum, maximum
        self._selected_profile = self._profile_key_for(minimum, maximum)
        self._sync_selection()

    def _profile_key_for(self, minimum: int, maximum: int) -> str:
        for profile_card in self._profile_cards:
            profile = profile_card.profile
            if (profile.minimum, profile.maximum) == (minimum, maximum):
                return profile.key
        return "custom"

    def _selected_profile_name(self) -> str:
        for profile_card in self._profile_cards:
            if profile_card.profile.key == self._selected_profile:
                return profile_card.profile.name
        return tr("Custom")

    def _confirm_and_apply(self) -> None:
        minimum, maximum = self._selected_minimum, self._selected_maximum
        risky = maximum > SAFE_CEILING
        message = tr(
            "The governor rewrites the range over D-Bus and saves persistence. "
            "If the board hangs, it reverts to the last valid range on reboot."
        )
        if risky:
            message += "\n\n" + tr_format(
                "You are above the safe ceiling ({ceiling} MHz). The board may "
                "hang and need a cold reboot.",
                ceiling=SAFE_CEILING,
            )
            if self._state.set_method == "kernel":
                # amdgpu publishes an OD_RANGE the kernel path cannot exceed
                # (2000 MHz on a stock BC-250 driver), so the request would be
                # refused after the TOML had already been written.
                message += "\n\n" + tr(
                    "The Kernel method cannot go past 2000 MHz on a stock "
                    "BC-250 driver. Switch the governor method to SMU, or use "
                    "a patched kernel."
                )
        dialog = ConfirmDialog(
            tr_format("Apply {minimum} – {maximum} MHz", minimum=minimum, maximum=maximum),
            message,
            summary=(
                ("Profile", self._selected_profile_name()),
                ("Voltage", f"{backend_voltage_for(maximum, is_oberon=self._oberon_mode)} mV"),
                # Named explicitly: this is the TOML's ceiling, not the range
                # being applied, and reading it as the latter is confusing.
                ("TOML ceiling", f"{ceiling_for(unlocked=self._state.unlocked)} MHz"),
            ),
            confirm_text="Apply now",
            eyebrow="CONFIRM HARDWARE ACTION",
            tone="red" if risky else "blue",
            parent=self,
        )
        if dialog.exec():
            self.range_apply_requested.emit(minimum, maximum)

    # ── backend inputs ─────────────────────────────────────────────────────
    def set_profiles(self, profiles: Sequence[GpuProfile]) -> None:
        """Applies profiles saved by the user, in order."""
        for profile_card, profile in zip(self._profile_cards, profiles):
            profile_card.set_profile(profile)
        self._sync_selection()

    def set_oberon_mode(self, is_oberon: bool) -> None:
        """Dress this same screen for the Oberon backend.

        Oberon is not a reduced Cyan: it has two YAML endpoints instead of a
        multi-point TOML curve, no kernel compatibility switches, and no
        commented-out points to uncomment. So the panels that only describe
        Cyan's model are hidden rather than shown empty or, worse, shown with
        Cyan's numbers over an Oberon board.

        Everything the two backends genuinely share — profiles, telemetry, the
        service controls, the voltage laboratory — keeps the same layout and
        the same button positions, which is the point of reusing this view.
        """
        is_oberon = bool(is_oberon)
        if is_oberon == self._oberon_mode:
            return
        self._oberon_mode = is_oberon

        # Cyan's frequency model, in three panels that Oberon has no analogue for.
        self._range_panel.setVisible(not is_oberon)
        self._compat_panel.setVisible(not is_oberon)
        self._risk_panel.setVisible(not is_oberon)
        # The range state and the busy ring live in the Cyan compatibility
        # heading; with that panel gone they go up beside the profiles.
        self._place_status(self._profiles_title_row if is_oberon else self._compat_title_row)

        for profile_card in self._profile_cards:
            profile_card.set_editable(not is_oberon)
        # Oberon's three profiles are fixed by the shared contract and Decky
        # already ships the matching oberon-1500/1850/2000 buttons; there is
        # nothing user-edited here to export.
        self._export_decky_button.setVisible(not is_oberon)

        # The backend refuses startup persistence for Oberon outright
        # (``guardar_rango_gpu_arranque`` raises), so offering it would be a
        # button whose only outcome is an error.
        self.startup_button.setVisible(not is_oberon)
        self.apply_button.setText(
            tr("Review and apply Oberon profile") if is_oberon
            else tr("Review and apply range")
        )
        self._lab_title.setText(
            tr("YAML endpoint laboratory") if is_oberon else tr("Voltage laboratory")
        )
        self._open_config_button.setText(
            tr("Open oberon-config.yaml") if is_oberon else tr("Open config.toml")
        )

    def _place_status(self, row: QHBoxLayout) -> None:
        widgets = [w for w in (self._safe_pill, self._busy_badge) if w is not None]
        for widget in widgets:
            for layout in (self._profiles_title_row, self._compat_title_row):
                layout.removeWidget(widget)
        # After the heading and its stretch, ahead of any action on the row.
        position = 2 if row is self._profiles_title_row else 1
        for offset, widget in enumerate(widgets):
            row.insertWidget(position + offset, widget, 0, Qt.AlignmentFlag.AlignVCenter)
        # A widget handed to another parent comes back hidden; restore the
        # one of the two that should be showing.
        busy = self._operation_busy
        self._busy_badge.setVisible(busy)
        if self._safe_pill is not None:
            self._safe_pill.setVisible(not busy)

    def profiles(self) -> tuple[GpuProfile, ...]:
        return tuple(profile_card.profile for profile_card in self._profile_cards)

    def selected_range(self) -> tuple[int, int]:
        return self._selected_minimum, self._selected_maximum

    def set_operation_busy(self, active: bool, text: str) -> None:
        """A small ring in the status pill's place while hardware work runs."""
        self._operation_busy = bool(active)
        self._busy_badge.set_text(text)
        self._busy_badge.set_running(active)
        if self._safe_pill is not None:
            self._safe_pill.setVisible(not active)

    def apply_state(self, state: GpuViewState) -> None:
        self._state = state
        unlocked = state.unlocked

        self._tiles["core"].set_values(f"{state.core_clock} MHz")
        self._tiles["voltage"].set_values(f"{state.voltage} mV")
        self._tiles["temperature"].set_values(
            f"{state.temperature:.1f} °C",
            temperature_detail(state.temperature),
        )
        self._tiles["load"].set_values(f"{state.load} %")
        self._tiles["memory"].set_values(f"{state.memory_clock} MHz")
        range_known = state.active_minimum > 0 and state.active_maximum > 0
        stalled = state.dbus_responsive is False
        # 0–0 MHz read as a real range; it only ever meant "not read".
        self._tiles["range"].set_values(
            f"{state.active_minimum}–{state.active_maximum} MHz" if range_known else "--",
            "Cyan is not answering" if stalled and not range_known else "Persisted on hardware",
        )
        if stalled:
            self._bus_notice.setText(
                tr(
                    "Cyan is running but not answering. Its usage reading is set to process, "
                    "which reads every open file of every program; a Proton game keeps tens of "
                    "thousands open. Choose busy-flag in Cyan kernel compatibility and apply."
                )
                if state.usage_method == "process"
                else tr(
                    "Cyan is running but not answering on D-Bus, so its range cannot be read or "
                    "changed right now. Restart the governor if it does not recover."
                )
            )
        self._bus_notice.setVisible(stalled)

        self._sync_service_toggle(running=state.service_running)

        self._unlock_state.setText(tr("Enabled") if unlocked else tr("Locked"))
        self.unlock_button.setText(
            tr("Re-comment the +2000 MHz points")
            if unlocked
            else tr("Uncomment +2000 MHz points")
        )
        self._locked_label.setText(
            ""
            if unlocked
            else tr_format(
                "{minimum}–{maximum} MHz COMMENTED IN THE TOML",
                minimum=EXTRA_POINTS[0][0],
                maximum=ABSOLUTE_CEILING,
            )
        )

        self._sync_safe_mode(state)
        self._sync_compatibility(state)
        self._rail.set_unlocked(unlocked)
        for profile_card in self._profile_cards:
            profile_card.set_unlocked(unlocked)
        self._sync_selection()

    def sync_active_range(self, minimum: int, maximum: int) -> None:
        """Aligns the selection with the range the hardware reports.

        Ignored while the user is staging a range of their own — otherwise the
        next refresh would snap the rail back to the active range mid-edit.
        Re-entering the screen (``showEvent``) resumes following the hardware.
        """
        if not self._follow_hardware:
            return
        if minimum and maximum:
            self._selected_minimum, self._selected_maximum = minimum, maximum
            self._selected_profile = self._profile_key_for(minimum, maximum)
            self._sync_selection()

    def _sync_selection(self) -> None:
        unlocked = self._state.unlocked
        ceiling = ceiling_for(unlocked=unlocked)
        self._selected_maximum = min(self._selected_maximum, ceiling)
        self._selected_minimum = min(self._selected_minimum, self._selected_maximum)

        self._rail.set_range(self._selected_minimum, self._selected_maximum)
        self._range_readout.setText(
            f"{self._selected_minimum} – {self._selected_maximum} MHz"
        )
        self._range_subtitle.setText(
            tr_format(
                "Fine-tune over the TOML points · current ceiling {ceiling} MHz.",
                ceiling=ceiling,
            )
        )
        self._minimum_line.set_values(str(self._selected_minimum))
        self._maximum_line.set_values(
            str(self._selected_maximum),
            tr_format("Current ceiling {ceiling} MHz per config.toml.", ceiling=ceiling),
        )
        self._lab_point.setText(
            f"{self._selected_maximum} MHz · "
            f"{backend_voltage_for(self._selected_maximum, is_oberon=self._oberon_mode)} mV"
        )

        for profile_card in self._profile_cards:
            profile_card.set_active(profile_card.profile.key == self._selected_profile)

        self._safe_point_table.refresh(
            self._selected_minimum,
            self._selected_maximum,
            unlocked=unlocked,
            points=self._state.safe_points,
        )
        active = sum(
            1 for frequency, _v in self._state.safe_points if frequency <= ceiling
        )
        self._contract.set_rows(
            (
                ("Device", self._state.device),
                ("Governor", self._state.backend),
                ("Accepted range", f"{self._selected_minimum} – {self._selected_maximum} MHz"),
                ("Allowed ceiling", f"{ceiling} MHz"),
                (
                    "Active points",
                    tr_format(
                        "{active} of {total} in config.toml",
                        active=active,
                        total=len(self._state.safe_points),
                    ),
                ),
                (
                    "D-Bus API",
                    tr("Connected · range running")
                    if self._state.dbus_connected
                    else tr("Not connected"),
                ),
                ("Configuration", self._state.config_path),
            )
        )

    def set_console_lines(self, lines: Iterable[str]) -> None:
        self.console.set_lines(lines)

    def append_console_line(self, line: str) -> None:
        self.console.append(line)

    def console_text(self) -> str:
        return self.console.text()

    # ── lifecycle ──────────────────────────────────────────────────────────
    def showEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().showEvent(event)
        # Coming back to the screen is the moment to trust the hardware again —
        # for the rail and for the compatibility controls alike. Without this,
        # one click on a check box latched _compatibility_dirty forever and the
        # panel kept showing values config.toml no longer had.
        self._follow_hardware = True
        self._compatibility_dirty = False
        self.sync_active_range(self._state.active_minimum, self._state.active_maximum)
        self._sync_compatibility(self._state)

    # ── reflow ─────────────────────────────────────────────────────────────
    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().resizeEvent(event)
        self._reflow(self.width())

    def _reflow(self, width: int) -> None:
        stacked = width < 1180
        telemetry_stacked = self._workspace.itemAtPosition(1, 0) is not None
        if stacked and not telemetry_stacked:
            self._workspace.removeWidget(self._telemetry)
            self._workspace.addWidget(self._telemetry, 1, 0)
            self._workspace.setColumnStretch(1, 0)
        elif not stacked and telemetry_stacked:
            self._workspace.removeWidget(self._telemetry)
            self._workspace.addWidget(self._telemetry, 0, 1)
            self._workspace.setColumnStretch(1, 12)

        console_stacked = self._advanced_grid.itemAtPosition(1, 0) is not None
        if stacked and not console_stacked:
            self._advanced_grid.removeWidget(self.console)
            self._advanced_grid.addWidget(self.console, 1, 0)
            self._advanced_grid.setColumnStretch(1, 0)
        elif not stacked and console_stacked:
            self._advanced_grid.removeWidget(self.console)
            self._advanced_grid.addWidget(self.console, 0, 1)
            self._advanced_grid.setColumnStretch(1, 10)

        columns = 1 if width < 700 else 3
        current = 1 if self._profiles_grid.itemAtPosition(1, 0) is not None else 3
        if columns != current:
            for index, profile_card in enumerate(self._profile_cards):
                self._profiles_grid.removeWidget(profile_card)
                row, column = (index, 0) if columns == 1 else (0, index)
                self._profiles_grid.addWidget(profile_card, row, column)


# ─────────────────────────────────────────────────────────────────────────────
# Standalone preview — python -m frontends.desktop.pages.gpu_governor_view
# ─────────────────────────────────────────────────────────────────────────────

def _demo() -> None:  # pragma: no cover
    """Bring the screen up with simulated telemetry, no hardware required."""
    import random
    import sys

    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication

    from ..theme import application_stylesheet, configure_theme

    app = QApplication(sys.argv)
    mode = "dark" if "--light" not in sys.argv else "light"
    configure_theme(mode=mode, accent="cyan")
    app.setStyleSheet(application_stylesheet(mode=mode, accent="cyan"))

    view = GpuGovernorView()
    # The page property is what the GPU-specific stylesheet rules key off.
    view.setProperty("redesignedModule", True)
    view.resize(1600, 980)
    # An f-string keeps this developer-only title out of the i18n catalogs.
    view.setWindowTitle(f"BC250 · GPU module ({mode} preview)")
    view.set_console_lines(
        (
            "10:41:58 governor → cyan-skillfish-governor-smu ready",
            f"10:41:58 toml → {len(SAFE_POINTS)} safe-points loaded",
            "10:42:06 dbus → SetRange(1000, 1850)",
            "10:42:06 ok range accepted · max 1850 MHz",
        )
    )
    view.show()

    def tick() -> None:
        minimum, maximum = view.selected_range()
        view.apply_state(
            replace(
                view._state,
                core_clock=snap_to_point(
                    random.randint(FLOOR, maximum), unlocked=view._state.unlocked
                ),
                voltage=voltage_for(maximum),
                temperature=48 + random.random() * 30,
                load=random.randint(1, 7),
                memory_clock=450,
                active_minimum=minimum,
                active_maximum=maximum,
                service_running=True,
                service_persistent=True,
                dbus_connected=True,
            )
        )

    timer = QTimer(view)
    timer.timeout.connect(tick)
    timer.start(1600)
    tick()

    view.range_apply_requested.connect(
        lambda low, high: view.append_console_line(f"dbus → SetRange({low}, {high})")
    )
    view.high_points_toggle_requested.connect(
        lambda enabled: (
            view.apply_state(replace(view._state, unlocked=enabled)),
            view.append_console_line(
                f"toml → +2000 points {'uncommented' if enabled else 'commented out'}"
            ),
        )
    )
    sys.exit(app.exec())


if __name__ == "__main__":  # pragma: no cover
    _demo()
