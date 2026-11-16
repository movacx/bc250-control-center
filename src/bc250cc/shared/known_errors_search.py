"""Precomputed offline search: entry evidence first, module vocabulary second.

Search aliases help discovery only. They never select a repair automatically;
the error-dialog lookup deliberately continues to use the strict message API.
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from difflib import get_close_matches
from functools import lru_cache
from pathlib import Path

from . import known_errors as handbook

TERMS_PATH = Path(__file__).with_name("known_errors_search.json")
STOP_WORDS = frozenset("""
    a al algo ante como con de del el en es esta este esto la las le lo los me mi
    mis muy no nos o para pero por que se si sin son su sus te tengo tiene un una
    unas uno unos y ya hay ha he the and or of to is are was were be been it its
    in on at for from with without not can cannot could do does did my your this
    that these those an as all get has have i you we will would please
""".split())
_SEMANTIC = {"Módulo", "Español", "Inglés", "Otros idiomas",
             "Errores de escritura y variantes", "Palabras parciales (prefijos)",
             "Textos de la app traducidos (30 idiomas)"}
# Host suffixes are not searchable words: "com" must not match github.com.
_HOST = re.compile(r"\b([\w-]+)\.(?:com|org|net|io|dev|cloud|edu)\b", re.IGNORECASE)
_REFERENCE = re.compile(r"(?:(bc250)\s*)?([a-z]+)\s*(\d+)$")
_ENTRY_ALIASES = {"STOR-01": ("no space left",), "MEM-02": ("no space left",),
                  "VID-03": ("vaapi",), "VID-04": ("vaapi",)}


@dataclass(frozen=True)
class SearchMatch:
    entry: dict
    kind: str
    term: str


def _words(text: str) -> set[str]:
    return set(handbook.normalize(_HOST.sub(r"\1", text)).split()) - STOP_WORDS


@lru_cache(maxsize=1)
def vocabulary() -> dict:
    return json.loads(TERMS_PATH.read_text(encoding="utf-8"))


@dataclass
class _Index:
    entries: dict
    modules: dict
    aliases: dict
    names: dict
    words: dict
    prefixes: dict
    lengths: dict
    patterns: tuple


@lru_cache(maxsize=1)
def _index() -> _Index:
    entries = {entry["id"]: entry for entry in handbook.load()}
    modules, aliases, names = defaultdict(set), defaultdict(set), defaultdict(set)
    words = defaultdict(dict)

    def add(identity: str, text: str, rank: int) -> None:
        compounds = {handbook.normalize(term).replace(" ", "")
                     for term in re.findall(r"\b\w+(?:[-_]\w+)+\b", text)}
        for word in _words(text) | compounds:
            if word == "com":
                continue  # Portuguese connective, not a domain or a symptom.
            words[word][identity] = min(rank, words[word].get(identity, rank))

    for identity, entry in entries.items():
        modules[entry["module"]].add(identity)
        for text in (*entry["title"].values(), *entry["guide"]["title"].values()):
            add(identity, text, 3)
        for terms in entry["keywords"].values():
            for term in terms:
                add(identity, term, 4)
        for text in (*entry["symptom"].values(), *entry["cause"].values(),
                     *entry["guide"]["summary"].values()):
            add(identity, text, 6)
        for fix in entry["fix"].values():
            if fix is not None:
                for block in fix["article"]:
                    for text in (*block["text"].values(), *block["commands"]):
                        add(identity, text, 6)
        for distro in entry["distros"]["reported"]:
            add(identity, distro, 5)
        families = entry["distros"]["possible"]
        for family in families:
            add(identity, family, 5)
        for alias, family in handbook._FAMILY_ALIASES.items():
            if family in families:
                add(identity, alias, 5)
        if entry.get("fixed_in"):
            # Versions are matched as a whole below, never as loose digits.
            add(identity, "fixed_in", 5)
        for alias in _ENTRY_ALIASES.get(identity, ()):
            add(identity, alias, 4)

    for module, metadata in vocabulary().items():
        for category, terms in metadata["categories"].items():
            for term in terms:
                query = handbook.normalize(term)
                if not _words(term):
                    continue
                aliases[query].add(module)
                if category == "Módulo":
                    names[query].add(module)
                if category in _SEMANTIC:
                    for identity in modules[module]:
                        add(identity, term, 5)
        for name in (module, metadata["label"], *metadata["title"].values()):
            names[handbook.normalize(name)].add(module)

    prefixes, lengths = defaultdict(dict), defaultdict(list)
    for word, postings in words.items():
        lengths[len(word)].append(word)
        if len(postings) > 25:
            continue  # Common handbook boilerplate is poor prefix evidence.
        for length in range(3, min(len(word), 8) + 1):
            for identity, rank in postings.items():
                if rank <= 5:
                    prefixes[word[:length]][identity] = 7
    patterns = tuple((identity, tuple(re.compile(pattern, re.IGNORECASE)
                                     for pattern in entry["match"]))
                     for identity, entry in entries.items())
    return _Index(entries, modules, aliases, names, words, prefixes, lengths, patterns)


def _distance(left: str, right: str, limit: int) -> int:
    """Bounded Levenshtein distance, also accepting adjacent transpositions."""
    previous = list(range(len(right) + 1))
    before = previous
    for row, char in enumerate(left, 1):
        current = [row]
        for col, other in enumerate(right, 1):
            cost = char != other
            value = min(current[-1] + 1, previous[col] + 1, previous[col - 1] + cost)
            if row > 1 and col > 1 and char == right[col - 2] and left[row - 2] == other:
                value = min(value, before[col - 2] + 1)
            current.append(value)
        if min(current) > limit:
            return limit + 1
        before, previous = previous, current
    return previous[-1]


@lru_cache(maxsize=1024)
def _near(word: str) -> tuple[str, ...]:
    if len(word) < 5 or not word.isalpha():
        return ()
    limit = 2 if len(word) >= 8 else 1
    candidates = []
    for length in range(len(word) - limit, len(word) + limit + 1):
        for candidate in _index().lengths.get(length, ()):
            distance = _distance(word, candidate, limit)
            if distance <= limit:
                candidates.append((distance, candidate))
    return tuple(candidate for _, candidate in sorted(candidates)[:3])


def _postings(word: str, *, fuzzy: bool) -> tuple[dict, str]:
    index = _index()
    postings = dict(index.words.get(word, {}))
    if len(word) >= 3:
        if len(word) <= 8:
            prefixed = index.prefixes.get(word, {})
        else:
            prefixed = {identity: 7 for candidate in index.lengths.get(len(word), ())
                        if candidate.startswith(word) for identity in index.words[candidate]}
            # Longer prefixes are uncommon; inspect only vocabulary sharing 8 letters.
            if not prefixed:
                prefixed = {identity: 7 for candidate in index.words
                            if candidate.startswith(word) for identity in index.words[candidate]}
        for identity, rank in prefixed.items():
            postings.setdefault(identity, rank)
    if postings:
        return postings, word
    near = _near(word) if fuzzy else ()
    return ({identity: 8 for candidate in near for identity in index.words[candidate]},
            near[0] if near else word)


def _identifiers(text: str, index: _Index) -> dict[str, tuple[int, str, str]]:
    query = handbook.normalize(text)
    explicit = query.startswith("ficha ")
    query = re.sub(r"^(?:ficha|entry|code|codigo)\s+", "", query)
    reference = _REFERENCE.fullmatch(query)
    found = {}
    if reference:
        prefix, area, number = reference.groups()
        identity = f"{area.upper()}-{int(number):02d}"
        # Two-digit IDs are unambiguous. Legacy PKG-6 means code PKG-006;
        # CU-1 and the other handbook shorthands retain the entry convention.
        entry_first = explicit or (not prefix and (len(number) == 2 or
                                                   (len(number) == 1 and area != "pkg")))
        if identity in index.entries and entry_first:
            found[identity] = (0, "id", identity)
        for key, entry in index.entries.items():
            for code in entry["codes"]:
                if handbook._code_matches(query, code):
                    found.setdefault(key, (1, "code", code))
    elif re.fullmatch(r"[a-z]+", query):
        for key, entry in index.entries.items():
            if key.split("-")[0].lower() == query or any(
                code.split("-")[1].lower() == query for code in entry["codes"]
            ):
                found[key] = (1, "term", query.upper())
    return found


@lru_cache(maxsize=256)
def matches(text: str, *, module: str = "") -> tuple[SearchMatch, ...]:
    index = _index()
    allowed = index.modules.get(module, set()) if module else set(index.entries)
    query = handbook.normalize(text)
    if not query:
        return tuple(SearchMatch(entry, "", "") for key, entry in index.entries.items() if key in allowed)
    ranked = {}

    def offer(identity: str, rank: int, kind: str, term: str, coverage: int = 0):
        if identity not in allowed:
            return
        score = (rank, -coverage)
        if identity not in ranked or score < ranked[identity][0]:
            ranked[identity] = (score, SearchMatch(index.entries[identity], kind, term))

    references = _identifiers(text, index)
    for identity, (rank, kind, term) in references.items():
        offer(identity, rank, kind, term)
    if references and _REFERENCE.fullmatch(re.sub(r"^(?:ficha|entry|code|codigo)\s+", "", query)):
        # The supplied vocabulary also cross-references errors from other
        # modules (NET-001 is emitted by a video download). Keep that link
        # below the actual coded entry, without attaching its code to a guide.
        for key in index.aliases.get(query, ()):
            if not any(index.entries[identity]["module"] == key for identity in ranked):
                identity = next(identity for identity in index.entries if identity in index.modules[key])
                offer(identity, 5, "module", key)
        return tuple(item[1] for _, item in sorted(ranked.items(), key=lambda pair: pair[1][0]))
    for identity, patterns in index.patterns:
        if identity in allowed and any(pattern.search(text) for pattern in patterns):
            offer(identity, 0 if len(text) > 60 or "\n" in text else 2, "message", text.strip().splitlines()[0][:90])
    for identity, entry in index.entries.items():
        if entry.get("fixed_in") and (query == handbook.normalize(entry["fixed_in"])):
            offer(identity, 3, "term", entry["fixed_in"])
    if re.fullmatch(r"\d+\.\d+\.\d+", text.strip()):
        return tuple(item[1] for item in ranked.values() if item[1].term == text.strip())
    for key in index.names.get(query, ()):
        for identity in index.modules[key]:
            offer(identity, 3, "module", key)
    for key in index.aliases.get(query, ()):
        for identity in index.modules[key]:
            offer(identity, 5, "term", text.strip()[:90])

    tokens = sorted(_words(text))
    evidence = defaultdict(list)
    corrections = {}
    for token in tokens:
        postings, corrected = _postings(token, fuzzy=len(tokens) <= 8 and query not in index.aliases)
        corrections[token] = corrected
        for identity, rank in postings.items():
            if identity in allowed:
                evidence[identity].append(rank)
    maximum = max((len(ranks) for ranks in evidence.values()), default=0)
    threshold = max(1, math.ceil(len(tokens) / 2))
    # A partial phrase is a fallback, never mixed with complete matches.
    if maximum >= threshold:
        for identity, ranks in evidence.items():
            if len(ranks) == maximum:
                rank = max(ranks)
                corrected = " ".join(corrections[token] for token in tokens)
                offer(identity, max(rank, 6) if maximum < len(tokens) else rank,
                      "spelling" if rank == 8 else "term",
                      corrected if rank == 8 else text.strip()[:90], maximum)
    if any(score[0] <= 5 for score, _ in ranked.values()):
        ranked = {key: value for key, value in ranked.items() if value[0][0] <= 5}
    return tuple(item[1] for _, item in sorted(ranked.items(),
                 key=lambda pair: (*pair[1][0], tuple(index.entries).index(pair[0]))))


def suggestions(text: str, *, module: str = "") -> tuple[str, ...]:
    """Offer corrections only if they lead to results in the current scope."""
    tokens = sorted(_words(text))
    if len(tokens) > 8:
        return ()  # A pasted log is not a useful spelling-suggestion query.
    proposed = []
    for token in tokens:
        for near in _near(token):
            candidate = " ".join(near if word == token else word for word in tokens)
            if candidate != handbook.normalize(text) and matches(candidate, module=module):
                proposed.append(candidate)
    return tuple(dict.fromkeys(proposed))[:3]


def suggested_modules(text: str) -> tuple[str, ...]:
    """Closest named modules for the empty state, without an arbitrary default."""
    index = _index()
    near = get_close_matches(handbook.normalize(text), tuple(index.names), n=3, cutoff=0.45)
    return tuple(dict.fromkeys(module for name in near for module in sorted(index.names[name])))[:3]
