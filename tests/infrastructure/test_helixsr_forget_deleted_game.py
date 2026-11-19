"""R-2e7f6048: a game deleted from the disk can be taken off the HelixSR list."""

from __future__ import annotations

import json

import pytest

from bc250cc.infrastructure import helixsr


@pytest.fixture
def stores(tmp_path, monkeypatch):
    bridge, folders = tmp_path / "bridge.json", tmp_path / "folders.json"
    monkeypatch.setattr(helixsr, "_bridge_records_path", lambda: bridge)
    monkeypatch.setattr(helixsr, "_folders_path", lambda: folders)
    monkeypatch.setattr(helixsr, "_forget_bridge_games", lambda: None)
    monkeypatch.setattr(helixsr, "_records", lambda: {})
    monkeypatch.setattr(helixsr, "_scaler_records", lambda: {})

    def bridge_must_not_run(*args, **kwargs):
        raise AssertionError("the bridge must not run for a folder that is gone")

    monkeypatch.setattr(helixsr, "_run_bridge", bridge_must_not_run)
    return bridge, folders


def test_a_bridge_record_whose_folder_is_gone_is_dropped(tmp_path, stores):
    bridge, _ = stores
    gone = tmp_path / "gone"
    bridge.write_text(json.dumps({"42": {"name": "Old game", "folder": str(gone)}}))
    result = helixsr.remove_helixsr_bridge("42")
    assert result["game"] == "Old game"
    assert json.loads(bridge.read_text()) == {}


def test_a_listed_folder_that_is_gone_is_forgotten(tmp_path, stores):
    _, folders = stores
    folders.write_text(json.dumps({"folder-x": {"name": "Moved", "path": str(tmp_path / "nowhere")}}))
    result = helixsr.remove_helixsr_bridge("folder-x")
    assert result["game"] == "Moved"
    assert json.loads(folders.read_text()) == {}


def test_only_one_network_build_runs_in_a_release_folder():
    block = helixsr._setup_block("/x/HelixSR")
    assert "flock -n 9" in block and ".bc250-network-build.lock" in block


def test_a_listed_steam_game_whose_folder_is_gone_is_hidden_for_good(tmp_path, stores, monkeypatch):
    monkeypatch.setattr(helixsr, "helixsr_root", lambda: tmp_path)

    def gone(_appid):
        raise RuntimeError("This game is not installed in Steam.")

    monkeypatch.setattr(helixsr, "_game", gone)
    result = helixsr.remove_helixsr_bridge("1234")
    assert result["forgotten"] is True
    assert "1234" in helixsr._hidden_games()


def test_the_list_marks_a_missing_folder_and_leaves_out_a_hidden_one(tmp_path, monkeypatch):
    monkeypatch.setattr(helixsr, "helixsr_root", lambda: tmp_path)
    present = tmp_path / "present"
    present.mkdir()
    monkeypatch.setattr(helixsr, "installed_steam_game_folders", lambda: [
        {"appid": "1", "name": "Here", "path": str(present)},
        {"appid": "2", "name": "Gone", "path": str(tmp_path / "gone")},
        {"appid": "3", "name": "Hidden", "path": str(tmp_path / "hidden")},
    ])
    monkeypatch.setattr(helixsr, "steam_shortcut_game_folders", lambda: [])
    monkeypatch.setattr(helixsr, "_folders", lambda: {})
    monkeypatch.setattr(helixsr, "_records", lambda: {})
    monkeypatch.setattr(helixsr, "_scaler_records", lambda: {})
    monkeypatch.setattr(helixsr, "_bridge_records", lambda: {})
    monkeypatch.setattr(helixsr, "_run_bridge", lambda *a, **k: {"games": []})
    monkeypatch.setattr(helixsr, "helixsr_directory", lambda: tmp_path)
    helixsr._bridge_games_cache.clear()
    helixsr._hide_game("3")
    rows = {row["appid"]: row for row in helixsr._bridge_game_rows({})}
    assert rows["1"]["missing"] is False and rows["2"]["missing"] is True and "3" not in rows


def test_a_missing_game_offers_only_to_come_off_the_list():
    from frontends.desktop.components import dashboard_widgets

    rows = {}

    def row_for(appid, name):
        return rows.setdefault(appid, {"appid": appid, "name": name, "helixsr": None})

    dashboard_widgets._bridge_cells(row_for, [{"appid": "2", "name": "Gone", "missing": True}])
    text, _tone, _copy, actions = rows["2"]["helixsr"]
    assert text == "Not on disk" and actions == (("Remove from list", "helixsr_bridge_remove:2", True),)


def test_an_uninstalled_game_whose_folder_was_left_behind_is_forgotten(tmp_path, stores, monkeypatch):
    """R-76c35a55: Steam left the folder (saves, configs) but no .exe; the bridge refused."""
    monkeypatch.setattr(helixsr, "helixsr_root", lambda: tmp_path)
    leftovers = tmp_path / "Hogwarts Legacy"
    (leftovers / "Phoenix" / "Saved").mkdir(parents=True)
    (leftovers / "Phoenix" / "Saved" / "settings.ini").write_text("x")
    monkeypatch.setattr(helixsr, "_game", lambda _appid: {"name": "Hogwarts Legacy", "path": str(leftovers)})
    result = helixsr.remove_helixsr_bridge("990080")
    assert result == {"game": "Hogwarts Legacy", "forgotten": True}
    assert "990080" in helixsr._hidden_games()
    assert leftovers.is_dir()  # nothing of the owner's is deleted


def test_a_bridge_record_whose_game_left_only_leftovers_is_dropped(tmp_path, stores):
    bridge, _ = stores
    leftovers = tmp_path / "leftovers"
    leftovers.mkdir()
    (leftovers / "dxgi.dll").write_text("helix")
    bridge.write_text(json.dumps({"7": {"name": "Gone game", "folder": str(leftovers)}}))
    result = helixsr.remove_helixsr_bridge("7")
    assert result == {"game": "Gone game", "forgotten": True}
    assert json.loads(bridge.read_text()) == {}


def test_a_game_that_is_still_installed_goes_through_the_bridge(tmp_path, stores, monkeypatch):
    game = tmp_path / "Game"
    game.mkdir()
    (game / "Game.exe").write_text("mz")
    monkeypatch.setattr(helixsr, "_game", lambda _appid: {"name": "Game", "path": str(game)})
    monkeypatch.setattr(helixsr, "_refuse_running", lambda _folder: None)
    calls = []
    monkeypatch.setattr(helixsr, "_run_bridge", lambda *args: calls.append(args) or {"ok": True})
    assert helixsr.remove_helixsr_bridge("55") == {"game": "Game"}
    assert calls == [("remove", "--game", str(game))]


def test_a_shader_compiler_crash_is_retried_once_like_a_wine_disconnect():
    """R-72957d45: dxc under Wine crashed on one shader at 99%; R-3f6a7098: Wine closed."""
    import subprocess

    block = helixsr._setup_block("/x/HelixSR")
    assert "grep -q 'wine client error'" in block
    assert "grep -Eq '^failed: .*dxc-wine[.]sh|Internal compiler error'" in block
    assert block.count('bc250_attempt=2') == 2  # one retry in total, whatever the cause
    assert '> >(tee -a "$bc250_wine_log") 2> >(tee -a "$bc250_wine_log" >&2)' in block
    result = subprocess.run(["bash", "-n", "-c", block], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
