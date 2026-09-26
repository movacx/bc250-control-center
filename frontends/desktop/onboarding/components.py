"""Choosing what to install: one compact row per component.

The first run asks for four preferences and then, at the end, for the one
thing that actually takes time. The seven components used to be large animated
tiles, two to a row, each carrying its description — a scrolling bento grid for
seven checkboxes, which pushed the terminal off the step. They are rows now:
a tick, the name, and a word when it is required or already installed. The
one-line description is still there, as the row's tooltip and accessible
description, for whoever wants it.

Anything already on the machine says so instead of offering to be installed
again. What each component costs is explained where it is decided — on the
dashboard panel that runs them — rather than on a first-run screen.

Labels come from the dashboard's own preparation panel. There is one list of
components in this application and this is not a second copy of it.
"""

from __future__ import annotations

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
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
from ..i18n import tr, tr_format

ROW_HEIGHT = 38
#: Rows while the terminal is open under them: the panel has a fixed height.
DENSE_ROW_HEIGHT = 30
ROW_RADIUS = 8.0
GRID_GAP = 6


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
    """One installable component as a single compact row."""

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

        self.setFixedHeight(ROW_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip(self.detail)
        self.setAccessibleName(self.label)
        self.setAccessibleDescription(self.detail)

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

    def gamepad_activate(self) -> None:
        self._toggle()

    # ---------------------------------------------------------- interaction

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._hovered = False
        self.update()
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
        return QSize(240, ROW_HEIGHT)

    def _badge(self) -> str:
        if self.installed:
            return tr("Installed")
        if self.required:
            return tr("Required")
        return ""

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        colors = theme_module.COLORS
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        body = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(body, ROW_RADIUS, ROW_RADIUS)
        if self._selected:
            fill, edge = colors["blue_soft"], colors["blue_border"]
        elif self._hovered and self.actionable:
            fill, edge = colors["panel_raised"], colors["border_strong"]
        else:
            fill, edge = colors["control"], colors["border_soft"]
        painter.fillPath(path, QColor(fill))
        focused = self.hasFocus()
        painter.setPen(QPen(QColor(colors["blue"] if focused else edge), 1.4 if focused else 1.0))
        painter.drawPath(path)

        size = 15.0
        box = QRectF(body.left() + 11.0, body.center().y() - size / 2, size, size)
        mark = QPainterPath()
        mark.addRoundedRect(box, 4.0, 4.0)
        if self.installed:
            painter.fillPath(mark, QColor(colors["green"]))
        elif self._selected:
            painter.fillPath(mark, QColor(colors["blue"]))
        else:
            painter.setPen(QPen(QColor(colors["border_strong"]), 1.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(mark)
        if self.installed or self._selected:
            pen = QPen(QColor(colors["on_accent"]), 1.8)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            tick = QPainterPath()
            tick.moveTo(box.left() + 3.8, box.center().y())
            tick.lineTo(box.center().x() - 0.8, box.bottom() - 4.0)
            tick.lineTo(box.right() - 3.4, box.top() + 4.2)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(tick)

        badge = self._badge()
        badge_font = QFont(self.font())
        badge_font.setPointSizeF(max(7.0, badge_font.pointSizeF() - 1.5))
        badge_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(badge_font)
        badge_width = painter.fontMetrics().horizontalAdvance(badge) + 4 if badge else 0
        if badge:
            painter.setPen(QColor(colors["green"] if self.installed else colors["muted"]))
            painter.drawText(
                QRectF(body.right() - 10.0 - badge_width, body.top(), badge_width, body.height()),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                badge,
            )

        name = QFont(self.font())
        name.setWeight(QFont.Weight.DemiBold)
        painter.setFont(name)
        painter.setPen(QColor(colors["subtle"] if self.installed else colors["text"]))
        left = box.right() + 10.0
        width = max(30.0, body.right() - 14.0 - badge_width - left)
        painter.drawText(
            QRectF(left, body.top(), width, body.height()),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            painter.fontMetrics().elidedText(self.label, Qt.TextElideMode.ElideRight, int(width)),
        )
        painter.end()


class ComponentPicker(QWidget):
    """The seven rows, a select-all, and what the choice adds up to."""

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
        self._grid = grid
        self.dense = False
        self.action: QWidget | None = None
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

        # Not in this widget's layout: the caller places it above the rows.
        self.header = QWidget()
        header_layout = QGridLayout(self.header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(self.select_all, 0, 0, Qt.AlignmentFlag.AlignLeft)
        header_layout.addWidget(self.summary, 0, 1, Qt.AlignmentFlag.AlignRight)
        header_layout.setColumnStretch(1, 1)
        self._announce()

    def place_action(self, widget: QWidget) -> None:
        """Put the install button in the grid, in the first free cell.

        Seven rows in two columns leave the last cell empty; the button sits
        there, level with the rows it acts on, instead of in a row of its own
        that took the height the terminal needs.
        """
        self.action = widget
        position = len(self.tiles)
        widget.setParent(self)
        widget.setFixedHeight(DENSE_ROW_HEIGHT if self.dense else ROW_HEIGHT)
        self._grid.addWidget(widget, position // self.COLUMNS, position % self.COLUMNS)

    def set_dense(self, dense: bool) -> None:
        """Shorter rows while the terminal is open beneath them.

        The first-run panel has a fixed height. Full rows, the terminal and
        the action row did not fit together, and the install button was
        drawn over the terminal's last line.
        """
        dense = bool(dense)
        if dense == self.dense:
            return
        self.dense = dense
        height = DENSE_ROW_HEIGHT if dense else ROW_HEIGHT
        for tile in self.tiles.values():
            tile.setFixedHeight(height)
        if self.action is not None:
            self.action.setFixedHeight(height)
        self._grid.setVerticalSpacing(4 if dense else GRID_GAP)
        self.updateGeometry()

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
        parts = [tr_format("{count} selected", count=chosen)]
        if done:
            parts.append(tr_format("{count} installed", count=done))
        self.summary.setText(" · ".join(parts))
        self.select_all.setText(tr("Select all"))
        self.selection_changed.emit()

    # -------------------------------------------------------------- arrival

    def reveal(self) -> None:
        """Kept for callers: the rows are simply there, with no entrance."""
        for tile in self.tiles.values():
            tile.update()

    def retranslate(self) -> None:
        self._announce()
        for tile in self.tiles.values():
            tile.update()
