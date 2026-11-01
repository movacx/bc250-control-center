"""The vendored SMU mailbox waits by time, not by a count of reads.

Upstream read the response register 100 times with no pause, so a valid command
the firmware had not answered yet was reported as ``status 0x00``. The vendored
copy (``bc250_smu_oc_vendor.zip``) now follows keyboardspecialist's patch 0004:
it polls for up to five seconds, 1 ms apart, and says so when nothing answers.
These tests run the very file the privileged helper runs.
"""

from __future__ import annotations

import sys
import time
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / "privileged" / "lib" / "bc250_smu_oc_vendor.zip"


@pytest.fixture()
def mailbox_module(monkeypatch):
    for name in [n for n in sys.modules if n == "bc250_smu" or n.startswith("bc250_smu.")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.syspath_prepend(str(VENDOR))
    from bc250_smu import mailbox  # type: ignore[import-not-found]

    yield mailbox
    for name in [n for n in sys.modules if n == "bc250_smu" or n.startswith("bc250_smu.")]:
        sys.modules.pop(name, None)


class _Transport:
    """A firmware that answers ``answers`` reads late, then with ``status``."""

    def __init__(self, status: int, late: int = 0):
        self.status, self.late, self.reads, self.writes = status, late, 0, []

    def write_smu_reg(self, address, value):
        self.writes.append((address, value))

    def read_smu_reg(self, address):
        self.reads += 1
        return 0 if self.reads <= self.late else self.status


def test_a_slow_answer_is_waited_for_not_reported_as_status_zero(mailbox_module):
    # 100 reads were the whole budget before; this one answers after 300.
    transport = _Transport(status=0x01, late=300)
    box = mailbox_module.Bc250Mailbox(transport, 0xC, 0xD, 0xE, timeout=5.0)
    assert box.send(0x3B, 7) == 0x01
    assert transport.reads == 301


def test_nothing_answering_is_a_clear_timeout_that_names_the_message(mailbox_module):
    box = mailbox_module.Bc250Mailbox(_Transport(status=0), 0xC, 0xD, 0xE, timeout=0.05)
    started = time.monotonic()
    with pytest.raises(RuntimeError, match=r"smu timed out after 0\.05s for msg 0x3B \(last status 0x00\)"):
        box.send(0x3B)
    assert 0.04 <= time.monotonic() - started < 2


def test_every_reply_that_means_done_is_returned_as_before(mailbox_module):
    for status in (0x01, 0xFF, 0xFE, 0xFD, 0xFC):
        box = mailbox_module.Bc250Mailbox(_Transport(status=status), 0xC, 0xD, 0xE, timeout=1.0)
        assert box.send(0x01) == status


def test_the_polling_leaves_the_cpu_between_reads(mailbox_module, monkeypatch):
    pauses = []
    monkeypatch.setattr(mailbox_module.time, "sleep", lambda seconds: pauses.append(seconds))
    box = mailbox_module.Bc250Mailbox(_Transport(status=0x01, late=3), 0xC, 0xD, 0xE, timeout=5.0)
    box.send(0x01)
    assert pauses == [0.001] * 3


def test_the_public_default_is_five_seconds_and_the_ledger_says_why():
    with zipfile.ZipFile(VENDOR) as archive:
        assert "timeout: float = 5.0" in archive.read("bc250_smu/api.py").decode()
        assert "timeout: float = 5.0" in archive.read("bc250_smu/mailbox.py").decode()
        ledger = archive.read("BC250CC_PATCHES").decode()
    assert "0004-time-based-mailbox-timeout.patch" in ledger
    assert "0001-transaction-level-flock.patch" in ledger
