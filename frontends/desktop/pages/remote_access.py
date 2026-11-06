"""One web-access workspace: connection, QR pairing and device approval."""
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
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from bc250cc.application.system import web_access, web_pairing

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

QR_SIZE = 224


class RemoteAccessPage(QWidget):
    """Scan the QR on this screen to pair a device: it gets hardware control for good.

    A device that only typed the access key stays read-only until the owner
    approves it here. Approving is one click and has no expiry.
    """

    def __init__(self, parent: QWidget | None = None, *, settings=None):
        super().__init__(parent)
        self.setProperty("processPage", True)
        self._background = BackgroundExecutor(self)
        self._web_state = {}
        self._firewall_repair_pending = False
        self._name_health_display = None
        self._name_ready_samples = 0
        self._name_repair_pending = False
        self._syncing_web = False
        self._code_boxes = []
        self._panels = []
        self._dividers = []
        self._qr_signature = None
        self._pair_token = None
        self._known_devices = None
        self._updates_active = False
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
        scroll = self._scroll = QScrollArea()
        content = QWidget()
        configure_responsive_scroll_area(scroll, content)
        content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        content.setProperty("redesignedModule", True)
        root = QVBoxLayout(content)
        root.setContentsMargins(18, 8, 18, 20)
        self.card = self.web_card = SectionCard("Remote access", "Control and monitor this board from a browser on your home network.", icon_name="")
        self.card.root.setSpacing(14)
        root.addWidget(self.card)
        root.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        body = self.card.body

        # -- Status bar -----------------------------------------------------------------------
        status_panel, status = self._panel(QHBoxLayout)
        status.setSpacing(12)
        self.web_state_label = QLabel("")
        self.web_state_label.setObjectName("remoteStatusPill")
        self.web_state_label.setTextFormat(Qt.TextFormat.PlainText)
        status.addWidget(self.web_state_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.web_notice = self._label("")
        status.addWidget(self.web_notice, 1)
        # The active key, for signing in from a computer. A phone only needs the QR.
        self.key_row = QWidget()
        key_line = QHBoxLayout(self.key_row)
        key_line.setContentsMargins(0, 0, 0, 0)
        key_line.setSpacing(8)
        self.key_caption = self._label("Remote access key")
        key_line.addWidget(self.key_caption, 0, Qt.AlignmentFlag.AlignVCenter)
        self.web_pin_box = self._code("")
        self.web_pin_box.setWordWrap(False)
        self.web_pin_box.setToolTip(tr("Type this key in the browser. That device stays read-only until you approve it below."))
        key_line.addWidget(self.web_pin_box, 0, Qt.AlignmentFlag.AlignVCenter)
        self.web_copy_pin_button = self._button("Copy", self._copy_web_pin)
        self.web_new_key_button = self._button("New access key", self._new_web_key)
        key_line.addWidget(self.web_copy_pin_button)
        key_line.addWidget(self.web_new_key_button)
        key_line.addStretch(1)
        status.addWidget(self.key_row, 1)
        self.web_open_button = self._button("Open in browser", self._open_web)
        self.web_switch_button = self._button("Start web access", self._toggle_web, primary=True)
        status.addWidget(self.web_open_button)
        status.addWidget(self.web_switch_button)
        body.addWidget(status_panel)

        # -- Pair a device ----------------------------------------------------------------------
        pair_panel, pair_box = self._panel(QVBoxLayout)
        pair_box.setSpacing(10)
        pair_box.addWidget(self._label("Pair a device", strong=True))
        self.pairing_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.pairing_layout.setSpacing(24)
        pair_box.addLayout(self.pairing_layout)
        connection = QVBoxLayout()
        connection.setSpacing(6)
        self.pairing_layout.addLayout(connection, 1)
        connection.addWidget(self._label("Connect your phone to the same Wi-Fi and scan the code. It pairs right away with full hardware control, with no key to type."))
        self.web_address = GuardedComboBox()
        self._web_address_chosen = False
        self.web_address.activated.connect(lambda _index: setattr(self, "_web_address_chosen", True))
        self.web_address.setAccessibleName(tr("Address"))
        self.web_address.currentIndexChanged.connect(self._render_qr)
        connection.addWidget(self.web_address)
        self.web_copy_url_button = self._button("Copy address", self._copy_web_url)
        connection.addWidget(self.web_copy_url_button)
        self.web_name_status = self._label("")
        connection.addWidget(self.web_name_status)
        self.web_name_repair = self._button("Repair local address", self._repair_local_name)
        connection.addWidget(self.web_name_repair)
        self.web_firewall_status = self._label("")
        connection.addWidget(self.web_firewall_status)
        self.web_firewall_repair = self._button("Configure LAN firewall", self._repair_firewall)
        connection.addWidget(self.web_firewall_repair)
        connection.addSpacing(8)
        divider = QFrame()
        divider.setObjectName("remoteDivider")
        divider.setFixedHeight(1)
        self._dividers.append(divider)
        connection.addWidget(divider)
        connection.addSpacing(8)
        # Both options on one clean row, the certificate right under them.
        self.web_lan_switch = ToggleSwitch()
        self.web_lan_switch.setAccessibleName(tr("Reachable from the local network"))
        self.web_lan_switch.toggled.connect(lambda checked: self._web_option("lan", checked))
        self.web_autostart_switch = ToggleSwitch()
        self.web_autostart_switch.setAccessibleName(tr("Start with the session"))
        self.web_autostart_switch.toggled.connect(self._autostart_web_toggled)
        options = QHBoxLayout()
        options.setSpacing(10)
        for index, (switch, text) in enumerate(((self.web_lan_switch, "Reachable from the local network"),
                                                (self.web_autostart_switch, "Start with the session"))):
            if index:
                options.addSpacing(18)
            options.addWidget(switch, 0, Qt.AlignmentFlag.AlignVCenter)
            options.addWidget(self._label(text), 1)
        connection.addLayout(options)
        self.web_certificate_button = self._button("Download certificate", self._save_certificate)
        connection.addWidget(self.web_certificate_button)
        connection.addStretch(1)
        pairing = QVBoxLayout()
        pairing.setSpacing(6)
        self.pairing_layout.addLayout(pairing)
        self.web_qr_image = QLabel()
        self.web_qr_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.web_qr_image.setFixedSize(QR_SIZE, QR_SIZE)
        self.web_qr_image.setWordWrap(True)
        self.web_qr_image.setAccessibleName(tr("Scan to connect"))
        pairing.addWidget(self.web_qr_image, 0, Qt.AlignmentFlag.AlignHCenter)
        note = self._label("Scan to pair. The code works once and renews by itself.")
        note.setFixedWidth(QR_SIZE)
        note.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.web_qr_note = note
        pairing.addWidget(note)
        pairing.addStretch(1)
        body.addWidget(pair_panel)

        # -- Devices ----------------------------------------------------------------------------
        device_panel, device_box = self._panel(QVBoxLayout)
        device_box.setSpacing(8)
        self.device_heading = self._label("Paired devices", strong=True)
        device_box.addWidget(self.device_heading)
        self.device_hint = self._label("A paired device keeps hardware control until you disconnect it or create a new access key.")
        device_box.addWidget(self.device_hint)
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
        self.device_group = QVBoxLayout()
        self.device_group.setSpacing(2)
        device_box.addLayout(self.device_group)
        self.device_group.addWidget(self.device_table)
        self.device_grip = ResizeGrip()
        self.device_grip.setAccessibleName(tr("Resize connected devices table"))
        self.device_grip.setToolTip(tr("Drag to resize the table. Double-click to fit its rows."))
        self.device_grip.pressed.connect(lambda: setattr(self, "_table_drag_start", self.device_table.height()))
        self.device_grip.dragged.connect(lambda delta: self._set_device_table_height(self._table_drag_start + delta))
        self.device_grip.double_clicked.connect(self._fit_device_table)
        self.device_group.addWidget(self.device_grip)
        self.device_empty_label = self._label("No connected browsers.")
        self.device_group.addWidget(self.device_empty_label)
        actions = self.device_actions_layout = QHBoxLayout()
        actions.setSpacing(8)
        self.device_control_button = self._button("Approve device", self._approve_selected_device, primary=True)
        self.device_disconnect_button = self._button("Disconnect", self._disconnect_selected_device)
        self.revoke_all_button = self._button("Disconnect all devices", self._revoke_all)
        actions.addWidget(self.device_control_button)
        actions.addWidget(self.device_disconnect_button)
        actions.addStretch(1)
        actions.addWidget(self.revoke_all_button)
        device_box.addLayout(actions)
        body.addWidget(device_panel)

        # The fingerprint is still kept for anyone who wants to compare it; it is just not shown.
        self.web_fingerprint_box = self._code("")
        self.web_fingerprint_box.hide()

        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.refresh)
        self.apply_appearance()
        self._render_web()

    # -- building blocks ----------------------------------------------------------------------

    def _panel(self, layout_class):
        panel = QFrame()
        panel.setObjectName("remotePanel")
        layout = layout_class(panel)
        layout.setContentsMargins(16, 14, 16, 14)
        self._panels.append(panel)
        return panel, layout

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
        from .. import theme
        light = theme.ACTIVE_MODE == "light"
        for panel in self._panels:
            panel.setStyleSheet(scale_stylesheet(
                f"QFrame#remotePanel {{ background: {c['panel']}; border: 1px solid {c['border_soft']}; border-radius: 12px; }}"
                "QFrame#remotePanel QLabel { border: none; background: transparent; }"))
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
                f"background: {c['panel_alt']}; color: {c['text']}; border: 1px solid {c['border_soft']};"
                "border-radius: 8px; padding: 9px 12px; font-family: monospace; font-size: 12px;"))
        for divider in self._dividers:
            divider.setStyleSheet(f"QFrame#remoteDivider {{ background: {c['border_soft']}; border: none; }}")
        self._style_status_pill()

    def _style_status_pill(self):
        c = COLORS
        running = bool(self._web_state.get("running"))
        foreground, background = (c["green"], c["green_soft"]) if running else (c["muted"], c["neutral_soft"])
        self.web_state_label.setStyleSheet(scale_stylesheet(
            f"QLabel#remoteStatusPill {{ color: {foreground}; background: {background}; border: none;"
            " border-radius: 12px; padding: 5px 14px; font-size: 12px; font-weight: 700; }"))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.pairing_layout.setDirection(QBoxLayout.Direction.TopToBottom if self.width() < 740 else QBoxLayout.Direction.LeftToRight)
        self.device_actions_layout.setDirection(QBoxLayout.Direction.TopToBottom if self.width() < 560 else QBoxLayout.Direction.LeftToRight)

    def hideEvent(self, event):
        self._view_settings.sync()
        super().hideEvent(event)

    # -- refresh --------------------------------------------------------------------------------

    def set_updates_active(self, active):
        self._updates_active = bool(active)
        if active:
            self.timer.start()
            self.refresh()
        else:
            self.timer.stop()

    def refresh(self):
        self._background.start("web_status", web_access.status, on_success=self._apply_web,
                               on_error=lambda message: self.web_notice.setText(tr(message)))

    def retranslate_dynamic_copy(self):
        self._render_web()

    def _apply_web(self, state):
        self._web_state = dict(state or {})
        health = self._web_state.get("name_health") or {}
        previous = self._name_health_display or {}
        if not self._name_repair_pending:
            # A single successful/uncertain sample must not withdraw a repair
            # action the owner is about to press. Two successful reads settle it.
            if health.get("status") == "ready" and previous.get("repairable"):
                self._name_ready_samples += 1
                if self._name_ready_samples >= 2:
                    self._name_health_display = health
            elif health.get("status") == "unavailable" and previous.get("repairable"):
                self._name_ready_samples = 0
            else:
                self._name_ready_samples = 0
                self._name_health_display = health
        self._render_web()

    def _notice(self, state, firewall):
        """A plain sentence only when something blocks pairing; empty when all is well."""
        if not state.get("running"):
            return "Start web access to pair a phone."
        if not state.get("lan"):
            return "Turn on local network access below so phones can connect."
        if firewall.get("state") in {"blocked", "needs_check", "update_helper"}:
            return "The firewall may be blocking other devices. Use Configure LAN firewall."
        if firewall.get("state") == "no_network":
            return "No connected private network was detected. Connect this board to your Wi-Fi or cable."
        return ""

    def _render_web(self):
        state = self._web_state
        health = self._name_health_display if self._name_health_display is not None else state.get("name_health") or {}
        messages = {
            "resolver_failed": "The local address is advertised, but this computer cannot resolve it. Use the numeric address or repair name resolution.",
            "publication_failed": "The local address is not advertised yet. Use the numeric address or repair local name discovery.",
            "conflict": "The local address points to another device. Use the numeric address.",
            "unavailable": "Local name resolution could not be checked. Use the numeric address.",
        }
        # Only problems are shown: a working setup needs no explanation.
        self.web_name_status.setText(tr(messages.get(health.get("status"), "")))
        self.web_name_status.setVisible(bool(state.get("lan")) and health.get("status") in messages)
        # A successful host NSS lookup does not prove a Flatpak browser can
        # resolve the alias. Keep explicit repair reachable for that case.
        self.web_name_repair.setVisible(
            bool(health.get("repairable")) or self._name_repair_pending
            or bool(state.get("lan") and state.get("running") and health.get("status") == "ready")
        )
        self.web_name_repair.setEnabled(not self._name_repair_pending and not self._background.is_running("name_repair"))
        firewall = state.get("firewall") or {}
        firewall_messages = {
            "blocked": "The firewall may block access from other devices. Configure LAN access below.",
            "needs_check": "The firewall needs an administrator check before LAN access can be configured.",
            "inactive": "UFW is inactive. If connection fails, check Wi-Fi isolation and other network filters.",
            "unknown": "The firewall could not be checked. LAN connectivity is not verified.",
            "unsupported": "Custom or multiple firewall managers detected. Automatic changes are unavailable.",
            "update_helper": "Update or reinstall Control Center to install the LAN firewall helper.",
        }
        text = tr(firewall_messages.get(firewall.get("state"), ""))
        if text and firewall.get("networks"):
            text += "\nTCP " + str(state.get("port", 8250)) + " · " + ", ".join(firewall["networks"])
        self.web_firewall_status.setText(text)
        self.web_firewall_status.setVisible(bool(state.get("lan")) and bool(text))
        self.web_firewall_repair.setVisible(bool(state.get("lan")) and (bool(firewall.get("repairable")) or self._firewall_repair_pending))
        self.web_firewall_repair.setEnabled(not self._firewall_repair_pending)
        running = bool(state.get("running"))
        urls = state.get("urls") or []
        available = urls or ([state["local_url"]] if state.get("local_url") else [])
        self.web_state_label.setText(tr("Web access is active" if running else "Web access is stopped"))
        notice = self._notice(state, firewall)
        self.web_notice.setText(tr(notice) if notice else "")
        self.web_notice.setVisible(bool(notice))
        self.key_row.setVisible(running and bool(state.get("key")))
        self._style_status_pill()
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
            # Prefer the announced alias when it arrives after the initial IP
            # fallback, while respecting an address explicitly chosen by the user.
            if self._web_address_chosen and selected in available:
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
        fingerprint = state.get("trust_fingerprint") or ""
        self.web_fingerprint_box.setText("SHA-256\n" + fingerprint if fingerprint else "")
        self.web_certificate_button.setEnabled(bool(fingerprint))
        self._render_qr()
        self._render_devices()

    # -- QR pairing -----------------------------------------------------------------------------

    def _current_pair_token(self):
        """The token the QR carries: kept while fresh, replaced once used or close to expiry."""
        token = self._pair_token
        try:
            age = web_pairing.age(token) if token else None
            if age is None or age > web_pairing.RENEW_SECONDS:
                token = self._pair_token = web_pairing.issue()
        except OSError:
            return None
        return token

    def _render_qr(self):
        state = self._web_state
        address = self.web_address.currentText()
        ready = bool(state.get("running") and state.get("lan") and address.startswith("https://"))
        token = self._current_pair_token() if ready else None
        signature = (address, token, state.get("running"), state.get("tls", True), state.get("lan"))
        if signature == self._qr_signature:
            return
        self._qr_signature = signature
        if not ready or not token:
            self.web_qr_image.clear()
            self.web_qr_image.setText(tr("Start web access and enable the local network to display your QR here."))
            return
        renderer = QSvgRenderer(QByteArray(web_access.pairing_svg(address + "#pair=" + token)))
        pixmap = QPixmap(self.web_qr_image.size())
        pixmap.fill(Qt.GlobalColor.white)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        self.web_qr_image.setPixmap(pixmap)

    # -- devices --------------------------------------------------------------------------------

    def _selected_device(self):
        row = self.device_table.currentRow()
        item = self.device_table.item(row, 0) if row >= 0 and self.device_table.selectedItems() else None
        identifier = item.data(Qt.ItemDataRole.UserRole) if item else None
        return next((d for d in self._web_state.get("devices", []) if d["id"] == identifier), None)

    def _render_devices(self):
        devices = self._web_state.get("devices") or []
        selected = self._selected_device()
        selected_id = selected["id"] if selected else None
        identifiers = {device["id"] for device in devices}
        if self._known_devices is not None and identifiers - self._known_devices:
            show_toast(self, tr("Remote access"), tr("New device paired"), tone="green")
        self._known_devices = identifiers
        position = self.device_table.verticalScrollBar().value()
        self.device_table.blockSignals(True)
        self.device_table.setHorizontalHeaderLabels([tr(label) for label in (
            "Device", "IP address", "Device code", "Permissions", "Status", "Last activity", "Session")])
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
            expiry = web_access.deadline(device)
            expiry_text, expiry_full = timestamp(expiry)
            if expiry:
                expiry_date = datetime.fromtimestamp(expiry).astimezone()
                today = datetime.fromtimestamp(now).astimezone()
                if expiry_date.date() != today.date():
                    expiry_text = expiry_date.strftime("%d/%m/%Y %H:%M" if expiry_date.year != today.year else "%d/%m %H:%M")
            if web_access.is_permanent(device):
                expiry_text, expiry_full = tr("Permanent"), ""
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
        approved = bool(device and device.get("control") and web_access.is_permanent(device))
        self.device_control_button.setEnabled(device is not None and not approved)
        self.device_control_button.setText(tr("Approved" if approved else "Approve device"))
        self.device_disconnect_button.setEnabled(device is not None)

    def _approve_selected_device(self):
        device = self._selected_device()
        if device:
            self._run("device_approve", lambda: web_access.approve(device["id"]))

    def _disconnect_selected_device(self):
        device = self._selected_device()
        if device:
            self._run("revoke", lambda: web_access.revoke(device["id"]))

    def _run(self, name, work):
        self._background.start(name, work, on_success=lambda _r: self.refresh(),
                               on_error=lambda message: show_toast(self, tr("Remote access"), tr(message), tone="red"))

    def _revoke_all(self):
        self._run("revoke_all", web_access.revoke_all)

    # -- network repairs --------------------------------------------------------------------------

    def _repair_firewall(self):
        if self._firewall_repair_pending:
            return
        self._firewall_repair_pending = True
        self._render_web()
        networks = ", ".join((self._web_state.get("firewall") or {}).get("networks", []))
        message = tr("Allow this web port only from the connected private networks? Existing firewall rules are preserved. Administrator authorization is required.")
        message += "\n\nTCP " + str(self._web_state.get("port", 8250)) + " · " + networks

        def finished():
            self._firewall_repair_pending = False
            self._render_web()
            self.refresh()
        if QMessageBox.question(self, tr("Configure LAN firewall"), message,
                               QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                               QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            finished()
            return
        if not self._background.start(
            "firewall_repair", web_access.repair_firewall,
            on_error=lambda message: show_toast(self, tr("Remote access"), tr(message), tone="red"),
            on_finished=finished,
        ):
            finished()

    def _repair_local_name(self):
        if self._name_repair_pending:
            return
        self._name_repair_pending = True
        self._render_web()
        if QMessageBox.question(
            self, tr("Repair local address"),
            tr("Repair local name discovery and lookup? This may install Avahi and its resolver module, enable the Avahi service and update the system resolver configuration. A configuration backup is saved and failed resolver changes are reverted. Administrator authorization is required.") + "\n\n" + tr("On SteamOS, local name publishing will also be enabled.") + "\n" + tr("A local address entry lets this computer reach bc250cc.local even when its browser cannot use mDNS."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            def finished():
                self._name_repair_pending = False
                self._name_ready_samples = 0
                self._render_web()
                self.refresh()

            if not self._background.start(
                "name_repair", web_access.repair_local_name,
                on_error=lambda message: show_toast(self, tr("Remote access"), tr(message), tone="red"),
                on_finished=finished,
            ):
                finished()
        else:
            self._name_repair_pending = False
            self._render_web()

    # -- actions ----------------------------------------------------------------------------------

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
        url = self.web_address.currentText()
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
            target, _filter = QFileDialog.getSaveFileName(self, tr("Download certificate"),
                                                        str(Path.home() / "BC250-local-authority.crt"), "Certificate (*.crt)")
            if target:
                if Path(target).resolve() != source.resolve():
                    shutil.copyfile(source, target)
                show_toast(self, tr("Remote access"), tr("Certificate saved. Install it on your phone to trust this board."), tone="green")
        except (OSError, RuntimeError) as error:
            show_toast(self, tr("Remote access"), str(error), tone="red")
