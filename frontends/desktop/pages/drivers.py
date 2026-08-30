from __future__ import annotations

import shutil

from PyQt6.QtCore import QProcess, Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..components.async_tools import AsyncRefresh
from ..components.page_widgets import ConfirmDialog, ControlPageHeader, SectionCard
from ..components.responsive import (
    clear_grid,
    configure_responsive_scroll_area,
    effective_viewport_width,
)
from ..components.widgets import InfoDialog, PillLabel, icon
from ..core.external_links import open_external_url
from ..i18n import tr, tr_format
from ..theme import COLORS

USB_WIFI_GUIDE = (
    "https://github.com/morrownr/USB-WiFi/blob/main/home/"
    "USB_WiFi_Adapters_that_are_supported_with_Linux_in-kernel_drivers.md"
)


class DeviceRow(QFrame):
    def __init__(
        self, title: str, detail: str, status: str, tone: str = "green", parent=None
    ):
        super().__init__(parent)
        self.setProperty("compactPageCard", True)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 9, 12, 9)
        row.setSpacing(10)
        copy = QVBoxLayout()
        copy.setSpacing(2)
        self.name = QLabel(tr(title))
        self.name.source_text = title
        self.name.setProperty("cardTitle", True)
        self.name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.description = QLabel(tr(detail))
        self.description.source_text = detail
        self.description.setProperty("sectionSubtitle", True)
        self.description.setWordWrap(True)
        self.description.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        copy.addWidget(self.name)
        copy.addWidget(self.description)
        row.addLayout(copy, 1)
        self.status = PillLabel(status, tone)
        self.status.source_text = status
        row.addWidget(self.status)

    def set_data(self, title: str, detail: str, status: str, tone: str) -> None:
        self.name.source_text = title
        self.name.setText(tr(title))
        self.description.source_text = detail
        self.description.setText(tr(detail))
        self.status.source_text = status
        self.status.setText(tr(status))
        self.status.set_tone(tone)


class DriversPage(QWidget):
    """Safe device inventory and distribution-native support workflows."""

    def __init__(
        self,
        controller,
        parent: QWidget | None = None,
        *,
        embedded: bool = False,
    ):
        super().__init__(parent)
        self.controller = controller
        self._embedded = bool(embedded)
        self._updates_active = False
        self._columns = 0
        self._snapshot: dict = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.content = QWidget()
        configure_responsive_scroll_area(self.scroll, self.content)
        root = QVBoxLayout(self.content)
        root.setContentsMargins(0 if embedded else 18, 0 if embedded else 8, 0 if embedded else 18, 12 if embedded else 20)
        root.setSpacing(14)
        self.scroll.setWidget(self.content)
        outer.addWidget(self.scroll)

        self.header: ControlPageHeader | None = None
        if not embedded:
            self.header = ControlPageHeader(
                "Hardware",
                "Drivers",
                "Review active drivers and install distribution packages.",
            )
            self.header.refresh_requested.connect(self.refresh)
            root.addWidget(self.header)

        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(14)
        root.addLayout(self.grid)

        self.network_card = self._build_network_card()
        self.printing_card = self._build_printing_card()
        self.external_card = self._build_external_card()
        self._reflow(1400)

        self._refresh = AsyncRefresh(
            self,
            "driver-inventory",
            self.controller.driver_inventory,
            self._apply_snapshot,
            self._show_error,
        )
        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.setInterval(2_000)
        self.auto_refresh_timer.timeout.connect(self.refresh)

    @staticmethod
    def _clear(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def _build_network_card(self) -> SectionCard:
        card = SectionCard(
            "Network",
            "Active kernel drivers and official firmware packages.",
            icon_name="network_cyan",
            icon_background=COLORS["cyan_soft"],
        )
        self.network_rows = QVBoxLayout()
        self.network_rows.setSpacing(7)
        card.body.addLayout(self.network_rows)
        self.connectivity_button = card.add_header_button(
            "Install support",
            lambda: self._confirm_install("connectivity"),
            primary=True,
            width=176,
        )
        self.connectivity_button.setIcon(icon("check_green"))
        return card

    def _build_printing_card(self) -> SectionCard:
        card = SectionCard(
            "Printing",
            "Driverless printing with CUPS, IPP and IPP-over-USB. Existing queues are preserved.",
            icon_name="info_blue",
            icon_background=COLORS["blue_soft"],
        )
        self.printing_rows = QVBoxLayout()
        self.printing_rows.setSpacing(7)
        card.body.addLayout(self.printing_rows)
        self.printer_settings_button = card.add_header_button(
            "", self._open_printer_settings, width=42
        )
        self.printer_settings_button.setIcon(icon("settings_blue"))
        self.printer_settings_button.setToolTip(tr("Open settings"))
        self.printer_settings_button.setAccessibleName(tr("Open settings"))
        self.printer_settings_button.setMaximumWidth(42)
        self.printing_button = card.add_header_button(
            "Install support",
            lambda: self._confirm_install("printing"),
            primary=True,
            width=176,
        )
        self.printing_button.setIcon(icon("check_green"))
        return card

    def _build_external_card(self) -> SectionCard:
        card = SectionCard(
            "External drivers",
            "Device-specific kernel modules are not generic driver packs.",
            icon_name="warning_orange",
            icon_background=COLORS["orange_soft"],
            status=("Reference only", "orange"),
        )
        self.aic_status = DeviceRow(
            "AIC8800 Wi-Fi (SteamOS toolkit)",
            "SteamOS-specific; Wi-Fi only. Never installed automatically.",
            "Not detected",
            "gray",
        )
        card.body.addWidget(self.aic_status)
        note = QLabel(tr("Prefer devices supported by in-kernel Linux drivers."))
        note.setProperty("sectionSubtitle", True)
        note.setWordWrap(True)
        card.body.addWidget(note)
        guide = QPushButton(tr("View compatibility guide"))
        guide.clicked.connect(lambda: self._open_link(USB_WIFI_GUIDE))
        card.body.addWidget(guide, 0, Qt.AlignmentFlag.AlignLeft)
        return card

    def refresh(self) -> None:
        self._refresh.request()

    def set_updates_active(self, active: bool) -> None:
        self._updates_active = bool(active)
        if active:
            self._refresh.activate(fresh_for=0.0, refresh_delay_ms=0)
            self.auto_refresh_timer.start()
        else:
            self.auto_refresh_timer.stop()
            self._refresh.set_active(False)

    def _apply_snapshot(self, value: object) -> None:
        snapshot = value if isinstance(value, dict) else {}
        self._snapshot = snapshot
        family = str(snapshot.get("family", "unknown"))
        init = str(snapshot.get("init_manager", "unknown"))
        supported = set(snapshot.get("supported_components", ()))

        self._clear(self.network_rows)
        network = list(snapshot.get("network", ()))
        for item in network:
            kind = tr("Wi-Fi") if item.get("kind") == "wifi" else tr("Ethernet")
            driver = str(item.get("driver") or tr("No kernel driver"))
            detail = tr_format("{kind} · driver: {driver}", kind=kind, driver=driver)
            state = str(item.get("state") or "unknown")
            self.network_rows.addWidget(
                DeviceRow(
                    str(item.get("name", "--")),
                    detail,
                    state,
                    "green" if state == "up" else "gray",
                )
            )
        bluetooth = list(snapshot.get("bluetooth_controllers", ()))
        bt_detail = ", ".join(bluetooth) if bluetooth else tr("No controller detected")
        self.network_rows.addWidget(
            DeviceRow(
                tr("Bluetooth"),
                bt_detail,
                tr("Detected") if bluetooth else tr("Not detected"),
                "green" if bluetooth else "gray",
            )
        )
        if not network:
            self.network_rows.addWidget(
                DeviceRow(
                    tr("Network"),
                    tr("No interface detected"),
                    tr("Not detected"),
                    "gray",
                )
            )
        self.connectivity_button.setEnabled("connectivity" in supported)

        self._clear(self.printing_rows)
        printing = (
            snapshot.get("printing", {})
            if isinstance(snapshot.get("printing"), dict)
            else {}
        )
        queues = list(printing.get("queues", ()))
        printers = list(snapshot.get("usb_printers", ()))
        services = []
        if printing.get("cups_tools"):
            services.append("CUPS")
        if printing.get("ipp_usb"):
            services.append("IPP-over-USB")
        self.printing_rows.addWidget(
            DeviceRow(
                tr("Printing stack"),
                ", ".join(services) or tr("Printing packages not detected"),
                tr("Ready") if services else tr("Unavailable"),
                "green" if services else "gray",
            )
        )
        queue_detail = ", ".join(queues) if queues else tr("No configured queues")
        self.printing_rows.addWidget(
            DeviceRow(
                tr("Printer queues"),
                queue_detail,
                str(len(queues)),
                "blue" if queues else "gray",
            )
        )
        usb_detail = (
            ", ".join(str(item.get("name", "USB")) for item in printers)
            if printers
            else tr("No USB printer detected")
        )
        self.printing_rows.addWidget(
            DeviceRow(
                tr("USB printers"),
                usb_detail,
                tr("Detected") if printers else tr("Not detected"),
                "green" if printers else "gray",
            )
        )
        self.printing_button.setEnabled("printing" in supported)
        self.printer_settings_button.setEnabled(bool(printing.get("gui")))

        aic = (
            snapshot.get("aic8800", {})
            if isinstance(snapshot.get("aic8800"), dict)
            else {}
        )
        detected = bool(aic.get("loaded") or aic.get("candidate_detected"))
        self.aic_status.set_data(
            "AIC8800 Wi-Fi (SteamOS toolkit)",
            tr("Detected; automatic installation remains disabled.")
            if detected
            else tr("SteamOS-specific; Wi-Fi only. Never installed automatically."),
            tr("Detected") if detected else tr("Not detected"),
            "orange" if detected else "gray",
        )

        tooltip = tr_format(
            "Distribution: {distribution} · init: {init}",
            distribution=str(snapshot.get("distribution", family)),
            init=init,
        )
        self.connectivity_button.setToolTip(tooltip)
        self.printing_button.setToolTip(tooltip)

    def _confirm_install(self, component: str) -> None:
        supported = set(self._snapshot.get("supported_components", ()))
        if component not in supported:
            self._show_error(
                tr("No reviewed package workflow is available for this distribution.")
            )
            return
        title = "Network support" if component == "connectivity" else "Printing support"
        dialog = ConfirmDialog(
            title,
            "This opens a terminal with reviewed distribution packages. No external kernel driver is downloaded.",
            summary=(
                ("Distribution", str(self._snapshot.get("distribution", "--"))),
                ("Init system", str(self._snapshot.get("init_manager", "unknown"))),
            ),
            confirm_text="Open terminal",
            eyebrow="PACKAGE SETUP",
            parent=self,
        )
        if dialog.exec():
            try:
                self.controller.install_driver_support(component)
            except (OSError, RuntimeError, ValueError) as error:
                self._show_error(str(error))

    def _open_printer_settings(self) -> None:
        if shutil.which("systemsettings"):
            opened, _pid = QProcess.startDetached(
                "systemsettings", ["kcm_printer_manager"]
            )
        elif shutil.which("system-config-printer"):
            opened, _pid = QProcess.startDetached("system-config-printer", [])
        else:
            opened = False
        if not opened:
            self._show_error(tr("No printer settings application is installed."))

    def _open_link(self, url: str) -> None:
        opened, message = open_external_url(url)
        if not opened:
            self._show_error(message)

    def _show_error(self, message: str) -> None:
        InfoDialog(
            "Support unavailable",
            message,
            icon_name="warning_orange",
            eyebrow="Hardware",
            notice="No changes were made.",
            tone="orange",
            parent=self,
        ).open()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reflow(effective_viewport_width(self, self.scroll))

    def _reflow(self, width: int) -> None:
        columns = 2 if width >= 980 else 1
        if columns == self._columns:
            return
        self._columns = columns
        clear_grid(self.grid)
        if columns == 2:
            self.grid.addWidget(self.network_card, 0, 0)
            self.grid.addWidget(self.printing_card, 0, 1)
            self.grid.addWidget(self.external_card, 1, 0, 1, 2)
        else:
            self.grid.addWidget(self.network_card, 0, 0)
            self.grid.addWidget(self.printing_card, 1, 0)
            self.grid.addWidget(self.external_card, 2, 0)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1 if columns == 2 else 0)
        QTimer.singleShot(0, self.updateGeometry)
