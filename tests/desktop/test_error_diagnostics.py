from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QLabel

from frontends.desktop.components.widgets import InfoDialog
from frontends.desktop.core.error_diagnostics import (
    diagnose_error,
    format_error_for_user,
    umr_repair_command,
)
from frontends.desktop.i18n import tr


@pytest.mark.parametrize(
    ("message", "context", "code"),
    (
        ("Error opening current controlling terminal (/dev/tty): No such device or address", "GPU", "BC250-AUTH-001"),
        ("The BC-250 repository is already configured outside Control Center", "setup", "BC250-PKG-003"),
        ("Cyan D-Bus is not ready", "GPU", "BC250-DBUS-001"),
        ("QUICK_ACCESS_FAN: PWM 4 read-back failed", "Decky", "BC250-FAN-001"),
        ("UMR WGP verification failed", "Compute Units", "BC250-CU-001"),
        ("bc250-detect stress dependency is missing", "CPU", "BC250-CPU-001"),
        ("Process finished with exit code 65", "setup", "BC250-DATA-001"),
        ("operation timed out", "setup", "BC250-TIMEOUT-001"),
        ("unclassified failure", "GPU GOVERNOR", "BC250-GPU-900"),
        ("unclassified failure", "", "BC250-GENERAL-001"),
    ),
)
def test_low_level_failures_have_stable_specific_diagnostics(message, context, code):
    assert diagnose_error(message, context=context).code == code


def test_formatted_error_keeps_evidence_and_explains_each_section_in_spanish():
    result = format_error_for_user(
        "ERR QUICK_ACCESS_FAN: PWM 3 is unavailable",
        context="FAN CONTROL",
        translate=lambda value: tr(value, "es"),
    )
    assert "Qué ocurrió" in result
    assert "Causa probable" in result
    assert "Cómo corregirlo" in result
    assert "Detalle técnico" in result
    assert "QUICK_ACCESS_FAN: PWM 3 is unavailable" in result
    assert "BC250-FAN-001" in result


def test_diagnostic_strips_terminal_color_and_bounds_untrusted_output():
    result = format_error_for_user("\x1b[31mpermission denied\x1b[0m " + "x" * 3000)
    assert "\x1b" not in result
    assert len(result) < 3000
    assert result.endswith("BC250-PERM-001")


def test_red_info_dialog_uses_the_shared_human_diagnostic(qtbot):
    dialog = InfoDialog(
        "Could not update settings",
        "Cyan D-Bus is not ready",
        tone="red",
        notice="",
    )
    qtbot.addWidget(dialog)
    body = next(label for label in dialog.findChildren(QLabel) if label.objectName() == "DialogBody")
    assert "The GPU governor did not expose its D-Bus controls." in body.text()
    assert "BC250-DBUS-001" in body.text()


UMR_WGP_READ_FAILED = (
    "[ERR ] failed to read cyan_skillfish.gfx1013.mmSPI_PG_ENABLE_STATIC_WGP_MASK with umr. "
    "Set UMR_ASIC to the exact selector if your board differs."
)


@pytest.mark.parametrize(
    "message",
    (
        UMR_WGP_READ_FAILED,
        "umr: error while loading shared libraries: libLLVM.so.22.1: cannot open shared object file: No such file or directory",
        "umr is installed but does not start: a library it needs is missing.",
    ),
)
def test_a_broken_umr_asks_for_a_reinstall_instead_of_the_generic_cu_advice(message):
    assert diagnose_error(message, context="COMPUTE UNITS").code == "BC250-UMR-001"


@pytest.mark.parametrize(
    ("family", "command", "finish"),
    (
        ("cachyos", "paru -S umr-git", "4. Close Control Center"),
        ("ubuntu", "sudo apt install --reinstall -y umr", "tick UMR and press Prepare selected"),
        ("fedora", "sudo dnf reinstall -y umr", "4. Close Control Center"),
        ("bazzite", "sudo rpm-ostree upgrade", "4. Restart the computer"),
    ),
)
def test_umr_steps_name_this_systems_command_and_what_to_do_after(family, command, finish):
    result = format_error_for_user(UMR_WGP_READ_FAILED, os_family=family)
    assert "1. Press Copy command" in result and finish in result
    assert command in umr_repair_command(UMR_WGP_READ_FAILED, os_family=family)


def test_steamos_and_unknown_systems_get_steps_but_no_command_to_paste():
    steamos = format_error_for_user(UMR_WGP_READ_FAILED, os_family="steamos")
    assert "you do not need a terminal" in steamos and "Copy command" not in steamos
    assert "package manager" in format_error_for_user(UMR_WGP_READ_FAILED, os_family="gentoo")
    assert umr_repair_command(UMR_WGP_READ_FAILED, os_family="steamos") == ""
    assert umr_repair_command("Cyan D-Bus is not ready", os_family="cachyos") == ""


def test_umr_dialog_puts_its_copy_button_in_the_footer_where_the_steps_point(qtbot, monkeypatch):
    from PyQt6.QtWidgets import QApplication, QPushButton

    from frontends.desktop.core import error_diagnostics

    monkeypatch.setattr(error_diagnostics, "_os_family", lambda: "cachyos")
    monkeypatch.setattr("frontends.desktop.components.widgets.record_window_error", lambda *a, **k: None)
    dialog = InfoDialog("Compute Units operation failed", UMR_WGP_READ_FAILED, tone="red", notice="")
    qtbot.addWidget(dialog)
    copy = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Copy command")
    copy.click()
    assert QApplication.clipboard().text() == umr_repair_command(UMR_WGP_READ_FAILED, os_family="cachyos")
    assert copy.text() == "Copied"
