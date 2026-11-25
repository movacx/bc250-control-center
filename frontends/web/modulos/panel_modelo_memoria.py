"""Modelo pasivo GDDR6 del escritorio, separado de su motor QObject.

Las condiciones y textos se conservan de core/gddr6_monitor.py. Este módulo
solo interpreta disponibilidad: no inicia procesos ni lee el equipo.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from frontends.tui.i18n import tr, tr_format

#: How long one authenticated live session lasts, in seconds. Enforced by the
#: helper itself; this copy is only so the interface can say so. When it ends
#: the user presses the button again — nothing stays authenticated.
LIVE_SESSION_SECONDS = 600

#: Where the readings came from when BC250-Telemetry's collector took them.
EXTERNAL_SOURCE = "bc250-telemetry"
#: ...and when the kernel's own bc250_memory driver did (MastaG's kernels).
KERNEL_SOURCE = "bc250_memory"

_EXTERNAL_INTERRUPTED = (
    "BC250-Telemetry's memory service stopped in the middle of an SMU "
    "operation this boot. Power the board off completely before reading "
    "memory temperature again."
)
_GOVERNOR_STARTING = (
    "The GPU governor is starting, and while it starts it uses the same SMU "
    "queue as these readings. They resume once it is running."
)
_PATCH_EXISTING = (
    "The BIOS or another program already installed a memory temperature patch. Control Center neither "
    "replaces it nor reads through it, because it can hang. BC250-Telemetry can show its readings."
)
_PATCH_UNKNOWN = (
    "The SMU already has a memory-temperature patch this version does not "
    "recognise, or one that did not finish installing. Power the board off "
    "completely before reading memory temperature again."
)
_KERNEL_NO_SENSOR = (
    "The kernel's bc250_memory driver is loaded but publishes no memory "
    "temperatures. Check it with: sensors bc250_memory-*"
)
_NO_CHIP_ANSWERED = (
    "No memory chip answered, so live monitoring stopped. Try again later; if "
    "it keeps happening, power the board off completely."
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
    ("GDDR6_PATCH_EXISTING", _PATCH_EXISTING),
    ("GDDR6_PATCH_UNKNOWN", _PATCH_UNKNOWN),
    ("GDDR6_NO_CHIP_ANSWERED", _NO_CHIP_ANSWERED),
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


def _helper_error_line(error: str) -> str:
    """The helper's own "ERROR: ..." line, without the prefix, else the text."""
    lines = [line.strip() for line in str(error or "").splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith("ERROR:"):
            return line.removeprefix("ERROR:").strip()
    return lines[-1] if lines else ""


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
    #: The chip's MR3 code; None when the source has none (the kernel driver
    #: publishes temperatures only), so nothing reads "MR3 0x00".
    code: int | None = 0
    temperature_c: float = 0.0


@dataclass(frozen=True)
class Gddr6Reading:
    """Everything known about the GDDR6 interface right now."""

    hardware_detected: bool = False
    repository_ready: bool = False
    #: The official clone is there but at an earlier reviewed revision.
    repository_outdated: bool = False
    #: The kernel's bc250_memory driver owns the SMU patch: readings come from
    #: its sensors, nothing is patched and no checkout is needed.
    kernel_driver: bool = False
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
    #: Chips that did not answer the last sample: the payload gave up on
    #: them instead of waiting forever, and they are left out of ``chips``.
    unanswered_chips: tuple[int, ...] = ()
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
            and not self.kernel_driver
        )

    @property
    def can_read(self) -> bool:
        """A single read is allowed as soon as the reader is installed.

        It is also how the patch state is discovered: the reader reports it in
        the same round trip, so nothing has to spend a prompt just to ask.
        """
        return bool(
            self.hardware_detected
            and (self.repository_ready or self.kernel_driver)
            and self.reader_ready
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
        return bool(
            self.can_read and (self.patch_active or self.can_apply or self.kernel_driver)
        )

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
        if not self.repository_ready and not self.kernel_driver:
            if self.repository_outdated:
                return (
                    "This version uses a newer reviewed release of the memory-temperature "
                    "tool. Press Prepare readings to update the checkout."
                )
            return "The reviewed upstream checkout is not prepared yet."
        if not (self.reader_ready and self.helper_ready):
            return "Reinstall BC250 Control Center to install the privileged helpers."
        if not self.firmware_supported and not self.kernel_driver:
            return firmware_blocker(self.bios_version)
        if not self.patch_active:
            return (
                "The runtime SMU patch is not active. It lives in volatile SMU RAM, "
                "so it has to be applied again after every full power cycle."
            )
        return ""

    def unanswered_notice(self) -> str:
        """Which chips the last sample had to leave out, or ""."""
        if not self.unanswered_chips:
            return ""
        if len(self.unanswered_chips) == 1:
            return tr_format(
                "Chip {chip} did not answer this time. The other chips are shown.",
                chip=self.unanswered_chips[0],
            )
        return tr_format(
            "Chips {chips} did not answer this time. The other chips are shown.",
            chips=", ".join(str(chip) for chip in self.unanswered_chips),
        )

    def notice(self) -> str:
        """The one sentence to show under the devices, or "" for none."""
        if self.chips:
            return self.unanswered_notice()
        if self.manual_override and self.channel_blocked and self.can_monitor:
            return (
                "Manual mode: the SMU channel check is off. Readings can hang the "
                "board while Cyan starts."
            )
        if self.blocked_reason == "GDDR6_GOVERNOR_UNSETTLED":
            return _GOVERNOR_RESTARTING if self.governor_state == "restarting" else _GOVERNOR_STARTING
        if self.blocked_reason == "GDDR6_PATCH_EXISTING":
            return _PATCH_EXISTING
        if self.blocked_reason == "GDDR6_PATCH_UNKNOWN":
            return _PATCH_UNKNOWN
        if self.blocked_reason == "GDDR6_KERNEL_DRIVER_NO_SENSOR":
            return _KERNEL_NO_SENSOR
        for code, message in _SESSION_ERRORS:
            if code in self.error:
                return message
        if self.error:
            # A failure without a friendlier wording is still the answer: an
            # empty strip under a button that went back to off says nothing.
            return _helper_error_line(self.error)
        return "" if self.can_monitor else self.blocker()


