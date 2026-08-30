from pathlib import Path

import pytest

from frontends.desktop.i18n import normalize_language, tr


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        ("es-419", "es-419"),
        ("es_MX.UTF-8", "es"),
        ("latam", "es-419"),
        ("spanish-latam", "es-419"),
        ("pt-BR", "pt-BR"),
        ("pt_BR.UTF-8", "pt-BR"),
        ("brazilian", "pt-BR"),
        ("brazilian portuguese", "pt-BR"),
        ("russian", "ru"),
        ("ukrainian", "uk"),
        ("german", "de"),
        ("polish", "pl"),
    ),
)
def test_regional_and_steam_language_identifiers_use_supported_fallbacks(source, expected):
    assert normalize_language(source) == expected


def test_regional_fallback_resolves_the_same_dialog_copy_as_its_base_language():
    source = "Application update could not start"
    assert tr(source, "es-419") == tr(source, "es")
    assert tr(source, "pt-BR") == tr(source, "pt")


def test_quick_access_normalizes_spanish_steam_identifiers():
    plugin = Path(__file__).resolve().parents[3] / "integrations/decky/bc250-quick-access"
    source = (plugin / "src/i18n.ts").read_text(encoding="utf-8")
    bundle = (plugin / "dist/index.js").read_text(encoding="utf-8")
    for identifier in ("latam", "spanish", "spanish-latam"):
        assert identifier in source
        assert identifier in bundle
    assert 'base === "es"' in source
