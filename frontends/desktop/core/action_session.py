"""Lifecycle for one asynchronous mutating UI action."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .operation_gate import OperationGate


class ActionSession:
    def __init__(
        self,
        *,
        gate: OperationGate,
        token: int,
        controls: tuple[tuple[Any, bool], ...],
        on_success: Callable[[object], None],
        on_failure: Callable[[str], None],
        on_callback_error: Callable[[Exception], None],
        invalidate: Callable[[], None],
        refresh: Callable[[], None],
        refresh_enabled: bool,
        after_success: Callable[[], None] | None = None,
    ) -> None:
        self.gate = gate
        self.token = token
        self.controls = controls
        self.on_success = on_success
        self.on_failure = on_failure
        self.on_callback_error = on_callback_error
        self.invalidate = invalidate
        self.refresh = refresh
        self.refresh_enabled = bool(refresh_enabled)
        self.after_success = after_success
        self.result_seen = False
        self.refresh_pending = False

    def success(self, result: object) -> None:
        if not self.gate.is_current(self.token) or self.result_seen:
            return
        self.result_seen = True
        handled = False
        try:
            self.on_success(result)
            handled = True
        except Exception as error:  # UI callback boundary
            self.on_callback_error(error)
        self._request_reconciliation()
        if handled and self.after_success is not None:
            self.after_success()

    def failure(self, message: str) -> None:
        if not self.gate.is_current(self.token) or self.result_seen:
            return
        self.result_seen = True
        self.on_failure(str(message))
        self._request_reconciliation()

    def _request_reconciliation(self) -> None:
        self.refresh_pending = self.refresh_enabled
        if self.refresh_pending:
            self.invalidate()

    def finished(self) -> None:
        if not self.gate.finish(self.token):
            return
        self._restore_controls()
        if self.refresh_pending:
            self.refresh()

    def abort(self) -> None:
        if self.gate.finish(self.token):
            self._restore_controls()

    def _restore_controls(self) -> None:
        for control, was_enabled in self.controls:
            control.setEnabled(was_enabled)
