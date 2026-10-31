"""One web-access workspace: connection, visible pairing and device permissions."""
from __future__ import annotations

import math
import shutil
import time
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import (
    QByteArray,
    QElapsedTimer,
    QEvent,
    QPoint,
    QRect,
    QRectF,
    Qt,
    QTimer,
    QUrl,
)
from PyQt6.QtGui import (
    QColor,
    QDesktopServices,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPixmap,
    QRadialGradient,
)
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
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from bc250cc.application.system import web_access

from .. import theme
from ..components.async_tools import BackgroundExecutor
from ..components.buttons import WrappingButton as QPushButton
from ..components.full_diagnosis_dialog import ResizeGrip
from ..components.page_widgets import SectionCard
from ..components.responsive import configure_responsive_scroll_area
from ..components.toast import show_toast
from ..components.toggle_switch import ToggleSwitch
from ..components.wheel_guard import GuardedComboBox
from ..components.widgets import readable_text_on
from ..core.preferences import application_settings
from ..i18n import tr, tr_format
from ..theme import COLORS, scale_stylesheet
from .processes import process_stylesheet

PRIVACY_SECONDS = 5 * 60


def _privacy_time():
    # Linux's boottime includes suspend, so reopening a laptop cannot extend
    # the five-minute viewing window. Other platforms use a monotonic clock.
    if hasattr(time, "CLOCK_BOOTTIME"):
        return time.clock_gettime(time.CLOCK_BOOTTIME)
    return time.monotonic()


class _RemotePrivacyCover(QWidget):
    """Animated, pre-redacted layout context inside the existing access card."""

    def __init__(self, parent):
        super().__init__(parent)
        self._phase = 0.0
        self._motion_clock = QElapsedTimer()
        self._context = QPixmap()
        self._light_context = QPixmap()
        self._night_context = QPixmap()
        self._message = QWidget(self)
        box = QVBoxLayout(self._message)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(12)
        self.title = QLabel()
        self.title.setObjectName("remotePrivacyTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setWordWrap(True)
        box.addWidget(self.title)
        self.description = QLabel()
        self.description.setObjectName("remotePrivacyDescription")
        self.description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.description.setWordWrap(True)
        box.addWidget(self.description)
        self.reveal_button = QPushButton()
        self.reveal_button.setObjectName("remotePrivacyReveal")
        self.reveal_button.setCursor(Qt.CursorShape.PointingHandCursor)
        box.addWidget(self.reveal_button, 0, Qt.AlignmentFlag.AlignHCenter)
        self._sweep = QTimer(self)
        self._sweep.setInterval(16)
        self._sweep.setTimerType(Qt.TimerType.PreciseTimer)
        self._sweep.timeout.connect(self._animate)
        self.retranslate()
        self.apply_appearance()

    def _animate(self):
        self._phase = (self._motion_clock.elapsed() % 18000) / 18000
        self.update()

    def set_context(self, snapshot):
        # This source has already had every private field removed. Retain only
        # a small softened thumbnail, never a full-resolution screen capture.
        self._context = (snapshot.scaledToWidth(128, Qt.TransformationMode.SmoothTransformation)
                         if not snapshot.isNull() else QPixmap())
        self._light_context = QPixmap()
        self._night_context = QPixmap()
        if not self._context.isNull():
            # Cache all variants so changing theme while locked also
            # changes the veil. The source is already redacted.
            image = self._context.toImage()
            light_image = image.copy()
            night_image = image.copy()
            light = QColor(COLORS["panel"]).lightness() > 127
            for y in range(image.height()):
                for x in range(image.width()):
                    colour = image.pixelColor(x, y)
                    luminance = round(.2126 * colour.red() + .7152 * colour.green() + .0722 * colour.blue())
                    silhouette = 255 - luminance if light else luminance
                    value = 37 + round(silhouette * .23)
                    image.setPixelColor(x, y, QColor(value, value + 2, value + 4))
                    shade = round(silhouette * .20)
                    night_image.setPixelColor(x, y, QColor(28 + shade, 34 + shade, 44 + shade))
                    value = 230 - round(silhouette * .20)
                    light_image.setPixelColor(x, y, QColor(value, value + 1, value + 3))
            self._context = QPixmap.fromImage(image)
            self._light_context = QPixmap.fromImage(light_image)
            self._night_context = QPixmap.fromImage(night_image)
        self.update()

    def retranslate(self):
        self.setAccessibleName(tr("Hidden remote access information"))
        self.title.setText(tr("Information protected"))
        self.description.setText(tr("Access keys, codes and devices are hidden."))
        self.reveal_button.setText(tr("Show information"))

    def set_visible_region(self, region):
        width = max(180, min(380, region.width() - 48))
        self._message.setFixedWidth(width)
        layout = self._message.layout()
        height = max(layout.minimumSize().height(), layout.heightForWidth(width))
        self._message.setFixedHeight(height)
        self._message.move(max(16, region.center().x() - width // 2),
                           max(region.top() + 16, region.center().y() - self._message.height() // 2))

    def apply_appearance(self):
        c = COLORS
        light = QColor(c["panel"]).lightness() > 127
        title, description = ("#252A32", "#4F5865") if light else ("#F2F3F5", "#CBD0D6")
        title_size = 21 if light else 18
        description_size = 13 if light else 12
        ink = readable_text_on(QColor(c["blue"])).name()
        self.setStyleSheet(scale_stylesheet(
            f"QLabel#remotePrivacyTitle {{ color: {title}; font-size: {title_size}px; font-weight: 700; background: transparent; }}"
            f"QLabel#remotePrivacyDescription {{ color: {description}; font-size: {description_size}px; background: transparent; }}"
            f"QPushButton#remotePrivacyReveal {{ background: {c['blue']}; color: {ink}; border: 1px solid {c['blue']};"
            " border-radius: 8px; padding: 9px 18px; font-size: 12px; font-weight: 650; }"
            f"QPushButton#remotePrivacyReveal:hover {{ border-color: {c['blue_border']}; }}"))
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self._motion_clock.start()
        self._sweep.start()

    def hideEvent(self, event):
        self._sweep.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        boundary = QPainterPath()
        boundary.addRoundedRect(QRectF(self.rect()), 14, 14)
        painter.setClipPath(boundary)
        light = QColor(COLORS["panel"]).lightness() > 127
        night = theme.ACTIVE_THEME == "midnight"
        base = QColor("#E2E6EB" if light else "#1D232D" if night else "#27292D")
        painter.fillRect(self.rect(), base)
        phase = self._phase * math.tau
        if not self._context.isNull():
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.setOpacity(.88)
            # Floating-point geometry avoids the one-pixel jumps of a rounded
            # position. Motion is confined to the background, never the text.
            dx, dy = 7 * math.sin(phase), 5 * math.cos(phase)
            context = self._light_context if light else self._night_context if night else self._context
            painter.drawPixmap(QRectF(self.rect()).adjusted(-10 + dx, -10 + dy, 10 + dx, 10 + dy),
                               context, QRectF(context.rect()))
            painter.restore()
            tint = QColor(base)
            tint.setAlpha(28)
            painter.fillRect(self.rect(), tint)
        # Broad, overlapping graphite currents glide in different directions.
        width, height = self.width(), self.height()
        clouds = ((.18, .20, .48, "#ADB2BA", 88, 0.0),
                  (.82, .45, .42, "#080A0D", 135, 2.1),
                  (.48, .87, .55, "#868D98", 78, 4.2))
        if night:
            clouds = ((.18, .20, .48, "#93A0B1", 88, 0.0),
                      (.82, .45, .42, "#0B1018", 135, 2.1),
                      (.48, .87, .55, "#708094", 78, 4.2))
        if light:
            # Silver shadows and broad pearl highlights give the light veil
            # depth without turning it into a white sheet or a dark panel.
            clouds = ((.12, .15, .55, "#FFFFFF", 175, 0.0),
                      (.80, .34, .46, "#737F90", 110, 2.1),
                      (.38, .89, .58, "#AAB9CA", 85, 4.2),
                      (.92, .90, .36, "#FFFFFF", 170, 1.1))
        for x, y, radius, tone, opacity, offset in clouds:
            cx = width * (x + .23 * math.sin(phase + offset))
            cy = height * (y + .17 * math.cos(phase + offset))
            opacity = round(opacity * (.85 + .15 * math.sin(phase + offset)))
            colour = QColor(tone)
            colour.setAlpha(opacity)
            clear = QColor(colour)
            clear.setAlpha(0)
            gradient = QRadialGradient(cx, cy, max(width, height) * radius)
            gradient.setColorAt(0, colour)
            gradient.setColorAt(.45, QColor(colour.red(), colour.green(), colour.blue(), opacity // 2))
            gradient.setColorAt(1, clear)
            painter.fillRect(self.rect(), gradient)
        if light:
            # A broad satin reflection passes across the moving silver layers.
            # Its continuous cosine motion has no jump at the loop boundary.
            reflection_x = width * (.5 + .65 * math.sin(phase - .8))
            sheen = QLinearGradient(reflection_x - width * .45, 0,
                                    reflection_x + width * .45, height * .4)
            sheen.setColorAt(0, QColor(255, 255, 255, 0))
            sheen.setColorAt(.5, QColor(255, 255, 255, 82))
            sheen.setColorAt(1, QColor(255, 255, 255, 0))
            painter.fillRect(self.rect(), sheen)
        # A feathered clearing behind the existing message keeps it legible
        # without introducing another rectangular panel.
        veil = QRadialGradient(self._message.geometry().center().toPointF(), 340 if light else 260)
        colour = QColor("#F0F2F5") if light else QColor(base)
        colour.setAlpha(185 if light else 235)
        veil.setColorAt(0, colour)
        colour.setAlpha(125 if light else 200)
        veil.setColorAt(.45, colour)
        colour.setAlpha(0)
        veil.setColorAt(1, colour)
        painter.fillRect(self.rect(), veil)


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
        self._expiry_signature = None
        self._privacy_hidden = False
        self._privacy_deadline = None
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
        self.card.root.setSpacing(10)
        self.privacy_lock_button = self.card.add_header_button("Lock view", self._conceal_information, width=120)
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
        self.device_heading.setToolTip(tr("Choose an expiry for the selected browser. It takes effect immediately and does not change hardware permissions."))
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
        self.device_group = QVBoxLayout()
        self.device_group.setSpacing(2)
        body.addLayout(self.device_group)
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
        self.device_control_button = self._button("Allow hardware control", self._toggle_selected_device)
        self.device_disconnect_button = self._button("Disconnect", self._disconnect_selected_device)
        self.revoke_all_button = self._button("Disconnect all devices", self._revoke_all)
        actions.addWidget(self.device_control_button)
        actions.addWidget(self.device_disconnect_button)
        self.expiry_label = self._label("Expires in")
        actions.addWidget(self.expiry_label)
        self.device_expiry_choice = GuardedComboBox()
        self.device_expiry_choice.setObjectName("deviceExpiryChoice")
        self.device_expiry_choice.setMinimumWidth(150)
        self.device_expiry_choice.setAccessibleName(tr("Session expiry"))
        for label, seconds in (("Choose duration", None), ("15 minutes", 900), ("30 minutes", 1800),
                               ("1 hour", 3600), ("8 hours", 28800), ("24 hours", 86400),
                               ("7 days", 604800), ("30 days", 2592000), ("Custom", -1)):
            self.device_expiry_choice.addItem(tr(label), seconds)
        self.device_expiry_choice.currentIndexChanged.connect(self._update_expiry_form)
        actions.addWidget(self.device_expiry_choice)
        self.device_expiry_minutes = QSpinBox()
        self.device_expiry_minutes.setRange(1, 365 * 24 * 60)
        self.device_expiry_minutes.setValue(60)
        self.device_expiry_minutes.setSuffix(" min")
        self.device_expiry_minutes.setAccessibleName(tr("Custom session duration in minutes"))
        actions.addWidget(self.device_expiry_minutes)
        self.device_expiry_apply = self._button("Apply expiry", self._apply_selected_expiry)
        self.device_expiry_apply.setToolTip(tr("The selected duration starts now and replaces the inactivity limit for this session."))
        actions.addWidget(self.device_expiry_apply)
        actions.addStretch(1)
        actions.addWidget(self.revoke_all_button)
        self.device_group.addLayout(actions)

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
        self._privacy_cover = _RemotePrivacyCover(self.card)
        self._privacy_cover.reveal_button.clicked.connect(self._reveal_information)
        self._privacy_cover.hide()
        self._privacy_widgets = []
        self.card.installEventFilter(self)
        self._scroll.viewport().installEventFilter(self)
        self._scroll.verticalScrollBar().valueChanged.connect(self._position_privacy_cover)
        self._privacy_timer = QTimer(self)
        self._privacy_timer.setSingleShot(True)
        self._privacy_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._privacy_timer.timeout.connect(self._check_privacy)
        QGuiApplication.instance().applicationStateChanged.connect(self._application_state_changed)
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
        self._privacy_cover.apply_appearance()
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
        arrow = (Path(__file__).resolve().parents[1] / "theme" / "icons" / "chevron_down_gray.svg").as_posix()
        self.device_expiry_choice.setStyleSheet(scale_stylesheet(
            f"QComboBox#deviceExpiryChoice {{ background: transparent; color: {c['text']}; border: 1px solid {c['border']};"
            " border-radius: 8px; min-height: 0px; padding: 0px 32px 0px 12px; font-size: 11px; font-weight: 650; }"
            f"QComboBox#deviceExpiryChoice:hover {{ background: {c['control_hover']}; border-color: {c['border_strong']}; }}"
            f"QComboBox#deviceExpiryChoice:focus {{ border-color: {c['blue']}; }}"
            f"QComboBox#deviceExpiryChoice:disabled {{ color: {c['disabled_text']}; border-color: {c['border_soft']}; }}"
            "QComboBox#deviceExpiryChoice::drop-down { subcontrol-origin: padding; subcontrol-position: center right; width: 28px; border: none; }"
            f'QComboBox#deviceExpiryChoice::down-arrow {{ image: url("{arrow}"); width: 12px; height: 12px; }}'
            f"QComboBox#deviceExpiryChoice QAbstractItemView {{ background: {c['panel']}; color: {c['text']};"
            f" border: 1px solid {c['border']}; selection-background-color: {c['blue_soft']}; selection-color: {c['text']};"
            " padding: 4px; outline: 0px; font-size: 11px; }"
            "QComboBox#deviceExpiryChoice QAbstractItemView::item { min-height: 28px; padding: 4px 10px; }"))
        self.device_disconnect_button.ensurePolished()
        control_height = self.device_disconnect_button.sizeHint().height()
        self.device_expiry_choice.setFixedHeight(control_height)
        self.device_expiry_minutes.setFixedHeight(control_height)
        for box in self._code_boxes:
            box.setStyleSheet(scale_stylesheet(
                f"background: {COLORS['panel_alt']}; color: {COLORS['text']}; border: 1px solid {COLORS['border_soft']};"
                "border-radius: 8px; padding: 9px 12px; font-family: monospace; font-size: 12px;"))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.pairing_layout.setDirection(QBoxLayout.Direction.TopToBottom if self.width() < 740 else QBoxLayout.Direction.LeftToRight)
        self.device_actions_layout.setDirection(QBoxLayout.Direction.TopToBottom if self.width() < 1000 else QBoxLayout.Direction.LeftToRight)

    def hideEvent(self, event):
        self._view_settings.sync()
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if self._privacy_deadline is None:
            self._conceal_information()
        else:
            self._check_privacy()

    def _start_privacy_window(self):
        self._privacy_deadline = _privacy_time() + PRIVACY_SECONDS
        self._privacy_timer.start(PRIVACY_SECONDS * 1000)

    def _check_privacy(self):
        if self._privacy_hidden or self._privacy_deadline is None:
            return
        remaining = self._privacy_deadline - _privacy_time()
        if remaining > 0:
            self._privacy_timer.start(max(1, int(remaining * 1000) + 1))
            return
        self._conceal_information()

    def _conceal_information(self):
        if self._privacy_hidden:
            return
        self._privacy_hidden = True
        self._privacy_timer.stop()
        self.timer.stop()
        self.web_address.hidePopup()
        self.device_expiry_choice.hidePopup()
        QToolTip.hideText()
        self._privacy_widgets = []
        self._privacy_card_heights = (self.card.minimumHeight(), self.card.maximumHeight())
        self.card.setFixedHeight(self.card.height())
        self._privacy_cover.set_context(self._sanitized_privacy_context())
        for widget in self.card.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
            if widget is self._privacy_cover:
                continue
            policy = widget.sizePolicy()
            self._privacy_widgets.append((widget, widget.isHidden(), policy))
            retained = widget.sizePolicy()
            retained.setRetainSizeWhenHidden(True)
            widget.setSizePolicy(retained)
            widget.hide()
        self._position_privacy_cover()
        self._privacy_cover.show()
        self._privacy_cover.raise_()
        if self.isVisible():
            self._privacy_cover.reveal_button.setFocus(Qt.FocusReason.OtherFocusReason)

    def _reveal_information(self):
        if not self._privacy_hidden:
            return
        self._privacy_hidden = False
        for widget, hidden, policy in self._privacy_widgets:
            widget.setSizePolicy(policy)
            widget.setVisible(not hidden)
        self._privacy_widgets = []
        self.card.setMinimumHeight(self._privacy_card_heights[0])
        self.card.setMaximumHeight(self._privacy_card_heights[1])
        self._render_web()
        self._privacy_cover.hide()
        self._privacy_cover.set_context(QPixmap())
        self._start_privacy_window()
        if self._updates_active:
            self.timer.start()
            self.refresh()

    def _sanitized_privacy_context(self):
        if not self.card.isVisible():
            return QPixmap()
        labels = [(label, label.text()) for label in (self.web_pin_box, self.network_label)]
        address_hidden = self.web_address.isHidden()
        address_policy = self.web_address.sizePolicy()
        qr = self.web_qr_image.pixmap()
        qr_text = self.web_qr_image.text()
        cells = [(self.device_table.item(row, column), self.device_table.item(row, column).text())
                 for row in range(self.device_table.rowCount()) for column in range(self.device_table.columnCount())
                 if self.device_table.item(row, column) is not None]
        signals_blocked = self.device_table.blockSignals(True)
        try:
            for label, _text in labels:
                label.setText("•••• ••••")
            policy = self.web_address.sizePolicy()
            policy.setRetainSizeWhenHidden(True)
            self.web_address.setSizePolicy(policy)
            self.web_address.hide()
            placeholder = QPixmap(self.web_qr_image.size())
            placeholder.fill(QColor(COLORS["panel"]))
            painter = QPainter(placeholder)
            colour = QColor(COLORS["text"])
            colour.setAlpha(100)
            # Decorative blocks suggest the QR's position, never its contents.
            cell = min(placeholder.width(), placeholder.height()) // 8
            for row in range(6):
                for column in range(6):
                    if (row * 7 + column * 11 + row * column) % 5 < 3:
                        painter.fillRect((column + 1) * cell, (row + 1) * cell, cell, cell, colour)
            painter.end()
            self.web_qr_image.setPixmap(placeholder)
            for item, _text in cells:
                item.setText("••••")
            return self.card.grab()
        finally:
            for label, text in labels:
                label.setText(text)
            self.web_address.setSizePolicy(address_policy)
            self.web_address.setVisible(not address_hidden)
            if qr is not None and not qr.isNull():
                self.web_qr_image.setPixmap(qr)
            else:
                self.web_qr_image.setText(qr_text)
            for item, text in cells:
                item.setText(text)
            self.device_table.blockSignals(signals_blocked)

    def _position_privacy_cover(self):
        if not self._privacy_hidden:
            return
        self._privacy_cover.setGeometry(self.card.rect().adjusted(1, 1, -1, -1))
        viewport = self._scroll.viewport()
        visible = self.card.rect().intersected(QRect(self.card.mapFrom(viewport, QPoint(0, 0)), viewport.size()))
        self._privacy_cover.set_visible_region(visible.translated(-1, -1))

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Move) and self._privacy_hidden:
            QTimer.singleShot(0, self._position_privacy_cover)
        return super().eventFilter(watched, event)

    def _application_state_changed(self, state):
        if state == Qt.ApplicationState.ApplicationActive:
            self._check_privacy()

    def set_updates_active(self, active):
        self._updates_active = bool(active)
        self._check_privacy()
        if active and not self._privacy_hidden:
            self.timer.start()
            self.refresh()
        else:
            self.timer.stop()

    def refresh(self):
        self._check_privacy()
        if self._privacy_hidden:
            return
        self._background.start("web_status", web_access.status, on_success=self._apply_web,
                               on_error=lambda message: self.web_state_label.setText(tr(message)))

    def retranslate_dynamic_copy(self):
        self.privacy_lock_button.setText(tr("Lock view"))
        self._privacy_cover.retranslate()
        self._render_web()

    def _apply_web(self, state):
        self._web_state = dict(state or {})
        self._render_web()

    def _render_web(self):
        if self._privacy_hidden:
            return
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
            expiry = web_access.deadline(device)
            expiry_text, expiry_full = timestamp(expiry)
            if expiry:
                expiry_date = datetime.fromtimestamp(expiry).astimezone()
                today = datetime.fromtimestamp(now).astimezone()
                if expiry_date.date() != today.date():
                    expiry_text = expiry_date.strftime("%d/%m/%Y %H:%M" if expiry_date.year != today.year else "%d/%m %H:%M")
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
        signature = (device["id"], device.get("duration_seconds")) if device else None
        if signature != self._expiry_signature:
            self._expiry_signature = signature
            seconds = device.get("duration_seconds") if device else None
            self.device_expiry_choice.blockSignals(True)
            index = self.device_expiry_choice.findData(seconds)
            if seconds is not None and index < 0:
                index = self.device_expiry_choice.findData(-1)
                self.device_expiry_minutes.setValue(max(1, int(seconds) // 60))
            self.device_expiry_choice.setCurrentIndex(max(0, index))
            self.device_expiry_choice.blockSignals(False)
        self.device_expiry_choice.setEnabled(device is not None)
        self.device_expiry_minutes.setEnabled(device is not None)
        self._update_expiry_form()

    def _update_expiry_form(self):
        value = self.device_expiry_choice.currentData()
        self.device_expiry_minutes.setVisible(value == -1)
        self.device_expiry_apply.setEnabled(self._selected_device() is not None and value is not None)

    def _apply_selected_expiry(self):
        device = self._selected_device()
        value = self.device_expiry_choice.currentData()
        if device is None or value is None:
            return
        seconds = self.device_expiry_minutes.value() * 60 if value == -1 else int(value)
        self._run("device_expiry", lambda: web_access.set_lifetime(device["id"], seconds))

    def _toggle_selected_device(self):
        device = self._selected_device()
        if device:
            self._device_control(device["id"], not bool(device.get("control")))

    def _disconnect_selected_device(self):
        device = self._selected_device()
        if device:
            self._run("revoke", lambda: web_access.revoke(device["id"]))

    def _run(self, name, work):
        self._check_privacy()
        if self._privacy_hidden:
            return
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
        self._check_privacy()
        if self._privacy_hidden:
            return
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
        self._check_privacy()
        if self._privacy_hidden:
            return
        if text:
            QGuiApplication.clipboard().setText(text)
            show_toast(self, tr("Copied"), tr("Remote access"), tone="green")

    def _save_certificate(self):
        self._check_privacy()
        if self._privacy_hidden:
            return
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
