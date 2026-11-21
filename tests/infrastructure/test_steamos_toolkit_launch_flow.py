"""Full launch orchestration with fixture identity, source and storage only.

No real privileged identity, SteamOS files, hardware writes or network access.
The actual verifier, cache, workspace, lock, dispatcher and Bash child run.
"""
import fcntl
import io
import subprocess
import tarfile
import urllib.error
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
REVISION = '0123456789abcdef0123456789abcdef01234567'
NEWER = 'fedcba9876543210fedcba9876543210fedcba98'


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
            functions.append('run_status() { printf "%s\\n" "$AUTO" "$SUDO_USER" > "$BC250_FIXTURE_TRACE"; return "${BC250_FIXTURE_STATUS:-0}"; }')
        else:
            functions.append(name + '() { :; }')
    source = ('#!/bin/bash\nset -euo pipefail\n' + '\n'.join(functions)
              + '\nensure_desktop_shortcut() { :; }\n' + provider._GUARD_BOUNDARY
              + 'if [[ "${1:-}" == --revert-all ]]; then\n' + REVERT_FLAG_BODY + 'fi\n'
              + 'show_menu() { echo UNEXPECTED_MENU; }\n' + provider._MAIN_LOOP + 'break\ndone\n').encode()
    def archive_for(revision):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w:gz') as archive:
            for relative, payload in [('start.sh', source), ('external/demo.txt', b'fixture ' + revision.encode()),
                                      ('external/bc250_smu_oc/bc250_apply.py', b'')]:
                member = tarfile.TarInfo('bc250-steamos-real-toolkit-' + revision + '/' + relative)
                member.size, member.mode = len(payload), 0o755
                archive.addfile(member, io.BytesIO(payload))
        return stream.getvalue()
    # What upstream currently serves: the newest commit and that commit's archive.
    upstream = SimpleNamespace(revision=REVISION, offline=False, corrupt=False)
    downloads, lookups = [], []
    def fetch(request, **kwargs):
        url = getattr(request, 'full_url', request)
        if upstream.offline:
            raise urllib.error.URLError('offline')
        if url == provider.REVISION_API:
            lookups.append(url)
            return io.BytesIO(upstream.revision.encode() + b'\n')
        downloads.append(url)
        revision = url.rsplit('/', 1)[1]
        return io.BytesIO(b'corrupted download' if upstream.corrupt else archive_for(revision))
    def storage(path):
        assert path == state
        path.mkdir(exist_ok=True)
    monkeypatch.setattr(runtime, '_require_invoking_user', lambda: SimpleNamespace(pw_name='canonical-user', pw_dir=str(home)))
    monkeypatch.setattr(runtime, 'prepare_state_root', storage)
    monkeypatch.setattr(runtime, 'STATE_ROOT', state)
    monkeypatch.setattr(provider, 'INSTALLED_RUNTIME_ROOT', installed)
    monkeypatch.setattr(runtime.urllib.request, 'urlopen', fetch)
    monkeypatch.setattr(runtime.shutil, 'disk_usage', lambda path: SimpleNamespace(free=2 * 1024**3))
    monkeypatch.setattr(runtime, '_root_mode', lambda attempts=1: 'enabled')
    monkeypatch.setattr(runtime, '_read_root', lambda attempts=2: runtime.guard.RootReading('enabled', 0, 'enabled'))
    monkeypatch.setattr(runtime.guard, 'var_space', lambda: (4096, 'ok'))
    monkeypatch.setattr(runtime.guard, 'root_space', lambda: (2048, 'ok'))
    trace = tmp_path / 'executed'
    monkeypatch.setenv('BC250_FIXTURE_TRACE', str(trace))
    monkeypatch.setenv('SUDO_USER', 'untrusted-environment-name')
    monkeypatch.setenv('AUTO', '1')
    return SimpleNamespace(state=state, trace=trace, downloads=downloads, lookups=lookups, upstream=upstream,
                           monkeypatch=monkeypatch)


def test_fresh_launch_resolves_the_latest_commit_and_refreshes_without_losing_build_cache(launch):
    assert runtime.run_action('verify') == 0
    assert launch.trace.read_text().splitlines() == ['0', 'canonical-user']
    assert launch.downloads == [provider.archive_url(REVISION)]
    workspace = launch.state / 'workspace'
    assert REVISION in (workspace / '.bc250cc-provider.json').read_text()
    assert (launch.state / 'runtime/bc250-steamos-toolkit-check').is_file()
    assert (launch.state / 'runtime/lib/bc250_steamos_toolkit_runtime.zip').is_file()
    (workspace / 'start.sh').write_text('exit 99\n')
    build = workspace / 'external/compiled.o'
    build.write_bytes(b'preserved fixture build')
    launch.trace.unlink()
    assert runtime.run_action('verify') == 0
    assert launch.trace.read_text().splitlines() == ['0', 'canonical-user']
    assert build.read_bytes() == b'preserved fixture build'
    assert launch.downloads == [provider.archive_url(REVISION)], 'The same commit is not downloaded again'
    assert len(launch.lookups) == 2, 'Every run asks upstream for its newest commit'
    assert not list(launch.state.glob('.verify-*'))


def test_a_newer_upstream_commit_replaces_the_old_source_and_its_leftovers(launch):
    assert runtime.run_action('verify') == 0
    workspace = launch.state / 'workspace'
    (workspace / 'external/removed-upstream.sh').write_text('dropped by the new revision')
    launch.upstream.revision = NEWER
    assert runtime.run_action('verify') == 0
    assert launch.downloads == [provider.archive_url(REVISION), provider.archive_url(NEWER)]
    assert NEWER in (workspace / '.bc250cc-provider.json').read_text()
    assert not (workspace / 'external/removed-upstream.sh').exists()
    assert [path.name for path in launch.state.glob('*.tar.gz')] == [NEWER + '.tar.gz']


def test_a_failed_action_clears_the_cache_so_the_next_attempt_starts_from_scratch(launch, capsys):
    launch.monkeypatch.setenv('BC250_FIXTURE_STATUS', '23')
    assert runtime.run_action('verify') == 23
    assert not (launch.state / 'workspace').exists()
    assert not list(launch.state.glob('*.tar.gz'))
    assert 'cache was cleared' in capsys.readouterr().out
    assert (launch.state / 'runtime/bc250-steamos-toolkit-check').is_file(), 'the guard runtime stays'
    launch.upstream.revision = NEWER  # upstream published a fix meanwhile
    launch.monkeypatch.setenv('BC250_FIXTURE_STATUS', '0')
    assert runtime.run_action('verify') == 0
    assert launch.downloads == [provider.archive_url(REVISION), provider.archive_url(NEWER)]


@pytest.mark.parametrize('status', [130, 143])
def test_an_interrupt_keeps_the_cache(launch, status):
    launch.monkeypatch.setenv('BC250_FIXTURE_STATUS', str(status))
    assert runtime.run_action('verify') == status
    assert (launch.state / 'workspace/start.sh').is_file()
    assert list(launch.state.glob('*.tar.gz'))


def test_without_network_the_copy_already_downloaded_is_used(launch):
    assert runtime.run_action('verify') == 0
    launch.upstream.offline = True
    launch.trace.unlink()
    assert runtime.run_action('verify') == 0
    assert launch.trace.exists() and len(launch.downloads) == 1


def test_without_network_and_without_a_copy_nothing_runs(launch):
    launch.upstream.offline = True
    with pytest.raises(RuntimeError, match='no earlier copy'):
        runtime.run_action('verify')
    assert not launch.trace.exists()


def test_a_changed_upstream_shape_refuses_to_run_and_clears_the_cache(launch):
    original = provider.prepare_entrypoint
    launch.monkeypatch.setattr(provider, 'prepare_entrypoint',
                               lambda source: original(source.replace(provider._MAIN_LOOP.encode(), b'')))
    with pytest.raises(ValueError, match='main-loop'):
        runtime.run_action('verify')
    assert not launch.trace.exists()
    assert not (launch.state / 'workspace').exists() and not list(launch.state.glob('*.tar.gz'))


def test_concurrent_launch_stops_before_cache_download_or_execution(launch):
    launch.state.mkdir()
    with (launch.state / '.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match='Another Real Toolkit action'):
            runtime.run_action('verify')
        assert launch.downloads == [] and launch.lookups == [] and not launch.trace.exists()
        assert not (launch.state / 'runtime').exists()
    assert runtime.run_action('verify') == 0


def test_bad_download_cannot_execute_clears_the_cache_and_does_not_hold_the_lock(launch):
    launch.upstream.corrupt = True
    with pytest.raises(Exception):
        runtime.run_action('verify')
    assert not launch.trace.exists() and not (launch.state / 'workspace').exists()
    assert not list(launch.state.glob('*.tar.gz'))
    launch.upstream.corrupt = False
    assert runtime.run_action('verify') == 0
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


# --- the read-only root around an action -------------------------------------------------------

def _root(launch, mode, *, toolkit_leaves=None, switch_ok=True):
    """A root that behaves like SteamOS' (``disabled`` exits 1), and a toolkit that changes it.

    ``toolkit_leaves`` is what the upstream script leaves behind when it starts
    (it unlocks the system itself, and turns protection back on blindly).
    """
    state, calls = {'mode': mode}, []
    real_run, real_popen = runtime.subprocess.run, runtime.subprocess.Popen

    def run(command, *args, **kwargs):
        if command and command[0] == runtime.READONLY_COMMAND:
            calls.append(command[1])
            if command[1] in ('enable', 'disable') and switch_ok:
                state['mode'] = 'enabled' if command[1] == 'enable' else 'disabled'
            return SimpleNamespace(returncode=0 if switch_ok else 1, stdout='', stderr='')
        return real_run(command, *args, **kwargs)

    def popen(command, *args, **kwargs):
        if toolkit_leaves and '--bc250cc-action' in list(command):
            state['mode'] = toolkit_leaves
        return real_popen(command, *args, **kwargs)

    mp = launch.monkeypatch
    mp.setattr(runtime.subprocess, 'run', run)
    mp.setattr(runtime.subprocess, 'Popen', popen)
    mp.setattr(runtime, '_read_root', lambda attempts=2: runtime.guard.RootReading(state['mode'], 1, state['mode']))
    mp.setattr(runtime, '_root_mode', lambda attempts=1: state['mode'])
    mp.setattr(runtime.time, 'sleep', lambda _seconds: None)
    return state, calls


def _watch_the_note(launch):
    """What the note said at the moment the original state was verified back."""
    seen, original = [], runtime.guard.clear_session

    def clear(root):
        seen.append(runtime.guard.read_session(root))
        original(root)

    launch.monkeypatch.setattr(runtime.guard, 'clear_session', clear)
    return seen


def test_a_protected_root_the_toolkit_unlocks_is_locked_again_and_the_note_is_removed(launch, capsys):
    state, calls = _root(launch, 'enabled', toolkit_leaves='disabled')
    seen = _watch_the_note(launch)
    assert runtime.run_action('verify') == 0
    assert state['mode'] == 'enabled' and calls == ['enable']
    assert seen[0]['initial'] == 'enabled' and seen[0]['action'] == 'verify', 'written before the toolkit ran'
    assert runtime.guard.read_session(launch.state) is None
    out = capsys.readouterr().out
    assert 'protected (read-only)' in out and 'on again' in out and 'system update' in out


def test_a_root_the_user_had_already_unlocked_stays_unlocked_even_if_the_toolkit_locks_it(launch, capsys):
    state, calls = _root(launch, 'disabled', toolkit_leaves='enabled')
    assert runtime.run_action('verify') == 0
    assert state['mode'] == 'disabled' and calls == ['disable']
    assert 'already writable' in capsys.readouterr().out


def test_a_toolkit_that_leaves_the_root_alone_causes_no_switching(launch):
    _state, calls = _root(launch, 'enabled')
    assert runtime.run_action('verify') == 0
    assert calls == []


def test_an_unlock_left_by_a_run_that_died_is_locked_again_not_adopted(launch, capsys):
    """Power cut, killed terminal or reboot: no finally ran, the note is all that is left."""
    state, calls = _root(launch, 'disabled')
    runtime.guard.write_session(launch.state, initial='enabled', action='video-install', pid=999_999_999)
    assert runtime.run_action('verify') == 0
    assert state['mode'] == 'enabled' and calls == ['enable']
    assert runtime.guard.read_session(launch.state) is None
    assert 'ended without locking the system again' in capsys.readouterr().out


def test_when_the_root_cannot_be_restored_the_note_stays_and_the_command_is_given(launch):
    state, calls = _root(launch, 'enabled', toolkit_leaves='disabled', switch_ok=False)
    with pytest.raises(RuntimeError, match=r'sudo steamos-readonly enable'):
        runtime.run_action('verify')
    assert state['mode'] == 'disabled' and calls == ['enable'] * 3, 'retried, then gave up'
    assert runtime.guard.read_session(launch.state)['initial'] == 'enabled'


def test_an_unreadable_root_stops_before_anything_is_downloaded_and_says_why(launch):
    launch.monkeypatch.setattr(runtime, '_read_root',
                               lambda attempts=2: runtime.guard.RootReading('unknown', 3, 'weird output'))
    with pytest.raises(RuntimeError, match="exit status 3.*'weird output'"):
        runtime.run_action('verify')
    assert launch.downloads == [] and launch.lookups == [] and not launch.trace.exists()


def test_a_full_var_stops_before_anything_is_downloaded(launch):
    _root(launch, 'enabled')
    launch.monkeypatch.setattr(runtime.guard, 'var_space', lambda: (12, 'critical'))
    with pytest.raises(RuntimeError, match=r'(?s)only 12 MB free.*pacman -Scc'):
        runtime.run_action('verify')
    assert launch.downloads == [] and not launch.trace.exists()


def test_a_low_var_warns_and_still_runs(launch, capsys):
    _root(launch, 'enabled')
    launch.monkeypatch.setattr(runtime.guard, 'var_space', lambda: (120, 'low'))
    assert runtime.run_action('verify') == 0
    assert '[WARN] /var has only 120 MB free' in capsys.readouterr().out


def test_an_ownership_refusal_keeps_the_cache_and_says_why(launch, capsys):
    """The checker's refusal (79) is not an upstream bug; re-downloading changes nothing."""
    assert runtime.run_action('verify') == 0
    launch.monkeypatch.setenv('BC250_FIXTURE_STATUS', str(provider.CONFLICT_STATUS))
    assert runtime.run_action('verify') == provider.CONFLICT_STATUS
    out = capsys.readouterr().out
    assert 'The toolkit cache was kept' in out and 'cache was cleared' not in out
    assert list(launch.state.glob('*.tar.gz')) and (launch.state / 'workspace' / 'start.sh').is_file()


def test_a_nearly_full_system_partition_warns_and_still_runs(launch, capsys):
    """SteamOS' 5 GB root arrives nearly full; package installs there can stop half way."""
    _root(launch, 'enabled')
    launch.monkeypatch.setattr(runtime.guard, 'root_space', lambda: (167, 'low'))
    assert runtime.run_action('verify') == 0
    assert '[WARN] The SteamOS system partition (/) has only 167 MB free' in capsys.readouterr().out


def test_the_toolkits_own_logs_survive_the_cache_clear_after_a_failure(launch, capsys):
    assert runtime.run_action('verify') == 0
    logs = launch.state / 'workspace' / 'logs'
    logs.mkdir()
    (logs / 'bc250-toolkit-error-1.log').write_text('what the toolkit said')
    launch.monkeypatch.setenv('BC250_FIXTURE_STATUS', '23')
    assert runtime.run_action('verify') == 23
    kept = launch.state / runtime.FAILURE_LOGS / 'bc250-toolkit-error-1.log'
    assert kept.read_text() == 'what the toolkit said'
    assert not (launch.state / 'workspace').exists()
    assert str(launch.state / runtime.FAILURE_LOGS) in capsys.readouterr().out


def test_the_launcher_command_checks_for_a_sudo_password_first_and_is_valid_shell(tmp_path):
    command = provider.launch_command('verify')
    assert 'bc250_require_password' in command
    assert command.index('bc250_require_password') < command.index('sudo /usr/bin/python3 -I')
    assert command.rstrip().endswith("bc250-steamos-toolkit verify")
    script = tmp_path / 'launch.sh'
    script.write_text('#!/bin/bash\n' + command + '\n')
    assert subprocess.run(['bash', '-n', str(script)], capture_output=True).returncode == 0
