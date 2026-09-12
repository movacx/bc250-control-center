from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QLabel

from frontends.desktop.components.widgets import InfoDialog
from frontends.desktop.core.error_diagnostics import (
    diagnose_error,
    format_error_for_user,
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
