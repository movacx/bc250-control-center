"""Additional settings > Upscaling: one page card per upscaler, with its games."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QLabel

from frontends.desktop.components.dashboard_widgets import (
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
    assert section.rows["prepare"].value.text() == "Not built yet"
    assert sidebar.helixsr_network_button.objectName() == "PrimaryAction"
    assert sidebar.helixsr_install_button.objectName() == ""
    assert _footer(section)[-1] is sidebar.helixsr_network_button


def test_ready_shows_the_readings_and_puts_the_search_last():
    sidebar = _sidebar()
    sidebar.set_state(_state(_ready()))
    section = sidebar.helixsr_section
    values = {key: row.value.text() for key, row in section.rows.items()}
    assert values == {"state": "Ready", "prepare": "Built on this PC", "games": "0 / 0"}
    assert section.version.text() == "1.2.0"
    assert section.rows["state"].property("tone") == "good"
    assert section.notice.isHidden()
    footer = _footer(section)
    assert footer[-1] is sidebar.helixsr_scan_button
    assert sidebar.helixsr_scan_button.objectName() == "PrimaryAction"
    assert sidebar.helixsr_install_button.text() == "Reinstall"
    assert sidebar.helixsr_remove_button in footer


def test_each_helixsr_game_has_its_add_or_remove_button():
    sidebar = _sidebar()
    games = [
        {"appid": "1", "kind": "game", "name": "Active", "state": "installed", "files": ["/a.dll"]},
        {"appid": "2", "kind": "optiscaler", "name": "Opti", "state": "available", "files": []},
    ]
    sidebar.set_state(_state(_ready(games)))
    controls = sidebar.upscaling_games.controls
    assert [b.text() for b in controls["1"]] == ["Remove HelixSR"]
    assert [b.text() for b in controls["2"]] == ["Add HelixSR"]
    requested = []
    sidebar.dependency_action_requested.connect(requested.append)
    controls["1"][0].click()
    controls["2"][0].click()
    assert [item["action"] for item in requested] == [
        "helixsr_game_remove:1",
        "helixsr_opti_install:2",
    ]


def test_a_game_outside_steam_is_marked_and_can_leave_the_list():
    sidebar = _sidebar()
    games = [{"appid": "folder-abc", "kind": "game", "name": "Loose", "state": "available",
              "files": ["/g/a.dll"], "folder": "/g"}]
    sidebar.set_state(_state(_ready(games)))
    table = sidebar.upscaling_games
    assert "Outside Steam" in [label.text() for label in table.table.findChildren(QLabel)]
    requested = []
    sidebar.dependency_action_requested.connect(requested.append)
    for button in table.controls["folder-abc"]:
        button.click()
    assert [item["action"] for item in requested] == [
        "helixsr_game_install:folder-abc",
        "helixsr_forget_folder:folder-abc",
    ]


def test_the_folder_button_asks_the_page_for_a_folder():
    sidebar = _sidebar()
    sidebar.set_state(_state(_ready()))
    assert not sidebar.helixsr_folder_button.isHidden()
    requested = []
    sidebar.dependency_action_requested.connect(requested.append)
    sidebar.helixsr_folder_button.click()
    assert [item["action"] for item in requested] == ["helixsr_add_folder"]
    sidebar.set_state(_state(_helixsr()))
    assert sidebar.helixsr_folder_button.isHidden()


def test_an_empty_library_says_how_to_find_games():
    sidebar = _sidebar()
    sidebar.set_state(_state(_ready()))
    empty = sidebar.upscaling_games.empty
    assert not empty.isHidden()
    assert empty.text() == "No games yet. Find FSR 3.1 games looks through your Steam library."


def test_a_rebuilt_list_leaves_nothing_of_the_old_one_on_screen():
    sidebar = _sidebar()
    sidebar.set_state(_state(_ready([
        {"appid": "1", "kind": "game", "name": "One", "state": "available", "files": ["/a.dll"]},
    ])))
    old = sidebar.upscaling_games.controls["1"][0]
    sidebar.set_state(_state(_ready([
        {"appid": "1", "kind": "game", "name": "One", "state": "installed", "files": ["/a.dll"]},
    ])))
    assert old.parentWidget().isHidden()
    assert sidebar.upscaling_games.controls["1"][0].text() == "Remove HelixSR"


def _fsr4_ready(**overrides) -> dict:
    state = {
        "installer_available": True, "installed": True, "current": True, "state": "ready",
        "version": "1.0.7", "steam_launch_option": 'WINEDLLOVERRIDES="dxgi=n,b" %command%',
        "games": [{"appid": "10", "name": "Puzzle", "state": "needs-launch-option",
                   "steam": True, "adapter": "dxgi.dll"}],
    }
    state.update(overrides)
    return state


def test_fsr4_spells_out_the_launch_option_where_a_game_misses_it():
    sidebar = _sidebar()
    sidebar.set_state(_state(_helixsr(), _fsr4_ready()))
    section = sidebar.fsr4_section
    assert not sidebar.fsr4_launch_panel.isHidden()
    assert sidebar.fsr4_launch_field.text() == 'WINEDLLOVERRIDES="dxgi=n,b" %command%'
    assert sidebar.fsr4_launch_field.cursorPosition() == 0, "the start of the option in view"
    assert sidebar.fsr4_copy_button.text() == "Copy"
    assert section.version.text() == "1.0.7"
    assert section.rows["prepare"].value.text() == "Missing in some games"
    assert section.rows["prepare"].property("tone") == "warning"
    assert _footer(section)[-1] is sidebar.fsr4_steam_all_button
    assert sidebar.fsr4_steam_all_button.objectName() == "PrimaryAction"
    assert sidebar.fsr4_launch_button in _footer(section)


def test_fsr4_with_every_game_loading_opens_the_client_as_the_next_step():
    sidebar = _sidebar()
    games = [{"appid": "10", "name": "Puzzle", "state": "ready", "steam": True, "adapter": "dxgi.dll"},
             {"appid": "11", "name": "Racer", "state": "not-installed", "steam": True}]
    sidebar.set_state(_state(_helixsr(), _fsr4_ready(games=games)))
    section = sidebar.fsr4_section
    assert not sidebar.fsr4_launch_panel.isHidden(), "always in view, at the head of the games"
    assert sidebar.upscaling_games.isAncestorOf(sidebar.fsr4_launch_panel)
    values = {key: row.value.text() for key, row in section.rows.items()}
    assert values == {"state": "Ready", "prepare": "In every game", "games": "1 / 2"}
    assert _footer(section)[-1] is sidebar.fsr4_launch_button
    assert sidebar.fsr4_launch_button.objectName() == "PrimaryAction"
    assert sidebar.fsr4_steam_all_button.isHidden()


def test_both_cards_read_the_same_way():
    sidebar = _sidebar()
    sidebar.set_state(_state(_ready(), _fsr4_ready()))
    fsr4, helixsr = sidebar.fsr4_section, sidebar.helixsr_section
    assert list(fsr4.rows) == list(helixsr.rows) == ["state", "prepare", "games"]
    labels = [[row.label.text() for row in section.rows.values()] for section in (fsr4, helixsr)]
    assert labels[0][0] == labels[1][0] == "State"
    assert labels[0][2] == labels[1][2] == "Active games"
    for section in (fsr4, helixsr):
        footer = _footer(section)
        assert footer[0].text() == "Reinstall" and footer[1].text() == "Remove"
        assert footer[-1].objectName() == "PrimaryAction"


def test_a_narrow_card_moves_the_next_step_to_its_own_row_instead_of_cutting_labels():
    sidebar = _sidebar()
    sidebar.set_state(_state(_helixsr(), _fsr4_ready()))
    sidebar.select_tab(sidebar.tab_index("upscaling"))
    sidebar.resize(460, 900)
    sidebar.show()
    QApplication.processEvents()
    section = sidebar.fsr4_section
    assert section._footer_wrapped
    index = section.footer.indexOf(sidebar.fsr4_steam_all_button)
    assert section.footer.getItemPosition(index)[0] == 1
    for button in _footer(section):
        if not button.isHidden():
            assert button.minimumWidth() >= button.fontMetrics().horizontalAdvance(button.text())


def test_an_fsr4_game_missing_the_option_offers_the_fix():
    sidebar = _sidebar()
    sidebar.set_state(_state(_helixsr(), _fsr4_ready()))
    button = sidebar.upscaling_games.controls["10"][0]
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
    # OptiScaler loads its own FidelityFX DLLs: where it is, HelixSR goes through it.
    assert by_name["Racer"]["helixsr"][3] == (("Add HelixSR", "helixsr_opti_install:7", True),)
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


def test_a_game_with_an_earlier_release_offers_the_update_next_to_removal():
    rows = game_matrix_rows(
        [
            {"appid": "1", "kind": "game", "name": "Old", "state": "installed", "outdated": True},
            {"appid": "2", "kind": "optiscaler", "name": "Old via Opti", "state": "installed", "outdated": True},
            {"appid": "3", "kind": "game", "name": "Current", "state": "installed", "outdated": False},
            {"appid": "4", "kind": "game", "name": "Restored", "state": "restored", "outdated": True},
        ],
        [], helixsr_ready=True,
    )
    by_name = {row["name"]: row for row in rows}
    assert by_name["Old"]["helixsr"][:2] == ("Update available", "orange")
    assert by_name["Old"]["helixsr"][3] == (
        ("Update HelixSR", "helixsr_game_update:1", True),
        ("Remove HelixSR", "helixsr_game_remove:1", True),
    )
    assert by_name["Old via Opti"]["helixsr"][3][0] == ("Update HelixSR", "helixsr_game_update:2", True)
    assert by_name["Current"]["helixsr"][:2] == ("Active", "green")
    assert len(by_name["Current"]["helixsr"][3]) == 1
    assert by_name["Restored"]["helixsr"][3] == (("Remove HelixSR", "helixsr_game_remove:4", True),)




def test_the_table_follows_the_cards_and_shows_only_what_is_set_up():
    sidebar = _sidebar()
    games = [{"appid": "10", "kind": "game", "name": "Puzzle", "state": "available", "files": ["/a.dll"]}]
    sidebar.set_state(_state(_ready(games), _fsr4_ready()))
    table = sidebar.upscaling_games
    heads = [label.source_text for label in table.table.findChildren(QLabel) if label.property("gameColumn")]
    assert heads == ["Game", "FSR4 INT8", "HelixSR"], "the cards' order"
    assert [b.text() for b in table.controls["10"]] == ["Add FSR4 to Steam", "Add HelixSR"]

    sidebar.set_state(_state(_helixsr(), _fsr4_ready()))
    QApplication.processEvents()  # the old header goes with deleteLater
    heads = [label.source_text for label in table.table.findChildren(QLabel)
             if label.property("gameColumn") and not label.isHidden()]
    assert heads == ["Game", "FSR4 INT8"], "no column for an upscaler that is not set up"
    assert sidebar.helixsr_settings.isHidden(), "no settings before HelixSR is installed"

    sidebar.set_state(_state(_helixsr(), {"installer_available": True, "state": "not-installed"}))
    assert table.isHidden(), "nothing set up, nothing to list"


def test_a_long_library_can_be_searched():
    sidebar = _sidebar()
    games = [
        {"appid": str(i), "kind": "game", "name": f"Game {i}", "state": "available", "files": ["/a.dll"]}
        for i in range(10)
    ]
    sidebar.set_state(_state(_ready(games)))
    table = sidebar.upscaling_games
    assert not table.search.isHidden()
    table.search.setText("Game 7")
    shown = [key for key, buttons in table.controls.items() if not buttons[0].parentWidget().isHidden()]
    assert shown == ["7"]
    table.search.setText("nothing like it")
    assert table.empty.text() == "No game matches the search."


def test_an_update_sits_beside_removal_with_its_own_label():
    sidebar = _sidebar()
    games = [
        {"appid": "1", "kind": "game", "name": "Old", "state": "installed", "outdated": True, "files": []},
        {"appid": "2", "kind": "game", "name": "Bare", "state": "installed", "network_missing": True,
         "files": []},
    ]
    sidebar.set_state(_state(_ready(games)))
    controls = sidebar.upscaling_games.controls
    for key in ("1", "2"):
        assert [b.text() for b in controls[key]] == ["Update HelixSR", "Remove HelixSR"]
    requested = []
    sidebar.dependency_action_requested.connect(requested.append)
    controls["2"][0].click()
    assert requested[-1]["action"] == "helixsr_game_update:2"


def test_missing_games_and_network_files_are_named():
    rows = game_matrix_rows(
        [
            {"appid": "1", "kind": "game", "name": "Gone", "state": "missing"},
            {"appid": "2", "kind": "optiscaler", "name": "Gone Opti", "state": "missing"},
            {"appid": "3", "kind": "game", "name": "Bare", "state": "installed", "network_missing": True,
             "outdated": True},
        ],
        [], helixsr_ready=True,
    )
    by_name = {row["name"]: row for row in rows}
    assert by_name["Gone"]["helixsr"][:2] == ("Game not found", "orange")
    assert by_name["Gone"]["helixsr"][3] == (("Remove HelixSR", "helixsr_game_remove:1", True),)
    assert by_name["Gone Opti"]["helixsr"][3] == (("Remove HelixSR", "helixsr_opti_remove:2", True),)
    assert by_name["Bare"]["helixsr"][:2] == ("Network files missing", "orange"), "before the update"
    assert by_name["Bare"]["helixsr"][3][0] == ("Update HelixSR", "helixsr_game_update:3", True)


def _settings(**overrides) -> dict:
    from bc250cc.infrastructure.helixsr import helixsr_defaults

    return {**helixsr_defaults(), **overrides}


def test_the_settings_form_shows_saves_and_restores():
    from bc250cc.infrastructure.helixsr import helixsr_defaults

    sidebar = _sidebar()
    form = sidebar.helixsr_settings
    sidebar.set_state(_state(_ready(settings=_settings(**{"Sharpening.Mode": "override",
                                                            "Sharpening.Sharpness": 0.5}),
                                    settings_defaults=helixsr_defaults())))
    assert form.values() == _settings(**{"Sharpening.Mode": "override", "Sharpening.Sharpness": 0.5})
    assert not form.save_button.isEnabled(), "nothing to save yet"
    assert form.defaults_button.isEnabled()
    assert form.controls["Sharpening.Sharpness"].isEnabled()

    form.controls["Compatibility.WaveSize"].setCurrentIndex(form.controls["Compatibility.WaveSize"].findData("32"))
    form.controls["ModelE.InvertJitter"].setChecked(True)
    assert form.save_button.isEnabled() and not form.hint.isHidden()
    requested = []
    sidebar.dependency_action_requested.connect(requested.append)
    form.save_button.click()
    assert requested[-1]["action"] == "helixsr_settings"
    assert requested[-1]["helixsr_settings"]["Compatibility.WaveSize"] == "32"
    assert requested[-1]["helixsr_settings"]["ModelE.InvertJitter"] is True

    form.defaults_button.click()
    assert form.values() == helixsr_defaults()
    assert not form.controls["Sharpening.Sharpness"].isEnabled(), "Off does not sharpen"


def test_saved_settings_can_reach_the_games_again_without_a_change():
    """A game open at the save, or one an update gave its own helixsr.ini back."""
    from bc250cc.infrastructure.helixsr import helixsr_defaults

    sidebar = _sidebar()
    form = sidebar.helixsr_settings
    saved = _settings(**{"Sharpening.Mode": "game"})
    sidebar.set_state(_state(_ready(settings=saved, settings_defaults=helixsr_defaults())))
    assert not form.reapply_button.isEnabled(), "no game has HelixSR yet"

    games = [{"appid": "1", "name": "Racer", "state": "installed", "kind": "game", "files": ["/g/a.dll"]},
             {"appid": "2", "name": "Shooter", "state": "available", "kind": "game", "files": ["/g/b.dll"]}]
    sidebar.set_state(_state(_ready(games, settings=saved, settings_defaults=helixsr_defaults())))
    assert form.reapply_button.isEnabled() and not form.save_button.isEnabled()
    requested = []
    sidebar.dependency_action_requested.connect(requested.append)
    form.reapply_button.click()
    assert requested[-1]["action"] == "helixsr_settings"
    assert requested[-1]["helixsr_settings"] == saved

    form.controls["Log.Enabled"].setChecked(False)
    assert not form.reapply_button.isEnabled(), "unsaved changes go through Save"


def test_a_form_being_edited_is_not_overwritten_by_a_refresh():
    from bc250cc.infrastructure.helixsr import helixsr_defaults

    sidebar = _sidebar()
    form = sidebar.helixsr_settings
    state = _state(_ready(settings=helixsr_defaults(), settings_defaults=helixsr_defaults()))
    sidebar.set_state(state)
    form.controls["Log.Enabled"].setChecked(False)
    sidebar.set_state(_state(_ready(settings=_settings(**{"ModelE.Network": "main"}),
                                    settings_defaults=helixsr_defaults())))
    assert form.values()["Log.Enabled"] is False
    assert form.values()["ModelE.Network"] == "auto", "the user's form stays as they left it"
    assert form.save_button.isEnabled()


def test_an_optiscaler_folder_added_by_hand_is_marked_and_can_leave_the_list():
    sidebar = _sidebar()
    games = [{"appid": "optifolder-abc", "kind": "optiscaler", "name": "Hand Racer", "state": "available",
              "files": [], "folder": "/games/Hand Racer/Bin"}]
    sidebar.set_state(_state(_ready(games)))
    assert not sidebar.helixsr_opti_folder_button.isHidden()
    controls = sidebar.upscaling_games.controls["optifolder-abc"]
    assert [b.text() for b in controls] == ["Add HelixSR", "Remove from list"]
    requested = []
    sidebar.dependency_action_requested.connect(requested.append)
    controls[0].click()
    controls[1].click()
    sidebar.helixsr_opti_folder_button.click()
    assert [item["action"] for item in requested] == [
        "helixsr_opti_install:optifolder-abc",
        "helixsr_forget_folder:optifolder-abc",
        "helixsr_add_opti_folder",
    ]
    rows = game_matrix_rows(games, [], helixsr_ready=True)
    assert rows[0]["folder_detail"] == "OptiScaler added by hand"


def test_saving_says_so_at_once_without_waiting_for_a_refresh():
    from bc250cc.infrastructure import helixsr

    sidebar = _sidebar()
    form = sidebar.helixsr_settings
    defaults = helixsr.helixsr_defaults()
    sidebar.set_state(_state(_ready(settings=defaults, settings_defaults=defaults)))
    form.controls["Compatibility.WaveSize"].setCurrentIndex(form.controls["Compatibility.WaveSize"].findData("64"))
    requested = []
    sidebar.dependency_action_requested.connect(requested.append)
    form.save_button.click()
    assert requested[-1]["helixsr_settings"]["Compatibility.WaveSize"] == "64"
    assert form.hint.text() == "Saved"
    assert not form.save_button.isEnabled(), "nothing left to save"


def test_the_motion_settings_follow_the_sharpening_and_keep_their_order():
    from bc250cc.infrastructure import helixsr

    sidebar = _sidebar()
    form = sidebar.helixsr_settings
    defaults = helixsr.helixsr_defaults()
    sidebar.set_state(_state(_ready(settings=defaults, settings_defaults=defaults)))
    motion = [form.controls[name] for name in
              ("Sharpening.MotionThreshold", "Sharpening.MotionLimit", "Sharpening.MotionReduction")]
    assert not any(control.isEnabled() for control in motion), "sharpening is off"
    mode = form.controls["Sharpening.Mode"]
    mode.setCurrentIndex(mode.findData("override"))
    assert all(control.isEnabled() for control in motion)
    limit = form.controls["Sharpening.MotionLimit"]
    limit.setCurrentIndex(limit.findData("1"))
    assert not form.save_button.isEnabled(), "the start must come before the end"
    assert form.hint.text() == "The motion where it starts must be below the motion where it is complete."
    limit.setCurrentIndex(limit.findData("32"))
    assert form.save_button.isEnabled()
    assert form.values()["Sharpening.MotionLimit"] == 32.0


def test_the_settings_groups_open_on_demand_and_say_what_they_hold():
    from bc250cc.infrastructure import helixsr

    sidebar = _sidebar()
    form = sidebar.helixsr_settings
    defaults = helixsr.helixsr_defaults()
    sidebar.set_state(_state(_ready(settings=defaults, settings_defaults=defaults)))
    assert [title for title in form.groups] == ["Sharpening", "Network", "Compatibility"]
    assert not any(form.is_group_expanded(title) for title in form.groups), "closed, as on Compatibility"
    summary = form.groups["Sharpening"][3]
    assert summary.text() == "Off", "nothing else counts while sharpening is off"
    mode = form.controls["Sharpening.Mode"]
    mode.setCurrentIndex(mode.findData("override"))
    assert summary.text().startswith("Fixed · 0.3")
    form.groups["Network"][1].click()
    assert form.is_group_expanded("Network")
