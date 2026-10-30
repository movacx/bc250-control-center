"""One web-access workspace: connection, visible pairing and device permissions."""
from __future__ import annotations

import shutil
from pathlib import Path

from PyQt6.QtCore import QByteArray, Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QGuiApplication, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QBoxLayout,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from bc250cc.application.system import web_access

from ..components.async_tools import BackgroundExecutor
from ..components.buttons import WrappingButton as QPushButton
from ..components.page_widgets import SectionCard
from ..components.responsive import configure_responsive_scroll_area
from ..components.toast import show_toast
from ..components.toggle_switch import ToggleSwitch
from ..components.wheel_guard import GuardedComboBox
from ..i18n import tr, tr_format
from ..theme import COLORS, scale_stylesheet
from .processes import process_stylesheet


class RemoteAccessPage(QWidget):
    """The desktop owner grants control; a newly paired phone can only monitor."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("processPage", True)
        self._background = BackgroundExecutor(self)
        self._web_state = {}
        self._syncing_web = False
        self._code_boxes = []
        self._qr_signature = None
        self._device_signature = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        content = QWidget()
        configure_responsive_scroll_area(scroll, content)
        content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        content.setProperty("redesignedModule", True)
        root = QVBoxLayout(content)
        root.setContentsMargins(18, 8, 18, 20)
        self.card = self.web_card = SectionCard("Remote access", "Control and monitor this board from a browser on your home network.", icon_name="")
        root.addWidget(self.card)
        root.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        body = self.card.body
        self.web_state_label = self._label("")
        body.addWidget(self.web_state_label)
        controls = QHBoxLayout()
        self.web_switch_button = self._button("Start web access", self._toggle_web, primary=True)
        self.web_open_button = self._button("Open in browser", self._open_web)
        controls.addWidget(self.web_switch_button)
        controls.addWidget(self.web_open_button)
        controls.addStretch(1)
        body.addLayout(controls)

        self.pairing_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.pairing_layout.setSpacing(24)
        body.addLayout(self.pairing_layout)
        connection = QVBoxLayout()
        self.pairing_layout.addLayout(connection, 1)
        connection.addWidget(self._label("Connect your phone", strong=True))
        self.web_address = GuardedComboBox()
        self.web_address.setAccessibleName(tr("Address"))
        self.web_address.currentIndexChanged.connect(self._render_qr)
        connection.addWidget(self.web_address)
        self.web_copy_url_button = self._button("Copy address", self._copy_web_url)
        connection.addWidget(self.web_copy_url_button)
        connection.addWidget(self._label("Access key", strong=True))
        self.web_pin_box = self._code("")
        connection.addWidget(self.web_pin_box)
        key_controls = QHBoxLayout()
        self.web_copy_pin_button = self._button("Copy access key", self._copy_web_pin)
        self.web_new_key_button = self._button("New access key", self._new_web_key)
        key_controls.addWidget(self.web_copy_pin_button)
        key_controls.addWidget(self.web_new_key_button)
        connection.addLayout(key_controls)
        connection.addWidget(self._label("New devices can monitor only. Match the device code shown on your phone before allowing hardware control below."))
        connection.addStretch(1)
        pairing = QVBoxLayout()
        self.pairing_layout.addLayout(pairing)
        self.web_qr_image = QLabel()
        self.web_qr_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.web_qr_image.setMinimumSize(240, 240)
        self.web_qr_image.setWordWrap(True)
        self.web_qr_image.setAccessibleName(tr("Scan to connect"))
        pairing.addWidget(self.web_qr_image)
        note = self._label("Scan on the same Wi-Fi. This QR contains your access key; keep it private.")
        note.setMaximumWidth(300)
        pairing.addWidget(note)
        body.addWidget(self._label("Browser sessions", strong=True))
        body.addWidget(self._label("Sessions expire after 30 minutes without activity or eight hours in total. Closing access disconnects the selected browser; a new login starts with monitoring permission."))
        self.device_list = QVBoxLayout()
        body.addLayout(self.device_list)
        self.revoke_all_button = self._button("Disconnect all devices", self._revoke_all)
        body.addWidget(self.revoke_all_button)

        body.addWidget(self._label("Network and connection", strong=True))
        self.web_lan_switch = ToggleSwitch()
        self.web_lan_switch.setAccessibleName(tr("Reachable from the local network"))
        self.web_lan_switch.toggled.connect(lambda checked: self._web_option("lan", checked))
        self.web_autostart_switch = ToggleSwitch()
        self.web_autostart_switch.setAccessibleName(tr("Start with the session"))
        self.web_autostart_switch.toggled.connect(self._autostart_web_toggled)
        for switch, text in ((self.web_lan_switch, "Reachable from the local network"),
                             (self.web_autostart_switch, "Start with the session")):
            row = QHBoxLayout()
            row.addWidget(switch)
            row.addWidget(self._label(text), 1)
            body.addLayout(row)
        self.network_label = self._label("")
        body.addWidget(self.network_label)
        body.addWidget(self._label("HTTPS is required for home-network access. No router ports or public tunnels are configured by this application."))
        body.addWidget(self._label("Verify HTTPS on your phone", strong=True))
        body.addWidget(self._label("Save this board's public CA certificate and transfer it privately to your phone. Check its SHA-256 fingerprint before trusting it. Android: install it as a CA certificate. iPhone/iPad: install the profile, then enable full trust in Certificate Trust Settings. Trust it only on devices you own."))
        self.web_fingerprint_box = self._code("")
        body.addWidget(self.web_fingerprint_box)
        self.web_certificate_button = self._button("Save public certificate", self._save_certificate)
        body.addWidget(self.web_certificate_button)
        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.refresh)
        self.apply_appearance()
        self._render_web()

    @staticmethod
    def _label(text: str, *, strong=False) -> QLabel:
        label = QLabel(tr(text) if text else "")
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setProperty("sectionSubtitle", not strong)
        label.setProperty("readingLabel", strong)
        return label

    def _code(self, text: str) -> QLabel:
        box = self._label(text)
        box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._code_boxes.append(box)
        return box

    @staticmethod
    def _button(text, action, *, primary=False):
        button = QPushButton(tr(text))
        button.setProperty("processButton", "secondary")
        button.setProperty("PrimaryAction", primary)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda _checked=False: action())
        return button

    def apply_appearance(self):
        self.setStyleSheet(process_stylesheet())
        for box in self._code_boxes:
            box.setStyleSheet(scale_stylesheet(
                f"background: {COLORS['panel_alt']}; color: {COLORS['text']}; border: 1px solid {COLORS['border_soft']};"
                "border-radius: 8px; padding: 9px 12px; font-family: monospace; font-size: 12px;"))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.pairing_layout.setDirection(QBoxLayout.Direction.TopToBottom if self.width() < 740 else QBoxLayout.Direction.LeftToRight)

    def set_updates_active(self, active):
        if active:
            self.timer.start()
            self.refresh()
        else:
            self.timer.stop()

    def refresh(self):
        self._background.start("web_status", web_access.status, on_success=self._apply_web,
                               on_error=lambda message: self.web_state_label.setText(tr(message)))

    def retranslate_dynamic_copy(self):
        self._device_signature = None
        self._render_web()

    def _apply_web(self, state):
        self._web_state = dict(state or {})
        self._render_web()

    def _render_web(self):
        state = self._web_state
        running = bool(state.get("running"))
        urls = state.get("urls") or []
        available = urls or ([state["local_url"]] if state.get("local_url") else [])
        self.web_state_label.setText(tr("Web access is active" if running else "Web access is stopped"))
        self.web_switch_button.setEnabled(not self._background.is_running("switch_web"))
        self.web_switch_button.setText(tr("Stop web access" if running else "Start web access"))
        self.web_switch_button.setProperty("PrimaryAction", not running)
        self.web_switch_button.style().unpolish(self.web_switch_button)
        self.web_switch_button.style().polish(self.web_switch_button)
        self.web_open_button.setEnabled(running)
        existing = [self.web_address.itemText(i) for i in range(self.web_address.count())]
        if existing != available:
            selected = self.web_address.currentText()
            self.web_address.blockSignals(True)
            self.web_address.clear()
            self.web_address.addItems(available)
            if selected in available:
                self.web_address.setCurrentText(selected)
            self.web_address.blockSignals(False)
        self.web_pin_box.setText(state.get("key") or "—")
        self.web_copy_url_button.setEnabled(bool(available))
        self.web_copy_pin_button.setEnabled(bool(state.get("key")))
        self._syncing_web = True
        try:
            self.web_lan_switch.setChecked(bool(state.get("lan")))
            autostart = state.get("autostart") or {}
            self.web_autostart_switch.setChecked(bool(autostart.get("enabled")))
            self.web_autostart_switch.setEnabled(bool(autostart.get("supported")) and not autostart.get("foreign"))
        finally:
            self._syncing_web = False
        networks = ", ".join(state.get("networks") or [])
        self.network_label.setText(tr_format("Allowed home networks: {networks}", networks=networks) if networks else tr("Access from this computer only; no home network is currently available."))
        fingerprint = state.get("trust_fingerprint") or ""
        self.web_fingerprint_box.setText("SHA-256\n" + fingerprint if fingerprint else tr("Start web access to prepare the certificate."))
        self.web_certificate_button.setEnabled(bool(fingerprint))
        self._render_qr()
        self._render_devices()

    def _render_qr(self):
        state = self._web_state
        address = self.web_address.currentText()
        signature = (address, state.get("key"), state.get("running"), state.get("tls", True), state.get("lan"))
        if signature == self._qr_signature:
            return
        self._qr_signature = signature
        if not state.get("running") or not state.get("lan") or not address.startswith("https://") or not state.get("key"):
            self.web_qr_image.clear()
            self.web_qr_image.setText(tr("Start web access and enable the local network to display your QR here."))
            return
        renderer = QSvgRenderer(QByteArray(web_access.pairing_svg(address + "#pair=" + state["key"])))
        pixmap = QPixmap(240, 240)
        pixmap.fill(Qt.GlobalColor.white)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        self.web_qr_image.setPixmap(pixmap)

    def _render_devices(self):
        devices = self._web_state.get("devices") or []
        signature = tuple((d["id"], d.get("control"), d.get("address"), d.get("agent")) for d in devices)
        if signature == self._device_signature:
            return
        self._device_signature = signature
        while self.device_list.count():
            item = self.device_list.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        for device in devices:
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 4, 0, 4)
            description = self._label("")
            raw_agent = device.get("agent") or ""
            platform = next((name for marker, name in (("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"),
                            ("Windows", "Windows"), ("Macintosh", "macOS"), ("Linux", "Linux")) if marker in raw_agent), tr("Browser"))
            browser = next((name for marker, name in (("Edg/", "Edge"), ("Firefox/", "Firefox"), ("Chrome/", "Chrome"),
                           ("Safari/", "Safari")) if marker in raw_agent), "")
            agent = " · ".join(part for part in (platform, browser) if part)
            description.setText(f"{agent} · {device.get('address', '')} · {device['id'][:8]}\n{tr('Hardware control' if device.get('control') else 'Monitoring only')}")
            layout.addWidget(description, 1)
            device_id = device["id"]
            control = bool(device.get("control"))
            layout.addWidget(self._button("Monitoring only" if control else "Allow hardware control",
                                          lambda d=device_id, c=control: self._device_control(d, not c)))
            layout.addWidget(self._button("Disconnect", lambda d=device_id: self._run("revoke", lambda: web_access.revoke(d))))
            self.device_list.addWidget(row)
        if not devices:
            self.device_list.addWidget(self._label("No connected browsers."))
        self.revoke_all_button.setEnabled(bool(devices))

    def _run(self, name, work):
        self._background.start(name, work, on_success=lambda _r: self.refresh(),
                               on_error=lambda message: show_toast(self, tr("Remote access"), tr(message), tone="red"))

    def _device_control(self, device, allowed):
        self._run("device_control", lambda: web_access.set_control(device, allowed))

    def _revoke_all(self):
        self._run("revoke_all", web_access.revoke_all)

    def _toggle_web(self):
        running = bool(self._web_state.get("running"))
        self.web_switch_button.setEnabled(False)

        def apply():
            if running:
                return web_access.stop()
            web_access.save_settings(tls=True)
            return web_access.start()
        self._run("switch_web", apply)

    def _open_web(self):
        url = self._web_state.get("local_url")
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _autostart_web_toggled(self, checked):
        if not self._syncing_web:
            self._run("web_autostart", lambda: web_access.set_autostart(checked))

    def _web_option(self, name, checked):
        if self._syncing_web:
            return

        def apply():
            web_access.save_settings(**{name: checked}, tls=True)
            if self._web_state.get("running"):
                web_access.stop()
                web_access.start()
        self._run("web_option", apply)

    def _new_web_key(self):
        self._run("web_key", lambda: web_access.access_key(renew=True))

    def _copy_web_url(self):
        self._copy(self.web_address.currentText())

    def _copy_web_pin(self):
        self._copy(self._web_state.get("key", ""))

    def _copy(self, text):
        if text:
            QGuiApplication.clipboard().setText(text)
            show_toast(self, tr("Copied"), tr("Remote access"), tone="green")

    def _save_certificate(self):
        try:
            source = web_access.trust_certificate()
            target, _filter = QFileDialog.getSaveFileName(self, tr("Save public certificate"),
                                                        str(Path.home() / "BC250-local-authority.crt"), "Certificate (*.crt)")
            if target:
                if Path(target).resolve() != source.resolve():
                    shutil.copyfile(source, target)
                show_toast(self, tr("Remote access"), tr("Public certificate saved. The private key stays on this board."), tone="green")
        except (OSError, RuntimeError) as error:
            show_toast(self, tr("Remote access"), str(error), tone="red")
