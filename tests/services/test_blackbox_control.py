"""The black box from the window: is it recording, start it, stop it, read it, start it with the session."""

from __future__ import annotations

import os
import signal
import sys
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from bc250cc.infrastructure import blackbox, blackbox_control
from bc250cc.shared.errors import ActionNeeded

# The real scan, kept before the fixture swaps it for one that sees nothing.
REAL_RECORDER_PIDS = blackbox.recorder_pids
SAMPLE = "12:00:01.250 2000Mhz busy=99% t_gpu=71 t_cpu=60 v=1050 w=140 rpm=fan1:2400,fan2:2300 cpu=3500 mem=9000"


@pytest.fixture()
def box(tmp_path, monkeypatch):
    """A state directory of its own and a BC-250 that is there."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(blackbox, "boot_id", lambda: "boot-now")
    monkeypatch.setattr(blackbox, "Sensors", lambda: SimpleNamespace(device="/sys/fake", describe=lambda: "fake"))
    # Never the recorders that may really be running on the machine of the tests.
    monkeypatch.setattr(blackbox, "recorder_pids", lambda **kw: [])
    directory = blackbox.log_directory()
    directory.mkdir(parents=True)
    return directory


def _alive(directory: Path, tmp_path: Path, pid: int = 4242) -> Path:
    """A pid file whose process, in a fake /proc, is a recorder."""
    (directory / blackbox.PID_FILE).write_text(f"{pid} boot-now\n", encoding="ascii")
    proc = tmp_path / "proc" / str(pid)
    proc.mkdir(parents=True)
    (proc / "cmdline").write_bytes(b"/usr/bin/python3\0-m\0bc250cc.infrastructure.blackbox\0")
    return tmp_path / "proc"


def test_a_sample_line_becomes_columns():
    row = blackbox.parse_sample(SAMPLE)
    assert row == {
        "time": "12:00:01.250", "clock": "2000Mhz", "busy": "99%", "t_gpu": "71", "t_cpu": "60",
        "volts": "1050", "watts": "140", "rpm": "fan1:2400,fan2:2300", "cpu": "3500", "mem": "9000",
    }


@pytest.mark.parametrize("line", ["# boot=a start=1", "# stopped 2026-10-28", "", "garbage"])
def test_anything_that_is_not_a_sample_is_skipped(line):
    assert blackbox.parse_sample(line) is None


def test_a_sample_with_missing_sensors_keeps_its_columns():
    row = blackbox.parse_sample("12:00:01.250 - busy=- t_gpu=- t_cpu=- v=- w=- rpm=- cpu=- mem=-")
    assert row["clock"] == "-" and row["t_gpu"] == "-" and row["rpm"] == "-"


def test_a_pid_file_of_a_dead_process_is_not_recording(box, tmp_path):
    (box / blackbox.PID_FILE).write_text("999999 boot-now\n", encoding="ascii")
    assert blackbox.running_pid(box, proc=tmp_path / "proc") is None


def test_a_pid_the_system_reused_for_something_else_is_not_recording(box, tmp_path):
    proc = _alive(box, tmp_path)
    (proc / "4242" / "cmdline").write_bytes(b"/usr/bin/firefox\0")
    assert blackbox.running_pid(box, proc=proc) is None


def test_the_recorder_is_seen_while_it_runs(box, tmp_path):
    proc = _alive(box, tmp_path)
    assert blackbox.running_pid(box, proc=proc) == 4242


def test_status_reads_the_last_session_newest_first(box, monkeypatch):
    (box / "current.log").write_text(
        "# boot=old-boot start=x\n12:00:01.000 1000Mhz busy=1% t_gpu=50\n12:00:01.250 2000Mhz busy=99% t_gpu=71\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(blackbox_control, "systemd_available", lambda *a, **k: False)
    old = (box / "current.log").stat().st_mtime - 3600  # written long ago: nothing records now
    os.utime(box / "current.log", (old, old))
    state = blackbox_control.status(directory=box)
    assert state["supported"] is True and state["running"] is False
    assert state["state"] == "cut-off"
    assert "CUT OFF" in state["state_text"]
    assert [row["time"] for row in state["rows"]] == ["12:00:01.250", "12:00:01.000"]


def test_without_a_recording_status_says_so_and_has_no_rows(box, monkeypatch):
    monkeypatch.setattr(blackbox_control, "systemd_available", lambda *a, **k: False)
    state = blackbox_control.status(directory=box)
    assert state["state"] == "none" and state["rows"] == []


def test_without_the_gpu_it_is_not_supported(box, monkeypatch):
    monkeypatch.setattr(blackbox, "Sensors", lambda: SimpleNamespace(device="", describe=lambda: ""))
    monkeypatch.setattr(blackbox_control, "systemd_available", lambda *a, **k: False)
    assert blackbox_control.status(directory=box)["supported"] is False
    with pytest.raises(RuntimeError, match="1002:13fe"):
        blackbox_control.start(directory=box)


def test_starting_under_systemd_hands_the_recorder_to_the_user_manager(box, monkeypatch):
    monkeypatch.setattr(blackbox_control, "systemd_available", lambda *a, **k: True)
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        # Nothing runs yet: is-active says so; systemd-run starts the recorder.
        return SimpleNamespace(returncode=3 if "is-active" in command else 0, stdout="", stderr="")

    result = blackbox_control.start(directory=box, runner=runner)
    assert result == {"started": True, "via": "systemd"}
    command = next(call for call in calls if call[0] == "systemd-run")
    assert command[:3] == ["systemd-run", "--user", f"--unit={blackbox_control.UNIT}"]
    assert any(part.startswith("--setenv=PYTHONPATH=") for part in command)
    assert command[-1] in {"black-box", "bc250cc.infrastructure.blackbox"}


def test_a_systemd_failure_is_reported_with_its_reason(box, monkeypatch):
    monkeypatch.setattr(blackbox_control, "systemd_available", lambda *a, **k: True)
    runner = lambda command, **kw: SimpleNamespace(  # noqa: E731
        returncode=3 if "is-active" in command else 1, stdout="", stderr="Failed to connect to bus"
    )
    with pytest.raises(RuntimeError, match="Failed to connect to bus"):
        blackbox_control.start(directory=box, runner=runner)


def test_without_systemd_the_recorder_is_a_detached_process(box, monkeypatch):
    monkeypatch.setattr(blackbox_control, "systemd_available", lambda *a, **k: False)
    seen = {}
    blackbox_control.start(directory=box, popen=lambda command, **kwargs: seen.update(command=command, **kwargs))
    assert seen["start_new_session"] is True
    assert seen["stdin"] == subprocess.DEVNULL and seen["stdout"] == subprocess.DEVNULL
    assert "PYTHONPATH" in seen["env"]


def test_starting_twice_does_not_start_a_second_recorder(box, tmp_path, monkeypatch):
    proc = _alive(box, tmp_path)
    monkeypatch.setattr(blackbox, "running_pid", lambda directory=None, proc=proc: 4242)
    result = blackbox_control.start(directory=box, popen=lambda *a, **k: pytest.fail("started twice"))
    assert result == {"started": False, "reason": "already-recording"}


def _recorders(monkeypatch, *pids):
    """Recorders that run until they get a signal; ``kill`` ends them."""
    alive = list(pids)
    monkeypatch.setattr(blackbox, "recorder_pids", lambda **kw: list(alive))
    monkeypatch.setattr(blackbox, "running_pid", lambda directory=None, **kw: alive[0] if alive else None)
    sent = []

    def kill(pid, sig):
        sent.append((pid, sig))
        alive.remove(pid)

    return sent, kill


def test_stopping_without_systemd_ends_the_process_the_way_ctrl_c_does(box, monkeypatch):
    monkeypatch.setattr(blackbox_control, "systemd_available", lambda *a, **k: False)
    sent, kill = _recorders(monkeypatch, 4242)
    result = blackbox_control.stop(directory=box, kill=kill, wait=1.0)
    # SIGINT: every release of the recorder closes its file properly on it.
    assert sent == [(4242, signal.SIGINT)]
    assert result == {"stopped": True}


def test_every_recorder_is_stopped_not_only_the_first(box, monkeypatch):
    """A terminal one and the button's can run at once, both writing the same file."""
    monkeypatch.setattr(blackbox_control, "systemd_available", lambda *a, **k: False)
    sent, kill = _recorders(monkeypatch, 4242, 5151)
    result = blackbox_control.stop(directory=box, kill=kill, wait=1.0)
    assert sorted(pid for pid, _sig in sent) == [4242, 5151]
    assert result == {"stopped": True}


def test_a_systemd_recording_is_asked_with_ctrl_c_first_and_stopped_only_if_it_stays(box, monkeypatch):
    monkeypatch.setattr(blackbox_control, "systemd_available", lambda *a, **k: True)
    monkeypatch.setattr(blackbox, "running_pid", lambda directory=None, **kw: None)
    calls = []
    active = {"on": True}

    def runner(command, **kwargs):
        calls.append(command[2:])
        if command[2:4] == ["is-active", "--quiet"]:
            return SimpleNamespace(returncode=0 if active["on"] else 3, stdout="", stderr="")
        if command[2] == "stop":
            active["on"] = False
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    result = blackbox_control.stop(directory=box, runner=runner, kill=lambda *a: pytest.fail("killed behind systemd"), wait=0.2)
    assert ["kill", "--signal=SIGINT", blackbox_control.UNIT_FILE_NAME] in calls
    assert ["stop", blackbox_control.UNIT_FILE_NAME] in calls
    assert result == {"stopped": True}


def test_a_systemd_recording_that_ends_on_ctrl_c_is_not_stopped_again(box, monkeypatch):
    monkeypatch.setattr(blackbox_control, "systemd_available", lambda *a, **k: True)
    monkeypatch.setattr(blackbox, "running_pid", lambda directory=None, **kw: None)
    calls = []
    active = {"on": True}

    def runner(command, **kwargs):
        calls.append(command[2:])
        if command[2:4] == ["is-active", "--quiet"]:
            return SimpleNamespace(returncode=0 if active["on"] else 3, stdout="", stderr="")
        if command[2] == "kill":
            active["on"] = False
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    blackbox_control.stop(directory=box, runner=runner, wait=1.0)
    assert ["stop", blackbox_control.UNIT_FILE_NAME] not in calls


def test_stopping_when_nothing_records_does_nothing(box, monkeypatch):
    monkeypatch.setattr(blackbox_control, "systemd_available", lambda *a, **k: False)
    assert blackbox_control.stop(directory=box) == {"stopped": False, "reason": "not-recording"}


def test_a_recording_with_no_process_to_find_says_how_to_stop_it(box, monkeypatch):
    monkeypatch.setattr(blackbox_control, "systemd_available", lambda *a, **k: False)
    (box / "current.log").write_text("# boot=boot-now start=x\n" + SAMPLE + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Ctrl\\+C"):
        blackbox_control.stop(directory=box)


# ----------------------------------------------- recorders of any release, any way started

@pytest.mark.parametrize("argv, expected", [
    (["python3", "-m", "frontends.cli", "black-box"], True),
    (["/usr/bin/python3", "/usr/bin/bc250-control-center-cli", "black-box"], True),
    (["/usr/bin/bc250-control-center-cli", "black-box"], True),
    (["/usr/bin/python3", "-m", "bc250cc.infrastructure.blackbox"], True),
    (["tail", "-f", "/home/u/.local/state/bc250-control-center/black-box/current.log"], False),
    (["vim", "black-box"], False),
    (["python3", "-m", "frontends.desktop.main"], False),
    ([], False),
])
def test_a_recorder_is_told_by_its_command_line(argv, expected):
    assert blackbox._is_recorder(argv) is expected


def _fake_proc(tmp_path, entries):
    proc = tmp_path / "fakeproc"
    for pid, argv in entries.items():
        (proc / str(pid)).mkdir(parents=True)
        (proc / str(pid) / "cmdline").write_bytes(b"\0".join(part.encode() for part in argv) + b"\0")
    return proc


def test_a_recorder_from_an_older_release_without_a_pid_file_is_found(tmp_path):
    proc = _fake_proc(tmp_path, {
        4242: ["python3", "-m", "frontends.cli", "black-box"],
        4343: ["/usr/bin/bc250-control-center-cli", "black-box"],
        4444: ["tail", "-f", "/x/black-box/current.log"],
    })
    assert blackbox.recorder_pids(proc=proc) == [4242, 4343]


def test_running_pid_finds_an_older_recorder_that_wrote_no_pid_file(box, tmp_path, monkeypatch):
    """The reported case: the window said "Stopped" while the board was being recorded."""
    proc = _fake_proc(tmp_path, {4242: ["/usr/bin/bc250-control-center-cli", "black-box"]})
    monkeypatch.setattr(blackbox, "recorder_pids", lambda **kw: REAL_RECORDER_PIDS(proc=proc))
    assert not (box / blackbox.PID_FILE).exists()
    assert blackbox.running_pid(box, proc=proc) == 4242


def test_a_systemd_recording_counts_as_recording_without_a_pid_file(box, monkeypatch):
    monkeypatch.setattr(blackbox_control, "systemd_available", lambda *a, **k: True)
    runner = lambda command, **kw: SimpleNamespace(returncode=0, stdout="", stderr="")  # noqa: E731
    assert blackbox_control.status(directory=box, runner=runner)["running"] is True


def test_a_file_written_a_moment_ago_counts_as_recording(box, monkeypatch):
    monkeypatch.setattr(blackbox_control, "systemd_available", lambda *a, **k: False)
    (box / "current.log").write_text("# boot=boot-now start=x\n" + SAMPLE + "\n", encoding="utf-8")
    assert blackbox_control.status(directory=box)["running"] is True


def test_a_file_that_ended_with_stopped_is_not_recording(box, monkeypatch):
    monkeypatch.setattr(blackbox_control, "systemd_available", lambda *a, **k: False)
    (box / "current.log").write_text("# boot=boot-now start=x\n" + SAMPLE + "\n# stopped 2026-10-29\n", encoding="utf-8")
    assert blackbox_control.status(directory=box)["running"] is False


def test_an_old_file_with_no_recorder_is_not_recording(box, monkeypatch):
    monkeypatch.setattr(blackbox_control, "systemd_available", lambda *a, **k: False)
    path = box / "current.log"
    path.write_text("# boot=boot-now start=x\n" + SAMPLE + "\n", encoding="utf-8")
    old = path.stat().st_mtime - 60
    os.utime(path, (old, old))
    assert blackbox_control.status(directory=box)["running"] is False


def test_the_recorder_that_is_started_is_this_code_not_the_installed_cli():
    """An installed 1.21.3 recorder wrote no pid file, so the window could not see it."""
    command = blackbox_control.recorder_command()
    assert command[:2] == [sys.executable, "-m"] and command[2] == "bc250cc.infrastructure.blackbox"


def test_a_missing_load_reading_is_a_dash():
    assert blackbox.parse_sample("12:00:01.250 1000Mhz busy=-% t_gpu=53")["busy"] == "-"


# ------------------------------------------------------- start with the session

def _systemctl_log(monkeypatch):
    calls = []

    def runner(command, **kwargs):
        calls.append(command[2:])
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(blackbox_control, "systemd_available", lambda *a, **k: True)
    return calls, runner


def test_start_with_the_session_installs_and_enables_a_user_service(box, tmp_path, monkeypatch):
    calls, runner = _systemctl_log(monkeypatch)
    state = blackbox_control.set_autostart(True, home=tmp_path, runner=runner)
    unit = blackbox_control.unit_path(tmp_path)
    text = unit.read_text(encoding="utf-8")
    assert text.startswith(blackbox_control.UNIT_MARKER)
    assert "ExecStart=" in text and "WantedBy=default.target" in text and "Restart=on-failure" in text
    assert ["daemon-reload"] in calls and ["enable", "--now", blackbox_control.UNIT_FILE_NAME] in calls
    assert state["enabled"] is True and state["foreign"] is False


def test_turning_it_off_removes_only_its_own_service(box, tmp_path, monkeypatch):
    calls, runner = _systemctl_log(monkeypatch)
    blackbox_control.set_autostart(True, home=tmp_path, runner=runner)
    blackbox_control.set_autostart(False, home=tmp_path, runner=runner)
    assert not blackbox_control.unit_path(tmp_path).exists()
    assert ["disable", "--now", blackbox_control.UNIT_FILE_NAME] in calls


def test_a_service_somebody_else_wrote_is_never_touched(box, tmp_path, monkeypatch):
    calls, runner = _systemctl_log(monkeypatch)
    unit = blackbox_control.unit_path(tmp_path)
    unit.parent.mkdir(parents=True)
    unit.write_text("[Service]\nExecStart=/bin/true\n", encoding="utf-8")
    with pytest.raises(ActionNeeded, match="not managed by Control Center"):
        blackbox_control.set_autostart(True, home=tmp_path, runner=runner)
    with pytest.raises(ActionNeeded):
        blackbox_control.set_autostart(False, home=tmp_path, runner=runner)
    assert unit.read_text(encoding="utf-8") == "[Service]\nExecStart=/bin/true\n"
    assert calls == []


def test_without_systemd_starting_with_the_session_is_a_notice(box, tmp_path, monkeypatch):
    monkeypatch.setattr(blackbox_control, "systemd_available", lambda *a, **k: False)
    with pytest.raises(ActionNeeded, match="needs systemd"):
        blackbox_control.set_autostart(True, home=tmp_path)


def test_the_unit_names_the_recorder_and_where_this_code_lives(box):
    text = blackbox_control._unit_text()
    assert "black-box" in text or "bc250cc.infrastructure.blackbox" in text
    assert 'Environment="PYTHONPATH=' in text


def test_the_recorder_writes_a_pid_file_while_it_runs_and_removes_it_after(box, monkeypatch):
    seen = []

    class FakeSensors:
        device = "/sys/fake"

        def describe(self):
            return "fake"

        def sample(self):
            seen.append((box / blackbox.PID_FILE).read_text(encoding="ascii").split()[0])
            return "12:00:00.000 1000Mhz busy=1%"

    monkeypatch.setattr(blackbox, "Sensors", FakeSensors)
    assert blackbox.record(interval=0, samples=2) == 0
    assert seen == [str(os.getpid())] * 2
    assert not (box / blackbox.PID_FILE).exists()
    assert "# stopped" in (box / "current.log").read_text(encoding="utf-8")


def test_a_second_recorder_does_not_start_while_one_runs(box, monkeypatch, capsys):
    monkeypatch.setattr(blackbox, "running_pid", lambda directory=None, **kw: 4242)
    monkeypatch.setattr(blackbox, "Sensors", lambda: SimpleNamespace(device="/sys/fake", describe=lambda: "x"))
    assert blackbox.record(interval=0, samples=1) == 3
