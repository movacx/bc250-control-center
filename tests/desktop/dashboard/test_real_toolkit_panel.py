"""Provider components are ordinary Compatibility rows, never executed by browsing."""
import pytest

from bc250cc.infrastructure.steamos_real_toolkit import ACTIONS
from frontends.desktop.components.real_toolkit import (
    ALTERNATIVE_SCOPE,
    LABELS,
    REAL_TOOLKIT_SCOPE,
    RealToolkitRows,
    SteamOSAlternativeRows,
)
from frontends.desktop.pages.gpu_governor_state import GpuGovernorStateMixin

OFFERED_ELSEWHERE = {'cpu-install', 'gpu-install', 'cu', 'cores-install', 'profiles', 'swap',
                     'zswap-install', 'uma-install', 'coolercontrol', 'sensors', 'extras', 'emulators',
                     'decky-install', 'kyty-install', 'lichii-install', 'install-all', 'manual', 'revert-all',
                     'mitigations-disable', 'mitigations-restore'}


def _sidebar(qtbot, tmp_path, os_family='steamos'):
    from PyQt6.QtCore import QSettings

    from frontends.desktop.components.dashboard_widgets import PreparationSidebar
    from frontends.desktop.core.state import DashboardState
    sidebar = PreparationSidebar(settings=QSettings(str(tmp_path / 'ui.ini'), QSettings.Format.IniFormat),
                                 standalone=True)
    qtbot.addWidget(sidebar)
    sidebar.set_state(DashboardState(preparation_tools={'os_family': os_family}))
    return sidebar


def test_alternative_buttons_keep_the_provider_explicit(qtbot):
    from bc250cc.infrastructure.steamos_alternative import ALTERNATIVE_ACTIONS

    rows = SteamOSAlternativeRows()
    assert set(rows.buttons) == set(ALTERNATIVE_ACTIONS)
    for action, button in rows.buttons.items():
        with qtbot.waitSignal(rows.action_requested) as signal:
            button.click()
        assert signal.args[0]['action'] == 'steamos_alternative:' + action


def test_every_row_names_the_provider_it_comes_from():
    for rows, scope in ((RealToolkitRows(), REAL_TOOLKIT_SCOPE), (SteamOSAlternativeRows(), ALTERNATIVE_SCOPE)):
        assert rows.all_cards()
        assert {card.scope.text() for card in rows.all_cards()} == {scope}
    assert REAL_TOOLKIT_SCOPE == 'SteamOS · rpf16rj'
    assert ALTERNATIVE_SCOPE == 'SteamOS · keyboardspecialist'


def test_features_the_application_already_offers_are_not_exposed():
    keys = {action.key for action in ACTIONS}
    assert not keys & OFFERED_ELSEWHERE
    assert 'acpi-install' in keys and 'keyring' in keys and 'aic8800' in keys


def test_all_provider_actions_have_native_controls():
    rows = RealToolkitRows()
    expected = {action.key for action in ACTIONS}
    assert set(LABELS) == set(rows.buttons) == expected
    events = []
    rows.action_requested.connect(events.append)
    rows.buttons['proton-install'].click()
    assert events == [{'action': 'real_toolkit:proton-install', 'governor': ''}]


def test_component_groups_preserve_every_action_exactly_once():
    from bc250cc.infrastructure.steamos_alternative import ALTERNATIVE_ACTIONS
    from frontends.desktop.components.real_toolkit import ALTERNATIVE_TOOLS, TOOLS

    keys = [key for _category, _names, _description, actions in TOOLS for key in actions]
    assert len(keys) == len(set(keys)) == len(ACTIONS)
    alternative = [key for _category, _names, _description, actions in ALTERNATIVE_TOOLS for key in actions]
    assert set(alternative) == set(ALTERNATIVE_ACTIONS)
    assert len(alternative) == len(set(alternative))


def test_rows_are_placed_in_the_topic_that_owns_them(qtbot, tmp_path):
    sidebar = _sidebar(qtbot, tmp_path)
    groups = dict(sidebar.compatibility_groups)
    rows = sidebar.real_toolkit_rows
    assert set(rows.cards_for('system')) <= set(groups['System'])
    assert set(rows.cards_for('graphics')) <= set(groups['Kernel and graphics'])
    assert set(rows.cards_for('video')) <= set(groups['Video'])
    browser = sidebar.drivers_browser
    assert set(rows.cards_for('audio', 'drivers')) <= set(browser.cards())
    assert not hasattr(sidebar, 'real_toolkit_panel')


def test_component_row_groups_secondary_actions_in_the_native_more_menu(qtbot, tmp_path):
    from frontends.desktop.i18n import tr

    sidebar = _sidebar(qtbot, tmp_path)
    rows = sidebar.real_toolkit_rows
    row = sidebar.compatibility_browser._rows[id(rows.cards['proton-install'])]
    assert row.action.text() == tr('Install / update')
    events = []
    rows.action_requested.connect(events.append)
    row._fill_menu()
    actions = [action for action in row.menu.actions() if not action.isSeparator()]
    assert len(actions) == 2
    actions[0].trigger()
    assert events == [{'action': 'real_toolkit:proton-revert', 'governor': ''}]
    actions[1].trigger()
    assert events[-1]['action'] == 'steamos_graphics_upstream'


def test_toolkit_changelog_uses_a_documentation_route_without_a_backend_action(qtbot, tmp_path):
    from types import SimpleNamespace

    from frontends.desktop.i18n import tr

    sidebar = _sidebar(qtbot, tmp_path)
    rows = sidebar.real_toolkit_rows
    events = []
    rows.action_requested.connect(events.append)
    row = sidebar.compatibility_browser._rows[id(rows.cards['verify'])]
    row._fill_menu()
    changelog = next(action for action in row.menu.actions() if action.text() == tr("What's new"))
    changelog.trigger()
    assert events == [{'action': 'steamos_toolkit_changelog', 'governor': ''}]
    opened = []
    page = SimpleNamespace(current_state={}, _open_steamos_graphics_upstream=lambda **kwargs: opened.append(kwargs))
    GpuGovernorStateMixin.execute_dependency_action(
        page, action='steamos_toolkit_changelog', preference='auto', selected_components=set())
    assert opened == [{'dialog_parent': None, 'document': 'changelog'}]


def test_live_language_change_preserves_routes_and_more_actions(qtbot):
    from frontends.desktop.i18n import (
        current_language,
        localize_widget_tree,
        set_language,
    )
    from frontends.desktop.pages.additional_settings import AdditionalSettingsPage

    previous = current_language()
    page = AdditionalSettingsPage()
    qtbot.addWidget(page)
    rows = page.panel.real_toolkit_rows
    events = []
    page.dependency_action_requested.connect(events.append)
    payloads = {key: dict(button.request_payload) for key, button in rows.buttons.items()}
    try:
        for language, title in [('en', 'Audio'), ('es', 'Audio'), ('en', 'Audio')]:
            set_language(language)
            localize_widget_tree(page)
            page.retranslate_dynamic_copy()
            assert {key: button.request_payload for key, button in rows.buttons.items()} == payloads
        assert events == []
    finally:
        set_language(previous)


def test_native_ownership_is_visible_before_selecting_a_toolkit_operation():
    rows = RealToolkitRows()
    rows.set_provider_state({'native_ownership': {'acpi': ['/etc/native-acpi']}})
    assert not rows.buttons['acpi-install'].isEnabled()
    assert not rows.buttons['acpi-revert'].isEnabled()
    assert rows.buttons['recovery'].isEnabled()
    assert rows.cards['acpi-install'].status.text() == 'BC250 Control Center'
    rows.retranslate_dynamic_copy()
    assert not rows.buttons['acpi-install'].isEnabled()
    rows.set_provider_state({'native_ownership': {}})
    assert rows.buttons['acpi-install'].isEnabled()
    assert rows.cards['acpi-install'].status.isHidden()


def test_native_cec_keeps_status_available():
    rows = RealToolkitRows()
    rows.set_provider_state({'native_ownership': {'cec': ['native CEC configuration']}})
    assert not rows.buttons['cec-setup'].isEnabled()
    assert not rows.buttons['cec-wake-install'].isEnabled()
    assert rows.buttons['cec-status'].isEnabled()


def test_native_video_configuration_protects_its_controls_without_blocking_graphics():
    rows = RealToolkitRows()
    rows.set_provider_state({'native_ownership': {'video': ['native VA-API environment']}})
    assert not rows.buttons['video-install'].isEnabled()
    assert not rows.buttons['video-revert'].isEnabled()
    assert rows.cards['video-install'].status.text() == 'BC250 Control Center'
    assert rows.buttons['combined-install'].isEnabled()
    assert rows.buttons['verify'].isEnabled()


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
    assert sidebar.real_toolkit_rows.cards['proton-install'].isEnabled()
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


def test_toolkit_rows_are_enabled_only_on_steamos(qtbot, tmp_path):
    steamos = _sidebar(qtbot, tmp_path, 'steamos')
    assert all(card.isEnabled() for card in steamos.real_toolkit_rows.all_cards())
    other = _sidebar(qtbot, tmp_path, 'arch')
    assert not any(card.isEnabled() for card in other.real_toolkit_rows.all_cards())
    assert all(card.isHidden() for card in other.real_toolkit_rows.all_cards())


def test_steamos_names_whose_row_each_one_is_and_hides_our_acpi(qtbot, tmp_path):
    from frontends.desktop.components.real_toolkit import NATIVE_SCOPE

    sidebar = _sidebar(qtbot, tmp_path, 'steamos')
    assert NATIVE_SCOPE == 'SteamOS · BC250 Control Center'
    for name in ('cyan_card', 'oberon_card', 'pacman_lock_card', 'hdmi_ac3_card', 'vaapi_card'):
        assert getattr(sidebar, name).scope.text() == NATIVE_SCOPE, name
    assert sidebar.acpi_card.isHidden()
    assert not sidebar.real_toolkit_rows.cards['acpi-install'].isHidden()
    assert 'SteamOS Real Toolkit' not in sidebar.gfx_card.scope.text()


def test_other_systems_keep_their_acpi_and_their_own_scope_text(qtbot, tmp_path):
    sidebar = _sidebar(qtbot, tmp_path, 'arch')
    assert not sidebar.acpi_card.isHidden()
    assert 'BC250 Control Center' not in sidebar.cyan_card.scope.text()


# Product names that read the same in every language: no catalog entry needed.
PRODUCT_NAMES = {'Proton · FSR4', 'Dolby Digital · AC-3', 'AIC8800 · Wi-Fi / Bluetooth', 'Intel BE200',
                 'DualSense', 'OpenLinkHub', 'Mesa / RADV · GFX1013', 'BC-250 GE-Proton'}


# A translation that is spelled exactly like the English in that language.
SAME_IN_LANGUAGE = {('hu', 'Intel BE200 Wi-Fi firmware')}


def _row_strings():
    from bc250cc.application.preparation.steamos_providers import ALTERNATIVE_ACTIONS
    from frontends.desktop.components.real_toolkit import ALTERNATIVE_TOOLS, TOOLS
    strings = {pair[0] for pair in (*LABELS.values(), *ALTERNATIVE_ACTIONS.values())}
    for spec in (TOOLS, ALTERNATIVE_TOOLS):
        for _category, names, descriptions, _keys in spec:
            strings |= {names[0], descriptions[0]}
    strings |= {'Repair', 'SteamOS toolkit', 'Controllers and wireless'}
    return strings - PRODUCT_NAMES


def test_every_provider_row_string_is_translated_in_every_language():
    from frontends.desktop.i18n.locale_catalog import (
        COMPLETE_LOCALES,
        load_locale_catalog,
    )

    for code in COMPLETE_LOCALES:
        catalog = load_locale_catalog(code)
        missing = sorted(source for source in _row_strings() if not catalog.get(source))
        assert not missing, (code, missing)
        if code != 'en':
            untranslated = sorted(source for source in _row_strings()
                                  if catalog[source] == source and (code, source) not in SAME_IN_LANGUAGE)
            assert not untranslated, (code, untranslated)


def test_rows_follow_the_interface_language_for_all_thirty_languages(qtbot):
    from frontends.desktop.i18n import current_language, set_language, tr
    from frontends.desktop.i18n.locale_catalog import COMPLETE_LOCALES

    previous = current_language()
    rows = RealToolkitRows()
    try:
        for code in COMPLETE_LOCALES:
            set_language(code)
            rows.retranslate_dynamic_copy()
            assert rows.cards['acpi-install'].title.text() == tr('ACPI power management'), code
            assert rows.buttons['acpi-revert'].text() == tr('Remove ACPI fix'), code
            if code != 'en':
                assert rows.buttons['acpi-revert'].text() != 'Remove ACPI fix', code
    finally:
        set_language(previous)


def test_provider_cards_never_become_windows_on_a_page_that_does_not_place_them(qtbot, tmp_path):
    """The Dashboard builds the sidebar without Compatibility/Drivers lists; showing a
    parentless card there opened dozens of loose windows."""
    from PyQt6.QtCore import QSettings

    from frontends.desktop.components.dashboard_widgets import PreparationSidebar
    from frontends.desktop.core.state import DashboardState

    sidebar = PreparationSidebar(settings=QSettings(str(tmp_path / 'ui.ini'), QSettings.Format.IniFormat))
    qtbot.addWidget(sidebar)
    sidebar.show()
    sidebar.set_state(DashboardState(preparation_tools={'os_family': 'steamos'}))
    qtbot.wait(50)
    cards = [*sidebar.real_toolkit_rows.all_cards(), *sidebar.steamos_alternative_rows.all_cards()]
    assert cards
    for card in cards:
        assert not card.isWindow(), card.title.text()
        assert card.parentWidget() is not None
    assert not [card for card in cards if card.isVisible()]


def test_every_driver_row_on_steamos_names_whose_it_is(qtbot, tmp_path):
    from frontends.desktop.components.real_toolkit import (
        ALTERNATIVE_SCOPE,
        NATIVE_SCOPE,
        REAL_TOOLKIT_SCOPE,
    )

    sidebar = _sidebar(qtbot, tmp_path, 'steamos')
    browser = sidebar.drivers_browser
    browser.refresh()
    origins = {}
    for card in browser.cards():
        if card.isHidden():
            continue  # superseded by the provider's own row on SteamOS
        origins[card.title.text()] = browser._rows[id(card)].scope.text().removeprefix('Compatibility: ')
    assert origins and all(origins.values()), origins
    assert set(origins.values()) <= {NATIVE_SCOPE, REAL_TOOLKIT_SCOPE, ALTERNATIVE_SCOPE}, origins
    assert NATIVE_SCOPE in origins.values() and REAL_TOOLKIT_SCOPE in origins.values()


def _steamos_with(qtbot, tmp_path, os_family='steamos', **tools):
    from PyQt6.QtCore import QSettings

    from frontends.desktop.components.dashboard_widgets import PreparationSidebar
    from frontends.desktop.core.state import DashboardState
    sidebar = PreparationSidebar(settings=QSettings(str(tmp_path / 'ui.ini'), QSettings.Format.IniFormat),
                                 standalone=True)
    qtbot.addWidget(sidebar)
    sidebar.set_state(DashboardState(preparation_tools={'os_family': os_family, **tools}))
    return sidebar


def test_steamos_offers_the_toolkits_rows_and_hides_our_copies_of_the_same_things(qtbot, tmp_path):
    sidebar = _steamos_with(qtbot, tmp_path, vaapi_video={'state': 'not-installed', 'supported': True},
                            accessories={'hdmi_ac3': {'state': 'not-installed'}, 'hdmi_cec': {'state': 'not-installed'}})
    for name in ('vaapi_card', 'hdmi_ac3_card', 'hdmi_cec_card', 'steamos_proton_card'):
        assert getattr(sidebar, name).isHidden(), name
    rows = sidebar.real_toolkit_rows
    for key in ('video-install', 'ac3-install', 'dual-install', 'cec-setup', 'proton-install'):
        assert not rows.cards[key].isHidden(), key


def test_an_install_of_ours_that_already_exists_stays_visible_so_it_can_be_removed(qtbot, tmp_path):
    sidebar = _steamos_with(qtbot, tmp_path, vaapi_video={'state': 'active', 'installed': True, 'supported': True},
                            accessories={'hdmi_ac3': {'state': 'active'}, 'hdmi_cec': {'state': 'installed'}})
    for name in ('vaapi_card', 'hdmi_ac3_card', 'hdmi_cec_card'):
        assert not getattr(sidebar, name).isHidden(), name
    assert sidebar.steamos_proton_card.isHidden(), 'its actions are the toolkit row'


def test_another_installer_already_managing_it_does_not_bring_our_copy_back(qtbot, tmp_path):
    sidebar = _steamos_with(qtbot, tmp_path, vaapi_video={'state': 'managed-elsewhere', 'supported': True},
                            accessories={'hdmi_ac3': {'state': 'managed-elsewhere'}, 'hdmi_cec': {'state': 'managed-elsewhere'}})
    assert all(getattr(sidebar, name).isHidden() for name in ('vaapi_card', 'hdmi_ac3_card', 'hdmi_cec_card'))


def test_other_systems_keep_all_of_ours(qtbot, tmp_path):
    sidebar = _steamos_with(qtbot, tmp_path, 'arch', vaapi_video={'state': 'not-installed', 'supported': True},
                            accessories={'hdmi_ac3': {'state': 'not-installed'}, 'hdmi_cec': {'state': 'not-installed'}})
    assert not sidebar.vaapi_card.isHidden()
    assert not sidebar.hdmi_ac3_card.isHidden() and not sidebar.hdmi_cec_card.isHidden()


def test_boot_options_sit_under_the_list_of_tools_not_above_it(qtbot, tmp_path):
    """Read-only mode, kernel options and mitigations come last, as in the other workflows."""
    sidebar = _steamos_with(qtbot, tmp_path, steamos_readonly={'available': True, 'state': 'enabled'})
    layout = sidebar.compatibility_browser.parentWidget().layout()
    widgets = [layout.itemAt(index).widget() for index in range(layout.count())]
    assert widgets.index(sidebar.compatibility_browser) < widgets.index(sidebar._boot_holder)
    last = layout.itemAt(layout.count() - 1)
    assert last.spacerItem() is not None, 'the closing stretch stays at the very end'
    between = [layout.itemAt(i) for i in range(layout.count())
               if widgets[i] is None and i < widgets.index(sidebar.compatibility_browser)]
    assert not between, 'no stretch between the filter and the list'


@pytest.mark.parametrize('kernel,text', [
    ({'installed': True, 'ready': True}, 'Installed'),
    ({'installed': True, 'ready': False, 'reboot_pending': True}, 'Reboot required'),
    ({'installed': True, 'ready': False}, 'Incomplete'),
    ({}, 'Not installed'),
])
def test_an_install_from_the_previous_version_shows_its_kernel_state_on_the_alternative_row(kernel, text):
    from frontends.desktop.i18n import tr

    rows = SteamOSAlternativeRows()
    rows.set_provider_state({'radv': {'state': 'ready'}, 'kernel': kernel})
    assert rows.cards['kernel-install'].status.text() == tr(text)
    assert rows.cards['graphics-install'].status.text() == tr('Installed')


@pytest.mark.parametrize('status,visible', [
    ('not-installed', False), ('managed-elsewhere', False),
    ('active', True), ('outdated', True), ('needs-repair', True), ('pending-reboot', True),
])
def test_our_acpi_stays_for_whoever_installed_it_with_the_previous_version(qtbot, tmp_path, status, visible):
    from frontends.desktop.components.real_toolkit import NATIVE_SCOPE

    sidebar = _steamos_with(qtbot, tmp_path, system_setup={'helper_available': True, 'acpi': {'status': status}})
    assert (not sidebar.acpi_card.isHidden()) is visible
    if visible:
        assert sidebar.acpi_card.scope.text() == NATIVE_SCOPE
    assert not sidebar.real_toolkit_rows.cards['acpi-install'].isHidden()
