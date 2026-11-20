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


#: Codes that only say "it failed": every workflow prints one of them, so
#: finding one in a message says nothing about which entry applies.
GENERIC_CODES = frozenset({"BC250-GENERAL-001", "BC250-WORKFLOW-001"})
#: A rule whose hit is much shorter than the best one is a loose hint
#: (a sudo prompt, a word) next to a real signature: the signature wins.
_SPECIFICITY_RATIO = 0.6


def _message_matches(entry: dict, text: str) -> bool:
    return _specificity(entry, text) > 0


_ESCAPE_CLASSES = frozenset("dDsSwWbBAZzntr")


def _literal_length(pattern: str) -> int:
    """How many characters a rule insists on, at the least.

    ``.*`` and character classes demand nothing, an alternation demands its
    shortest branch, and an optional piece demands nothing. So
    ``authorization.*(?:cancel|fail)`` is worth 17 and the full sentence
    ``SteamOS write verification needs ...`` is worth all of its letters,
    however long the text a loose rule happens to swallow.
    """

    def sequence(text: str, index: int, stop: str) -> tuple[list[int], int]:
        branches, current, last = [], 0, 0
        while index < len(text) and text[index] not in stop:
            char = text[index]
            atom = 0
            if char == "\\" and index + 1 < len(text):
                atom = 0 if text[index + 1] in _ESCAPE_CLASSES else 1
                index += 2
            elif char == "[":
                index += 1
                if index < len(text) and text[index] == "]":
                    index += 1
                while index < len(text) and text[index] != "]":
                    index += 2 if text[index] == "\\" else 1
                index += 1
            elif char == "(":
                index += 1
                if text.startswith("?:", index) or text.startswith("?=", index) or text.startswith("?!", index):
                    index += 2
                inner, index = sequence(text, index, ")")
                atom = min(inner) if inner else 0
                index += 1
            elif char == "|":
                branches.append(current)
                current, last = 0, 0
                index += 1
                continue
            elif char in "*?":
                current -= last
                last = 0
                index += 1
                if index < len(text) and text[index] in "?+":
                    index += 1
                continue
            elif char == "{":
                close = text.find("}", index)
                close = len(text) - 1 if close < 0 else close
                if text[index + 1:close].split(",")[0].strip() in ("", "0"):
                    current -= last
                last = 0
                index = close + 1
                continue
            elif char in "+^$":
                index += 1
                continue
            elif char == ".":
                index += 1
            else:
                atom = 1
                index += 1
            current += atom
            last = atom
        branches.append(current)
        return branches, index

    branches, _index = sequence(pattern, 0, "")
    return max(0, min(branches))


def _specificity(entry: dict, text: str) -> int:
    """How specific the best of this entry's rules that recognise ``text`` is."""
    best = 0
    for pattern in entry["match"]:
        if re.search(pattern, text, re.IGNORECASE):
            best = max(best, _literal_length(pattern) or 1)
    return best


def for_message(text: str) -> tuple[dict, ...]:
    """Recognise the actual message before consulting its historical code.

    Workflow output is long and repeats the same failure in several words,
    so loose rules hit next to the one that names it. Only the entries whose
    hit is close to the most specific one are kept, most specific first.
    """
    scored = [(score, entry) for entry in load() if (score := _specificity(entry, text))]
    if scored:
        top = max(score for score, _entry in scored)
        kept = [(score, entry) for score, entry in scored if score >= top * _SPECIFICITY_RATIO]
        return tuple(entry for _score, entry in sorted(kept, key=lambda item: -item[0]))
    codes = {code.upper() for code in re.findall(r"BC250-[A-Z0-9]+-\d{3}", text, re.IGNORECASE)}
    codes -= GENERIC_CODES
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
