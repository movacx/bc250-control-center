"""The TV and the receiver, driven by hand through cecd.

cecd (Valve's CEC daemon, see ``hdmi_cec``) exports every CEC adapter on the
user's D-Bus. This module asks it for what a remote control does: wake the
TV, put it in standby, take the input, wake the receiver, change its volume.
Nothing here needs a terminal or a password, and nothing writes a file.

The calls are the ones keyboardspecialist/bc250-steamos's bc250-cec.sh sends
(public domain), which its author checked against real TVs and receivers.
CEC fixes a few logical addresses by specification: 0 is the TV and 5 the
audio system. cecd reports the audio system's real address when it learned
one (255, or 0 before it did, means none), and 5 stands in for it otherwise.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .hdmi_cec import BUS_NAME, DAEMON_PATH, adapters

DEVICE_INTERFACE = f"{BUS_NAME}.CecDevice1"
TV = 0
AUDIO_SYSTEM = 5
BUS_TIMEOUT_S = 5
#: A call that waits for the receiver to answer can take a few seconds.
RUN_TIMEOUT_S = 20.0

#: <Give Device Power Status> and its reply; <System Audio Mode Request> and
#: its reply; <User Control Pressed> keys (HDMI-CEC 1.4, table 27).
GIVE_POWER_STATUS, REPORT_POWER_STATUS = 143, 144
SYSTEM_AUDIO_MODE_REQUEST, SET_SYSTEM_AUDIO_MODE = 112, 114
KEY_POWER_ON = 109

ACTIONS = ("tv-on", "tv-off", "switch", "amp-on", "amp-off", "volume-up", "volume-down", "mute")
POWER = {"0": "on", "1": "standby", "2": "waking", "3": "going-to-standby"}

#: Runs one command and returns (exit status, stdout); tests replace it.
Runner = Callable[[Sequence[str]], "tuple[int, str]"]


@dataclass(frozen=True)
class Result:
    """What an action did. ``code`` says which message to show; ``detail`` adds a fact."""

    ok: bool
    code: str
    detail: str = ""


def _run(argv: Sequence[str]) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            list(argv), capture_output=True, text=True, timeout=RUN_TIMEOUT_S, check=False,
            env={**os.environ, "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return completed.returncode, completed.stdout.strip()


def device_path(adapter: str) -> str:
    """``cec0`` is exported as ``/com/steampowered/CecDaemon1/Devices/Cec0``."""
    return f"/com/steampowered/CecDaemon1/Devices/Cec{adapter.removeprefix('cec') or '0'}"


def _busctl(*args: str) -> list[str]:
    return ["busctl", "--user", f"--timeout={BUS_TIMEOUT_S}", *args]


class TvControl:
    """One CEC adapter's remote control, through cecd."""

    def __init__(self, adapter: str | None = None, *, runner: Runner = _run, adapter_list: Sequence[str] | None = None):
        found = list(adapter_list) if adapter_list is not None else adapters()
        self.adapter = adapter or (found[0] if found else "")
        self._run = runner

    # ---------------------------------------------------------- plumbing

    def _call(self, method: str, *args: str) -> tuple[int, str]:
        return self._run(_busctl("call", BUS_NAME, device_path(self.adapter), DEVICE_INTERFACE, method, *args))

    def _property(self, name: str) -> str:
        """The value of a device property with its type letter removed; ``""`` when unreadable."""
        status, out = self._run(_busctl("get-property", BUS_NAME, device_path(self.adapter), DEVICE_INTERFACE, name))
        if status != 0 or not out:
            return ""
        return out.partition(" ")[2].strip().strip('"')

    def daemon_running(self) -> bool:
        """cecd answers; it is D-Bus activatable, so asking also starts it."""
        status, _out = self._run(_busctl("call", BUS_NAME, DAEMON_PATH, "org.freedesktop.DBus.Peer", "Ping"))
        return status == 0

    def audio_address(self) -> int:
        """The receiver's logical address: what cecd learned, else the one the specification fixes."""
        value = self._property("AudioLogicalAddress")
        return int(value) if value.isdigit() and 1 <= int(value) <= 14 else AUDIO_SYSTEM

    def physical_address(self) -> int | None:
        value = self._property("PhysicalAddress")
        if not value.isdigit() or int(value) == 0xFFFF:
            return None
        return int(value)

    def power(self, logical: int) -> str:
        """``on``, ``standby``, ``waking``, ``going-to-standby``, ``unknown`` or ``no-reply``."""
        status, out = self._call(
            "SendReceiveRawMessage", "ayyyq", "1", str(GIVE_POWER_STATUS), str(logical),
            str(REPORT_POWER_STATUS), "1500",
        )
        if status != 0:
            return "no-reply"
        return POWER.get(out.split(" ")[-1], "unknown")

    # ------------------------------------------------------------ actions

    def _ready(self) -> Result | None:
        if not self.adapter:
            return Result(False, "no-adapter")
        if shutil.which("busctl") is None:
            return Result(False, "no-busctl")
        if not self.daemon_running():
            return Result(False, "no-daemon")
        return None

    def run(self, action: str) -> Result:
        if action not in ACTIONS:
            raise ValueError(f"Unsupported TV control action: {action or '--'}")
        not_ready = self._ready()
        if not_ready is not None:
            return not_ready
        handler = {
            "tv-on": self._tv_on,
            "tv-off": self._tv_off,
            "switch": self._switch,
            "amp-on": self._amp_on,
            "amp-off": self._amp_off,
            "volume-up": lambda: self._audio("VolumeUp"),
            "volume-down": lambda: self._audio("VolumeDown"),
            "mute": lambda: self._audio("Mute"),
        }[action]
        return handler()

    @staticmethod
    def _sent(status: int) -> Result:
        return Result(status == 0, "sent" if status == 0 else "failed")

    def _tv_on(self) -> Result:
        # Wake powers the TV on and switches its input to this computer.
        return self._sent(self._call("Wake")[0])

    def _tv_off(self) -> Result:
        return self._sent(self._call("Standby", "y", str(TV))[0])

    def _switch(self) -> Result:
        # -1 asks cecd to claim the input at this adapter's own physical address.
        return self._sent(self._call("SetActiveSource", "i", "--", "-1")[0])

    def _audio(self, method: str) -> Result:
        return self._sent(self._call(method, "y", str(self.audio_address()))[0])

    def _amp_off(self) -> Result:
        return self._sent(self._call("Standby", "y", str(self.audio_address()))[0])

    def _amp_on(self) -> Result:
        """<System Audio Mode Request> with this adapter's address: a receiver in standby wakes and takes the audio."""
        address = self.physical_address()
        if address is None:
            return Result(False, "no-address")
        logical = self.audio_address()
        status, out = self._call(
            "SendReceiveRawMessage", "ayyyq", "3", str(SYSTEM_AUDIO_MODE_REQUEST),
            str((address >> 8) & 255), str(address & 255), str(logical), str(SET_SYSTEM_AUDIO_MODE), "2000",
        )
        if status == 0:
            return Result(True, "amp-awake", "on" if out.split(" ")[-1] == "1" else "off")
        # A receiver that skips the reply: the remote's discrete power-on key.
        status, _out = self._call("PressOnceUserControl", "ayy", "1", str(KEY_POWER_ON), str(logical))
        return self._sent(status)

    # ------------------------------------------------------------- status

    def status(self) -> dict:
        """What the owner needs to see before pressing anything."""
        if not self.adapter:
            return {"adapter": "", "daemon": False, "tv": "", "receiver": "", "address": ""}
        daemon = self.daemon_running()
        if not daemon:
            return {"adapter": self.adapter, "daemon": False, "tv": "", "receiver": "", "address": ""}
        address = self.physical_address()
        return {
            "adapter": self.adapter,
            "daemon": True,
            "tv": self.power(TV),
            "receiver": self.power(self.audio_address()),
            "address": "" if address is None else physical_address_text(address),
        }


def physical_address_text(address: int) -> str:
    """CEC writes a physical address as four hex digits: 13312 is 3.4.0.0."""
    return ".".join(f"{(address >> shift) & 15:x}" for shift in (12, 8, 4, 0))
