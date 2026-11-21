"""Reading, remembering and restoring SteamOS' read-only root, with the real command's habits."""
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from bc250cc.infrastructure import steamos_root_guard as guard


def _runner(stdout='', status=0, stderr='', calls=None):
    def run(command, **kwargs):
        if calls is not None:
            calls.append(command)
        return SimpleNamespace(returncode=status, stdout=stdout, stderr=stderr)
    return run


@pytest.mark.parametrize('stdout,status,state', [
    ('disabled\n', 1, 'disabled'),     # SteamOS: writable root exits 1
    ('enabled\n', 0, 'enabled'),
    ('enabled\n', 1, 'enabled'),
    ('DISABLED', 0, 'disabled'),
    ('', 1, 'unknown'),
    ('Segmentation fault', 139, 'unknown'),
])
def test_the_state_is_read_from_the_text_whatever_the_exit_status(stdout, status, state):
    assert guard.read_root(runner=_runner(stdout, status), sleep=lambda _s: None).state == state


def test_an_unclear_answer_is_asked_again_once_then_reported_with_what_it_said():
    calls = []
    reading = guard.read_root(runner=_runner('???', 3, calls=calls), sleep=lambda _s: None)
    assert reading.state == 'unknown' and reading.status == 3 and reading.detail == '???'
    assert len(calls) == 2


def test_a_slow_first_answer_does_not_make_the_state_unknown():
    answers = iter([subprocess.TimeoutExpired('steamos-readonly', 10), 'disabled'])

    def run(command, **kwargs):
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return SimpleNamespace(returncode=1, stdout=answer, stderr='')

    assert guard.read_root(runner=run, sleep=lambda _s: None).state == 'disabled'


def test_a_missing_command_is_unavailable_not_unknown():
    def run(command, **kwargs):
        raise FileNotFoundError(command[0])

    reading = guard.read_root(runner=run)
    assert reading.state == 'unavailable'
    assert 'not found' in guard.explain_unreadable(reading)


def test_the_refusal_quotes_what_the_command_said_so_it_can_be_diagnosed():
    reading = guard.RootReading('unknown', 3, 'something unexpected')
    message = guard.explain_unreadable(reading)
    assert 'was not started' in message and "'something unexpected'" in message and 'exit status 3' in message


def test_the_state_is_looked_up_at_call_time_so_it_can_be_replaced(monkeypatch):
    monkeypatch.setattr(guard.subprocess, 'run', _runner('enabled', 0))
    assert guard.read_root().state == 'enabled'


# --- the note that outlives the process ----------------------------------------------------

def test_the_original_state_is_written_before_anything_changes_and_is_world_readable(tmp_path):
    guard.write_session(tmp_path, initial='enabled', action='acpi-install')
    note = guard.read_session(tmp_path)
    assert note['initial'] == 'enabled' and note['action'] == 'acpi-install' and note['pid'] == os.getpid()
    assert (tmp_path / guard.SESSION_FILE).stat().st_mode & 0o777 == 0o644
    assert not list(tmp_path.glob('.session-*'))
    guard.clear_session(tmp_path)
    assert guard.read_session(tmp_path) is None
    guard.clear_session(tmp_path)  # idempotent


@pytest.mark.parametrize('content', ['', 'not json', '[]', '{"initial": "banana"}', '{"initial": null}'])
def test_a_damaged_note_is_ignored_not_trusted(tmp_path, content):
    (tmp_path / guard.SESSION_FILE).write_text(content)
    assert guard.read_session(tmp_path) is None


def test_an_unknown_state_is_never_recorded(tmp_path):
    with pytest.raises(ValueError):
        guard.write_session(tmp_path, initial='unknown', action='x')


def test_a_note_belongs_to_a_live_process_only_when_pid_boot_and_start_agree(tmp_path):
    guard.write_session(tmp_path, initial='enabled', action='x')
    mine = guard.read_session(tmp_path)
    assert guard.session_running(mine)
    assert not guard.session_running({**mine, 'pid': 999_999_999})            # process gone
    assert not guard.session_running({**mine, 'boot_id': 'another-boot'})     # rebooted since
    assert not guard.session_running({**mine, 'start_ticks': '1'})            # PID reused later
    assert not guard.session_running(None) and not guard.session_running({'pid': 'x'})


DEAD = {'initial': 'enabled', 'action': 'gpu', 'pid': 999_999_999, 'boot_id': guard.boot_id()}


def test_a_leftover_unlock_from_a_dead_run_is_not_adopted_as_the_users_choice():
    state, note = guard.initial_state(guard.RootReading('disabled'), DEAD)
    assert state == 'enabled' and 'ended without locking' in note and 'gpu' in note


@pytest.mark.parametrize('current,session', [
    ('disabled', None),                                          # nothing recorded
    ('enabled', DEAD),                                           # already protected again
    ('disabled', {**DEAD, 'initial': 'disabled'}),               # the user's own unlock
    ('unknown', DEAD),
])
def test_without_a_leak_the_current_state_is_the_one_to_give_back(current, session):
    assert guard.initial_state(guard.RootReading(current), session) == (current, '')


def test_a_running_toolkit_session_is_not_mistaken_for_a_leak(tmp_path):
    guard.write_session(tmp_path, initial='enabled', action='x')
    live = guard.read_session(tmp_path)
    assert guard.initial_state(guard.RootReading('disabled'), live) == ('disabled', '')
    assert not guard.interrupted(guard.RootReading('disabled'), live)


def test_the_interface_sees_an_interrupted_run_and_a_running_one(tmp_path):
    guard.write_session(tmp_path, initial='enabled', action='video-install', pid=999_999_999)
    summary = guard.session_summary(tmp_path, guard.RootReading('disabled'))
    assert summary == {'running': False, 'action': 'video-install', 'restore_pending': True}
    assert guard.session_summary(tmp_path, guard.RootReading('enabled'))['restore_pending'] is False
    assert guard.session_summary(tmp_path / 'nothing') == {'running': False, 'action': '', 'restore_pending': False}


# --- /var --------------------------------------------------------------------------------

@pytest.mark.parametrize('free_mb,level', [(10, 'critical'), (39, 'critical'), (40, 'low'),
                                          (249, 'low'), (250, 'ok'), (4000, 'ok')])
def test_var_space_levels_match_the_guards_the_other_workflows_use(free_mb, level):
    stats = SimpleNamespace(f_bavail=free_mb * 1024, f_frsize=1024)
    assert guard.var_space(lambda _path: stats) == (free_mb, level)


def test_unreadable_var_space_never_blocks():
    def broken(_path):
        raise OSError

    assert guard.var_space(broken) == (None, 'unknown')


@pytest.mark.parametrize('free_mb,level', [(0, 'low'), (167, 'low'), (299, 'low'), (300, 'ok'), (4000, 'ok')])
def test_root_space_only_warns(free_mb, level):
    stats = SimpleNamespace(f_bavail=free_mb * 1024, f_frsize=1024)
    seen = []
    assert guard.root_space(lambda path: seen.append(path) or stats) == (free_mb, level)
    assert seen == ['/']


def test_unreadable_root_space_is_unknown():
    def broken(_path):
        raise OSError

    assert guard.root_space(broken) == (None, 'unknown')


def test_the_note_is_plain_json(tmp_path):
    guard.write_session(tmp_path, initial='disabled', action='y')
    assert set(json.loads((tmp_path / guard.SESSION_FILE).read_text())) == {
        'initial', 'action', 'pid', 'start_ticks', 'boot_id', 'started'}
    assert isinstance(Path(tmp_path), Path)
