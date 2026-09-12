from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any

from PyQt6.QtCore import QObject, QSettings, QTimer, pyqtSignal

from ..components.async_tools import BackgroundExecutor
from ..i18n import tr, tr_format
from .alert_policy import AlertEvent, classify_alerts, evaluate_alert_cooldown
from .state import state_cache_for

logger = logging.getLogger(__name__)

# Notifications are deliberately retired for now.  Keep the monitor class and
# its alert policy in place for a future opt-in feature, but make every entry
# point fail closed until that feature is explicitly restored.
NOTIFICATIONS_ENABLED = False


class SmartAlertMonitor(QObject):
    """Passive safety monitor migrated from the retired interface.

    Reads execute outside the UI thread. The monitor never changes hardware; it
    records throttled events and can send localized desktop notifications.
    """

    alert_triggered = pyqtSignal(str, str, str)

    def __init__(self, controller: Any, settings: QSettings, *, activity_service, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.activity_service = activity_service
        self.settings = settings
        self._executor = BackgroundExecutor(self)
        self._state_cache = state_cache_for(controller, activity_service=activity_service)
        self._last_alert: dict[str, float] = {}
        self._gpu_history: deque[tuple[float, float]] = deque(maxlen=90)
        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self.refresh)
        self._sample_busy = False
        self.set_enabled(False)

    def set_enabled(self, enabled: bool) -> None:
        del enabled
        self.settings.setValue("settings/smart_alerts", "false")
        self.settings.setValue("settings/desktop_notifications", "false")
        self._timer.stop()

    def refresh(self) -> None:
        if not NOTIFICATIONS_ENABLED or self._sample_busy:
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

    def _process_sample(self, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
        gpu_state = data.get("gpu_state") if isinstance(data.get("gpu_state"), dict) else {}
        classification = classify_alerts(
            metrics,
            gpu_state,
            gpu_history=self._gpu_history,
            now=time.monotonic(),
        )
        self._gpu_history.clear()
        self._gpu_history.extend(classification.gpu_history)
        for event in classification.events:
            self._emit_alert(event)

    def _emit_alert(self, event: AlertEvent) -> None:
        if not NOTIFICATIONS_ENABLED:
            return
        now = time.monotonic()
        decision = evaluate_alert_cooldown(
            event,
            last_alerts=self._last_alert,
            now=now,
        )
        if not decision.accepted:
            return
        self._last_alert[event.key] = decision.accepted_at or now
        title = tr(event.title_key)
        message = tr_format(event.message_key, **dict(event.values))
        self.alert_triggered.emit(title, message, event.level)

        metadata = {
            "key": event.key,
            "i18n_title": event.title_key,
            "i18n_message": event.message_key,
            "i18n_values": dict(event.values),
        }

        def record() -> object:
            return self.activity_service.record(
                "alert",
                event.level,
                event.title_key,
                event.canonical_message(),
                metadata,
            )

        self._executor.start(f"smart-alert-record:{event.key}", record)
