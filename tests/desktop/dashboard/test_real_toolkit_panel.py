"""Real Toolkit native controls never execute while searching or previewing."""
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QPushButton, QVBoxLayout

from bc250cc.infrastructure.steamos_real_toolkit import ACTIONS
from frontends.desktop.components.real_toolkit import LABELS, RealToolkitPanel
from frontends.desktop.pages.gpu_governor_state import GpuGovernorStateMixin


def test_alternative_buttons_keep_the_provider_explicit(qtbot):
    from bc250cc.infrastructure.steamos_alternative import ALTERNATIVE_ACTIONS
    from frontends.desktop.components.real_toolkit import SteamOSAlternativePanel

    panel = SteamOSAlternativePanel()
    qtbot.addWidget(panel)
    assert set(panel.buttons) == set(ALTERNATIVE_ACTIONS)
    for action, button in panel.buttons.items():
        with qtbot.waitSignal(panel.action_requested) as signal:
            button.click()
        assert signal.args[0]['action'] == 'steamos_alternative:' + action


def test_all_provider_actions_have_native_controls(qtbot):
    panel = RealToolkitPanel()
    qtbot.addWidget(panel)
    expected = {action.key for action in ACTIONS}
    assert set(LABELS) == set(panel.buttons) == expected
    events = []
    panel.action_requested.connect(events.append)
    panel.buttons['proton-install'].click()
    assert events == [{'action': 'real_toolkit:proton-install', 'governor': ''}]


def test_component_row_groups_secondary_actions_in_the_native_more_menu(qtbot):
    from frontends.desktop.i18n import tr

    panel = RealToolkitPanel()
    qtbot.addWidget(panel)
    row = panel.rows['gpu-install']
    assert row is panel.rows['gpu-revert']
    assert row.action.text() == tr('Install / update')
    events = []
    panel.action_requested.connect(events.append)
    row._fill_menu()
    actions = [action for action in row.menu.actions() if not action.isSeparator()]
    assert len(actions) == 2
    actions[0].trigger()
    assert events == [{'action': 'real_toolkit:gpu-revert', 'governor': ''}]
    actions[1].trigger()
    assert events[-1]['action'] == 'steamos_graphics_upstream'


def test_toolkit_changelog_uses_a_documentation_route_without_a_backend_action(qtbot):
    from types import SimpleNamespace

    from frontends.desktop.i18n import tr

    panel = RealToolkitPanel()
    qtbot.addWidget(panel)
    events = []
    panel.action_requested.connect(events.append)
    row = panel.rows['manual']
    row._fill_menu()
    changelog = next(action for action in row.menu.actions() if action.text() == tr("What's new"))
    changelog.trigger()
    assert events == [{'action': 'steamos_toolkit_changelog', 'governor': ''}]
    opened = []
    page = SimpleNamespace(current_state={}, _open_steamos_graphics_upstream=lambda **kwargs: opened.append(kwargs))
    GpuGovernorStateMixin.execute_dependency_action(
        page, action='steamos_toolkit_changelog', preference='auto', selected_components=set())
    assert opened == [{'dialog_parent': None, 'document': 'changelog'}]


def test_component_groups_preserve_every_action_exactly_once():
    from frontends.desktop.components.real_toolkit import ALTERNATIVE_TOOLS, TOOLS

    keys = [key for _category, _names, _description, actions in TOOLS for key in actions]
    assert len(keys) == len(set(keys)) == len(ACTIONS)
    alternative = [key for _category, _names, _description, actions in ALTERNATIVE_TOOLS for key in actions]
    from bc250cc.infrastructure.steamos_alternative import ALTERNATIVE_ACTIONS
    assert set(alternative) == set(ALTERNATIVE_ACTIONS)
    assert len(alternative) == len(set(alternative))


def test_live_language_change_preserves_search_routes_and_more_actions(qtbot):
    from frontends.desktop.i18n import (
        current_language,
        localize_widget_tree,
        set_language,
    )
    from frontends.desktop.pages.additional_settings import AdditionalSettingsPage

    previous = current_language()
    page = AdditionalSettingsPage()
    qtbot.addWidget(page)
    panel = page.panel.real_toolkit_panel
    events = []
    page.dependency_action_requested.connect(events.append)
    payloads = {key: dict(button.request_payload) for key, button in panel.buttons.items()}
    panel.search.setText('BE200')
    try:
        for language, title in [('en', 'CPU core unlock'), ('es', 'Desbloqueo de núcleos de CPU'),
                                ('en', 'CPU core unlock')]:
            set_language(language)
            localize_widget_tree(page)
            page.retranslate_dynamic_copy()
            assert panel.cards['cores-install'].title.text() == title
            assert panel.search.text() == 'BE200'
            assert {key for key, row in panel.rows.items() if not row.isHidden()} == {'be200'}
            assert {key: button.request_payload for key, button in panel.buttons.items()} == payloads
        assert events == []
    finally:
        set_language(previous)


def test_native_ownership_is_visible_before_selecting_a_toolkit_operation(qtbot):
    panel = RealToolkitPanel()
    qtbot.addWidget(panel)
    panel.set_provider_state({'native_ownership': {'cpu': ['/etc/systemd/system/bc250-smu-oc.service']}})
    assert not panel.buttons['cpu-install'].isEnabled()
    assert not panel.buttons['cpu-revert'].isEnabled()
    assert not panel.buttons['profiles'].isEnabled()
    assert not panel.buttons['install-all'].isEnabled()
    assert panel.buttons['gpu-install'].isEnabled()
    assert panel.buttons['manual'].isEnabled()
    assert panel.cards['cpu-install'].status.text() == 'BC250 Control Center'
    panel.retranslate_dynamic_copy()
    assert not panel.buttons['cpu-install'].isEnabled()
    panel.set_provider_state({'native_ownership': {}})
    assert panel.buttons['cpu-install'].isEnabled()
    assert panel.cards['cpu-install'].status.isHidden()


def test_native_cec_keeps_status_available_without_blocking_unrelated_bulk_actions(qtbot):
    panel = RealToolkitPanel()
    qtbot.addWidget(panel)
    panel.set_provider_state({'native_ownership': {'cec': ['native CEC configuration']}})
    assert not panel.buttons['cec-setup'].isEnabled()
    assert not panel.buttons['cec-wake-install'].isEnabled()
    assert panel.buttons['cec-status'].isEnabled()
    assert panel.buttons['install-all'].isEnabled()
    assert panel.buttons['revert-all'].isEnabled()


def test_native_video_configuration_protects_its_controls_without_blocking_graphics(qtbot):
    panel = RealToolkitPanel()
    qtbot.addWidget(panel)
    panel.set_provider_state({'native_ownership': {'video': ['native VA-API environment']}})
    assert not panel.buttons['video-install'].isEnabled()
    assert not panel.buttons['video-revert'].isEnabled()
    assert not panel.buttons['install-all'].isEnabled()
    assert not panel.buttons['revert-all'].isEnabled()
    assert panel.cards['video-install'].status.text() == 'BC250 Control Center'
    assert panel.buttons['combined-install'].isEnabled()
    assert panel.buttons['manual'].isEnabled()
    assert panel.buttons['verify'].isEnabled()


def test_native_request_reaches_the_toolkit_action_handler():
    from types import SimpleNamespace
    calls = []
    page = SimpleNamespace(current_state={},
                           _manage_real_toolkit=lambda action, **kwargs: calls.append(action))
    GpuGovernorStateMixin.execute_dependency_action(
        page, action='real_toolkit:dual-install', preference='auto', selected_components=set())
    assert calls == ['dual-install']


def test_dashboard_uses_real_toolkit_configuration_without_old_kernel_gate(qtbot, tmp_path):
    from PyQt6.QtCore import QSettings

    from frontends.desktop.components.dashboard_widgets import PreparationSidebar
    from frontends.desktop.core.state import DashboardState
    sidebar = PreparationSidebar(settings=QSettings(str(tmp_path / 'ui.ini'), QSettings.Format.IniFormat),
                                 standalone=True)
    qtbot.addWidget(sidebar)
    sidebar.set_state(DashboardState(preparation_tools={
        'os_family': 'steamos', 'gfx1013_compute': {
            'reason_key': 'steamos-dedicated-backend',
            'steamos_kernel_ready': False,
            'steamos_real_toolkit': {'graphics': {'state': 'configured', 'activation_configured': True},
                                     'proton': {'state': 'installed'}},
        }}))
    assert not sidebar.real_toolkit_panel.isHidden()
    assert sidebar.real_toolkit_panel.isEnabled()
    assert sidebar.gfx_secondary_button.isEnabled()
    with qtbot.waitSignal(sidebar.dependency_action_requested) as signal:
        sidebar.gfx_secondary_button.click()
    assert signal.args[0]['action'] == 'real_toolkit:verify'


@pytest.mark.parametrize('graphics,label', [
    ({}, 'Unknown'),
    ({'state': 'incomplete', 'activation_configured': False}, 'Incomplete'),
    ({'state': 'configured', 'activation_configured': True, 'active': None}, 'Configured'),
    ({'state': 'not-installed', 'activation_configured': False}, 'Not installed'),
])
def test_dashboard_never_falls_back_to_old_provider_steps_while_inventory_changes(qtbot, tmp_path, graphics, label):
    from PyQt6.QtCore import QSettings

    from frontends.desktop.components.dashboard_widgets import PreparationSidebar
    from frontends.desktop.core.state import DashboardState
    from frontends.desktop.i18n import tr

    sidebar = PreparationSidebar(settings=QSettings(str(tmp_path / 'ui.ini'), QSettings.Format.IniFormat),
                                 standalone=True)
    qtbot.addWidget(sidebar)
    policy = {'reason_key': 'steamos-dedicated-backend', 'steamos_kernel_ready': False}
    if graphics:
        policy['steamos_real_toolkit'] = {'graphics': graphics}
    sidebar.set_state(DashboardState(preparation_tools={'os_family': 'steamos', 'gfx1013_compute': policy}))
    for button, action in [(sidebar.gfx_primary_button, 'combined-install'),
                           (sidebar.gfx_secondary_button, 'verify'),
                           (sidebar.gfx_tertiary_button, 'proton-install'),
                           (sidebar.gfx_quaternary_button, 'combined-revert')]:
        assert button.isEnabled()
        assert button.request_payload['action'] == 'real_toolkit:' + action
    assert sidebar.steamos_radv_status.text() == tr(label)
    assert sidebar.steamos_kernel_status.text() == tr('Unknown')


def test_partial_proton_variants_are_shown_as_incomplete(qtbot, tmp_path):
    from PyQt6.QtCore import QSettings

    from frontends.desktop.components.dashboard_widgets import PreparationSidebar
    from frontends.desktop.core.state import DashboardState
    from frontends.desktop.i18n import tr

    sidebar = PreparationSidebar(settings=QSettings(str(tmp_path / 'ui.ini'), QSettings.Format.IniFormat),
                                 standalone=True)
    qtbot.addWidget(sidebar)
    sidebar.set_state(DashboardState(preparation_tools={
        'os_family': 'steamos', 'gfx1013_compute': {
            'reason_key': 'steamos-dedicated-backend', 'steamos_real_toolkit': {
                'proton': {'state': 'incomplete', 'tools': ['one-complete-variant']},
            },
        },
    }))
    assert sidebar.steamos_fsr4_status.text() == tr('Incomplete')
    assert sidebar.gfx_tertiary_button.isEnabled()


def test_additional_settings_opens_provider_index_without_backend_dispatch(qtbot, tmp_path):
    from PyQt6.QtCore import QSettings

    from frontends.desktop.components.dashboard_widgets import PreparationSidebar
    from frontends.desktop.core.state import DashboardState

    sidebar = PreparationSidebar(settings=QSettings(str(tmp_path / 'ui.ini'), QSettings.Format.IniFormat),
                                 standalone=True)
    qtbot.addWidget(sidebar)
    sidebar.set_state(DashboardState(preparation_tools={'os_family': 'steamos'}))
    browser = sidebar.compatibility_browser
    calls = []
    sidebar.dependency_action_requested.connect(calls.append)
    for card in [sidebar.real_toolkit_card, sidebar.steamos_alternative_card]:
        assert card in browser.cards()
        row = browser._rows[id(card)]
        assert row.details.isHidden()
        card.primary_button.click()
        assert not row.details.isHidden()
    assert calls == []


def test_search_and_categories_filter_without_dispatch(qtbot):
    panel = RealToolkitPanel()
    qtbot.addWidget(panel)
    events = []
    panel.action_requested.connect(events.append)
    panel.search.setText('BE200')
    assert {key for key, row in panel.rows.items() if not row.isHidden()} == {'be200'}
    panel.search.clear()
    panel.category.setCurrentIndex(panel.category.findData('audio'))
    assert {key for key, row in panel.rows.items() if not row.isHidden()} == {
        action.key for action in ACTIONS if action.category == 'audio'}
    panel.search.setText('qxzxq')
    assert not panel.empty.isHidden() and events == []


def test_enter_in_search_cannot_trigger_the_default_dialog_action(qtbot):
    dialog = QDialog()
    qtbot.addWidget(dialog)
    layout = QVBoxLayout(dialog)
    panel = RealToolkitPanel()
    layout.addWidget(panel)
    default = QPushButton('Install')
    default.setDefault(True)
    default.clicked.connect(dialog.accept)
    layout.addWidget(default)
    dialog.resize(800, 600)
    dialog.show()
    panel.search.setFocus()
    qtbot.keyClicks(panel.search, 'Proton')
    qtbot.keyClick(panel.search, Qt.Key.Key_Return)
    qtbot.keyClick(panel.search, Qt.Key.Key_Enter)
    assert dialog.isVisible()
