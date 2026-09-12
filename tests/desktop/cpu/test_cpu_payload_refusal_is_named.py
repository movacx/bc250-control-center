"""The audited CPU payload has its own limits, and saying so is the whole job.

A user asked for 3200 MHz — a frequency this interface offers — and the R64
payload refused it, because upstream treats anything below the stock clock as a
usage mistake. What the user was told instead was that a protected helper was
missing and that they should reinstall the application. Nothing was missing.

The rule added for this has to win over two broader ones that used to swallow
it: ``BC250-CONFIG-001`` matches "invalid ... value" and therefore matches
argparse's "invalid int_freq value", and ``BC250-HELPER-001`` is the reinstall
advice that must never be given for a value the interface itself offered.
"""

from __future__ import annotations

import pytest

from bc250cc.shared import error_catalog
from frontends.desktop.core.error_diagnostics import diagnose_error

CODE = "BC250-CPUTOOL-001"

# Copied from the session console of the board that reported this.
REAL_FAILURE = (
    "usage: python3 -m bc250_detect [-h] -f MHz -v mV [-t °C] [-k] [-c path]"
    "Cannot overclock below stock frequency!\n\n"
    "python3 -m bc250_detect: error: argument -f/--frequency: "
    "invalid int_freq value: '3200'"
)


def test_the_real_failure_is_named_for_what_it_is():
    assert diagnose_error(REAL_FAILURE).code == CODE


def test_the_user_is_not_sent_to_reinstall_for_a_value_we_offered():
    diagnosis = diagnose_error(REAL_FAILURE)
    text = f"{diagnosis.summary} {diagnosis.cause} {diagnosis.action}".lower()
    assert "reinstall" not in text.replace("needs reinstalling", "")
    assert "missing" not in text.replace("nothing is missing", "")


def test_the_advice_says_plainly_that_nothing_is_broken():
    assert "Nothing is missing" in diagnose_error(REAL_FAILURE).action


@pytest.mark.parametrize(
    "message",
    [
        "Cannot overclock below stock frequency!",
        "Target frequency is too high!",
        "It is not allowed to go below 950 mV Vid!",
        "It is not allowed to go above 1325 mV Vid!",
        "Temperature limit cannot be above 100 °C!",
        "Specify positive integers for temperature limit!",
        "error: argument -v/--vid: invalid int_vid value: '900'",
        "error: argument -t/--temp: invalid int_temp value: '120'",
    ],
)
def test_every_refusal_the_payload_can_print_is_covered(message):
    """These are all of the messages bc250_detect's own validators emit."""
    assert diagnose_error(message).code == CODE


def test_the_rule_wins_over_the_configuration_rule_that_used_to_take_it():
    """``invalid int_freq value`` matches "invalid ... value" as well."""
    config = diagnose_error("The governor TOML is invalid: invalid value in [gpu]")
    assert config.code == "BC250-CONFIG-001"
    assert diagnose_error(REAL_FAILURE).code != config.code


def test_a_genuinely_missing_helper_still_reports_the_helper_problem():
    """Narrowing one rule must not blind the one it sits in front of."""
    missing = diagnose_error("The protected helper is missing from /usr/libexec")
    assert missing.code == "BC250-HELPER-001"


def test_the_backend_catalog_carries_the_same_identifier_and_wording():
    """One set of sentences, so the thirty locales translate both layers."""
    entry = next(code for code in error_catalog.all_codes() if code.code == CODE)
    desktop = diagnose_error(REAL_FAILURE)
    assert entry.summary == desktop.summary
    assert entry.cause == desktop.cause
    assert entry.action == desktop.action


def test_the_diagnosis_is_translated_everywhere_it_is_shown():
    from frontends.desktop.i18n import translation_coverage

    diagnosis = diagnose_error(REAL_FAILURE)
    missing = translation_coverage(
        (diagnosis.summary, diagnosis.cause, diagnosis.action)
    )
    assert missing == {}, missing
