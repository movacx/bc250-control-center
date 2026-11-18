"""Real child-process cancellation with fixture files instead of root writes."""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from bc250cc.infrastructure import steamos_real_toolkit_runtime as runtime


def _wait_for(path, process):
    deadline = time.monotonic() + 5
    while not path.exists():
        assert process.poll() is None, 'Fixture launcher exited before the expected event'
        assert time.monotonic() < deadline, 'Timed out waiting for ' + str(path)
        time.sleep(0.01)


@pytest.mark.parametrize('number', [signal.SIGINT, signal.SIGTERM, signal.SIGHUP])
def test_parent_only_signal_waits_for_child_before_restoring_root(tmp_path, number):
    mode = tmp_path / 'mode'
    mode.write_text('enabled')
    child = tmp_path / 'child.py'
    child.write_text('''import os, signal, sys, time
from pathlib import Path
folder = Path(sys.argv[1])
def stop(number, frame):
    (folder / 'received').write_text(str(number))
for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(number, stop)
(folder / 'mode').write_text('disabled')
(folder / 'ready').write_text(str(os.getpid()))
while not (folder / 'release').exists():
    time.sleep(0.01)
(folder / 'finished').touch()
''')
    parent = tmp_path / 'parent.py'
    parent.write_text('''import sys
from pathlib import Path
from types import SimpleNamespace
from bc250cc.infrastructure import steamos_real_toolkit_runtime as runtime
folder = Path(sys.argv[1])
runtime._root_mode = lambda: (folder / 'mode').read_text()
def restore(command, **kwargs):
    assert command == [runtime.READONLY_COMMAND, 'enable']
    assert (folder / 'finished').exists(), 'Root restored before child completion'
    (folder / 'mode').write_text('enabled')
    return SimpleNamespace(returncode=0)
runtime.subprocess.run = restore
raise SystemExit(runtime.run_preserving_root_mode([sys.executable, str(folder / 'child.py'), str(folder)]))
''')
    environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2] / 'src'))
    process = subprocess.Popen([sys.executable, str(parent), str(tmp_path)],
                               env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        _wait_for(tmp_path / 'ready', process)
        process.send_signal(number)
        _wait_for(tmp_path / 'received', process)
        assert (tmp_path / 'received').read_text() == str(number)
        assert process.poll() is None
        assert mode.read_text() == 'disabled'
        (tmp_path / 'release').touch()
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == 128 + number, (stdout, stderr)
        assert mode.read_text() == 'enabled'
        assert 'Traceback' not in stderr
    finally:
        (tmp_path / 'release').touch()
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)


def test_signal_handlers_are_restored_after_execution():
    numbers = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    previous = {number: signal.getsignal(number) for number in numbers}
    with runtime._interactive_signal_relay() as execute:
        assert execute(['/usr/bin/true']) == 0
    assert {number: signal.getsignal(number) for number in numbers} == previous


def test_unexpected_wait_failure_stops_and_reaps_child_before_propagation(monkeypatch):
    events = []
    def wait():
        events.append('wait')
        if len(events) == 1:
            raise RuntimeError('fixture wait failed')
        return 0
    child = SimpleNamespace(wait=wait, poll=lambda: None, terminate=lambda: events.append('terminate'))
    monkeypatch.setattr(runtime.subprocess, 'Popen', lambda command: child)
    with pytest.raises(RuntimeError, match='fixture wait failed'), runtime._interactive_signal_relay() as execute:
        execute(['fixture'])
    assert events == ['wait', 'terminate', 'wait']


def test_signal_exit_status_is_normalized_without_claiming_success(monkeypatch):
    monkeypatch.setattr(runtime.subprocess, 'Popen',
                        lambda command: SimpleNamespace(wait=lambda: -signal.SIGTERM))
    with runtime._interactive_signal_relay() as execute:
        assert execute(['fixture']) == 143
