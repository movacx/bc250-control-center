"""Additional settings > Upscaling: FSR4 and HelixSR panels and the game table."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QLabel

from frontends.desktop.components.dashboard_widgets import (
    PillLabel,
    PreparationSidebar,
    game_matrix_rows,
)

_APP: QApplication | None = None


def _sidebar() -> PreparationSidebar:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    temporary = TemporaryDirectory()
    settings = QSettings(str(Path(temporary.name) / "helixsr.ini"), QSettings.Format.IniFormat)
    sidebar = PreparationSidebar(settings=settings, standalone=True)
    sidebar._test_settings_directory = temporary
    return sidebar


def _state(helixsr: dict, fsr4: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        preparation_tools={
            "os_id": "bazzite",
            "os_label": "Bazzite",
            "os_family": "bazzite",
            "prepare_components": {},
            "helixsr": helixsr,
            "fsr4": fsr4 or {},
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


def _ready(games=(), **overrides) -> dict:
    return _helixsr(installed=True, current=True, network_ready=True, state="ready",
                    version="1.2.0", games=list(games), **overrides)


def test_fsr4_and_helixsr_live_on_their_own_tab_not_in_compatibility():
    sidebar = _sidebar()
    upscaling = sidebar.stack.widget(sidebar.tab_index("upscaling"))
    assert sidebar.tab_buttons[sidebar.tab_index("upscaling")].text() == "Upscaling"
    assert sidebar.fsr4_card.parent() is upscaling
    assert sidebar.helixsr_card.parent() is upscaling
    assert "Upscaling" not in dict(sidebar.compatibility_groups)


def test_the_panels_carry_no_badges():
    sidebar = _sidebar()
    sidebar.set_state(_state(_ready(), {"installer_available": True, "installed": True,
                                        "current": True, "state": "ready", "version": "1.0.7"}))
    for card in (sidebar.fsr4_card, sidebar.helixsr_card):
        assert card.status.isHidden() and card.scope.isHidden()
        assert not [pill for pill in card.findChildren(PillLabel) if not pill.isHidden()]
    assert sidebar.helixsr_card.status.text() == "Ready"
    assert sidebar.fsr4_card.status.text() == "Ready"


def test_not_installed_offers_only_the_install():
    sidebar = _sidebar()
    sidebar.set_state(_state(_helixsr()))
    assert sidebar.helixsr_card.status.text() == "Not installed"
    assert sidebar.helixsr_sheet.values["state"].text() == "Not installed"
    assert sidebar.helixsr_install_button.text() == "Install HelixSR"
    assert sidebar.helixsr_install_button.property("accented") is True
    for button in (sidebar.helixsr_network_button, sidebar.helixsr_scan_button, sidebar.helixsr_remove_button):
        assert button.isHidden()


def test_without_proton_the_install_waits_for_it():
    sidebar = _sidebar()
    sidebar.set_state(_state(_helixsr(wine_available=False)))
    assert sidebar.helixsr_card.status.text() == "Proton required"
    assert sidebar.helixsr_sheet.values["state"].property("tone") == "orange"
    assert not sidebar.helixsr_install_button.isEnabled()


def test_missing_network_files_put_the_build_first():
    sidebar = _sidebar()
    sidebar.set_state(_state(_helixsr(installed=True, current=True, state="needs-network", version="1.2.0")))
    assert sidebar.helixsr_sheet.values["network"].text() == "Not built yet"
    assert sidebar.helixsr_network_button.property("accented") is True
    assert sidebar.helixsr_install_button.property("quietAction") is True
    flow = sidebar.helixsr_card.actions
    shown = [flow.itemAt(i).widget() for i in range(flow.count()) if not flow.itemAt(i).widget().isHidden()]
    assert shown[0] is sidebar.helixsr_network_button


def test_ready_fills_the_datasheet_and_puts_the_search_first():
    sidebar = _sidebar()
    games = [
        {"appid": "1", "kind": "game", "name": "Active", "state": "installed", "files": ["/a.dll"]},
        {"appid": "3", "kind": "game", "name": "Found", "state": "available", "files": ["/c.dll"]},
    ]
    sidebar.set_state(_state(_ready(games)))
    values = {key: label.text() for key, label in sidebar.helixsr_sheet.values.items()}
    assert values == {
        "release": "1.2.0",
        "network": "Built on this PC",
        "games": "1 active · 1 available",
        "state": "Ready",
    }
    assert sidebar.helixsr_scan_button.property("accented") is True
    assert sidebar.helixsr_remove_button.property("quietAction") is True


def test_one_table_row_per_game_with_both_tools():
    rows = game_matrix_rows(
        [
            {"appid": "7", "kind": "game", "name": "Racer", "state": "available"},
            {"appid": "7", "kind": "optiscaler", "name": "Racer", "state": "available"},
            {"appid": "8", "kind": "optiscaler", "name": "Shooter", "state": "installed"},
            {"appid": "9", "kind": "game", "name": "Updated", "state": "restored"},
        ],
        [
            {"appid": "8", "name": "Shooter", "state": "ready", "steam": True},
            {"appid": "10", "name": "Puzzle", "state": "needs-launch-option", "steam": True,
             "adapter": "dxgi.dll"},
        ],
        helixsr_ready=True,
    )
    by_name = {row["name"]: row for row in rows}
    assert [row["name"] for row in rows][:2] == ["Puzzle", "Updated"], "attention first"
    assert by_name["Racer"]["helixsr"][3] == (("Add", "helixsr_game_install:7", True),)
    assert by_name["Racer"]["fsr4"] is None
    assert by_name["Shooter"]["helixsr"][:2] == ("Active via OptiScaler", "green")
    assert by_name["Shooter"]["helixsr"][3] == (("Remove", "helixsr_opti_remove:8", True),)
    assert by_name["Shooter"]["fsr4"][:2] == ("Active", "green")
    assert by_name["Updated"]["helixsr"][:2] == ("Original file back", "orange")
    assert by_name["Puzzle"]["helixsr"] is None
    assert by_name["Puzzle"]["fsr4"][3] == (("Add to Steam", "fsr4_steam_option:10", True),)


def test_optiscaler_only_games_are_added_through_optiscaler_and_wait_for_the_network():
    rows = game_matrix_rows(
        [{"appid": "5", "kind": "optiscaler", "name": "Only DLSS", "state": "available"}],
        [], helixsr_ready=False,
    )
    assert rows[0]["helixsr"][3] == (("Add via OptiScaler", "helixsr_opti_install:5", False),)


def test_table_actions_reach_the_page():
    sidebar = _sidebar()
    games = [
        {"appid": "1", "kind": "game", "name": "Active", "state": "installed", "files": ["/a.dll"]},
        {"appid": "2", "kind": "optiscaler", "name": "Opti", "state": "available", "files": []},
    ]
    sidebar.set_state(_state(_ready(games)))
    assert set(sidebar.game_matrix.rows) == {"1", "2"}
    requested = []
    sidebar.dependency_action_requested.connect(requested.append)
    for appid in ("1", "2"):
        sidebar.game_matrix.rows[appid][0].click()
    assert [item["action"] for item in requested] == [
        "helixsr_game_remove:1",
        "helixsr_opti_install:2",
    ]


def test_an_empty_table_says_how_to_find_games():
    sidebar = _sidebar()
    sidebar.set_state(_state(_ready()))
    texts = [label.text() for label in sidebar.game_matrix.findChildren(QLabel)]
    assert "No games yet. Find FSR 3.1 games looks through your Steam library." in texts


def test_a_rebuilt_table_leaves_nothing_of_the_old_one_on_screen():
    sidebar = _sidebar()
    sidebar.set_state(_state(_ready()))
    old = sidebar.game_matrix.findChildren(QLabel)
    sidebar.set_state(_state(_ready([
        {"appid": "1", "kind": "game", "name": "Active", "state": "installed", "files": ["/a.dll"]},
    ])))
    assert all(label.isHidden() for label in old)
