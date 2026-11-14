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

import json
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

# The boot service of movacx/core_unlock_bc250, which Control Center installs.
# Enabled means its WantedBy=sysinit.target link exists: that is exactly what
# `systemctl enable` creates and what its give-up path removes, so a file alone
# (left behind after a give-up) is not counted.
BOOT_SERVICE_UNIT = "/etc/systemd/system/bc250-core-unlock.service"
BOOT_SERVICE_WANTS_LINK = "/etc/systemd/system/sysinit.target.wants/bc250-core-unlock.service"
# World-readable record of what the service did on its last run.
BOOT_SERVICE_STATE = "/var/lib/bc250-core-unlock/state.json"
# Statuses after which the service has disabled itself.
BOOT_SERVICE_STOPPED = frozenset({"gave-up", "refused"})
# Why an installed, enabled service is not doing its job:
#   "outdated": its unit executes the copy under /var/lib directly, which
#       SELinux (Fedora, Bazzite) refuses, so it never ran a line (seen on the
#       maintainer's Bazzite board, 2026-11-13: state.json still "idle");
#   "not-run": the tool recorded neither this boot's run nor an install in it.
BOOT_SERVICE_REPAIR_OUTDATED = "outdated"
BOOT_SERVICE_REPAIR_NOT_RUN = "not-run"
BOOT_ID_PATH = "/proc/sys/kernel/random/boot_id"
CMDLINE_PATH = "/proc/cmdline"
CMDLINE_DISABLE = "bc250.core_unlock=0"


@dataclass(frozen=True)
class CoreUnlockPersistence:
    """Read-only evidence about how an active unlock is being maintained."""

    unlocked: bool
    # "boot-service" and "efi-shim" persist by themselves; "volatile" is lost
    # on a full power off; "stock" means the factory core count.
    mechanism: str
    survives_power_off: bool
    shim_paths: tuple[str, ...] = ()
    boot_entry_present: bool = False
    # The Control Center boot service: unit file present, enabled at boot,
    # and what its last run recorded ("unlocked", "gave-up", ...).
    boot_service_installed: bool = False
    boot_service_enabled: bool = False
    boot_service_status: str = ""
    boot_service_note: str = ""
    boot_service_repair: str = ""

    @property
    def boot_service_active(self) -> bool:
        return (
            self.boot_service_installed
            and self.boot_service_enabled
            and self.boot_service_status not in BOOT_SERVICE_STOPPED
            and not self.boot_service_repair
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "unlocked": self.unlocked,
            "mechanism": self.mechanism,
            "survives_power_off": self.survives_power_off,
            "shim_paths": list(self.shim_paths),
            "boot_entry_present": self.boot_entry_present,
            "boot_service_installed": self.boot_service_installed,
            "boot_service_enabled": self.boot_service_enabled,
            "boot_service_active": self.boot_service_active,
            "boot_service_status": self.boot_service_status,
            "boot_service_note": self.boot_service_note,
            "boot_service_repair": self.boot_service_repair,
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


def _read(base: Path, path: str) -> str:
    try:
        return (base / path.lstrip("/")).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _boot_service_record(base: Path) -> dict[str, str]:
    """String fields of the service's state file; {} when unreadable."""
    try:
        raw = json.loads(_read(base, BOOT_SERVICE_STATE) or "null")
    except ValueError:
        return {}
    if not isinstance(raw, dict):
        return {}
    return {key: value for key, value in raw.items() if isinstance(value, str)}


def _unit_runs_interpreter(unit_text: str) -> bool:
    """The unit starts the tool through a Python interpreter (SELinux-safe)."""
    for line in unit_text.splitlines():
        if line.strip().startswith("ExecStart="):
            command = line.split("=", 1)[1].split()
            return bool(command) and Path(command[0].lstrip("-@!+:")).name.startswith("python")
    return False


def _boot_service_repair(base: Path, record: dict[str, str]) -> str:
    """Which repair an installed, enabled service needs, or '' when none."""
    if not _unit_runs_interpreter(_read(base, BOOT_SERVICE_UNIT)):
        return BOOT_SERVICE_REPAIR_OUTDATED
    if CMDLINE_DISABLE in _read(base, CMDLINE_PATH).split():
        return ""  # skipped on purpose with the escape hatch
    current = _read(base, BOOT_ID_PATH).strip()
    served = {record.get("last_run_boot_id", ""), record.get("installed_boot_id", "")} - {""}
    if current and served and current not in served:
        return BOOT_SERVICE_REPAIR_NOT_RUN
    return ""


def detect_core_unlock_persistence(
    *, physical_cores: int, logical_cpus: int, root: Path | str = "/", run_command=None,
) -> dict[str, object]:
    """Classify how an active core unlock is being kept, without changing it."""
    base = Path(root)
    unlocked = physical_cores >= 8 and logical_cpus >= 16
    shim_paths = _present(EFI_SHIM_PATHS, base)
    boot_entry = _boot_entry_present(run_command)
    has_shim = bool(shim_paths) or boot_entry
    service_installed = bool(_present((BOOT_SERVICE_UNIT,), base))
    wants_link = base / BOOT_SERVICE_WANTS_LINK.lstrip("/")
    try:
        service_enabled = wants_link.is_symlink() or wants_link.exists()
    except OSError:
        service_enabled = False
    state = _boot_service_record(base)
    service_status, service_note = state.get("status", ""), state.get("note", "")
    repair = ""
    if (service_installed and service_enabled
            and service_status not in BOOT_SERVICE_STOPPED):
        repair = _boot_service_repair(base, state)
    record = CoreUnlockPersistence(
        unlocked=unlocked, mechanism="", survives_power_off=False,
        boot_service_installed=service_installed,
        boot_service_enabled=service_enabled,
        boot_service_status=service_status,
        boot_service_repair=repair,
    )

    if not unlocked:
        mechanism, survives = "stock", True
    elif record.boot_service_active:
        mechanism, survives = "boot-service", True
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
        boot_service_installed=service_installed,
        boot_service_enabled=service_enabled,
        boot_service_status=service_status,
        boot_service_note=service_note,
        boot_service_repair=repair,
    ).to_dict()
