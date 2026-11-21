from types import SimpleNamespace

from PyQt6.QtWidgets import QApplication

from bc250cc.infrastructure import dependencias_repository as repo_module
from frontends.desktop.components.dashboard_widgets import PreparationSidebar

_APP = QApplication.instance() or QApplication([])


def _main(sidebar):
    button = sidebar.directmesh_install_button
    return button.text(), button.request_payload['action']


def test_card_state_actions_and_copy():
    sidebar = PreparationSidebar(standalone=True)
    releases = [{'tag': 'directmesh-v1.5', 'version': '1.5'},
                {'tag': 'directmesh-v1.4', 'version': '1.4', 'default': True},
                {'tag': 'directmesh-v1.3', 'version': '1.3'}]
    state = dict(supported=True, platform='host', installed=True, installed_version='1.4',
                 installed_tag='directmesh-v1.4', selected_tag='directmesh-v1.4', releases=releases,
                 newer={'tag': 'directmesh-v1.5', 'version': '1.5'},
                 launch_option='VK_DRIVER_FILES=test %command%')
    sidebar._render_directmesh(state)
    assert sidebar.directmesh_card.status.text() == 'Update available'
    assert sidebar.directmesh_card.scope.text() == 'Arch family · v1.4'
    sidebar.directmesh_copy_button.click()
    assert _APP.clipboard().text() == state['launch_option']
    assert not hasattr(sidebar, 'directmesh_upgrade_button')
    assert not hasattr(sidebar, 'directmesh_upstream_button')

    # The main button follows the version picked in the combo box.
    combo = sidebar.directmesh_version_combo
    assert _main(sidebar) == ('Reinstall', 'directmesh_upgrade:directmesh-v1.4')
    combo.setCurrentIndex(combo.findData('directmesh-v1.5'))
    assert _main(sidebar) == ('Update to 1.5', 'directmesh_upgrade:directmesh-v1.5')
    combo.setCurrentIndex(combo.findData('directmesh-v1.3'))
    assert _main(sidebar) == ('Switch to 1.3', 'directmesh_upgrade:directmesh-v1.3')
    actions = []
    sidebar.directmesh_card.action_requested.connect(actions.append)
    sidebar.directmesh_install_button.click()
    assert actions[-1]['action'] == 'directmesh_upgrade:directmesh-v1.3'

    sidebar._render_directmesh({**state, 'installed': False, 'installed_tag': '', 'installed_version': '',
                                'newer': None, 'launch_option': ''})
    assert _main(sidebar) == ('Install 1.4', 'directmesh_upgrade:directmesh-v1.4')
    assert sidebar.directmesh_check_button.isHidden() and sidebar.directmesh_remove_button.isHidden()

    sidebar._render_directmesh({'supported': False, 'reason': 'Unavailable here'})
    assert sidebar.directmesh_card.status.text() == 'Unsupported'
    assert 'Unavailable here' in sidebar.directmesh_card.detail.text()
    assert not sidebar.directmesh_install_button.isEnabled()
    assert sidebar.directmesh_launch_row.isHidden()


def test_repository_upgrade_and_uninstall_platform(monkeypatch):
    repo = repo_module.DependenciasRepository()
    repo._os_repository = lambda: SimpleNamespace(info=SimpleNamespace(family='bazzite', distro_id='bazzite'))
    repo._abrir_terminal = lambda command, title: (command, title)
    monkeypatch.setattr(repo_module, 'read_os_release', lambda: {'VERSION_ID': '42'})
    monkeypatch.setattr(repo_module, 'directmesh_state', lambda **kw: {'supported': True})
    selected = []
    monkeypatch.setattr(repo_module, 'select_directmesh_release', selected.append)
    monkeypatch.setattr(repo_module, 'build_directmesh_install_command', lambda **kw: str(kw))
    monkeypatch.setattr(repo_module, 'build_directmesh_uninstall_command', lambda **kw: str(kw))
    command, _ = repo.gestionar_directmesh('upgrade:directmesh-v1.5')
    assert selected == ['directmesh-v1.5']
    assert "'version_id': '42'" in command
    command, _ = repo.gestionar_directmesh('uninstall')
    assert "'family': 'bazzite'" in command and "'distro_id': 'bazzite'" in command


def test_installed_tools_open_their_activation_details_once():
    """A launch option behind "Show details" is never found: once DirectMesh is
    installed, its row opens by itself, and a row the user closed stays closed."""
    sidebar = PreparationSidebar(standalone=True)
    browser = sidebar.compatibility_browser
    details = browser._rows[id(sidebar.directmesh_card)].details
    base = dict(supported=True, platform='host', releases=[{'tag': 'directmesh-v1.4', 'version': '1.4', 'default': True}],
                selected_tag='directmesh-v1.4', launch_option='VK_DRIVER_FILES=test %command%')
    sidebar._render_directmesh({**base, 'installed': False})
    assert details.isHidden()
    installed = {**base, 'installed': True, 'installed_tag': 'directmesh-v1.4', 'installed_version': '1.4'}
    sidebar._render_directmesh(installed)
    assert not details.isHidden()
    details.hide()
    sidebar._render_directmesh(installed)
    assert details.isHidden()


def test_the_gfx1013_row_opens_while_it_needs_a_launch_option():
    sidebar = PreparationSidebar(standalone=True)
    details = sidebar.compatibility_browser._rows[id(sidebar.gfx_card)].details
    sidebar._reveal_next_step(sidebar.gfx_card, 'bazzite_async', False)
    assert details.isHidden()
    sidebar._reveal_next_step(sidebar.gfx_card, 'bazzite_async', True)
    assert not details.isHidden()


def test_the_arch_route_offers_its_own_launch_option_like_bazzite():
    """Arch/Fedora's patched RADV: installed but not in this session, the row
    opens with the per-game option and Bazzite's tip; active, it needs neither."""
    from bc250cc.infrastructure.radv_async_compute import RADV_ASYNC_LAUNCH_OPTION

    sidebar = PreparationSidebar(standalone=True)
    details = sidebar.compatibility_browser._rows[id(sidebar.gfx_card)].details
    radv = dict(installed=True, enabled=True, version='26.2.3', expected_version='26.2.3', kernel='7.3.5-arch1-1')
    sidebar._render_radv_async({**radv, 'state': 'relogin-required'}, {})
    assert not sidebar.radv_launch_row.isHidden() and not details.isHidden()
    assert 'launch option below' in sidebar.gfx_card.detail.text()
    sidebar.radv_launch_copy_button.click()
    assert _APP.clipboard().text() == RADV_ASYNC_LAUNCH_OPTION == 'bc250cc-async-compute run %command%'
    sidebar._render_radv_async({**radv, 'state': 'active'}, {})
    assert sidebar.radv_launch_row.isHidden()
    sidebar._render_radv_async({**radv, 'enabled': False, 'state': 'switched-off'}, {})
    assert not sidebar.radv_launch_row.isHidden()


def test_the_version_picker_hides_behind_more_and_comes_back():
    sidebar = PreparationSidebar(standalone=True)
    releases = [{'tag': 'directmesh-v1.4', 'version': '1.4', 'default': True},
                {'tag': 'directmesh-v1.3', 'version': '1.3'}]
    sidebar._render_directmesh(dict(supported=True, platform='host', installed=True, installed_version='1.4',
                                    installed_tag='directmesh-v1.4', selected_tag='directmesh-v1.4',
                                    releases=releases, launch_option='x %command%'))
    row, button = sidebar.directmesh_version_row, sidebar.directmesh_version_button
    assert row.isHidden() and button.text() == 'Choose version'
    button.click()
    assert not row.isHidden() and button.text() == 'Hide versions'
    combo = sidebar.directmesh_version_combo
    combo.setCurrentIndex(combo.findData('directmesh-v1.3'))
    assert _main(sidebar)[0] == 'Switch to 1.3'
    button.click()
    # Hidden again, the pick goes back so the main button never names a hidden version.
    assert row.isHidden() and _main(sidebar)[0] == 'Reinstall'
