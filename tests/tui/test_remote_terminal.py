"""TUI-only remote ownership: privacy, permissions and independent SSH policy."""
import time

import pytest

from bc250cc.application.system import remote_access, web_access
from frontends.tui.pages.remote import RemoteAccessPage

from .fakes import FakeUI, make_context
from .test_pages import choice, render, text_of


def reveal(ctx):
    ctx.state('remote')['visible_until'] = time.monotonic() + 300


def test_remote_information_starts_hidden_and_expires_after_five_minutes(isolated_remote_access, monkeypatch):
    web, _ssh = isolated_remote_access
    web.update(key='SECRET-KEY', urls=['https://private-address:8250'])
    ctx, ui, page = make_context(), FakeUI(), RemoteAccessPage()
    assert 'SECRET' not in text_of(render(page, ctx, ui))
    choice(render(page, ctx, ui), 'Show information').handler(ui)
    assert 'SECRET-KEY' in text_of(render(page, ctx, ui))
    ctx.state('remote')['visible_until'] = time.monotonic() - 1
    assert 'SECRET' not in text_of(render(page, ctx, ui))
    fresh = make_context()
    assert 'SECRET' not in text_of(render(page, fresh, ui))


def test_permissions_and_session_duration_target_only_the_selected_device(isolated_remote_access, monkeypatch):
    web, _ssh = isolated_remote_access
    web['devices'] = [{'id': 'abc12345full-id', 'address': '192.0.2.3', 'agent': 'Test', 'control': False}]
    calls = []
    monkeypatch.setattr(web_access, 'set_control', lambda *args: calls.append(('control', args)))
    monkeypatch.setattr(web_access, 'set_lifetime', lambda *args: calls.append(('lifetime', args)))
    ctx, ui, page = make_context(), FakeUI(ints=[120]), RemoteAccessPage()
    reveal(ctx)
    layout = render(page, ctx, ui, 'devices')
    choice(layout, 'Allow hardware control').handler(ui)
    choice(layout, 'Custom session duration in minutes').handler(ui)
    assert calls == [('control', ('abc12345full-id', True)), ('lifetime', ('abc12345full-id', 7200))]
    assert ui.confirmations[-1][1]


def test_ssh_start_and_boot_policy_are_independent_and_require_confirmation(isolated_remote_access, monkeypatch):
    _web, ssh = isolated_remote_access
    ssh.update(unit='sshd.service', supported=True, active=False, enabled=False)
    calls = []
    monkeypatch.setattr(remote_access, 'configure', lambda **updates: calls.append(updates))
    ctx, ui, page = make_context(), FakeUI(), RemoteAccessPage()
    reveal(ctx)
    layout = render(page, ctx, ui, 'ssh')
    choice(layout, 'Start SSH').handler(ui)
    choice(layout, 'Enable SSH at boot').handler(ui)
    assert calls == [{'active': True}, {'boot': True}]
    assert all(danger for _text, danger in ui.confirmations)


def test_unsupported_init_disables_ssh_instead_of_faking_success(isolated_remote_access):
    ctx, ui = make_context(), FakeUI()
    reveal(ctx)
    layout = render(RemoteAccessPage(), ctx, ui, 'ssh')
    assert not choice(layout, 'Start SSH').enabled
    assert not choice(layout, 'Enable SSH at boot').enabled


@pytest.mark.parametrize('manager,expected', [('systemd', ['start', 'sshd.service']),
                                              ('openrc', ['sshd', 'start'])])
def test_native_ssh_commands_use_the_active_init_adapter(manager, expected, monkeypatch):
    from types import SimpleNamespace

    from bc250cc.infrastructure import remote_access as backend

    monkeypatch.setattr(backend, 'status', lambda: {'supported': True, 'manager': manager, 'unit':
                        'sshd' if manager == 'openrc' else 'sshd.service'})
    monkeypatch.setattr(backend.shutil, 'which', lambda name: '/tools/' + name)
    monkeypatch.setattr(backend, 'pkexec_argv', lambda executor, *args: [executor, *args])
    calls = []
    monkeypatch.setattr(backend.subprocess, 'run', lambda argv, **kwargs:
                        calls.append(argv) or SimpleNamespace(returncode=0, stderr=''))
    backend.configure(active=True)
    assert calls[0][-2:] == expected
    assert 'enable' not in calls[0] and 'add' not in calls[0]


def test_an_idle_remote_dialog_closes_when_visibility_expires():
    from .test_screen import make_screen

    window, screen = make_screen()
    screen.goto('remote')
    screen.ctx.state('remote')['visible_until'] = time.monotonic() - 1
    window.queue = [-1]
    assert not screen.confirm('Hardware control', danger=True)
    assert screen.ctx.state('remote')['visible_until'] == 0
    assert 'TEST-TEST' not in window.text()
