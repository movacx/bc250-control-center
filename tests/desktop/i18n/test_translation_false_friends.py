"""Machine-translation mistakes that reached users, pinned so they stay gone.

Each of these shipped: the Settings section "General" rendered as the
military rank in six languages, "Hardware" as a hardware *store* in Spanish,
a PWM channel as a TV channel, the Cinnamon desktop as the spice and Python as
the snake. They are single words, so no placeholder or length check noticed.
"""

from __future__ import annotations

import json
import re

import pytest

from frontends.desktop.i18n.locale_catalog import COMPLETE_LOCALES, LOCALE_DIRECTORY

#: (English source, language, pattern that must NOT match the translation)
FALSE_FRIENDS = (
    ("General", "pl", r"Genera[łl]"),
    ("General", "cs", r"Generál"),
    ("General", "hu", r"tábornok"),
    ("General", "bg", r"генерал"),
    ("General", "fi", r"Kenraali"),
    ("General", "el", r"Στρατηγ"),
    ("General", "es", r"generales"),
    ("Hardware", "es", r"Ferreter"),
    ("Hardware", "es-419", r"Ferreter"),
    ("Channel", "fr", r"Chaîne"),
    ("Channel", "zh-CN", r"频道"),
    ("Channel", "zh-TW", r"頻道"),
    ("History & reports", "ja", r"歴史"),
    ("History & reports", "ko", r"역사"),
    ("Cinnamon protected", "es", r"[Cc]anela"),
    ("Python", "es", r"[Pp]itón"),
    ("Read the board", "es", r"tablero"),
    ("Used swap", "es", r"intercambio"),
    ("Yes", "it", r"^SÌ$"),
    ("No", "it", r"^NO$"),
    # The sidebar's Fans page as admirers, the Dashboard as a car's, a device
    # driver as a chauffeur and Apply as applying for a job.
    ("Fans", "zh-CN", r"粉丝"),
    ("Fans", "zh-TW", r"粉絲"),
    ("Fans", "it", r"Tifosi"),
    ("Fans", "tr", r"Hayran"),
    ("Fans", "vi", r"hâm mộ"),
    ("Dashboard", "de", r"Armaturenbrett"),
    ("Processes", "zh-CN", r"流程"),
    ("Driver", "fr", r"Chauffeur"),
    ("Driver", "zh-CN", r"司机"),
    ("Driver", "pl", r"Kierowca"),
    ("Apply", "fr", r"Postuler"),
    ("Apply", "ja", r"申し込"),
    ("Apply", "zh-CN", r"申请"),
    ("Apply", "sv", r"Ansök"),
    ("Profile", "zh-CN", r"公司"),
)

#: Sentence fragments that are spliced into a longer message, where a
#: lowercase article is correct ("No se pudo iniciar la preparación…").
SPLICED_FRAGMENTS = {"PWM driver preparation", "PWM driver removal"}
CASED = {
    "es", "es-419", "pt-BR", "pt", "ru", "pl", "de", "fr", "uk", "it", "cs", "tr",
    "nl", "ro", "hu", "bg", "da", "fi", "el", "id", "ms", "no", "sv", "vi",
}


def _catalog(code: str) -> dict[str, str]:
    return json.loads((LOCALE_DIRECTORY / f"{code}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("source, language, wrong", FALSE_FRIENDS)
def test_known_false_friends_do_not_come_back(source, language, wrong):
    translated = _catalog(language)[source]
    assert not re.search(wrong, translated), (language, source, translated)


def test_capitalised_labels_stay_capitalised_in_every_cased_language():
    """A label that starts with a capital in English starts with one everywhere.

    Unless its first word is a lowercase identifier the source itself uses
    (``nct6687``, ``hwmon``) or it is spliced into another sentence.
    """
    english = _catalog("en")
    offenders = []
    for code in COMPLETE_LOCALES:
        if code not in CASED:
            continue
        for source, translated in _catalog(code).items():
            if source in SPLICED_FRAGMENTS or source not in english:
                continue
            head = source.lstrip()[:1]
            value = translated.lstrip()
            if not (head.isupper() and value[:1].islower()):
                continue
            first_word = value.split()[0] if value.split() else ""
            if first_word and first_word.lower() in source.lower():
                continue
            offenders.append((code, source, translated))
    assert offenders == [], offenders[:10]
