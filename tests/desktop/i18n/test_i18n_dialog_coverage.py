"""Regression guard for every literal shown by a desktop dialog."""
from __future__ import annotations

import ast
from pathlib import Path

from frontends.desktop.i18n import translation_coverage

VIEW_ROOT = Path(__file__).resolve().parents[3] / "frontends" / "desktop"
DIALOG_CALLS = {"InfoDialog", "ConfirmDialog", "_show_info"}
DIALOG_KEYWORDS = {
    "title", "message", "body", "detail", "confirm_text", "cancel_text",
    "eyebrow", "button_text", "notice",
}
VISIBLE_CALL_ARGS = {
    "tr": (0,),
    "tr_format": (0,),
    "QLabel": (0,),
    "QPushButton": (0,),
    "QCheckBox": (0,),
    "QRadioButton": (0,),
    "QGroupBox": (0,),
    "QAction": (0,),
    "setText": (0,),
    "setWindowTitle": (0,),
    "setPlaceholderText": (0,),
    "setToolTip": (0,),
    "setTitle": (0,),
    "InfoDialog": (0, 1),
    "ConfirmDialog": (0, 1),
    "SectionCard": (0, 1),
    "RuntimeStat": (0, 1, 2),
    "MetricTile": (0, 1, 2),
    "StatusLine": (0, 1, 2),
}

# Product names, hardware identifiers and compact telemetry formats are not
# natural-language dialog copy. SUPPORT is also the normal German spelling.
LITERAL_EXEMPT = {
    "BC250 Control Center",
    "BC250 Control\nCenter",
    "Bazzite",
    "CPU",
    "CPU / SMU",
    "Decky",
    "GPU · CPU · 40CU · PWM",
    "GPU · CU · PWM · CPU",
    "MHz",
    "PWM 2",
    "SUPPORT",
    "cyan-skillfish-governor-smu.service",
    "systemd UnitFileState",
}


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _literal(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        value = node.value.strip()
        if value and value not in LITERAL_EXEMPT and not value.startswith(("/", ":/")):
            return value
    return None


def _dialog_literals() -> set[str]:
    values: set[str] = set()
    for path in VIEW_ROOT.rglob("*.py"):
        if "i18n" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))

        # Shared dialog calls can appear in any widget or presenter.
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _call_name(node) not in DIALOG_CALLS:
                continue
            for argument in node.args[:2]:
                if value := _literal(argument):
                    values.add(value)
            for keyword in node.keywords:
                if keyword.arg in DIALOG_KEYWORDS and (value := _literal(keyword.value)):
                    values.add(value)

        # Custom QDialog classes have their own labels, buttons and tooltips.
        dialogs = (
            node for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef)
            and any(isinstance(base, ast.Name) and base.id == "QDialog" for base in node.bases)
        )
        for dialog in dialogs:
            for node in ast.walk(dialog):
                if not isinstance(node, ast.Call):
                    continue
                for index in VISIBLE_CALL_ARGS.get(_call_name(node), ()):
                    if index < len(node.args) and (value := _literal(node.args[index])):
                        values.add(value)
    return values


def test_every_desktop_dialog_literal_is_translated_in_complete_languages():
    missing = translation_coverage(_dialog_literals())
    assert missing == {}, "Desktop dialog translation fallback detected: " + repr(missing)
