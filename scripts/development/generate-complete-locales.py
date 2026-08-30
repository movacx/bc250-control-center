#!/usr/bin/env python3
"""Generate complete reviewed-source locale JSON files.

Existing exact translations are preserved. Missing languages and unresolved
natural-language entries are translated in bounded batches while format
placeholders, commands, URLs and BC250 technical identifiers are protected.
The output is deterministic JSON and is validated before it replaces a locale.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from frontends.desktop import i18n  # noqa: E402

LOCALE_ROOT = ROOT / "frontends" / "desktop" / "i18n" / "locales"
COMPLETE_LOCALES = (
    "en", "es", "es-419", "pt-BR", "pt", "ru", "pl", "de", "fr", "uk",
    "zh-CN", "zh-TW", "ja", "ko", "it", "cs", "tr", "nl", "ro", "hu",
    "bg", "da", "fi", "el", "id", "ms", "no", "sv", "th", "vi",
)
REVIEWED_BASES = {"en", "es", "pt", "ru", "pl", "de", "uk"}
REGIONAL_BASE = {"es-419": "es", "pt-BR": "pt"}
INTENTIONAL_ENGLISH_VALUES = {
    "Cyan Skillfish Governor (SMU)",
    "PWM 2 · Pump Fan / J4003 Fan 1",
    "ZRAM {zram} · ZSWAP {zswap}",
}
GOOGLE_LANGUAGE = {"zh-CN": "zh-CN", "zh-TW": "zh-TW"}
PROTECTED_TERMS = (
    "BC250", "BC-250", "SMU", "UMR", "TTM", "ZRAM", "ZSWAP", "WGP",
    "PWM", "Cyan", "Oberon", "Decky", "AMDGPU", "AMD", "GFX1013",
    "NCT", "nct6687d", "nct6683", "hwmon", "D-Bus", "TOML", "YAML",
    "JSONL", "RPM", "VID", "SCLK", "CU", "CPU", "GPU", "VRAM", "NVMe", "M.2",
    "SteamOS", "Bazzite", "CachyOS", "OpenRC", "systemd", "runit",
    "s6-rc", "s6", "dinit", "SysVinit", "Linux", "Mesa", "RADV", "Polkit",
    "Arch", "Manjaro", "Fedora", "Ubuntu", "Debian", "Gentoo", "Artix", "Void",
    "fix-metrics", "fix-freq", "set-method", "gpu-usage", "config.toml",
    "rpm-ostree", "systemctl", "systemctl --user",
)
REQUIRED_PROTECTED_TERMS = PROTECTED_TERMS
DYNAMIC_COUNT_FORMS = {
    "point": ("point", "points", "points"),
    "WGP pair": ("WGP pair", "WGP pairs", "WGP pairs"),
    "routed WGP": ("routed WGP", "routed WGPs", "routed WGPs"),
    "row": ("row", "rows", "rows"),
    "process": ("process", "processes", "processes"),
    "application": ("application", "applications", "applications"),
    "event": ("event", "events", "events"),
    "second": ("second", "seconds", "seconds"),
    "minute": ("minute", "minutes", "minutes"),
}
DYNAMIC_EXAMPLES = tuple(
    f"{number} {form}"
    for forms in DYNAMIC_COUNT_FORMS.values()
    for number, form in zip((1, 2, 5), forms, strict=True)
)
PLACEHOLDER_RE = re.compile(r"\{[^{}]+\}")
URL_RE = re.compile(r"https?://[^\s)]+")
BACKTICK_RE = re.compile(r"`[^`]+`")
COMMAND_LINE_PATTERN = (
    r"(?m:^(?:sudo\s+)?(?:"
    r"systemctl(?:\s+--\S+)*\s+(?:enable|disable|start|stop|restart|status|daemon-reload)"
    r"|journalctl\s+|pacman\s+-|dnf\s+|apt(?:-get)?\s+|rpm-ostree\s+"
    r"|mkinitcpio\s+|dracut(?:\s+|$)|grub\S*\s+|modprobe\s+|cat\s+/"
    r"|VK_DRIVER_FILES=)[^\n]*$)"
)
COMMAND_LINE_RE = re.compile(COMMAND_LINE_PATTERN)
TECHNICAL_RE = re.compile(
    r"(?<!\w)(" + "|".join(re.escape(term) for term in sorted(PROTECTED_TERMS, key=len, reverse=True)) + r")(?!\w)"
)
TOKEN_RE = re.compile(r"</?code\b", re.IGNORECASE)
FORMAT_RE = re.compile(r"\{[^{}]+\}")
PROTECT_RE = re.compile(
    COMMAND_LINE_PATTERN + r"|\{[^{}]+\}|https?://[^\s)]+|`[^`]+`|"
    + r"(?<!\w)(?:"
    + "|".join(re.escape(term) for term in sorted(PROTECTED_TERMS, key=len, reverse=True))
    + r")(?!\w)"
)


def protected_terms_in(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(match.group(0) for match in PROTECT_RE.finditer(text)))


def protected_terms_preserved(source: str, translated: str) -> bool:
    return all(term in translated for term in protected_terms_in(source))


def canonical_sources() -> list[str]:
    sources = set(i18n._EXACT)
    sources.update(str(value) for value in i18n.BASE_TRANSLATIONS.get("en", {}).values())
    sources.add(i18n.PROJECT_OVERVIEW["en"])
    sources.add(i18n.DAEMON_DETAILS["en"])
    sources.update(i18n.HISTORY_DYNAMIC_SOURCES)
    sources.update(i18n.ADDITIONAL_VISIBLE_SOURCES)
    sources.update(DYNAMIC_EXAMPLES)
    return sorted(source for source in sources if source)


def is_technical_only(source: str) -> bool:
    lines = [line.strip() for line in source.splitlines() if line.strip()]
    return bool(lines) and all(i18n._looks_technical_line(line) for line in lines)


def protect(source: str, ordinal: int) -> tuple[str, dict[str, str]]:
    del ordinal  # kept in the signature for deterministic batch diagnostics
    replacements: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        key = f"bc{len(replacements)}"
        replacements[key] = match.group(0)
        return f'<code id="{key}">{html.escape(match.group(0))}</code>'

    return PROTECT_RE.sub(replace, source), replacements


def restore(value: str, replacements: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1).lower()
        return replacements.get(key, match.group(0))

    value = re.sub(
        r'<code\s+id=["\'](bc\d+)["\'][^>]*>.*?</code>',
        replace,
        value,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return html.unescape(value)


def translate_request(text: str, language: str) -> str:
    language = GOOGLE_LANGUAGE.get(language, language)
    query = urllib.parse.urlencode({
        "client": "gtx", "sl": "en", "tl": GOOGLE_LANGUAGE.get(language, language),
        "dt": "t", "q": text,
    })
    urls = (
        ("https://translate.googleapis.com/translate_a/single?" + query, "single"),
        (
            "https://clients5.google.com/translate_a/t?"
            + urllib.parse.urlencode({
                "client": "dict-chrome-ex",
                "sl": "en",
                "tl": language,
                "q": text,
            }),
            "compact",
        ),
    )
    last_error: Exception | None = None
    for attempt in range(3):
        for url, response_kind in urls:
            try:
                request = urllib.request.Request(
                    url, headers={"User-Agent": "BC250-i18n-QA/1.0"}
                )
                # Both endpoints are fixed HTTPS Google hosts assembled above;
                # callers cannot supply a scheme or host.
                with urllib.request.urlopen(request, timeout=45) as response:  # nosec B310
                    payload = json.loads(response.read().decode("utf-8"))
                if response_kind == "compact":
                    value = payload[0] if isinstance(payload, list) and payload else ""
                    if isinstance(value, str) and value.strip():
                        return value
                    raise ValueError("unexpected compact translation response")
                return "".join(part[0] for part in payload[0] if part and part[0])
            except Exception as error:  # network retry boundary
                last_error = error
        time.sleep(min(6.0, 0.75 * (2 ** attempt)))
    raise RuntimeError(f"translation request failed for {language}: {last_error}")


def translate_segmented(source: str, language: str) -> str:
    """Last-resort translation that never sends protected spans upstream."""
    output: list[str] = []
    cursor = 0
    for match in PROTECT_RE.finditer(source):
        segment = source[cursor:match.start()]
        output.append(translate_request(segment, language) if re.search(r"[A-Za-z]", segment) else segment)
        output.append(match.group(0))
        cursor = match.end()
    segment = source[cursor:]
    output.append(translate_request(segment, language) if re.search(r"[A-Za-z]", segment) else segment)
    return "".join(output)


def chunks(entries: list[tuple[str, str, dict[str, str]]], maximum: int = 2400):
    current: list[tuple[str, str, dict[str, str]]] = []
    size = 0
    for entry in entries:
        required = len(entry[1]) + 32
        if current and size + required > maximum:
            yield current
            current = []
            size = 0
        current.append(entry)
        size += required
    if current:
        yield current


def translate_chunk(language: str, index: int, entries):
    separator = f"ZXQSEPARATOR{index:05d}QXZ"
    request = (f"\n{separator}\n").join(entry[1] for entry in entries)
    translated = translate_request(request, language)
    values = translated.split(separator)
    if len(values) != len(entries):
        # A bounded individual fallback prevents one altered separator from
        # poisoning the rest of the catalog.
        values = [translate_request(entry[1], language) for entry in entries]
    result = []
    for (source, _protected, replacements), value in zip(entries, values, strict=True):
        value = restore(value.strip("\n"), replacements)
        valid = (
            value.strip()
            and not TOKEN_RE.search(value)
            and sorted(FORMAT_RE.findall(source)) == sorted(FORMAT_RE.findall(value))
            and protected_terms_preserved(source, value)
        )
        if not valid:
            # Translation services occasionally damage one sentinel inside a
            # large batch. Retry only that entry with fresh protection tokens.
            protected, retry_replacements = protect(source, 99999)
            value = restore(translate_request(protected, language), retry_replacements)
        valid = (
            value.strip()
            and not TOKEN_RE.search(value)
            and sorted(FORMAT_RE.findall(source)) == sorted(FORMAT_RE.findall(value))
            and protected_terms_preserved(source, value)
        )
        if not valid:
            value = translate_segmented(source, language)
        if TOKEN_RE.search(value):
            raise ValueError(f"unrestored protection token for {language}: {source!r}")
        result.append((source, value))
    return result


def validate_catalog(language: str, sources: list[str], catalog: dict[str, str]) -> None:
    if set(catalog) != set(sources):
        missing = set(sources) - set(catalog)
        extra = set(catalog) - set(sources)
        raise ValueError(f"{language}: key mismatch; missing={len(missing)} extra={len(extra)}")
    for source, translated in catalog.items():
        if not isinstance(translated, str) or not translated.strip():
            raise ValueError(f"{language}: empty translation for {source!r}")
        if sorted(FORMAT_RE.findall(source)) != sorted(FORMAT_RE.findall(translated)):
            raise ValueError(f"{language}: placeholder mismatch for {source!r}")
        for term in protected_terms_in(source):
            if term not in translated:
                raise ValueError(f"{language}: technical term {term!r} changed in {source!r}")


def reviewed_catalog(language: str, sources: list[str]) -> tuple[dict[str, str], list[str]]:
    result: dict[str, str] = {}
    unresolved: list[str] = []
    for source in sources:
        translated = i18n.tr(source, language)
        lost_required_term = not protected_terms_preserved(source, translated)
        if lost_required_term or (
            translated == source and language != "en" and not is_technical_only(source)
        ):
            unresolved.append(source)
        else:
            result[source] = translated
    return result, unresolved


def generate_language(language: str, sources: list[str], workers: int) -> dict[str, str]:
    if language == "en":
        return {source: source for source in sources}
    if language in REVIEWED_BASES:
        catalog, pending = reviewed_catalog(language, sources)
    else:
        catalog, pending = {}, list(sources)
    entries = []
    for ordinal, source in enumerate(pending):
        protected, replacements = protect(source, ordinal)
        entries.append((source, protected, replacements))
    batches = list(chunks(entries))
    if batches:
        print(f"{language}: translating {len(entries)} entries in {len(batches)} batches", flush=True)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(translate_chunk, language, index, batch): index
                for index, batch in enumerate(batches)
            }
            completed = 0
            for future in as_completed(futures):
                catalog.update(future.result())
                completed += 1
                if completed % 25 == 0 or completed == len(batches):
                    print(f"{language}: {completed}/{len(batches)} batches", flush=True)
    validate_catalog(language, sources, catalog)
    return catalog


def write_catalog(language: str, catalog: dict[str, str]) -> None:
    LOCALE_ROOT.mkdir(parents=True, exist_ok=True)
    target = LOCALE_ROOT / f"{language}.json"
    temporary = target.with_suffix(".json.new")
    temporary.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)


def repair_existing_catalog(language: str, sources: list[str]) -> int:
    target = LOCALE_ROOT / f"{language}.json"
    catalog = json.loads(target.read_text(encoding="utf-8"))
    repaired = 0
    for source in sources:
        translated = str(catalog.get(source, ""))
        damaged = (
            not translated.strip()
            or TOKEN_RE.search(translated)
            or re.search(r"QAZ|ZXQ|QXZ|XZZ", translated)
            or sorted(FORMAT_RE.findall(source)) != sorted(FORMAT_RE.findall(translated))
            or not protected_terms_preserved(source, translated)
        )
        if damaged:
            catalog[source] = source if language == "en" else translate_segmented(source, language)
            repaired += 1
    validate_catalog(language, sources, catalog)
    write_catalog(language, catalog)
    return repaired


def augment_existing_catalog(language: str, sources: list[str]) -> int:
    target = LOCALE_ROOT / f"{language}.json"
    catalog = json.loads(target.read_text(encoding="utf-8"))
    missing = [source for source in sources if source not in catalog]
    if not missing:
        validate_catalog(language, sorted(set(sources) | set(catalog)), catalog)
        return 0
    if language == "en":
        catalog.update({source: source for source in missing})
    else:
        entries = []
        for ordinal, source in enumerate(missing):
            reviewed = i18n.tr(source, language)
            if (language in REVIEWED_BASES or language in REGIONAL_BASE) and (
                reviewed != source or is_technical_only(source)
            ):
                catalog[source] = reviewed
                continue
            protected, replacements = protect(source, ordinal)
            entries.append((source, protected, replacements))
        for index, batch in enumerate(chunks(entries)):
            catalog.update(translate_chunk(language, index, batch))
    # Older releases may retain valid compatibility strings that are no
    # longer reachable from the current widget tree.  Augmentation must never
    # delete that user-facing translation history merely to add new keys.
    validate_catalog(language, sorted(set(sources) | set(catalog)), catalog)
    write_catalog(language, catalog)
    return len(missing)


def repair_english_fallbacks(language: str, sources: list[str]) -> int:
    """Translate stale natural-language English values in one complete catalog."""
    if language == "en":
        return 0
    target = LOCALE_ROOT / f"{language}.json"
    catalog = json.loads(target.read_text(encoding="utf-8"))
    candidates = [
        source
        for source in sources
        if catalog.get(source) == source
        and source not in INTENTIONAL_ENGLISH_VALUES
        and not is_technical_only(source)
        and len(re.findall(r"[A-Za-z]{3,}", source)) >= 3
    ]
    pending = []
    for ordinal, source in enumerate(candidates):
        reviewed = i18n._EXACT.get(source, {}).get(language, "")
        if reviewed and reviewed != source:
            catalog[source] = reviewed
            continue
        protected, replacements = protect(source, ordinal)
        pending.append((source, protected, replacements))
    for index, batch in enumerate(chunks(pending)):
        catalog.update(translate_chunk(language, index, batch))
    validate_catalog(language, sorted(set(sources) | set(catalog)), catalog)
    write_catalog(language, catalog)
    return len(candidates)


def repair_command_literals(language: str, sources: list[str]) -> int:
    """Retranslate help text whose copyable shell lines were modified."""
    if language == "en":
        return 0
    target = LOCALE_ROOT / f"{language}.json"
    catalog = json.loads(target.read_text(encoding="utf-8"))
    candidates = [
        source
        for source in sources
        if any(
            command.strip() not in catalog.get(source, "")
            for command in COMMAND_LINE_RE.findall(source)
        )
    ]
    entries = []
    for ordinal, source in enumerate(candidates):
        protected, replacements = protect(source, ordinal)
        entries.append((source, protected, replacements))
    for index, batch in enumerate(chunks(entries)):
        catalog.update(translate_chunk(language, index, batch))
    validate_catalog(language, sorted(set(sources) | set(catalog)), catalog)
    write_catalog(language, catalog)
    return len(candidates)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--languages", nargs="*", default=list(COMPLETE_LOCALES))
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--repair-existing", action="store_true")
    parser.add_argument("--augment-existing", action="store_true")
    parser.add_argument("--repair-english-fallbacks", action="store_true")
    parser.add_argument("--repair-command-literals", action="store_true")
    args = parser.parse_args()
    invalid = set(args.languages) - set(COMPLETE_LOCALES)
    if invalid:
        parser.error("unsupported locale(s): " + ", ".join(sorted(invalid)))
    sources = canonical_sources()
    print(f"canonical sources: {len(sources)}", flush=True)
    generated: dict[str, dict[str, str]] = {}
    for language in args.languages:
        if args.augment_existing:
            added = augment_existing_catalog(language, sources)
            print(f"{language}: added {added} entries", flush=True)
            continue
        if args.repair_english_fallbacks:
            repaired = repair_english_fallbacks(language, sources)
            print(f"{language}: translated {repaired} English fallbacks", flush=True)
            continue
        if args.repair_command_literals:
            repaired = repair_command_literals(language, sources)
            print(f"{language}: repaired {repaired} command-bearing entries", flush=True)
            continue
        if args.repair_existing:
            repaired = repair_existing_catalog(language, sources)
            print(f"{language}: repaired {repaired} entries", flush=True)
            continue
        base = REGIONAL_BASE.get(language)
        if language == "zh-TW":
            try:
                from opencc import OpenCC
            except ImportError as error:
                raise RuntimeError(
                    "zh-TW generation requires opencc-python-reimplemented from requirements-dev.txt"
                ) from error
            catalog = generated.get("zh-CN")
            if catalog is None:
                catalog = json.loads((LOCALE_ROOT / "zh-CN.json").read_text(encoding="utf-8"))
            converter = OpenCC("s2twp")
            generated[language] = {
                source: converter.convert(translated) for source, translated in catalog.items()
            }
            validate_catalog(language, sources, generated[language])
        elif base:
            catalog = generated.get(base)
            if catalog is None:
                base_file = LOCALE_ROOT / f"{base}.json"
                catalog = json.loads(base_file.read_text(encoding="utf-8"))
            validate_catalog(language, sources, catalog)
            generated[language] = dict(catalog)
        else:
            generated[language] = generate_language(language, sources, max(1, args.workers))
        write_catalog(language, generated[language])
        print(f"{language}: wrote {len(generated[language])} entries", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
