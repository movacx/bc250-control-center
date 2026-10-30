"""One web-access workspace: connection, visible pairing and device permissions."""
from __future__ import annotations

import shutil
import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QByteArray, Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QGuiApplication, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QBoxLayout,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bc250cc.application.system import web_access

from ..components.async_tools import BackgroundExecutor
from ..components.buttons import WrappingButton as QPushButton
from ..components.full_diagnosis_dialog import ResizeGrip
from ..components.page_widgets import SectionCard
from ..components.responsive import configure_responsive_scroll_area
from ..components.toast import show_toast
from ..components.toggle_switch import ToggleSwitch
from ..components.wheel_guard import GuardedComboBox
from ..core.preferences import application_settings
from ..i18n import tr, tr_format
from ..theme import COLORS, scale_stylesheet
from .processes import process_stylesheet


class RemoteAccessPage(QWidget):
    """The desktop owner grants control; a newly paired phone can only monitor."""

    def __init__(self, parent: QWidget | None = None, *, settings=None):
        super().__init__(parent)
        self.setProperty("processPage", True)
        self._background = BackgroundExecutor(self)
        self._web_state = {}
        self._syncing_web = False
        self._code_boxes = []
        self._qr_signature = None
        self._view_settings = settings if settings is not None else application_settings()
        try:
            saved_height = self._view_settings.value("remote_access/device_table_height")
            self._table_height = max(90, min(3000, int(saved_height))) if saved_height is not None else None
        except (TypeError, ValueError):
            self._table_height = None
        self._table_drag_start = 0
        self._save_view_timer = QTimer(self)
        self._save_view_timer.setSingleShot(True)
        self._save_view_timer.setInterval(200)
        self._save_view_timer.timeout.connect(self._view_settings.sync)
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
        self.card.root.setSpacing(10)
        root.addWidget(self.card)
        root.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        body = self.card.body
        self.web_state_label = self._label("")
        controls = QHBoxLayout()
        self.web_switch_button = self._button("Start web access", self._toggle_web, primary=True)
        self.web_open_button = self._button("Open in browser", self._open_web)
        controls.addWidget(self.web_switch_button)
        controls.addWidget(self.web_open_button)
        controls.addStretch(1)

        self.pairing_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.pairing_layout.setSpacing(20)
        body.addLayout(self.pairing_layout)
        connection = QVBoxLayout()
        connection.setContentsMargins(0, 8, 0, 0)
        connection.setSpacing(4)
        self.pairing_layout.addLayout(connection, 1)
        connection.addWidget(self.web_state_label)
        connection.addLayout(controls)
        connection.addSpacing(6)
        connection.addWidget(self._label("Connect your phone", strong=True))
        self.web_address = GuardedComboBox()
        self.web_address.setAccessibleName(tr("Address"))
        self.web_address.currentIndexChanged.connect(self._render_qr)
        connection.addWidget(self.web_address)
        self.web_copy_url_button = self._button("Copy address", self._copy_web_url)
        connection.addWidget(self.web_copy_url_button)
        connection.addSpacing(6)
        connection.addWidget(self._label("Access key", strong=True))
        self.web_pin_box = self._code("")
        connection.addWidget(self.web_pin_box)
        key_controls = QHBoxLayout()
        self.web_copy_pin_button = self._button("Copy access key", self._copy_web_pin)
        self.web_new_key_button = self._button("New access key", self._new_web_key)
        key_controls.addWidget(self.web_copy_pin_button)
        key_controls.addWidget(self.web_new_key_button)
        connection.addLayout(key_controls)
        connection.addStretch(1)
        pairing = QVBoxLayout()
        pairing.setSpacing(0)
        self.pairing_layout.addLayout(pairing)
        self.web_qr_image = QLabel()
        self.web_qr_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.web_qr_image.setFixedSize(240, 240)
        self.web_qr_image.setWordWrap(True)
        self.web_qr_image.setAccessibleName(tr("Scan to connect"))
        pairing.addWidget(self.web_qr_image, 0, Qt.AlignmentFlag.AlignHCenter)
        note = self._label("Scan on the same Wi-Fi. This QR contains your access key; keep it private.")
        note.setFixedWidth(240)
        note.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.web_qr_note = note
        pairing.addWidget(note)
        pairing.addStretch(1)
        body.addSpacing(8)
        self.device_heading = self._label("Connected devices · Read-only until you verify the code and allow control.", strong=True)
        self.device_heading.setToolTip(tr("Sessions expire after 30 minutes without activity or eight hours in total. Closing access disconnects the selected browser; a new login starts with monitoring permission."))
        body.addWidget(self.device_heading)
        self.device_table = QTableWidget(0, 7)
        self.device_table.setObjectName("remoteDeviceTable")
        self.device_table.setAlternatingRowColors(True)
        self.device_table.setAccessibleName(tr("Connected devices"))
        self.device_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.device_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.device_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.device_table.setShowGrid(False)
        self.device_table.setWordWrap(False)
        self.device_table.verticalHeader().hide()
        self.device_table.verticalHeader().setDefaultSectionSize(40)
        self.device_table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.device_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.device_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.device_table.setMinimumHeight(120)
        self.device_table.setMaximumHeight(3000)
        self.device_table.itemSelectionChanged.connect(self._update_device_actions)
        body.addWidget(self.device_table)
        self.device_grip = ResizeGrip()
        self.device_grip.setAccessibleName(tr("Resize connected devices table"))
        self.device_grip.setToolTip(tr("Drag to resize the table. Double-click to fit its rows."))
        self.device_grip.pressed.connect(lambda: setattr(self, "_table_drag_start", self.device_table.height()))
        self.device_grip.dragged.connect(lambda delta: self._set_device_table_height(self._table_drag_start + delta))
        self.device_grip.double_clicked.connect(self._fit_device_table)
        body.addWidget(self.device_grip)
        self.device_empty_label = self._label("No connected browsers.")
        body.addWidget(self.device_empty_label)
        actions = QHBoxLayout()
        self.device_control_button = self._button("Allow hardware control", self._toggle_selected_device)
        self.device_disconnect_button = self._button("Disconnect", self._disconnect_selected_device)
        self.revoke_all_button = self._button("Disconnect all devices", self._revoke_all)
        actions.addWidget(self.device_control_button)
        actions.addWidget(self.device_disconnect_button)
        actions.addStretch(1)
        actions.addWidget(self.revoke_all_button)
        body.addLayout(actions)

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
        c = COLORS
        # Match the light game tables: white rows, a soft grey header and thin
        # separators. Dark mode retains alternating surfaces for distinction.
        from .. import theme
        light = theme.ACTIVE_MODE == "light"
        self.device_table.setAlternatingRowColors(not light)
        self.device_table.setStyleSheet(scale_stylesheet(
            f"QTableWidget#remoteDeviceTable {{ background: {c['panel']}; alternate-background-color: {c['panel'] if light else c['panel_alt']};"
            f" color: {c['text']}; border: 1px solid {c['border']}; border-radius: 7px; }}"
            f"QTableWidget#remoteDeviceTable::item {{ color: {c['text']}; border-bottom: 1px solid {c['border']}; padding: 0 8px; }}"
            f"QTableWidget#remoteDeviceTable::item:selected {{ background: {c['blue_soft']}; color: {c['text']}; }}"
            f"QTableWidget#remoteDeviceTable QHeaderView::section {{ background: {c['panel_alt']}; color: {c['text']};"
            f" border: none; border-bottom: 1px solid {c['border']}; padding: 9px 8px; font-size: 11px; font-weight: 700; }}"))
        for box in self._code_boxes:
            box.setStyleSheet(scale_stylesheet(
                f"background: {COLORS['panel_alt']}; color: {COLORS['text']}; border: 1px solid {COLORS['border_soft']};"
                "border-radius: 8px; padding: 9px 12px; font-family: monospace; font-size: 12px;"))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.pairing_layout.setDirection(QBoxLayout.Direction.TopToBottom if self.width() < 740 else QBoxLayout.Direction.LeftToRight)

    def hideEvent(self, event):
        self._view_settings.sync()
        super().hideEvent(event)

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
        pixmap = QPixmap(self.web_qr_image.size())
        pixmap.fill(Qt.GlobalColor.white)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        self.web_qr_image.setPixmap(pixmap)

    def _selected_device(self):
        row = self.device_table.currentRow()
        item = self.device_table.item(row, 0) if row >= 0 and self.device_table.selectedItems() else None
        identifier = item.data(Qt.ItemDataRole.UserRole) if item else None
        return next((d for d in self._web_state.get("devices", []) if d["id"] == identifier), None)

    def _render_devices(self):
        devices = self._web_state.get("devices") or []
        selected = self._selected_device()
        selected_id = selected["id"] if selected else None
        position = self.device_table.verticalScrollBar().value()
        self.device_table.blockSignals(True)
        self.device_table.setHorizontalHeaderLabels([tr(label) for label in (
            "Device", "IP address", "Device code", "Permissions", "Status", "Last activity", "Expires")])
        self.device_table.setRowCount(len(devices))
        self.device_table.clearSelection()
        now = time.time()

        def timestamp(value):
            if not value:
                return "—", ""
            date = datetime.fromtimestamp(float(value)).astimezone()
            return date.strftime("%H:%M:%S"), date.strftime("%Y-%m-%d %H:%M:%S %Z")

        for index, device in enumerate(devices):
            raw_agent = device.get("agent") or ""
            platform = next((name for marker, name in (("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"),
                            ("Windows", "Windows"), ("Macintosh", "macOS"), ("Linux", "Linux")) if marker in raw_agent), tr("Browser"))
            browser = next((name for marker, name in (("Edg/", "Edge"), ("Firefox/", "Firefox"), ("Chrome/", "Chrome"),
                           ("Safari/", "Safari")) if marker in raw_agent), "")
            seen = device.get("seen")
            active = seen is not None and now - float(seen) <= 15
            seen_text, seen_full = timestamp(seen)
            expiry = min(float(device.get("expires") or 0), float(seen or 0) + 1800)
            expiry_text, expiry_full = timestamp(expiry)
            values = (" · ".join(part for part in (platform, browser) if part), device.get("address", "—"),
                      device["id"][:8], tr("Hardware control" if device.get("control") else "Monitoring only"),
                      tr("Active" if active else "Idle") if seen else "—", seen_text, expiry_text)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                item.setData(Qt.ItemDataRole.UserRole, device["id"])
                if column == 0:
                    item.setToolTip(raw_agent)
                elif column == 2:
                    item.setToolTip(tr_format("Session started: {time}", time=timestamp(device.get("created"))[1] or "—"))
                elif column in (5, 6):
                    item.setToolTip(seen_full if column == 5 else expiry_full)
                self.device_table.setItem(index, column, item)
            if device["id"] == selected_id:
                self.device_table.selectRow(index)
        self.device_table.blockSignals(False)
        self.device_table.verticalScrollBar().setValue(position)
        self.device_table.setFixedHeight(self._table_height or min(320, max(90, 40 * len(devices) + 42)))
        self.device_empty_label.setVisible(not devices)
        self.revoke_all_button.setEnabled(bool(devices))
        self._update_device_actions()

    def _set_device_table_height(self, height):
        self._table_height = max(90, min(3000, int(height)))
        self.device_table.setFixedHeight(self._table_height)
        self._view_settings.setValue("remote_access/device_table_height", self._table_height)
        self._save_view_timer.start()

    def _fit_device_table(self):
        header = self.device_table.horizontalHeader().height()
        rows = self.device_table.verticalHeader().length()
        scrollbar = self.device_table.horizontalScrollBar()
        extra = scrollbar.height() if scrollbar.isVisible() else 0
        self._set_device_table_height(header + rows + extra + 4)

    def _update_device_actions(self):
        device = self._selected_device()
        self.device_control_button.setEnabled(device is not None)
        self.device_disconnect_button.setEnabled(device is not None)
        self.device_control_button.setText(tr("Monitoring only" if device and device.get("control") else "Allow hardware control"))

    def _toggle_selected_device(self):
        device = self._selected_device()
        if device:
            self._device_control(device["id"], not bool(device.get("control")))

    def _disconnect_selected_device(self):
        device = self._selected_device()
        if device:
            self._run("revoke", lambda: web_access.revoke(device["id"]))

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

        self._run("web_option", lambda: web_access.configure(**{name: checked}, tls=True))

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
