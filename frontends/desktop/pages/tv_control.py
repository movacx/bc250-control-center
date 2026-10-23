"""TV control: a remote for the TV and the receiver, and when they follow the computer.

cecd, the CEC daemon, is set up from the Compatibility tab. This is the window
the owner opens afterwards. It opens on a drawn remote control, which is what
is wanted most of the time; a gear swaps it for the settings: what cecd says
the TV and the receiver are doing, and the two automations cecd does not do by
itself (waking the TV at start, standing it by at power-off). The buttons run
in the background; the two automations are system changes and run in the
terminal, like every other install.
"""

from __future__ import annotations

from collections.abc import Mapping

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..components.dialogs import enable_adaptive_dialog
from ..components.remote_widgets import GlyphButton, RemoteBody
from ..i18n import localize_widget_tree, tr, tr_format
from ..theme import application_stylesheet
from .settings import SettingsTask, settings_stylesheet

POWER_TEXT = {
    "on": "Powered on",
    "standby": "Standby",
    "waking": "Waking up",
    "going-to-standby": "Going to standby",
    "unknown": "Unknown",
    "no-reply": "No reply",
}
#: What each answer reads as. ``sent`` is an order given, not a confirmation: CEC
#: has no reply for most of them, and a TV that ignores CEC says nothing either.
MESSAGES = {
    "sent": "Sent.",
    "amp-awake": "The receiver is awake.",
    "no-adapter": "No CEC adapter is connected. CEC needs a DisplayPort-to-HDMI adapter that passes it.",
    "no-daemon": "cecd is not running. Install TV control first.",
    "no-busctl": "busctl (systemd) is required.",
    "no-address": "This adapter has no address yet; the receiver may still be negotiating. Try again in a few seconds.",
    "failed": "The command was not accepted. If nothing happened, the TV or the adapter does not pass CEC.",
}
#: (automation, install action, remove action, title, hint)
AUTOMATIONS = (
    (
        "wake", "wake-install", "wake-remove",
        "Turn the TV on when this computer starts",
        "Wakes the TV and switches it to this input once per session. A TV that is on and showing another device is left alone.",
    ),
    (
        "poweroff", "poweroff-install", "poweroff-remove",
        "Turn the TV off when this computer shuts down",
        "A real power-off only, not a reboot or a suspend. Needs cec-ctl (v4l-utils). A TV showing another device is left alone.",
    ),
)
REMOTE_PAGE, SETTINGS_PAGE = 0, 1


class TvControlDialog(QDialog):
    """The remote, and behind a gear the settings."""

    #: ``wake-install``, ``wake-remove``, ``poweroff-install`` or ``poweroff-remove``.
    automation_requested = pyqtSignal(str)

    def __init__(self, controller, *, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller = controller
        self._tasks: set[SettingsTask] = set()
        #: The remote's buttons, by action.
        self.buttons: dict[str, GlyphButton] = {}
        self.automation_buttons: dict[str, QPushButton] = {}
        self._automation_state: dict[str, str] = {}
        self.setModal(True)
        self.setWindowTitle(tr("TV control"))
        self.setStyleSheet(application_stylesheet() + settings_stylesheet())
        self.setProperty("settingsPage", True)
        enable_adaptive_dialog(
            self, preferred_width=420, preferred_height=650, minimum_width=340, minimum_height=420,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(10)
        self.title = QLabel(tr("TV control"))
        self.title.setProperty("bannerTitle", True)
        header.addWidget(self.title, 1)
        self.gear_button = GlyphButton("gear", tr("Settings"), width=34)
        self.gear_button.clicked.connect(lambda: self._show(SETTINGS_PAGE))
        self.back_button = GlyphButton("back", tr("Back"), width=34)
        self.back_button.clicked.connect(lambda: self._show(REMOTE_PAGE))
        header.addWidget(self.gear_button)
        header.addWidget(self.back_button)
        layout.addLayout(header)

        self.result = QLabel("")
        self.result.setProperty("bannerText", True)
        self.result.setProperty("naturalHeight", True)
        self.result.setWordWrap(True)
        self.result.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._remote_page())
        self.stack.addWidget(self._settings_page())
        layout.addWidget(self.stack, 1)

        footer = QHBoxLayout()
        self.check_button = QPushButton(tr("Check"))
        self.check_button.setProperty("ghostAction", True)
        self.check_button.clicked.connect(self.refresh)
        footer.addWidget(self.check_button)
        footer.addStretch(1)
        close = QPushButton(tr("Close"))
        close.setProperty("primaryAction", True)
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        layout.addLayout(footer)
        # Not on the gear: an arrow or Enter would open the settings by accident.
        close.setFocus()

        localize_widget_tree(self)
        self._show(REMOTE_PAGE)
        self.refresh()

    # ------------------------------------------------------------ the remote

    def _remote_page(self) -> QWidget:
        self.remote = RemoteBody()
        inner = QVBoxLayout(self.remote)
        inner.setContentsMargins(26, 36, 26, 26)
        inner.setSpacing(10)
        inner.addWidget(self._display())
        inner.addSpacing(4)
        inner.addWidget(self._tag("TV"), 0, Qt.AlignmentFlag.AlignHCenter)
        row = QHBoxLayout()
        row.setSpacing(18)
        row.addStretch(1)
        row.addWidget(self._glyph("tv-on", "power", "Turn the TV on", tone="on", width=50))
        row.addWidget(self._glyph("tv-off", "power", "Turn the TV off", tone="off", width=50))
        row.addStretch(1)
        inner.addLayout(row)
        inner.addWidget(
            self._glyph("switch", "input", "Use this input", shape="pill", width=112, height=36),
            0, Qt.AlignmentFlag.AlignHCenter,
        )
        inner.addSpacing(8)
        inner.addWidget(self._tag("Receiver"), 0, Qt.AlignmentFlag.AlignHCenter)
        row = QHBoxLayout()
        row.setSpacing(18)
        row.addStretch(1)
        row.addWidget(self._glyph("amp-on", "power", "Wake the receiver", shape="square", tone="on", width=46))
        row.addWidget(self._glyph("amp-off", "power", "Receiver standby", shape="square", tone="off", width=46))
        row.addStretch(1)
        inner.addLayout(row)
        row = QHBoxLayout()
        row.setSpacing(22)
        row.addStretch(1)
        rocker = QVBoxLayout()
        rocker.setSpacing(0)
        rocker.addWidget(self._glyph("volume-up", "plus", "Volume up", shape="rocker-top", width=54, height=62))
        rocker.addWidget(self._glyph("volume-down", "minus", "Volume down", shape="rocker-bottom", width=54, height=62))
        row.addLayout(rocker)
        row.addWidget(self._glyph("mute", "mute", "Mute", width=46), 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)
        inner.addLayout(row)
        inner.addStretch(1)

        # The remote keeps its own proportions; a small screen scrolls it.
        self.remote.setFixedWidth(250)
        holder = QWidget()
        holder_layout = QHBoxLayout(holder)
        holder_layout.setContentsMargins(0, 0, 0, 0)
        holder_layout.addStretch(1)
        holder_layout.addWidget(self.remote)
        holder_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(holder)
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(6)
        page_layout.addWidget(scroll, 1)
        page_layout.addWidget(self.result)
        return page

    def _display(self) -> QFrame:
        """The little read-out at the top of the remote."""
        frame = QFrame()
        frame.setProperty("repositoryRow", True)
        grid = QGridLayout(frame)
        grid.setContentsMargins(12, 6, 12, 6)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(0)
        self.display: dict[str, QLabel] = {}
        for row, (key, caption) in enumerate((("tv", "TV"), ("receiver", "Receiver"))):
            name = QLabel(tr(caption))
            name.setProperty("repositoryIndex", True)
            value = QLabel("--")
            value.setProperty("repositoryName", True)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(name, row, 0)
            grid.addWidget(value, row, 1)
            self.display[key] = value
        grid.setColumnStretch(1, 1)
        return frame

    @staticmethod
    def _tag(text: str) -> QLabel:
        label = QLabel(tr(text))
        label.setProperty("groupTitle", True)
        return label

    def _glyph(self, action: str, glyph: str, label: str, **options) -> GlyphButton:
        button = GlyphButton(glyph, tr(label), **options)
        button.clicked.connect(lambda _checked=False, name=action: self._send(name))
        self.buttons[action] = button
        return button

    # ---------------------------------------------------------- the settings

    def _settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.subtitle = QLabel("")
        self.subtitle.setProperty("bannerText", True)
        self.subtitle.setProperty("naturalHeight", True)
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.subtitle)

        # What the TV and the receiver say they are doing.
        readings = QFrame()
        readings.setProperty("repositoryRow", True)
        grid = QGridLayout(readings)
        grid.setContentsMargins(12, 8, 12, 8)
        grid.setHorizontalSpacing(18)
        self.readings: dict[str, QLabel] = {}
        for column, (key, caption) in enumerate(
            (("tv", "TV"), ("receiver", "Receiver"), ("address", "This computer"))
        ):
            name = QLabel(tr(caption))
            name.setProperty("repositoryIndex", True)
            value = QLabel("--")
            value.setProperty("repositoryName", True)
            grid.addWidget(name, 0, column)
            grid.addWidget(value, 1, column)
            grid.setColumnStretch(column, 1)
            self.readings[key] = value
        layout.addWidget(readings)

        automatic = QLabel(tr("Automatic"))
        automatic.setProperty("groupTitle", True)
        layout.addWidget(automatic)
        for key, install, remove, heading, hint in AUTOMATIONS:
            layout.addWidget(self._automation_row(key, install, remove, heading, hint))
        layout.addStretch(1)
        return page

    def _automation_row(self, key: str, install: str, remove: str, heading: str, hint: str) -> QFrame:
        row = QFrame()
        row.setProperty("repositoryRow", True)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 6, 10, 6)
        layout.setSpacing(10)
        copy = QVBoxLayout()
        copy.setSpacing(1)
        name = QLabel(tr(heading))
        name.setProperty("repositoryName", True)
        name.setWordWrap(True)
        name.setProperty("naturalHeight", True)
        detail = QLabel(tr(hint))
        detail.setProperty("bannerText", True)
        detail.setWordWrap(True)
        detail.setProperty("naturalHeight", True)
        copy.addWidget(name)
        copy.addWidget(detail)
        layout.addLayout(copy, 1)
        button = QPushButton(tr("Install"))
        button.setProperty("ghostAction", True)
        button.setMinimumWidth(88)
        button.clicked.connect(lambda _checked=False, k=key, i=install, r=remove: self._toggle_automation(k, i, r))
        layout.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.automation_buttons[key] = button
        return row

    # ----------------------------------------------------------- behaviour

    def _show(self, page: int) -> None:
        settings = page == SETTINGS_PAGE
        self.stack.setCurrentIndex(page)
        self.title.setText(tr("Settings") if settings else tr("TV control"))
        self.gear_button.setVisible(not settings)
        self.back_button.setVisible(settings)
        self.check_button.setVisible(settings)

    def _background(self, operation, done) -> None:
        task = SettingsTask(operation, self)
        self._tasks.add(task)
        task.succeeded.connect(done)
        task.failed.connect(lambda message: done({"ok": False, "code": "failed", "detail": message}))
        task.finished.connect(lambda t=task: self._tasks.discard(t))
        task.start()

    def _busy(self, busy: bool) -> None:
        for button in self.buttons.values():
            button.setEnabled(not busy)
        self.check_button.setEnabled(not busy)

    def _send(self, action: str) -> None:
        self._busy(True)
        self.result.setText(tr("Sending..."))
        self._background(lambda: self.controller.tv_control_action(action), self._sent)

    def _sent(self, outcome: object) -> None:
        outcome = dict(outcome) if isinstance(outcome, Mapping) else {}
        text = tr(MESSAGES.get(str(outcome.get("code") or "failed"), MESSAGES["failed"]))
        detail = str(outcome.get("detail") or "")
        if outcome.get("code") == "amp-awake" and detail:
            text += " " + tr_format("System audio: {state}.", state=tr("on") if detail == "on" else tr("off"))
        self.result.setText(text)
        self._busy(False)
        if outcome.get("ok"):
            self.refresh()

    def refresh(self) -> None:
        """Ask cecd what the TV and the receiver are doing, and what is installed."""
        self.check_button.setEnabled(False)
        self._background(
            lambda: {
                "status": self.controller.tv_control_status(),
                "automation": self.controller.tv_control_automation(),
            },
            self._refreshed,
        )

    def _refreshed(self, answer: object) -> None:
        answer = dict(answer) if isinstance(answer, Mapping) else {}
        self.show_status(dict(answer.get("status") or {}))
        self.show_automation(dict(answer.get("automation") or {}))
        self.check_button.setEnabled(True)

    @staticmethod
    def _power_text(power: object) -> str:
        power = str(power or "")
        return tr(POWER_TEXT[power]) if power in POWER_TEXT else "--"

    def show_status(self, status: Mapping[str, object]) -> None:
        adapter = str(status.get("adapter") or "")
        daemon = bool(status.get("daemon"))
        for key in ("tv", "receiver"):
            text = self._power_text(status.get(key))
            self.display[key].setText(text)
            self.readings[key].setText(text)
        self.readings["address"].setText(str(status.get("address") or "--"))
        if not adapter:
            note = tr(MESSAGES["no-adapter"])
        elif not daemon:
            note = tr(MESSAGES["no-daemon"])
        else:
            note = ""
        # The remote says what is wrong in place of an answer; the settings always say what they talk to.
        self.subtitle.setText(note or tr_format("Talking to cecd through {adapter}.", adapter=adapter))
        if note:
            self.result.setText(note)
        for button in self.buttons.values():
            button.setEnabled(bool(adapter) and daemon)

    def show_automation(self, automation: Mapping[str, object]) -> None:
        for key, _install, _remove, _heading, _hint in AUTOMATIONS:
            state = str(automation.get(key) or "absent")
            self._automation_state[key] = state
            button = self.automation_buttons[key]
            button.setText(tr("Remove") if state == "installed" else tr("Install"))
            button.setEnabled(state != "foreign")
            button.setToolTip(
                tr("Another toolkit already does this. Remove it first to manage it here.") if state == "foreign" else ""
            )

    def _toggle_automation(self, key: str, install: str, remove: str) -> None:
        self.automation_requested.emit(remove if self._automation_state.get(key) == "installed" else install)
        self.accept()
