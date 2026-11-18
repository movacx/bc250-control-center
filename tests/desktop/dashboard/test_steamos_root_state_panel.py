"""The application shows whether SteamOS' system files are locked, and what a toolkit action did to them."""
import pytest

from frontends.desktop.i18n import tr
from frontends.desktop.pages.additional_settings import AdditionalSettingsPage


@pytest.fixture
def panel(qtbot):
    page = AdditionalSettingsPage()
    qtbot.addWidget(page)
    page.resize(1200, 900)
    page.show()
    return page.panel


def _tools(mode='enabled', **session):
    return {'steamos_readonly': {'available': True, 'state': mode, 'toolkit_session': {
        'running': False, 'action': '', 'restore_pending': False, **session}}}


def test_a_plain_protected_or_writable_root_keeps_the_quiet_panel(panel):
    for mode in ('enabled', 'disabled'):
        panel._update_steamos_readonly_control(_tools(mode))
        assert panel.readonly_status.isHidden() and panel.readonly_session_note.isHidden(), mode
        assert panel.readonly_button.isEnabled()


def test_a_toolkit_action_in_progress_says_the_unlock_is_on_purpose_and_blocks_a_second_switch(panel):
    panel._update_steamos_readonly_control(_tools('disabled', running=True, action='acpi-install'))
    assert panel.readonly_status.text() == tr('In use') and not panel.readonly_status.isHidden()
    assert not panel.readonly_session_note.isHidden()
    assert 'is running' in panel.readonly_session_note.text()
    assert not panel.readonly_button.isEnabled(), 'a manual switch would fight the running action'


def test_an_action_that_died_with_the_system_unlocked_offers_to_lock_it_again(panel):
    panel._update_steamos_readonly_control(_tools('disabled', restore_pending=True, action='video-install'))
    assert panel.readonly_status.text() == tr('Interrupted') and not panel.readonly_status.isHidden()
    assert 'ended before it could lock' in panel.readonly_session_note.text()
    assert panel.readonly_button.isEnabled()
    assert panel.readonly_button.text() == tr('Turn read-only back on')
    with_signal = []
    panel.dependency_action_requested.connect(with_signal.append)
    panel.readonly_button.click()
    assert with_signal[0]['action'] == 'steamos_readonly_enable'


def test_the_notice_goes_away_once_the_system_is_locked_again(panel):
    panel._update_steamos_readonly_control(_tools('disabled', restore_pending=True))
    panel._update_steamos_readonly_control(_tools('enabled'))
    assert panel.readonly_session_note.isHidden() and panel.readonly_status.isHidden()


def test_a_running_action_wins_over_a_stale_interruption(panel):
    panel._update_steamos_readonly_control(_tools('disabled', running=True, restore_pending=True))
    assert panel.readonly_status.text() == tr('In use')


@pytest.mark.parametrize('mode,kwargs,text', [
    ('enabled', {}, 'Protected'),
    ('disabled', {}, 'Writable'),
    ('disabled', {'running': True}, 'In use'),
    ('disabled', {'restore_pending': True}, 'Interrupted'),
])
def test_the_toolkit_management_row_reports_the_lock(panel, mode, kwargs, text):
    panel._update_steamos_readonly_control(_tools(mode, **kwargs))
    card = panel.real_toolkit_rows.cards['verify']
    assert card.status.text() == tr(text) and not card.status.isHidden()
    panel.real_toolkit_rows.set_provider_state({'native_ownership': {}})
    assert card.status.text() == tr(text), 'refreshing provider state must not erase it'


def test_an_unreadable_state_leaves_the_management_row_without_a_status(panel):
    panel._update_steamos_readonly_control(_tools('unknown'))
    assert panel.real_toolkit_rows.cards['verify'].status.isHidden()
