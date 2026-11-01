"""The unprivileged status of the system setup helper on SteamOS."""

from __future__ import annotations

import pathlib
import sys

LIB = pathlib.Path(__file__).resolve().parents[2] / "privileged" / "lib"
sys.path.insert(0, str(LIB))

import system_setup_common as common  # noqa: E402
import system_setup_kernel_args as kernel_args  # noqa: E402


def test_a_root_only_steamos_boot_menu_does_not_break_the_status(monkeypatch):
    # The SteamOS report: "[Errno 13] Permission denied: /efi/EFI/steamos/
    # grub.cfg" took the whole status down and locked every memory control.
    original = pathlib.Path.stat

    def stat(self, *args, **kwargs):
        if str(self).startswith("/efi/EFI/steamos"):
            raise PermissionError(13, "Permission denied", str(self))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "stat", stat)
    assert kernel_args._steamos_menu_present(common.Host()) is True


def test_every_status_section_is_isolated():
    helper = (LIB.parent / "helpers" / "bc250-system-setup-helper").read_text(encoding="utf-8")
    for name in ("memory_section", "acpi.status", "telemetry.status", "kernel_args.status",
                 "vram.status", "ttm.status"):
        assert f"section(lambda: {name}" in helper or f"section({name})" in helper, name


def test_python314_is_file_cannot_hide_an_unreadable_efi_menu(monkeypatch):
    """3.14 returns False from is_file on EACCES; stat must preserve the cause."""
    original_stat = pathlib.Path.stat
    original_is_file = pathlib.Path.is_file

    def stat(self, *args, **kwargs):
        if str(self) == kernel_args.STEAMOS_GRUB_OUTPUT:
            raise PermissionError(13, "Permission denied", str(self))
        return original_stat(self, *args, **kwargs)

    def is_file(self):
        if str(self) == kernel_args.STEAMOS_GRUB_OUTPUT:
            return False
        return original_is_file(self)

    monkeypatch.setattr(pathlib.Path, 'stat', stat)
    monkeypatch.setattr(pathlib.Path, 'is_file', is_file)
    assert kernel_args._steamos_menu_present(common.Host()) is True


def test_a_missing_efi_menu_still_disables_boot_management(tmp_path):
    assert kernel_args._steamos_menu_present(common.Host(tmp_path)) is False
