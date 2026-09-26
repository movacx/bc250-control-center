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

#: ASRock's own Setup hides a UMA option that runs from 32 MB to 2 GB. Only
#: the AMD CBS menu the Chipset Menu mod opens goes past it (up to 12 GB), so
#: a larger carve-out is proof that menu was used.
ASROCK_UMA_MAX_BYTES = 2 * 1024 ** 3
#: The die has eight cores and ASRock leaves six running.
STOCK_CPU_CORES = 6
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
}


def identify_installed_bios(
    board: BoardFirmware,
    *,
    efi_variables: tuple[str, ...] = (),
    vram_total_bytes: int = 0,
    physical_cores: int = 0,
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

    if any("meimei" in name.lower() for name in efi_variables):
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
    if vram_total_bytes > ASROCK_UMA_MAX_BYTES:
        # Both mods open the same CBS menu; MeiMeiDXE is the one that also
        # brings the two factory-disabled cores back.
        if physical_cores > STOCK_CPU_CORES:
            return InstalledBios(
                version, _P3_VARIANTS["meimeidxe-v3"], "meimeidxe-v3",
                "VRAM is set above 2 GB, which only the unlocked AMD CBS menu offers, "
                "and all eight cores are running.",
            )
        return InstalledBios(
            version, _P3_VARIANTS["p3-chipset-menu"], "p3-chipset-menu",
            "VRAM is set above 2 GB, which only the unlocked AMD CBS menu offers.",
        )
    return InstalledBios(
        version,
        evidence=(
            "ASRock's P3.00 and the Chipset Menu mod report the same version, and "
            "with the default VRAM nothing on the running system tells them apart."
        ),
    )


def read_installed_bios(
    *,
    vram_total_bytes: int = 0,
    physical_cores: int = 0,
    dmi_root: Path = DMI_ROOT,
    efivars_root: Path = EFIVARS_ROOT,
    kit_path: Path | None = None,
) -> InstalledBios:
    return identify_installed_bios(
        read_board_firmware(dmi_root),
        efi_variables=efi_variable_names(efivars_root),
        vram_total_bytes=vram_total_bytes,
        physical_cores=physical_cores,
        prepared_kit=load_prepared_kit(kit_path),
    )
