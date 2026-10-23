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
    original = pathlib.Path.is_file

    def is_file(self):
        if str(self).startswith("/efi/EFI/steamos"):
            raise PermissionError(13, "Permission denied", str(self))
        return original(self)

    monkeypatch.setattr(pathlib.Path, "is_file", is_file)
    assert kernel_args._steamos_menu_present(common.Host()) is True


def test_every_status_section_is_isolated():
    helper = (LIB.parent / "helpers" / "bc250-system-setup-helper").read_text(encoding="utf-8")
    for name in ("memory_section", "acpi.status", "telemetry.status", "kernel_args.status",
                 "vram.status", "ttm.status"):
        assert f"section(lambda: {name}" in helper or f"section({name})" in helper, name
