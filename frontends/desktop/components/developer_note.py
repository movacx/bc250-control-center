"""A note from the developer, behind the footer's heart button.

Support for BC250 Control Center is paused while the developer's own BC-250
is broken: every fix and every new tool is tried on that board before it
ships. The note says so plainly, what still works (reports from the app),
how to help (testing on Discord; Ko-fi stays on the dashboard), and when it
should end.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core.preferences import application_settings
from ..i18n import localize_widget_tree, tr
from .buttons import WrappingButton as QPushButton
from .dialogs import center_dialog, enable_adaptive_dialog
from .widgets import dialog_card, icon

#: Once the note has been opened, the button stops glowing.
SEEN_KEY = "notes/support_pause_2026_seen"
DISCORD_HANDLE = "@_movacx"
#: Opens the profile, where a message or a friend request can be sent.
DISCORD_PROFILE_URL = "https://discord.com/users/719291715369959445"

TITLE = "Support is paused until further notice"
WHEN = "Probably until January 2027."
#: The note, told plainly in a few paragraphs. The Discord box follows the
#: last one, where it asks for help.
PARAGRAPHS = (
    "Quick story: my BC-250 died. The fans spin, but there's no video and it doesn't even react to the "
    "keyboard, not even the Caps Lock light. I've spent three days trying everything: another power supply, "
    "another HDMI cable, a full cleaning... nothing. In a few days I'm taking it to a technician to have it "
    "checked.",
    "Everything that goes into BC250 Control Center gets tested on that board first, so until I have it back, "
    "support will be pretty basic. I'll keep reading the reports you send from the app, but fixes may take a "
    "lot longer, because I usually reproduce each bug on my own board before shipping the fix.",
    "I'm paying for the repair with the scholarship I get in January, so it will most likely be back around "
    "then, and everything goes back to normal. Meanwhile, if something breaks, report it anyway; just bear "
    "with me a bit.",
    "If you want to give me a hand in the meantime by testing new versions on your own BC-250, message me on "
    "Discord. And if you'd like to support me, the Ko-fi link is on the dashboard.",
)
THANKS = "Thanks for your patience!"
#: Why the pause should not be felt much: what the app does on its own.
POSTSCRIPT = (
    "P.S. Don't worry too much, the app pretty much takes care of itself. Things like the Cyan governor are "
    "installed from their own official projects, and Control Center's own parts, like compute unit unlock and "
    "CPU overclocking, don't depend on anything outside, so they'll keep working. And if something fails, "
    "Settings › About › Support › Known errors explains how to fix the most common problems."
)
SIGNATURE = "— movacx"


def note_seen() -> bool:
    try:
        return str(application_settings().value(SEEN_KEY, "false")).lower() == "true"
    except (OSError, RuntimeError):
        return False


def mark_note_seen() -> None:
    try:
        application_settings().setValue(SEEN_KEY, "true")
    except (OSError, RuntimeError):
        pass


def _text(text: str, name: str = "DialogBody") -> QLabel:
    label = QLabel(tr(text))
    label.setObjectName(name)
    label.setWordWrap(True)
    label.setProperty("naturalHeight", True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


class DeveloperNoteDialog(QDialog):
    """The note itself: it informs and points to Discord; Ko-fi stays on the dashboard."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("InfoDialog")
        self.setModal(True)
        self.setWindowTitle(tr("A note from the developer"))
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        enable_adaptive_dialog(self, preferred_width=640, preferred_height=780, minimum_width=420, minimum_height=360)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        card = dialog_card(self)
        outer.addWidget(card)
        frame = QVBoxLayout(card)
        frame.setContentsMargins(26, 24, 26, 18)
        frame.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(12)
        glyph = QLabel()
        glyph.setPixmap(icon("note_heart").pixmap(30, 30))
        glyph.setFixedSize(30, 30)
        head.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        eyebrow = QLabel(tr("A note from the developer"))
        eyebrow.setObjectName("DialogEyebrow")
        titles.addWidget(eyebrow)
        title = QLabel(tr(TITLE))
        title.setObjectName("DialogTitle")
        title.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(_text(WHEN, "DialogSubtitle"))
        head.addLayout(titles, 1)
        frame.addLayout(head)

        # The text scrolls on a short screen or in a longer language; the
        # title and the buttons stay in place.
        body = QWidget()
        body.setObjectName("GuidePanelContent")
        text = QVBoxLayout(body)
        text.setContentsMargins(0, 0, 6, 0)
        text.setSpacing(12)
        scroll = QScrollArea()
        scroll.setObjectName("DialogContentScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(body)
        frame.addWidget(scroll, 1)

        for paragraph in PARAGRAPHS:
            text.addWidget(_text(paragraph))

        # Where to write for testing: the handle with a copy button.
        contact = QFrame()
        contact.setObjectName("DialogDetail")
        row = QHBoxLayout(contact)
        row.setContentsMargins(12, 8, 8, 8)
        row.setSpacing(10)
        discord = QLabel()
        discord.setPixmap(icon("discord").pixmap(18, 18))
        row.addWidget(discord)
        handle = QLabel(DISCORD_HANDLE)
        handle.setObjectName("DialogDetailText")
        handle.setProperty("i18nLiteral", True)
        handle.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(handle, 1)
        self.profile_button = QPushButton(tr("Open profile"))
        self.profile_button.setObjectName("DialogSecondary")
        self.profile_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.profile_button.setToolTip(DISCORD_PROFILE_URL)
        self.profile_button.clicked.connect(self._open_profile)
        row.addWidget(self.profile_button)
        self.copy_button = QPushButton(tr("Copy"))
        self.copy_button.setObjectName("DialogSecondary")
        self.copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_button.clicked.connect(self._copy_handle)
        row.addWidget(self.copy_button)
        text.addWidget(contact)

        text.addWidget(_text(THANKS))
        signature = QLabel(SIGNATURE)
        signature.setObjectName("DialogBody")
        signature.setProperty("i18nLiteral", True)
        text.addWidget(signature)
        text.addSpacing(4)
        text.addWidget(_text(POSTSCRIPT))
        text.addStretch(1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        footer.addStretch(1)
        close = QPushButton(tr("Close"))
        close.setObjectName("DialogPrimary")
        close.setDefault(True)
        close.clicked.connect(self.reject)
        footer.addWidget(close)
        frame.addLayout(footer)
        localize_widget_tree(self)

    def _open_profile(self) -> None:
        from ..core.external_links import open_external_url

        opened, _message = open_external_url(DISCORD_PROFILE_URL)
        if not opened:
            # No browser to hand it to: the link goes to the clipboard instead.
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(DISCORD_PROFILE_URL)
            self.profile_button.setText(tr("Copied"))

    def _copy_handle(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(DISCORD_HANDLE)
        self.copy_button.setText(tr("Copied"))

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().showEvent(event)
        center_dialog(self)
