"""Full launch orchestration with fixture identity, source and storage only.

No real privileged identity, SteamOS files, hardware writes or network access.
The actual verifier, cache, workspace, lock, dispatcher and Bash child run.
"""
import fcntl
import hashlib
import io
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from bc250cc.infrastructure import steamos_real_toolkit as provider
from bc250cc.infrastructure import steamos_real_toolkit_runtime as runtime
from bc250cc.infrastructure.steamos_real_toolkit_recovery import (
    REVERT_ALL_STEPS,
    REVERT_FLAG_BODY,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def launch(tmp_path, monkeypatch):
    home, state, installed = tmp_path / 'user', tmp_path / 'state', tmp_path / 'installed'
    home.mkdir()
    (installed / 'lib').mkdir(parents=True)
    for relative, source, mode in [
        ('bc250-steamos-toolkit-check', 'scripts/system/check-steamos-toolkit-conflicts.py', 0o755),
        ('lib/bc250_steamos_toolkit_runtime.zip', 'privileged/lib/bc250_steamos_toolkit_runtime.zip', 0o644),
    ]:
        target = installed / relative
        target.write_bytes((ROOT / source).read_bytes())
        target.chmod(mode)
    names = {action.function for action in provider.ACTIONS} | set(provider.GUARDED_FUNCTIONS)
    functions = []
    for name in sorted(names):
        if name == 'run_revert_all':
            functions.append(name + '() {\n' + ''.join('    ' + step + '\n' for step in REVERT_ALL_STEPS) + '}\n')
        elif name == 'run_status':
            functions.append('run_status() { printf "%s\\n" "$AUTO" "$SUDO_USER" > "$BC250_FIXTURE_TRACE"; return 23; }')
        else:
            functions.append(name + '() { :; }')
    source = ('#!/bin/bash\nset -euo pipefail\n' + '\n'.join(functions)
              + '\nensure_desktop_shortcut() { :; }\n' + provider._GUARD_BOUNDARY
              + 'if [[ "${1:-}" == --revert-all ]]; then\n' + REVERT_FLAG_BODY + 'fi\n'
              + 'show_menu() { echo UNEXPECTED_MENU; }\n' + provider._MAIN_LOOP + 'break\ndone\n').encode()
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:gz') as archive:
        for relative, payload in [('start.sh', source), ('external/demo.txt', b'reviewed fixture')]:
            member = tarfile.TarInfo('bc250-steamos-real-toolkit-' + provider.REVISION + '/' + relative)
            member.size, member.mode = len(payload), 0o755
            archive.addfile(member, io.BytesIO(payload))
    payload = stream.getvalue()
    response, downloads = [payload], []
    def fetch(url, **kwargs):
        downloads.append(url)
        return io.BytesIO(response[0])
    def storage(path):
        assert path == state
        path.mkdir(exist_ok=True)
    monkeypatch.setattr(runtime, '_require_invoking_user', lambda: SimpleNamespace(pw_name='canonical-user', pw_dir=str(home)))
    monkeypatch.setattr(runtime, 'prepare_state_root', storage)
    monkeypatch.setattr(runtime, 'STATE_ROOT', state)
    monkeypatch.setattr(provider, 'INSTALLED_RUNTIME_ROOT', installed)
    monkeypatch.setattr(provider, 'ENTRYPOINT_SHA256', hashlib.sha256(source).hexdigest())
    monkeypatch.setattr(provider, 'ARCHIVE_SHA256', hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(runtime.urllib.request, 'urlopen', fetch)
    monkeypatch.setattr(runtime.shutil, 'disk_usage', lambda path: SimpleNamespace(free=2 * 1024**3))
    monkeypatch.setattr(runtime, '_root_mode', lambda: 'enabled')
    trace = tmp_path / 'executed'
    monkeypatch.setenv('BC250_FIXTURE_TRACE', str(trace))
    monkeypatch.setenv('SUDO_USER', 'untrusted-environment-name')
    monkeypatch.setenv('AUTO', '1')
    return SimpleNamespace(state=state, trace=trace, downloads=downloads, response=response, payload=payload)


def test_fresh_launch_verifies_dispatches_and_refreshes_without_losing_build_cache(launch):
    assert runtime.run_action('verify') == 23
    assert launch.trace.read_text().splitlines() == ['0', 'canonical-user']
    assert launch.downloads == [provider.ARCHIVE_URL]
    workspace = launch.state / 'workspace'
    assert (workspace / '.bc250cc-provider.json').is_file()
    assert (launch.state / 'runtime/bc250-steamos-toolkit-check').is_file()
    assert (launch.state / 'runtime/lib/bc250_steamos_toolkit_runtime.zip').is_file()
    (workspace / 'start.sh').write_text('exit 99\n')
    build = workspace / 'external/compiled.o'
    build.write_bytes(b'preserved fixture build')
    launch.trace.unlink()
    assert runtime.run_action('verify') == 23
    assert launch.trace.read_text().splitlines() == ['0', 'canonical-user']
    assert build.read_bytes() == b'preserved fixture build'
    assert launch.downloads == [provider.ARCHIVE_URL], 'A verified cache must not download again'
    assert not list(launch.state.glob('.verify-*'))


def test_concurrent_launch_stops_before_cache_download_or_execution(launch):
    launch.state.mkdir()
    with (launch.state / '.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match='Another Real Toolkit action'):
            runtime.run_action('verify')
        assert launch.downloads == [] and not launch.trace.exists()
        assert not (launch.state / 'runtime').exists()
    assert runtime.run_action('verify') == 23


def test_bad_download_cannot_execute_and_does_not_hold_the_lock(launch):
    launch.response[0] = b'corrupted download'
    with pytest.raises(ValueError, match='SHA-256'):
        runtime.run_action('verify')
    assert not launch.trace.exists() and not (launch.state / 'workspace').exists()
    assert not list(launch.state.glob('*.tar.gz'))
    launch.response[0] = launch.payload
    assert runtime.run_action('verify') == 23
    assert len(launch.downloads) == 2


@pytest.mark.parametrize('effective_uid,sudo_uid,os_id,error', [
    (1000, '1000', 'steamos', PermissionError),
    (0, '0', 'steamos', PermissionError),
    (0, '1000', 'arch', ValueError),
])
def test_identity_boundary_rejects_before_hardware_or_preparation(
    tmp_path, monkeypatch, effective_uid, sudo_uid, os_id, error,
):
    monkeypatch.setattr(runtime.os, 'geteuid', lambda: effective_uid)
    monkeypatch.setenv('SUDO_UID', sudo_uid)
    monkeypatch.setattr(runtime.pwd, 'getpwuid', lambda uid: SimpleNamespace(pw_dir=str(tmp_path)))
    monkeypatch.setattr(runtime.platform, 'freedesktop_os_release', lambda: {'ID': os_id, 'ID_LIKE': 'steamos'})
    monkeypatch.setattr(runtime, 'require_bc250_hardware', lambda: pytest.fail('Hardware validation must not run'))
    with pytest.raises(error):
        runtime._require_invoking_user()


def test_valid_identity_is_looked_up_by_uid_and_requires_actual_bc250_hardware(tmp_path, monkeypatch):
    expected = SimpleNamespace(pw_dir=str(tmp_path), pw_name='canonical-user')
    monkeypatch.setattr(runtime.os, 'geteuid', lambda: 0)
    monkeypatch.setenv('SUDO_UID', '1000')
    looked_up, hardware = [], []
    monkeypatch.setattr(runtime.pwd, 'getpwuid', lambda uid: looked_up.append(uid) or expected)
    monkeypatch.setattr(runtime.platform, 'freedesktop_os_release', lambda: {'ID': 'steamos'})
    monkeypatch.setattr(runtime, 'require_bc250_hardware', lambda: hardware.append(True))
    assert runtime._require_invoking_user() is expected
    assert looked_up == [1000] and hardware == [True]
