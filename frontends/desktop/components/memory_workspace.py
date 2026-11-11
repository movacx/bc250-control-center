"""Memory & Swap as three independent settings, each a set of options to pick from.

Swap and compression is a compact list, one policy a line; the GPU memory
limit (TTM) and the VRAM size are rails of sizes, like the GPU range rail.
Each section has its own Apply. The rows and rails only present the panel's
own combo boxes, which stay the record:
they are what the apply requests read and what the render code enables,
disables and fills, so nothing behind the page changed.
"""

from __future__ import annotations

from collections.abc import Mapping

from pathlib import Path

from PyQt6.QtCore import QEvent, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen
from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ..i18n import tr
from ..theme import COLORS


def adopt_button(button, kind: str = "secondary"):
    """One of the panel's buttons, in this page's flat style."""
    for name in ("dashboardCardAction", "accented", "linkAction"):
        button.setProperty(name, False)
    button.setProperty("memoryButton", kind)
    button.setIcon(QIcon())
    button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    button.style().unpolish(button)
    button.style().polish(button)
    return button


def _repolish(widget: QWidget, name: str, value) -> None:
    if widget.property(name) != value:
        widget.setProperty(name, value)
        widget.style().unpolish(widget)
        widget.style().polish(widget)


def _color(name: str, alpha: int = 255) -> QColor:
    color = QColor(COLORS.get(name, name))
    color.setAlpha(alpha)
    return color


class ComboRail(QWidget):
    """The sizes of a combo box as stops on a rail, like the GPU range rail.

    Only the items whose data is a positive size become stops; picking one
    sets the combo. Stops the panel disabled are drawn dimmed and cannot be
    picked. ``current`` marks what the system uses now.
    """

    _TICK_TOP = 4
    _TICK_TALL = 18
    _TICK_SHORT = 13
    _RAIL_Y = 20
    _LABEL_ROW_A = 38
    _LABEL_ROW_B = 58
    _LABEL_HEIGHT = 18
    _MARGIN = 34

    def __init__(self, combo, label_for, unit_mb: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.combo = combo
        self.label_for = label_for
        self.unit_mb = unit_mb
        self.current_mb: float | None = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        combo.currentIndexChanged.connect(lambda _index: self.update())
        self._dragging = False
        self._fit_height()

    def _staggered(self) -> bool:
        return len(self.stops()) > 6

    def _fit_height(self) -> None:
        """Room for one row of sizes, two only when they alternate."""
        bottom = (self._LABEL_ROW_B if self._staggered() else self._LABEL_ROW_A) + self._LABEL_HEIGHT
        self.setFixedHeight(bottom + 2)

    def stops(self) -> list[tuple[int, int, bool]]:
        """(combo index, size, enabled) for every size item."""
        result = []
        model = self.combo.model()
        for index in range(self.combo.count()):
            value = self.combo.itemData(index)
            if type(value) is int and value > 0:
                item = model.item(index) if hasattr(model, "item") else None
                enabled = self.combo.isEnabled() and (item is None or item.isEnabled())
                result.append((index, value, enabled))
        return result

    def _x_for_position(self, position: float, count: int) -> float:
        usable = max(1, self.width() - self._MARGIN * 2)
        return self._MARGIN + usable * (position / max(1, count - 1))

    def _position_of(self, size_mb: float, values: list[int]) -> float:
        """Index along the rail, interpolated between stops (sizes, in MB)."""
        sizes = [value * self.unit_mb for value in values]
        if size_mb <= sizes[0]:
            return 0.0
        for index in range(1, len(sizes)):
            if size_mb <= sizes[index]:
                span = sizes[index] - sizes[index - 1] or 1
                return index - 1 + (size_mb - sizes[index - 1]) / span
        return float(len(sizes) - 1)

    def _pick(self, x: float) -> None:
        stops = self.stops()
        choices = [(abs(self._x_for_position(i, len(stops)) - x), stop) for i, stop in enumerate(stops) if stop[2]]
        if choices:
            self.combo.setCurrentIndex(min(choices, key=lambda pair: pair[0])[1][0])

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self._dragging = True
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self._pick(event.position().x())

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if self._dragging:
            self._pick(event.position().x())

    def mouseReleaseEvent(self, _event) -> None:  # noqa: N802 - Qt API name
        self._dragging = False

    def step(self, delta: int) -> None:
        enabled = [stop for stop in self.stops() if stop[2]]
        if not enabled:
            return
        indexes = [stop[0] for stop in enabled]
        current = self.combo.currentIndex()
        if current in indexes:
            target = indexes[max(0, min(len(indexes) - 1, indexes.index(current) + delta))]
        else:
            target = indexes[0 if delta > 0 else -1]
        self.combo.setCurrentIndex(target)

    def gamepad_direction(self, direction: str) -> bool:
        if direction not in {"left", "right"}:
            return False
        self.step(-1 if direction == "left" else 1)
        return True

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self.step(-1 if event.key() == Qt.Key.Key_Left else 1)
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API name
        stops = self.stops()
        if not stops:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        count = len(stops)
        left, right = self._x_for_position(0, count), self._x_for_position(count - 1, count)
        painter.setBrush(_color("border_strong"))
        painter.drawRoundedRect(QRectF(left, self._RAIL_Y, right - left, 4), 2, 2)

        selected = next((i for i, stop in enumerate(stops) if stop[0] == self.combo.currentIndex()), None)
        if selected is not None:
            painter.setBrush(_color("blue"))
            painter.drawRoundedRect(QRectF(left, self._RAIL_Y, max(3, self._x_for_position(selected, count) - left), 4), 2, 2)

        font = painter.font()
        font.setPointSizeF(font.pointSizeF() + 0.5)
        painter.setFont(font)
        for position, (_index, value, enabled) in enumerate(stops):
            x = self._x_for_position(position, count)
            inside = selected is not None and position <= selected
            if not enabled:
                tick, text = _color("border_strong"), _color("subtle")
            elif inside:
                tick, text = _color("blue"), _color("text")
            else:
                tick, text = _color("muted"), _color("muted")
            staggered = self._staggered() and position % 2 == 1
            painter.setBrush(tick)
            painter.drawRoundedRect(QRectF(x - 1, self._TICK_TOP, 2, self._TICK_SHORT if staggered else self._TICK_TALL), 1, 1)
            painter.setPen(text)
            row = self._LABEL_ROW_B if staggered else self._LABEL_ROW_A
            painter.drawText(QRectF(x - 40, row, 80, self._LABEL_HEIGHT), Qt.AlignmentFlag.AlignCenter, self.label_for(value))
            painter.setPen(Qt.PenStyle.NoPen)

        # What the system uses now: a small open ring on the rail.
        if self.current_mb:
            x = self._x_for_position(self._position_of(self.current_mb, [stop[1] for stop in stops]), count)
            painter.setPen(QPen(_color("green"), 2))
            painter.setBrush(_color("panel"))
            painter.drawEllipse(QRectF(x - 4, self._RAIL_Y - 2, 8, 8))
            painter.setPen(Qt.PenStyle.NoPen)

        if selected is not None:
            x = self._x_for_position(selected, count)
            handle = QRectF(x - 7.5, self._RAIL_Y - 8, 15, 20)
            if self.hasFocus():
                painter.setPen(QPen(_color("focus"), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(handle.adjusted(-3.5, -3.5, 3.5, 3.5), 7, 7)
            painter.setPen(_color("blue"))
            painter.setBrush(_color("blue"))
            painter.drawRoundedRect(handle, 5, 5)
        painter.end()

    def focusInEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().focusOutEvent(event)
        self.update()


class ComboChoices(QWidget):
    """The combo's items that are not sizes (keep, restore), as plain buttons."""

    def __init__(self, combo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from PyQt6.QtWidgets import QPushButton

        self.combo = combo
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.buttons = []
        for index in range(combo.count()):
            value = combo.itemData(index)
            if type(value) is int and value > 0:
                continue
            button = QPushButton(combo.itemText(index))
            button.setCheckable(True)
            button.setProperty("memoryChoice", True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, i=index: self.combo.setCurrentIndex(i))
            layout.addWidget(button)
            self.buttons.append((index, button))
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        combo.currentIndexChanged.connect(lambda _index: self.refresh())
        self.refresh()

    def refresh(self) -> None:
        model = self.combo.model()
        for index, button in self.buttons:
            button.setText(self.combo.itemText(index))
            button.setChecked(index == self.combo.currentIndex())
            item = model.item(index) if hasattr(model, "item") else None
            button.setEnabled(self.combo.isEnabled() and (item is None or item.isEnabled()))


class _Radio(QWidget):
    """A round radio mark, painted so it is a circle at every scale."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.selected = False
        self.setFixedSize(19, 19)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(1.5, 1.5, self.width() - 3, self.height() - 3)
        enabled = self.isEnabled()
        if self.selected:
            painter.setPen(QPen(_color("blue"), 1.8))
            painter.setBrush(_color("panel"))
            painter.drawEllipse(rect)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_color("blue"))
            painter.drawEllipse(rect.adjusted(3.5, 3.5, -3.5, -3.5))
        else:
            painter.setPen(QPen(_color("muted" if enabled else "subtle"), 1.6))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect)
        painter.end()


class _ListRow(QFrame):
    """One policy on one line: a radio mark, its name, a short note at the right."""

    TITLE_WIDTH = 470

    clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("memoryListRow", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 14, 10)
        layout.setSpacing(14)
        self.mark = _Radio()
        layout.addWidget(self.mark, 0, Qt.AlignmentFlag.AlignVCenter)
        # Two columns, as a table reads: the name, then what it does.
        self.title = QLabel("")
        self.title.setProperty("memoryOptionTitle", True)
        self.title.setFixedWidth(self.TITLE_WIDTH)
        layout.addWidget(self.title)
        self.note = QLabel("")
        self.note.setProperty("memoryOptionDetail", True)
        self.note.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.note.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.note, 1)

    def set_content(self, title: str, note: str) -> None:
        self.title.setText(title)
        self._note = note
        self.setToolTip(note)
        self._elide()

    def _elide(self) -> None:
        width = max(40, self.note.width())
        self.note.setText(self.note.fontMetrics().elidedText(getattr(self, "_note", ""), Qt.TextElideMode.ElideRight, width))

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._elide()

    def set_selected(self, selected: bool) -> None:
        self.mark.selected = selected
        self.mark.update()
        for widget in (self, self.title, self.note):
            _repolish(widget, "selected", selected)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.clicked.emit()
        super().mousePressEvent(event)

    def gamepad_activate(self) -> None:
        if self.isEnabled():
            self.clicked.emit()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.gamepad_activate()
            event.accept()
            return
        super().keyPressEvent(event)


class SwapList(QWidget):
    """Every swap policy as one line of a compact list, bound to the policy combo."""

    def __init__(self, combo, details, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.combo = combo
        self.details = details
        combo.hide()
        self.rows: list[_ListRow] = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        table = QFrame()
        table.setProperty("memoryTable", True)
        outer.addWidget(table)
        self.layout_ = QVBoxLayout(table)
        self.layout_.setContentsMargins(0, 0, 0, 0)
        self.layout_.setSpacing(0)
        # Column headings, as the Fans and Processes tables have them.
        header = QFrame()
        header.setProperty("memoryTableHeader", True)
        head = QHBoxLayout(header)
        head.setContentsMargins(12 + 19 + 14, 7, 14, 7)
        head.setSpacing(14)
        option = QLabel(tr("Option").upper())
        option.setProperty("memoryTableHeading", True)
        option.setFixedWidth(_ListRow.TITLE_WIDTH)
        description = QLabel(tr("Description").upper())
        description.setProperty("memoryTableHeading", True)
        head.addWidget(option)
        head.addWidget(description, 1)
        self.layout_.addWidget(header)
        combo.currentIndexChanged.connect(lambda _index: self.refresh())
        self.refresh()

    def add_footer(self, footer: QWidget, follows: QWidget) -> None:
        """A last row that shows while ``follows`` is shown."""
        self._footer, self._follows = footer, follows
        self.layout_.addWidget(footer)
        follows.installEventFilter(self)
        footer.setVisible(not follows.isHidden())
        self.refresh()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API name
        if watched is getattr(self, "_follows", None) and event.type() in (
            QEvent.Type.ShowToParent, QEvent.Type.HideToParent, QEvent.Type.Show, QEvent.Type.Hide,
        ):
            self._footer.setVisible(not watched.isHidden())
            self.refresh()
        return super().eventFilter(watched, event)

    def refresh(self) -> None:
        combo = self.combo
        while len(self.rows) < combo.count():
            row = _ListRow()
            index = len(self.rows)
            row.clicked.connect(lambda i=index: self.combo.setCurrentIndex(i))
            footer = getattr(self, "_footer", None)
            # New rows go above the footer, which stays the table's last row.
            position = self.layout_.indexOf(footer) if footer is not None else -1
            self.layout_.insertWidget(position if position >= 0 else self.layout_.count(), row)
            self.rows.append(row)
        while len(self.rows) > combo.count():
            row = self.rows.pop()
            self.layout_.removeWidget(row)
            row.deleteLater()
        model = combo.model()
        for index, row in enumerate(self.rows):
            value = str(combo.itemData(index) or "")
            row.set_content(combo.itemText(index), tr(self.details.get(value, "")))
            row.set_selected(index == combo.currentIndex())
            item = model.item(index) if hasattr(model, "item") else None
            row.setEnabled(combo.isEnabled() and (item is None or item.isEnabled()))
            _repolish(row, "alternate", index % 2 == 1)
            footer = getattr(self, "_footer", None)
            footer_shown = footer is not None and not footer.isHidden()
            _repolish(row, "last", index == len(self.rows) - 1 and not footer_shown)


def _gib_label(value: int) -> str:
    return f"{value} GiB"


def _mib_label(value: int) -> str:
    return f"{value} MiB" if value < 1024 else f"{value // 1024} GiB"


def read_vram_total_mb(base: Path = Path("/sys/class/drm")) -> float | None:
    for card in sorted(base.glob("card[0-9]*")):
        try:
            return int((card / "device" / "mem_info_vram_total").read_text(encoding="ascii")) / (1024 ** 2)
        except (OSError, ValueError):
            continue
    return None


class _Section(QFrame):
    """A setting: its name and state, its Apply button, its options."""

    def __init__(self, title: str, note: QLabel | None, button, options: QWidget, parent=None,
                 *, extra=()) -> None:
        super().__init__(parent)
        self.setProperty("memorySection", True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 16, 22, 14)
        layout.setSpacing(12)
        head = QHBoxLayout()
        head.setSpacing(12)
        copy = QVBoxLayout()
        copy.setSpacing(3)
        name = QLabel(tr(title))
        name.setProperty("memorySectionTitle", True)
        copy.addWidget(name)
        if note is not None:
            note.setProperty("memorySectionNote", True)
            note.setWordWrap(True)
            copy.addWidget(note)
        head.addLayout(copy, 1)
        for widget in extra:
            head.addWidget(widget, 0, Qt.AlignmentFlag.AlignTop)
        head.addWidget(adopt_button(button, "primary"), 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(head)
        layout.addWidget(options)


class MemoryWorkspace(QWidget):
    """Swap, TTM and VRAM, one section each, each applied on its own."""

    def __init__(self, owner, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from .dashboard_widgets import _MEMORY_POLICY_DETAILS

        self.setProperty("memoryWorkspace", True)
        self._owner = owner
        self._runtime: Mapping[str, object] = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        # What the kernel has on now, then the full report.
        owner.memory_detail.hide()
        # The "Testing" tag said nothing a reader can act on.
        owner.memory_scope.hide()

        self.swap_cards = SwapList(owner.memory_policy_combo, _MEMORY_POLICY_DETAILS)
        swap_options = QWidget()
        swap_layout = QVBoxLayout(swap_options)
        swap_layout.setContentsMargins(0, 0, 0, 0)
        swap_layout.setSpacing(10)
        swap_layout.addWidget(self.swap_cards)
        # Shown by the panel only for a policy that creates a swap file.
        # Where the swap file goes: the table's last row, shown only for a
        # policy that creates one. The ZRAM note is not drawn; the apply
        # workflow says it before changing anything.
        footer = QFrame()
        footer.setProperty("memoryTableFooter", True)
        location = QHBoxLayout(footer)
        location.setContentsMargins(12 + 19 + 14, 8, 14, 8)
        location.setSpacing(14)
        label = owner.memory_swap_target_label
        label.setProperty("dashboardMemoryControlLabel", False)
        label.setProperty("memoryOptionTitle", True)
        label.setWordWrap(False)
        label.setFixedWidth(_ListRow.TITLE_WIDTH)
        location.addWidget(label)
        owner.memory_swap_target_combo.setProperty("memoryField", True)
        owner.memory_swap_target_combo.setFixedWidth(340)
        location.addWidget(owner.memory_swap_target_combo)
        location.addStretch(1)
        self.swap_cards.add_footer(footer, owner.memory_swap_target_combo)
        # Kept in the panel's hidden holder: the render code still sets its
        # text and visibility, and it must never become a window of its own.
        holder = getattr(owner, "_memory_holder", None)
        if holder is not None:
            holder.layout().addWidget(owner.memory_zram_warning_frame)
        # The detailed report sits beside Apply: it is about what Apply changes.
        root.addWidget(_Section("Swap and compression", None, owner.memory_swap_apply_button, swap_options,
                                extra=(adopt_button(owner.memory_status_button),)))

        owner.ttm_limit_combo.hide()
        self.ttm_rail = ComboRail(owner.ttm_limit_combo, _gib_label, 1024)
        self.ttm_choices = ComboChoices(owner.ttm_limit_combo)
        root.addWidget(_Section("Dynamic GPU Memory Limit (TTM)", owner.memory_ttm_state,
                                owner.memory_ttm_apply_button, self.ttm_rail, extra=(self.ttm_choices,)))

        owner.vram_size_combo.hide()
        self.vram_rail = ComboRail(owner.vram_size_combo, _mib_label, 1)
        self.vram_rail.current_mb = read_vram_total_mb()
        self.vram_choices = ComboChoices(owner.vram_size_combo)
        root.addWidget(_Section("VRAM size (UMA_SIZE)", QLabel(tr("A reboot may be required.")),
                                owner.vram_apply_button, self.vram_rail, extra=(self.vram_choices,)))
        root.addStretch(1)

    def _refresh_cards(self) -> None:
        self.swap_cards.refresh()
        for widget in (self.ttm_choices, self.vram_choices):
            widget.refresh()
        for rail in (self.ttm_rail, self.vram_rail):
            rail.update()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().showEvent(event)
        self._refresh_cards()

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().changeEvent(event)
        if event.type() == QEvent.Type.StyleChange:
            self.set_runtime(self._runtime)

    def set_runtime(self, runtime: Mapping[str, object]) -> None:
        """Light the three words at the top, and follow what the panel enabled."""
        runtime = runtime or {}
        self._runtime = runtime
        ttm = runtime.get("ttm_limit_bytes")
        self.ttm_rail.current_mb = ttm / (1024 ** 2) if isinstance(ttm, int) and ttm > 0 else None
        self._refresh_cards()
