"""Persistent workspace and application routing without root or hardware writes."""
import io
import os
from types import SimpleNamespace

import pytest

from bc250cc.infrastructure import steamos_real_toolkit as provider
from bc250cc.infrastructure import steamos_real_toolkit_runtime as runtime
from bc250cc.infrastructure.dependencias_steamos import SteamosDependenciesMixin

REVISION = '0123456789abcdef0123456789abcdef01234567'


def test_download_names_the_commit_and_a_cached_copy_never_hits_network(tmp_path, monkeypatch):
    content = b'upstream source archive'
    calls = []
    def fetch(url, **kwargs):
        calls.append(url)
        return io.BytesIO(content)
    monkeypatch.setattr(runtime.urllib.request, 'urlopen', fetch)
    destination = tmp_path / 'cache' / (REVISION + '.tar.gz')
    runtime.download_archive(destination, REVISION)
    runtime.download_archive(destination, REVISION)
    assert destination.read_bytes() == content and calls == [provider.archive_url(REVISION)]
    assert provider.archive_url(REVISION).endswith('/tar.gz/' + REVISION)


def test_an_empty_download_is_never_published(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime.urllib.request, 'urlopen', lambda *args, **kwargs: io.BytesIO(b''))
    with pytest.raises(ValueError, match='empty'):
        runtime.download_archive(tmp_path / 'archive', REVISION)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('reply,valid', [(REVISION + '\n', True), ('Not Found', False), ('main', False), ('', False)])
def test_the_latest_revision_must_be_a_full_commit_hash(monkeypatch, reply, valid):
    monkeypatch.setattr(runtime.urllib.request, 'urlopen', lambda *args, **kwargs: io.BytesIO(reply.encode()))
    if valid:
        assert runtime.resolve_revision() == REVISION
    else:
        with pytest.raises(ValueError, match='commit hash'):
            runtime.resolve_revision()


def test_clear_cache_forgets_sources_and_workspace_but_keeps_guard_and_lock(tmp_path):
    (tmp_path / (REVISION + '.tar.gz')).write_bytes(b'archive')
    (tmp_path / '.download-x').write_bytes(b'partial')
    (tmp_path / 'workspace/external').mkdir(parents=True)
    (tmp_path / 'workspace/external/build.o').write_bytes(b'half-built')
    (tmp_path / 'runtime').mkdir()
    (tmp_path / 'runtime/guard').write_text('guard')
    (tmp_path / '.lock').write_text('')
    runtime.clear_cache(tmp_path)
    assert sorted(path.name for path in tmp_path.iterdir()) == ['.lock', 'runtime']
    runtime.clear_cache(tmp_path)  # idempotent


def test_workspace_restores_provider_files_but_keeps_build_outputs(tmp_path):
    snapshot, workspace = tmp_path / 'snapshot', tmp_path / 'workspace'
    (snapshot / 'external').mkdir(parents=True)
    (snapshot / 'external' / 'builder.sh').write_text('reviewed code')
    runtime.refresh_workspace(snapshot, workspace)
    (workspace / 'external' / 'builder.sh').write_text('locally changed code')
    (workspace / 'external' / 'compiled.o').write_bytes(b'cached object')
    runtime.refresh_workspace(snapshot, workspace)
    assert (workspace / 'external' / 'builder.sh').read_text() == 'reviewed code'
    assert (workspace / 'external' / 'compiled.o').read_bytes() == b'cached object'


def test_workspace_cannot_redirect_provider_files_through_a_symlink(tmp_path):
    snapshot, workspace, outside = tmp_path / 'snapshot', tmp_path / 'workspace', tmp_path / 'outside'
    (snapshot / 'external').mkdir(parents=True)
    (snapshot / 'external' / 'code').write_text('reviewed')
    workspace.mkdir()
    outside.mkdir()
    (workspace / 'external').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        runtime.refresh_workspace(snapshot, workspace)
    assert not list(outside.iterdir())


@pytest.mark.parametrize('method,argument,expected', [
    ('preparar_compatibilidad_steamos', None, 'combined-install'),
    ('gestionar_proton_steamos', 'install', 'proton-install'),
    ('gestionar_proton_steamos', 'update', 'proton-install'),
    ('gestionar_proton_steamos', 'status', 'verify'),
    ('gestionar_proton_steamos', 'uninstall', 'proton-revert'),
])
def test_application_routes_use_real_toolkit_instead_of_old_provider(monkeypatch, method, argument, expected):
    from bc250cc.infrastructure import dependencias_steamos
    monkeypatch.setattr(dependencias_steamos, 'require_bc250_hardware', lambda: None)
    class Repository(SteamosDependenciesMixin):
        def _os_repository(self):
            return SimpleNamespace(info=SimpleNamespace(family='steamos'))
        def _abrir_terminal(self, command, title):
            return command
    repo = Repository()
    command = getattr(repo, method)(*(() if argument is None else (argument,)))
    assert command == provider.launch_command(expected)
    assert 'keyboardspecialist' not in command
    assert '-I' in command and 'sudo ' in command


def test_invalid_action_is_rejected_before_any_privilege_or_network_operation():
    with pytest.raises(ValueError, match='Unknown'):
        runtime.run_action('arbitrary-shell')


def test_source_preparation_refuses_storage_under_a_shared_writable_parent(tmp_path):
    destination = tmp_path / 'must-not-create' / 'toolkit'
    with pytest.raises(PermissionError, match='protected root-owned ancestors'):
        runtime.prepare_state_root(destination)
    assert not destination.parent.exists()


def test_source_preparation_reports_low_space_without_creating_any_files(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime.shutil, 'disk_usage', lambda path: SimpleNamespace(free=100 * 1024**2))
    with pytest.raises(RuntimeError, match='768 MiB'):
        runtime.require_source_space(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_source_preparation_with_space_on_home_uses_the_same_inventory_path():
    from bc250cc.infrastructure.external_tools.catalog import EXTERNAL_TOOL_DIRECTORIES

    assert provider.WORKSPACE == provider.STATE_ROOT / 'workspace'
    assert provider.STATE_ROOT.is_relative_to('/home')
    assert EXTERNAL_TOOL_DIRECTORIES['steamos_real_toolkit'] == str(provider.WORKSPACE)


@pytest.mark.parametrize('initial,after,exit_code,expected_switch', [
    ('enabled', 'disabled', 23, 'enable'),
    ('disabled', 'enabled', 0, 'disable'),
    ('enabled', 'enabled', 0, None),
])
def test_toolkit_returns_original_status_and_restores_only_a_changed_root_mode(
    monkeypatch, initial, after, exit_code, expected_switch,
):
    current = [initial]
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if command[0] == runtime.READONLY_COMMAND:
            if command[1] == 'status':
                return SimpleNamespace(returncode=0, stdout=current[0], stderr='')
            current[0] = 'enabled' if command[1] == 'enable' else 'disabled'
            return SimpleNamespace(returncode=0)
        assert current[0] == initial, 'The launcher must not unlock root before entering upstream'
        current[0] = after
        return SimpleNamespace(returncode=exit_code)
    monkeypatch.setattr(runtime.subprocess, 'run', run)
    monkeypatch.setattr(runtime.subprocess, 'Popen',
                        lambda command: SimpleNamespace(wait=lambda result=run(command): result.returncode))
    assert runtime.run_preserving_root_mode(['fixture-action']) == exit_code
    assert current[0] == initial
    switches = [command[1] for command in calls if command[0] == runtime.READONLY_COMMAND and command[1] != 'status']
    assert switches == ([expected_switch] if expected_switch else [])


def test_unknown_root_state_stops_before_the_toolkit_action(monkeypatch):
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='unrecognized state', stderr='')
    monkeypatch.setattr(runtime.subprocess, 'run', run)
    with pytest.raises(RuntimeError, match='was not started'):
        runtime.run_preserving_root_mode(['fixture-action'])
    assert calls == [[runtime.READONLY_COMMAND, 'status']]


def test_root_restoration_failure_cannot_be_reported_as_a_success(monkeypatch):
    states = iter(['enabled', 'disabled'])
    monkeypatch.setattr(runtime, '_root_mode', lambda: next(states))
    monkeypatch.setattr(runtime.subprocess, 'run', lambda command, **kwargs:
                        SimpleNamespace(returncode=1 if command[0] == runtime.READONLY_COMMAND else 0))
    monkeypatch.setattr(runtime.subprocess, 'Popen', lambda command: SimpleNamespace(wait=lambda: 0))
    with pytest.raises(RuntimeError, match='Could not restore SteamOS read-only mode'):
        runtime.run_preserving_root_mode(['fixture-action'])


def test_toolkit_python_exception_still_restores_original_root_mode(monkeypatch):
    current = ['enabled']
    def run(command, **kwargs):
        if command[0] == runtime.READONLY_COMMAND:
            if command[1] == 'status':
                return SimpleNamespace(returncode=0, stdout=current[0], stderr='')
            current[0] = 'enabled'
            return SimpleNamespace(returncode=0)
        current[0] = 'disabled'
        raise OSError('fixture launch failure')
    monkeypatch.setattr(runtime.subprocess, 'run', run)
    monkeypatch.setattr(runtime.subprocess, 'Popen', run)
    with pytest.raises(OSError, match='fixture launch failure'):
        runtime.run_preserving_root_mode(['fixture-action'])
    assert current[0] == 'enabled'


def test_cached_guard_runtime_is_independent_of_removed_installation(tmp_path):
    installed, cached = tmp_path / 'installed', tmp_path / 'cached'
    (installed / 'lib').mkdir(parents=True)
    (installed / 'bc250-steamos-toolkit-check').write_text('checker')
    (installed / 'lib/bc250_steamos_toolkit_runtime.zip').write_bytes(b'fixture runtime')
    (installed / 'bc250-steamos-toolkit-check').chmod(0o755)
    (installed / 'lib/bc250_steamos_toolkit_runtime.zip').chmod(0o644)
    runtime.cache_guard_runtime(installed, cached)
    (installed / 'bc250-steamos-toolkit-check').unlink()
    (installed / 'lib/bc250_steamos_toolkit_runtime.zip').unlink()
    assert (cached / 'bc250-steamos-toolkit-check').read_text() == 'checker'
    assert (cached / 'lib/bc250_steamos_toolkit_runtime.zip').read_bytes() == b'fixture runtime'


def test_cached_guard_runtime_refuses_directory_symlinks(tmp_path):
    installed = tmp_path / 'installed'
    installed.mkdir()
    (installed / 'bc250-steamos-toolkit-check').write_text('checker')
    (installed / 'bc250-steamos-toolkit-check').chmod(0o755)
    outside = tmp_path / 'outside'
    outside.mkdir()
    destination = tmp_path / 'cached'
    destination.symlink_to(outside, target_is_directory=True)
    with pytest.raises(PermissionError, match='symlink'):
        runtime.cache_guard_runtime(installed, destination)
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize('stdout,status,expected', [
    ('disabled\n', 1, 'disabled'),   # what SteamOS really does while the root is writable
    ('enabled\n', 0, 'enabled'),
    ('enabled\n', 1, 'enabled'),
    ('', 1, 'unknown'),
    ('steamos-readonly: command exploded\n', 2, 'unknown'),
])
def test_root_mode_is_read_from_the_text_not_the_exit_status(monkeypatch, stdout, status, expected):
    monkeypatch.setattr(runtime.subprocess, 'run', lambda *a, **k: SimpleNamespace(
        returncode=status, stdout=stdout, stderr=''))
    assert runtime._root_mode() == expected


def test_root_mode_distinguishes_a_missing_command_from_one_that_hangs(monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError

    def hangs(*args, **kwargs):
        raise runtime.subprocess.TimeoutExpired('steamos-readonly', 10)

    monkeypatch.setattr(runtime.subprocess, 'run', missing)
    assert runtime._root_mode() == 'unavailable'
    monkeypatch.setattr(runtime.subprocess, 'run', hangs)
    assert runtime._root_mode() == 'unknown'


def test_failure_logs_are_the_newest_few_plain_files_and_replace_the_previous_set(tmp_path):
    logs = tmp_path / 'workspace' / 'logs'
    logs.mkdir(parents=True)
    for number in range(8):
        path = logs / ('run-%d.log' % number)
        path.write_text(str(number))
        os.utime(path, (1000 + number, 1000 + number))
    (logs / 'elsewhere.log').symlink_to(tmp_path)
    (logs / 'notes.txt').write_text('not a log')
    (tmp_path / runtime.FAILURE_LOGS).mkdir()
    (tmp_path / runtime.FAILURE_LOGS / 'old.log').write_text('previous failure')
    runtime.clear_cache(tmp_path)
    assert sorted(path.name for path in (tmp_path / runtime.FAILURE_LOGS).iterdir()) == [
        'run-2.log', 'run-3.log', 'run-4.log', 'run-5.log', 'run-6.log', 'run-7.log']


def test_no_logs_means_no_failure_folder(tmp_path):
    (tmp_path / 'workspace').mkdir()
    runtime.clear_cache(tmp_path)
    assert not (tmp_path / runtime.FAILURE_LOGS).exists()
