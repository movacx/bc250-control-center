"""One GDDR6 sampling engine, shared by every page that shows the readings.

The CPU module and the dashboard both display per-chip memory temperature,
but a reading costs a Polkit check and the runtime SMU patch is global board
state. Two independent samplers would mean two password prompts, two timers
racing on the same mailbox, and two answers that disagree.

So the engine lives here, once per controller (the same shape
``state_cache_for`` uses), and the pages are views onto it:

* Nothing is sampled unless a page explicitly asks. A periodic dashboard
  refresh must never trigger a privileged call on its own.
* Live monitoring is **one** authenticated session, not a timer that re-runs a
  privileged read: the helper is launched once, applies the patch if the board
  needs it, streams a sample per line, and ends itself after a bounded window.
  That is one Polkit prompt for the whole session, and nothing stays
  authenticated once it closes.
* When the session ends the button goes back to off. Resuming is a deliberate
  act, which is the point: the SMU is shared with the GPU governor and the CPU
  overclocking tool, so an unattended machine should not keep poking at it.
"""

from __future__ import annotations

import json
import threading
import weakref
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from PyQt6.QtCore import QObject, QProcess, pyqtSignal

from ..components.async_tools import BackgroundExecutor

#: How long one authenticated live session lasts, in seconds. Enforced by the
#: helper itself; this copy is only so the interface can say so. When it ends
#: the user presses the button again — nothing stays authenticated.
LIVE_SESSION_SECONDS = 600


def _dict(value: Any) -> dict:
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    try:
        return dict(value or {})
    except Exception:
        return {}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


@dataclass(frozen=True)
class Gddr6Chip:
    index: int
    code: int = 0
    temperature_c: float = 0.0


@dataclass(frozen=True)
class Gddr6Reading:
    """Everything known about the GDDR6 interface right now."""

    hardware_detected: bool = False
    repository_ready: bool = False
    reader_ready: bool = False
    helper_ready: bool = False
    payload_present: bool = False
    firmware_supported: bool = False
    bios_version: str = ""
    patch_active: bool = False
    chips: tuple[Gddr6Chip, ...] = ()
    average_c: float | None = None
    hotspot_c: float | None = None
    hotspot_chip: int | None = None
    sampled_at: str = ""
    error: str = ""
    busy: bool = False
    live: bool = False

    @property
    def can_apply(self) -> bool:
        return bool(
            self.hardware_detected
            and self.repository_ready
            and self.helper_ready
            and self.payload_present
            and self.firmware_supported
            and not self.patch_active
        )

    @property
    def can_read(self) -> bool:
        """A single read is allowed as soon as the reader is installed.

        It is also how the patch state is discovered: the reader reports it in
        the same round trip, so nothing has to spend a prompt just to ask.
        """
        return bool(
            self.hardware_detected and self.repository_ready and self.reader_ready
        )

    @property
    def can_monitor(self) -> bool:
        """Live sampling needs the patch, and can install it on the way in."""
        return bool(self.can_read and (self.patch_active or self.can_apply))

    def blocker(self) -> str:
        """The single most useful thing to say about why this is not running."""
        if not self.hardware_detected:
            return "No BC-250 hardware was detected on this machine."
        if not self.repository_ready:
            return "The reviewed upstream checkout is not prepared yet."
        if not (self.reader_ready and self.helper_ready):
            return "Reinstall BC250 Control Center to install the privileged helpers."
        if not self.firmware_supported:
            return (
                "The reviewed SMU payload targets board firmware P3.0; this board "
                "reports a different version, so the patch is not offered."
            )
        if not self.patch_active:
            return (
                "The runtime SMU patch is not active. It lives in volatile SMU RAM, "
                "so it has to be applied again after every full power cycle."
            )
        return ""


@dataclass
class _RawState:
    """The two backend answers a reading is assembled from."""

    status: dict = field(default_factory=dict)
    sample: dict = field(default_factory=dict)


class Gddr6Monitor(QObject):
    """Owns the patch/read workflow and broadcasts one reading to every view."""

    changed = pyqtSignal(object)

    def __init__(self, controller: Any, parent: QObject | None = None):
        super().__init__(parent)
        self.controller = controller
        self._state = _RawState()
        self._reading = Gddr6Reading()
        self._background = BackgroundExecutor(self)
        self._live = False
        self._session: QProcess | None = None
        self._session_buffer = ""

    # ------------------------------------------------------------------ state

    @property
    def reading(self) -> Gddr6Reading:
        return self._reading

    def _backend(self, name: str):
        """The GDDR6 workflow is optional; an older backend simply has none."""
        return getattr(self.controller, name, None)

    def _rebuild(self) -> None:
        status, sample = self._state.status, self._state.sample
        chips = tuple(
            Gddr6Chip(
                index=int(_number(entry.get("chip"), -1)),
                code=int(_number(entry.get("code"))),
                temperature_c=_number(entry.get("temperature_c")),
            )
            for entry in (sample.get("chips") or [])
            if isinstance(entry, dict) and int(_number(entry.get("chip"), -1)) >= 0
        )
        hotspot_chip = sample.get("hotspot_chip")
        self._reading = Gddr6Reading(
            hardware_detected=bool(status.get("hardware_detected")),
            repository_ready=bool(status.get("repository_ready")),
            reader_ready=bool(status.get("reader_ready")),
            helper_ready=bool(status.get("helper_ready")),
            payload_present=bool(status.get("payload_present")),
            firmware_supported=bool(status.get("firmware_supported")),
            bios_version=str(status.get("bios_version") or ""),
            patch_active=bool(sample.get("patch_active")),
            chips=chips,
            average_c=_number(sample["average_c"]) if "average_c" in sample else None,
            hotspot_c=_number(sample["hotspot_c"]) if "hotspot_c" in sample else None,
            hotspot_chip=int(_number(hotspot_chip)) if hotspot_chip is not None else None,
            sampled_at=str(sample.get("sampled_at") or ""),
            error=str(sample.get("error") or ""),
            busy=self._live,
            live=self._live,
        )
        self.changed.emit(self._reading)

    # --------------------------------------------------------------- readiness

    def refresh_status(self) -> None:
        """Unprivileged readiness only, safe to call on any page refresh."""
        operation = self._backend("estado_gddr6_memory_temp")
        if operation is None:
            return

        def success(status: object) -> None:
            self._state.status = _dict(status)
            self._rebuild()

        def failure(_message: str) -> None:
            return None

        self._background.start("gddr6-status", operation, success, failure)

    # --------------------------------------------------------------- preparing

    def prepare(self) -> bool:
        """Fetch the reviewed upstream checkout, in the embedded terminal.

        Nothing here reads the hardware or patches anything: it is a clone of
        a reviewed revision, which is why it costs no Polkit prompt. It exists
        because without the checkout every other action on this strip is
        refused, and until now the only interface that offered it was a page
        that no longer ships — leaving the live button permanently grey with
        nothing on screen saying why.
        """
        operation = self._backend("comando_preparar_gddr6_memory_temp")
        if operation is None:
            return False
        try:
            return bool(operation())
        except Exception as error:  # noqa: BLE001 - surfaced through the reading
            self._session_error(str(error))
            return False

    # -------------------------------------------------------------------- live

    def start_live(self) -> None:
        """One authenticated session: patch if needed, then sample until it ends.

        Deliberately a single privileged process rather than a timer that
        re-runs a privileged read: a timer costs a Polkit check per sample and
        leaves the grant cached between them. This asks once, samples for a
        bounded window, and ends by itself.
        """
        if self._live or self._session is not None:
            return
        operation = self._backend("comando_monitorizar_vram")
        if operation is None:
            return
        try:
            command = [str(item) for item in (operation() or [])]
        except Exception as error:  # noqa: BLE001 - surfaced through the reading
            self._session_error(str(error))
            return
        if not command:
            return

        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.readyReadStandardOutput.connect(self._read_session_output)
        process.finished.connect(self._session_finished)
        process.errorOccurred.connect(lambda _error: self._session_finished(1, None))
        self._session = process
        self._session_buffer = ""
        self._live = True
        self._rebuild()
        process.start(command[0], command[1:])

    def stop_live(self) -> None:
        session, self._session = self._session, None
        self._live = False
        if session is not None:
            session.readyReadStandardOutput.disconnect()
            session.finished.disconnect()
            session.terminate()
            if not session.waitForFinished(1500):
                session.kill()
        self._rebuild()

    def set_live(self, active: bool) -> None:
        self.start_live() if active else self.stop_live()

    # ------------------------------------------------------- session plumbing

    def _read_session_output(self) -> None:
        """Each line is one sample; the helper flushes them as it takes them."""
        process = self._session
        if process is None:
            return
        self._session_buffer += bytes(
            process.readAllStandardOutput()
        ).decode("utf-8", errors="replace")
        while "\n" in self._session_buffer:
            line, self._session_buffer = self._session_buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            if payload.get("session_ended"):
                continue
            payload["available"] = True
            payload["sampled_at"] = datetime.now().strftime("%H:%M:%S")
            self._state.sample = payload
            self._rebuild()

    def _session_finished(self, exit_code: int, _status) -> None:
        session, self._session = self._session, None
        self._live = False
        error = ""
        if session is not None and exit_code != 0:
            error = bytes(session.readAllStandardError()).decode(
                "utf-8", errors="replace"
            ).strip()
        # Back to the base state. The readings were live measurements, and the
        # moment sampling stops they are only a photograph of a minute that has
        # passed — leaving them on screen presents stale numbers as current
        # ones, which is worse than showing nothing. The patch state survives:
        # the patch itself is still installed until the board loses power.
        self._state.sample = {
            "patch_active": self._state.sample.get("patch_active", False),
            "error": error,
        }
        self._rebuild()

    def _session_error(self, message: str) -> None:
        self._state.sample = dict(self._state.sample, error=message)
        self._rebuild()


_LOCK = threading.RLock()
_MONITORS: weakref.WeakKeyDictionary[Any, Gddr6Monitor] = weakref.WeakKeyDictionary()
_FALLBACK: dict[int, Gddr6Monitor] = {}


def gddr6_monitor_for(controller: Any) -> Gddr6Monitor:
    """One monitor per controller, so every page shares the same engine."""
    with _LOCK:
        try:
            monitor = _MONITORS.get(controller)
            if monitor is None:
                monitor = Gddr6Monitor(controller)
                _MONITORS[controller] = monitor
            return monitor
        except TypeError:
            key = id(controller)
            monitor = _FALLBACK.get(key)
            if monitor is None:
                monitor = Gddr6Monitor(controller)
                _FALLBACK[key] = monitor
            return monitor
