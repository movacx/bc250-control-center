"""TUI-only remote ownership: privacy, permissions and independent SSH policy."""
import pytest

from bc250cc.application.system import remote_access, web_access
from frontends.tui.pages.remote import RemoteAccessPage

from .fakes import FakeUI, make_context
from .test_pages import choice, render, text_of


def test_the_page_opens_with_its_information_and_a_qr_that_never_carries_the_key(isolated_remote_access, monkeypatch):
    from frontends.tui.pages import remote

    web, _ssh = isolated_remote_access
    web.update(running=True, lan=True, key='SECRET-KEY', urls=['http://plain:1', 'https://192.0.2.1:8250', 'https://10.0.0.2:8250'])
    tokens, encoded = ['TOKEN-1', 'TOKEN-2'], []
    ages = {'TOKEN-1': 0.0}
    monkeypatch.setattr(remote.web_pairing, 'issue', lambda: tokens.pop(0))
    monkeypatch.setattr(remote.web_pairing, 'age', lambda token: ages.get(token))
    real = web_access.pairing_matrix
    monkeypatch.setattr(web_access, 'pairing_matrix', lambda url: encoded.append(url) or real(url))
    ctx, ui, page = make_context(), FakeUI(), RemoteAccessPage()
    shown = text_of(render(page, ctx, ui))
    assert 'SECRET-KEY' in shown and 'Show information' not in shown and '▀' in shown
    assert encoded[-1] == 'https://192.0.2.1:8250#pair=TOKEN-1'
    choice(render(page, ctx, ui), 'Address').adjust(ui, 1)
    render(page, ctx, ui)
    assert encoded[-1] == 'https://10.0.0.2:8250#pair=TOKEN-1'
    ages.clear()  # a phone used it
    render(page, ctx, ui)
    assert encoded[-1].endswith('#pair=TOKEN-2') and all('SECRET' not in url for url in encoded)


def test_without_access_or_the_local_network_no_code_is_issued(isolated_remote_access, monkeypatch):
    from frontends.tui.pages import remote

    web, _ssh = isolated_remote_access
    monkeypatch.setattr(remote.web_pairing, 'issue', lambda: (_ for _ in ()).throw(AssertionError('issued')))
    for state in ({'running': False, 'lan': True}, {'running': True, 'lan': False}):
        web.update(state)
        assert 'to display your QR here' in text_of(render(RemoteAccessPage(), make_context(), FakeUI()))


def test_a_new_device_is_announced_but_not_the_ones_already_there(isolated_remote_access):
    web, _ssh = isolated_remote_access
    web['devices'] = [{'id': 'one'}]
    ctx, ui, page = make_context(), FakeUI(), RemoteAccessPage()
    render(page, ctx, ui)
    assert not ui.notes
    web['devices'] = [{'id': 'one'}, {'id': 'two'}]
    render(page, ctx, ui)
    assert ui.notes == [('New device paired', 'ok')]


def test_permissions_and_session_duration_target_only_the_selected_device(isolated_remote_access, monkeypatch):
    web, _ssh = isolated_remote_access
    web['devices'] = [{'id': 'abc12345full-id', 'address': '192.0.2.3', 'agent': 'Test', 'control': False}]
    calls = []
    monkeypatch.setattr(web_access, 'set_control', lambda *args: calls.append(('control', args)))
    monkeypatch.setattr(web_access, 'set_lifetime', lambda *args: calls.append(('lifetime', args)))
    ctx, ui, page = make_context(), FakeUI(ints=[120]), RemoteAccessPage()
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
    layout = render(page, ctx, ui, 'ssh')
    choice(layout, 'Start SSH').handler(ui)
    choice(layout, 'Enable · Boot persistence').handler(ui)
    assert calls == [{'active': True}, {'boot': True}]
    assert all(danger for _text, danger in ui.confirmations)


def test_unsupported_init_disables_ssh_instead_of_faking_success(isolated_remote_access):
    ctx, ui = make_context(), FakeUI()
    layout = render(RemoteAccessPage(), ctx, ui, 'ssh')
    assert not choice(layout, 'Start SSH').enabled
    assert not choice(layout, 'Enable · Boot persistence').enabled


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


def test_a_small_terminal_shows_the_qr_over_the_whole_screen():
    from frontends.tui.pages.remote import qr_rows

    from .test_screen import make_screen

    rows = qr_rows(web_access.pairing_matrix('https://192.0.2.1:8250#pair=abcdefghijklmnopqrstuvwx'))
    window, screen = make_screen(height=24, width=80)
    window.queue = [27]
    screen.show_qr(rows)
    assert '▀' in window.text() and screen.toast is None
    window, screen = make_screen(height=14, width=60)
    screen.show_qr(rows)
    assert 'too small' in screen.toast[0]
