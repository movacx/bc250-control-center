"""Bounded reads and finite user-service controls for the desktop black box."""
from __future__ import annotations

import threading
import time

from bc250cc.application.system.privacy import redact_machine
from frontends.desktop.core.diagnosis_groups import TABS, section_group

COLUMNS = (("Time", "time"), ("GPU clock", "clock"), ("GPU load", "busy"),
           ("GPU °C", "t_gpu"), ("CPU °C", "t_cpu"), ("GFX mV", "volts"),
           ("Power W", "watts"), ("Fans rpm", "rpm"), ("CPU MHz", "cpu"), ("Free RAM MiB", "mem"))
STATE_TEXT = {
    "none": "No recording is available. Start recording before playing to catch a freeze.",
    "recording": "Recording now. The newest row is at the top.",
    "stopped": "Stopped. These are the last rows it recorded.",
    "stopped-before-restart": "It was stopped normally before the last restart. These are the last rows it recorded.",
    "cut-off": "Cut off by a restart or a freeze. The top rows are the board's last seconds.",
}
MAX_ROWS = 500


def collect_diagnosis():
    from bc250cc.application.system.diagnostics import collect_readonly_attachments

    return collect_readonly_attachments()


class BlackBox:
    def __init__(self, service, *, collect=None):
        self.service = service
        self.collect = collect or collect_diagnosis
        self._status_lock = threading.Lock()
        self._stamp = 0.0
        self._status = None
        self._lock = threading.Lock()
        self._diagnosis = {"loading": False, "ready": False, "sections": [], "error": ""}
        self._started = None

    def recording(self):
        with self._status_lock:
            if self._status is not None and time.monotonic() - self._stamp < 1:
                return self._status
            raw = self.service.blackbox_estado(MAX_ROWS) or {}
            state = raw.get("state", "none")
            rows = [{key: str(row.get(key, "—"))[:160] for _, key in COLUMNS}
                    for row in (raw.get("rows") or [])[:MAX_ROWS] if isinstance(row, dict)]
            self._status = {"running": bool(raw.get("running")), "state": state,
                            "message": STATE_TEXT.get(state, STATE_TEXT["none"]), "rows": rows,
                            "supported": bool(raw.get("supported")),
                            "autostart": {key: bool((raw.get("autostart") or {}).get(key)) for key in ("supported", "enabled", "foreign")},
                            "limit": MAX_ROWS, "columns": [{"key": key, "label": label} for label, key in COLUMNS]}
            self._stamp = time.monotonic()
            return self._status

    def control(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("operation")
        operation = payload.get("operation")
        if not isinstance(operation, str) or operation not in {"start", "stop", "autostart"} or set(payload) - {"operation", "enabled"}:
            raise ValueError("operation")
        if operation == "autostart":
            if type(payload.get("enabled")) is not bool:
                raise ValueError("enabled")
        elif "enabled" in payload:
            raise ValueError("enabled")
        with self._status_lock:
            try:
                if operation == "start":
                    self.service.blackbox_iniciar()
                elif operation == "stop":
                    self.service.blackbox_detener()
                else:
                    self.service.blackbox_con_la_sesion(payload["enabled"])
            finally:
                # Even a partial service failure must invalidate the old status.
                self._status = None
                self._stamp = 0.0
        return {"ok": True}

    def diagnosis(self, *, refresh=False):
        with self._lock:
            now = time.monotonic()
            if not self._diagnosis["loading"] and (self._started is None or refresh and now - self._started >= 30):
                self._started = now
                self._diagnosis = {**self._diagnosis, "loading": True, "error": ""}
                threading.Thread(target=self._collect, name="bc250-web-diagnosis", daemon=True).start()
            return {**self._diagnosis, "tabs": [{"key": key, "label": label} for key, label in TABS]}

    def _collect(self):
        try:
            sections = []
            remaining = 240_000
            for title, text in self.collect():
                if len(sections) >= 64 or remaining <= 0:
                    break
                body = redact_machine(str(text))[:min(16000, remaining)]
                sections.append({"title": str(title)[:160], "text": body, "group": section_group(title)})
                remaining -= len(body)
            result = {"loading": False, "ready": True, "sections": sections, "error": ""}
        except Exception:
            # Internal exception details can contain paths or command output.
            result = {**self._diagnosis, "loading": False, "error": "The diagnosis could not be read. Try refreshing it."}
        with self._lock:
            self._diagnosis = result
