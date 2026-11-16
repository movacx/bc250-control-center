"""Offline, declarative support handbook shared by every frontend.

Entries describe reported issues, not individual reports. Several entries may
share a diagnostic code: a code-only lookup must keep all candidates.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

CATALOG_PATH = Path(__file__).with_name("known_errors.json")
FAMILIES = ("arch", "steamos", "bazzite", "fedora", "ubuntu", "debian", "other")
_FAMILY_ALIASES = {
    "cachyos": "arch", "manjaro": "arch", "endeavouros": "arch", "garuda": "arch",
    "mint": "ubuntu", "linuxmint": "ubuntu", "pop": "ubuntu", "zorin": "ubuntu",
    "nobara": "fedora", "silverblue": "bazzite", "kinoite": "bazzite",
    "aurora": "bazzite", "bluefin": "bazzite", "unsupported": "other",
}


def normalize(text: object) -> str:
    value = unicodedata.normalize("NFKD", str(text or "").casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(re.sub(r"[\W_]+", " ", value).split())


def localized(value: dict, language: str = "en") -> str:
    """Long-form content has Spanish and English; other locales use English."""
    key = "es" if str(language).startswith("es") else "en"
    return str(value.get(key) or value.get("en") or "")


@lru_cache(maxsize=1)
def catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def load() -> tuple[dict, ...]:
    return tuple(catalog()["entries"])


def modules() -> tuple[dict, ...]:
    return tuple(catalog()["modules"])


def for_id(identity: str) -> dict | None:
    key = normalize(identity).replace(" ", "")
    return next((entry for entry in load() if normalize(entry["id"]).replace(" ", "") == key), None)


def _code_matches(query: str, code: str) -> bool:
    def parts(value: str):
        match = re.fullmatch(r"(?:bc250)?([a-z]+)0*(\d+)", normalize(value).replace(" ", ""))
        return (match[1], int(match[2])) if match else None

    return parts(query) is not None and parts(query) == parts(code)


def for_code(code: str) -> tuple[dict, ...]:
    return tuple(entry for entry in load() if any(_code_matches(code, item) for item in entry["codes"]))


def _message_matches(entry: dict, text: str) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in entry["match"])


def for_message(text: str) -> tuple[dict, ...]:
    """Recognise the actual message before consulting its historical code."""
    matched = tuple(entry for entry in load() if _message_matches(entry, text))
    if matched:
        return matched
    codes = re.findall(r"BC250-[A-Z0-9]+-\d{3}", text, re.IGNORECASE)
    return tuple(entry for entry in load() if any(entry in for_code(code) for code in codes))


def search(text: str, language: str = "en", *, module: str = "") -> tuple[dict, ...]:
    """Search all supported languages, independently of the interface locale."""
    return tuple(match.entry for match in search_matches(text, module=module))


def search_matches(text: str, *, module: str = "") -> tuple:
    """Include short match explanations without changing the entry-only API."""
    from .known_errors_search import matches

    return matches(text, module=module)


def search_suggestions(text: str, *, module: str = "") -> tuple[str, ...]:
    from .known_errors_search import suggestions

    return suggestions(text, module=module)


def family_for(distro_family: str) -> str:
    value = str(distro_family).lower()
    return _FAMILY_ALIASES.get(value, value if value in FAMILIES else "other")


def fix_for(entry: dict, distro_family: str) -> dict | None:
    """An explicit non-applicable fix stays None; never borrow another backend."""
    return entry["fix"].get(family_for(distro_family))


def needs_update(entry: dict, installed: str) -> bool:
    def version(value: str) -> tuple[int, ...]:
        return tuple(int(part) for part in re.findall(r"\d+", value))

    return bool(entry.get("fixed_in")) and version(entry["fixed_in"]) > version(installed)
