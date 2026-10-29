"""Remote access: reach the terminal interface from a phone over SSH.

One button starts the SSH server (and keeps it for the next boot); the rest
says, in four short steps, what to install on the phone and what to type.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from bc250cc.application.system import remote_access

from ..components.async_tools import BackgroundExecutor
from ..components.buttons import WrappingButton as QPushButton
from ..components.page_widgets import SectionCard
from ..components.responsive import configure_responsive_scroll_area
from ..components.toast import show_toast
from ..i18n import tr, tr_format
from ..theme import COLORS, scale_stylesheet
from .processes import process_stylesheet

TUI_COMMAND = "bc250-control-center tui"
#: (platform, apps): what to install on the phone.
PHONE_APPS = (
    ("Android", "Termux (Google Play / F-Droid)"),
    ("iPhone / iPad", "Termius / Blink Shell (App Store)"),
)


class RemoteAccessPage(QWidget):
    """Switch the SSH server on and explain how to open the terminal interface from a phone."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("processPage", True)
        self._background = BackgroundExecutor(self)
        self._state: dict = {}
        self._code_boxes: list[QLabel] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        content = QWidget()
        configure_responsive_scroll_area(scroll, content)
        content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        content.setProperty("redesignedModule", True)
        root = QVBoxLayout(content)
        root.setContentsMargins(18, 8, 18, 20)
        root.setSpacing(14)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        self.card = SectionCard(
            "Remote access",
            "Use Control Center from your phone or tablet through SSH.",
            icon_name="",
            status=("Checking", "gray"),
        )
        root.addWidget(self.card)
        self.state_label = self._label("")
        self.card.body.addWidget(self.state_label)
        self.switch_button = QPushButton(tr("Turn on remote access"))
        self.switch_button.setProperty("processButton", "secondary")
        self.switch_button.setProperty("PrimaryAction", True)
        self.switch_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.switch_button.clicked.connect(lambda _checked=False: self._toggle())
        row = QHBoxLayout()
        row.addWidget(self.switch_button)
        row.addStretch(1)
        self.card.body.addLayout(row)
        self.address_label = self._label("")
        self.card.body.addWidget(self.address_label)

        steps = SectionCard("Connect from your phone", icon_name="")
        root.addWidget(steps)
        self.command_box = self._code("")
        for text in (
            "1. Turn on remote access with the button above.",
            "2. Install a terminal app on the phone:",
        ):
            steps.body.addWidget(self._label(text, strong=True))
        for platform, app in PHONE_APPS:
            steps.body.addWidget(self._label(f"•  {platform}: {app}", translate=False))
        steps.body.addWidget(self._label("3. On the same Wi-Fi as the board, type:", strong=True))
        steps.body.addWidget(self.command_box)
        steps.body.addWidget(self._label("4. Enter your password and open the terminal interface:", strong=True))
        steps.body.addWidget(self._code(TUI_COMMAND))
        copy = QPushButton(tr("Copy connection command"))
        copy.setProperty("processButton", "secondary")
        copy.clicked.connect(lambda _checked=False: self._copy())
        row = QHBoxLayout()
        row.addWidget(copy)
        row.addStretch(1)
        steps.body.addLayout(row)

        steps.body.addWidget(self._label(
            "Use it only on a network you trust, and do not open the SSH port to the internet."
        ))
        root.addStretch(1)
        self.apply_appearance()

    # -- construction --------------------------------------------------------

    @staticmethod
    def _label(text: str, *, strong: bool = False, translate: bool = True) -> QLabel:
        label = QLabel(tr(text) if text and translate else text)
        label.setWordWrap(True)
        label.setProperty("sectionSubtitle", not strong)
        label.setProperty("readingLabel", strong)
        return label

    def _code(self, text: str) -> QLabel:
        box = QLabel(text)
        box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.setWordWrap(True)
        self._code_boxes.append(box)
        return box

    def apply_appearance(self) -> None:
        c = COLORS
        self.setStyleSheet(process_stylesheet())
        for box in self._code_boxes:
            box.setStyleSheet(scale_stylesheet(
                f"background: {c['panel_alt']}; color: {c['text']}; border: 1px solid {c['border_soft']};"
                "border-radius: 8px; padding: 9px 12px; font-family: monospace; font-size: 13px;"
            ))
        self.update()

    # -- updates -------------------------------------------------------------

    def set_updates_active(self, active: bool) -> None:
        if active:
            self.refresh()

    def refresh(self) -> None:
        self._background.start("status", remote_access.status, on_success=self._apply, on_error=lambda _m: None)

    def retranslate_dynamic_copy(self) -> None:
        self._render()

    def _apply(self, state: dict) -> None:
        self._state = dict(state or {})
        self._render()

    def _command(self) -> str:
        state = self._state
        addresses = state.get("addresses") or ["<ip>"]
        port = f" -p {state['port']}" if state.get("port", 22) != 22 else ""
        return f"ssh{port} {state.get('user', '<user>')}@{addresses[0]}"

    def _render(self) -> None:
        state = self._state
        if not state:
            return
        if not state["systemd"]:
            status, tone, note = "Not installed", "gray", "This system does not use systemd: start the SSH server yourself."
        elif not state["unit"]:
            status, tone, note = "Not installed", "gray", "No SSH server is installed. Install the openssh-server package first."
        elif state["active"]:
            status, tone, note = "On", "green", "The SSH server is running."
        else:
            status, tone, note = "Off", "gray", "The SSH server is stopped."
        self.card.status.setText(tr(status))
        self.card.status.set_tone(tone)
        self.state_label.setText(tr(note))
        usable = state["systemd"] and bool(state["unit"])
        self.switch_button.setVisible(usable)
        self.switch_button.setEnabled(not self._background.is_running("switch"))
        self.switch_button.setText(tr("Turn off remote access" if state["active"] else "Turn on remote access"))
        self.switch_button.setProperty("PrimaryAction", not state["active"])
        self.switch_button.style().unpolish(self.switch_button)
        self.switch_button.style().polish(self.switch_button)
        addresses = state["addresses"]
        self.address_label.setText(
            tr_format("Address of this board: {address}", address=", ".join(addresses) or "–")
        )
        self.command_box.setText(self._command())

    # -- actions -------------------------------------------------------------

    def _toggle(self) -> None:
        turning_on = not self._state.get("active")
        self.switch_button.setEnabled(False)

        def failed(message: str) -> None:
            show_toast(self, tr("Remote access"), tr(message), tone="red")
            self.refresh()

        self._background.start(
            "switch",
            lambda: remote_access.set_enabled(turning_on),
            on_success=lambda _result: self.refresh(),
            on_error=failed,
        )

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self._command())
        show_toast(self, tr("Copied"), self._command(), tone="green")
