"""An SMU that did not answer is not a broken install.

A manual scale test on Ubuntu stopped with ``smu returned status 0x00 for
queue 3 msg 0x8F``: the mailbox gave no answer in time, and the very next
message restored the defaults. The CPU/SMU helper exits 70 for any unexpected
exception, and 70 alone means a helper version mismatch, so the user was told
to reinstall the application. Nothing was wrong with the install.
"""

from __future__ import annotations

import pytest

from bc250cc.shared.failure_text import describe_failure
from frontends.desktop.core.error_diagnostics import diagnose_error

# The helper's catch-all exit status for an exception raised by bc250_smu.
HELPER_EXCEPTION_STATUS = 70


def _code(stderr: str) -> str:
    failure = describe_failure(HELPER_EXCEPTION_STATUS, "", stderr)
    return diagnose_error(failure, context="CPU SMU").code


@pytest.mark.parametrize("status", ["0x00", "0xFC"])
def test_an_smu_that_did_not_answer_or_was_busy_asks_for_a_retry(status):
    assert _code(f"ERR smu returned status {status} for queue 3 msg 0x8F\n") == "BC250-BUSY-001"


@pytest.mark.parametrize("status", ["0xFF", "0xFD", "0xFE"])
def test_an_smu_refusal_is_a_cpu_tuning_failure(status):
    assert _code(f"ERR smu returned status {status} for queue 3 msg 0x50\n") == "BC250-CPU-001"


def test_no_smu_status_is_ever_answered_with_reinstall_advice():
    for status in range(256):
        code = _code(f"ERR smu returned status 0x{status:02X} for queue 3 msg 0x8F\n")
        assert code not in {"BC250-HELPER-001", "BC250-PROTOCOL-001"}, status
