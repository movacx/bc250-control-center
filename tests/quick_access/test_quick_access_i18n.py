from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path("integrations/decky/bc250-quick-access")
LOCALE_ROOT = ROOT / "locales"
QUICK_ACCESS_LOCALES = ("en", "es", "es-419", "pt", "ru", "pl", "de", "uk")
CORRUPTED_SENTINEL_RE = re.compile(r"QAZ|ZXQ|QXZ|XZZ|</?code\b|spantranslate", re.I)


def _catalog(code: str) -> dict[str, str]:
    return json.loads((LOCALE_ROOT / f"{code}.json").read_text(encoding="utf-8"))


def test_quick_access_has_complete_supported_catalogs():
    assert {path.stem for path in LOCALE_ROOT.glob("*.json")} == set(QUICK_ACCESS_LOCALES)
    english = _catalog("en")
    assert len(english) >= 92
    for code in QUICK_ACCESS_LOCALES:
        catalog = _catalog(code)
        assert set(catalog) == set(english), code
        assert all(isinstance(value, str) and value.strip() for value in catalog.values()), code


def test_quick_access_catalogs_have_no_natural_language_english_fallbacks_or_tokens():
    english = _catalog("en")
    for code in QUICK_ACCESS_LOCALES:
        catalog = _catalog(code)
        assert not any(CORRUPTED_SENTINEL_RE.search(value) for value in catalog.values()), code
        if code == "en":
            continue
        fallbacks = [
            key for key, value in catalog.items()
            if value == english[key] and len(re.findall(r"[A-Za-z]{3,}", english[key])) >= 3
        ]
        assert fallbacks == [], (code, fallbacks)


def test_quick_access_runtime_uses_catalogs_and_steam_language_aliases():
    source = (ROOT / "src/i18n.ts").read_text(encoding="utf-8")
    interface = (ROOT / "src/index.tsx").read_text(encoding="utf-8")
    assert '"en" | "es" | "es-419" | "pt" | "ru" | "pl" | "de" | "uk"' in source
    for steam_name in ("english", "spanish", "latam", "brazilian", "russian", "polish", "german", "ukrainian"):
        assert steam_name in source
    assert "LocalizationManager" in source
    assert "GetCurrentLanguage" in source
    assert "isSpanish" not in interface
    assert "const text =" not in interface


def test_built_decky_bundle_contains_every_quick_access_language():
    bundle = (ROOT / "dist/index.js").read_text(encoding="utf-8")
    for code in QUICK_ACCESS_LOCALES:
        catalog = _catalog(code)
        assert catalog["stale"] in bundle, code
        assert catalog["automaticApplyWarning"] in bundle, code


def test_quick_access_keeps_memory_tuning_out_of_the_game_mode_panel():
    interface = (ROOT / "src/index.tsx").read_text(encoding="utf-8")
    helper = Path("privileged/helpers/bc250-quick-access-helper").read_text(
        encoding="utf-8"
    )

    assert 'kind="memory"' not in interface
    assert "memoryOpen" not in interface
    # Keep the passive status keys during rolling upgrades so an older
    # frontend and a newer protected helper remain protocol-compatible.
    assert "memory_runtime_state" in helper
