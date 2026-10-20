"""Which SMU payload is installed decides how, and whether, the chips are read.

The reviewed payload (4a2221d) gives up on a chip that does not answer and
reads four chips per message. The first one (b7e6bff), which Control Center
1.21.1 and earlier installed and BC250-Telemetry still bundles, waits for a
chip with no time limit. A board updated without a power cycle still has the
first one loaded, and a failed upgrade can leave a handler pointing into
bytes that are no longer the code it expects. Each case is told apart here,
and nothing is sent to a payload that is not recognised byte for byte.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import struct
import subprocess
from pathlib import Path

import pytest

from bc250cc.infrastructure import gddr6_memory_temp_repository as desktop
from bc250cc.infrastructure.gddr6_memory_temp_trust import (
    REVIEWED_PATCH_SCRIPT_SHA256,
    REVIEWED_REVISION,
)

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "privileged/helpers"

#: Stand-in for the first payload's bytes: the reader compares a hash, and the
#: tests point that hash at these instead of shipping the real binary.
LEGACY_BYTES = bytes(range(176))


def _load(name: str):
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), str(HELPERS / name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.fixture
def reader(monkeypatch):
    module = _load("bc250-gddr6-temp-reader")
    monkeypatch.setattr(module, "LEGACY_PAYLOAD_SHA256", hashlib.sha256(LEGACY_BYTES).hexdigest())
    monkeypatch.setattr(module, "smn_window_lock", lambda: contextlib.nullcontext())
    monkeypatch.setattr(module, "governor_unsettled", lambda: "")
    return module


@pytest.fixture
def helper():
    return _load("bc250-gddr6-temp-helper")


class FakeSmu:
    """Queue 3's handler table, the payload area, and the chips behind it."""

    def __init__(self, module, handlers, *, payload=b"", packed=(0x26262626, 0x26262626), per_chip=None):
        self.module = module
        self.handlers = handlers
        self.payload = payload
        self.packed = packed
        self.per_chip = per_chip or [0x2600 + 38] * 8
        self.messages = []

    def smu_read(self, address, count):
        if address == self.module.QUEUE_3_HANDLER_TABLE + 5 * 8:
            msg5, msg6, msg7 = self.handlers
            return struct.pack("<5I", msg5, 0, msg6, 0, msg7)[: count * 4]
        offset = address - self.module.PAYLOAD_START
        return self.payload[offset : offset + count * 4].ljust(count * 4, b"\0")

    def send_message(self, queue, message, arguments):
        self.messages.append((queue, message, tuple(arguments)))
        if message == 0x6:
            return (1, self.packed[arguments[0]])
        return (1, self.per_chip[arguments[0]])

    def close(self):
        pass


def _sample(module, smu, monkeypatch, *, collector_installed=False, chips_wanted=True) -> dict:
    monkeypatch.setattr(module, "_open_smu", lambda *args: smu)
    payload = {"patch_active": False, "blocked_reason": "", "chips": []}
    module._sample_smu(
        payload,
        Path("/unused"),
        os.getuid(),
        chips_wanted=chips_wanted,
        collector_installed=collector_installed,
    )
    return payload


def _packed(*codes: int) -> int:
    return sum(code << (8 * slot) for slot, code in enumerate(codes))


# ------------------------------------------------------------ the reader


def test_the_reviewed_payload_is_read_four_chips_per_message(reader, monkeypatch):
    # Parity 0 answers chips 0/2/4/6, parity 1 chips 1/3/5/7, one byte each.
    smu = FakeSmu(
        reader,
        reader.CURRENT_HANDLERS,
        packed=(_packed(38, 40, 42, 44), _packed(39, 41, 43, 45)),
    )
    payload = _sample(reader, smu, monkeypatch)

    assert payload["payload"] == "current"
    assert payload["patch_active"] is True
    assert smu.messages == [(3, 0x6, (0,)), (3, 0x6, (1,))]
    assert [(chip["chip"], chip["code"]) for chip in payload["chips"]] == [
        (0, 38), (1, 39), (2, 40), (3, 41), (4, 42), (5, 43), (6, 44), (7, 45)
    ]
    assert payload["chips"][7]["temperature_c"] == 45 * 2 - 40
    assert payload["hotspot_c"] == 50 and payload["hotspot_chip"] == 7
    assert "chip_errors" not in payload


def test_a_chip_that_timed_out_is_reported_not_shown_as_470_degrees(reader, monkeypatch):
    # 0xFF and 0xFE are the payload's timeouts; decoded as temperatures they
    # would read 470 and 468 °C. 0x90 is outside JEDEC's 0..80.
    smu = FakeSmu(
        reader,
        reader.CURRENT_HANDLERS,
        packed=(_packed(38, 0xFF, 38, 38), _packed(39, 0xFE, 60, 0x90)),
    )
    payload = _sample(reader, smu, monkeypatch)

    assert [chip["chip"] for chip in payload["chips"]] == [0, 1, 4, 5, 6]
    assert payload["chip_errors"] == [
        {"chip": 2, "raw": 0xFF, "error": "stage1_timeout"},
        {"chip": 3, "raw": 0xFE, "error": "stage2_timeout"},
        {"chip": 7, "raw": 0x90, "error": "out_of_range"},
    ]
    assert all(chip["temperature_c"] < 200 for chip in payload["chips"])
    # The hotspot names the chip, not its position in a shortened list.
    assert (payload["hotspot_c"], payload["hotspot_chip"]) == (80, 5)
    assert payload["average_c"] == pytest.approx((36 + 38 + 36 + 80 + 36) / 5)


def test_no_chip_answering_is_named(reader, monkeypatch):
    smu = FakeSmu(reader, reader.CURRENT_HANDLERS, packed=(0xFFFFFFFF, 0xFEFEFEFE))
    payload = _sample(reader, smu, monkeypatch)

    assert payload["patch_active"] is True
    assert payload["chips"] == []
    assert len(payload["chip_errors"]) == 8
    assert payload["blocked_reason"] == "GDDR6_NO_CHIP_ANSWERED"
    assert "hotspot_c" not in payload


def test_a_board_without_the_patch_is_never_sent_a_message(reader, monkeypatch):
    smu = FakeSmu(reader, (0x00012340, 0x00012350, 0x00012360))
    payload = _sample(reader, smu, monkeypatch)

    assert payload["payload"] == ""
    assert payload["patch_active"] is False
    assert payload["blocked_reason"] == "GDDR6_PATCH_INACTIVE"
    assert smu.messages == []


def test_the_first_payload_is_replaced_when_nothing_else_needs_it(reader, monkeypatch):
    smu = FakeSmu(reader, (reader.LEGACY_HANDLER, 0x00012350, 0x00012360), payload=LEGACY_BYTES)
    payload = _sample(reader, smu, monkeypatch, collector_installed=False)

    assert payload["payload"] == "legacy"
    # Inactive, so every front end (old Decky plugins included) asks for the
    # patch, and the helper upgrades it.
    assert payload["patch_active"] is False
    assert payload["blocked_reason"] == "GDDR6_PATCH_INACTIVE"
    assert smu.messages == []


def test_the_first_payload_is_still_read_for_bc250_telemetry(reader, monkeypatch):
    smu = FakeSmu(reader, (reader.LEGACY_HANDLER, 0x00012350, 0x00012360), payload=LEGACY_BYTES)
    payload = _sample(reader, smu, monkeypatch, collector_installed=True)

    assert payload["payload"] == "legacy"
    assert payload["patch_active"] is True
    assert smu.messages == [(3, 0x5, (chip,)) for chip in range(8)]
    assert [chip["code"] for chip in payload["chips"]] == [38] * 8


def test_the_first_handler_over_other_bytes_is_left_alone(reader, monkeypatch):
    # What a failed upgrade leaves: message 5 rolled back to the first
    # payload's address, but the new payload already written over it.
    smu = FakeSmu(
        reader, (reader.LEGACY_HANDLER, 0x00012350, 0x00012360), payload=bytes(176)
    )
    payload = _sample(reader, smu, monkeypatch, collector_installed=True)

    assert payload["payload"] == "unknown"
    assert payload["patch_active"] is False
    assert payload["blocked_reason"] == "GDDR6_PATCH_UNKNOWN"
    assert smu.messages == []


def test_a_half_installed_payload_is_left_alone(reader, monkeypatch):
    msg5, msg6, _msg7 = reader.CURRENT_HANDLERS
    smu = FakeSmu(reader, (msg5, msg6, 0x00012360))
    payload = _sample(reader, smu, monkeypatch)

    assert payload["payload"] == "unknown"
    assert payload["blocked_reason"] == "GDDR6_PATCH_UNKNOWN"
    assert smu.messages == []


def test_status_reads_only_the_handler_table(reader, monkeypatch):
    smu = FakeSmu(reader, reader.CURRENT_HANDLERS)
    payload = _sample(reader, smu, monkeypatch, chips_wanted=False)

    assert payload["patch_active"] is True
    assert payload["chips"] == []
    assert smu.messages == []


def test_the_handler_table_is_the_one_patch_smu_writes(reader):
    # patch_smu.py: QUEUE3_TABLE_BASE + message * 8; message 5's entry is the
    # register the first payload's patcher wrote directly.
    assert reader.QUEUE_3_HANDLER_TABLE + 5 * reader.QUEUE_3_ENTRY_SIZE == 0x748C
    assert all(reader.PAYLOAD_START <= handler < reader.PAYLOAD_END for handler in reader.CURRENT_HANDLERS)
    assert reader.PAYLOAD_START <= reader.LEGACY_HANDLER < reader.PAYLOAD_END


# ------------------------------------------------------------ the patcher


@pytest.mark.parametrize(
    "status, arguments",
    [
        ({"payload": ""}, ()),
        # Byte for byte the first payload, and BC250-Telemetry is not installed.
        ({"payload": "legacy", "patch_active": False}, ("-f",)),
        # Kept for BC250-Telemetry, whose collector refuses any other one.
        ({"payload": "legacy", "patch_active": True}, None),
        ({"payload": "current", "patch_active": True}, None),
    ],
)
def test_patch_smu_is_forced_only_over_the_first_payload(helper, status, arguments):
    assert helper._patch_arguments(status) == arguments


def test_an_unrecognised_patch_is_never_written_over(helper):
    with pytest.raises(RuntimeError, match="GDDR6_PATCH_UNKNOWN"):
        helper._patch_arguments({"payload": "unknown"})


def test_patching_waits_for_what_the_status_said(helper):
    with pytest.raises(helper.ExternalCollectorActive):
        helper._patch_arguments({"external_collector": True, "patch_active": True})
    with pytest.raises(RuntimeError, match="GDDR6_GOVERNOR_UNSETTLED"):
        helper._patch_arguments({"deferred": True, "governor_state": "restarting"})


def _patch_run(helper, monkeypatch, tmp_path, status):
    monkeypatch.setattr(helper, "bios_version", lambda: "P3.00")
    monkeypatch.setattr(helper, "staged_checkout", lambda *args: contextlib.nullcontext(tmp_path))
    monkeypatch.setattr(helper, "external_collector_lock", lambda: contextlib.nullcontext(False))
    monkeypatch.setattr(helper, "smn_window_lock", lambda: contextlib.nullcontext())
    monkeypatch.setattr(helper, "governor_unsettled", lambda: "")
    monkeypatch.setattr(helper, "_patch_status", lambda *args, **kwargs: dict(status))
    ran = []
    monkeypatch.setattr(
        helper.subprocess,
        "run",
        lambda command, **kwargs: ran.append(command) or subprocess.CompletedProcess(command, 0, "", ""),
    )
    assert helper._do_apply(tmp_path, os.getuid(), os.getgid()) == 0
    return ran


def test_the_first_payload_is_upgraded_in_place(helper, monkeypatch, tmp_path):
    ran = _patch_run(helper, monkeypatch, tmp_path, {"payload": "legacy", "patch_active": False})
    assert len(ran) == 1 and ran[0][-1] == "-f"


def test_a_fresh_board_is_patched_without_force(helper, monkeypatch, tmp_path):
    ran = _patch_run(helper, monkeypatch, tmp_path, {"payload": ""})
    assert len(ran) == 1 and "-f" not in ran[0]


def test_an_installed_payload_is_not_written_again(helper, monkeypatch, tmp_path, capsys):
    ran = _patch_run(helper, monkeypatch, tmp_path, {"payload": "current", "patch_active": True})
    assert ran == []
    assert "already active" in capsys.readouterr().out


def test_the_artifacts_patch_smu_reads_are_the_reviewed_ones(helper, monkeypatch, tmp_path):
    repository = tmp_path / "bc250-memory-temperature"
    repository.mkdir()
    staging_parent = tmp_path / "run"
    staging_parent.mkdir()
    monkeypatch.setattr(helper, "STAGING_PARENT", str(staging_parent))
    files = {helper.PAYLOAD_FILE: b"payload", helper.SYMBOLS_FILE: b"symbols"}
    for name, content in files.items():
        (repository / name).write_bytes(content)
        (repository / name).chmod(0o644)
    reviewed = {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}
    with helper.staged_checkout(repository, os.getuid(), reviewed) as staging:
        assert {name: (staging / name).read_bytes() for name in files} == files

    (repository / helper.SYMBOLS_FILE).write_bytes(b"umc_read_temp_packed T 00000800 0000011e\n")
    with pytest.raises(RuntimeError, match="SMUPayload.symbols does not match"):
        with helper.staged_checkout(repository, os.getuid(), reviewed):
            pytest.fail("a payload that is not the reviewed one must never be handed out")

    (repository / helper.SYMBOLS_FILE).write_bytes(b"symbols")
    (repository / helper.PAYLOAD_FILE).chmod(0o666)
    with pytest.raises(RuntimeError, match="not be writable by group or others"):
        with helper.staged_checkout(repository, os.getuid(), reviewed):
            pytest.fail("a payload others can write must never be handed out")
    assert list(staging_parent.iterdir()) == []


def test_a_session_stops_when_no_chip_answers(helper, monkeypatch, capsys):
    silent = {
        "patch_active": True,
        "chips": [],
        "chip_errors": [{"chip": chip, "raw": 0xFF, "error": "stage1_timeout"} for chip in range(8)],
        "blocked_reason": "GDDR6_NO_CHIP_ANSWERED",
    }
    reads = []
    monkeypatch.setattr(helper, "_installed_reader", lambda: "/usr/libexec/reader")
    monkeypatch.setattr(
        helper, "_read_once", lambda _r, _repo, _uid, action, **_kw: reads.append(action) or dict(silent)
    )
    monkeypatch.setattr(helper, "MONITOR_INTERVAL_SECONDS", 0.01)

    with pytest.raises(RuntimeError, match="GDDR6_NO_CHIP_ANSWERED"):
        helper._do_monitor(Path("/unused"), os.getuid(), os.getgid(), 5.0)
    assert reads == ["status", "read"]
    # The sample that found it is still delivered before the session ends.
    assert json.loads(capsys.readouterr().out.splitlines()[0])["chip_errors"]


def test_a_session_keeps_going_when_some_chips_answer(helper, monkeypatch, capsys):
    partial = {
        "patch_active": True,
        "chips": [{"chip": 0, "code": 38, "temperature_c": 36}],
        "chip_errors": [{"chip": 1, "raw": 0xFF, "error": "stage1_timeout"}],
    }
    reads = []
    monkeypatch.setattr(helper, "_installed_reader", lambda: "/usr/libexec/reader")
    monkeypatch.setattr(
        helper, "_read_once", lambda _r, _repo, _uid, action, **_kw: reads.append(action) or dict(partial)
    )
    monkeypatch.setattr(helper, "MONITOR_INTERVAL_SECONDS", 0.01)

    assert helper._do_monitor(Path("/unused"), os.getuid(), os.getgid(), 0.05) == 0
    assert reads.count("read") >= 2
    assert json.loads(capsys.readouterr().out.splitlines()[-1]) == {"session_ended": True}


def test_the_session_passes_its_status_to_the_patch(helper, monkeypatch, capsys):
    """One status decides both whether to patch and whether to force it."""
    status = {"payload": "legacy", "patch_active": False, "blocked_reason": "GDDR6_PATCH_INACTIVE"}
    live = {"patch_active": True, "chips": [{"chip": 0, "code": 38, "temperature_c": 36}]}
    answers = iter([dict(status), dict(live)])
    applied = []
    monkeypatch.setattr(helper, "_installed_reader", lambda: "/usr/libexec/reader")
    monkeypatch.setattr(helper, "_read_once", lambda *args, **kwargs: next(answers, dict(live)))
    monkeypatch.setattr(helper, "_do_apply", lambda *args, **kwargs: applied.append(kwargs["status"]))
    monkeypatch.setattr(helper, "MONITOR_INTERVAL_SECONDS", 0.01)

    helper._do_monitor(Path("/unused"), os.getuid(), os.getgid(), 0.02)
    capsys.readouterr()
    assert applied == [status]


# ------------------------------------------------------- every copy agrees


def test_both_helpers_and_the_desktop_pin_the_same_revision(reader, helper):
    assert reader.REVIEWED_REVISION == helper.REVIEWED_REVISION == REVIEWED_REVISION
    assert helper.REVIEWED_SCRIPT_SHA256[helper.PATCH_SCRIPT] == REVIEWED_PATCH_SCRIPT_SHA256


def test_both_helpers_pin_the_same_bc250_smu_files(reader, helper):
    # The reader imports the package; patch_smu.py imports it too, with unlock.
    package = {
        name: digest
        for name, digest in helper.REVIEWED_MODULE_SHA256.items()
        if name.startswith("bc250_smu/")
    }
    assert package == reader.REVIEWED_PACKAGE_SHA256
    assert "bc250_smu/__init__.py" in package
    assert set(helper._reviewed_files()) == {
        helper.PATCH_SCRIPT,
        "unlock.py",
        *package,
        helper.PAYLOAD_FILE,
        helper.SYMBOLS_FILE,
    }


def test_bc250_telemetrys_rejections_of_the_new_payload_are_benign_everywhere(reader, helper):
    # BC250-Telemetry's patcher raises these after reads only, before unlock
    # or any write, when it finds this payload instead of its own.
    for state in (
        {"state": "failed", "error": "unexpected original Q3/5 handler: 0x0003ab34"},
        {"state": "failed", "error": "SMU patch changed during this boot; reboot before retrying"},
    ):
        assert state in reader.EXTERNAL_GUARD_BENIGN
        assert f"0x{reader.CURRENT_HANDLERS[0]:08x}" in json.dumps(reader.EXTERNAL_GUARD_BENIGN)
    assert reader.EXTERNAL_GUARD_BENIGN == helper.EXTERNAL_GUARD_BENIGN
    assert list(reader.EXTERNAL_GUARD_BENIGN) == list(desktop.EXTERNAL_GUARD_BENIGN)


def test_the_first_payload_is_the_one_bc250_telemetry_bundles(reader):
    # memory/patcher.py in BC250-Telemetry pins the same 176 bytes by hash.
    module = _load("bc250-gddr6-temp-reader")
    assert module.LEGACY_PAYLOAD_SHA256 == (
        "b31908460e932a615d9eafb6b3112e6448994f9f6fa656d1d80a8616ac1df4df"
    )
    assert module.LEGACY_PAYLOAD_SIZE == 176
