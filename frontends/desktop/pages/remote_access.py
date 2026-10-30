"""Remote access: reach the terminal interface from a phone over SSH.

One button starts the SSH server (and keeps it for the next boot); the rest
says, in four short steps, what to install on the phone and what to type.
"""

from __future__ import annotations

from PyQt6.QtCore import QByteArray, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QGuiApplication, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from bc250cc.application.system import remote_access, web_access

from ..components.async_tools import BackgroundExecutor
from ..components.buttons import WrappingButton as QPushButton
from ..components.page_widgets import SectionCard
from ..components.responsive import configure_responsive_scroll_area
from ..components.toast import show_toast
from ..components.toggle_switch import ToggleSwitch
from ..components.tui_preview_dialog import TuiPreviewDialog
from ..components.wheel_guard import GuardedComboBox
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
        self._web_state: dict = {}
        self._syncing_web = False
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
        )
        root.addWidget(self.card)
        self.state_label = self._label("")
        self.card.body.addWidget(self.state_label)
        self.switch_button = QPushButton(tr("Turn on remote access"))
        self.switch_button.setProperty("processButton", "secondary")
        self.switch_button.setProperty("PrimaryAction", True)
        self.switch_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.switch_button.clicked.connect(lambda _checked=False: self._toggle())
        preview = QPushButton(tr("Preview the terminal interface"))
        preview.setProperty("processButton", "secondary")
        preview.setCursor(Qt.CursorShape.PointingHandCursor)
        preview.clicked.connect(lambda _checked=False: self._preview())
        row = QHBoxLayout()
        row.addWidget(self.switch_button)
        row.addWidget(preview)
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

        # -- Web Telemetry ----------------------------------------------------
        self.web_card = SectionCard(
            "Web telemetry",
            "Open Control Center on your phone, tablet or another computer of your network, in a web page.",
            icon_name="",
        )
        root.addWidget(self.web_card)

        self.web_state_label = self._label("")
        self.web_card.body.addWidget(self.web_state_label)

        self.web_switch_button = QPushButton(tr("Open web telemetry"))
        self.web_switch_button.setProperty("processButton", "secondary")
        self.web_switch_button.setProperty("PrimaryAction", True)
        self.web_switch_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.web_switch_button.clicked.connect(lambda _checked=False: self._toggle_web())

        self.web_open_button = QPushButton(tr("Open in browser"))
        self.web_open_button.setProperty("processButton", "secondary")
        self.web_open_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.web_open_button.clicked.connect(lambda _checked=False: self._open_web())

        self.web_autostart_switch = ToggleSwitch()
        self.web_autostart_switch.setAccessibleName(tr("Start with the session"))
        self.web_autostart_switch.toggled.connect(self._autostart_web_toggled)

        self.web_autostart_label = QLabel(tr("Start with the session"))
        self.web_autostart_label.setProperty("readingLabel", True)
        self.web_autostart_label.setToolTip(tr("Starts the web interface at every login with a systemd user service."))

        web_controls = QHBoxLayout()
        web_controls.addWidget(self.web_switch_button)
        web_controls.addWidget(self.web_open_button)
        self.web_qr_button = QPushButton(tr("Connect with QR"))
        self.web_qr_button.setProperty("processButton", "secondary")
        self.web_qr_button.clicked.connect(self._show_web_qr)
        web_controls.addWidget(self.web_qr_button)
        web_controls.addStretch(1)
        web_controls.addWidget(self.web_autostart_switch)
        web_controls.addWidget(self.web_autostart_label)
        self.web_card.body.addLayout(web_controls)

        self.web_details_widget = QWidget()
        web_details = QVBoxLayout(self.web_details_widget)
        web_details.setContentsMargins(0, 8, 0, 0)
        web_details.setSpacing(8)

        self.web_url_label = self._label("Address", strong=True)
        self.web_url_box = self._code("")
        self.web_copy_url_button = QPushButton(tr("Copy address"))
        self.web_copy_url_button.setProperty("processButton", "secondary")
        self.web_copy_url_button.clicked.connect(lambda _checked=False: self._copy_web_url())

        url_row = QHBoxLayout()
        url_row.addWidget(self.web_url_box, 1)
        url_row.addWidget(self.web_copy_url_button)

        self.web_pin_label = self._label("Access key", strong=True)
        self.web_pin_box = self._code("")
        self.web_copy_pin_button = QPushButton(tr("Copy access key"))
        self.web_copy_pin_button.setProperty("processButton", "secondary")
        self.web_copy_pin_button.clicked.connect(lambda _checked=False: self._copy_web_pin())

        pin_row = QHBoxLayout()
        pin_row.addWidget(self.web_pin_box, 1)
        pin_row.addWidget(self.web_copy_pin_button)

        self.web_lan_switch = ToggleSwitch()
        self.web_lan_switch.setAccessibleName(tr("Reachable from the local network"))
        self.web_lan_switch.toggled.connect(lambda checked: self._web_option("lan", checked))
        self.web_password_switch = ToggleSwitch()
        self.web_password_switch.setAccessibleName(tr("HTTPS (encrypted connection)"))
        self.web_password_switch.toggled.connect(lambda checked: self._web_option("tls", checked))
        self.web_new_key_button = QPushButton(tr("New access key"))
        self.web_new_key_button.setProperty("processButton", "secondary")
        self.web_new_key_button.clicked.connect(lambda _checked=False: self._new_web_key())
        options = QGridLayout()
        options.addWidget(self.web_lan_switch, 0, 0)
        options.addWidget(self._label("Reachable from the local network", strong=True), 0, 1)
        options.addWidget(self.web_password_switch, 1, 0)
        options.addWidget(self._label("HTTPS (encrypted connection)", strong=True), 1, 1)
        options.setColumnStretch(1, 1)

        web_details.addWidget(self.web_url_label)
        web_details.addLayout(url_row)
        web_details.addWidget(self.web_pin_label)
        web_details.addLayout(pin_row)
        web_details.addWidget(self.web_new_key_button)
        web_details.addWidget(self._label("The first time, accept this board's local certificate in your browser. SSH authorization is available inside the web interface."))
        self.web_card.body.addLayout(options)
        self.web_card.body.addWidget(self.web_details_widget)

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
        self._background.start("web_status", web_access.status, on_success=self._apply_web, on_error=lambda _m: None)

    def retranslate_dynamic_copy(self) -> None:
        self._render()
        self._render_web()

    def _apply_web(self, state: dict) -> None:
        self._web_state = dict(state or {})
        self._render_web()

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
            note = "This system does not use systemd: start the SSH server yourself."
        elif not state["unit"]:
            note = "No SSH server is installed. Install the openssh-server package first."
        elif state["active"]:
            note = "The SSH server is running."
        else:
            note = "The SSH server is stopped."
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

    def _preview(self) -> None:
        dialog = TuiPreviewDialog(self.window())
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.show()

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self._command())
        show_toast(self, tr("Copied"), self._command(), tone="green")

    # -- web actions & render -------------------------------------------------

    def _render_web(self) -> None:
        state = self._web_state
        if not state:
            return
        running = bool(state.get("running"))
        urls = state.get("urls") or []
        local_url = state.get("local_url", "")
        key = state.get("key", "")
        autostart = state.get("autostart") or {}

        if running:
            display_url = urls[0] if urls else local_url
            self.web_state_label.setText(tr_format("The web interface is running on {address}", address=display_url))
        else:
            self.web_state_label.setText(tr("The web interface is stopped."))

        self.web_switch_button.setEnabled(not self._background.is_running("switch_web"))
        self.web_switch_button.setText(tr("Stop web telemetry" if running else "Open web telemetry"))
        self.web_switch_button.setProperty("PrimaryAction", not running)
        self.web_switch_button.style().unpolish(self.web_switch_button)
        self.web_switch_button.style().polish(self.web_switch_button)

        self.web_open_button.setVisible(running)
        self.web_qr_button.setVisible(running and bool(urls))
        self.web_qr_button.setEnabled(bool(state.get("tls", True)))
        self.web_qr_button.setToolTip("" if state.get("tls", True) else tr("HTTPS required"))

        all_urls = ([local_url] if local_url else []) + urls
        self.web_url_box.setText(" · ".join(all_urls) if all_urls else "–")
        self.web_pin_box.setText(key or "–")
        self.web_details_widget.setVisible(running)

        self._syncing_web = True
        try:
            self.web_lan_switch.setChecked(bool(state.get("lan")))
            self.web_password_switch.setChecked(bool(state.get("tls", True)))
            self.web_password_switch.setEnabled(True)
            self.web_autostart_switch.setEnabled(bool(autostart.get("supported")) and not autostart.get("foreign"))
            self.web_autostart_switch.setChecked(bool(autostart.get("enabled")))
        finally:
            self._syncing_web = False

    def _toggle_web(self) -> None:
        running = bool(self._web_state.get("running"))
        self.web_switch_button.setEnabled(False)

        def failed(message: str) -> None:
            show_toast(self, tr("Web telemetry"), tr(message), tone="red")
            self.refresh()

        action = web_access.stop if running else web_access.start
        self._background.start("switch_web", action, on_success=lambda _r: self.refresh(), on_error=failed)

    def _open_web(self) -> None:
        url = self._web_state.get("local_url") or "http://127.0.0.1:8250"
        QDesktopServices.openUrl(QUrl(url))

    def _autostart_web_toggled(self, checked: bool) -> None:
        if self._syncing_web:
            return
        self.web_autostart_switch.setEnabled(False)

        def failed(message: str) -> None:
            show_toast(self, tr("Web telemetry"), tr(message), tone="red")
            self.refresh()

        self._background.start(
            "web_autostart",
            lambda: web_access.set_autostart(checked),
            on_success=lambda _r: self.refresh(),
            on_error=failed,
        )

    def _copy_web_url(self) -> None:
        urls = self._web_state.get("urls") or []
        target = urls[0] if urls else self._web_state.get("local_url", "")
        if target:
            QGuiApplication.clipboard().setText(target)
            show_toast(self, tr("Copied"), target, tone="green")

    def _web_option(self, name: str, checked: bool) -> None:
        """A changed option reaches the running server only when it starts again."""
        if self._syncing_web:
            return

        def apply() -> None:
            web_access.save_settings(**{name: checked})
            if self._web_state.get("running"):
                web_access.stop()
                web_access.start()

        self._background.start("web_option", apply, on_success=lambda _r: self.refresh(), on_error=lambda _m: self.refresh())

    def _new_web_key(self) -> None:
        self._background.start("web_key", lambda: web_access.access_key(renew=True),
                               on_success=lambda _r: self.refresh(), on_error=lambda _m: None)

    def _copy_web_pin(self) -> None:
        key = self._web_state.get("key", "")
        if key:
            QGuiApplication.clipboard().setText(key)
            show_toast(self, tr("Copied"), key, tone="green")

    def _show_web_qr(self) -> None:
        urls = self._web_state.get("urls") or []
        if not urls or not self._web_state.get("tls", True):
            return
        dialog = QDialog(self.window())
        dialog.setWindowTitle(tr("Connect with QR"))
        layout = QVBoxLayout(dialog)
        address = GuardedComboBox()
        address.addItems(urls)
        address.setAccessibleName(tr("Address"))
        layout.addWidget(address)
        image = QLabel()
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(image)
        note = self._label("Scan with your phone on the same Wi-Fi. The QR contains the access key; do not share it.")
        layout.addWidget(note)
        fingerprint = self._web_state.get("tls_fingerprint")
        if fingerprint:
            proof = QLabel("SHA-256\n" + fingerprint[:47] + "\n" + fingerprint[48:])
            proof.setWordWrap(True)
            proof.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(proof)

        def render() -> None:
            url = address.currentText() + "#pair=" + self._web_state.get("key", "")
            renderer = QSvgRenderer(QByteArray(web_access.pairing_svg(url)))
            pixmap = QPixmap(300, 300)
            pixmap.fill(Qt.GlobalColor.white)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            image.setPixmap(pixmap)

        address.currentIndexChanged.connect(render)
        render()
        close = QPushButton(tr("Close"))
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()
