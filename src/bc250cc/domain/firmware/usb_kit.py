"""What goes on a BIOS update USB, and the scripts that drive it at boot.

The USB boots straight into the UEFI shell: \\EFI\\BOOT\\BOOTX64.EFI is the
removable-media boot path every UEFI firmware tries. The shell runs
startup.nsh, which finds the kit folder on whichever drive the firmware
mapped the USB to and shows the kit's menu. From there the user types one
word: ``flash``, ``backup`` or ``restore``.

``flash`` saves the BIOS the board runs now to the USB before anything is
written, refuses to go on if that backup did not land, and never overwrites
the first backup on a second run: that file is the way back.

The scripts are generated rather than shipped so they name the exact image
and flash command the USB was prepared for. They are plain ASCII with CRLF
line ends, like every script known to run on this board's shell, and avoid
the characters the shell gives meaning to.

A kit with a custom boot logo is planned twice. The first plan names the
published image as a download and marks it with the picture to put into it;
once that image is on disk and the logo is in, ``KitPlan.with_logo_rom``
plans again around the finished bytes, so the scripts on the USB name the
file that is really there and its real SHA-256.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .catalog import UEFI_SHELL, FirmwareFamily, FirmwareImage, Source

#: The FAT volume label: at most 11 characters, upper case.
VOLUME_LABEL = "BC250BIOS"
KIT_FOLDER = "BC250"
#: The shell maps removable drives as fs0, fs1, ...; with every internal drive
#: unplugged, as the guides ask, the USB is almost always fs0.
MAPPINGS = tuple(f"fs{index}" for index in range(10))

_SAFE_NAME = re.compile(r"^[A-Za-z0-9._+-]+$")
#: Characters the UEFI shell treats as syntax inside a script line.
_SHELL_SYNTAX = set('#%^"<>|')


@dataclass(frozen=True)
class KitFile:
    """One file on the USB: downloaded (``source``) or written (``content``)."""

    path: str
    source: Source | None = None
    content: bytes | None = None
    #: A JPEG still to be put into ``source`` as its boot logo. A file that
    #: carries one is never written as it is.
    logo: bytes | None = None

    @property
    def size(self) -> int:
        if self.content is not None:
            return len(self.content)
        return self.source.size if self.source is not None else 0


@dataclass(frozen=True)
class KitPlan:
    family: FirmwareFamily
    image: FirmwareImage
    files: tuple[KitFile, ...]
    #: Folders created even when nothing is copied into them yet.
    folders: tuple[str, ...]
    #: The JPEG that replaces the image's boot logo, or None for the image as
    #: it is published.
    logo: bytes | None = None
    prepared: str = ""

    @property
    def downloads(self) -> tuple[Source, ...]:
        return tuple(item.source for item in self.files if item.source is not None)

    @property
    def total_bytes(self) -> int:
        return sum(item.size for item in self.files)

    @property
    def rom_path(self) -> str:
        return f"{KIT_FOLDER}/FIRMWARE/{_rom_name(self.image, self.logo)}"

    @property
    def logo_pending(self) -> bool:
        """The picture still has to be put into the image before anything is written."""
        return any(item.logo is not None for item in self.files)

    def with_logo_rom(self, rom: bytes) -> KitPlan:
        """The same kit around ``rom``, the image with the logo already in it."""
        if self.logo is None:
            raise ValueError("This kit has no custom boot logo.")
        return plan_kit(self.family, self.image, prepared=self.prepared, logo=self.logo, rom=rom)


def _crlf(*lines: str) -> bytes:
    text = "\r\n".join(lines) + "\r\n"
    return text.encode("ascii")


def _echo(text: str) -> str:
    if set(text) & _SHELL_SYNTAX:
        raise ValueError(f"UEFI shell syntax character in: {text!r}")
    return f'echo "{text}"' if text else 'echo " "'


def _dos(path: str) -> str:
    return "\\" + path.replace("/", "\\")


def _image_title(family: FirmwareFamily, image: FirmwareImage, logo: bytes | None = None) -> str:
    # With a custom logo, a variant's label would name the logo it no longer has.
    if logo is not None:
        return f"{family.title} - your boot logo"
    if family.has_variants:
        return f"{family.title} - {image.label}"
    return family.title


def _rom_name(image: FirmwareImage, logo: bytes | None) -> str:
    """A changed image never carries the published file's name."""
    return f"LOGO-{image.rom.name}" if logo is not None else image.rom.name


@dataclass(frozen=True)
class _Rom:
    """The image file as the scripts describe it."""

    name: str
    #: "" while the logo is still to be put in.
    sha256: str
    #: The published image's SHA-256 when this one was made from it.
    original: str = ""


def _startup() -> bytes:
    lines = [
        "@echo -off",
        "# BC250 Control Center - BIOS update kit.",
        "# Finds the kit on whichever drive the firmware mapped this USB to.",
    ]
    for mapping in MAPPINGS:
        lines += [
            f"if exist {mapping}:\\{KIT_FOLDER}\\MENU.NSH then",
            f"  {mapping}:",
            f"  cd \\{KIT_FOLDER}",
            "  MENU.NSH",
            "  goto done",
            "endif",
        ]
    lines += [
        _echo("The BC250 folder was not found on any drive."),
        _echo("Type map -r, switch to the USB drive (for example fs0:),"),
        _echo(f"then type cd {KIT_FOLDER} and then MENU."),
        ":done",
    ]
    return _crlf(*lines)


def _menu(title: str, rom: _Rom, prepared: str) -> bytes:
    rule = "=" * 72
    original = [_echo(f"  Original : {rom.original}")] if rom.original else []
    return _crlf(
        "@echo -off",
        "cls",
        _echo(rule),
        _echo("  BC250 Control Center - BIOS update kit"),
        _echo(rule),
        _echo(f"  Firmware : {title}"),
        _echo(f"  File     : {_dos(f'{KIT_FOLDER}/FIRMWARE/{rom.name}')}"),
        _echo(f"  SHA-256  : {rom.sha256 or 'pending'}"),
        *original,
        _echo(f"  Prepared : {prepared}"),
        _echo(""),
        _echo("  Type one of these words and press Enter:"),
        _echo(""),
        _echo("    flash     Save the current BIOS to this USB, then install the one above"),
        _echo("    backup    Only save the current BIOS to this USB"),
        _echo("    restore   Put back the BIOS saved by the first backup"),
        _echo("    menu      Show this menu again"),
        _echo(""),
        _echo("  Never switch the board off while a command is running."),
        _echo(rule),
    )


def _backup_block(tool: str) -> list[str]:
    backup = _dos(f"{KIT_FOLDER}/BACKUP/BACKUP.ROM")
    return [
        f"if exist {backup} then",
        "  " + _echo("Step 1 of 2: the backup from an earlier run is kept as it is."),
        "  goto install",
        "endif",
        _echo(f"Step 1 of 2: saving the BIOS this board runs now to {backup}"),
        f"{tool} {backup} /O",
        f"if not exist {backup} then",
        "  " + _echo(""),
        "  " + _echo("The backup could not be saved, so nothing was flashed."),
        "  goto done",
        "endif",
        ":install",
    ]


def _after_flash(family: FirmwareFamily) -> list[str]:
    if family.tool.clears_settings:
        next_steps = [_echo("Next the board switches off. Power it on again: its settings were reset.")]
    else:
        # The settings the old BIOS saved stay in the CMOS, and the new one
        # cannot start with them: the board powers on to a black screen. Said
        # before the key press, in a box, because it is the one thing that
        # makes a finished flash look like a dead board.
        rule = "=" * 68
        next_steps = [
            _echo(rule),
            _echo("  IMPORTANT - READ BEFORE PRESSING A KEY"),
            _echo("  The board switches off next. When powered on again it shows"),
            _echo("  NO PICTURE until the CMOS is cleared. That is expected:"),
            _echo("  unplug the power, remove the CMOS battery for a minute,"),
            _echo("  put it back, then power on. The first start can take a"),
            _echo("  minute with a black screen."),
            _echo(rule),
        ]
    return [
        _echo(""),
        _echo("If the tool above finished without an error, the new BIOS is installed."),
        *next_steps,
        _echo("If it reported an error, press q now and type flash to try again,"),
        _echo("or restore to put the saved BIOS back. Do not switch off in between."),
        _echo("Press any key to switch the board off."),
        "pause",
        "reset -s",
    ]


def _flash(family: FirmwareFamily, title: str, rom_name: str) -> bytes:
    tool = _dos(f"{KIT_FOLDER}/TOOLS/{family.tool.binary.name}")
    rom = _dos(f"{KIT_FOLDER}/FIRMWARE/{rom_name}")
    return _crlf(
        "@echo -off",
        "cls",
        _echo(f"BC250 BIOS update - {title}"),
        _echo(""),
        *_backup_block(tool),
        _echo(""),
        _echo("Step 2 of 2: installing the new BIOS. It takes about a minute."),
        _echo("Do not switch the board off or unplug the USB until it has finished."),
        _echo("Press any key to start, or q to cancel."),
        "pause",
        f"{tool} {rom} {family.tool.arguments}",
        *_after_flash(family),
        ":done",
    )


def _backup(family: FirmwareFamily) -> bytes:
    tool = _dos(f"{KIT_FOLDER}/TOOLS/{family.tool.binary.name}")
    first = _dos(f"{KIT_FOLDER}/BACKUP/BACKUP.ROM")
    latest = _dos(f"{KIT_FOLDER}/BACKUP/LATEST.ROM")
    return _crlf(
        "@echo -off",
        "cls",
        f"if exist {first} then",
        "  " + _echo(f"Saving the BIOS this board runs now to {latest}"),
        "  " + _echo("The first backup, BACKUP.ROM, is kept as it is."),
        f"  {tool} {latest} /O",
        "  goto done",
        "endif",
        _echo(f"Saving the BIOS this board runs now to {first}"),
        f"{tool} {first} /O",
        ":done",
        _echo("Keep this USB: the backup lives on it."),
    )


def _restore(family: FirmwareFamily) -> bytes:
    tool = _dos(f"{KIT_FOLDER}/TOOLS/{family.tool.binary.name}")
    first = _dos(f"{KIT_FOLDER}/BACKUP/BACKUP.ROM")
    return _crlf(
        "@echo -off",
        "cls",
        f"if not exist {first} then",
        "  " + _echo("There is no backup on this USB yet, so there is nothing to restore."),
        "  goto done",
        "endif",
        _echo(f"This puts back {first}, the BIOS saved by the first backup."),
        _echo("Do not switch the board off or unplug the USB until it has finished."),
        _echo("Press any key to start, or q to cancel."),
        "pause",
        f"{tool} {first} {family.tool.arguments}",
        _echo(""),
        _echo("If the tool finished without an error, the saved BIOS is back."),
        _echo("Press any key to switch the board off."),
        "pause",
        "reset -s",
        ":done",
    )


def _readme(family: FirmwareFamily, title: str, rom: _Rom, prepared: str) -> bytes:
    settings = (
        "The flash resets the BIOS settings by itself."
        if family.tool.clears_settings
        else "After flashing, clear CMOS: remove the coin battery for a minute.\r\n"
        "   Until then the board shows no picture; that is expected."
    )
    original = [
        f"Original: {rom.original}",
        "          The published image, before the boot logo was replaced.",
        "          Nothing else in the file differs from it.",
    ] if rom.original else []
    return _crlf(
        "BC250 Control Center - BIOS update kit",
        "",
        f"Firmware: {title} ({family.version}, {family.origin})",
        f"File:     {KIT_FOLDER}/FIRMWARE/{rom.name}",
        f"SHA-256:  {rom.sha256 or 'pending'}",
        *original,
        f"Source:   {family.project_url}",
        f"Flasher:  {KIT_FOLDER}/TOOLS/{family.tool.binary.name} {family.tool.arguments}",
        f"Prepared: {prepared}",
        "",
        "How to use it",
        "1. Switch the BC-250 off and unplug its internal drives.",
        "2. Plug this USB in and switch the board on. It starts the UEFI shell",
        "   and shows the kit menu by itself.",
        "3. Type flash and press Enter. The current BIOS is saved to",
        "   BC250/BACKUP/BACKUP.ROM first; nothing is flashed without it.",
        "4. Do not switch the board off while the flash tool runs.",
        f"5. {settings}",
        "",
        "If the menu does not appear: type map -r, then fs0: (or the drive that",
        f"holds the {KIT_FOLDER} folder), cd {KIT_FOLDER}, and MENU.",
        "",
        "Keep this USB: the backup of your previous BIOS lives on it.",
    )


def plan_kit(
    family: FirmwareFamily,
    image: FirmwareImage,
    *,
    prepared: str,
    logo: bytes | None = None,
    rom: bytes | None = None,
) -> KitPlan:
    """Every file for a USB that installs ``image``, in the order they are written.

    ``logo`` is a JPEG to put into the image as its boot logo; ``rom`` is the
    image once it is in. With a logo and no ``rom`` the plan is only good for
    downloading: its image file still has to be made.
    """
    rom_name = _rom_name(image, logo)
    for name in (family.tool.binary.name, rom_name):
        if not _SAFE_NAME.match(name):
            raise ValueError(f"Unsafe file name for a UEFI script: {name!r}")
    if not prepared.isascii() or not prepared.isprintable() or set(prepared) & _SHELL_SYNTAX:
        raise ValueError("The preparation stamp must be plain ASCII text")
    if rom is not None and (logo is None or len(rom) != image.rom.size):
        raise ValueError("A finished image needs its logo and the size of the original")
    if logo is None:
        described = _Rom(rom_name, image.rom.sha256)
        firmware = KitFile(f"{KIT_FOLDER}/FIRMWARE/{rom_name}", source=image.rom)
    elif rom is None:
        described = _Rom(rom_name, "", image.rom.sha256)
        firmware = KitFile(f"{KIT_FOLDER}/FIRMWARE/{rom_name}", source=image.rom, logo=logo)
    else:
        described = _Rom(rom_name, hashlib.sha256(rom).hexdigest(), image.rom.sha256)
        firmware = KitFile(f"{KIT_FOLDER}/FIRMWARE/{rom_name}", content=bytes(rom))
    title = _image_title(family, image, logo)
    folder = KIT_FOLDER
    files = (
        KitFile(f"EFI/BOOT/{UEFI_SHELL.name}", source=UEFI_SHELL),
        KitFile("startup.nsh", content=_startup()),
        KitFile(f"{folder}/MENU.NSH", content=_menu(title, described, prepared)),
        KitFile(f"{folder}/FLASH.NSH", content=_flash(family, title, rom_name)),
        KitFile(f"{folder}/BACKUP.NSH", content=_backup(family)),
        KitFile(f"{folder}/RESTORE.NSH", content=_restore(family)),
        KitFile(f"{folder}/README.TXT", content=_readme(family, title, described, prepared)),
        KitFile(f"{folder}/TOOLS/{family.tool.binary.name}", source=family.tool.binary),
        firmware,
    )
    return KitPlan(
        family=family,
        image=image,
        files=files,
        folders=(f"{folder}/BACKUP",),
        logo=logo,
        prepared=prepared,
    )
