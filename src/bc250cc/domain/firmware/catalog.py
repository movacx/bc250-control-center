"""The BIOS images Control Center can put on an update USB.

Every file is pinned twice: to one upstream commit, so its address never moves
under us, and to its SHA-256, so what reaches the USB is byte for byte the file
that was reviewed. None of it is redistributed by this project. Each image is
downloaded from the repository that published it, and that repository is
credited next to it in the interface.

Sources, as reviewed in September 2026:

* TuxThePenguin0/bc250-bios (GitLab): stock P3.00 and the Chipset Menu mod.
  The mod is the one the community documentation recommends, and its hash
  matches the one that documentation publishes.
* ASRock's own "4U12G BIOS Update" kit, mirrored by kenavru/BC-250: the AFU
  flash tool, the official P5.00 image ("Robin5.00") and the flash command the
  kit itself uses.
* kenavru/BC-250: the P2.00 image the earliest boards shipped with.
* Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script: the UEFI
  Shell 2.2 the kit boots, and MeiMeiDXE v3 (P3.00 with all eight cores
  unlocked) in sixteen boot-logo variants, with the newer AFU and the command
  that project flashes them with.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Union

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PINNED_COMMIT = re.compile(r"/[0-9a-f]{40}/")

#: Every BC-250 BIOS image is one 16 MiB SPI flash dump.
ROM_BYTES = 16 * 1024 * 1024
#: A card lists at most this many: three rows of two.
MAX_HIGHLIGHTS = 6


@dataclass(frozen=True)
class RemoteFile:
    """One file downloaded as it is published."""

    url: str
    sha256: str
    size: int
    name: str


@dataclass(frozen=True)
class ArchivedFile:
    """One file taken out of a published archive."""

    archive: RemoteFile
    member: str
    sha256: str
    size: int
    name: str

    @property
    def archive_format(self) -> str:
        return "7z" if self.archive.name.lower().endswith(".7z") else "zip"


Source = Union[RemoteFile, ArchivedFile]


@dataclass(frozen=True)
class FlashTool:
    """The flasher an image is installed with, and exactly how.

    ``arguments`` follow the ROM path on the AFU command line. They are the
    ones each image's own publisher uses, never a blend of the two.
    """

    key: str
    binary: Source
    arguments: str
    #: /CLRCFG resets the saved BIOS settings as part of the flash, so the
    #: board does not need its CMOS cleared by hand afterwards.
    clears_settings: bool


@dataclass(frozen=True)
class FirmwareImage:
    key: str
    #: The variant's name inside its family ("CachyOS logo"); for a family of
    #: one image it is never shown.
    label: str
    rom: Source


@dataclass(frozen=True)
class FirmwareFamily:
    key: str
    title: str
    version: str
    #: "modded" or "stock".
    origin: str
    summary: str
    caution: str
    tool: FlashTool
    images: tuple[FirmwareImage, ...]
    project: str
    project_url: str
    recommended: bool = False
    #: What the images of a multi-image family differ in, for its selector.
    variant_title: str = ""
    default_image: str = ""
    #: What flashing it changes, in the terms the page compares images by.
    #: Read from the images themselves, not from their descriptions: the
    #: Chipset Menu and MeiMeiDXE v3 carry the same unlocked Setup module.
    vram_menu: bool = False
    #: CPU cores running after the flash. The die has eight; ASRock ships six.
    cpu_cores: int = 6
    #: Boot logos to choose from; 0 keeps the one the image came with.
    boot_logos: int = 0
    #: A custom boot logo can be put into its images: their DXE region was
    #: read and matches, file for file, the layout ``boot_logo`` rebuilds.
    #: Set only after checking the real images, never by assumption.
    logo_replaceable: bool = False
    #: What the image offers beyond the four facts, one short line each.
    #: Read from the images (their drivers, menu strings and build dates) and
    #: from their publishers' own documentation, never from reputation.
    highlights: tuple[str, ...] = ()

    @property
    def has_variants(self) -> bool:
        return len(self.images) > 1

    def image(self, key: str | None = None) -> FirmwareImage:
        wanted = key or self.default_image or self.images[0].key
        for image in self.images:
            if image.key == wanted:
                return image
        return self.images[0]


# ------------------------------------------------------------------ sources

_TUX = "https://gitlab.com/TuxThePenguin0/bc250-bios/-/raw/309a13b6ec8a1da79499f7305dc5519f570463ec"
_KENAVRU = "https://raw.githubusercontent.com/kenavru/BC-250/73dd0bbaaeb16c53acd75995771aeb38253f124d"
_FORBIDDEN_DARKNESS = (
    "https://raw.githubusercontent.com/Forbidden-Darkness/"
    "AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script/7aa9f4ba3b91fde8a160039450d274ac5c0eb6e0"
)

#: EDK2 UEFI Shell 2.2. It is what the USB boots into, and it runs the kit's
#: scripts; the shell in ASRock's kit is an older EFI 1.x build.
UEFI_SHELL = RemoteFile(
    url=f"{_FORBIDDEN_DARKNESS}/EFI/BOOT/BOOTX64.EFI",
    sha256="8204279f882fba62611179bc7e141a4613c0bb3016078d84d89416727a6010ee",
    size=1204224,
    name="BOOTX64.EFI",
)

ASROCK_KIT = RemoteFile(
    url=f"{_KENAVRU}/4U12G%20BIOS%20Update.zip",
    sha256="b3a5b1b3f60b02d5d9f55406072b56227cdb95187d6bc3ed6d1f6d8626506308",
    size=3851992,
    name="4U12G BIOS Update.zip",
)

MEIMEIDXE_ARCHIVE = RemoteFile(
    url=f"{_FORBIDDEN_DARKNESS}/Firmware/Firmware.7z",
    sha256="e754a635de8dcbb919c9bf1a9b0ee6c2b487989c966879e9d878800a58aff63e",
    size=17197600,
    name="Firmware.7z",
)

ASROCK_AFU = FlashTool(
    key="afu-asrock",
    binary=ArchivedFile(
        archive=ASROCK_KIT,
        member="4U12G BIOS Update/BIOS EFI/AfuEfix64.efi",
        sha256="1f01ee07c5b0160fc0442eae871c054265e009be00a3b71cbed6baee508578f4",
        size=569072,
        name="AfuEfix64.efi",
    ),
    # Verbatim from the kit's own Flash.nsh.
    arguments="/p /b /n /k /x /rlc:e",
    clears_settings=False,
)

MEIMEIDXE_AFU = FlashTool(
    key="afu-meimeidxe",
    binary=RemoteFile(
        url=f"{_FORBIDDEN_DARKNESS}/EFI/BOOT/AfuEfix64.efi",
        sha256="a21bab5c87e80676d06b44716a93251f9961316ab6ad4d242b3b247586120d9a",
        size=629680,
        name="AfuEfix64.efi",
    ),
    # Verbatim from that project's menu.nsh.
    arguments="/P /B /N /K /RLC:E /CLRCFG",
    clears_settings=True,
)


def _meimeidxe(key: str, label: str, member: str, sha256: str) -> FirmwareImage:
    return FirmwareImage(
        key=key,
        label=label,
        rom=ArchivedFile(
            archive=MEIMEIDXE_ARCHIVE,
            member=f"Firmware/{member}",
            sha256=sha256,
            size=ROM_BYTES,
            name=member,
        ),
    )


# ----------------------------------------------------------------- families

FIRMWARE_FAMILIES: tuple[FirmwareFamily, ...] = (
    FirmwareFamily(
        key="p3-chipset-menu",
        title="P3.00 Chipset Menu",
        version="P3.00",
        origin="modded",
        summary=(
            "ASRock's P3.00 with its hidden Chipset menu opened, so the VRAM size "
            "is chosen in the BIOS. The one most boards run."
        ),
        caution="",
        tool=ASROCK_AFU,
        images=(
            FirmwareImage(
                key="p3-chipset-menu",
                label="P3.00 Chipset Menu",
                rom=RemoteFile(
                    url=f"{_TUX}/BC250_3.00_CHIPSETMENU.ROM",
                    sha256="48fbe5d366e6a56e2fdffdca848426216ba1f083610dab63db89d2f4e6c940b5",
                    size=ROM_BYTES,
                    name="BC250_3.00_CHIPSETMENU.ROM",
                ),
            ),
        ),
        project="TuxThePenguin0/bc250-bios",
        project_url="https://gitlab.com/TuxThePenguin0/bc250-bios",
        recommended=True,
        vram_menu=True,
        logo_replaceable=True,
        highlights=(
            "VRAM from 256 MB to 12 GB, set in the BIOS",
            "Built on ASRock's P3.00 of December 2021",
            "The community's most tested BIOS",
            "MeiMeiDXE v3 is built on it",
        ),
    ),
    FirmwareFamily(
        key="meimeidxe-v3",
        title="P3.00 MeiMeiDXE v3",
        version="P3.00",
        origin="modded",
        summary=(
            "The Chipset Menu BIOS plus the two CPU cores the factory switched "
            "off, with its own core menu and a boot logo of your choice."
        ),
        caution=(
            "Cores disabled at the factory can make some boards unstable once "
            "unlocked. If yours is, flash the Chipset Menu BIOS instead."
        ),
        tool=MEIMEIDXE_AFU,
        images=(
            _meimeidxe("bc250", "BC250 logo (white)", "BC250_3.00_MeiMeiDXEv3-BC250",
                       "8338bf61b70d706d2376e5e9a9702a894ad7855f9932f5a39b4a8336e6256b49"),
            _meimeidxe("no-logo", "No boot logo", "BC250_3.00_MeiMeiDXEv3",
                       "606a7a7f9ef8fb1c445d8ccfa9640de0339bfec5ab52969135a9e87d62028182"),
            _meimeidxe("bazzite", "Bazzite logo", "BC250_3.00_MeiMeiDXEv3-BazziteOS",
                       "1dabc7e7aa798b0d2f5bfcc0ba42bb4de137237b1196f85ff7d59ecc7651ff99"),
            _meimeidxe("cachyos", "CachyOS logo", "BC250_3.00_MeiMeiDXEv3-CachyOS",
                       "a745e468d9a67e347100520c80f06d9d40a9455ef304b00dce75747f68a48958"),
            _meimeidxe("steam", "Steam logo", "BC250_3.00_MeiMeiDXEv3-SteamOS.M",
                       "481aa7746c8c4a71001bf20b7b1e0769b6b704bb6cca2dd61b0fe913b1aab49f"),
            _meimeidxe("steam-large", "Steam logo, large", "BC250_3.00_MeiMeiDXEv3-SteamOS.XL",
                       "2b69dc329f857b273af826fc8a1788e63b210f981670d534ebabafc19622773e"),
            _meimeidxe("steam-wordmark", "Steam wordmark", "BC250_3.00_MeiMeiDXEv3-SteamOS_Name",
                       "be91847ad624904f6bd5da0c0025fb22e2d4928b85850167ed03c25650c9c574"),
            _meimeidxe("steam-logo-wordmark", "Steam logo and wordmark",
                       "BC250_3.00_MeiMeiDXEv3-SteamOS_LG+N",
                       "b0d0906527288dcbdd9eddd613c876f160c1e41c1998505ff9b4cf5f38e75e0b"),
            _meimeidxe("steam-glass", "Steam text, glass", "BC250_3.00_MeiMeiDXEv3-SteamOS_Name.GB",
                       "e90b96985168da46aaa186271e54d25f23034e54cfd4ce99e290a026be001238"),
            _meimeidxe("steam-frost", "Steam text, frost", "BC250_3.00_MeiMeiDXEv3-SteamOS_Name.FST",
                       "62d89864733055986112f2c0f60963a34cebda0e8751e252104fcdce4f3de39f"),
            _meimeidxe("steamos-blackout", "SteamOS BlackOut", "BC250_3.00_MeiMeiDXEv3-SteamOS-BlackOut",
                       "7c636c8fe043b383d17881655eefb78a92cd4a0fbdc5b7ae0fb2bbdf8d77dee6"),
            _meimeidxe("steamos-blackout-2", "SteamOS BlackOut 2",
                       "BC250_3.00_MeiMeiDXEv3-SteamOS-BlackOut.2",
                       "202b98b202e25a2a5137b0506ced30032661486c0ea22f56a0a91537a52f9e38"),
            _meimeidxe("amd", "AMD logo", "BC250_3.00_MeiMeiDXEv3-AMD",
                       "7253be0e4610a9f6b4ec8e32037ace7f93503904314c0d5e498ffe3bedb51c9f"),
            _meimeidxe("amd-white", "AMD logo (white)", "BC250_3.00_MeiMeiDXEv3-AMD.PW",
                       "df0f6e3bbb034193f52dc95b7425108f6da6cdc2eaaf3dda9933a5c317f2cd99"),
            _meimeidxe("atari", "Atari logo", "BC250_3.00_MeiMeiDXEv3-Atari",
                       "b2ee8afc67fd881f3999c30adaf4372cef04f44f7f28151197b798ff1940d30d"),
            _meimeidxe("weyland", "Weyland logo", "BC250_3.00_MeiMeiDXEv3-Weyland",
                       "a6397f9250c5b439b988369652f125c558781ba2ba560d596d7832daa15df987"),
        ),
        project="Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script",
        project_url="https://github.com/Forbidden-Darkness/AMD-BC-250-UEFI-v2.2-Firmware-Menu-Script",
        variant_title="Boot logo",
        default_image="bc250",
        vram_menu=True,
        cpu_cores=8,
        boot_logos=16,
        logo_replaceable=True,
        # Its six drivers (MeiMeiDXEv3_*) and the strings of its own menu.
        highlights=(
            "All 8 CPU cores, or choose which ones run",
            "Cores switched on by the BIOS at every boot",
            "SMU unlock and 8-core reporting patch",
            "ACPI patch: CPU P-states and C-states",
            "Learns the factory cores and can restore them",
            "Its own menu: Advanced › MeiMeiDXEv3 Menu",
        ),
    ),
    FirmwareFamily(
        key="p5-stock",
        title="P5.00 (ASRock)",
        version="P5.00",
        origin="stock",
        summary="ASRock's newest official firmware, from its own update kit. Nothing unlocked.",
        caution="",
        tool=ASROCK_AFU,
        images=(
            FirmwareImage(
                key="p5-stock",
                label="P5.00 (ASRock)",
                rom=ArchivedFile(
                    archive=ASROCK_KIT,
                    member="4U12G BIOS Update/BIOS EFI/Robin5.00",
                    sha256="0d6f136cb120cf3b2de26d5c4d7f255604fdbf4b9442af5ba55419b95b89aa82",
                    size=ROM_BYTES,
                    name="Robin5.00",
                ),
            ),
        ),
        project="ASRock 4U12G BIOS Update (kenavru/BC-250)",
        project_url="https://github.com/kenavru/BC-250",
        logo_replaceable=True,
        # Against P3.00, its SMU driver (AmdNbioSmuV10Dxe) and Bds changed.
        highlights=(
            "Built in May 2022, ASRock's latest",
            "Newer SMU and boot drivers than P3.00",
        ),
    ),
    FirmwareFamily(
        key="p3-stock",
        title="P3.00 (ASRock)",
        version="P3.00",
        origin="stock",
        summary="ASRock's official P3.00, to take a board back to how it left the factory.",
        caution=(
            "A dump from a board after a settings clear, so it may carry that "
            "board's saved UEFI variables."
        ),
        tool=ASROCK_AFU,
        images=(
            FirmwareImage(
                key="p3-stock",
                label="P3.00 (ASRock)",
                rom=RemoteFile(
                    url=f"{_TUX}/BC250_3.00.ROM",
                    sha256="07595ca3aecf8a4caa28a397b5298f3946a1b769f87b16f67adc369c3f69045c",
                    size=ROM_BYTES,
                    name="BC250_3.00.ROM",
                ),
            ),
        ),
        project="TuxThePenguin0/bc250-bios",
        project_url="https://gitlab.com/TuxThePenguin0/bc250-bios",
        logo_replaceable=True,
        highlights=(
            "Built in December 2021",
            "The base of the Chipset Menu and MeiMeiDXE",
        ),
    ),
    FirmwareFamily(
        key="p2-stock",
        title="P2.00 (ASRock)",
        version="P2.00",
        origin="stock",
        summary="The firmware the first boards shipped with. For troubleshooting only.",
        caution="Older than P3.00, with nothing to gain from it unless someone asked you to try it.",
        tool=ASROCK_AFU,
        images=(
            FirmwareImage(
                key="p2-stock",
                label="P2.00 (ASRock)",
                rom=RemoteFile(
                    url=f"{_KENAVRU}/BC250_2.00.bin",
                    sha256="ee6150dfed33bd05ea46063a352549416fdf3f45fa0e5edac2a68ef78d71083c",
                    size=ROM_BYTES,
                    name="BC250_2.00.bin",
                ),
            ),
        ),
        project="kenavru/BC-250",
        project_url="https://github.com/kenavru/BC-250",
        logo_replaceable=True,
        highlights=("Built in November 2021",),
    ),
)

FAMILIES_BY_KEY = {family.key: family for family in FIRMWARE_FAMILIES}
DEFAULT_FAMILY = next(family for family in FIRMWARE_FAMILIES if family.recommended)


def sources_for(family: FirmwareFamily, image: FirmwareImage) -> tuple[Source, ...]:
    """Every file a USB for this image needs, in the order they are fetched."""
    return (UEFI_SHELL, family.tool.binary, image.rom)


def archives_of(source: Source) -> RemoteFile:
    """The published file a source comes out of: itself, or its archive."""
    return source.archive if isinstance(source, ArchivedFile) else source


def catalog_problems() -> list[str]:
    """Everything wrong with the catalog, for the tests that guard it."""
    problems: list[str] = []
    keys: set[str] = set()
    for family in FIRMWARE_FAMILIES:
        if family.key in keys:
            problems.append(f"duplicate family key {family.key}")
        keys.add(family.key)
        if family.origin not in {"modded", "stock"}:
            problems.append(f"{family.key}: unknown origin {family.origin}")
        if not family.project_url.startswith("https://"):
            problems.append(f"{family.key}: project URL is not https")
        image_keys = [image.key for image in family.images]
        if len(set(image_keys)) != len(image_keys):
            problems.append(f"{family.key}: duplicate image keys")
        if family.has_variants and family.default_image not in image_keys:
            problems.append(f"{family.key}: default image is not one of its images")
        if family.boot_logos and family.boot_logos != len(family.images):
            problems.append(f"{family.key}: boot logo count does not match its images")
        if not 6 <= family.cpu_cores <= 8:
            problems.append(f"{family.key}: a BC-250 runs six to eight CPU cores")
        if not 1 <= len(family.highlights) <= MAX_HIGHLIGHTS or not all(
            line.strip() for line in family.highlights
        ):
            problems.append(f"{family.key}: one to {MAX_HIGHLIGHTS} highlights, none of them empty")
        for image in family.images:
            for source in sources_for(family, image):
                problems.extend(_source_problems(f"{family.key}/{image.key}", source))
    if sum(family.recommended for family in FIRMWARE_FAMILIES) != 1:
        problems.append("exactly one family must be recommended")
    return problems


def _source_problems(owner: str, source: Source) -> list[str]:
    problems: list[str] = []
    remote = archives_of(source)
    for label, digest in (("file", source.sha256), ("archive", remote.sha256)):
        if not _SHA256.match(digest):
            problems.append(f"{owner}: {label} SHA-256 is malformed")
    if not remote.url.startswith("https://") or not _PINNED_COMMIT.search(remote.url):
        problems.append(f"{owner}: {remote.url} is not pinned to a commit over https")
    if source.size <= 0 or remote.size <= 0:
        problems.append(f"{owner}: size must be positive")
    if "/" in source.name or "\\" in source.name or not source.name:
        problems.append(f"{owner}: file name {source.name!r} is not a plain name")
    return problems
