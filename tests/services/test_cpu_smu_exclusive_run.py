"""A CPU tuning run must not share the SMU mailbox with another sampler.

Two testers hit ``smu returned status 0x00`` on a different message each time:
the SMU has one mailbox, every message is several register writes, and the
vendor payload locks each 32-bit access rather than each message. A GDDR6
sample, from BC250-Telemetry's memory collector or from Control Center's own
live monitor, landed between two steps of a message and cleared the response
the payload was polling for. Disabling the memory collector and rebooting made
the same run pass.

The tuning helper now refuses while the collector runs and holds a run lock for
its whole length; the GDDR6 helpers take that lock shared, one sample at a time.
"""

from __future__ import annotations

import fcntl
import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "privileged/helpers"
SAMPLERS = ["bc250-gddr6-temp-reader", "bc250-gddr6-temp-helper"]

HOLDER = (
    "import fcntl,os,sys;"
    "fd=os.open(sys.argv[1], os.O_RDWR|os.O_CREAT, 0o644);"
    "fcntl.flock(fd, fcntl.LOCK_EX);"
    "print('held', flush=True);"
    "sys.stdin.read()"
)


def _load(name: str):
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), str(HELPERS / name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cpu():
    return _load("bc250-cpu-smu-helper")


@pytest.fixture
def collector_lock(tmp_path):
    """A stand-in for bc250-memory.service holding its SMU lock."""
    path = tmp_path / "smu.lock"
    holder = subprocess.Popen(
        [sys.executable, "-c", HOLDER, str(path)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "held"
        yield path
    finally:
        holder.stdin.close()
        holder.wait(timeout=5)


def test_a_running_memory_collector_refuses_the_tuning_before_the_smu_is_touched(cpu, tmp_path, collector_lock):
    with pytest.raises(cpu.SmuInUse) as caught:
        with cpu.smu_exclusive_run(collector_lock=collector_lock, run_lock=tmp_path / "run.lock", wait=0.1):
            pytest.fail("the tuning ran while the collector held the SMU")
    assert "bc250-memory.service" in caught.value.what
    assert "disable --now bc250-memory.service" in caught.value.how


def test_a_collector_that_is_installed_but_not_running_is_no_obstacle(cpu, tmp_path):
    lock = tmp_path / "smu.lock"
    lock.write_text("")  # left behind by an earlier run; nobody holds it
    with cpu.smu_exclusive_run(collector_lock=lock, run_lock=tmp_path / "run.lock", wait=0.1):
        pass
    with cpu.smu_exclusive_run(collector_lock=tmp_path / "absent.lock", run_lock=tmp_path / "run.lock", wait=0.1):
        pass


def _hold_shared(path: Path, seconds: float):
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(fd, fcntl.LOCK_SH)

    def release():
        time.sleep(seconds)
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

    thread = threading.Thread(target=release)
    thread.start()
    return thread


def test_a_sample_already_in_flight_is_waited_for(cpu, tmp_path):
    run_lock = tmp_path / "run.lock"
    thread = _hold_shared(run_lock, 0.3)
    started = time.monotonic()
    with cpu.smu_exclusive_run(collector_lock=tmp_path / "none", run_lock=run_lock, wait=5):
        waited = time.monotonic() - started
    thread.join()
    assert 0.2 <= waited < 3


def test_a_sampler_that_never_lets_go_ends_in_a_plain_explanation(cpu, tmp_path):
    run_lock = tmp_path / "run.lock"
    thread = _hold_shared(run_lock, 0.6)
    with pytest.raises(cpu.SmuInUse) as caught:
        with cpu.smu_exclusive_run(collector_lock=tmp_path / "none", run_lock=run_lock, wait=0.1):
            pytest.fail("the tuning started while a sample held the SMU")
    thread.join()
    assert "GDDR6 live monitoring" in caught.value.how


@pytest.mark.parametrize("sampler", SAMPLERS)
def test_the_gddr6_helpers_stand_aside_for_the_whole_run_and_resume_after(cpu, tmp_path, monkeypatch, sampler):
    module = _load(sampler)
    run_lock = tmp_path / "run.lock"
    monkeypatch.setattr(module, "SMU_RUN_LOCK_PATH", str(run_lock))
    window = tmp_path / "config"
    window.write_bytes(b"\0" * 256)

    with cpu.smu_exclusive_run(collector_lock=tmp_path / "none", run_lock=run_lock, wait=0.1):
        with pytest.raises(RuntimeError, match="SMU_BUSY: CPU overclocking"):
            with module.smu_run_share(str(run_lock)):
                pytest.fail("a sample ran in the middle of a tuning run")
        with pytest.raises(RuntimeError, match="SMU_BUSY: CPU overclocking"):
            with module.smn_window_lock(timeout=0.1, path=str(window)):
                pytest.fail("a sample took the SMU window in the middle of a tuning run")

    with module.smu_run_share(str(run_lock)):
        pass  # the run is over: sampling resumes


@pytest.mark.parametrize("sampler", SAMPLERS)
def test_a_sample_in_flight_is_not_a_reason_for_another_sample_to_fail(tmp_path, sampler):
    module = _load(sampler)
    run_lock = tmp_path / "run.lock"
    with module.smu_run_share(str(run_lock)):
        with module.smu_run_share(str(run_lock)):
            pass  # shared: two samplers do not exclude each other


@pytest.mark.parametrize("sampler", SAMPLERS)
def test_where_the_lock_cannot_be_made_sampling_behaves_as_before(tmp_path, sampler):
    module = _load(sampler)
    with module.smu_run_share(str(tmp_path / "no-such-directory" / "run.lock")):
        pass


def test_only_the_actions_that_message_the_smu_are_guarded(cpu, monkeypatch, capsys):
    entered = []

    class Guard:
        def __enter__(self):
            entered.append(True)

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(cpu, "require_root_and_payload", lambda: None)
    monkeypatch.setattr(cpu, "smu_exclusive_run", lambda: Guard())
    seen = []
    monkeypatch.setattr(cpu, "_dispatch", lambda action, args: seen.append(action) or 0)

    for action in ("detect", "verify-scale", "apply-live", "detect-qam", "apply-qam-scale"):
        assert cpu.main([action]) == 0
    guarded = len(entered)
    for action in ("qam-status", "install-boot", "apply-config", "disable-boot", "install-qam"):
        assert cpu.main([action]) == 0

    assert guarded == 5 and len(entered) == 5
    assert len(seen) == 10


def test_an_obstacle_is_explained_in_the_helpers_own_words_and_nothing_runs(cpu, monkeypatch, capsys):
    monkeypatch.setattr(cpu, "require_root_and_payload", lambda: None)

    def busy():
        raise cpu.SmuInUse("what is in the way", "what to do about it")

    class Raises:
        def __enter__(self):
            busy()

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(cpu, "smu_exclusive_run", lambda: Raises())
    monkeypatch.setattr(cpu, "_dispatch", lambda *_: pytest.fail("the action ran"))

    assert cpu.main(["detect", "3800", "1170", "90", "x"]) == 44

    out = capsys.readouterr()
    assert "[ERROR] what is in the way" in out.out
    assert "[ERROR] what to do about it" in out.out
    assert "SMU_IN_USE" in out.err
