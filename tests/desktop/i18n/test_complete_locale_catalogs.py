from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from frontends.desktop.i18n import (
    SUPPORTED_LANGUAGES,
    normalize_language,
    project_overview,
    tr,
)
from frontends.desktop.i18n.locale_catalog import COMPLETE_LOCALES, LOCALE_DIRECTORY

PLACEHOLDER_RE = re.compile(r"\{[^{}]+\}")
CORRUPTED_SENTINEL_RE = re.compile(
    r"QAZ|ZXQ|QXZ|XZZ|</?code\b|<[^>]*\bid=[\"']bc\d+[\"'][^>]*>|spantranslate",
    re.I,
)
COMMAND_LINE_RE = re.compile(
    r"(?m:^(?:sudo\s+)?(?:"
    r"systemctl(?:\s+--\S+)*\s+(?:enable|disable|start|stop|restart|status|daemon-reload)"
    r"|journalctl\s+|pacman\s+-|dnf\s+|apt(?:-get)?\s+|rpm-ostree\s+"
    r"|mkinitcpio\s+|dracut(?:\s+|$)|grub\S*\s+|modprobe\s+|cat\s+/"
    r"|VK_DRIVER_FILES=)[^\n]*$)"
)
PROTECTED_NAMES = (
    "BC250", "BC-250", "FSR4", "SMU", "UMR", "TTM", "ZRAM", "ZSWAP", "WGP",
    "PWM", "Cyan", "Oberon", "Decky", "OpenRC", "systemd", "runit",
    "s6-rc", "dinit", "SysVinit", "SteamOS", "Bazzite", "CachyOS",
    "Arch", "Manjaro", "Fedora", "Ubuntu", "Debian", "Podman", "NVMe", "M.2",
)
VISIBLE_CALL_ARGS = {
    "tr": (0,), "tr_format": (0,), "QLabel": (0,), "QPushButton": (0,),
    "QCheckBox": (0,), "QRadioButton": (0,), "QGroupBox": (0,), "QAction": (0,),
    "setText": (0,), "setWindowTitle": (0,), "setPlaceholderText": (0,),
    "setToolTip": (0,), "setTitle": (0,), "InfoDialog": (0, 1),
    "ConfirmDialog": (0, 1), "SectionCard": (0, 1), "RuntimeStat": (0, 1, 2),
    "MetricTile": (0, 1, 2), "StatusLine": (0, 1, 2), "CpuValueField": (0, 1),
    "CpuSummaryItem": (0, 1, 2), "add_header_button": (0,), "set_values": (0, 1),
}
TECHNICAL_VISIBLE_EXEMPT = {
    "-- MHz", "-- RPM", "-- °C | -- MHz", "3500–4200 MHz", "Bazzite", "CPU",
    "GPU -- °C", "GPU · CPU · 40CU · PWM", "GPU · CU · PWM · CPU", "PWM --",
    "PWM -- %", "PWM 2", "bc250-detect --keep", "cyan-skillfish-governor-smu.service",
    "systemd UnitFileState", "{path}: {error}", "{url}: {error}",
}


def _catalog(code: str) -> dict[str, str]:
    return json.loads((LOCALE_DIRECTORY / f"{code}.json").read_text(encoding="utf-8"))


def test_desktop_exposes_exactly_the_thirty_requested_locales_without_arabic():
    assert tuple(COMPLETE_LOCALES) == (
        "en", "es", "es-419", "pt-BR", "pt", "ru", "pl", "de", "fr", "uk",
        "zh-CN", "zh-TW", "ja", "ko", "it", "cs", "tr", "nl", "ro", "hu",
        "bg", "da", "fi", "el", "id", "ms", "no", "sv", "th", "vi",
    )
    assert SUPPORTED_LANGUAGES == set(COMPLETE_LOCALES)
    assert {path.stem for path in LOCALE_DIRECTORY.glob("*.json")} == set(COMPLETE_LOCALES)
    assert not (LOCALE_DIRECTORY / "ar.json").exists()


def test_every_desktop_catalog_has_the_same_complete_nonempty_key_set():
    english = _catalog("en")
    assert len(english) >= 2768
    for code in COMPLETE_LOCALES:
        catalog = _catalog(code)
        assert set(catalog) == set(english), code
        assert all(isinstance(value, str) and value.strip() for value in catalog.values()), code


def test_placeholders_technical_names_and_translation_sentinels_are_intact():
    english = _catalog("en")
    for code in COMPLETE_LOCALES:
        for source, translated in _catalog(code).items():
            assert sorted(PLACEHOLDER_RE.findall(translated)) == sorted(PLACEHOLDER_RE.findall(source)), (code, source)
            assert not CORRUPTED_SENTINEL_RE.search(translated), (code, source, translated)
            for name in PROTECTED_NAMES:
                if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", source):
                    assert name in translated, (code, name, source, translated)
        if code != "en":
            long_english_fallbacks = [
                source for source, translated in _catalog(code).items()
                if translated == source and len(re.findall(r"[A-Za-z]{3,}", source)) >= 4
            ]
            assert len(long_english_fallbacks) <= 5, (code, long_english_fallbacks)
    assert english["Settings"] == "Settings"


def test_platform_scope_label_keeps_product_names_untranslated():
    scopes = ("BC-250 FSR4 V3", "Fedora 44 · GFX1013 · Podman")
    for code in COMPLETE_LOCALES:
        for scope in scopes:
            assert _catalog(code)[scope] == scope, (code, scope)


def test_copyable_shell_commands_are_never_translated():
    english = _catalog("en")
    for code in COMPLETE_LOCALES:
        catalog = _catalog(code)
        for source in english:
            for command in COMMAND_LINE_RE.findall(source):
                assert command.strip() in catalog[source], (code, source, command)


def test_steam_and_regional_language_identifiers_normalize_without_losing_region():
    expected = {
        "Spanish-Latam": "es-419", "es_MX.UTF-8": "es", "pt_BR.UTF-8": "pt-BR",
        "brazilian": "pt-BR", "schinese": "zh-CN", "tchinese": "zh-TW",
        "koreana": "ko", "czech": "cs", "vietnamese": "vi",
    }
    assert {source: normalize_language(source) for source in expected} == expected


def test_opposite_actions_do_not_collapse_to_the_same_translation():
    """Catch logically dangerous catalogs even when their keys are complete."""
    opposite_pairs = (
        ("Install", "Uninstall"),
        ("Enable", "Disable"),
        ("Start", "Stop"),
        ("Apply", "Cancel"),
        ("Install / update", "Uninstall"),
    )
    for code in COMPLETE_LOCALES:
        catalog = _catalog(code)
        for positive, negative in opposite_pairs:
            if positive not in catalog or negative not in catalog:
                continue
            assert catalog[positive].casefold().strip() != catalog[negative].casefold().strip(), (
                code,
                positive,
                negative,
            )


def test_new_locale_runtime_paths_use_catalogs_for_dialogs_and_long_form_copy():
    for code in COMPLETE_LOCALES:
        assert tr("Settings", code).strip()
        assert project_overview(code).strip()
        if code != "en":
            assert tr("Settings", code) != "Settings"
            assert project_overview(code) != project_overview("en")


def test_reviewed_exact_translation_precedes_the_english_disk_fallback():
    # This key was intentionally added after the generated locale snapshots;
    # it guards the runtime ordering used during incremental catalog updates.
    assert tr("Available only on plain Arch Linux or CachyOS", "es") == (
        "Disponible solo en Arch Linux puro o CachyOS"
    )


def test_every_literal_visible_in_the_desktop_widget_tree_is_catalogued():
    english = _catalog("en")
    view_root = Path("frontends/desktop")
    missing: set[str] = set()
    visible_keywords = {
        "title", "message", "body", "detail", "confirm_text", "cancel_text",
        "eyebrow", "button_text", "notice", "description", "status",
        "info_title", "info_message",
    }
    for path in view_root.rglob("*.py"):
        if "i18n" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
            candidates = [node.args[index] for index in VISIBLE_CALL_ARGS.get(name, ()) if index < len(node.args)]
            candidates.extend(keyword.value for keyword in node.keywords if keyword.arg in visible_keywords)
            for candidate in candidates:
                if not isinstance(candidate, ast.Constant) or not isinstance(candidate.value, str):
                    continue
                source = candidate.value.strip()
                if (
                    re.search(r"[A-Za-z]{3}", source)
                    and source not in english
                    and source not in TECHNICAL_VISIBLE_EXEMPT
                    and not source.startswith(("/", ":/"))
                ):
                    missing.add(source)
    assert missing == set()
