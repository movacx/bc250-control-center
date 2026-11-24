"""The BIOS this computer runs now, as its firmware reports it through DMI.

World-readable and cheap. DMI cannot tell a modded P3.00 from the stock one:
both report "P3.00". :func:`identify_installed_bios` adds what else the
running system gives away without root, and says which of it it used.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from bc250cc.shared.paths import state_root

DMI_ROOT = Path("/sys/class/dmi/id")
EFIVARS_ROOT = Path("/sys/firmware/efi/efivars")

# The VRAM carve-out is deliberately not evidence: the CMOS UMA_SIZE write
# (fanoush/bc250_memcfg, and this application's VRAM setting) sets any size
# on ASRock's own P3.00 and P5.00, so a large VRAM says nothing about which
# image is flashed. Nor are eight running cores: the SMU core unlock and its
# EFI shim bring them back on stock firmware too.
#: Where the firmware page notes the kit it last wrote.
KIT_RECORD_NAME = "firmware-kit.json"


@dataclass(frozen=True)
class BoardFirmware:
    board: str = ""
    vendor: str = ""
    version: str = ""
    date: str = ""

    @property
    def is_bc250(self) -> bool:
        return "bc-250" in self.board.lower() or "bc250" in self.board.lower()


@dataclass(frozen=True)
class InstalledBios:
    """What is known about the firmware image the board runs."""

    #: As DMI reports it: "P3.00".
    version: str = ""
    #: "ASRock", "Chipset Menu", "MeiMeiDXE v3", or "" when DMI's version is
    #: shared by images nothing here can tell apart.
    variant: str = ""
    #: The catalog family, when the variant is known.
    family: str = ""
    #: One sentence: how the variant was told, or why it could not be.
    evidence: str = ""


def _read(root: Path, name: str) -> str:
    try:
        return (root / name).read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return ""


def read_board_firmware(root: Path = DMI_ROOT) -> BoardFirmware:
    return BoardFirmware(
        board=_read(root, "board_name") or _read(root, "product_name"),
        vendor=_read(root, "bios_vendor"),
        version=_read(root, "bios_version"),
        date=_read(root, "bios_date"),
    )


def _major(version: str) -> str:
    """"P3.00", "p3.0" and "P3" are the same release: "P3"."""
    text = str(version or "").strip().upper()
    return text.split(".", 1)[0]


def kit_record_path() -> Path:
    return state_root() / "bc250-control-center" / KIT_RECORD_NAME


def record_prepared_kit(family: str, version: str, board_version: str, path: Path | None = None) -> None:
    """Note the image a USB was just prepared with, and the BIOS seen then.

    If DMI later reports the kit's version where it reported another one,
    that USB is what was flashed: nothing else changes a BIOS version.
    """
    target = path or kit_record_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"family": str(family), "version": str(version), "seen": str(board_version)}),
        encoding="utf-8",
    )
    os.replace(temporary, target)


def load_prepared_kit(path: Path | None = None) -> dict[str, str]:
    try:
        payload = json.loads((path or kit_record_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {key: str(payload.get(key) or "") for key in ("family", "version", "seen")}


def efi_variable_names(root: Path = EFIVARS_ROOT) -> tuple[str, ...]:
    """The names alone: listing the directory needs no privilege."""
    try:
        return tuple(sorted(entry.name for entry in root.iterdir()))
    except OSError:
        return ()


_STOCK = {
    "P2": ("p2-stock", "ASRock"),
    "P5": ("p5-stock", "ASRock"),
}
_P3_VARIANTS = {
    "p3-stock": "ASRock",
    "p3-chipset-menu": "Chipset Menu",
    "meimeidxe-v3": "MeiMeiDXE v3",
    "bc250-native": "BC250 Native",
}


def identify_installed_bios(
    board: BoardFirmware,
    *,
    efi_variables: tuple[str, ...] = (),
    prepared_kit: dict[str, str] | None = None,
) -> InstalledBios:
    """Name the image as far as the evidence goes, and never further."""
    version = board.version.strip()
    if not version:
        return InstalledBios(evidence="The firmware did not report a BIOS version.")
    major = _major(version)
    if major in _STOCK:
        family, variant = _STOCK[major]
        # No mod is built on these two, so the version alone settles it.
        return InstalledBios(version, variant, family, "Only ASRock publishes this version.")
    if major != "P3":
        return InstalledBios(version, evidence="Not a version any known BC-250 image reports.")

    # MeiMeiDXE v3 keeps its menu in EFI variables of its own, named
    # MeiMeiDXEv3CoreVar, MeiMeiDXEv3SmuUnlockVar... under the vendor GUID
    # 49cc168d-e8b0-4613-a807-16969986726f (read on a flashed board). Their
    # names are world-readable; their contents are not needed.
    # onlinermm's BIOS is MeiMeiDXE plus its own settings variable (GpuForms.vfr),
    # so it is asked about first.
    if any(name.lower().startswith("bc250gpuconfig") for name in efi_variables):
        return InstalledBios(
            version, _P3_VARIANTS["bc250-native"], "bc250-native",
            "The firmware keeps BC250 Native's own settings variable.",
        )
    if any(name.lower().startswith("meimeidxe") for name in efi_variables):
        return InstalledBios(
            version, _P3_VARIANTS["meimeidxe-v3"], "meimeidxe-v3",
            "The firmware keeps MeiMeiDXE's own settings variable.",
        )
    kit = prepared_kit or {}
    if (
        kit.get("family") in _P3_VARIANTS
        and _major(kit.get("version", "")) == "P3"
        and kit.get("seen")
        and _major(kit["seen"]) != "P3"
    ):
        return InstalledBios(
            version, _P3_VARIANTS[kit["family"]], kit["family"],
            "This board changed to P3.00 after this application prepared that USB.",
        )
    return InstalledBios(
        version,
        evidence=(
            "ASRock's P3.00, the Chipset Menu mod and MeiMeiDXE report the same "
            "version, and nothing readable without root tells them apart."
        ),
    )


def read_installed_bios(
    *,
    dmi_root: Path = DMI_ROOT,
    efivars_root: Path = EFIVARS_ROOT,
    kit_path: Path | None = None,
) -> InstalledBios:
    return identify_installed_bios(
        read_board_firmware(dmi_root),
        efi_variables=efi_variable_names(efivars_root),
        prepared_kit=load_prepared_kit(kit_path),
    )
