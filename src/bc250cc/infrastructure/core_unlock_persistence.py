"""Whether an active CPU core unlock will survive the next power off.

The integrated upstream tool writes the core presence mask through the SMU.
Its own README is explicit: "survives warm reboots. a full power off clears
it, so redo after every cold boot." So a machine can be running with 8 cores
and still lose them the next morning, with nothing in the interface saying so.

A community EFI shim (Hexxeh/bc250-efi-core-unlock) applies the same write
before the bootloader and therefore persists. It publishes no release binary
and its NVMe installation rewrites the boot order, so this module only
*detects* it and reports what is in place. It never compiles, writes to a USB
device, or calls efibootmgr: a mistake there leaves the board unbootable and
recoverable only from the BIOS.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# The EFI shim, as documented by its README's two installation paths.
EFI_SHIM_UPSTREAM = "https://github.com/Hexxeh/bc250-efi-core-unlock"
# Verified against the upstream source: the Makefile builds `bc250-unlock.efi`
# and the README installs it either as the USB fallback loader
# (EFI/BOOT/BOOTX64.EFI) or under its own name on the ESP. Users also keep the
# built binary beside the bootloader, so all three spellings are checked.
EFI_SHIM_NAMES = ("COREUNLOCK.EFI", "bc250-unlock.efi")
EFI_SHIM_PATHS = (
    "/boot/EFI/BOOT/COREUNLOCK.EFI",
    "/boot/efi/EFI/BOOT/COREUNLOCK.EFI",
    "/efi/EFI/BOOT/COREUNLOCK.EFI",
    "/boot/EFI/BOOT/bc250-unlock.efi",
    "/boot/efi/EFI/BOOT/bc250-unlock.efi",
    "/efi/EFI/BOOT/bc250-unlock.efi",
)

# The core presence mask the SMU exposes. The runtime tool addresses it as
# 0x5A870 and the EFI shim as 0x0115A870; same register, different bus prefix.
CORE_MASK_STOCK = 0x77   # 6 cores as shipped
CORE_MASK_UNLOCKED = 0xFF  # all 8 cores
# efibootmgr labels the NVMe entry this way in the documented command.
EFI_SHIM_BOOT_LABEL = "CoreUnlock"


@dataclass(frozen=True)
class CoreUnlockPersistence:
    """Read-only evidence about how an active unlock is being maintained."""

    unlocked: bool
    # "efi-shim" persists by itself; "volatile" is lost on a full power off;
    # "stock" means the board is running its factory core count.
    mechanism: str
    survives_power_off: bool
    shim_paths: tuple[str, ...] = ()
    boot_entry_present: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "unlocked": self.unlocked,
            "mechanism": self.mechanism,
            "survives_power_off": self.survives_power_off,
            "shim_paths": list(self.shim_paths),
            "boot_entry_present": self.boot_entry_present,
            "reference_url": EFI_SHIM_UPSTREAM,
        }


def _present(paths, root: Path) -> tuple[str, ...]:
    found = []
    for raw in paths:
        candidate = root / str(raw).lstrip("/")
        try:
            if candidate.is_file():
                found.append(str(raw))
        except OSError:
            continue
    return tuple(found)


def _boot_entry_present(run_command) -> bool:
    """Look for the shim's documented efibootmgr entry, read-only."""
    if run_command is None:
        return False
    try:
        code, stdout, _stderr = run_command(["efibootmgr"], timeout=3)
    except (OSError, RuntimeError, TypeError, ValueError):
        return False
    return code == 0 and EFI_SHIM_BOOT_LABEL.casefold() in (stdout or "").casefold()


def detect_core_unlock_persistence(
    *, physical_cores: int, logical_cpus: int, root: Path | str = "/", run_command=None,
) -> dict[str, object]:
    """Classify how an active core unlock is being kept, without changing it."""
    base = Path(root)
    unlocked = physical_cores >= 8 and logical_cpus >= 16
    shim_paths = _present(EFI_SHIM_PATHS, base)
    boot_entry = _boot_entry_present(run_command)
    has_shim = bool(shim_paths) or boot_entry

    if not unlocked:
        mechanism, survives = "stock", True
    elif has_shim:
        mechanism, survives = "efi-shim", True
    else:
        # Unlocked with no persistent mechanism in place: the mask was written
        # this boot and a full power off reverts it.
        mechanism, survives = "volatile", False

    return CoreUnlockPersistence(
        unlocked=unlocked,
        mechanism=mechanism,
        survives_power_off=survives,
        shim_paths=shim_paths,
        boot_entry_present=boot_entry,
    ).to_dict()
