from types import SimpleNamespace

from PyQt6.QtWidgets import QApplication

from frontends.desktop.components.dashboard_widgets import PreparationSidebar
from bc250cc.infrastructure import dependencias_repository as repo_module

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
    assert sidebar.directmesh_launch_field.isReadOnly()
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
