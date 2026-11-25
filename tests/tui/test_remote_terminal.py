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
    ctx, ui, page = make_context(), FakeUI(ints=[120], choices=[-1]), RemoteAccessPage()
    layout = render(page, ctx, ui, 'devices')
    choice(layout, 'Hardware control').handler(ui)
    choice(layout, 'Session expiry').handler(ui)
    assert calls == [('control', ('abc12345full-id', True)), ('lifetime', ('abc12345full-id', 7200))]
    assert ui.confirmations[-1][1]


def test_ssh_start_and_boot_policy_are_independent_and_require_confirmation(isolated_remote_access, monkeypatch):
    _web, ssh = isolated_remote_access
    ssh.update(unit='sshd.service', supported=True, active=False, enabled=False)
    calls = []
    monkeypatch.setattr(remote_access, 'configure', lambda **updates: calls.append(updates))
    ctx, ui, page = make_context(), FakeUI(), RemoteAccessPage()
    layout = render(page, ctx, ui, 'ssh')
    choice(layout, 'SSH server').handler(ui)
    choice(layout, 'Boot persistence').handler(ui)
    assert calls == [{'active': True}, {'boot': True}]
    assert all(danger for _text, danger in ui.confirmations)


def test_without_an_ssh_server_only_the_missing_step_is_shown(isolated_remote_access):
    ctx, ui = make_context(), FakeUI()
    layout = render(RemoteAccessPage(), ctx, ui, 'ssh')
    assert not layout.choices
    assert 'Install the openssh-server package first.' in text_of(layout)


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


def test_build_never_issues_a_pairing_token(isolated_remote_access, monkeypatch):
    from frontends.tui.pages import remote

    web, _ssh = isolated_remote_access
    web.update(running=True, lan=True, urls=['https://192.0.2.1:8250'])
    monkeypatch.setattr(remote.web_pairing, 'issue', lambda: pytest.fail('issued during build'))
    page = RemoteAccessPage()
    for tab in ('web', 'devices', 'ssh', 'network'):
        page.build(make_context(), {'web': web, 'pair': 'ONE-TIME'}, tab, FakeUI())


def test_device_table_moves_opens_and_keeps_selection_after_refresh(isolated_remote_access, monkeypatch):
    from frontends.tui.content import Pad

    web, _ssh = isolated_remote_access
    first = {'id': 'first-device', 'agent': 'Mozilla/5.0 Android Chrome/140', 'address': '192.0.2.1'}
    second = {'id': 'second-device', 'agent': 'Mozilla/5.0 Linux Firefox/143', 'address': '192.0.2.2'}
    web['devices'] = [first, second]
    page, ctx, ui = RemoteAccessPage(), make_context(), FakeUI()
    table = page.build(ctx, {'web': web}, 'devices', ui)[0].blocks[0]
    assert isinstance(table, Pad) and table.whole
    assert table.rows[0].name == 'Android · Chrome'
    assert table.move(1, 0)
    assert not table.move(1, 0) and not table.move(0, 1)
    table.toggle(ui)
    assert '192.0.2.2' in ui.texts[-1]
    web['devices'].reverse()
    layout = render(page, ctx, ui, 'devices')
    assert ctx.state('remote')['device'] == 'second-device'
    calls = []
    monkeypatch.setattr(web_access, 'revoke', lambda device: calls.append(device))
    choice(layout, 'Disconnect').handler(ui)
    assert calls == ['second-device'] and ui.confirmations[-1][1]
    assert 'Mozilla' not in text_of(layout)
    web['devices'] = [first]
    render(page, ctx, ui, 'devices')
    assert ctx.state('remote')['device'] == 'first-device'


@pytest.mark.parametrize('minutes', [15, 30, 60, 480, 1440, 10080, 43200, -1, 0, None])
def test_session_options_run_inside_guard_and_preserve_their_api_semantics(isolated_remote_access, monkeypatch, minutes):
    web, _ssh = isolated_remote_access
    web['devices'] = [{'id': 'selected', 'control': False}]
    calls, inside = [], []
    ui = FakeUI(choices=[minutes], ints=[120])
    original = ui.run

    def run(label, work):
        inside.append(True)
        try:
            return original(label, work)
        finally:
            inside.pop()

    def record(name, *args):
        assert inside
        calls.append((name, args))

    ui.run = run
    monkeypatch.setattr(web_access, 'set_lifetime', lambda *args: record('lifetime', *args))
    monkeypatch.setattr(web_access, 'approve', lambda *args: record('approve', *args))
    monkeypatch.setattr(web_access, 'set_control', lambda *args: pytest.fail('unexpected permission change'))
    choice(render(RemoteAccessPage(), make_context(), ui, 'devices'), 'Session expiry').handler(ui)
    if minutes is None:
        assert not calls and not ui.ran
    elif minutes == 0:
        assert calls == [('approve', ('selected',))]
        assert ui.confirmations[-1][1] and 'Allow hardware control' in ui.confirmations[-1][0]
    else:
        assert calls == [('lifetime', ('selected', (120 if minutes == -1 else minutes) * 60))]


@pytest.mark.parametrize('action', ['Hardware control', 'Disconnect', 'Disconnect all devices', 'Session expiry'])
def test_cancelled_device_security_actions_change_nothing(isolated_remote_access, monkeypatch, action):
    web, _ssh = isolated_remote_access
    web['devices'] = [{'id': 'selected'}]
    for name in ('set_control', 'revoke', 'revoke_all', 'approve'):
        monkeypatch.setattr(web_access, name, lambda *args: pytest.fail('cancelled action ran'))
    ui = FakeUI(confirm=False, choices=[0])
    choice(render(RemoteAccessPage(), make_context(), ui, 'devices'), action).handler(ui)
    assert ui.confirmations and not ui.ran


def test_disconnect_all_runs_in_guarded_console(isolated_remote_access, monkeypatch):
    web, _ssh = isolated_remote_access
    web['devices'] = [{'id': 'one'}, {'id': 'two'}]
    ui = FakeUI()
    calls = []
    monkeypatch.setattr(web_access, 'revoke_all', lambda: calls.append(list(ui.ran)))
    choice(render(RemoteAccessPage(), make_context(), ui, 'devices'), 'Disconnect all devices').handler(ui)
    assert calls == [['Disconnect all devices']]
    assert ui.confirmations == [('Disconnect all devices', True)]


def test_certificate_is_public_and_saved_only_inside_guard(isolated_remote_access, monkeypatch, tmp_path):
    source, destination = tmp_path / 'public.crt', tmp_path / 'saved.crt'
    source.write_text('PUBLIC CERTIFICATE')
    ui = FakeUI()
    ui.ask_text = lambda *args: str(destination)
    calls = []

    def certificate():
        assert ui.ran == ['Save public certificate']
        calls.append(True)
        return source

    monkeypatch.setattr(web_access, 'trust_certificate', certificate)
    page, ctx = RemoteAccessPage(), make_context()
    choice(render(page, ctx, ui), 'Save public certificate').handler(ui)
    assert calls == [True] and destination.read_text() == 'PUBLIC CERTIFICATE'
    ui.confirm_answer = False
    choice(render(page, ctx, ui), 'Save public certificate').handler(ui)
    assert calls == [True] and ui.confirmations[-1][1]
    ui.ask_text = lambda *args: None
    choice(render(page, ctx, ui), 'Save public certificate').handler(ui)
    assert calls == [True]


def test_fingerprint_is_available_without_a_service_call(isolated_remote_access):
    web, _ssh = isolated_remote_access
    web['trust_fingerprint'] = 'AA:BB:CC'
    ui = FakeUI()
    choice(render(RemoteAccessPage(), make_context(), ui), 'SHA-256').handler(ui)
    assert 'AA:BB:CC' in ui.texts[-1] and 'Trust it only on devices you own.' in ui.texts[-1]
    assert not ui.ran


def test_port_adjustment_and_web_switches_keep_confirmation_and_calls(isolated_remote_access, monkeypatch):
    web, _ssh = isolated_remote_access
    web['autostart'] = {'supported': True, 'enabled': False}
    ui, calls = FakeUI(ints=[8251, 9000]), []
    monkeypatch.setattr(web_access, 'configure', lambda **kwargs: calls.append((list(ui.ran), kwargs)))
    layout = render(RemoteAccessPage(), make_context(), ui)
    assert choice(layout, 'TCP').adjust is None  # each step would restart the server
    choice(layout, 'TCP').handler(ui)
    choice(layout, 'Reachable from the local network').handler(ui)
    assert calls == [(['Remote access'], {'port': 8251}),
                     (['Remote access', 'Reachable from the local network'], {'lan': True, 'tls': True})]
    assert len(ui.confirmations) == 2
    ui.confirm_answer = False
    choice(layout, 'TCP').handler(ui)
    assert len(calls) == 2


def test_ssh_commands_cover_each_address_and_never_request_secrets(isolated_remote_access):
    _web, ssh = isolated_remote_access
    ssh.update(unit='sshd', supported=True, addresses=['192.0.2.1', '2001:db8::1'], port=2222, user='owner')
    layout = render(RemoteAccessPage(), make_context(), FakeUI(), 'ssh')
    text = text_of(layout)
    assert 'ssh -p 2222 owner@192.0.2.1' in text
    assert 'ssh -p 2222 owner@[2001:db8::1]' in text
    assert all('Linux account and files' in item.info.summary and 'do not open the SSH port' in item.info.risk
               for item in layout.choices)
    assert [item.detail for item in layout.choices] == ['[ ]', '[ ]']


def test_a_cancelled_ssh_switch_does_not_configure(isolated_remote_access, monkeypatch):
    _web, ssh = isolated_remote_access
    ssh.update(unit='sshd', supported=True)
    monkeypatch.setattr(remote_access, 'configure', lambda **kwargs: pytest.fail('cancelled SSH action ran'))
    ui = FakeUI(confirm=False)
    layout = render(RemoteAccessPage(), make_context(), ui, 'ssh')
    for item in layout.choices:
        item.handler(ui)
    assert len(ui.confirmations) == 2 and not ui.ran


def test_small_terminal_pairing_uses_the_full_screen_fallback(isolated_remote_access):
    from frontends.tui.content import Choice

    web, _ssh = isolated_remote_access
    web.update(running=True, lan=True, urls=['https://192.0.2.1:8250'])
    ui = FakeUI()
    ui._content_box = lambda: (0, 50)
    ui._view = lambda: 14
    shown = []
    ui.show_qr = lambda rows: shown.append(rows)
    blocks = RemoteAccessPage().build(make_context(), {'web': web, 'pair': 'TOKEN'}, 'web', ui)
    pairing = next(block for block in blocks if block.title == 'Scan to connect')
    assert isinstance(pairing.blocks[0], Choice)
    pairing.blocks[0].handler(ui)
    assert shown and any(tone == 'qr' for row in shown[0] for _text, tone in row)


@pytest.mark.parametrize('language', ['en', 'es'])
@pytest.mark.parametrize('unicode', [True, False])
@pytest.mark.parametrize('width,height', [(142, 36), (92, 32), (52, 16)])
def test_all_tabs_fit_terminal_content_widths(isolated_remote_access, language, unicode, width, height):
    from frontends.tui.content import cell_width
    from frontends.tui.i18n import set_language
    from frontends.tui.layout import Glyphs, build_page

    web, ssh = isolated_remote_access
    web.update(running=True, lan=True, urls=['https://192.0.2.1:8250'],
               devices=[{'id': 'one', 'agent': 'Android Chrome/140', 'address': '192.0.2.2'}])
    ssh.update(unit='sshd', supported=True, addresses=['192.0.2.1'], user='owner')
    set_language(language)
    ui, ctx, page = FakeUI(), make_context(), RemoteAccessPage()
    ui._content_box = lambda: (0, width)
    ui._view = lambda: height
    for tab in ('web', 'devices', 'ssh', 'network'):
        blocks = page.build(ctx, {'web': web, 'ssh': ssh, 'pair': 'TOKEN'}, tab, ui)
        layout = build_page(blocks, width, Glyphs.for_terminal(unicode_ok=unicode))
        assert layout.rows
        assert all(sum(cell_width(text) for text, _tone in row.spans) <= width for row in layout.rows)


@pytest.mark.parametrize('label,method,expected', [
    ('Remote access', 'start', {}),
    ('New access key', 'access_key', {'renew': True}),
    ('Start with the session', 'set_autostart', {}),
])
def test_web_actions_remain_guarded_and_confirmed(isolated_remote_access, monkeypatch, label, method, expected):
    web, _ssh = isolated_remote_access
    web['autostart'] = {'supported': True, 'enabled': False}
    ui, calls = FakeUI(), []

    def operation(*args, **kwargs):
        assert ui.ran
        calls.append((args, kwargs))

    monkeypatch.setattr(web_access, method, operation)
    page, ctx = RemoteAccessPage(), make_context()
    layout = render(page, ctx, ui)
    choice(layout, label).handler(ui)
    assert calls == [((True,) if method == 'set_autostart' else (), expected)]
    assert ui.confirmations[-1][1] == (method == 'access_key')
    ui.confirm_answer = False
    choice(layout, label).handler(ui)
    assert len(calls) == 1


def test_stopping_web_access_uses_the_existing_stop_operation(isolated_remote_access, monkeypatch):
    web, _ssh = isolated_remote_access
    web['running'] = True
    ui, calls = FakeUI(), []
    monkeypatch.setattr(web_access, 'stop', lambda: calls.append(list(ui.ran)))
    choice(render(RemoteAccessPage(), make_context(), ui), 'Remote access').handler(ui)
    assert calls == [['Stop web access']] and ui.confirmations == [('Stop web access', False)]


@pytest.mark.parametrize('state,notice', [
    ({'running': False}, 'Start web access to pair a phone.'),
    ({'running': True, 'lan': False}, 'Turn on local network access below so phones can connect.'),
    ({'running': True, 'lan': True, 'firewall': {'state': 'blocked'}},
     'The firewall may be blocking other devices. Use Configure LAN firewall.'),
    ({'running': True, 'lan': True, 'firewall': {'state': 'no_network'}},
     'No connected private network was detected. Connect this board to your Wi-Fi or cable.'),
    ({'running': True, 'lan': True, 'firewall': {'state': 'ready'}}, ''),
])
def test_pairing_notice_names_the_first_missing_step(state, notice):
    assert RemoteAccessPage._notice(state) == notice


def test_a_custom_session_replaces_the_permanent_reading(isolated_remote_access):
    web, _ssh = isolated_remote_access
    web['devices'] = [{'id': 'one', 'permanent': True, 'duration_seconds': 3600,
                       'idle_seconds': None, 'expires': 2000000000}]
    text = text_of(render(RemoteAccessPage(), make_context(), FakeUI(), 'devices'))
    assert 'Permanent' not in text
    assert '--' not in text.split('Session')[-1]


def test_one_action_offers_everything_a_phone_still_needs(isolated_remote_access, monkeypatch):
    from frontends.tui.pages import remote

    web, _ssh = isolated_remote_access
    ran = []
    monkeypatch.setattr(remote.web_setup, 'apply', lambda say: ran.append(True))
    ctx, ui, page = make_context(), FakeUI(), RemoteAccessPage()
    for tab in ('web', 'network'):
        choice(render(page, ctx, ui, tab), 'Prepare the connection').handler(ui)
    question, danger = ui.confirmations[-1]
    assert danger and '1. Reachable from the local network' in question and '2. Start web access' in question
    assert 'Avahi' in question and 'fixed only if needed' in question
    assert len(ran) == 2 and ui.ran == ['Prepare the connection'] * 2
    ui.confirm_answer = False
    choice(render(page, ctx, ui), 'Prepare the connection').handler(ui)
    assert len(ran) == 2
    web.update(running=True, lan=True, firewall={'state': 'ready'}, name_health={'status': 'ready'})
    for tab in ('web', 'network'):
        assert not any(item.label == 'Prepare the connection' for item in render(page, ctx, ui, tab).choices)
