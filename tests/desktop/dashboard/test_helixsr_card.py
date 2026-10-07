"""Additional settings > Compatibility > Upscaling: the HelixSR row."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QPushButton

from frontends.desktop.components.dashboard_widgets import PreparationSidebar

_APP: QApplication | None = None


def _sidebar() -> PreparationSidebar:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    temporary = TemporaryDirectory()
    settings = QSettings(str(Path(temporary.name) / "helixsr.ini"), QSettings.Format.IniFormat)
    sidebar = PreparationSidebar(settings=settings, standalone=True)
    sidebar._test_settings_directory = temporary
    return sidebar


def _state(helixsr: dict) -> SimpleNamespace:
    return SimpleNamespace(
        preparation_tools={
            "os_id": "bazzite",
            "os_label": "Bazzite",
            "os_family": "bazzite",
            "prepare_components": {},
            "helixsr": helixsr,
        },
        dependencies_ready=False,
        governor_tool_ready=False,
        cpu_tools_ready=False,
        core_unlock_ready=False,
        umr_ready=False,
        cu_manager_ready=False,
        nct_ready=False,
    )


def _helixsr(**overrides) -> dict:
    state = {
        "provider": "helixsr",
        "installer_available": True,
        "installed": False,
        "current": False,
        "network_ready": False,
        "state": "not-installed",
        "wine_available": True,
        "games": [],
        "installed_games": 0,
    }
    state.update(overrides)
    return state


def test_helixsr_sits_in_the_upscaling_group_next_to_fsr4():
    sidebar = _sidebar()
    groups = dict(sidebar.compatibility_groups)
    assert sidebar.helixsr_card in groups["Upscaling"]
    assert sidebar.fsr4_card in groups["Upscaling"]


def test_not_installed_offers_only_the_install():
    sidebar = _sidebar()
    sidebar.set_state(_state(_helixsr()))
    assert sidebar.helixsr_card.status.text() == "Not installed"
    assert sidebar.helixsr_card.scope.text() == "All distributions · per game · no root"
    assert not sidebar.helixsr_install_button.isHidden()
    assert sidebar.helixsr_install_button.isEnabled()
    assert sidebar.helixsr_install_button.text() == "Install HelixSR"
    for button in (sidebar.helixsr_network_button, sidebar.helixsr_scan_button, sidebar.helixsr_remove_button):
        assert button.isHidden()
    assert not sidebar.helixsr_upstream_button.isHidden()
    assert sidebar.helixsr_games.isHidden()


def test_without_proton_the_install_waits_for_it():
    sidebar = _sidebar()
    sidebar.set_state(_state(_helixsr(wine_available=False)))
    assert sidebar.helixsr_card.status.text() == "Proton required"
    assert not sidebar.helixsr_install_button.isEnabled()


def test_missing_network_files_offer_the_build():
    sidebar = _sidebar()
    sidebar.set_state(_state(_helixsr(installed=True, current=True, state="needs-network")))
    assert sidebar.helixsr_card.status.text() == "Network files missing"
    assert not sidebar.helixsr_network_button.isHidden()
    assert sidebar.helixsr_scan_button.isHidden()
    assert not sidebar.helixsr_remove_button.isHidden()


def test_ready_lists_each_game_with_its_own_action():
    sidebar = _sidebar()
    games = [
        {"appid": "1", "name": "Installed Game", "state": "installed", "files": ["/a.dll"]},
        {"appid": "2", "name": "Updated Game", "state": "restored", "files": ["/b.dll"]},
        {"appid": "3", "name": "New Game", "state": "available", "files": ["/c.dll"]},
    ]
    sidebar.set_state(_state(_helixsr(
        installed=True, current=True, network_ready=True, state="ready", games=games, installed_games=2,
    )))
    assert sidebar.helixsr_card.status.text() == "Ready"
    assert not sidebar.helixsr_scan_button.isHidden()
    assert sidebar.helixsr_install_button.text() == "Reinstall HelixSR"
    assert not sidebar.helixsr_games.isHidden()
    assert list(sidebar.helixsr_game_rows) == ["1", "2", "3"]

    requested = []
    sidebar.dependency_action_requested.connect(requested.append)
    for appid in ("1", "3"):
        button = sidebar.helixsr_game_rows[appid].findChild(QPushButton)
        button.click()
    assert [item["action"] for item in requested] == [
        "helixsr_game_remove:1",
        "helixsr_game_install:3",
    ]


def test_a_preview_of_another_distribution_never_runs_the_installer():
    sidebar = _sidebar()
    sidebar.set_state(_state(_helixsr()))
    index = next(
        position for position, (_label, identifier) in enumerate(sidebar.compatibility_filter_entries)
        if identifier not in {"detected", "all", "bazzite"}
    )
    sidebar.compatibility_filter.setCurrentIndex(index)
    assert not sidebar.helixsr_install_button.isEnabled()
    assert sidebar.helixsr_upstream_button.isEnabled()


def test_optiscaler_games_get_their_own_row_and_action():
    sidebar = _sidebar()
    games = [
        {"appid": "7", "kind": "game", "name": "Racer", "state": "available", "files": ["/r.dll"]},
        {"appid": "7", "kind": "optiscaler", "name": "Racer", "state": "available", "files": []},
        {"appid": "8", "kind": "optiscaler", "name": "Shooter", "state": "installed", "files": ["/OptiScaler.ini"]},
    ]
    sidebar.set_state(_state(_helixsr(
        installed=True, current=True, network_ready=True, state="ready", games=games, installed_games=1,
    )))
    assert list(sidebar.helixsr_game_rows) == ["7", "opti:7", "opti:8"]
    opti_button = sidebar.helixsr_game_rows["opti:7"].findChild(QPushButton)
    assert opti_button.text() == "Add"
    assert opti_button.toolTip() == "Use HelixSR in OptiScaler"

    requested = []
    sidebar.dependency_action_requested.connect(requested.append)
    for key in ("opti:7", "opti:8"):
        sidebar.helixsr_game_rows[key].findChild(QPushButton).click()
    assert [item["action"] for item in requested] == [
        "helixsr_opti_install:7",
        "helixsr_opti_remove:8",
    ]


def test_rows_carry_state_as_a_dot_and_one_line_not_a_badge():
    from PyQt6.QtWidgets import QLabel

    from frontends.desktop.components.dashboard_widgets import PillLabel, _StatusDot

    sidebar = _sidebar()
    games = [
        {"appid": "1", "kind": "game", "name": "Active", "state": "installed", "files": ["/a.dll"]},
        {"appid": "2", "kind": "game", "name": "Restored", "state": "restored", "files": ["/b.dll"]},
        {"appid": "3", "kind": "game", "name": "Found", "state": "available", "files": ["/c.dll"]},
    ]
    sidebar.set_state(_state(_helixsr(
        installed=True, current=True, network_ready=True, state="ready", version="1.2.0",
        games=games, installed_games=2,
    )))
    tones = {}
    for appid, row in sidebar.helixsr_game_rows.items():
        assert not row.findChildren(PillLabel)
        tones[appid] = row.findChild(_StatusDot).tone()
        assert row.toolTip()
    assert tones == {"1": "green", "2": "orange", "3": ""}
    facts = {key: label.text() for key, (_dot, label) in sidebar.helixsr_facts.items()}
    assert facts == {
        "release": "HelixSR 1.2.0",
        "network": "Built on this PC",
        "games": "1 active · 1 available",
    }
    assert not sidebar.helixsr_strip.isHidden()
    # The main action stands out; reinstall and remove are quiet text.
    assert sidebar.helixsr_scan_button.property("accented") is True
    assert sidebar.helixsr_install_button.property("quietAction") is True
    assert sidebar.helixsr_remove_button.property("quietAction") is True
    assert isinstance(sidebar.helixsr_games.findChild(QLabel), QLabel)


def test_before_installing_there_is_no_strip_of_dashes():
    sidebar = _sidebar()
    sidebar.set_state(_state(_helixsr()))
    assert sidebar.helixsr_strip.isHidden()
    assert sidebar.helixsr_install_button.property("accented") is True
    assert not sidebar.helixsr_install_button.property("quietAction")


def test_a_ready_install_without_games_says_how_to_find_them():
    from PyQt6.QtWidgets import QLabel

    sidebar = _sidebar()
    sidebar.set_state(_state(_helixsr(installed=True, current=True, network_ready=True, state="ready")))
    assert not sidebar.helixsr_games.isHidden()
    texts = [label.text() for label in sidebar.helixsr_games.findChildren(QLabel)]
    assert texts == ["No games yet. Find FSR 3.1 games looks through your Steam library."]
