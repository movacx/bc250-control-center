"""Controller and keyboard behaviour for cards that select on click.

The CPU and GPU operating profiles are cards: a click selects the profile and
a small pencil edits it. A controller could not use them. The card itself was
not a focus stop, so the D-pad landed on the only thing inside it that was --
the pencil -- and A opened the editor instead of choosing the profile.

With this mixin the card is the stop. A (or Enter/Space) selects it, X (or F2)
edits it, and the pencil stays for the mouse but is left out of controller
navigation. While the editor is open the card steps aside so the D-pad moves
between its fields, and closing the editor puts focus back on the card.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QWidget


class EditableCardNavigation:
    """Mix in before QFrame. The card provides ``_editor``, ``selected`` and
    ``_profile``; ``_card_selectable`` may be overridden."""

    def _install_card_navigation(self, edit_button: QWidget) -> None:
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        edit_button.setProperty("gamepadSkip", True)
        edit_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    # -- state -----------------------------------------------------------
    def _card_editing(self) -> bool:
        editor = getattr(self, "_editor", None)
        return bool(editor is not None and editor.isVisible())

    def _card_selectable(self) -> bool:
        return not self._card_editing()

    def _card_enter_edit(self) -> None:
        self.setProperty("gamepadSkip", True)

    def _card_leave_edit(self) -> None:
        had_focus = self.isAncestorOf(QApplication.focusWidget() or self)
        self.setProperty("gamepadSkip", False)
        if had_focus:
            self.setFocus(Qt.FocusReason.OtherFocusReason)

    # -- controller ------------------------------------------------------
    def gamepad_activate(self) -> None:
        if self._card_selectable():
            self.selected.emit(self._profile)

    def gamepad_secondary(self) -> None:
        if not self._card_editing():
            self.begin_edit()

    def gamepad_secondary_available(self) -> bool:
        return not self._card_editing()

    def gamepad_secondary_label(self) -> str:
        return "Edit"

    # -- keyboard --------------------------------------------------------
    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API name
        key = event.key()
        if not self._card_editing():
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                self.gamepad_activate()
                event.accept()
                return
            if key == Qt.Key.Key_F2:
                self.begin_edit()
                event.accept()
                return
        super().keyPressEvent(event)
