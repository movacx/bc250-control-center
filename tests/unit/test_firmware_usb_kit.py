"""The files and UEFI shell scripts that go on a BIOS update USB.

The scripts run on the board with nothing else to catch a mistake, so the
properties that keep a flash recoverable are pinned here: the current BIOS is
saved before anything is written, the first backup is never overwritten, the
flash command is exactly the publisher's, and every line is plain ASCII the
shell reads the way it was written.
"""

from __future__ import annotations

import hashlib
import re

import pytest

from bc250cc.domain.firmware.catalog import (
    FAMILIES_BY_KEY,
    FIRMWARE_FAMILIES,
    UEFI_SHELL,
    FirmwareFamily,
    FirmwareImage,
    RemoteFile,
)
from bc250cc.domain.firmware.usb_kit import KIT_FOLDER, VOLUME_LABEL, plan_kit

STAMP = "2026-09-24 10:30, BC250 Control Center"
SHELL_SYNTAX = set('#%^"<>|')


def _plan(key: str = "p3-chipset-menu", image: str | None = None):
    family = FAMILIES_BY_KEY[key]
    return plan_kit(family, family.image(image), prepared=STAMP)


def _script(plan, path: str) -> str:
    item = next(item for item in plan.files if item.path == path)
    assert item.content is not None
    return item.content.decode("ascii")


def _lines(plan, path: str) -> list[str]:
    return _script(plan, path).split("\r\n")


def test_the_kit_layout_boots_from_the_removable_media_path():
    plan = _plan()
    assert [item.path for item in plan.files] == [
        "EFI/BOOT/BOOTX64.EFI",
        "startup.nsh",
        "BC250/MENU.NSH",
        "BC250/FLASH.NSH",
        "BC250/BACKUP.NSH",
        "BC250/RESTORE.NSH",
        "BC250/README.TXT",
        "BC250/TOOLS/AfuEfix64.efi",
        "BC250/FIRMWARE/BC250_3.00_CHIPSETMENU.ROM",
    ]
    assert plan.folders == ("BC250/BACKUP",)
    assert plan.rom_path == "BC250/FIRMWARE/BC250_3.00_CHIPSETMENU.ROM"
    assert plan.downloads[0] is UEFI_SHELL
    assert len(VOLUME_LABEL) <= 11 and VOLUME_LABEL.isupper()


def test_total_bytes_counts_downloads_and_scripts():
    plan = _plan()
    assert plan.total_bytes == sum(item.size for item in plan.files)
    assert plan.total_bytes > sum(source.size for source in plan.downloads)


@pytest.mark.parametrize("family", FIRMWARE_FAMILIES, ids=lambda family: family.key)
def test_every_script_is_ascii_with_crlf_and_no_stray_shell_syntax(family):
    plan = plan_kit(family, family.image(), prepared=STAMP)
    for item in plan.files:
        if item.content is None:
            continue
        text = item.content.decode("ascii")
        assert text.endswith("\r\n")
        assert "\n" not in text.replace("\r\n", "")
        if not item.path.endswith(".nsh") and not item.path.endswith(".NSH"):
            continue
        for line in text.split("\r\n"):
            if line.lstrip().startswith("#"):
                continue  # a comment line
            if line.lstrip().startswith("echo "):
                inner = line.lstrip()[len('echo "'):-1]
                assert not set(inner) & SHELL_SYNTAX, (item.path, line)
                continue
            assert not set(line) & SHELL_SYNTAX, (item.path, line)


def test_startup_finds_the_kit_on_any_mapped_drive():
    text = _script(_plan(), "startup.nsh")
    for index in range(10):
        assert f"if exist fs{index}:\\BC250\\MENU.NSH then" in text
    assert text.count("MENU.NSH\r\n") >= 10
    assert text.rstrip().endswith(":done")


def test_flash_saves_the_current_bios_before_writing_the_new_one():
    lines = _lines(_plan(), "BC250/FLASH.NSH")
    tool = "\\BC250\\TOOLS\\AfuEfix64.efi"
    backup = "\\BC250\\BACKUP\\BACKUP.ROM"
    save = lines.index(f"{tool} {backup} /O")
    verify = lines.index(f"if not exist {backup} then")
    flash = next(index for index, line in enumerate(lines) if line.startswith(f"{tool} \\BC250\\FIRMWARE\\"))
    assert save < verify < flash
    # A missing backup jumps past the flash instead of falling through to it.
    assert lines[verify + 3] == "  goto done"
    assert lines.index(":done") > flash


def test_flash_never_overwrites_the_first_backup():
    lines = _lines(_plan(), "BC250/FLASH.NSH")
    backup = "\\BC250\\BACKUP\\BACKUP.ROM"
    keep = lines.index(f"if exist {backup} then")
    assert lines[keep + 2] == "  goto install"
    assert keep < lines.index(f"\\BC250\\TOOLS\\AfuEfix64.efi {backup} /O")
    assert ":install" in lines


def test_flash_asks_before_writing_and_switches_off_at_the_end():
    lines = _lines(_plan(), "BC250/FLASH.NSH")
    flash = next(index for index, line in enumerate(lines) if "\\BC250\\FIRMWARE\\" in line and line.startswith("\\"))
    assert "pause" in lines[:flash]
    assert lines[flash + 1:].count("reset -s") == 1


@pytest.mark.parametrize(
    "key, arguments, clears",
    [
        ("p3-chipset-menu", "/p /b /n /k /x /rlc:e", False),
        ("p5-stock", "/p /b /n /k /x /rlc:e", False),
        ("meimeidxe-v3", "/P /B /N /K /RLC:E /CLRCFG", True),
    ],
)
def test_the_flash_command_is_the_publishers_own(key, arguments, clears):
    plan = _plan(key)
    rom = plan.image.rom.name
    flash = _script(plan, "BC250/FLASH.NSH")
    restore = _script(plan, "BC250/RESTORE.NSH")
    assert f"\\BC250\\TOOLS\\AfuEfix64.efi \\BC250\\FIRMWARE\\{rom} {arguments}\r\n" in flash
    assert f"\\BC250\\TOOLS\\AfuEfix64.efi \\BC250\\BACKUP\\BACKUP.ROM {arguments}\r\n" in restore
    readme = _script(plan, "BC250/README.TXT")
    if clears:
        assert "resets the BIOS settings by itself" in readme
        assert "Power it on again" in flash
    else:
        assert "clear CMOS" in readme
        assert "no picture" in readme
        assert "NO PICTURE until the CMOS is cleared" in flash
        assert "remove the CMOS battery for a minute" in flash


def test_the_cmos_warning_comes_before_the_key_that_switches_the_board_off():
    lines = _lines(_plan("p5-stock"), "BC250/FLASH.NSH")
    warning = next(index for index, line in enumerate(lines) if "NO PICTURE" in line)
    flash = next(index for index, line in enumerate(lines) if "\\BC250\\FIRMWARE\\" in line and line.startswith("\\"))
    pause = lines.index("pause", flash)
    assert flash < warning < pause < lines.index("reset -s")


def test_backup_keeps_the_first_copy_and_writes_latest_after_it():
    text = _script(_plan(), "BC250/BACKUP.NSH")
    assert "if exist \\BC250\\BACKUP\\BACKUP.ROM then" in text
    assert "\\BC250\\TOOLS\\AfuEfix64.efi \\BC250\\BACKUP\\LATEST.ROM /O" in text
    assert "\\BC250\\TOOLS\\AfuEfix64.efi \\BC250\\BACKUP\\BACKUP.ROM /O" in text


def test_restore_refuses_without_a_backup():
    lines = _lines(_plan(), "BC250/RESTORE.NSH")
    guard = lines.index("if not exist \\BC250\\BACKUP\\BACKUP.ROM then")
    assert lines[guard + 2] == "  goto done"
    assert lines.index("pause") > guard


def test_the_menu_names_the_image_its_hash_and_the_stamp():
    plan = _plan("meimeidxe-v3", "cachyos")
    menu = _script(plan, "BC250/MENU.NSH")
    assert "P3.00 MeiMeiDXE v3 - CachyOS logo" in menu
    assert plan.image.rom.sha256 in menu
    assert STAMP in menu
    for word in ("flash", "backup", "restore", "menu"):
        assert re.search(rf'echo "\s+{word}\s', menu), word


def test_a_variant_puts_its_own_rom_on_the_usb():
    first = _plan("meimeidxe-v3", "bazzite")
    second = _plan("meimeidxe-v3", "steamos-blackout")
    assert first.rom_path != second.rom_path
    assert first.files[-1].source is first.image.rom


@pytest.mark.parametrize("stamp", ["héllo", "50% done", 'say "hi"', "a|b", "tab\there"])
def test_the_stamp_must_be_plain_text_the_shell_reads_literally(stamp):
    family = FAMILIES_BY_KEY["p3-stock"]
    with pytest.raises(ValueError):
        plan_kit(family, family.image(), prepared=stamp)


def test_unsafe_file_names_are_refused_before_any_script_is_written():
    family = FAMILIES_BY_KEY["p3-stock"]
    rom = RemoteFile(url="https://example.com/x", sha256="0" * 64, size=1, name="BIOS ROM.bin")
    image = FirmwareImage(key="bad", label="bad", rom=rom)
    tampered = FirmwareFamily(**{**family.__dict__, "images": (image,)})
    with pytest.raises(ValueError, match="Unsafe file name"):
        plan_kit(tampered, image, prepared=STAMP)


def test_the_kit_folder_is_what_the_guide_tells_people_to_type():
    assert KIT_FOLDER == "BC250"


# ------------------------------------------------------- custom boot logo

LOGO = b"\xff\xd8 a picture \xff\xd9"


def _logo_plan(key: str = "p3-chipset-menu", image: str | None = None):
    family = FAMILIES_BY_KEY[key]
    return plan_kit(family, family.image(image), prepared=STAMP, logo=LOGO)


def test_a_logo_kit_downloads_the_published_image_and_marks_it_for_the_logo():
    plan = _logo_plan()
    rom = plan.files[-1]
    assert rom.path == plan.rom_path == "BC250/FIRMWARE/LOGO-BC250_3.00_CHIPSETMENU.ROM"
    assert rom.source is FAMILIES_BY_KEY["p3-chipset-menu"].image().rom
    assert rom.logo == LOGO and rom.content is None
    assert plan.logo_pending
    assert plan.downloads[-1] is rom.source


def test_the_finished_logo_kit_carries_the_image_and_names_both_hashes():
    family = FAMILIES_BY_KEY["p3-chipset-menu"]
    finished_rom = bytes(family.image().rom.size)
    plan = _logo_plan().with_logo_rom(finished_rom)
    rom = plan.files[-1]
    assert rom.content == finished_rom and rom.source is None and rom.logo is None
    assert not plan.logo_pending
    assert plan.downloads == (UEFI_SHELL, family.tool.binary)
    digest = hashlib.sha256(finished_rom).hexdigest()
    menu = _script(plan, "BC250/MENU.NSH")
    assert f"SHA-256  : {digest}" in menu
    assert f"Original : {family.image().rom.sha256}" in menu
    assert "P3.00 Chipset Menu - your boot logo" in menu
    assert "\\BC250\\FIRMWARE\\LOGO-BC250_3.00_CHIPSETMENU.ROM" in menu
    flash = _script(plan, "BC250/FLASH.NSH")
    assert "\\BC250\\FIRMWARE\\LOGO-BC250_3.00_CHIPSETMENU.ROM /p /b /n /k /x /rlc:e" in flash
    readme = _script(plan, "BC250/README.TXT")
    assert f"SHA-256:  {digest}" in readme and f"Original: {family.image().rom.sha256}" in readme
    assert "before the boot logo was replaced" in readme


def test_a_logo_replaces_the_variant_in_the_title_but_keeps_its_flasher():
    family = FAMILIES_BY_KEY["meimeidxe-v3"]
    plan = _logo_plan("meimeidxe-v3", "cachyos").with_logo_rom(bytes(family.image().rom.size))
    title = next(line for line in _lines(plan, "BC250/MENU.NSH") if "Firmware :" in line)
    assert title == 'echo "  Firmware : P3.00 MeiMeiDXE v3 - your boot logo"'
    assert "LOGO-BC250_3.00_MeiMeiDXEv3-CachyOS" in _script(plan, "BC250/FLASH.NSH")
    assert "/P /B /N /K /RLC:E /CLRCFG" in _script(plan, "BC250/FLASH.NSH")


@pytest.mark.parametrize("family", FIRMWARE_FAMILIES, ids=lambda family: family.key)
def test_every_logo_script_is_ascii_with_crlf(family):
    plan = plan_kit(family, family.image(), prepared=STAMP, logo=LOGO).with_logo_rom(bytes(family.image().rom.size))
    for item in plan.files:
        if item.path.endswith((".NSH", ".nsh", ".TXT")):
            text = item.content.decode("ascii")
            assert "\n" not in text.replace("\r\n", "")
            # What the shell prints has to fit its console; commands may be longer.
            assert all(len(line) <= 90 for line in text.split("\r\n") if line.lstrip().startswith("echo"))


def test_a_finished_image_needs_its_logo_and_the_original_size():
    family = FAMILIES_BY_KEY["p5-stock"]
    with pytest.raises(ValueError, match="needs its logo"):
        plan_kit(family, family.image(), prepared=STAMP, rom=bytes(family.image().rom.size))
    with pytest.raises(ValueError, match="size of the original"):
        plan_kit(family, family.image(), prepared=STAMP, logo=LOGO, rom=b"short")
    with pytest.raises(ValueError, match="no custom boot logo"):
        plan_kit(family, family.image(), prepared=STAMP).with_logo_rom(bytes(16))
