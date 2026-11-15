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
