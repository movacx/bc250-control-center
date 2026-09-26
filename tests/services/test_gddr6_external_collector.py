"""The GDDR6 helpers must never sample the SMU while BC250-Telemetry does.

BC250-Telemetry (onlinermm) can install ``bc250-memory.service``, a root
collector that patches the SMU with the same payload and polls Queue 3 /
Message 5 every three seconds. It locks ``/run/bc250-memory/smu.lock`` for
its whole life and never the PCI window the other SMU clients share. Two
samplers on one mailbox handed the payload a chip index outside 0-7, and the
SMU hung waiting for a UMC that never answered: the crash a Bazzite tester
reported. The helpers now take that collector's lock, and when it is already
taken they relay the collector's published reading instead.
"""

from __future__ import annotations

import functools
import importlib.machinery
import importlib.util
import json
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

import pytest

from bc250cc.infrastructure.vrm_telemetry_reader import leer_memoria_telemetria

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "privileged/helpers"
BOTH = ["bc250-gddr6-temp-reader", "bc250-gddr6-temp-helper"]

#: BC250-Telemetry's own README example of its published ``memory`` object.
PUBLISHED = {
    "memory": {
        "valid": True,
        "status": "ok",
        "error": None,
        "age_ms": 120,
        "chips_c": [36, 34, 44, 36, 36, 42, 42, 38],
        "average_c": 38.5,
        "hotspot_c": 44,
        "hotspot_chip": 2,
        "saturated": False,
        "saturated_chips": [],
        "raw": [9766, 9509, 10794, 9766, 9766, 10537, 10537, 10023],
    }
}

HOLDER = (
    "import fcntl,os,sys,time;"
    "fd=os.open(sys.argv[1], os.O_RDWR|os.O_CREAT, 0o644);"
    "fcntl.flock(fd, fcntl.LOCK_EX);"
    "print('held', flush=True);"
    "time.sleep(30)"
)


def _load(name: str):
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), str(HELPERS / name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.fixture
def runtime(tmp_path):
    return tmp_path / "bc250-memory"


@pytest.fixture
def installed(tmp_path):
    marker = tmp_path / "bc250-memory.service"
    marker.write_text("[Unit]\n")
    return (marker,)


@pytest.fixture
def collector(runtime):
    """A stand-in for bc250-memory.service holding its lock."""
    runtime.mkdir(mode=0o755, exist_ok=True)
    holder = subprocess.Popen(
        [sys.executable, "-c", HOLDER, str(runtime / "smu.lock")],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "held"
        yield holder
    finally:
        holder.kill()
        holder.wait()


def _lock(module, runtime, markers):
    return functools.partial(
        module.external_collector_lock, runtime, markers, owner=os.getuid()
    )


@pytest.mark.parametrize("helper", BOTH)
def test_nothing_is_coordinated_when_the_collector_is_not_installed(helper, runtime, tmp_path):
    module = _load(helper)
    with _lock(module, runtime, (tmp_path / "absent.service",))() as held:
        assert held is False
    assert not runtime.exists()


@pytest.mark.parametrize("helper", BOTH)
def test_an_installed_collector_that_has_not_started_finds_its_lock_taken(
    helper, runtime, installed
):
    module = _load(helper)
    with _lock(module, runtime, installed)() as held:
        assert held is True
        assert (runtime / "smu.lock").is_file()
        # The collector opens this same file and asks without waiting: it
        # must find it taken, report "another collector owns the SMU lock"
        # and exit before touching anything.
        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                "import fcntl,os,sys;fd=os.open(sys.argv[1], os.O_RDONLY);"
                "fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)",
                str(runtime / "smu.lock"),
            ],
            capture_output=True,
        )
        assert probe.returncode != 0
    # And it is free again the moment the helper is done.
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import fcntl,os,sys;fd=os.open(sys.argv[1], os.O_RDONLY);"
            "fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)",
            str(runtime / "smu.lock"),
        ],
        check=True,
    )


@pytest.mark.parametrize("helper", BOTH)
def test_a_running_collector_keeps_the_helper_off_the_smu(helper, runtime, installed, collector):
    module = _load(helper)
    started = time.monotonic()
    with pytest.raises(module.ExternalCollectorActive):
        with _lock(module, runtime, installed)():
            pytest.fail("the body must not run while the collector owns the SMU")
    # It asks without waiting: the collector never lets go while it runs.
    assert time.monotonic() - started < 1.0


@pytest.mark.parametrize("helper", BOTH)
@pytest.mark.parametrize(
    "state",
    [
        {"state": "preparing"},
        {"state": "reading"},
        {"state": "failed", "error": "SMU timeout on queue 3 message 5"},
        "not json",
    ],
)
def test_an_interrupted_collector_keeps_the_smu_untouched_until_power_off(
    helper, runtime, installed, state
):
    module = _load(helper)
    runtime.mkdir(mode=0o755)
    text = state if isinstance(state, str) else json.dumps(state)
    (runtime / "patch-state.json").write_text(text)
    with pytest.raises(RuntimeError, match="GDDR6_EXTERNAL_INTERRUPTED"):
        with _lock(module, runtime, installed)():
            pytest.fail("the SMU may still be running the interrupted operation")


@pytest.mark.parametrize("helper", BOTH)
@pytest.mark.parametrize(
    "state",
    [
        {"state": "ready"},
        # Raised by an earlier collector before it wrote anything; its own
        # later version retries it, so it is not a wedged SMU.
        {"state": "failed", "error": "unexpected original Q3/5 handler: 0x00000000"},
    ],
)
def test_a_clean_collector_guard_lets_the_helper_proceed(helper, runtime, installed, state):
    module = _load(helper)
    runtime.mkdir(mode=0o755)
    (runtime / "patch-state.json").write_text(json.dumps(state))
    with _lock(module, runtime, installed)() as held:
        assert held is True


@pytest.mark.parametrize("helper", BOTH)
def test_a_runtime_directory_others_can_write_is_not_trusted(helper, runtime, installed):
    module = _load(helper)
    runtime.mkdir()
    runtime.chmod(0o777)
    with pytest.raises(RuntimeError, match="GDDR6_EXTERNAL_UNTRUSTED"):
        with _lock(module, runtime, installed)():
            pass


def _write_telemetry(path: Path, payload: dict, *, age: float = 0.0) -> Path:
    path.write_text(json.dumps(payload))
    moment = time.time() - age
    os.utime(path, (moment, moment))
    return path


def test_the_reader_relays_the_collectors_published_reading(tmp_path):
    reader = _load("bc250-gddr6-temp-reader")
    relay = reader.relay_external_sample(_write_telemetry(tmp_path / "t.json", PUBLISHED))
    assert relay["source"] == "bc250-telemetry"
    assert relay["external_collector"] is True
    assert relay["patch_active"] is True
    assert relay["blocked_reason"] == ""
    assert [chip["temperature_c"] for chip in relay["chips"]] == [36, 34, 44, 36, 36, 42, 42, 38]
    assert relay["chips"][2] == {"chip": 2, "raw": 10794, "code": 42, "temperature_c": 44}
    assert relay["average_c"] == pytest.approx(38.5)
    assert (relay["hotspot_c"], relay["hotspot_chip"]) == (44, 2)


@pytest.mark.parametrize(
    "memory, age",
    [
        (PUBLISHED["memory"], 60.0),  # the telemetry daemon stopped writing
        ({**PUBLISHED["memory"], "valid": False, "status": "starting"}, 0.0),
        ({**PUBLISHED["memory"], "raw": [9766] * 7 + [0xFF]}, 0.0),  # code 255 > 80
        ({**PUBLISHED["memory"], "raw": [9766] * 7}, 0.0),
    ],
)
def test_the_reader_relays_nothing_it_cannot_trust(tmp_path, memory, age):
    reader = _load("bc250-gddr6-temp-reader")
    path = _write_telemetry(tmp_path / "t.json", {"memory": memory}, age=age)
    relay = reader.relay_external_sample(path)
    assert relay["external_collector"] is True
    assert relay["chips"] == []
    assert relay["patch_active"] is False
    assert relay["blocked_reason"] == "GDDR6_EXTERNAL_NO_SAMPLE"


def test_the_desktop_and_the_reader_read_the_same_contract_the_same_way(tmp_path):
    reader = _load("bc250-gddr6-temp-reader")
    path = _write_telemetry(tmp_path / "t.json", PUBLISHED)
    relay = reader.relay_external_sample(path)
    desktop = leer_memoria_telemetria(path)
    assert desktop["state"] == "active"
    assert [
        (chip["chip"], chip["code"], chip["temperature_c"]) for chip in desktop["chips"]
    ] == [(chip["chip"], chip["code"], chip["temperature_c"]) for chip in relay["chips"]]
    assert (desktop["average_c"], desktop["hotspot_c"], desktop["hotspot_chip"]) == (
        relay["average_c"],
        relay["hotspot_c"],
        relay["hotspot_chip"],
    )


def _read_payload(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_a_read_never_reaches_the_smu_while_the_collector_owns_it(
    tmp_path, runtime, installed, collector, monkeypatch, capsys
):
    reader = _load("bc250-gddr6-temp-reader")
    touched = []
    monkeypatch.setattr(reader, "external_collector_lock", _lock(reader, runtime, installed))
    monkeypatch.setattr(reader, "_sample_smu", lambda *args, **kwargs: touched.append(args))
    monkeypatch.setattr(
        reader,
        "relay_external_sample",
        functools.partial(
            reader.relay_external_sample, _write_telemetry(tmp_path / "t.json", PUBLISHED)
        ),
    )
    assert reader._do_read(tmp_path, os.getuid(), chips_wanted=True) == 0
    payload = _read_payload(capsys)
    assert touched == []
    assert payload["source"] == "bc250-telemetry"
    assert len(payload["chips"]) == 8


def test_a_read_samples_the_smu_itself_when_the_collector_is_idle(
    tmp_path, runtime, installed, monkeypatch, capsys
):
    reader = _load("bc250-gddr6-temp-reader")
    monkeypatch.setattr(reader, "external_collector_lock", _lock(reader, runtime, installed))

    def sample(payload, _repository, _uid, *, chips_wanted, ignore_governor=False):
        payload["patch_active"] = True

    monkeypatch.setattr(reader, "_sample_smu", sample)
    assert reader._do_read(tmp_path, os.getuid(), chips_wanted=True) == 0
    payload = _read_payload(capsys)
    assert payload["patch_active"] is True
    assert "source" not in payload


def test_a_live_session_never_patches_over_a_running_collector(tmp_path, monkeypatch, capsys):
    helper = _load("bc250-gddr6-temp-helper")
    relayed = {
        "external_collector": True,
        "patch_active": True,
        "source": "bc250-telemetry",
        "chips": [{"chip": 0, "code": 38, "temperature_c": 36}],
    }
    reads = []
    applied = []
    monkeypatch.setattr(helper, "_installed_reader", lambda: "/usr/libexec/reader")
    monkeypatch.setattr(
        helper, "_read_once", lambda _r, _repo, _uid, action, **_kw: reads.append(action) or dict(relayed)
    )
    monkeypatch.setattr(helper, "_do_apply", lambda *args, **kwargs: applied.append(args))
    monkeypatch.setattr(helper, "MONITOR_INTERVAL_SECONDS", 0.01)
    assert helper._do_monitor(tmp_path, os.getuid(), os.getgid(), 0.05) == 0
    assert applied == []
    assert reads[0] == "status" and reads.count("read") >= 1
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert lines[0]["source"] == "bc250-telemetry"
    assert lines[-1] == {"session_ended": True}


def test_a_session_keeps_relaying_while_the_collector_is_still_starting(
    tmp_path, monkeypatch, capsys
):
    """No reading yet is not "the patch went away": the session must not end."""
    helper = _load("bc250-gddr6-temp-helper")
    waiting = {"external_collector": True, "patch_active": False, "chips": []}
    reads = []
    monkeypatch.setattr(helper, "_installed_reader", lambda: "/usr/libexec/reader")
    monkeypatch.setattr(
        helper, "_read_once", lambda _r, _repo, _uid, action, **_kw: reads.append(action) or dict(waiting)
    )
    monkeypatch.setattr(helper, "_do_apply", lambda *args, **kwargs: pytest.fail("must not patch"))
    monkeypatch.setattr(helper, "MONITOR_INTERVAL_SECONDS", 0.01)
    helper._do_monitor(tmp_path, os.getuid(), os.getgid(), 0.08)
    assert reads.count("read") >= 2


def test_patching_is_refused_while_the_collector_owns_the_smu(
    tmp_path, runtime, installed, collector, monkeypatch
):
    helper = _load("bc250-gddr6-temp-helper")
    repository = tmp_path / "bc250-memory-temperature"
    repository.mkdir()
    (repository / "SMUPayload.bin").write_bytes(b"\0" * 176)
    script = tmp_path / "patch_smu.py"
    script.write_text("raise SystemExit('must not run')\n")
    ran = []
    monkeypatch.setattr(helper, "bios_version", lambda: "P3.00")
    monkeypatch.setattr(
        helper, "_open_verified_script", lambda *args: os.open(script, os.O_RDONLY)
    )
    monkeypatch.setattr(helper, "external_collector_lock", _lock(helper, runtime, installed))
    monkeypatch.setattr(helper.subprocess, "run", lambda *args, **kwargs: ran.append(args))
    with pytest.raises(RuntimeError, match="GDDR6_EXTERNAL_COLLECTOR"):
        helper._do_apply(repository, os.getuid(), os.getgid())
    assert ran == []


# ----------------------------------------------------------- the SMN index


@pytest.mark.parametrize("helper", BOTH)
def test_the_window_lock_hands_back_the_index_another_client_selected(helper, tmp_path):
    """Cyan locks each 32-bit access, not the index/data pair.

    It can have written 0xB8 and be waiting for the lock to touch 0xBC when
    a helper takes the lock. Leaving 0xB8 on the helper's last register sent
    Cyan's pending write there; the lock now restores what it found.
    """
    module = _load(helper)
    window = tmp_path / "config"
    window.write_bytes(bytes(256))
    cyan_selected = 0x03B10A48  # Queue 0's argument register

    with open(window, "r+b") as handle:
        handle.seek(module.SMN_INDEX_OFFSET)
        handle.write(struct.pack("<I", cyan_selected))
    with module.smn_window_lock(timeout=0.5, path=str(window)):
        # The upstream client moves the index around while it samples.
        with open(window, "r+b") as handle:
            handle.seek(module.SMN_INDEX_OFFSET)
            handle.write(struct.pack("<I", 0x03B10A88))
    index = struct.unpack("<I", window.read_bytes()[0xB8:0xBC])[0]
    assert index == cyan_selected


@pytest.mark.parametrize("helper", BOTH)
def test_the_window_lock_leaves_the_index_alone_when_it_cannot_write(helper, tmp_path):
    module = _load(helper)
    window = tmp_path / "config"
    window.write_bytes(bytes(256))
    window.chmod(0o444)
    if os.access(window, os.W_OK):
        pytest.skip("running as root: every file is writable")
    with module.smn_window_lock(timeout=0.5, path=str(window)):
        pass
    assert window.read_bytes() == bytes(256)


# ------------------------------------------------------------ the governor
#
# Cyan sends two Queue 3 messages while it starts, a test echo and the GPU
# temperature limit, locking each 32-bit word rather than each message. A
# sample taken in the middle mixes the two: the payload is handed Cyan's
# argument as a chip index, or Cyan's limit becomes a chip number. With Fix
# metrics on a kernel without gpu_metrics, Cyan restarts every 15 s -- the
# combination a development BC-250 logged as "queue 3 msg 0x05 timed out -
# SMU wedged".


@pytest.mark.parametrize("helper", BOTH)
@pytest.mark.parametrize(
    "properties, now, expected",
    [
        ({"LoadState": "not-found"}, 100.0, ""),
        ({"LoadState": "loaded", "ActiveState": "inactive", "SubState": "dead"}, 100.0, ""),
        ({"LoadState": "loaded", "ActiveState": "failed", "SubState": "failed"}, 100.0, ""),
        (
            {"LoadState": "loaded", "ActiveState": "activating", "SubState": "start-pre", "NRestarts": "0"},
            100.0,
            "starting",
        ),
        (
            {"LoadState": "loaded", "ActiveState": "activating", "SubState": "auto-restart", "NRestarts": "60"},
            100.0,
            "restarting",
        ),
        (
            {
                "LoadState": "loaded",
                "ActiveState": "active",
                "SubState": "running",
                "NRestarts": "0",
                "ExecMainStartTimestampMonotonic": str(98 * 1_000_000),
            },
            100.0,
            "starting",
        ),
        (
            {
                "LoadState": "loaded",
                "ActiveState": "active",
                "SubState": "running",
                "NRestarts": "0",
                "ExecMainStartTimestampMonotonic": str(40 * 1_000_000),
            },
            100.0,
            "",
        ),
    ],
)
def test_the_governor_is_unsettled_while_it_may_be_mid_message(helper, properties, now, expected):
    module = _load(helper)
    assert module._governor_state(properties, now) == expected


def test_a_read_waits_out_a_governor_that_is_starting(tmp_path, monkeypatch, capsys):
    import contextlib

    reader = _load("bc250-gddr6-temp-reader")
    opened = []
    monkeypatch.setattr(reader, "external_collector_lock", lambda: contextlib.nullcontext(False))
    monkeypatch.setattr(reader, "smn_window_lock", lambda: contextlib.nullcontext())
    monkeypatch.setattr(reader, "governor_unsettled", lambda: "restarting")
    monkeypatch.setattr(reader, "_open_smu", lambda *args: opened.append(args))

    assert reader._do_read(tmp_path, os.getuid(), chips_wanted=True) == 0

    payload = _read_payload(capsys)
    assert opened == []
    assert payload["deferred"] is True
    assert payload["blocked_reason"] == "GDDR6_GOVERNOR_UNSETTLED"
    assert payload["governor_state"] == "restarting"


def test_patching_waits_out_a_governor_that_is_starting(tmp_path, monkeypatch):
    import contextlib

    helper = _load("bc250-gddr6-temp-helper")
    repository = tmp_path / "bc250-memory-temperature"
    repository.mkdir()
    (repository / "SMUPayload.bin").write_bytes(b"\0" * 176)
    script = tmp_path / "patch_smu.py"
    script.write_text("raise SystemExit('must not run')\n")
    ran = []
    monkeypatch.setattr(helper, "bios_version", lambda: "P3.00")
    monkeypatch.setattr(helper, "_open_verified_script", lambda *args: os.open(script, os.O_RDONLY))
    monkeypatch.setattr(helper, "external_collector_lock", lambda: contextlib.nullcontext(False))
    monkeypatch.setattr(helper, "smn_window_lock", lambda: contextlib.nullcontext())
    monkeypatch.setattr(helper, "governor_unsettled", lambda: "starting")
    monkeypatch.setattr(helper.subprocess, "run", lambda *args, **kwargs: ran.append(args))

    with pytest.raises(RuntimeError, match="GDDR6_GOVERNOR_UNSETTLED"):
        helper._do_apply(repository, os.getuid(), os.getgid())
    assert ran == []


def test_a_session_rides_out_a_governor_restart(tmp_path, monkeypatch, capsys):
    helper = _load("bc250-gddr6-temp-helper")
    deferred = {"deferred": True, "patch_active": False, "blocked_reason": "GDDR6_GOVERNOR_UNSETTLED"}
    live = {"patch_active": True, "chips": [{"chip": 0, "code": 38, "temperature_c": 36}]}
    answers = iter([dict(deferred), dict(deferred), dict(live), dict(live), dict(live)])
    monkeypatch.setattr(helper, "_installed_reader", lambda: "/usr/libexec/reader")
    monkeypatch.setattr(helper, "_read_once", lambda *args, **kwargs: next(answers, dict(live)))
    monkeypatch.setattr(helper, "_do_apply", lambda *args, **kwargs: pytest.fail("must not patch blind"))
    monkeypatch.setattr(helper, "MONITOR_INTERVAL_SECONDS", 0.01)

    helper._do_monitor(tmp_path, os.getuid(), os.getgid(), 0.08)

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert any(line.get("deferred") for line in lines)
    assert any(line.get("chips") for line in lines)
    assert lines[-1] == {"session_ended": True}


# ------------------------------------------------- the manual override (Settings)


def test_the_manual_override_reads_through_a_starting_governor(tmp_path, monkeypatch, capsys):
    """Only the governor check is skipped; the window lock is still taken."""
    import contextlib

    reader = _load("bc250-gddr6-temp-reader")
    locks = []

    @contextlib.contextmanager
    def window_lock():
        locks.append("smn")
        yield

    monkeypatch.setattr(reader, "external_collector_lock", lambda: contextlib.nullcontext(False))
    monkeypatch.setattr(reader, "smn_window_lock", window_lock)
    monkeypatch.setattr(reader, "governor_unsettled", lambda: pytest.fail("override must not ask"))

    class FakeSmu:
        def smu_read(self, _register, _count):
            return struct.pack("<I", reader.QUEUE_3_MSG_5_HANDLER)

        def send_message(self, _queue, _message, arguments):
            return (0, 38 + arguments[0])

        def close(self):
            pass

    monkeypatch.setattr(reader, "_open_smu", lambda *args: FakeSmu())

    assert reader._do_read(tmp_path, os.getuid(), chips_wanted=True, ignore_governor=True) == 0
    payload = _read_payload(capsys)
    assert locks == ["smn"]
    assert payload["patch_active"] is True and len(payload["chips"]) == 8
    assert not payload.get("deferred")


def test_the_manual_override_patches_through_a_starting_governor(tmp_path, monkeypatch):
    import contextlib

    helper = _load("bc250-gddr6-temp-helper")
    repository = tmp_path / "bc250-memory-temperature"
    repository.mkdir()
    (repository / "SMUPayload.bin").write_bytes(b"\0" * 176)
    script = tmp_path / "patch_smu.py"
    script.write_text("print('patched')\n")
    monkeypatch.setattr(helper, "bios_version", lambda: "P3.00")
    monkeypatch.setattr(helper, "_open_verified_script", lambda *args: os.open(script, os.O_RDONLY))
    monkeypatch.setattr(helper, "external_collector_lock", lambda: contextlib.nullcontext(False))
    monkeypatch.setattr(helper, "smn_window_lock", lambda: contextlib.nullcontext())
    monkeypatch.setattr(helper, "governor_unsettled", lambda: "starting")
    ran = []
    monkeypatch.setattr(
        helper.subprocess,
        "run",
        lambda *args, **kwargs: ran.append(args) or subprocess.CompletedProcess(args, 0, "", ""),
    )

    assert helper._do_apply(repository, os.getuid(), os.getgid(), ignore_governor=True) == 0
    assert len(ran) == 1


def test_the_manual_override_still_refuses_another_firmware(tmp_path, monkeypatch):
    helper = _load("bc250-gddr6-temp-helper")
    monkeypatch.setattr(helper, "bios_version", lambda: "P5.00")
    with pytest.raises(RuntimeError, match="GDDR6_FIRMWARE_UNSUPPORTED"):
        helper._do_apply(tmp_path, os.getuid(), os.getgid(), ignore_governor=True)


def test_a_session_passes_the_override_to_every_read(tmp_path, monkeypatch, capsys):
    helper = _load("bc250-gddr6-temp-helper")
    calls = []
    live = {"patch_active": True, "chips": [{"chip": 0, "code": 38, "temperature_c": 36}]}

    def read_once(*args, **kwargs):
        calls.append(kwargs.get("ignore_governor"))
        return dict(live)

    monkeypatch.setattr(helper, "_installed_reader", lambda: "/usr/libexec/reader")
    monkeypatch.setattr(helper, "_read_once", read_once)
    monkeypatch.setattr(helper, "MONITOR_INTERVAL_SECONDS", 0.01)

    helper._do_monitor(tmp_path, os.getuid(), os.getgid(), 0.03, ignore_governor=True)
    capsys.readouterr()
    assert calls and all(calls)
