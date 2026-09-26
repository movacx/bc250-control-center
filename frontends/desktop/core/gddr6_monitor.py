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
* BC250-Telemetry can run its own GDDR6 collector on the same SMU mailbox.
  While it does, this engine never starts a session: two samplers on that
  mailbox is what hung the board. It shows what that collector publishes
  instead, which costs no prompt and never touches the SMU.
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
from ..i18n import tr, tr_format

#: How long one authenticated live session lasts, in seconds. Enforced by the
#: helper itself; this copy is only so the interface can say so. When it ends
#: the user presses the button again — nothing stays authenticated.
LIVE_SESSION_SECONDS = 600

#: Where the readings came from when BC250-Telemetry's collector took them.
EXTERNAL_SOURCE = "bc250-telemetry"

_EXTERNAL_INTERRUPTED = (
    "BC250-Telemetry's memory service stopped in the middle of an SMU "
    "operation this boot. Power the board off completely before reading "
    "memory temperature again."
)
_GOVERNOR_STARTING = (
    "The GPU governor is starting, and while it starts it uses the same SMU "
    "queue as these readings. They resume once it is running."
)
_GOVERNOR_RESTARTING = (
    "The GPU governor keeps restarting, and every restart uses the same SMU "
    "queue as these readings, so they are paused. This usually means “Fix "
    "metrics” is on but this kernel has no gpu_metrics file: turn it off on "
    "the GPU page."
)

#: Why a live session ended, for the failures a user can act on. Anything
#: else keeps the base state's own explanation.
_SESSION_ERRORS = (
    ("GDDR6_EXTERNAL_INTERRUPTED", _EXTERNAL_INTERRUPTED),
    (
        "GDDR6_EXTERNAL_COLLECTOR",
        "BC250-Telemetry's memory service is running. Its readings will appear here.",
    ),
    (
        "GDDR6_GOVERNOR_UNSETTLED",
        _GOVERNOR_STARTING,
    ),
    (
        "SMU_BUSY",
        "Another BC-250 tool is using the SMU right now. Wait for it to finish "
        "and try again.",
    ),
)


def firmware_blocker(bios_version: str) -> str:
    """Why live readings are refused on this board's firmware, and the way out.

    Deliberately not something the manual override lifts: the payload writes
    fixed SMU addresses that upstream verified only on P3.00, and its own
    README warns that another firmware can corrupt memory.
    """
    detected = str(bios_version or "").strip()
    reason = (
        tr_format(
            "This board runs BIOS {version}. The SMU patch these readings need "
            "was verified only on P3.00, so live monitoring stays off.",
            version=detected,
        )
        if detected
        else tr(
            "This board did not report its BIOS version. The SMU patch these "
            "readings need was verified only on P3.00, so live monitoring stays off."
        )
    )
    return f"{reason} {tr('The P3.00, Chipset Menu and MeiMeiDXE images on the Firmware page all qualify.')}"


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
    #: Who took the readings on screen: "" for this application's own
    #: session, EXTERNAL_SOURCE when BC250-Telemetry's collector did.
    source: str = ""
    #: BC250-Telemetry's collector: "" when it is not running, otherwise
    #: "active", "waiting" (no valid reading yet), "stale", or "interrupted"
    #: when it stopped in the middle of an SMU operation this boot.
    external_state: str = ""
    #: Cyan, the GPU governor: "" when settled, "starting" or "restarting"
    #: while it may be using the SMU queue these readings go through.
    governor_state: str = ""
    #: Why the helper's last sample held back, when it did.
    blocked_reason: str = ""
    #: The user switched off the SMU channel check in Settings, knowing the
    #: risk: sampling is then allowed while the GPU governor is starting or
    #: BC250-Telemetry's collector is idle. Firmware and interrupted-operation
    #: guards, and every lock, still apply.
    manual_override: bool = False

    @property
    def external_owns_smu(self) -> bool:
        """BC250-Telemetry's collector is running and owns the SMU mailbox."""
        return self.external_state in {"active", "waiting", "stale", "interrupted"}

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
    def channel_blocked(self) -> bool:
        """The SMU channel check holds sampling back right now."""
        return bool(self.governor_state) or self.external_state in {"waiting", "stale"}

    @property
    def can_monitor(self) -> bool:
        """Live sampling needs the patch, and can install it on the way in.

        Never while BC250-Telemetry's collector is publishing (its readings
        are already on screen) or after it was interrupted mid-operation, and
        by default not while the SMU channel check holds back: a second
        sampler on that mailbox is what hangs the SMU. The manual override
        lifts only the channel check.
        """
        if self.external_state in {"active", "interrupted"}:
            return False
        if self.channel_blocked and not self.manual_override:
            return False
        return bool(self.can_read and (self.patch_active or self.can_apply))

    def blocker(self) -> str:
        """The single most useful thing to say about why this is not running.

        The manual override lifts the SMU channel check, so the reasons that
        check gives are no longer what holds the button back. Repeating one
        of them under a button that stays grey sent the user looking in the
        wrong place: on a P2.00 board the answer is the firmware.
        """
        if self.external_state == "interrupted":
            return _EXTERNAL_INTERRUPTED
        if not self.manual_override:
            if self.external_state == "waiting":
                return "BC250-Telemetry's memory service is running. Its readings will appear here."
            if self.external_state == "stale":
                return (
                    "BC250-Telemetry's memory service stopped updating its readings. "
                    "Control Center leaves the SMU alone while that service may still "
                    "be using it."
                )
            if self.governor_state == "restarting":
                return _GOVERNOR_RESTARTING
            if self.governor_state == "starting":
                return _GOVERNOR_STARTING
        if not self.hardware_detected:
            return "No BC-250 hardware was detected on this machine."
        if not self.repository_ready:
            return "The reviewed upstream checkout is not prepared yet."
        if not (self.reader_ready and self.helper_ready):
            return "Reinstall BC250 Control Center to install the privileged helpers."
        if not self.firmware_supported:
            return firmware_blocker(self.bios_version)
        if not self.patch_active:
            return (
                "The runtime SMU patch is not active. It lives in volatile SMU RAM, "
                "so it has to be applied again after every full power cycle."
            )
        return ""

    def notice(self) -> str:
        """The one sentence to show under the devices, or "" for none."""
        if self.chips:
            return ""
        if self.manual_override and self.channel_blocked and self.can_monitor:
            return (
                "Manual mode: the SMU channel check is off. Readings can hang the "
                "board while Cyan starts."
            )
        if self.blocked_reason == "GDDR6_GOVERNOR_UNSETTLED":
            return _GOVERNOR_RESTARTING if self.governor_state == "restarting" else _GOVERNOR_STARTING
        for code, message in _SESSION_ERRORS:
            if code in self.error:
                return message
        return "" if self.can_monitor else self.blocker()


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
        self._manual_override = False

    # ------------------------------------------------------------------ state

    @property
    def reading(self) -> Gddr6Reading:
        return self._reading

    def _backend(self, name: str):
        """The GDDR6 workflow is optional; an older backend simply has none."""
        return getattr(self.controller, name, None)

    def _rebuild(self) -> None:
        status, sample = self._state.status, self._state.sample
        external = _dict(status.get("external"))
        external_state = str(external.get("state") or "")
        source = str(sample.get("source") or "")
        # A session's own samples win while they arrive; between sessions the
        # collector's published reading is what there is to show.
        if not sample.get("chips") and not self._live and external_state == "active":
            sample = external
            source = EXTERNAL_SOURCE
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
            patch_active=bool(sample.get("patch_active") or external_state == "active"),
            chips=chips,
            average_c=_number(sample["average_c"]) if "average_c" in sample else None,
            hotspot_c=_number(sample["hotspot_c"]) if "hotspot_c" in sample else None,
            hotspot_chip=int(_number(hotspot_chip)) if hotspot_chip is not None else None,
            sampled_at=str(sample.get("sampled_at") or ""),
            error=str(sample.get("error") or ""),
            busy=self._live,
            live=self._live,
            source=source,
            external_state=external_state,
            governor_state=str(
                sample.get("governor_state") or status.get("governor_state") or ""
            ),
            blocked_reason=str(sample.get("blocked_reason") or ""),
            manual_override=self._manual_override,
        )
        self.changed.emit(self._reading)

    # ---------------------------------------------------------------- override

    @property
    def manual_override(self) -> bool:
        return self._manual_override

    def set_manual_override(self, enabled: bool) -> None:
        """The Settings switch: sample even when the SMU channel check says wait."""
        enabled = bool(enabled)
        if enabled == self._manual_override:
            return
        self._manual_override = enabled
        self._rebuild()

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
        reading = self._reading
        if reading.external_state in {"active", "interrupted"} or (
            reading.channel_blocked and not self._manual_override
        ):
            # BC250-Telemetry is sampling the same mailbox, or the GPU
            # governor is starting on it: a session now would only race them.
            self._rebuild()
            return
        operation = self._backend("comando_monitorizar_vram")
        if operation is None:
            return
        try:
            if self._manual_override:
                command = [str(item) for item in (operation(ignore_governor=True) or [])]
            else:
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
