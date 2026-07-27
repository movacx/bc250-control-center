from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import logging
import shutil
import subprocess
import time
from typing import Any, Mapping

from PyQt6.QtCore import QObject, QSettings, QTimer, pyqtSignal

from ..components.async_tools import BackgroundExecutor
from ..i18n import tr, tr_format
from .state import state_cache_for


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlertEvent:
    key: str
    title_key: str
    message_key: str
    values: Mapping[str, object] = field(default_factory=dict)
    level: str = "info"
    cooldown_seconds: int = 300

    def localized(self) -> tuple[str, str]:
        return tr(self.title_key), tr_format(self.message_key, **dict(self.values))

    def canonical_message(self) -> str:
        try:
            return self.message_key.format(**dict(self.values))
        except (KeyError, ValueError, IndexError):
            return self.message_key


class SmartAlertMonitor(QObject):
    """Passive safety monitor migrated from the retired interface.

    Reads execute outside the UI thread. The monitor never changes hardware; it
    records throttled events and can send localized desktop notifications.
    """

    alert_triggered = pyqtSignal(str, str, str)

    def __init__(self, controller: Any, settings: QSettings, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.settings = settings
        self._executor = BackgroundExecutor(self)
        self._state_cache = state_cache_for(controller)
        self._last_alert: dict[str, float] = {}
        self._gpu_history: deque[tuple[float, float]] = deque(maxlen=90)
        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self.refresh)
        self._sample_busy = False
        self.set_enabled(self._setting_bool("settings/smart_alerts", False))

    def _setting_bool(self, key: str, default: bool) -> bool:
        value = self.settings.value(key, "true" if default else "false")
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def set_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        self.settings.setValue("settings/smart_alerts", "true" if enabled else "false")
        if enabled:
            if not self._timer.isActive():
                self._timer.start()
            QTimer.singleShot(0, self.refresh)
        else:
            self._timer.stop()

    def refresh(self) -> None:
        if not self._setting_bool("settings/smart_alerts", False) or self._sample_busy:
            return
        self._sample_busy = True

        def operation() -> dict[str, Any]:
            metrics = self._state_cache.realtime_metrics()
            try:
                gpu_state = self._state_cache.gpu()
            except Exception as error:
                gpu_state = {"read_error": str(error)}
            return {"metrics": metrics, "gpu_state": gpu_state}

        def success(payload: object) -> None:
            self._sample_busy = False
            self._process_sample(payload)

        def failure(message: str) -> None:
            self._sample_busy = False
            logger.warning("Smart safety monitoring sample failed: %s", message)

        self._executor.start("smart-alert-sample", operation, success, failure)

    @staticmethod
    def _number(value: object) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError, OverflowError):
            return None

    def _process_sample(self, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
        gpu_state = data.get("gpu_state") if isinstance(data.get("gpu_state"), dict) else {}
        cpu = metrics.get("cpu") if isinstance(metrics.get("cpu"), dict) else {}
        gpu = metrics.get("gpu") if isinstance(metrics.get("gpu"), dict) else {}
        memory = metrics.get("memory") if isinstance(metrics.get("memory"), dict) else {}

        cpu_temp = self._number(cpu.get("temperature_c"))
        gpu_temp = self._number(gpu.get("temperature_c"))
        gpu_usage = self._number(gpu.get("usage_percent"))
        memory_usage = self._number(memory.get("usage_percent")) or 0.0
        swap_usage = self._number(memory.get("swap_percent")) or 0.0
        current_max = self._number(gpu_state.get("current_max")) or 0.0

        events: list[AlertEvent] = []
        if gpu_temp is not None:
            now = time.monotonic()
            self._gpu_history.append((now, gpu_temp))
            while self._gpu_history and now - self._gpu_history[0][0] > 60:
                self._gpu_history.popleft()
            if gpu_temp >= 85:
                events.append(AlertEvent(
                    "gpu-temp-critical",
                    "Critical GPU temperature",
                    "GPU edge is {temperature:.1f} °C. Reduce load or frequency and check cooling.",
                    {"temperature": gpu_temp},
                    "critical",
                    180,
                ))
            elif gpu_temp >= 78:
                events.append(AlertEvent(
                    "gpu-temp-high",
                    "High GPU temperature",
                    "GPU edge is {temperature:.1f} °C. Monitor overclock, 40CU mode, and cooling.",
                    {"temperature": gpu_temp},
                    "warning",
                    300,
                ))
            if len(self._gpu_history) >= 4:
                rise = gpu_temp - self._gpu_history[0][1]
                if gpu_temp >= 70 and rise >= 8:
                    events.append(AlertEvent(
                        "gpu-temp-rise",
                        "Rapid GPU temperature rise",
                        "GPU temperature increased {rise:.1f} °C in under one minute.",
                        {"rise": rise},
                        "warning",
                        300,
                    ))

        if cpu_temp is not None:
            if cpu_temp >= 90:
                events.append(AlertEvent(
                    "cpu-temp-critical",
                    "Critical CPU temperature",
                    "CPU Tctl is {temperature:.1f} °C. Throttling or shutdown may occur.",
                    {"temperature": cpu_temp},
                    "critical",
                    180,
                ))
            elif cpu_temp >= 82:
                events.append(AlertEvent(
                    "cpu-temp-high",
                    "High CPU temperature",
                    "CPU Tctl is {temperature:.1f} °C. Review CPU tuning and cooling.",
                    {"temperature": cpu_temp},
                    "warning",
                    300,
                ))

        if memory_usage >= 92 or swap_usage >= 70:
            events.append(AlertEvent(
                "memory-critical",
                "High memory pressure",
                "RAM {memory:.0f}% · swap {swap:.0f}%. Stutter or freezing is possible.",
                {"memory": memory_usage, "swap": swap_usage},
                "critical",
                240,
            ))
        elif memory_usage >= 85 or swap_usage >= 45:
            events.append(AlertEvent(
                "memory-warning",
                "Memory pressure detected",
                "RAM {memory:.0f}% · swap {swap:.0f}%. Consider closing heavy applications.",
                {"memory": memory_usage, "swap": swap_usage},
                "warning",
                420,
            ))

        service_state = str(gpu_state.get("service_active") or "").lower()
        if service_state and service_state not in {"active", "running"}:
            events.append(AlertEvent(
                "governor-inactive",
                "GPU governor is not active",
                "cyan-skillfish-governor-smu state: {state}.",
                {"state": service_state},
                "critical",
                180,
            ))
        elif gpu_state and not bool(gpu_state.get("dbus_ok", True)):
            events.append(AlertEvent(
                "governor-dbus",
                "GPU governor D-Bus unavailable",
                "Monitoring remains available, but GPU ranges cannot be applied through D-Bus.",
                level="critical",
                cooldown_seconds=180,
            ))

        if current_max >= 2000 and (gpu_usage or 0) >= 80 and (gpu_temp or 0) >= 72:
            events.append(AlertEvent(
                "gpu-high-oc-load",
                "High GPU overclock under load",
                "GPU load {usage:.0f}% · maximum {maximum:.0f} MHz · {temperature:.1f} °C.",
                {"usage": gpu_usage or 0.0, "maximum": current_max, "temperature": gpu_temp or 0.0},
                "warning",
                240,
            ))

        for event in events:
            self._emit_alert(event)

    def _emit_alert(self, event: AlertEvent) -> None:
        now = time.monotonic()
        if now - self._last_alert.get(event.key, 0.0) < event.cooldown_seconds:
            return
        self._last_alert[event.key] = now
        title, message = event.localized()
        self.alert_triggered.emit(title, message, event.level)

        metadata = {
            "key": event.key,
            "i18n_title": event.title_key,
            "i18n_message": event.message_key,
            "i18n_values": dict(event.values),
        }

        def record() -> object:
            return self.controller.registrar_evento(
                "alert",
                event.level,
                event.title_key,
                event.canonical_message(),
                metadata,
            )

        self._executor.start(f"smart-alert-record:{event.key}", record)

        if not self._setting_bool("settings/desktop_notifications", True):
            return
        notify_send = shutil.which("notify-send")
        if not notify_send:
            return
        urgency = "critical" if event.level == "critical" else "normal"
        try:
            subprocess.Popen(
                [notify_send, "-a", "BC250 Control Center", "-u", urgency, "-i", "utilities-system-monitor", title, message],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            logger.warning("Desktop safety notification could not be started", exc_info=True)
