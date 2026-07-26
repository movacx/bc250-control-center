from __future__ import annotations

from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QGridLayout, QScrollArea, QVBoxLayout, QWidget

from ..components.async_tools import AsyncRefresh
from ..components.page_widgets import ControlPageHeader
from ..components.responsive import clear_grid, configure_responsive_scroll_area, effective_viewport_width
from ..core.state import DashboardState, state_cache_for
from ..i18n import tr
from ..theme import COLORS
from ..components.widgets import ActivityCard, ModuleCard, QuickActionsCard, ReadinessCard, SystemSummaryBar


class DashboardPage(QWidget):
    module_requested = pyqtSignal(str)
    action_requested = pyqtSignal(str)

    def __init__(self, controller, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller = controller
        self.state = DashboardState()
        self._updates_active = False
        self._state_cache = state_cache_for(controller)
        self._top_columns = 4
        self._bottom_mode = "wide"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        self.scroll = scroll
        self.content = QWidget()
        configure_responsive_scroll_area(scroll, self.content)
        self.layout = QVBoxLayout(self.content)
        self.layout.setContentsMargins(18, 8, 18, 24)
        self.layout.setSpacing(16)
        scroll.setWidget(self.content)
        outer.addWidget(scroll)

        self.header = ControlPageHeader(
            "BC250 SYSTEM CONTROL",
            "Dashboard",
            "Monitor hardware health, services, and active tuning state.",
            mode_text="● LIVE TELEMETRY",
        )
        self.header.refresh_requested.connect(self.refresh)
        self.layout.addWidget(self.header)

        self.summary_bar = SystemSummaryBar()
        self.layout.addWidget(self.summary_bar)

        self.top_host = QWidget()
        self.top_grid = QGridLayout(self.top_host)
        self.top_grid.setContentsMargins(0, 0, 0, 0)
        self.top_grid.setHorizontalSpacing(15)
        self.top_grid.setVerticalSpacing(15)
        self.layout.addWidget(self.top_host)

        self.cpu_card = ModuleCard(
            "cpu", "CPU / SMU", "cpu_blue", COLORS["blue_soft"], "Not detected", "gray",
            [("Frequency (avg)", "--"), ("Voltage sensor", "--"), ("Core temperature", "--"), ("CPU usage", "--")],
            "Tune CPU / SMU",
        )
        self.gpu_card = ModuleCard(
            "gpu", "GPU Governor", "gpu_purple", COLORS["purple_soft"], "Not detected", "gray",
            [("Current frequency", "--"), ("Target range", "--"), ("Temperature", "--"), ("Utilization", "--")],
            "Configure Governor",
        )
        self.cu_card = ModuleCard(
            "cu", "Compute Units", "compute_orange", COLORS["orange_soft"], "Not verified", "gray",
            [("Active CUs", "--"), ("Mode", "Not verified"), ("Boot sync", "Not detected"), ("UMR", "Not detected")],
            "Configure CUs",
        )
        self.cu_card.set_progress(0, COLORS["orange"])
        self.fan_card = ModuleCard(
            "fans", "Fans", "fan_cyan", COLORS["cyan_soft"], "Not detected", "gray",
            [("Controller", "Not detected"), ("PWM mode", "Not detected"), ("Pump fan", "--"), ("PWM duty", "--")],
            "Fan Control",
        )
        self.module_cards = [self.cpu_card, self.gpu_card, self.cu_card, self.fan_card]
        for card in self.module_cards:
            card.activated.connect(self.module_requested)

        self.bottom_host = QWidget()
        self.bottom_grid = QGridLayout(self.bottom_host)
        self.bottom_grid.setContentsMargins(0, 0, 0, 0)
        self.bottom_grid.setHorizontalSpacing(15)
        self.bottom_grid.setVerticalSpacing(15)
        self.layout.addWidget(self.bottom_host)

        self.readiness = ReadinessCard(self._readiness_rows(self.state))
        self.readiness.prepare_clicked.connect(lambda: self.action_requested.emit("prepare_dependencies"))
        self.quick_actions = QuickActionsCard()
        self.quick_actions.action_clicked.connect(self.action_requested)
        self.activity = ActivityCard(self.state.activities)
        self.activity.view_all_clicked.connect(lambda: self.module_requested.emit("history"))
        self.bottom_cards = [self.readiness, self.quick_actions, self.activity]

        self.layout.addStretch(1)

        self._reflow(1400)
        self.apply_state(self.state)

        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.refresh)
        self._refresher = AsyncRefresh(
            self,
            "dashboard-refresh",
            lambda: DashboardState.from_controller(self.controller, self._state_cache),
            self.apply_state,
            self._refresh_failed,
        )

    def _readiness_rows(self, state: DashboardState):
        return [
            ("GPU Governor service", state.governor_tool_ready),
            ("UMR (User Mode Driver)", state.umr_ready),
            ("NCT fan/PWM module", state.nct_ready),
            ("Sensors (amdgpu / NCT)", state.sensors_ready),
        ]

    def set_updates_active(self, active: bool) -> None:
        self._updates_active = bool(active)
        if self._updates_active:
            if not self.timer.isActive():
                self.timer.start()
            self._refresher.activate(fresh_for=2.5)
        else:
            self._refresher.set_active(False)
            self.timer.stop()

    def refresh(self) -> None:
        if self._updates_active:
            self._refresher.request()

    def _refresh_failed(self, message: str) -> None:
        self.header.setToolTip(message)

    def apply_state(self, state: DashboardState) -> None:
        self.state = state
        self.cpu_card.status.setText(state.cpu_profile)
        self.cpu_card.status.set_tone("green" if state.performance_available else "gray")
        self.cpu_card.set_metric(0, self._format_ghz(state.cpu_frequency_mhz))
        self.cpu_card.set_metric(1, self._format_voltage(state.cpu_voltage_mv))
        self.cpu_card.set_metric(2, self._format_temperature(state.cpu_temperature_c))
        self.cpu_card.set_metric_label(3, "CPU usage")
        self.cpu_card.set_metric(3, self._format_percent(state.cpu_utilization_percent))
        self.cpu_card.metric_cells[3].setToolTip(tr("Current total CPU utilization."))

        if state.gpu_state_available:
            self.gpu_card.status.setText("running" if state.governor_running else "stopped")
            self.gpu_card.status.set_tone("green" if state.governor_running else "orange")
        else:
            self.gpu_card.status.setText("Not detected")
            self.gpu_card.status.set_tone("gray")
        self.gpu_card.set_metric(0, self._format_mhz(state.governor_frequency_mhz))
        self.gpu_card.set_metric(1, self._format_range(state.governor_min_mhz, state.governor_max_mhz))
        self.gpu_card.set_metric(2, self._format_temperature(state.gpu_temperature_c, decimals=0))
        self.gpu_card.set_metric(
            3,
            self._format_percent(state.gpu_utilization_percent)
            if state.gpu_state_available or state.performance_available
            else "Not detected",
        )

        self.cu_card.status.setText(state.cu_mode)
        self.cu_card.status.set_tone("green" if state.cu_state_available and state.active_cus >= 40 else "orange" if state.cu_state_available else "gray")
        self.cu_card.set_metric(0, f"{state.active_cus} / {state.total_cus}" if state.cu_state_available else "Not verified")
        self.cu_card.set_metric(1, state.cu_mode)
        self.cu_card.set_metric(2, state.cu_boot_sync)
        self.cu_card.set_metric(3, "loaded" if state.umr_ready else "missing" if state.tools_state_available else "Not detected")
        self.cu_card.set_progress(state.cu_percent, COLORS["orange"])

        self.fan_card.status.setText("PWM ready" if state.pwm_ready else "read only" if state.fan_state_available else "Not detected")
        self.fan_card.status.set_tone("green" if state.pwm_ready else "orange" if state.fan_state_available else "gray")
        self.fan_card.set_metric(0, state.fan_controller_label or "Not detected")
        self.fan_card.set_metric(1, state.fan_mode)
        self.fan_card.set_metric(2, f"{state.pump_fan_rpm} RPM" if state.pump_fan_rpm else "Not detected")
        self.fan_card.set_metric(3, self._format_percent(state.pump_fan_duty_percent) if state.fan_state_available else "Not detected")

        self.readiness.set_rows(self._readiness_rows(state))
        self.activity.set_activities(state.activities)
        self.summary_bar.set_values(
            gpu=state.gpu_summary,
            vram=state.vram_summary,
            power=self._format_power(state.power_w),
            uptime=state.uptime_summary,
            power_label=state.power_label,
            power_tooltip=state.power_tooltip,
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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow(effective_viewport_width(self, self.scroll))

    def _reflow(self, width: int) -> None:
        top_columns = 4 if width >= 1260 else 2 if width >= 900 else 1
        bottom_mode = "wide" if width >= 1180 else "split" if width >= 720 else "stack"
        if top_columns != self._top_columns or self.top_grid.count() == 0:
            self._top_columns = top_columns
            self._clear_layout(self.top_grid)
            for index, card in enumerate(self.module_cards):
                self.top_grid.addWidget(card, index // top_columns, index % top_columns)
            for column in range(top_columns):
                self.top_grid.setColumnStretch(column, 1)
        if bottom_mode != self._bottom_mode or self.bottom_grid.count() == 0:
            self._bottom_mode = bottom_mode
            self._clear_layout(self.bottom_grid)
            self.bottom_grid.setColumnStretch(0, 0)
            self.bottom_grid.setColumnStretch(1, 0)
            self.bottom_grid.setColumnStretch(2, 0)
            if bottom_mode == "wide":
                self.bottom_grid.addWidget(self.readiness, 0, 0, 1, 1)
                self.bottom_grid.addWidget(self.quick_actions, 0, 1, 1, 1)
                self.bottom_grid.addWidget(self.activity, 0, 2, 1, 1)
                for column in range(3):
                    self.bottom_grid.setColumnStretch(column, 1)
            elif bottom_mode == "split":
                self.bottom_grid.addWidget(self.readiness, 0, 0, 1, 2)
                self.bottom_grid.addWidget(self.quick_actions, 1, 0, 1, 1)
                self.bottom_grid.addWidget(self.activity, 1, 1, 1, 1)
                self.bottom_grid.setColumnStretch(0, 1)
                self.bottom_grid.setColumnStretch(1, 1)
            else:
                self.bottom_grid.addWidget(self.readiness, 0, 0, 1, 1)
                self.bottom_grid.addWidget(self.quick_actions, 1, 0, 1, 1)
                self.bottom_grid.addWidget(self.activity, 2, 0, 1, 1)
                self.bottom_grid.setColumnStretch(0, 1)

    @staticmethod
    def _clear_layout(layout: QGridLayout) -> None:
        clear_grid(layout)
