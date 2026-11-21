"""Real Toolkit dispatch runs only explicit functions, retaining user choices."""
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

REVISION = '0123456789abcdef0123456789abcdef01234567'


def _fixture():
    functions = "\n".join(f'{a.function}() {{ printf "%s:%s\\n" {a.key} "$AUTO"; }}'
                          for a in toolkit.ACTIONS)
    # The recovery flag still runs upstream's bulk revert, which we do not expose as a row.
    functions += '\nrun_revert_all() {\n' + ''.join('    ' + step + '\n' for step in REVERT_ALL_STEPS) + '}\n'
    extra = '\n'.join(f'{name}() {{ :; }}' for name in toolkit.GUARDED_FUNCTIONS
                      if name not in {a.function for a in toolkit.ACTIONS} | {'run_revert_all'})
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


def test_entrypoint_is_checked_structurally_before_it_is_adapted():
    source = _fixture()
    adapted = toolkit.prepare_entrypoint(source)
    assert b'bc250cc_original_run_cpu_governor()' in adapted
    assert toolkit._guard_shell().encode() in adapted
    assert subprocess.run(['bash', '-n'], input=adapted, capture_output=True).returncode == 0
    # Any digest is acceptable (upstream moves); a changed shape is not.
    with pytest.raises(ValueError, match='main-loop'):
        toolkit.prepare_entrypoint(source.replace(toolkit._MAIN_LOOP.encode(), b'while true; do\n    other_menu\n'))
    with pytest.raises(ValueError, match='startup'):
        toolkit.prepare_entrypoint(source.replace(toolkit._GUARD_BOUNDARY.encode(), b''))


def test_a_renamed_guarded_function_stops_the_adapter_instead_of_leaving_it_unguarded():
    source = _fixture().replace(b'run_overclock_menu()', b'run_renamed_menu()')
    with pytest.raises(ValueError, match='run_overclock_menu'):
        toolkit.prepare_entrypoint(source)


def test_missing_upstream_action_cannot_silently_reduce_the_integration(monkeypatch):
    source = _fixture().replace(b'install_ac3_surround()', b'renamed_ac3_surround()')
    with pytest.raises(ValueError, match='install_ac3_surround'):
        toolkit.prepare_entrypoint(source)


@pytest.mark.parametrize('action', ['acpi-install', 'recovery'])
def test_guard_stops_direct_and_nested_calls_before_the_original_body(monkeypatch, tmp_path, action):
    source = _fixture().replace(b'run_recovery_menu() {', b'run_recovery_menu() { install_acpi_fix || return $?;')
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
    checker = tmp_path / 'check.sh'
    checker.write_text('test "$1" = acpi\n')
    monkeypatch.setattr(toolkit, 'CONFLICT_CHECK_COMMAND', ('/usr/bin/bash', str(checker)))
    result = subprocess.run(['bash', '-s', '--', '--bc250cc-action', 'acpi-install'],
                            input=toolkit.prepare_entrypoint(source), capture_output=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == b'acpi-install:0\n'


def test_recovery_flag_before_main_loop_also_uses_the_component_guard(monkeypatch, tmp_path):
    source = _fixture()
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


def _archive(tmp_path, monkeypatch, malicious=None, *, vendored=True, source=None):
    source = _fixture() if source is None else source
    archive = tmp_path / 'source.tar.gz'
    prefix = 'bc250-steamos-real-toolkit-' + REVISION
    with tarfile.open(archive, 'w:gz') as bundle:
        member = tarfile.TarInfo(prefix + '/start.sh')
        member.size, member.mode = len(source), 0o4755
        bundle.addfile(member, io.BytesIO(source))
        if vendored:
            # The vendored tree that tells start.sh it is a complete checkout.
            marker = tarfile.TarInfo(prefix + '/external/bc250_smu_oc/bc250_apply.py')
            marker.mode = 0o644
            bundle.addfile(marker, io.BytesIO(b''))
        if malicious:
            bundle.addfile(malicious)
    return archive


def test_snapshot_is_complete_and_atomic_and_strips_special_permissions(tmp_path, monkeypatch):
    archive = _archive(tmp_path, monkeypatch)
    target = tmp_path / 'snapshot'
    toolkit.prepare_snapshot(archive, target, REVISION)
    assert (target / 'start.sh').stat().st_mode & 0o7777 == 0o755
    assert '--bc250cc-action' in (target / 'start.sh').read_text()
    metadata = (target / '.bc250cc-provider.json').read_text()
    assert REVISION in metadata and 'archive_sha256' in metadata and 'entrypoint_sha256' in metadata
    with pytest.raises(ValueError, match='already exists'):
        toolkit.prepare_snapshot(archive, target, REVISION)


@pytest.mark.parametrize('kind', ['traversal', 'absolute', 'symlink', 'hardlink', 'duplicate'])
def test_bad_archive_never_publishes_a_partial_snapshot(tmp_path, monkeypatch, kind):
    prefix = 'bc250-steamos-real-toolkit-' + REVISION
    names = {'traversal': prefix + '/../escape', 'absolute': '/escape',
             'symlink': prefix + '/link', 'hardlink': prefix + '/hard', 'duplicate': prefix + '/start.sh'}
    member = tarfile.TarInfo(names[kind])
    if kind in {'symlink', 'hardlink'}:
        member.type = tarfile.SYMTYPE if kind == 'symlink' else tarfile.LNKTYPE
        member.linkname = '/escape'
    archive = _archive(tmp_path, monkeypatch, member)
    target = tmp_path / 'snapshot'
    with pytest.raises(ValueError):
        toolkit.prepare_snapshot(archive, target, REVISION)
    assert not target.exists()
    assert not list(tmp_path.glob('.real-toolkit-stage-*'))


def test_an_archive_that_is_not_a_toolkit_creates_no_staging_tree(tmp_path):
    archive = tmp_path / 'bad.tar.gz'
    archive.write_bytes(b'untrusted archive')
    with pytest.raises(Exception):
        toolkit.prepare_snapshot(archive, tmp_path / 'snapshot', REVISION)
    assert not (tmp_path / 'snapshot').exists()
    assert not list(tmp_path.glob('.real-toolkit-stage-*'))


def test_only_a_full_commit_hash_names_a_revision(tmp_path):
    for bad in ('main', 'abc123', '../x', ''):
        with pytest.raises(ValueError, match='commit hash'):
            toolkit.prepare_snapshot(tmp_path / 'x.tar.gz', tmp_path / 'snapshot', bad)
        with pytest.raises(ValueError, match='commit hash'):
            toolkit.archive_url(bad)
    assert toolkit.archive_url(REVISION).endswith('/' + REVISION)


STANDALONE_BLOCK = (
    'if [[ ! -d "$SCRIPT_DIR/.git" && ! -d "$EXTERNAL_DIR/bc250_smu_oc" ]]; then\n'
    '    runuser -u "$REAL_USER" -- git clone --depth 1 "https://github.com/rpf16rj/bc250-steamos-real-toolkit.git" "$TOOLKIT_REPO_DIR"\n'
    '    exec bash "$TOOLKIT_REPO_DIR/start.sh" "$@"\n'
    'fi\n'
)


def test_the_prepared_entrypoint_never_hands_over_to_a_freshly_cloned_unprepared_copy():
    """Upstream's lone-script path clones main and execs it, with no dispatch and no guards.

    The adapted entrypoint must stop there instead, as root, whatever the tree.
    """
    source = _fixture().decode().replace('#!/bin/bash\n', '#!/bin/bash\n' + STANDALONE_BLOCK, 1).encode()
    adapted = toolkit.prepare_entrypoint(source).decode()
    assert 'exec bash "$TOOLKIT_REPO_DIR/start.sh"' not in adapted
    assert 'does not run an unprepared copy' in adapted and 'exit 70' in adapted


def test_another_hand_over_to_a_fetched_copy_is_refused():
    source = _fixture().decode().replace(
        '#!/bin/bash\n', '#!/bin/bash\nexec sudo bash "$TOOLKIT_REPO_DIR/start.sh"\n', 1).encode()
    with pytest.raises(ValueError, match='standalone re-launch'):
        toolkit.prepare_entrypoint(source)


def test_an_archive_without_the_vendored_tree_is_refused_before_anything_runs(tmp_path, monkeypatch):
    archive = _archive(tmp_path, monkeypatch, vendored=False)
    with pytest.raises(ValueError, match='bc250_smu_oc'):
        toolkit.prepare_snapshot(archive, tmp_path / 'snapshot', REVISION)
    assert not (tmp_path / 'snapshot').exists()
