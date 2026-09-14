from __future__ import annotations

import logging
import time
from typing import NamedTuple

from PyQt6.QtCore import QPoint, QRect, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QGridLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from bc250cc.infrastructure.install_source import (
    UpdateChannel,
    detect_install_source,
)
from bc250cc.infrastructure.release_check import (
    RELEASES_PAGE_URL,
    check_for_update,
)

from ..components.async_tools import AsyncRefresh, BackgroundExecutor
from ..components.dashboard_widgets import (
    DashboardFooter,
    DashboardGpuHero,
    DashboardMemorySummary,
    DashboardModuleCard,
    DashboardScrollArea,
    PreparationSidebar,
    UpdateCallout,
)
from ..components.responsive import (
    clear_grid,
    configure_responsive_scroll_area,
)
from ..components.widgets import InfoDialog
from ..core.external_links import open_external_url, update_checks_enabled
from ..core.gddr6_monitor import gddr6_monitor_for
from ..core.state import DashboardState, state_cache_for
from ..i18n import tr, tr_format

logger = logging.getLogger(__name__)


def _dict(value) -> dict:
    try:
        return dict(value or {})
    except Exception:
        return {}


def _number(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


class _UpdateLookup(NamedTuple):
    """What one background pass found: a version, and what to do about it."""

    status: object
    source: object


def _look_for_update() -> _UpdateLookup:
    """Both questions in one worker, off the interface thread.

    Asking the package manager who owns this file means running a subprocess,
    which has no business on the thread that paints. It is only asked once an
    update actually exists, so the ordinary case — nothing new — costs a cached
    string comparison and no processes at all.
    """
    status = check_for_update()
    source = detect_install_source() if status.update_available else None
    return _UpdateLookup(status=status, source=source)

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
        self.gpu_card.telemetry_repair_requested.connect(self._request_telemetry_repair)
        self.main_layout.addWidget(self.gpu_card)

        # Its own block directly under the hero's core strip, rather than
        # inside the hero: that card carries a height ratchet, and eight more
        # cells would push it past the compact size the dashboard fixes.
        self.memory_summary = DashboardMemorySummary(live_action=True)
        self.memory_monitor = gddr6_monitor_for(controller)
        self.memory_summary.live_toggled.connect(self.memory_monitor.set_live)
        self.memory_monitor.changed.connect(self._apply_memory_reading)
        self.main_layout.addWidget(self.memory_summary)

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
        self.footer.update_clicked.connect(self._badge_clicked)
        self.readiness.set_header_actions(self.footer)
        self.contact_button = self.footer.contact_button
        self.support_button = self.footer.support_button
        self.update_button = self.footer.update_button
        # The only place this application reaches the network itself, so it is
        # kept off the UI thread and never reports a failure. See
        # bc250cc.infrastructure.release_check for the rules it follows.
        self._release_executor = BackgroundExecutor(self)
        # The bubble opens on its own every time this screen is reached while
        # an update is available, and again whenever the badge is clicked -
        # it is meant to nag gently rather than be seen once and forgotten.
        self.update_callout = UpdateCallout(self)
        self.update_callout.action_clicked.connect(self._follow_update_advice)
        self.update_callout.dismissed.connect(self._callout_dismissed)
        self._install_source = None
        # Whether there is an update to announce at all. The bubble is taken
        # off screen for all sorts of reasons — another page, a scroll, a
        # panel covering the shell — and every one of them needs to know
        # whether bringing it back is still the right thing to do.
        self._update_pending = False
        # Parented to this page, so a pending retry dies with it rather than
        # firing into a destroyed widget once this page is gone.
        self._callout_retries = 0
        self._callout_retry_timer = QTimer(self)
        self._callout_retry_timer.setSingleShot(True)
        self._callout_retry_timer.timeout.connect(self._place_callout)
        # Scrolling is not the only thing that moves the badge: a refresh can
        # relayout the page under it, and the window can be resized. Neither
        # emits a scroll, so the bubble asks where the badge is rather than
        # waiting to be told.
        self._callout_anchored_at = QRect()
        self._callout_follow_timer = QTimer(self)
        self._callout_follow_timer.setInterval(250)
        self._callout_follow_timer.timeout.connect(self._follow_callout)
        self.layout.addStretch(1)
        self.scroll.viewport_width_changed.connect(self._reflow)
        # The badge scrolls with the page but the bubble is a child of the
        # window, so without this it stays where it was first drawn and ends
        # up pointing at whatever has scrolled into that spot.
        scrollbar = self.scroll.verticalScrollBar()
        if scrollbar is not None:
            scrollbar.valueChanged.connect(self._follow_callout)

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
            self._check_for_update()
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

    def _check_for_update(self) -> None:
        """Ask once per session, in the background, and stay quiet on failure.

        The published version is cached for hours by the layer below, so this
        reaches the network at most once even across several launches. A host
        with no internet, a proxy in the way or the preference switched off
        simply never shows the badge; nothing is logged at the user.
        """
        if not update_checks_enabled():
            return
        # Asked on every arrival at this screen, as intended. It is cheap:
        # the layer below keeps the published version for
        # ``release_check.CACHE_SECONDS``, so most arrivals are a local string
        # comparison and the network is touched at most once per window.
        # ``BackgroundExecutor.start`` refuses a duplicate key, so a fast
        # double navigation cannot stack two reads either.
        self._release_executor.start(
            "release-check",
            _look_for_update,
            self._apply_update_status,
            lambda _message: None,
        )

    def _apply_update_status(self, result: object) -> None:
        status = getattr(result, "status", None)
        source = getattr(result, "source", None)
        published = str(getattr(status, "published", "") or "")
        available = bool(getattr(status, "update_available", False))
        self._install_source = source
        self._update_pending = available
        self.footer.announce_update(published if available else "")
        if not available:
            self.update_callout.hide()
            return
        self._describe_update(published, source)
        self._show_callout()

    def _describe_update(self, published: str, source: object) -> None:
        """Say what to do, which depends entirely on how this copy was installed."""
        channel = getattr(source, "channel", None)
        command = str(getattr(source, "command", "") or "")
        if channel is UpdateChannel.AUR and command:
            detail = tr_format(
                "Version {version} is available. Update it with your AUR helper.",
                version=published,
            )
            action = command
        else:
            detail = tr_format("Version {version} is available", version=published)
            action = tr("Open the latest release")
        self.update_callout.set_message(version=published, detail=detail, action=action)

    def _show_callout(self) -> None:
        # Deferred: on the first arrival this page may not be inside a shown
        # window yet, and a bubble cannot be placed against a widget that has
        # no position.
        self._callout_retries = 0
        self._callout_retry_timer.start(0)

    def _place_callout(self) -> None:
        window = self.footer.update_button.window()
        if window is not None and getattr(window, "is_presenting_overlay", bool)():
            # The first-run panel, or the guided tour. Both are meant to be the
            # only thing on screen, and this bubble is a sibling that would
            # otherwise be drawn over them. Wait without spending the retries:
            # the user may well take a minute over those, and the bubble is
            # still wanted afterwards.
            self.update_callout.hide()
            self._callout_retry_timer.start(400)
            return
        if window is None or not window.isVisible():
            # A cached release check can resolve before the main window is
            # actually shown - the common case on a cold start straight into
            # the dashboard, where the answer is often already in cache. Keep
            # trying briefly instead of dropping the bubble silently; give up
            # quietly after a few seconds rather than retry forever.
            self._callout_retries += 1
            if self._callout_retries <= 40:
                self._callout_retry_timer.start(75)
            return
        if not self._update_pending or not self.isVisible():
            # This bubble belongs to this page. Reparenting it to the window is
            # what lets it hang outside the scroll area, and it is also what
            # stops it noticing that the user has gone to another module — so
            # the page says so itself.
            self.update_callout.hide()
            self._callout_follow_timer.stop()
            return
        # From here the bubble is wanted, whether or not it can be drawn this
        # instant. Watching starts now rather than after a successful
        # placement: the badge may be below the fold, or the page may not have
        # been laid out yet, and both of those resolve themselves a moment
        # later with nothing to announce them.
        self._callout_follow_timer.start()
        if not self._badge_is_on_screen():
            # Scrolled past. A bubble whose tail points off the top of the
            # viewport is worse than no bubble: it labels whatever happens to
            # be under it now.
            self.update_callout.hide()
            return
        self.update_callout.point_at(self.footer.update_button)
        self._callout_anchored_at = self._badge_rect()

    def _badge_rect(self) -> QRect:
        """Where the badge sits in the window right now."""
        badge = self.footer.update_button
        return QRect(badge.mapTo(self, QPoint(0, 0)), badge.size())

    def _badge_is_on_screen(self) -> bool:
        """Whether the update badge is actually inside the scrolled viewport."""
        badge = self.footer.update_button
        if badge.isHidden() or badge.width() <= 0:
            return False
        viewport = self.scroll.viewport()
        if viewport is None:
            return True
        top_left = badge.mapTo(viewport, QPoint(0, 0))
        return viewport.rect().intersects(QRect(top_left, badge.size()))

    def _follow_callout(self) -> None:
        """Re-decide where the bubble goes, or whether it goes at all.

        Cheap enough to run on every scroll step: it does nothing at all
        unless there is an update to announce.
        """
        if not self._update_pending:
            self._callout_follow_timer.stop()
            return
        if (
            not self.update_callout.isHidden()
            and self._badge_rect() == self._callout_anchored_at
        ):
            # Nothing moved. Re-placing anyway would fight the user for the
            # scroll position of a bubble they are reading.
            return
        self._place_callout()

    def dismiss_floating_callout(self) -> None:
        """Step aside while a full-window panel owns the screen.

        The bubble is a child of the window, not of this page, so a panel that
        opens after it has been placed does not cover it. It is taken off and
        asked to place itself again, which it will only manage once the window
        says nothing is covering the shell any more.
        """
        if self.update_callout.isHidden():
            return
        self.update_callout.hide()
        self._callout_retries = 0
        self._callout_retry_timer.start(400)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        """Coming back to the dashboard brings the bubble back with it."""
        super().showEvent(event)
        if self._update_pending:
            self._show_callout()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt API name
        """Leaving the dashboard takes it away.

        It announces an update from this page's own badge; on the fans page it
        would be a bubble with a tail pointing at nothing.
        """
        super().hideEvent(event)
        self.update_callout.hide()
        self._callout_retry_timer.stop()
        self._callout_follow_timer.stop()

    def _callout_dismissed(self) -> None:
        """Closing the bubble leaves the badge pulsing; nothing is lost."""
        return

    def _follow_update_advice(self) -> None:
        source = self._install_source
        if getattr(source, "channel", None) is UpdateChannel.AUR and source.command:
            InfoDialog(
                tr("New update available"),
                tr_format(
                    "This copy was installed from the AUR. Update it from a terminal:"
                    "\n\n{command}",
                    command=source.command,
                ),
                icon_name="download_blue",
                parent=self,
            ).exec()
            return
        self._open_releases()

    def _badge_clicked(self) -> None:
        """Re-open the bubble. Nothing else.

        The badge is a notification, not a command. Pressing it explains what
        is available and how to get it; the bubble's own button is the only
        thing that acts. An earlier version fell through to opening a browser
        when the bubble could not be placed, which made one click mean two
        different things depending on window state.
        """
        self._place_callout()

    def _open_releases(self) -> None:
        opened, message = open_external_url(RELEASES_PAGE_URL)
        if opened:
            return
        InfoDialog(
            tr("Official repositories"),
            message,
            icon_name="warning_orange",
            parent=self,
        ).exec()

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

    def _request_telemetry_repair(self) -> None:
        try:
            self.controller.reparar_telemetria_8core()
        except Exception:
            logger.exception("Eight-core GPU telemetry repair could not be started")

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

        invalid_telemetry = state.gpu_telemetry_invalid
        temperature = (
            tr("Invalid")
            if invalid_telemetry and state.gpu_temperature_c <= 0
            else self._format_temperature(state.gpu_temperature_c, decimals=0)
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
            tr("Invalid")
            if invalid_telemetry and state.gpu_voltage_mv <= 0
            else self._format_voltage(state.gpu_voltage_mv)
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
                tr("Invalid")
                if invalid_telemetry and state.gpu_memory_frequency_mhz <= 0
                else self._format_mhz(state.gpu_memory_frequency_mhz),
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
        diagnostic_hint = (
            tr("Advanced GPU diagnostics")
            if invalid_telemetry else ""
        )
        self.gpu_card.thermal_strip.values[0].setToolTip(diagnostic_hint)
        self.gpu_card.gpu_voltage_metric.setToolTip(diagnostic_hint)
        self.gpu_card.technical_strip.values[1].setToolTip(diagnostic_hint)
        self.gpu_card.range_row.set_value(target_range)
        self.gpu_card.accepted_row.set_value(
            self._format_mhz(state.governor_max_mhz)
        )
        repair_pending = state.gpu_telemetry_repair_pending
        repair_needed = state.gpu_metrics_layout_mismatch or repair_pending
        self.gpu_card.telemetry_repair_button.setVisible(repair_needed)
        self.gpu_card.telemetry_repair_button.setEnabled(
            state.gpu_metrics_layout_mismatch
            and state.gpu_telemetry_repair_available
            and not repair_pending
        )
        self.gpu_card.telemetry_repair_button.setText(
            tr("Restart to finish telemetry repair")
            if repair_pending
            else tr("Repair BC250 telemetry")
        )
        self.gpu_card.gpu_summary.set_value(state.gpu_summary)
        self.gpu_card.vram_summary.set_value(state.vram_summary)
        cores_known = 0 < state.cpu_physical_cores <= state.cpu_logical_cores
        self.gpu_card.cores_summary.set_value(
            tr_format("{cores} cores / {threads} threads", cores=state.cpu_physical_cores, threads=state.cpu_logical_cores)
            if cores_known else tr("Not detected")
        )
        if cores_known and state.cpu_oc_active and state.cpu_oc_scale is not None:
            cpu_oc_detail = tr_format(
                "Registered OC: {frequency} MHz · Scale {scale}",
                frequency=state.cpu_oc_frequency_mhz,
                scale=state.cpu_oc_scale,
            )
        else:
            cpu_oc_detail = ""
        self.gpu_card.cores_summary.set_detail(cpu_oc_detail)
        # Every BC-250 has eight physical core positions.  A stock firmware
        # exposes six to Linux; retain all eight slots so the two hidden cores
        # are visible instead of silently disappearing from the dashboard.
        self.gpu_card.cores_summary.set_core_count(8)
        self.gpu_card.cores_summary.set_core_metrics(
            self.state.cpu_per_core_frequency_mhz,
            self.state.cpu_per_core_percent,
        )
        self._apply_memory_summary()

    def _apply_memory_summary(self) -> None:
        """Mirror the shared monitor; a page refresh never samples by itself.

        A dashboard refresh runs every few seconds and a real read costs a
        Polkit check, so sampling from here would prompt for a password on a
        loop. Only the live button asks for readings.
        """
        self.memory_monitor.refresh_status()
        self._apply_memory_reading(self.memory_monitor.reading)

    def _apply_memory_reading(self, reading) -> None:
        summary = self.memory_summary
        summary.set_live(bool(getattr(reading, "live", False)))
        chips = [
            (chip.index, chip.code, chip.temperature_c) for chip in reading.chips
        ]
        summary.set_chips(chips)
        summary.live_button.setEnabled(reading.can_monitor or reading.live)
        if chips:
            summary.set_value(self._format_temperature(_number(reading.average_c)))
            summary.set_detail(
                tr_format(
                    "Hotspot {value}",
                    value=self._format_temperature(_number(reading.hotspot_c)),
                )
            )
        else:
            summary.set_value("Waiting for sample")
            # No instruction here any more: the CPU module's GDDR6 card is
            # gone, and the only way to get a reading is the button sitting on
            # this very row, which says so itself.
            summary.set_detail("")

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
