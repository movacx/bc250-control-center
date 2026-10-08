"""Additional settings > Upscaling: one page card per upscaler, with its games."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QPushButton

from frontends.desktop.components.dashboard_widgets import (
    PreparationSidebar,
    game_matrix_rows,
)
from frontends.desktop.components.toggle_switch import ToggleSwitch

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


def test_both_upscalers_are_page_cards_on_their_own_tab():
    sidebar = _sidebar()
    upscaling = sidebar.stack.widget(sidebar.tab_index("upscaling"))
    assert sidebar.tab_buttons[sidebar.tab_index("upscaling")].text() == "Upscaling"
    assert upscaling.isAncestorOf(sidebar.fsr4_section)
    assert upscaling.isAncestorOf(sidebar.helixsr_section)
    assert "Upscaling" not in dict(sidebar.compatibility_groups)
    # The cards only own the actions; their buttons live in the sections.
    assert sidebar.upscaling_sources.isHidden()
    assert sidebar.helixsr_section.isAncestorOf(sidebar.helixsr_install_button)
    assert sidebar.fsr4_section.isAncestorOf(sidebar.fsr4_install_button)


def _footer(section):
    grid = section.footer
    return [grid.itemAt(i).widget() for i in range(grid.count())]


def test_not_installed_offers_the_install_as_the_blue_button():
    sidebar = _sidebar()
    sidebar.set_state(_state(_helixsr()))
    section = sidebar.helixsr_section
    assert section.rows["state"].value.text() == "Not installed"
    assert sidebar.helixsr_install_button.text() == "Install HelixSR"
    assert sidebar.helixsr_install_button.objectName() == "PrimaryAction"
    assert _footer(section)[-1] is sidebar.helixsr_install_button
    for button in (sidebar.helixsr_network_button, sidebar.helixsr_scan_button,
                   sidebar.helixsr_remove_button):
        assert button.isHidden()


def test_without_proton_the_install_waits_for_it():
    sidebar = _sidebar()
    sidebar.set_state(_state(_helixsr(wine_available=False)))
    reading = sidebar.helixsr_section.rows["state"]
    assert reading.value.text() == "Proton required"
    assert reading.property("tone") == "warning"
    assert not sidebar.helixsr_install_button.isEnabled()
    assert not sidebar.helixsr_section.notice.isHidden()


def test_missing_network_files_make_the_build_the_next_step():
    sidebar = _sidebar()
    sidebar.set_state(_state(_helixsr(installed=True, current=True, state="needs-network",
                                      version="1.2.0")))
    section = sidebar.helixsr_section
    assert section.rows["network"].value.text() == "Not built yet"
    assert sidebar.helixsr_network_button.objectName() == "PrimaryAction"
    assert sidebar.helixsr_install_button.objectName() == ""
    assert _footer(section)[-1] is sidebar.helixsr_network_button


def test_ready_shows_the_readings_and_puts_the_search_last():
    sidebar = _sidebar()
    sidebar.set_state(_state(_ready()))
    section = sidebar.helixsr_section
    values = {key: row.value.text() for key, row in section.rows.items()}
    assert values == {"state": "Ready", "version": "1.2.0", "network": "Built on this PC"}
    assert section.rows["state"].property("tone") == "good"
    assert section.notice.isHidden()
    footer = _footer(section)
    assert footer[-1] is sidebar.helixsr_scan_button
    assert sidebar.helixsr_scan_button.objectName() == "PrimaryAction"
    assert sidebar.helixsr_install_button.text() == "Reinstall HelixSR"
    assert sidebar.helixsr_remove_button in footer


def test_each_helixsr_game_has_a_switch_that_asks_before_it_moves():
    sidebar = _sidebar()
    games = [
        {"appid": "1", "kind": "game", "name": "Active", "state": "installed", "files": ["/a.dll"]},
        {"appid": "2", "kind": "optiscaler", "name": "Opti", "state": "available", "files": []},
    ]
    sidebar.set_state(_state(_ready(games)))
    controls = sidebar.helixsr_section.game_controls
    assert set(controls) == {"1", "2"}
    assert all(isinstance(control, ToggleSwitch) for control in controls.values())
    assert controls["1"].isChecked() and not controls["2"].isChecked()
    requested = []
    sidebar.dependency_action_requested.connect(requested.append)
    controls["1"].click()
    controls["2"].click()
    assert [item["action"] for item in requested] == [
        "helixsr_game_remove:1",
        "helixsr_opti_install:2",
    ]
    # Nothing changed yet: the switches wait for the game's real state.
    assert controls["1"].isChecked() and not controls["2"].isChecked()


def test_a_game_outside_steam_is_marked_and_can_leave_the_list():
    sidebar = _sidebar()
    games = [{"appid": "folder-abc", "kind": "game", "name": "Loose", "state": "available",
              "files": ["/g/a.dll"], "folder": "/g"}]
    sidebar.set_state(_state(_ready(games)))
    section = sidebar.helixsr_section
    row = section.games.readings["folder-abc"]
    assert row.detail.text() == "Outside Steam"
    host = section.game_controls["folder-abc"]
    requested = []
    sidebar.dependency_action_requested.connect(requested.append)
    forget = [b for b in host.findChildren(QPushButton) if b.text() == "Remove from list"]
    forget[0].click()
    host.switch.click()
    assert [item["action"] for item in requested] == [
        "helixsr_forget_folder:folder-abc",
        "helixsr_game_install:folder-abc",
    ]


def test_the_folder_button_asks_the_page_for_a_folder():
    sidebar = _sidebar()
    sidebar.set_state(_state(_ready()))
    assert not sidebar.helixsr_folder_panel.isHidden()
    requested = []
    sidebar.dependency_action_requested.connect(requested.append)
    sidebar.helixsr_folder_button.click()
    assert [item["action"] for item in requested] == ["helixsr_add_folder"]
    sidebar.set_state(_state(_helixsr()))
    assert sidebar.helixsr_folder_panel.isHidden()


def test_an_empty_library_says_how_to_find_games():
    sidebar = _sidebar()
    sidebar.set_state(_state(_ready()))
    empty = sidebar.helixsr_section.games_empty
    assert not empty.isHidden()
    assert empty.text() == "No games yet. Find FSR 3.1 games looks through your Steam library."


def test_a_rebuilt_list_leaves_nothing_of_the_old_one_on_screen():
    sidebar = _sidebar()
    sidebar.set_state(_state(_ready([
        {"appid": "1", "kind": "game", "name": "One", "state": "available", "files": ["/a.dll"]},
    ])))
    old = sidebar.helixsr_section.games
    sidebar.set_state(_state(_ready([
        {"appid": "1", "kind": "game", "name": "One", "state": "installed", "files": ["/a.dll"]},
    ])))
    assert old.isHidden()
    assert sidebar.helixsr_section.game_controls["1"].isChecked()


def _fsr4_ready(**overrides) -> dict:
    state = {
        "installer_available": True, "installed": True, "current": True, "state": "ready",
        "version": "1.0.7", "steam_launch_option": 'WINEDLLOVERRIDES="dxgi=n,b" %command%',
        "games": [{"appid": "10", "name": "Puzzle", "state": "needs-launch-option",
                   "steam": True, "adapter": "dxgi.dll"}],
    }
    state.update(overrides)
    return state


def test_fsr4_shows_the_launch_option_and_opens_the_client_as_the_next_step():
    sidebar = _sidebar()
    sidebar.set_state(_state(_helixsr(), _fsr4_ready()))
    section = sidebar.fsr4_section
    assert not sidebar.fsr4_launch_panel.isHidden()
    assert sidebar.fsr4_launch_field.text() == 'WINEDLLOVERRIDES="dxgi=n,b" %command%'
    assert sidebar.fsr4_copy_button.text() == "Copy"
    assert section.rows["version"].value.text() == "1.0.7"
    assert _footer(section)[-1] is sidebar.fsr4_launch_button
    assert sidebar.fsr4_launch_button.objectName() == "PrimaryAction"


def test_an_fsr4_game_missing_the_option_offers_the_fix():
    sidebar = _sidebar()
    sidebar.set_state(_state(_helixsr(), _fsr4_ready()))
    button = sidebar.fsr4_section.game_controls["10"]
    requested = []
    sidebar.dependency_action_requested.connect(requested.append)
    button.click()
    assert [item["action"] for item in requested] == ["fsr4_steam_option:10"]


def test_fsr4_not_installed_hides_the_launch_option_and_offers_the_install():
    sidebar = _sidebar()
    sidebar.set_state(_state(_helixsr(), {"installer_available": True, "state": "not-installed"}))
    assert sidebar.fsr4_launch_panel.isHidden()
    assert _footer(sidebar.fsr4_section)[-1] is sidebar.fsr4_install_button
    assert sidebar.fsr4_install_button.objectName() == "PrimaryAction"


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
    assert by_name["Racer"]["helixsr"][3] == (("Add HelixSR", "helixsr_game_install:7", True),)
    assert by_name["Racer"]["fsr4"] is None
    assert by_name["Shooter"]["helixsr"][:2] == ("Active via OptiScaler", "green")
    assert by_name["Shooter"]["helixsr"][3] == (("Remove HelixSR", "helixsr_opti_remove:8", True),)
    assert by_name["Shooter"]["fsr4"][:2] == ("Active", "green")
    assert by_name["Updated"]["helixsr"][:2] == ("Original file back", "orange")
    assert by_name["Puzzle"]["helixsr"] is None
    assert by_name["Puzzle"]["fsr4"][3] == (("Add FSR4 to Steam", "fsr4_steam_option:10", True),)


def test_optiscaler_only_games_are_added_through_optiscaler_and_wait_for_the_network():
    rows = game_matrix_rows(
        [{"appid": "5", "kind": "optiscaler", "name": "Only DLSS", "state": "available"}],
        [], helixsr_ready=False,
    )
    assert rows[0]["helixsr"][0] == "Via OptiScaler"
    assert rows[0]["helixsr"][3] == (("Add HelixSR", "helixsr_opti_install:5", False),)


