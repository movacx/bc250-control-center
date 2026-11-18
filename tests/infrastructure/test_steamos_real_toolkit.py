"""Real Toolkit dispatch runs only explicit functions, retaining user choices."""
import hashlib
import io
import os
import subprocess
import tarfile

import pytest

from bc250cc.infrastructure import steamos_real_toolkit as toolkit
from bc250cc.infrastructure.steamos_real_toolkit_recovery import (
    REVERT_ALL_STEPS,
    REVERT_FLAG_BODY,
)


def _fixture():
    functions = "\n".join(f'{a.function}() {{ printf "%s:%s\\n" {a.key} "$AUTO"; }}'
                          for a in toolkit.ACTIONS)
    functions = functions.replace('run_revert_all() { printf "%s:%s\\n" revert-all "$AUTO"; }',
                                  'run_revert_all() {\n' + ''.join('    ' + step + '\n'
                                                                 for step in REVERT_ALL_STEPS) + '}\n')
    extra = '\n'.join(f'{name}() {{ :; }}' for name in toolkit.GUARDED_FUNCTIONS
                      if name not in {a.function for a in toolkit.ACTIONS})
    return ("#!/bin/bash\nset -euo pipefail\n" + functions + '\n' + extra +
            '\nensure_desktop_shortcut() { :; }\n' + toolkit._GUARD_BOUNDARY +
            'if [[ "${1:-}" == --revert-all ]]; then\n    AUTO=1\n' + REVERT_FLAG_BODY + 'fi\n' +
            '\nshow_menu() { echo WRONG_MENU; }\n' + toolkit._MAIN_LOOP + 'break\ndone\n').encode()


@pytest.mark.parametrize("action", toolkit.ACTIONS, ids=lambda action: action.key)
def test_each_action_dispatches_without_automatically_answering_prompts(action, tmp_path, monkeypatch):
    monkeypatch.setattr(toolkit, 'CONFLICT_CHECK_COMMAND', ('/usr/bin/true',))
    functions = "\n".join(f'{a.function}() {{ printf "%s:%s\\n" {a.key} "$AUTO"; }}'
                          for a in toolkit.ACTIONS)
    command = 'set -euo pipefail\n' + functions + '\n' + toolkit.dispatch_shell()
    if action.key == 'launch-coach-install':
        command = ('REAL_USER=fixture; SCRIPT_DIR=/fixture; '
                   'sudo() { printf "%s\\n" "$*"; };\n') + command
    if action.key == 'decky-plugin-only':
        (tmp_path / 'homebrew/plugins').mkdir(parents=True)
        command = 'REAL_HOME=' + str(tmp_path) + ';\n' + command
    if action.key in toolkit.CEC_ACTIONS:
        command = ('REAL_USER=fixture; REAL_HOME=/fixture/home; SCRIPT_DIR=/fixture; '
                   'id() { echo 42; }; runuser() { printf "%s\\n" "$*"; };\n') + command
    result = subprocess.run(['bash', '-c', command, 'adapter', '--bc250cc-action', action.key],
                            capture_output=True, text=True, timeout=5, env=os.environ | {"AUTO": "1"})
    assert result.returncode == 0, result.stderr
    expected = ('-u fixture -H /usr/bin/bash /fixture/extras/bc250-launch-coach/install.sh'
                if action.key == 'launch-coach-install' else
                'decky-install:0' if action.key == 'decky-plugin-only' else action.key + ':0')
    if action.key in toolkit.CEC_ACTIONS:
        expected = ('--pty -u fixture -- env HOME=/fixture/home XDG_RUNTIME_DIR=/run/user/42 '
                    'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/42/bus /usr/bin/bash '
                    '/fixture/external/bc250-steamos/bc250-cec.sh ' + ' '.join(toolkit.CEC_ACTIONS[action.key]))
    assert result.stdout.strip() == expected


@pytest.mark.parametrize("arguments", [[], ['verify', 'extra'], ['verify; echo unsafe'], ['$(id)']])
def test_unknown_or_extra_arguments_cannot_dispatch(arguments):
    result = subprocess.run(['bash', '-c', toolkit.dispatch_shell(), 'adapter', '--bc250cc-action', *arguments],
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 64 and not result.stdout


def test_action_failure_is_preserved():
    result = subprocess.run(['bash', '-c', 'run_status() { return 23; };\n' + toolkit.dispatch_shell(),
                             'adapter', '--bc250cc-action', 'verify'], timeout=5)
    assert result.returncode == 23


def test_plugin_only_action_cannot_bootstrap_decky(tmp_path):
    command = ('REAL_HOME=' + str(tmp_path) + '; '
               'install_toolkit_steamos_control_plugin() { echo UNEXPECTED_INSTALL; };\n' + toolkit.dispatch_shell())
    result = subprocess.run(['bash', '-c', command, 'adapter', '--bc250cc-action', 'decky-plugin-only'],
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 69
    assert 'UNEXPECTED_INSTALL' not in result.stdout
    assert 'already be installed' in result.stderr


def test_entrypoint_is_attested_before_it_is_adapted(monkeypatch):
    source = _fixture()
    with pytest.raises(ValueError, match='differs'):
        toolkit.prepare_entrypoint(source)
    monkeypatch.setattr(toolkit, 'ENTRYPOINT_SHA256', hashlib.sha256(source).hexdigest())
    adapted = toolkit.prepare_entrypoint(source)
    assert b'bc250cc_original_run_cpu_governor()' in adapted
    assert toolkit._guard_shell().encode() in adapted
    assert subprocess.run(['bash', '-n'], input=adapted, capture_output=True).returncode == 0


def test_missing_upstream_action_cannot_silently_reduce_the_integration(monkeypatch):
    source = _fixture().replace(b'install_core_unlock()', b'renamed_core_unlock()')
    monkeypatch.setattr(toolkit, 'ENTRYPOINT_SHA256', hashlib.sha256(source).hexdigest())
    with pytest.raises(ValueError, match='install_core_unlock'):
        toolkit.prepare_entrypoint(source)


@pytest.mark.parametrize('action', ['cpu-install', 'install-all', 'manual'])
def test_guard_stops_direct_bulk_and_nested_calls_before_the_original_body(monkeypatch, tmp_path, action):
    source = _fixture().replace(b'run_install_manual() {', b'run_install_manual() { run_cpu_governor || return $?;')
    monkeypatch.setattr(toolkit, 'ENTRYPOINT_SHA256', hashlib.sha256(source).hexdigest())
    # Stand-in conflict checker returns the real guard's conflict exit status.
    checker = tmp_path / 'check.sh'
    checker.write_text('echo NATIVE_CONFLICT >&2\nexit 79\n')
    monkeypatch.setattr(toolkit, 'CONFLICT_CHECK_COMMAND', ('/usr/bin/bash', str(checker)))
    result = subprocess.run(['bash', '-s', '--', '--bc250cc-action', action],
                            input=toolkit.prepare_entrypoint(source), capture_output=True)
    assert result.returncode == 79
    assert b'NATIVE_CONFLICT' in result.stderr
    assert result.stdout == b''


def test_nonconflicting_component_still_runs_its_original_action(monkeypatch, tmp_path):
    source = _fixture()
    monkeypatch.setattr(toolkit, 'ENTRYPOINT_SHA256', hashlib.sha256(source).hexdigest())
    checker = tmp_path / 'check.sh'
    checker.write_text('test "$1" = cpu\n')
    monkeypatch.setattr(toolkit, 'CONFLICT_CHECK_COMMAND', ('/usr/bin/bash', str(checker)))
    result = subprocess.run(['bash', '-s', '--', '--bc250cc-action', 'cpu-install'],
                            input=toolkit.prepare_entrypoint(source), capture_output=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == b'cpu-install:0\n'


def test_recovery_flag_before_main_loop_also_uses_the_component_guard(monkeypatch, tmp_path):
    source = _fixture()
    monkeypatch.setattr(toolkit, 'ENTRYPOINT_SHA256', hashlib.sha256(source).hexdigest())
    checker = tmp_path / 'check.sh'
    checker.write_text('echo RECOVERY_CONFLICT >&2\nexit 79\n')
    monkeypatch.setattr(toolkit, 'CONFLICT_CHECK_COMMAND', ('/usr/bin/bash', str(checker)))
    result = subprocess.run(['bash', '-s', '--', '--revert-all'],
                            input=toolkit.prepare_entrypoint(source), capture_output=True)
    assert result.returncode == 79
    assert result.stdout == b''
    assert b'RECOVERY_CONFLICT' in result.stderr
    assert b'command not found' not in result.stderr


def test_cec_mutation_stops_before_entering_the_user_session_on_native_conflict(monkeypatch, tmp_path):
    checker = tmp_path / 'check.sh'
    checker.write_text('exit 79\n')
    monkeypatch.setattr(toolkit, 'CONFLICT_CHECK_COMMAND', ('/usr/bin/bash', str(checker)))
    shell = ('REAL_USER=fixture; REAL_HOME=/fixture; SCRIPT_DIR=/fixture; '
             'id() { echo 42; }; runuser() { echo USER_SESSION; };\n' + toolkit.dispatch_shell())
    result = subprocess.run(['bash', '-c', shell, 'adapter', '--bc250cc-action', 'cec-wake-install'],
                            capture_output=True, text=True)
    assert result.returncode == 79 and not result.stdout
    status = subprocess.run(['bash', '-c', shell, 'adapter', '--bc250cc-action', 'cec-status'],
                            capture_output=True, text=True)
    assert status.returncode == 0 and status.stdout.strip() == 'USER_SESSION'


def _archive(tmp_path, monkeypatch, malicious=None):
    source = _fixture()
    monkeypatch.setattr(toolkit, 'ENTRYPOINT_SHA256', hashlib.sha256(source).hexdigest())
    archive = tmp_path / 'source.tar.gz'
    prefix = 'bc250-steamos-real-toolkit-' + toolkit.REVISION
    with tarfile.open(archive, 'w:gz') as bundle:
        member = tarfile.TarInfo(prefix + '/start.sh')
        member.size, member.mode = len(source), 0o4755
        bundle.addfile(member, io.BytesIO(source))
        if malicious:
            bundle.addfile(malicious)
    monkeypatch.setattr(toolkit, 'ARCHIVE_SHA256', hashlib.sha256(archive.read_bytes()).hexdigest())
    return archive


def test_snapshot_is_complete_and_atomic_and_strips_special_permissions(tmp_path, monkeypatch):
    archive = _archive(tmp_path, monkeypatch)
    target = tmp_path / 'snapshot'
    toolkit.prepare_snapshot(archive, target)
    assert (target / 'start.sh').stat().st_mode & 0o7777 == 0o755
    assert '--bc250cc-action' in (target / 'start.sh').read_text()
    assert toolkit.REVISION in (target / '.bc250cc-provider.json').read_text()
    with pytest.raises(ValueError, match='already exists'):
        toolkit.prepare_snapshot(archive, target)


@pytest.mark.parametrize('kind', ['traversal', 'absolute', 'symlink', 'hardlink', 'duplicate'])
def test_bad_archive_never_publishes_a_partial_snapshot(tmp_path, monkeypatch, kind):
    prefix = 'bc250-steamos-real-toolkit-' + toolkit.REVISION
    names = {'traversal': prefix + '/../escape', 'absolute': '/escape',
             'symlink': prefix + '/link', 'hardlink': prefix + '/hard', 'duplicate': prefix + '/start.sh'}
    member = tarfile.TarInfo(names[kind])
    if kind in {'symlink', 'hardlink'}:
        member.type = tarfile.SYMTYPE if kind == 'symlink' else tarfile.LNKTYPE
        member.linkname = '/escape'
    archive = _archive(tmp_path, monkeypatch, member)
    target = tmp_path / 'snapshot'
    with pytest.raises(ValueError):
        toolkit.prepare_snapshot(archive, target)
    assert not target.exists()
    assert not list(tmp_path.glob('.real-toolkit-stage-*'))


def test_unverified_archive_creates_no_staging_tree(tmp_path):
    archive = tmp_path / 'bad.tar.gz'
    archive.write_bytes(b'untrusted archive')
    with pytest.raises(ValueError, match='differs'):
        toolkit.prepare_snapshot(archive, tmp_path / 'snapshot')
    assert not list(tmp_path.glob('.real-toolkit-stage-*'))
