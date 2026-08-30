from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

LOCALE_DIRECTORY = Path(__file__).with_name("locales")

COMPLETE_LOCALES = (
    "en", "es", "es-419", "pt-BR", "pt", "ru", "pl", "de", "fr", "uk",
    "zh-CN", "zh-TW", "ja", "ko", "it", "cs", "tr", "nl", "ro", "hu",
    "bg", "da", "fi", "el", "id", "ms", "no", "sv", "th", "vi",
)

REGIONAL_BASE = {
    "es-419": "es",
    "pt-BR": "pt",
}


@lru_cache(maxsize=len(COMPLETE_LOCALES))
def load_locale_catalog(language: str) -> dict[str, str]:
    """Load one immutable-on-disk catalog through a bounded process cache."""
    if language not in COMPLETE_LOCALES:
        return {}
    path = LOCALE_DIRECTORY / f"{language}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(source): str(translated)
        for source, translated in payload.items()
        if isinstance(source, str) and isinstance(translated, str) and translated.strip()
    }


def locale_fallback_chain(language: str) -> tuple[str, ...]:
    """Return regional -> base -> English without duplicate candidates."""
    candidates = (language, REGIONAL_BASE.get(language), "en")
    return tuple(dict.fromkeys(candidate for candidate in candidates if candidate))
