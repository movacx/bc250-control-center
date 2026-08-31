from __future__ import annotations

import time

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QGridLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..components.async_tools import AsyncRefresh
from ..components.dashboard_widgets import (
    DashboardFooter,
    DashboardGpuHero,
    DashboardModuleCard,
    DashboardScrollArea,
    PreparationSidebar,
)
from ..components.responsive import (
    clear_grid,
    configure_responsive_scroll_area,
)
from ..components.widgets import InfoDialog
from ..core.external_links import open_external_url
from ..core.state import DashboardState, state_cache_for
from ..i18n import tr, tr_format

CONTACT_URL = "https://discord.com/channels/1315924807128449065/1526169299490836510"
SUPPORT_URL = "https://ko-fi.com/movacx"


class DashboardPage(QWidget):
    """GPU-first system overview with one real preparation surface."""

    module_requested = pyqtSignal(str)
    action_requested = pyqtSignal(str)
    dependency_action_requested = pyqtSignal(object)
    driver_support_requested = pyqtSignal(str)

    def __init__(self, controller, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller = controller
        self.state = DashboardState()
        self._updates_active = False
        self._state_cache = state_cache_for(controller)
        self._body_mode = ""
        self._module_columns = 0
        self._live_sample = None
        self._live_sample_at = 0.0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll = DashboardScrollArea()
        self.content = QWidget()
        configure_responsive_scroll_area(self.scroll, self.content)
        self.content.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self.layout = QVBoxLayout(self.content)
        # Match the shared page inset used by CPU/SMU and the other workspaces,
        # so every dashboard frame starts on the same visual grid after the
        # application sidebar.
        self.layout.setContentsMargins(18, 8, 18, 24)
        self.layout.setSpacing(12)
        self.scroll.setWidget(self.content)
        outer.addWidget(self.scroll, 1)

        self.body_host = QWidget()
        self.body_grid = QGridLayout(self.body_host)
        self.body_grid.setContentsMargins(0, 0, 0, 0)
        self.body_grid.setHorizontalSpacing(12)
        self.body_grid.setVerticalSpacing(12)
        self.layout.addWidget(self.body_host)

        self.main_host = QWidget()
        self.main_host.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        self.main_layout = QVBoxLayout(self.main_host)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(12)

        self.gpu_card = DashboardGpuHero()
        self.gpu_card.activated.connect(self.module_requested)
        self.main_layout.addWidget(self.gpu_card)

        self.modules_host = QWidget()
        self.modules_grid = QGridLayout(self.modules_host)
        self.modules_grid.setContentsMargins(0, 0, 0, 0)
        self.modules_grid.setHorizontalSpacing(12)
        self.modules_grid.setVerticalSpacing(12)
        self.main_layout.addWidget(self.modules_host)

        self.cpu_card = DashboardModuleCard(
            "cpu",
            "CPU / SMU",
            "",
            "cpu_blue",
            "blue",
            "GHz",
            ("Voltage sensor", "Core temperature", "CPU usage"),
            "Configure CPU",
            secondary_action=("cpu_overview", "Unlock cores"),
        )
        self.cu_card = DashboardModuleCard(
            "cu",
            "Compute Units",
            "",
            "compute_orange",
            "orange",
            "/ 40",
            ("Boot sync", "UMR"),
            "Configure CUs",
        )
        self.fan_card = DashboardModuleCard(
            "fans",
            "Fans",
            "",
            "fan_cyan",
            "cyan",
            "RPM",
            ("Controller", "PWM mode", "PWM duty"),
            "Fan Control",
            secondary_action=("fans_curve", "Automatic curve"),
        )
        self.module_cards = (self.cpu_card, self.cu_card, self.fan_card)
        self.cpu_card.status.hide()
        self.cu_card.status.hide()
        for card in self.module_cards:
            card.activated.connect(self._open_module)
            card.action_requested.connect(self.action_requested)

        self.readiness = PreparationSidebar()
        self.readiness.prepare_requested.connect(self.dependency_action_requested)
        self.readiness.dependency_action_requested.connect(
            self.dependency_action_requested
        )
        self.readiness.driver_support_requested.connect(self.driver_support_requested)

        self.footer = DashboardFooter(self)
        self.footer.repositories_clicked.connect(
            lambda: self.action_requested.emit("repositories")
        )
        self.footer.contact_clicked.connect(self._open_contact)
        self.footer.support_clicked.connect(self._open_support)
        self.readiness.set_header_actions(self.footer)
        self.contact_button = self.footer.contact_button
        self.support_button = self.footer.support_button
        self.layout.addStretch(1)
        self.scroll.viewport_width_changed.connect(self._reflow)

        self._reflow(1400)
        self.apply_state(self.state)

        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.refresh)
        self._refresher = AsyncRefresh(
            self,
            "dashboard-refresh",
            lambda: DashboardState.from_controller(
                self.controller, self._state_cache
            ),
            self.apply_state,
            self._refresh_failed,
        )
        self.live_timer = QTimer(self)
        self.live_timer.setInterval(1000)
        self._live_refresher = AsyncRefresh(
            self,
            "dashboard-live-sensors",
            lambda: (time.monotonic(), self._state_cache.realtime_metrics()),
            self._apply_live_sample,
            self._live_failed,
        )
        self.live_timer.timeout.connect(self._live_refresher.request)

    def _open_module(self, key: str) -> None:
        action = {"cpu": "cpu_configuration", "fans": "fans_manual"}.get(key)
        if action:
            self.action_requested.emit(action)
        else:
            self.module_requested.emit(key)

    def set_updates_active(self, active: bool) -> None:
        self._updates_active = bool(active)
        if self._updates_active:
            if not self.timer.isActive():
                self.timer.start()
            self._refresher.activate(fresh_for=2.5)
            if callable(getattr(self.controller, "metricas_tiempo_real", None)):
                self.live_timer.start()
                self._live_refresher.activate(fresh_for=0.75)
        else:
            self._refresher.set_active(False)
            self.timer.stop()
            self._live_refresher.set_active(False)
            self.live_timer.stop()

    def retranslate_dynamic_copy(self) -> None:
        self.readiness.retranslate_dynamic_copy()

    def _apply_live_sample(self, sample) -> None:
        sampled_at, metrics = sample
        if time.monotonic() - sampled_at > 3.0:
            metrics = {}
        self._live_sample_at = sampled_at
        self._live_sample = metrics
        self.state = self.state.with_live_metrics(metrics)
        self._apply_gpu_card(self.state)
        self._apply_cpu_card(self.state)

    def _live_failed(self, message: str) -> None:
        self._apply_live_sample((time.monotonic(), {}))
        self._refresh_failed(message)

    def refresh(self) -> None:
        if self._updates_active:
            self._refresher.request()

    def _refresh_failed(self, message: str) -> None:
        self.setToolTip(message)

    def _open_contact(self) -> None:
        opened, message = open_external_url(CONTACT_URL)
        if opened:
            return
        InfoDialog(
            "Contact link could not be opened",
            message,
            icon_name="warning_orange",
            parent=self,
            eyebrow="CONTACT",
            notice=tr_format("Copy this address manually: {url}", url=CONTACT_URL),
            tone="orange",
        ).exec()

    def _open_support(self) -> None:
        opened, message = open_external_url(SUPPORT_URL)
        if opened:
            return
        InfoDialog(
            "Support page could not be opened",
            message,
            icon_name="warning_orange",
            parent=self,
            eyebrow="SUPPORT",
            notice=tr_format("Copy this address manually: {url}", url=SUPPORT_URL),
            tone="orange",
        ).exec()

    def apply_state(self, state: DashboardState) -> None:
        if self._live_sample is not None:
            metrics = self._live_sample if time.monotonic() - self._live_sample_at <= 3.0 else {}
            state = state.with_live_metrics(metrics)
        self.state = state
        self._apply_gpu_card(state)
        self._apply_cpu_card(state)
        self._apply_cu_card(state)
        self._apply_fan_card(state)
        self.readiness.set_state(state)

    def _apply_gpu_card(self, state: DashboardState) -> None:
        if state.gpu_state_available:
            status = "running" if state.governor_running else "stopped"
            tone = "green" if state.governor_running else "orange"
        else:
            status, tone = "Not detected", "gray"
        self.gpu_card.status.setText(status)
        self.gpu_card.status.set_tone(tone)

        temperature = self._format_temperature(
            state.gpu_temperature_c, decimals=0
        )
        utilization = (
            self._format_percent(state.gpu_utilization_percent)
            if state.gpu_state_available or state.performance_available
            else "Not detected"
        )
        target_range = self._format_range(
            state.governor_min_mhz, state.governor_max_mhz
        )
        self.gpu_card.frequency_value.setText(
            str(state.governor_frequency_mhz)
            if state.governor_frequency_mhz > 0
            else "--"
        )
        self.gpu_card.governor_metric.set_value(
            state.governor_backend or status
        )
        self.gpu_card.governor_metric.set_detail(status if state.governor_backend else "")
        self.gpu_card.load_metric.set_value(utilization)
        self.gpu_card.gpu_voltage_metric.set_value(
            self._format_voltage(state.gpu_voltage_mv)
        )
        self.gpu_card.thermal_strip.set_temperatures(
            (
                temperature,
                self._format_temperature(state.cpu_temperature_c),
                self._format_temperature(state.nvme_temperature_c),
                self._format_temperature(state.board_temperature_c),
                self._format_temperature(state.vrm_temperature_c),
            )
        )
        self.gpu_card.technical_strip.set_values(
            (
                self._format_power(state.gpu_power_w),
                self._format_mhz(state.gpu_memory_frequency_mhz),
                self._format_temperature(state.nvme_hotspot_temperature_c),
                state.gtt_summary,
                state.dpm_summary,
            )
        )
        self.gpu_card.technical_strip.values[4].setToolTip(
            f"Power state: {state.gpu_dpm_state}"
            if state.gpu_dpm_state
            else ""
        )
        self.gpu_card.range_row.set_value(target_range)
        self.gpu_card.accepted_row.set_value(
            self._format_mhz(state.governor_max_mhz)
        )
        self.gpu_card.gpu_summary.set_value(state.gpu_summary)
        self.gpu_card.vram_summary.set_value(state.vram_summary)
        cores_known = 0 < state.cpu_physical_cores <= state.cpu_logical_cores
        self.gpu_card.cores_summary.set_value(
            tr_format("{cores} cores / {threads} threads", cores=state.cpu_physical_cores, threads=state.cpu_logical_cores)
            if cores_known else tr("Not detected")
        )
        self.gpu_card.cores_summary.set_detail("Detected by the OS" if cores_known else "")
        # Every BC-250 has eight physical core positions.  A stock firmware
        # exposes six to Linux; retain all eight slots so the two hidden cores
        # are visible instead of silently disappearing from the dashboard.
        self.gpu_card.cores_summary.set_core_count(8)
        self.gpu_card.cores_summary.set_core_metrics(
            self.state.cpu_per_core_frequency_mhz,
            self.state.cpu_per_core_percent,
        )

    def _apply_cpu_card(self, state: DashboardState) -> None:
        self.cpu_card.status.setText(state.cpu_profile)
        self.cpu_card.status.set_tone(
            "green" if state.performance_available else "gray"
        )
        if state.cpu_frequency_mhz > 0:
            self.cpu_card.set_headline(f"{state.cpu_frequency_mhz / 1000:.2f}")
        else:
            self.cpu_card.set_headline("--")
        self.cpu_card.set_metric(0, self._format_voltage(state.cpu_voltage_mv))
        self.cpu_card.set_metric(
            1, self._format_temperature(state.cpu_temperature_c)
        )
        self.cpu_card.set_metric(
            2, self._format_percent(state.cpu_utilization_percent)
        )

    def _apply_cu_card(self, state: DashboardState) -> None:
        self.cu_card.status.setText(state.cu_mode)
        if not state.cu_state_available:
            tone = "gray"
        elif state.active_cus >= 40:
            tone = "green"
        else:
            tone = "orange"
        self.cu_card.status.set_tone(tone)
        self.cu_card.set_headline(
            str(state.active_cus) if state.cu_state_available else "--",
            f"/ {state.total_cus}",
        )
        self.cu_card.set_metric(0, state.cu_boot_sync)
        self.cu_card.set_metric(
            1,
            "loaded"
            if state.umr_ready
            else "missing"
            if state.tools_state_available
            else "Not detected",
        )

    def _apply_fan_card(self, state: DashboardState) -> None:
        status = (
            "PWM ready"
            if state.pwm_ready
            else "read only"
            if state.fan_state_available
            else "Not detected"
        )
        self.fan_card.status.setText(status)
        self.fan_card.status.set_tone(
            "green"
            if state.pwm_ready
            else "orange"
            if state.fan_state_available
            else "gray"
        )
        self.fan_card.set_headline(
            str(state.pump_fan_rpm) if state.pump_fan_rpm > 0 else "--"
        )
        self.fan_card.set_metric(
            0, state.fan_controller_label or "Not detected"
        )
        self.fan_card.set_metric(1, state.fan_mode)
        self.fan_card.set_metric(
            2,
            self._format_percent(state.pump_fan_duty_percent)
            if state.fan_state_available
            else "Not detected",
        )

    @staticmethod
    def _format_ghz(value_mhz: int) -> str:
        return f"{value_mhz / 1000:.2f} GHz" if value_mhz > 0 else "Not detected"

    @staticmethod
    def _format_mhz(value_mhz: int) -> str:
        return f"{value_mhz} MHz" if value_mhz > 0 else "Not detected"

    @staticmethod
    def _format_voltage(value_mv: int) -> str:
        return f"{value_mv / 1000:.3f} V" if value_mv > 0 else "Not detected"

    @staticmethod
    def _format_temperature(value_c: float, *, decimals: int = 1) -> str:
        return f"{value_c:.{decimals}f} °C" if value_c > 0 else "Not detected"

    @staticmethod
    def _format_power(value_w: float) -> str:
        return f"{value_w:.0f} W" if value_w > 0 else "Not detected"

    @staticmethod
    def _format_percent(value: int) -> str:
        return f"{value} %" if value >= 0 else "Not detected"

    @staticmethod
    def _format_range(minimum_mhz: int, maximum_mhz: int) -> str:
        if minimum_mhz <= 0 or maximum_mhz <= 0:
            return "Not detected"
        return f"{minimum_mhz} – {maximum_mhz} MHz"

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self._reflow(self.scroll.viewport().width())

    def _reflow(self, width: int) -> None:
        body_mode = "vertical"
        module_columns = 3 if width >= 900 else 1

        if body_mode != self._body_mode or self.body_grid.count() == 0:
            self._body_mode = body_mode
            clear_grid(self.body_grid)
            self.readiness.setMinimumWidth(0)
            self.readiness.setMaximumWidth(16_777_215)
            self.readiness.setMinimumHeight(0)
            self.readiness.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            self.body_grid.addWidget(self.main_host, 0, 0)
            self.body_grid.addWidget(self.readiness, 1, 0)
            self.body_grid.setColumnStretch(0, 1)

        if module_columns != self._module_columns or self.modules_grid.count() == 0:
            self._module_columns = module_columns
            clear_grid(self.modules_grid)
            for index, card in enumerate(self.module_cards):
                self.modules_grid.addWidget(
                    card, index // module_columns, index % module_columns
                )
            for column in range(3):
                self.modules_grid.setColumnStretch(
                    column, 1 if column < module_columns else 0
                )
            for row in range((len(self.module_cards) + module_columns - 1) // module_columns):
                self.modules_grid.setRowStretch(row, 1)
