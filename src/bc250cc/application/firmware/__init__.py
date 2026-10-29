"""Firmware use cases: what the board runs, which USB drives exist, and the update kit.

The Qt page and the terminal interface both go through here, so neither talks to
udisks or the firmware cache directly.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from bc250cc.domain.firmware.catalog import FirmwareFamily, FirmwareImage
from bc250cc.domain.firmware.usb import UsbDrive
from bc250cc.domain.firmware.usb_kit import plan_kit
from bc250cc.infrastructure.firmware import udisks
from bc250cc.infrastructure.firmware.board import (
    BoardFirmware,
    InstalledBios,
    read_board_firmware,
    read_installed_bios,
    record_prepared_kit,
)
from bc250cc.infrastructure.firmware.preparation import (
    PreparationReport,
    UsbPreparation,
    steps_for,
)
from bc250cc.infrastructure.firmware.store import FirmwareStore
from bc250cc.infrastructure.firmware.usb_devices import list_usb_drives

#: (step, fraction of that step done, detail)
Progress = Callable[[str, float, str], None]


@dataclass(frozen=True, slots=True)
class FirmwareSnapshot:
    board: BoardFirmware
    installed: InstalledBios
    drives: tuple[UsbDrive, ...]


def firmware_snapshot() -> FirmwareSnapshot:
    return FirmwareSnapshot(read_board_firmware(), read_installed_bios(), tuple(list_usb_drives()))


def prepare_update_usb(
    family: FirmwareFamily, image: FirmwareImage, drive: UsbDrive, *, progress: Progress,
    cancelled: Callable[[], bool] = lambda: False,
) -> tuple[PreparationReport, tuple[str, ...]]:
    """Erase ``drive`` and write the update kit for ``image``; return the report and its steps.

    Records which firmware this USB carries, as the desktop page does, so the
    installed BIOS can later be told apart from the other P3.00 images.
    """
    board = read_board_firmware()
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    plan = plan_kit(family, image, prepared=f"{stamp}, BC250 Control Center")
    report = UsbPreparation(FirmwareStore(), udisks.UDisksClient()).run(
        plan, drive, progress=progress, cancelled=cancelled,
    )
    try:
        record_prepared_kit(family.key, family.version, board.version)
    except OSError:
        pass  # the note is a convenience; the USB itself is ready
    return report, steps_for(plan)
