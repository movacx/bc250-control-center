"""Compatibility as settings rows: one tool a line, one action, the rest under "More".

Each row names a tool and says what it does at the left; at the right its
state, as a word, its main action and a "More" menu with every other action.
Whatever else a tool shows (a version to pick, the kernel and Mesa states, a
note) opens under the row from "Show details".

The rows only present the PreparationInfoCard objects the render code already
updates: each card is moved under its row, its own title row and button bar are
kept out of sight, and the row's button and menu press the card's buttons. So
every status, label, enabled state and visibility the render code writes still
lands, and is read back here.
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import theme as theme_module
from ..i18n import tr
from ..theme import COLORS
from .buttons import WrappingButton

_TONES = {"green", "orange", "red"}


def explicitly_hidden(widget: QWidget) -> bool:
    """Hidden on purpose, not merely not shown yet."""
    return widget.isHidden() and widget.testAttribute(Qt.WidgetAttribute.WA_WState_ExplicitShowHide)


def _tone_color(tone: str) -> str:
    return COLORS[tone] if tone in _TONES else COLORS["muted"]


def _card_buttons(card) -> list[QPushButton]:
    """The card's action buttons the render code currently shows, in order."""
    layout = card.actions
    buttons = []
    for index in range(layout.count()):
        widget = layout.itemAt(index).widget()
        if isinstance(widget, QPushButton) and not explicitly_hidden(widget):
            buttons.append(widget)
    return buttons


def _primary(buttons: list[QPushButton]) -> QPushButton | None:
    """The one action the row shows: the card's accented one, else its first plain one."""
    for button in buttons:
        if button.property("accented"):
            return button
    for button in buttons:
        if not button.property("linkAction") and not button.property("dangerAction"):
            return button
    return None


class _ComponentRow(QFrame):
    """One tool on one line, and its details folded under it."""

    def __init__(self, card, parent: QWidget | None = None, *, show_scope: bool = True) -> None:
        super().__init__(parent)
        self.card = card
        self._show_scope = show_scope
        self._target: QPushButton | None = None
        self.setProperty("compatItem", True)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 12, 18, 12)
        root.setSpacing(10)

        line = self._line = QGridLayout()
        line.setSpacing(14)
        self._copy = QWidget()
        self._copy.setMinimumWidth(0)
        copy = QVBoxLayout(self._copy)
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(3)
        self.title = QLabel("")
        self.title.setProperty("compatItemTitle", True)
        self.title.setWordWrap(True)
        # One line of what it does (all of it on hover), one of where it applies.
        self.summary = QLabel("")
        self.summary.setProperty("compatItemSummary", True)
        self.summary.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.scope = QLabel("")
        self.scope.setProperty("compatItemScope", True)
        self.scope.setWordWrap(True)
        copy.addWidget(self.title)
        copy.addWidget(self.summary)
        copy.addWidget(self.scope)
        self.state = QLabel("")
        self.state.setProperty("compatItemState", True)
        self.state.setWordWrap(True)
        self.state.setMinimumWidth(0)
        self.state.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.action = WrappingButton("")
        self.action.setProperty("compatAction", True)
        self.action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action.clicked.connect(self._press)
        self.more = QToolButton()
        self.more.setProperty("compatMore", True)
        self.more.setText(tr("More") + "  ⌄")
        self.more.setCursor(Qt.CursorShape.PointingHandCursor)
        self.more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu = QMenu(self.more)
        self.menu.setToolTipsVisible(True)
        self.menu.aboutToShow.connect(self._fill_menu)
        self.more.setMenu(self.menu)
        # An absent button keeps its place, so the columns stay in line.
        for widget in (self.action, self.more):
            policy = widget.sizePolicy()
            policy.setRetainSizeWhenHidden(True)
            widget.setSizePolicy(policy)
        root.addLayout(line)

        # The card itself, folded: what is left once its title row, description
        # and buttons are kept out of sight is its detail (version, states, notes).
        self.details = QWidget()
        details_layout = QVBoxLayout(self.details)
        details_layout.setContentsMargins(0, 0, 0, 0)
        card.setParent(self.details)
        card.setProperty("listRow", False)
        card.setProperty("detailCard", True)
        card.layout().setContentsMargins(0, 0, 0, 0)
        card.layout().setSpacing(10)
        body = getattr(card, "_body", None)
        if body is not None:
            card.set_expanded(True)
            card._toggle.hide()
            body.layout().setContentsMargins(0, 0, 0, 0)
            card._body = card._toggle = None
        # Sized to nothing rather than hidden: the render code shows them again.
        for widget in (card.title, card.scope, card.status, card.detail, card.actions_panel):
            widget.setMaximumSize(0, 0)
        card.style().unpolish(card)
        card.style().polish(card)
        details_layout.addWidget(card)
        self.details.hide()
        root.addWidget(self.details)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self._stacked = None
        self._reflow()

    def _has_details(self) -> bool:
        """Anything the card shows besides what the row already says."""
        hidden = {self.card.title, self.card.scope, self.card.status, self.card.detail, self.card.actions_panel}

        def shows(layout) -> bool:
            for index in range(layout.count()):
                item = layout.itemAt(index)
                widget = item.widget()
                if widget is None:
                    if item.layout() is not None and shows(item.layout()):
                        return True
                    continue
                if widget in hidden or explicitly_hidden(widget):
                    continue
                if isinstance(widget, QLabel):
                    if widget.text().strip():
                        return True
                    continue
                inner = widget.layout()
                if inner is None or shows(inner):
                    return True
            return False

        return shows(self.card.layout())

    def _elide(self) -> None:
        text = getattr(self, "_summary", "")
        width = max(60, self.summary.width())
        self.summary.setText(self.summary.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, width))

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._reflow()
        self._elide()

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().changeEvent(event)
        if hasattr(self, "_stacked") and event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._reflow()

    def _reflow(self) -> None:
        if not hasattr(self, "_stacked"):
            return
        scale = theme_module.ACTIVE_SCALE / 100
        widths = (
            max(round(130 * scale), self.state.fontMetrics().horizontalAdvance(self.state.text()) + round(8 * scale)),
            max(round(190 * scale), QPushButton.sizeHint(self.action).width()),
            max(round(78 * scale), self.more.sizeHint().width()),
        )
        margins = self.layout().contentsMargins()
        available = self.width() - margins.left() - margins.right()
        copy_width = max(round(220 * scale), self.title.fontMetrics().averageCharWidth() * 34)
        stacked = available < copy_width + sum(widths) + 3 * self._line.horizontalSpacing()
        for column, width in enumerate((0, *widths)):
            self._line.setColumnMinimumWidth(column, 0 if stacked else width)
            self._line.setColumnStretch(column, int(column == 0))
        if stacked == self._stacked:
            return
        for widget in (self._copy, self.state, self.action, self.more):
            self._line.removeWidget(widget)
        if stacked:
            self._line.addWidget(self._copy, 0, 0, 1, 4)
            self._line.addWidget(self.state, 1, 0, 1, 4)
            self._line.addWidget(self.action, 2, 0, 1, 3)
            self._line.addWidget(self.more, 2, 3)
            self.state.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        else:
            for column, widget in enumerate((self._copy, self.state, self.action, self.more)):
                self._line.addWidget(widget, 0, column)
            self.state.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._stacked = stacked
        self.updateGeometry()

    def _press(self) -> None:
        if self._target is not None and self._target.isEnabled():
            self._target.click()

    def _fill_menu(self) -> None:
        self.menu.clear()
        for button in _card_buttons(self.card):
            if button is self._target:
                continue
            action = self.menu.addAction(button.text().replace("&&", "&"))
            action.setEnabled(button.isEnabled())
            action.setToolTip(button.toolTip() or button.text())
            action.triggered.connect(lambda _checked=False, b=button: b.click())
        if self._has_details():
            if not self.menu.isEmpty():
                self.menu.addSeparator()
            label = tr("Hide details") if self.details.isVisible() else tr("Show details")
            self.menu.addAction(label, lambda: self.details.setVisible(not self.details.isVisible()))

    def refresh(self) -> None:
        card = self.card
        self.title.setText(card.title.text())
        scope = card.scope.text() if self._show_scope and not explicitly_hidden(card.scope) else ""
        summary = " ".join(card.detail.text().split())
        self._summary = summary
        self.summary.setToolTip(summary)
        self._elide()
        self.scope.setText(f"{tr('Compatibility')}: {scope}" if scope else "")
        self.scope.setVisible(bool(scope))
        tone = getattr(card.status, "_tone", "gray")
        # A card that never shows a state keeps its default text out of sight.
        self.state.setText("" if explicitly_hidden(card.status) else card.status.text())
        self.state.setToolTip(self.state.text())
        self.state.setStyleSheet(f"QLabel {{ color:{_tone_color(tone)}; }}")
        buttons = _card_buttons(card)
        self._target = _primary(buttons)
        if self._target is None:
            self.action.hide()
        else:
            self.action.show()
            self.action.setText(self._target.text())
            self.action.setEnabled(self._target.isEnabled())
            self.action.setToolTip(self._target.toolTip())
            # Filled when it is the next step: not for a tool already working.
            accent = tone != "green" and self._target.isEnabled()
            if self.action.property("primary") != accent:
                self.action.setProperty("primary", accent)
                self.action.style().unpolish(self.action)
                self.action.style().polish(self.action)
        others = [button for button in buttons if button is not self._target]
        self.more.setText(tr("More") + "  ⌄")
        self.more.setVisible(bool(others) or self._has_details())
        self._reflow()


class CompatibilityBrowser(QWidget):
    """The tools as rows under their topic, in one section."""

    def __init__(self, groups, parent: QWidget | None = None, *, show_scope: bool = True) -> None:
        """``show_scope`` off where the card's scope only repeats its category."""
        super().__init__(parent)
        self.setProperty("compatBrowser", True)
        self._groups = [(title, list(cards)) for title, cards in groups]
        self._rows: dict[int, _ComponentRow] = {}
        self._captions: list[tuple[QWidget, list, QWidget]] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.setSpacing(6)
        for caption_text, cards in self._groups:
            heading = QLabel(tr(caption_text))
            heading.setProperty("compatGroupTitle", True)
            root.addWidget(heading)
            # Each topic is one card a step lighter than the page.
            group = QFrame()
            group.setProperty("compatGroup", True)
            layout = QVBoxLayout(group)
            layout.setContentsMargins(0, 2, 0, 2)
            layout.setSpacing(0)
            root.addWidget(group)
            self._captions.append((heading, cards, group))
            for card in cards:
                row = _ComponentRow(card, show_scope=show_scope)
                layout.addWidget(row)
                self._rows[id(card)] = row
                card.installEventFilter(self)
                # Every change of an action's label or state comes through here.
                original = card._refresh_action_styles

                def chained(original=original) -> None:
                    original()
                    self._schedule()

                card._refresh_action_styles = chained
                # A new state written to the card shows in its row at once.
                set_status = card.set_status

                def status_chained(text, tone, set_status=set_status) -> None:
                    set_status(text, tone)
                    self._schedule()

                card.set_status = status_chained
        self._pending = False
        self.refresh()

    def cards(self):
        return [card for _title, cards in self._groups for card in cards]

    def show_details(self, card) -> None:
        """Open a row's details: for a state whose next step is in them."""
        row = self._rows.get(id(card))
        if row is not None:
            row.details.show()

    def _schedule(self) -> None:
        if not self._pending:
            self._pending = True
            QTimer.singleShot(0, self.refresh)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API name
        if event.type() in (QEvent.Type.ShowToParent, QEvent.Type.HideToParent):
            self._schedule()
        return super().eventFilter(watched, event)

    def refresh(self) -> None:
        self._pending = False
        shown = []
        for card in self.cards():
            row = self._rows[id(card)]
            visible = not explicitly_hidden(card)
            row.setVisible(visible)
            if visible:
                row.refresh()
                shown.append(card)
        for caption, cards, group in self._captions:
            visible_rows = [self._rows[id(card)] for card in cards if card in shown]
            caption.setVisible(bool(visible_rows))
            group.setVisible(bool(visible_rows))
            for row in visible_rows:
                # A rule between rows of one topic, none above the first.
                ruled = row is not visible_rows[0]
                if row.property("ruled") != ruled:
                    row.setProperty("ruled", ruled)
                    row.style().unpolish(row)
                    row.style().polish(row)
