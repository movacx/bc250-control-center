from __future__ import annotations

import re

from frontends.desktop.i18n import (
    _EXACT,
    DAEMON_DETAILS,
    LANGUAGE_OPTIONS,
    PROJECT_OVERVIEW,
    SUPPORTED_LANGUAGES,
    count_label,
    normalize_language,
    tr,
    tr_format,
    translate_history_event,
)
from frontends.desktop.i18n.polish_catalog import POLISH_TRANSLATIONS

_PLACEHOLDER = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*(?::[^{}]+)?\}")


def test_polish_is_a_complete_supported_language_option():
    assert ("pl", "Polski") in LANGUAGE_OPTIONS
    assert "pl" in SUPPORTED_LANGUAGES
    assert normalize_language("pl_PL.UTF-8") == "pl"
    assert normalize_language("Polski") == "pl"
    assert normalize_language("Polish") == "pl"
    assert all(mapping.get("pl", "").strip() for mapping in _EXACT.values())


def test_polish_catalog_preserves_format_placeholders():
    mismatches = []
    for source, translated in POLISH_TRANSLATIONS.items():
        if sorted(_PLACEHOLDER.findall(source)) != sorted(_PLACEHOLDER.findall(translated)):
            mismatches.append((source, translated))
    assert mismatches == []


def test_polish_covers_critical_pages_actions_and_dialogs():
    sources = (
        "Dashboard",
        "Compute Units",
        "GPU Governor",
        "Fans",
        "Settings",
        "System health",
        "Run health check",
        "Repair installation",
        "Generate diagnostic report",
        "Restore factory",
        "Prepare dependencies",
        "Unlock hidden CPU cores",
        "Update application",
        "Add point",
        "Remove point",
        "Warning",
        "Error",
        "Confirm",
        "Cancel",
    )
    untranslated = [source for source in sources if tr(source, "pl") == source]
    assert untranslated == []
    assert tr("Compute Units", "pl") == "Jednostki obliczeniowe"


def test_polish_long_safety_messages_and_health_templates_are_localized():
    stale_body = (
        "The installed Compute Units service points to a manager that no longer exists. "
        "The operation was stopped before changing the hardware."
    )
    recovery = (
        "A stale Compute Units boot service points to a missing manager. Copy the recovery command, "
        "run it in a terminal, then reboot. You can also use Restore factory: it removes the stale "
        "service and restores the 24-CU factory topology."
    )
    assert tr(stale_body, "pl") != stale_body
    assert tr(recovery, "pl") != recovery
    rendered = tr_format(
        "Valid TOML; range mode: {mode}; {points} safe-points.",
        "pl",
        mode=tr("custom", "pl"),
        points=8,
    )
    assert rendered == "Poprawny TOML; tryb zakresu: niestandardowy; bezpieczne punkty: 8."


def test_stale_compute_units_recovery_dialog_is_localized_in_every_supported_language():
    sources = (
        "The installed Compute Units service points to a manager that no longer exists. "
        "The operation was stopped before changing the hardware.",
        "A stale Compute Units boot service points to a missing manager. Copy the recovery command, "
        "run it in a terminal, then reboot. You can also use Restore factory: it removes the stale "
        "service and restores the 24-CU factory topology.",
    )
    for language in SUPPORTED_LANGUAGES - {"en"}:
        assert all(tr(source, language) != source for source in sources), language


def test_new_health_repair_messages_are_localized_in_polish():
    sources = (
        "SteamOS compatibility repair started for the running kernel.",
        "Fan PWM driver repair started.",
        "Prepare the optional nct6687 PWM driver when fan control is required.",
    )
    assert all(tr(source, "pl") != source for source in sources)


def test_dual_governor_scale_and_pwm_workflows_are_localized_in_polish():
    sources = (
        "GPU governor backend",
        "Automatic detection",
        "Oberon telemetry limitation",
        "Open BC-250 telemetry compatibility guide",
        "Persistent scale override",
        "Confirm multi-step scale change",
        "Detected estimated VID",
        "PWM channel",
        "Add point",
        "Aggressive",
        "System health",
        "Generate diagnostic report",
    )
    assert all(tr(source, "pl") != source for source in sources)


def test_polish_daemon_help_keeps_commands_literal():
    text = DAEMON_DETAILS["pl"]
    assert "Opcjonalny demon" in text
    assert "systemctl --user enable --now bc250-control-centerd.service" in text
    assert "systemctl --user disable --now bc250-control-centerd.service" in text
    assert "systemctl --user status bc250-control-centerd.service --no-pager" in text
    assert "BC250 Control Center to graficzny interfejs" in PROJECT_OVERVIEW["pl"]


def test_polish_plural_rules_and_dynamic_history_details():
    assert count_label(1, "point", "pl") == "1 punkt"
    assert count_label(2, "point", "pl") == "2 punkty"
    assert count_label(5, "point", "pl") == "5 punktów"
    title, detail = translate_history_event(
        {"titulo": "Fan curve daemon applied", "detalle": "PWM 2 set to 55% (140/255)."},
        "pl",
    )
    assert title == "Demon zastosował krzywą wentylatora"
    assert detail == "PWM 2 ustawiono na 55% (140/255)."
