"""Choosing what to install, as tiles rather than a list of checkboxes.

The first run asks for four preferences and then, at the end, for the one
thing that actually takes time. A row of checkboxes would have been the
cheapest way to ask; it would also have been the least informative, because
these seven are not equivalent. One is required and touches nothing. One
replaces a kernel. The rest sit between, and the difference matters more here
than anywhere else in the application — this is the screen where somebody
meets the board for the first time.

So each one is a tile that says what it is and what it is for, and anything
already on the machine says so instead of offering to be installed again. They
arrive in sequence rather than all at once, which gives the eye somewhere to
start. What each one costs is explained where it is decided — on the dashboard
panel that runs them — rather than compressed into a badge on a first-run
screen, where a red word beside a name is a warning nobody can act on yet.

Labels come from the dashboard's own preparation panel. There is one list of
components in this application and this is not a second copy of it.
"""

from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QGridLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import theme as theme_module
from ..i18n import tr

#: Bento proportions, scaled to a panel rather than a marketing page.
TILE_RADIUS = 13.0
TILE_HEIGHT = 86
GRID_GAP = 9
#: Micro-interaction timings: quick enough to feel like feedback, slow enough
#: to be seen.
HOVER_MS = 110
ENTRANCE_MS = 260
#: How far apart the tiles start moving. Seven of these is under half a
#: second in total, which is a flourish rather than a wait.
ENTRANCE_STAGGER_MS = 45


def component_specs() -> tuple[dict, ...]:
    """The installable components, from the dashboard's own list.

    Labels and one-line details come from the preparation panel, and whether a
    component is required comes from the application layer that decides it.
    Nothing here is a second opinion about either.
    """
    from bc250cc.application.preparation.component_engine import COMPONENT_SPECS

    from ..components.dashboard_widgets import PreparationSidebar

    specs = []
    for key, label, detail in PreparationSidebar.COMPONENTS:
        rules = COMPONENT_SPECS.get(key)
        specs.append({
            "key": key,
            # tr() on a value rather than a literal: these strings are already
            # catalogued where the dashboard declares them.
            "label": tr(label),
            "detail": tr(detail),
            "required": bool(getattr(rules, "required", False)),
        })
    return tuple(specs)


class ComponentTile(QWidget):
    """One installable component: what it is, what it is for, whether it is on."""

    toggled = pyqtSignal(str, bool)

    def __init__(
        self,
        key: str,
        label: str,
        detail: str,
        *,
        required: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.key = str(key)
        self.label = str(label)
        self.detail = str(detail)
        self.required = bool(required)
        self.installed = False
        self._selected = bool(required)
        self._hovered = False
        self._lift = 0.0
        self._entrance = 1.0

        self.setMinimumHeight(TILE_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._hover_animation = QPropertyAnimation(self, b"lift", self)
        self._hover_animation.setDuration(HOVER_MS)
        self._hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._entrance_animation = QPropertyAnimation(self, b"entrance", self)
        self._entrance_animation.setDuration(ENTRANCE_MS)
        self._entrance_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    # ------------------------------------------------------------ animation

    def _get_lift(self) -> float:
        return self._lift

    def _set_lift(self, value: float) -> None:
        self._lift = float(value)
        self.update()

    #: How far the tile has risen towards the pointer, 0 to 1.
    lift = pyqtProperty(float, fget=_get_lift, fset=_set_lift)

    def _get_entrance(self) -> float:
        return self._entrance

    def _set_entrance(self, value: float) -> None:
        self._entrance = float(value)
        self.update()

    #: How far the tile has arrived, 0 to 1. Drives both fade and rise.
    entrance = pyqtProperty(float, fget=_get_entrance, fset=_set_entrance)

    def arrive(self, delay_ms: int) -> None:
        """Fade and rise into place after ``delay_ms``."""
        self._entrance = 0.0
        self.update()
        QTimer.singleShot(max(0, int(delay_ms)), self._start_entrance)

    def _start_entrance(self) -> None:
        self._entrance_animation.stop()
        self._entrance_animation.setStartValue(0.0)
        self._entrance_animation.setEndValue(1.0)
        self._entrance_animation.start()

    def _animate_lift(self, target: float) -> None:
        self._hover_animation.stop()
        self._hover_animation.setStartValue(self._lift)
        self._hover_animation.setEndValue(target)
        self._hover_animation.start()

    # ---------------------------------------------------------------- state

    @property
    def selected(self) -> bool:
        return self._selected

    def set_selected(self, selected: bool) -> None:
        selected = bool(selected) or self.required
        if selected == self._selected:
            return
        self._selected = selected
        self.update()

    def set_installed(self, installed: bool) -> None:
        """Mark it as already on the machine, and stop offering it."""
        installed = bool(installed)
        if installed == self.installed:
            return
        self.installed = installed
        if installed:
            self._selected = False
        self.update()

    @property
    def actionable(self) -> bool:
        """Whether choosing it would do anything."""
        return not self.installed

    def _toggle(self) -> None:
        if self.installed or self.required:
            return
        self._selected = not self._selected
        self.update()
        self.toggled.emit(self.key, self._selected)

    # ---------------------------------------------------------- interaction

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._hovered = True
        if self.actionable:
            self._animate_lift(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._hovered = False
        self._animate_lift(0.0)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if self.rect().contains(event.position().toPoint()):
            self._toggle()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._toggle()
            return
        super().keyPressEvent(event)

    # -------------------------------------------------------------- drawing

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        return QSize(270, TILE_HEIGHT)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        colors = theme_module.COLORS
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setOpacity(max(0.0, min(1.0, self._entrance)))

        # Rise on arrival, and again a little under the pointer. Both are the
        # same movement, so a tile never jumps between the two.
        offset = (1.0 - self._entrance) * 14.0 - self._lift * 2.0
        body = QRectF(self.rect()).adjusted(1.0, 1.0 + offset, -1.0, -1.0 + offset)
        path = QPainterPath()
        path.addRoundedRect(body, TILE_RADIUS, TILE_RADIUS)

        if self.installed:
            fill = QColor(colors["neutral_soft"])
        elif self._selected:
            fill = QColor(colors["blue_soft"])
        else:
            fill = QColor(colors["control"])
        painter.fillPath(path, fill)

        if self._selected:
            pen = QPen(QColor(colors["blue"]), 1.8)
        elif self._hovered and self.actionable:
            pen = QPen(QColor(colors["border_strong"]), 1.3)
        else:
            pen = QPen(QColor(colors["border_soft"]), 1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        self._paint_mark(painter, body, colors)
        self._paint_text(painter, body, colors)
        painter.end()

    def _paint_mark(self, painter: QPainter, body: QRectF, colors: dict) -> None:
        """The tick box on the left: chosen, already there, or empty."""
        size = 17.0
        box = QRectF(body.left() + 13.0, body.center().y() - size / 2, size, size)
        mark = QPainterPath()
        mark.addRoundedRect(box, 5.0, 5.0)

        if self.installed:
            painter.fillPath(mark, QColor(colors["green"]))
            painter.setPen(Qt.PenStyle.NoPen)
        elif self._selected:
            painter.fillPath(mark, QColor(colors["blue"]))
        else:
            painter.setPen(QPen(QColor(colors["border_strong"]), 1.3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(mark)

        if self.installed or self._selected:
            pen = QPen(QColor(colors["on_accent"]), 2.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            tick = QPainterPath()
            tick.moveTo(box.left() + 4.4, box.center().y())
            tick.lineTo(box.center().x() - 0.6, box.bottom() - 4.8)
            tick.lineTo(box.right() - 4.0, box.top() + 5.0)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(tick)

    def _paint_text(self, painter: QPainter, body: QRectF, colors: dict) -> None:
        left = body.left() + 40.0

        name = QFont(self.font())
        name.setPointSizeF(max(8.5, name.pointSizeF() + 0.2))
        name.setWeight(QFont.Weight.DemiBold)
        painter.setFont(name)
        painter.setPen(QColor(colors["subtle"] if self.installed else colors["text"]))
        # Elided rather than clipped: a long name in a narrow column should
        # end in an ellipsis, not halfway through a letter at the tile edge.
        title_width = max(30.0, body.right() - 12.0 - left)
        painter.drawText(
            QRectF(left, body.top() + 13.0, title_width, 18.0),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            painter.fontMetrics().elidedText(
                self.label, Qt.TextElideMode.ElideRight, int(title_width)
            ),
        )

        detail = QFont(self.font())
        detail.setPointSizeF(max(7.5, detail.pointSizeF() - 1.2))
        painter.setFont(detail)
        painter.setPen(QColor(colors["muted"]))
        painter.drawText(
            QRectF(left, body.top() + 34.0, body.right() - 12.0 - left, 34.0),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap),
            tr("Installed") if self.installed else self.detail,
        )


class ComponentPicker(QWidget):
    """The seven tiles, a select-all, and what the choice adds up to."""

    selection_changed = pyqtSignal()

    COLUMNS = 2

    def __init__(self, specs, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(GRID_GAP)
        grid.setVerticalSpacing(GRID_GAP)
        self.tiles: dict[str, ComponentTile] = {}
        for position, spec in enumerate(specs):
            tile = ComponentTile(
                spec["key"], spec["label"], spec["detail"],
                required=bool(spec.get("required")),
                parent=self,
            )
            tile.toggled.connect(lambda *_args: self._announce())
            self.tiles[tile.key] = tile
            grid.addWidget(tile, position // self.COLUMNS, position % self.COLUMNS)
        self.select_all = QPushButton(tr("Select all"))
        self.select_all.setObjectName("onboardingGhost")
        self.select_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.select_all.clicked.connect(self._select_all)
        self.summary = QLabel("")
        self.summary.setObjectName("onboardingHint")

        layout.addLayout(grid)
        layout.addStretch(1)

        # Deliberately not in this widget's layout. This one is the scrolled
        # content; anything added here scrolls away with the tiles, and a
        # select-all that disappears when the list gets long is the first
        # control anybody reaches for. The caller places it above the scroll.
        self.header = QWidget()
        header_layout = QGridLayout(self.header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(self.select_all, 0, 0, Qt.AlignmentFlag.AlignLeft)
        header_layout.addWidget(self.summary, 0, 1, Qt.AlignmentFlag.AlignRight)
        header_layout.setColumnStretch(1, 1)
        self._announce()

    # ------------------------------------------------------------- choosing

    def selection(self) -> set[str]:
        """The components the user actually wants installed."""
        return {
            key for key, tile in self.tiles.items()
            if tile.selected and tile.actionable
        }

    def _select_all(self) -> None:
        wanted = any(
            not tile.selected for tile in self.tiles.values() if tile.actionable
        )
        for tile in self.tiles.values():
            if tile.actionable:
                tile.set_selected(wanted)
        self._announce()

    def mark_installed(self, installed) -> None:
        """Say which are already on the machine, so they stop being offered."""
        for key, tile in self.tiles.items():
            tile.set_installed(key in set(installed or ()))
        self._announce()

    def _announce(self) -> None:
        chosen = len(self.selection())
        done = sum(1 for tile in self.tiles.values() if tile.installed)
        parts = [tr("Selected") + f" {chosen}"]
        if done:
            parts.append(tr("Installed") + f" {done}")
        self.summary.setText(" · ".join(parts))
        self.select_all.setText(tr("Select all"))
        self.selection_changed.emit()

    # -------------------------------------------------------------- arrival

    def reveal(self) -> None:
        """Bring the tiles in, one shortly after the other."""
        for position, tile in enumerate(self.tiles.values()):
            tile.arrive(position * ENTRANCE_STAGGER_MS)

    def retranslate(self) -> None:
        self._announce()
        for tile in self.tiles.values():
            tile.update()
