"""Old distro Cheroot must not block the desktop or be exposed on the LAN."""
from types import SimpleNamespace

import pytest

from bc250cc.infrastructure import web_runtime
from bc250cc.shared.errors import ActionNeeded


@pytest.mark.parametrize('version,allowed', [('10.0.0', False), ('11.1.1', False), ('11.1.2', True),
                                            ('11.1.2.post1', True), ('11.9.0', True), ('12.0.0', False)])
def test_supported_server_version_is_checked_before_listening(monkeypatch, version, allowed):
    monkeypatch.setattr(web_runtime, 'version', lambda _name: version)
    if allowed:
        web_runtime.require_supported_version()
    else:
        with pytest.raises(ActionNeeded, match='Cheroot >=11.1.2,<12'):
            web_runtime.require_supported_version()


def test_preparation_installs_into_the_user_venv_not_system_python(tmp_path, monkeypatch):
    monkeypatch.setattr(web_runtime.os, 'geteuid', lambda: 1000)
    (tmp_path / 'requirements-web.txt').write_text('cheroot>=11.1.2,<12\n')
    destination = tmp_path / 'data/web-runtime'
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(web_runtime.subprocess, 'run', run)
    assert web_runtime.prepare(tmp_path, destination) == destination / 'bin/python'
    assert calls[0][1:7] == ['-I', '-m', 'venv', '--system-site-packages', '--without-pip', str(destination)]
    pip = calls[1]
    assert pip[pip.index('--python') + 1] == str(destination / 'bin/python')
    assert pip[pip.index('-r') + 1] == str(tmp_path / 'requirements-web.txt')
    assert '--isolated' in pip and '--no-input' in pip
    assert not {'sudo', '--break-system-packages', '--trusted-host'} & set(pip)


def test_preparation_never_runs_pip_as_root(tmp_path, monkeypatch):
    monkeypatch.setattr(web_runtime.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(web_runtime.subprocess, 'run', lambda *_a, **_kw: pytest.fail('root pip'))
    with pytest.raises(ActionNeeded, match='ordinary Linux user'):
        web_runtime.prepare(tmp_path, tmp_path / 'runtime')


def test_preparation_failure_has_a_next_step_and_does_not_start_a_server(tmp_path, monkeypatch):
    monkeypatch.setattr(web_runtime.os, 'geteuid', lambda: 1000)
    (tmp_path / 'requirements-web.txt').write_text('cheroot>=11.1.2,<12\n')

    def unavailable(*_args, **_kwargs):
        raise OSError('network unavailable')

    monkeypatch.setattr(web_runtime.subprocess, 'run', unavailable)
    with pytest.raises(ActionNeeded, match='pip/venv packages'):
        web_runtime.prepare(tmp_path, tmp_path / 'runtime')
    assert not (tmp_path / 'web.pid').exists()


def test_existing_runtime_is_upgraded_without_clearing_user_files(tmp_path, monkeypatch):
    monkeypatch.setattr(web_runtime.os, 'geteuid', lambda: 1000)
    (tmp_path / 'requirements-web.txt').write_text('cheroot>=11.1.2,<12\n')
    destination = tmp_path / 'web-runtime'
    destination.mkdir()
    (destination / 'pyvenv.cfg').write_text('version = 3.12.0\n')
    calls = []
    monkeypatch.setattr(web_runtime.subprocess, 'run', lambda argv, **_kwargs: calls.append(argv))
    web_runtime.prepare(tmp_path, destination)
    assert '--upgrade' in calls[0]
    assert '--clear' not in calls[0]


def test_cli_help_does_not_prepare_or_import_a_web_server(monkeypatch, capsys):
    from frontends.web import __main__ as entry

    monkeypatch.setattr(entry.sys, 'argv', ['bc250-control-center', '--help'])
    monkeypatch.setattr(entry, 'launch_command', lambda: pytest.fail('Help must not install packages'))
    with pytest.raises(SystemExit) as result:
        entry.main()
    assert result.value.code == 0
    assert '--host' in capsys.readouterr().out


def test_cli_bootstrap_preserves_explicit_flags_when_switching_interpreters(monkeypatch):
    from frontends.web import __main__ as entry

    def unsupported():
        raise ActionNeeded('old system Cheroot')

    def replace(path, argv):
        assert path == '/isolated/bin/python'
        assert argv == ['/isolated/bin/python', '-m', 'frontends.web', '--port', '8300']
        raise SystemExit(0)

    monkeypatch.setattr(entry, 'require_supported_version', unsupported)
    monkeypatch.setattr(entry, 'launch_command', lambda: ['/isolated/bin/python', '-m', 'frontends.web'])
    monkeypatch.setattr(entry.os, 'execv', replace)
    with pytest.raises(SystemExit) as result:
        entry.main(['--port', '8300'])
    assert result.value.code == 0
