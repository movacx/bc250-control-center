"""Miniatures of the application, drawn from the palettes they describe.

A first-run screen that offers "Light / Dark / System" as three radio buttons
asks the user to imagine the answer. These draw it: each card is a small,
honest portrait of the shell — rail, cards, accent — rendered from the very
dictionaries the theme module will install if the card is chosen. Nothing here
is an asset, so a palette that changes changes the preview with it.
"""

from __future__ import annotations

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from .. import theme as theme_module


def palette_for(mode: str, accent: str, style: str | None = None) -> dict[str, str]:
    """The palette the theme module would install, without installing it.

    ``configure_theme`` writes into the module-level ``COLORS``, which is the
    live palette every open widget is painted from. A preview must never do
    that, so it asks for the finished palette of a choice as a copy of its
    own. ``mode`` is a theme ("light", "dark", "midnight"); the style
    defaults to the one on screen.
    """
    return theme_module.theme_palette(
        mode, accent, theme_module.ACTIVE_STYLE if style is None else style
    )


class _Card(QWidget):
    """Shared chrome: a selectable tile with a drawn illustration inside it."""

    chosen = pyqtSignal(str)

    RADIUS = 12.0

    def __init__(self, value: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.value = str(value)
        self._selected = False
        self._hovered = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_selected(self, selected: bool) -> None:
        selected = bool(selected)
        if selected == self._selected:
            return
        self._selected = selected
        self.update()

    @property
    def selected(self) -> bool:
        return self._selected

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
            self.chosen.emit(self.value)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        # A card is a control, so the keys that activate every other control
        # have to activate it too — this screen may be the first thing a
        # keyboard-only user meets.
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.chosen.emit(self.value)
            return
        super().keyPressEvent(event)

    # -------------------------------------------------------------- drawing

    def _frame(self, painter: QPainter) -> QRectF:
        """Paint the tile's own ground and border; return the inner area."""
        live = theme_module.COLORS
        body = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        path = QPainterPath()
        path.addRoundedRect(body, self.RADIUS, self.RADIUS)
        painter.setClipPath(path)
        painter.fillPath(path, QColor(live["panel_alt"]))
        painter.setClipping(False)

        if self._selected:
            pen = QPen(QColor(live["blue"]), 2.0)
        elif self._hovered or self.hasFocus():
            pen = QPen(QColor(live["border_strong"]), 1.4)
        else:
            pen = QPen(QColor(live["border_soft"]), 1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        return body.adjusted(10.0, 10.0, -10.0, -10.0)


class ThemePreview(_Card):
    """A miniature shell painted in the palette this card stands for."""

    def __init__(
        self, value: str, mode: str, accent: str, parent: QWidget | None = None,
        *, style: str = "standard",
    ) -> None:
        super().__init__(value, parent)
        self._mode = mode
        self._accent = accent
        self._style = style
        self.setMinimumHeight(104)

    def set_accent(self, accent: str) -> None:
        if accent == self._accent:
            return
        self._accent = accent
        self.update()

    def set_style(self, style: str) -> None:
        """Formal repaints the miniature too: quieter tones, squarer cards."""
        if style == self._style:
            return
        self._style = style
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        return QSize(150, 104)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        inner = self._frame(painter)
        self._paint_shell(
            painter, inner, palette_for(self._mode, self._accent, self._style),
            corner=theme_module.FORMAL_RADIUS_FACTOR if self._style == "formal" else 1.0,
        )
        painter.end()

    @staticmethod
    def _paint_shell(
        painter: QPainter, area: QRectF, colors: dict[str, str], *, corner: float = 1.0
    ) -> None:
        """The application in eight rectangles: rail, header, cards, accent."""
        painter.setPen(Qt.PenStyle.NoPen)
        canvas = QPainterPath()
        canvas.addRoundedRect(area, 5.0 * corner, 5.0 * corner)
        painter.fillPath(canvas, QColor(colors["window"]))
        painter.setClipPath(canvas)

        rail_width = area.width() * 0.26
        rail = QRectF(area.left(), area.top(), rail_width, area.height())
        painter.fillRect(rail, QColor(colors["panel"]))

        # The selected rail row, in the accent: the one spot of colour a real
        # screenshot of this application has at rest.
        row_height = max(4.0, area.height() * 0.11)
        gap = row_height * 0.62
        y = area.top() + gap
        for index in range(4):
            row = QRectF(rail.left() + 5.0, y, rail.width() - 10.0, row_height)
            painter.fillRect(row, QColor(colors["blue"] if index == 1 else colors["border_soft"]))
            y += row_height + gap

        # The page: a header strip and two cards, which is every screen here.
        page_left = rail.right() + 6.0
        page_width = area.right() - page_left - 5.0
        painter.fillRect(
            QRectF(page_left, area.top() + gap, page_width * 0.62, row_height * 0.8),
            QColor(colors["muted"]),
        )
        card_top = area.top() + gap * 2 + row_height
        card_height = area.height() - (card_top - area.top()) - gap
        for column in range(2):
            card = QRectF(
                page_left + column * (page_width / 2 + 2.0),
                card_top,
                page_width / 2 - 3.0,
                card_height,
            )
            face = QPainterPath()
            face.addRoundedRect(card, 3.0 * corner, 3.0 * corner)
            painter.fillPath(face, QColor(colors["panel"]))
            painter.setPen(QPen(QColor(colors["border_soft"]), 1.0))
            painter.drawPath(face)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.fillRect(
                QRectF(card.left() + 4.0, card.top() + 4.0, card.width() * 0.5, 3.0),
                QColor(colors["subtle"]),
            )
            painter.fillRect(
                QRectF(card.left() + 4.0, card.top() + 11.0, card.width() * 0.72, 5.0),
                QColor(colors["text"]),
            )
        painter.setClipping(False)


class SidebarPreview(_Card):
    """The same shell twice over, with the rail wide and with it collapsed."""

    def __init__(self, value: str, collapsed: bool, parent: QWidget | None = None) -> None:
        super().__init__(value, parent)
        self._collapsed = bool(collapsed)
        self.setMinimumHeight(104)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        return QSize(170, 104)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        inner = self._frame(painter)
        colors = theme_module.COLORS
        painter.setPen(Qt.PenStyle.NoPen)
        canvas = QPainterPath()
        canvas.addRoundedRect(inner, 5.0, 5.0)
        painter.fillPath(canvas, QColor(colors["window"]))
        painter.setClipPath(canvas)

        rail_width = inner.width() * (0.11 if self._collapsed else 0.30)
        rail = QRectF(inner.left(), inner.top(), rail_width, inner.height())
        painter.fillRect(rail, QColor(colors["panel"]))

        row_height = max(4.0, inner.height() * 0.115)
        gap = row_height * 0.55
        y = inner.top() + gap
        for index in range(5):
            if self._collapsed:
                # Collapsed, a row is its icon and nothing else — square, and
                # the same square whatever the label used to say.
                row = QRectF(rail.left() + 3.0, y, rail.width() - 6.0, row_height)
            else:
                row = QRectF(rail.left() + 4.0, y, rail.width() - 8.0, row_height)
            painter.fillRect(row, QColor(colors["blue"] if index == 1 else colors["border_soft"]))
            y += row_height + gap

        # The width the rail gives back is the whole point, so the page has to
        # be drawn wider in the collapsed card for the card to mean anything.
        page = QRectF(rail.right() + 5.0, inner.top() + gap,
                      inner.right() - rail.right() - 9.0, inner.height() - gap * 2)
        face = QPainterPath()
        face.addRoundedRect(page, 4.0, 4.0)
        painter.fillPath(face, QColor(colors["panel"]))
        painter.setPen(QPen(QColor(colors["border_soft"]), 1.0))
        painter.drawPath(face)
        painter.setPen(Qt.PenStyle.NoPen)
        for line in range(4):
            painter.fillRect(
                QRectF(page.left() + 6.0, page.top() + 8.0 + line * 9.0,
                       page.width() * (0.8 if line % 2 else 0.55), 4.0),
                QColor(colors["subtle"] if line % 2 else colors["text"]),
            )
        painter.setClipping(False)
        painter.end()


class AccentDot(_Card):
    """One accent, as the colour itself. Nothing else says it as directly."""

    DIAMETER = 30

    def __init__(self, accent: str, parent: QWidget | None = None) -> None:
        super().__init__(accent, parent)
        self.setFixedSize(QSize(self.DIAMETER + 10, self.DIAMETER + 10))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        colors = palette_for(theme_module.ACTIVE_THEME, self.value)
        centre = QRectF(self.rect()).center()
        radius = self.DIAMETER / 2.0
        body = QRectF(centre.x() - radius, centre.y() - radius, self.DIAMETER, self.DIAMETER)

        if self._selected or self._hovered or self.hasFocus():
            ring = body.adjusted(-4.0, -4.0, 4.0, 4.0)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(
                QColor(colors["blue"] if self._selected else theme_module.COLORS["border_strong"]),
                2.0 if self._selected else 1.2,
            ))
            painter.drawEllipse(ring)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colors["blue"]))
        painter.drawEllipse(body)
        painter.end()
