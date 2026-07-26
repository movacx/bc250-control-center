from __future__ import annotations

import os
import logging
import time
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal, pyqtSlot


logger = logging.getLogger(__name__)


_PERF_TRACE = os.environ.get("BC250_UI_PERF", "").strip().lower() in {"1", "true", "yes", "on"}


class _TaskSignals(QObject):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)
    finished = pyqtSignal()


class _FunctionTask(QRunnable):
    def __init__(self, name: str, operation: Callable[[], Any]):
        super().__init__()
        self.name = str(name)
        self.operation = operation
        self.signals = _TaskSignals()
        self.setAutoDelete(True)

    @pyqtSlot()
    def run(self) -> None:
        started = time.perf_counter()
        try:
            result = self.operation()
        except Exception as error:  # backend failures are reported to the UI thread
            self.signals.failed.emit(str(error))
        else:
            self.signals.succeeded.emit(result)
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            if _PERF_TRACE:
                logger.info("UI task %s completed in %.1f ms", self.name, elapsed_ms)
            self.signals.finished.emit()


class AsyncRefresh(QObject):
    """Coalesced background refresh for one page.

    At most one backend read is in flight. Timer ticks that arrive while a read is
    running are collapsed into one pending refresh. Results are cached while the
    page is inactive and rendered only after it becomes active again.
    """

    def __init__(
        self,
        owner: QObject,
        name: str,
        operation: Callable[[], Any],
        apply_result: Callable[[Any], None],
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(owner)
        self._name = str(name)
        self._operation = operation
        self._apply_result = apply_result
        self._on_error = on_error
        self._pool = QThreadPool.globalInstance()
        self._active = False
        self._running = False
        self._queued = False
        self._latest: Any = None
        self._has_latest = False
        self._latest_at = 0.0
        self._latest_version = 0
        self._rendered_version = 0
        self._activation_generation = 0
        self._task: _FunctionTask | None = None

    @property
    def running(self) -> bool:
        return self._running

    def set_active(self, active: bool) -> None:
        active = bool(active)
        if active != self._active:
            self._activation_generation += 1
        self._active = active
        if not active:
            # A timer tick queued just before a page was hidden must not start a
            # second backend read when the current one finishes.
            self._queued = False

    def activate(
        self,
        *,
        fresh_for: float = 0.0,
        render_delay_ms: int = 16,
        refresh_delay_ms: int = 120,
    ) -> None:
        """Resume a page without blocking the navigation slot.

        Rendering a cached snapshot synchronously inside a sidebar click keeps
        Qt from painting the newly selected page.  The result is functional but
        feels like a frozen navigation transition.  Activation is therefore
        queued for the next frame.  A recent cached snapshot is reused without
        immediately scheduling an identical backend read; stale snapshots are
        shown first and refreshed shortly afterwards.
        """
        self.set_active(True)
        # navigate() and Qt's showEvent can both activate the same page during
        # one transition.  Give every activation its own generation so only the
        # final queued render/read survives and duplicate refreshes are collapsed.
        self._activation_generation += 1
        generation = self._activation_generation

        def resume() -> None:
            if not self._active or generation != self._activation_generation:
                return
            had_latest = self._has_latest
            self.replay_latest()
            age = max(0.0, time.monotonic() - self._latest_at) if had_latest else float("inf")
            if had_latest and age <= max(0.0, float(fresh_for)):
                return

            def request_if_current() -> None:
                if self._active and generation == self._activation_generation:
                    self.request()

            QTimer.singleShot(max(0, int(refresh_delay_ms if had_latest else 0)), request_if_current)

        QTimer.singleShot(max(0, int(render_delay_ms)), resume)

    def replay_latest(self) -> bool:
        if not self._active or not self._has_latest:
            return False
        if self._rendered_version == self._latest_version:
            return False
        self._apply_on_ui(self._latest, "cached-render", self._latest_version)
        return True

    def request(self) -> None:
        if not self._active:
            return
        if self._running:
            self._queued = True
            return
        self._running = True
        self._queued = False
        task = _FunctionTask(self._name, self._operation)
        self._task = task
        task.signals.succeeded.connect(self._result_ready)
        task.signals.failed.connect(self._error_ready)
        task.signals.finished.connect(self._finished)
        self._pool.start(task)

    def _result_ready(self, result: Any) -> None:
        self._latest = result
        self._has_latest = True
        self._latest_at = time.monotonic()
        self._latest_version += 1
        if self._active:
            self._apply_on_ui(result, "render", self._latest_version)

    def _apply_on_ui(self, result: Any, phase: str, version: int) -> None:
        started = time.perf_counter()
        self._apply_result(result)
        self._rendered_version = version
        if _PERF_TRACE:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            logger.info("UI refresh %s:%s completed in %.1f ms", self._name, phase, elapsed_ms)

    def _error_ready(self, message: str) -> None:
        if not self._active:
            return
        if self._on_error is not None:
            self._on_error(message)
        else:
            logger.warning("UI refresh %s failed: %s", self._name, message)

    def _finished(self) -> None:
        self._running = False
        self._task = None
        if self._queued and self._active:
            self.request()


class BackgroundExecutor(QObject):
    """Small keyed executor for non-refresh backend operations."""

    busy_changed = pyqtSignal(bool)

    def __init__(self, owner: QObject):
        super().__init__(owner)
        self._pool = QThreadPool.globalInstance()
        self._running: dict[str, _FunctionTask] = {}

    def is_running(self, key: str | None = None) -> bool:
        return bool(self._running) if key is None else key in self._running

    def start(
        self,
        key: str,
        operation: Callable[[], Any],
        on_success: Callable[[Any], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_finished: Callable[[], None] | None = None,
    ) -> bool:
        key = str(key)
        if key in self._running:
            return False
        task = _FunctionTask(key, operation)
        self._running[key] = task
        if len(self._running) == 1:
            self.busy_changed.emit(True)
        if on_success is not None:
            task.signals.succeeded.connect(on_success)
        if on_error is not None:
            task.signals.failed.connect(on_error)
        else:
            task.signals.failed.connect(lambda message, task_key=key: logger.error("Background task %s failed: %s", task_key, message))

        def finished() -> None:
            self._running.pop(key, None)
            if on_finished is not None:
                on_finished()
            if not self._running:
                self.busy_changed.emit(False)

        task.signals.finished.connect(finished)
        self._pool.start(task)
        return True
