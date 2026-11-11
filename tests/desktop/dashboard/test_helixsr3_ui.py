"""HelixSR 3 in the Upscaling tab: the bridge's games, ways and settings."""

from __future__ import annotations

from PyQt6.QtWidgets import QApplication

from frontends.desktop.components.dashboard_widgets import PreparationSidebar, game_matrix_rows

_APP = QApplication.instance() or QApplication([])

READY = {"scaler": True, "fsr": True}


def _game(name, appid, ways, installed=None, **extra):
    return {"appid": appid, "name": name, "folder": f"/games/{name}", "ways": ways,
            "recommended": ways[0] if ways else None, "installed_way": installed,
            "version": extra.pop("version", "3.3.0" if installed else None),
            "way_ready": extra.pop("way_ready", READY), "managed_by": extra.pop("managed_by", "bridge"),
            "outdated": extra.pop("outdated", False), "previous_version": extra.pop("previous", None), **extra}


def _cell(rows, name):
    return next(row["helixsr"] for row in rows if row["name"] == name)


def _actions(cell):
    return [(label, action, enabled) for label, action, enabled in cell[3]]


def test_bridge_games_offer_both_ways_recommended_first():
    rows = game_matrix_rows([], [], helixsr_ready=True, bridge_games=[
        _game("Wukong", "1", ["scaler", "fsr"]),
        _game("Control", "2", ["scaler"]),
    ])
    assert _actions(_cell(rows, "Wukong")) == [
        ("Add DLSS", "helixsr_bridge_install:1:scaler", True),
        ("Add HLX FSR 4", "helixsr_bridge_install:1:fsr", True),
    ]
    assert [label for label, *_ in _actions(_cell(rows, "Control"))] == ["Add DLSS"]


def test_dlss_waits_for_the_network_but_hlx_fsr4_does_not():
    rows = game_matrix_rows([], [], helixsr_ready=False, bridge_games=[
        _game("Wukong", "1", ["scaler", "fsr"], way_ready={"scaler": False, "fsr": True}),
    ])
    cell = _cell(rows, "Wukong")
    assert [enabled for *_rest, enabled in _actions(cell)] == [False, True]
    assert "network" in cell[2]


def test_installed_ways_switch_go_back_and_remove():
    rows = game_matrix_rows([], [], helixsr_ready=True, bridge_games=[
        _game("Cyberpunk", "3", ["scaler", "fsr"], "scaler", previous="3.1.0"),
        _game("Alan Wake 2", "4", ["scaler", "fsr"], "fsr"),
    ])
    cyberpunk = _cell(rows, "Cyberpunk")
    assert cyberpunk[:2] == ("DLSS · HelixSR Scaler", "green")
    assert [label for label, *_ in _actions(cyberpunk)] == [
        "Switch to HLX FSR 4", "Go back to the previous version", "Remove HelixSR",
    ]
    alan = _cell(rows, "Alan Wake 2")
    assert alan[:2] == ("HLX FSR 4", "green")
    assert ("Remove HelixSR", "helixsr_bridge_remove:4", True) in _actions(alan)


def test_outdated_and_legacy_games_are_updated_through_the_bridge():
    rows = game_matrix_rows([], [], helixsr_ready=True, bridge_games=[
        _game("Starfield", "5", ["scaler"], "scaler", version="3.1.0", outdated=True),
        _game("Hogwarts", "6", ["scaler", "fsr"], None, version="2.0.0", managed_by="app-2x", legacy_way="fsr"),
    ])
    starfield = _cell(rows, "Starfield")
    assert starfield[:2] == ("Update available", "orange")
    assert ("Update HelixSR", "helixsr_bridge_install:5:scaler", True) in _actions(starfield)
    hogwarts = _cell(rows, "Hogwarts")
    assert hogwarts[:2] == ("Update available", "orange")
    assert _actions(hogwarts)[0] == ("Update HelixSR", "helixsr_bridge_install:6:fsr", True)


def test_without_bridge_games_the_2x_columns_are_unchanged():
    two = [{"appid": "7", "name": "Old", "state": "installed"}]
    assert _cell(game_matrix_rows(two, [], helixsr_ready=True), "Old")[0] == "Active"


def _helixsr3(**extra):
    state = {
        "installer_available": True, "installed": True, "current": True, "wine_available": True,
        "state": "installed", "version": "3.3.0", "tag": "v3.3.0", "layout": "3",
        "capabilities": {"fg": False, "preset_k": True, "vulkan": True},
        "releases": [{"tag": "v3.3.0", "version": "3.3.0", "default": True}],
        "games": [], "scaler_games": [], "scaler_supported": True,
        "bridge_games": [_game("Wukong", "1", ["scaler", "fsr"])],
    }
    state.update(extra)
    return state


def test_fresh_3x_is_ready_for_hlx_fsr4_and_offers_the_dlss_build():
    sidebar = PreparationSidebar(standalone=True)
    sidebar._render_helixsr(_helixsr3(
        network_ready=False, ready={"network": False, "hlx": True, "preset_k": False, "fg": False},
    ))
    assert sidebar.helixsr_card.status.text() == "Ready"
    assert not sidebar.helixsr_network_button.isHidden()
    assert sidebar.helixsr_network_button.text() == "Build DLSS network"
    assert sidebar.helixsr_fg_button.isHidden()
    assert sidebar.helixsr_preset_k_button.isHidden()
    assert not sidebar.helixsr_scan_button.isHidden()


def test_built_3x_offers_preset_k_and_vulkan_and_keeps_settings_to_scaler():
    sidebar = PreparationSidebar(standalone=True)
    sidebar._render_helixsr(_helixsr3(
        network_ready=True, ready={"network": True, "hlx": True, "preset_k": False, "fg": False},
        bridge_games=[_game("Cyberpunk", "3", ["scaler", "fsr"], "scaler")],
        scaler_settings=[{"id": "Scaler:HelixSR.WaveSize", "name": "HelixSR.WaveSize", "kind": "choice",
                          "choices": ["auto", "64", "32"], "default": "auto"}],
    ))
    assert sidebar.helixsr_network_button.isHidden()
    assert sidebar.helixsr_preset_k_button.request_payload["action"] == "helixsr_network:preset_k"
    assert sidebar.helixsr_vulkan_button.request_payload["action"] == "helixsr_network:vulkan,rebuild"
    settings = sidebar.helixsr_settings
    static = {title for title, _fields in settings.GROUPS}
    for title, (head, *_rest) in settings.groups.items():
        assert head.parentWidget().isHidden() == (title in static), title
    assert "HelixSR Scaler" in settings.groups


def test_games_put_in_outside_control_center_offer_only_remove():
    rows = game_matrix_rows([], [], helixsr_ready=True, bridge_games=[
        _game("Desktop game", "8", ["scaler", "fsr"], "scaler", managed_by="other"),
    ])
    cell = _cell(rows, "Desktop game")
    assert cell[:2] == ("DLSS · HelixSR Scaler", "green")
    assert _actions(cell) == [("Remove HelixSR", "helixsr_bridge_remove:8", True)]


def test_folders_added_by_hand_keep_their_detail():
    rows = game_matrix_rows([], [], helixsr_ready=True, bridge_games=[
        _game("Hand", "Folder_abc", ["fsr"]),
    ])
    row = next(row for row in rows if row["name"] == "Hand")
    assert row["folder_detail"] == "Outside Steam"
    assert ("Add HLX FSR 4", "helixsr_bridge_install:Folder_abc:fsr", True) in _actions(row["helixsr"])


def test_every_helixsr3_action_reaches_the_backend(monkeypatch):
    """Each payload the Upscaling tab sends is confirmed, then handed over."""
    from types import SimpleNamespace

    from PyQt6.QtWidgets import QDialog, QWidget

    from frontends.desktop.pages import gpu_governor
    from frontends.desktop.pages.gpu_governor import GpuGovernorPage

    monkeypatch.setattr(gpu_governor.ConfirmDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    sent = []
    page = SimpleNamespace(
        current_state={"tools": {"helixsr": _helixsr3(bridge_games=[
            _game("Cyberpunk", "3", ["scaler", "fsr"], "scaler", previous="3.1.0"),
            _game("Hogwarts", "6", ["scaler", "fsr"], None, managed_by="app-2x", legacy_way="fsr"),
        ])}},
        controller=SimpleNamespace(gestionar_helixsr=sent.append),
        _run_backend_action=lambda work, *_args, **_kwargs: work(),
    )
    parent = QWidget()
    page._manage_helixsr_bridge = lambda action, **kw: GpuGovernorPage._manage_helixsr_bridge(page, action, **kw)
    for action in ("bridge_install:3:fsr", "bridge_install:6:fsr", "bridge_install:9:scaler",
                   "bridge_rollback:3", "bridge_remove:3", "network:preset_k", "network:vulkan,rebuild"):
        GpuGovernorPage._manage_helixsr(page, action, dialog_parent=parent)
    assert sent == ["bridge_install:3:fsr", "bridge_install:6:fsr", "bridge_install:9:scaler",
                    "bridge_rollback:3", "bridge_remove:3", "network:preset_k", "network:vulkan,rebuild"]
