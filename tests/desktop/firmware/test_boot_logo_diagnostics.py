"""Every way a custom logo can fail is diagnosed as what it is.

The messages are read from the source, not copied here, so a new refusal
added later is covered the day it is written. They reach the diagnosis the
way the preparation reports them: prefixed with "Custom boot logo:".
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from frontends.desktop.core.error_diagnostics import diagnose_error

SOURCES = (
    Path("src/bc250cc/domain/firmware/boot_logo.py"),
    Path("src/bc250cc/infrastructure/firmware/lzma1.py"),
    Path("frontends/desktop/core/boot_logo_image.py"),
)
ERRORS = {"BootLogoError", "Lzma1Error", "LogoImageError"}


def _text(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(part.value if isinstance(part, ast.Constant) else "7" for part in node.values)
    return ""


def _messages() -> list[str]:
    found: list[str] = []
    for path in SOURCES:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id in ERRORS and node.args:
                text = _text(node.args[0])
            elif node.func.id == "_refuse" and len(node.args) == 2:
                where = _text(node.args[0]) or "DXE volume"
                text = f"{where}: {_text(node.args[1])}. This firmware image is not one a logo can be added to."
            else:
                continue
            if text:
                found.append(text)
    return sorted(set(found))


MESSAGES = _messages()


def test_the_messages_are_actually_collected():
    assert len(MESSAGES) > 40


@pytest.mark.parametrize("message", MESSAGES)
def test_every_logo_failure_is_diagnosed_as_a_logo_failure(message):
    for reported in (message, f"Custom boot logo: {message}"):
        assert diagnose_error(reported, context="firmware usb").code == "BC250-FIRMWARE-002", reported


def test_a_download_that_changed_under_the_logo_is_a_verification_failure():
    message = "BC250_3.00.ROM does not match the reviewed file (SHA-256 mismatch)."
    assert diagnose_error(message, context="firmware usb").code == "BC250-FIRMWARE-001"
