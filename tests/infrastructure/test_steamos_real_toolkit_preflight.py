from pathlib import Path
from types import SimpleNamespace

from bc250cc.infrastructure import steamos_real_toolkit as provider
from bc250cc.infrastructure import steamos_real_toolkit_runtime as runtime


def _checks(monkeypatch, *, free=None, cached=True):
    monkeypatch.setattr(runtime, '_cached_revision', lambda _: 'cached' if cached else None)
    monkeypatch.setattr(runtime, '_reachable', lambda _: False)
    monkeypatch.setattr(runtime.guard, 'read_root', lambda **_: runtime.guard.RootReading('enabled'))
    monkeypatch.setattr(runtime.guard, 'read_session', lambda _: None)

    def space(path):
        mib = (free or {}).get(Path(path).name, 6000)
        return SimpleNamespace(f_bavail=mib, f_frsize=1024**2)

    monkeypatch.setattr(runtime.os, 'statvfs', space)


def test_cached_verify_checks_no_network_kernel_or_headers(tmp_path, monkeypatch):
    _checks(monkeypatch)
    lines = runtime.preflight('verify', root=tmp_path, home=tmp_path)
    assert {line.label for line in lines} == {
        '/', '/var', '/home', 'Ownership', 'Toolkit session', 'SteamOS read-only mode',
    }


def test_combined_stops_at_upstreams_space_and_kernel_gates(tmp_path, monkeypatch):
    _checks(monkeypatch, free={'var': 99, 'home': 4096})
    lines = runtime.preflight('combined-install', root=tmp_path, home=tmp_path, kernel='6.18.1')
    assert {line.label for line in lines if line.blocks} == {'/var', '/home', 'Kernel'}
    assert all(line.fix for line in lines if line.blocks)
    assert any(line.label == 'Kernel headers' and line.fix and not line.blocks for line in lines)
    assert any(line.label == 'Network' and line.fix for line in lines)


def test_combined_source_fallback_requires_explicit_override(monkeypatch, tmp_path, capsys):
    _checks(monkeypatch)
    monkeypatch.setattr(provider, 'old_glibc', lambda: True)
    assert provider.known_combined_failure('7.2.1-valve')
    assert not provider.known_combined_failure('7.3.1-valve')
    lines = runtime.preflight('combined-install', root=tmp_path, home=tmp_path, kernel='7.2.1-valve')
    monkeypatch.setattr(runtime, 'preflight', lambda _: lines)
    monkeypatch.setattr('builtins.input', lambda _: '')
    assert runtime.show_preflight('combined-install') == 1
    monkeypatch.setattr('builtins.input', lambda _: 'try anyway')
    assert runtime.show_preflight('combined-install') == provider.OVERRIDE_STATUS
    assert 'Kernel compatibility' in capsys.readouterr().out


def test_hard_failure_cannot_be_overridden(monkeypatch):
    monkeypatch.setattr(runtime, 'preflight', lambda _: (
        runtime.PreflightLine('Build tools', 'Old glibc.', blocks=True, can_override=True),
        runtime.PreflightLine('Ownership', 'Conflict.', blocks=True),
    ))

    def unexpected(_):
        raise AssertionError('An ownership failure must not offer an override')

    monkeypatch.setattr('builtins.input', unexpected)
    assert runtime.show_preflight('combined-install') == 1


def test_put_back_runs_only_missing_actions_and_pauses_after_a_declined_install(monkeypatch, capsys):
    pending = [
        {'component': 'amdgpu', 'action': 'combined-install'},
        {'component': 'acpi', 'action': 'acpi-install'},
        {'component': 'video', 'action': 'video-install'},
    ]
    monkeypatch.setattr(runtime, '_pending_restore', lambda *_: pending.copy())
    calls = []

    def run(action):
        calls.append(action)
        if action == provider.COMBINED_OVERRIDE:
            pending.pop(0)
        return 0

    monkeypatch.setattr(runtime, 'run_action', run)
    assert runtime._put_back(SimpleNamespace(pw_dir='/fixture', pw_uid=1000), override=True) == 1
    assert calls == [provider.COMBINED_OVERRIDE, 'acpi-install']
    assert 'remaining Toolkit installs were paused' in capsys.readouterr().err


def test_firmware_download_needs_network_without_a_kernel_build(tmp_path, monkeypatch):
    _checks(monkeypatch)
    lines = runtime.preflight('be200-install', root=tmp_path, home=tmp_path, kernel='6.18.1')
    assert not any(line.label in {'Kernel', 'Kernel headers'} for line in lines)
    assert any(line.label == 'Network' and 'deb.debian.org' in line.result for line in lines)


def test_unprivileged_root_probe_distinguishes_unknown_from_missing(tmp_path, monkeypatch):
    _checks(monkeypatch)
    for state, blocks in [('unknown', False), ('unavailable', True)]:
        monkeypatch.setattr(runtime.guard, 'read_root', lambda **_: runtime.guard.RootReading(state))
        lines = runtime.preflight('verify', root=tmp_path, home=tmp_path)
        assert lines[-1].label == 'SteamOS read-only mode'
        assert lines[-1].blocks is blocks
