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
    """The Memory & Video tab may not change swap, zram or zswap policy.

    An earlier Quick Access build shipped a live zram/zswap policy switch
    here; changing swap policy needs a kernel-argument rewrite and a reboot,
    which made it an unreachable, half-working control in Game Mode, and it
    was swept out. Nothing in this plugin may ever call an RPC that writes
    swap, zram or zswap policy, and no in-panel policy picker may return.

    The GPU memory limit (TTM) is the one exception, by the owner's request
    (2026-10): it is a single boot argument with a reboot notice, and the
    panel only reaches it through the desktop's own system-setup helper
    (see test_the_gpu_memory_limit_goes_through_the_desktops_helper).
    """
    interface = (ROOT / "src/index.tsx").read_text(encoding="utf-8")
    main = (ROOT / "main.py").read_text(encoding="utf-8")

    assert "memoryOpen" not in interface
    forbidden_controls = (
        "swapPolicy", "zramPolicy", "zswapPolicy", "MemoryPolicyPicker",
        "SwapPolicySelector",
    )
    assert not any(token in interface for token in forbidden_controls)
    forbidden_writes = (
        "apply_memory", "set_memory", "apply_swap", "set_swap",
        "apply_zram", "set_zram", "apply_zswap", "set_zswap",
        "set_ttm", "memory-policy", "swap-policy", "memory-apply",
    )
    assert not any(token in main for token in forbidden_writes)


def test_the_gpu_memory_limit_goes_through_the_desktops_helper():
    """One implementation, one state: the plugin never writes the limit itself."""
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    helper = (ROOT.parents[2] / "privileged/helpers/bc250-quick-access-helper").read_text(encoding="utf-8")
    assert '"ttm-apply", normalized' in main
    assert "/sys/module/ttm" not in main and "kargs" not in main and "grub" not in main
    assert "SYSTEM_SETUP_HELPER" in helper
    assert '_system_setup_json(["ttm-apply", "--ttm", value]' in helper
    assert "/sys/module/ttm/parameters/pages_limit\").write" not in helper


def test_card_names_and_tags_fit_a_profile_card_in_every_language():
    """A GPU/CPU profile card is about 96 px wide: no unbroken word may outgrow it.

    The tag must stay short too; a long one would cover the name in the corner.
    """
    catalogs = {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in LOCALE_ROOT.glob("*.json")}
    names = ("profileBalanced", "profileGaming", "profileBenchmark",
             "cpuPresetBoardAverage", "cpuPresetMidPoint", "cpuPresetSafeMaximum")
    for language, catalog in catalogs.items():
        for key in names:
            for word in re.split(r"[\s\-]+", catalog[key]):
                assert len(word) <= 12, (language, key, word)
        assert len(catalog["current"]) <= 8, (language, catalog["current"])


def test_every_language_keeps_the_same_placeholders():
    catalogs = {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in LOCALE_ROOT.glob("*.json")}
    english = catalogs["en"]
    for key, value in english.items():
        expected = sorted(re.findall(r"\{[a-zA-Z_]+\}", value))
        for language, catalog in catalogs.items():
            assert sorted(re.findall(r"\{[a-zA-Z_]+\}", catalog[key])) == expected, (language, key)
