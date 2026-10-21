"""Undoing OptiScaler Client's install in a game when the client cannot.

The client records each game it patched in a receipt; its own Restore walks
the folder as the receipt spelled it and refuses any symlink, so a game added
through ``~/.steam/steam`` can never be restored by it. Control Center does
the same restore through the real folder, into a backup it can put back.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path

import pytest

from bc250cc.infrastructure import bc250_opticlient, helixsr, opticlient_undo
from frontends.desktop.components.dashboard_widgets import game_matrix_rows


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


#: What the client wrote: path -> (installed bytes, original bytes or None).
FILES = {
    "dxgi.dll": (b"optiscaler proxy", None),
    "OptiScaler.ini": (b"[FSR]\n", None),
    "OptiScaler/amd_fidelityfx_upscaler_dx12.dll": (b"fsr4 int8", None),
    "OptiScaler/plugins/OptiPatcher.asi": (b"patcher", None),
    "nvngx_dlss.dll": (b"client dlss", b"game's own dlss"),
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A game OptiScaler Client installed into through a linked Steam folder."""
    config, data = tmp_path / "config", tmp_path / "data"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    monkeypatch.setattr(opticlient_undo, "_running", lambda: False)
    monkeypatch.setattr(helixsr, "_refuse_running", lambda folder: None)
    monkeypatch.setattr(helixsr, "_optiscaler_records", lambda: {})
    opticlient_undo._DIGESTS.clear()
    real = tmp_path / "share" / "Steam"
    game = real / "steamapps" / "common" / "Space Game"
    (game / "OptiScaler" / "plugins").mkdir(parents=True)
    (game / "game.exe").write_bytes(b"MZ game")
    (tmp_path / "dotsteam").mkdir()
    (tmp_path / "dotsteam" / "steam").symlink_to(real)
    linked = tmp_path / "dotsteam" / "steam" / "steamapps" / "common" / "Space Game"
    state = config / "OptiscalerClient-BC250" / "BC250" / "games" / _key(os.path.realpath(game))
    (state / "originals").mkdir(parents=True)
    receipt = []
    for relative, (installed, original) in FILES.items():
        (game / relative).write_bytes(installed)
        backup = _key(relative)
        if original is not None:
            (state / "originals" / backup).write_bytes(original)
        receipt.append({"Path": relative, "Original": _sha(original) if original else None,
                        "Installed": _sha(installed), "Backup": backup})
    (state / "receipt.json").write_text(json.dumps({
        "Schema": 1, "Root": str(linked), "Target": "OptiScaler/amd_fidelityfx_upscaler_dx12.dll",
        "Release": "4.0.0-rc11", "Files": receipt, "Hint": "",
    }))
    (config / "OptiscalerClient-BC250" / "games.json").write_text(json.dumps([
        {"Name": "spacegame", "AppId": "Manual_1234", "InstallPath": str(linked)},
        {"Name": "Space Game", "AppId": "100", "InstallPath": str(game)},
    ]))
    return {"game": game, "linked": linked, "state": state, "key": state.name,
            "link": tmp_path / "dotsteam" / "steam", "data": data}


def test_every_recorded_game_is_read_through_its_real_folder(client):
    [record] = opticlient_undo.opticlient_installations()

    assert record["state"] == "intact" and record["removable"]
    # Steam's own entry names it, not the one added by hand.
    assert (record["name"], record["appid"]) == ("Space Game", "100")
    assert record["real_root"] == str(client["game"])
    assert record["linked_path"] == str(client["link"])
    assert (record["files"], record["replaced"]) == (5, 1)


def test_removal_moves_the_files_out_and_puts_the_games_own_back(client):
    game = client["game"]

    result = opticlient_undo.remove_opticlient_installation(client["key"])

    assert result["game"] == "Space Game" and result["files"] == 5 and result["restored"] == 1
    assert sorted(p.name for p in game.iterdir()) == ["game.exe", "nvngx_dlss.dll"]
    assert (game / "nvngx_dlss.dll").read_bytes() == b"game's own dlss"
    backup = Path(result["backup"])
    assert backup.parent == client["data"] / "bc250-control-center" / "opticlient-backups"
    for relative, (installed, _original) in FILES.items():
        assert (backup / "files" / relative).read_bytes() == installed
    # The client's record went with them, so the client sees a clean game.
    assert not client["state"].exists()
    assert (backup / "client-record" / "receipt.json").is_file()
    assert json.loads((backup / "manifest.json").read_text())["state"] == "complete"
    assert opticlient_undo.opticlient_installations() == []
    [saved] = opticlient_undo.opticlient_backups()
    assert saved["state"] == "ready" and saved["restorable"] and saved["appid"] == "100"


def test_put_back_returns_files_and_record_exactly(client):
    game = client["game"]
    backup = Path(opticlient_undo.remove_opticlient_installation(client["key"])["backup"])

    result = opticlient_undo.restore_opticlient_backup(backup.name)

    assert result == {"game": "Space Game", "files": 5}
    for relative, (installed, _original) in FILES.items():
        assert (game / relative).read_bytes() == installed
    assert (client["state"] / "receipt.json").is_file()
    assert not backup.exists()
    [record] = opticlient_undo.opticlient_installations()
    assert record["state"] == "intact"


def test_a_changed_file_stops_everything(client):
    (client["game"] / "OptiScaler.ini").write_bytes(b"[FSR]\nedited\n")

    [record] = opticlient_undo.opticlient_installations()
    assert record["state"] == "changed" and not record["removable"]
    assert record["changed"] == ["OptiScaler.ini"]
    with pytest.raises(RuntimeError, match="changed after the client installed them"):
        opticlient_undo.remove_opticlient_installation(client["key"])
    assert (client["game"] / "dxgi.dll").is_file()
    assert (client["state"] / "receipt.json").is_file()
    assert opticlient_undo.opticlient_backups() == []


def test_files_already_gone_leave_only_the_record_to_clear(client):
    game = client["game"]
    for relative, (_installed, original) in FILES.items():
        if original is None:
            (game / relative).unlink()
        else:
            (game / relative).write_bytes(original)

    [record] = opticlient_undo.opticlient_installations()
    assert record["state"] == "removed" and record["removable"]
    result = opticlient_undo.remove_opticlient_installation(client["key"])

    assert result["record_only"] and result["files"] == 0
    assert not client["state"].exists()
    [saved] = opticlient_undo.opticlient_backups()
    assert saved["state"] == "record-only" and not saved["restorable"]
    with pytest.raises(RuntimeError, match="only the client's record"):
        opticlient_undo.restore_opticlient_backup(saved["id"])


def test_files_deleted_by_hand_take_the_rest_out(client):
    (client["game"] / "dxgi.dll").unlink()

    [record] = opticlient_undo.opticlient_installations()
    assert record["state"] == "partial" and record["removable"]
    result = opticlient_undo.remove_opticlient_installation(client["key"])
    assert result["files"] == 4
    assert not (client["game"] / "OptiScaler.ini").exists()


def test_an_interrupted_client_operation_is_left_to_the_client(client):
    (client["state"] / "pending.json").write_text(json.dumps({"Root": str(client["linked"])}))

    [record] = opticlient_undo.opticlient_installations()
    assert record["state"] == "pending" and record["appid"] == "100"
    with pytest.raises(RuntimeError, match="Restore / recover selected"):
        opticlient_undo.remove_opticlient_installation(client["key"])


def test_a_helixsr_route_through_this_optiscaler_comes_out_first(client, monkeypatch):
    monkeypatch.setattr(helixsr, "_optiscaler_records", lambda: {"100": {"root": str(client["linked"])}})

    [record] = opticlient_undo.opticlient_installations()
    assert record["state"] == "helixsr"
    with pytest.raises(RuntimeError, match="Remove HelixSR"):
        opticlient_undo.remove_opticlient_installation(client["key"])


def test_nothing_happens_while_the_client_is_open(client, monkeypatch):
    monkeypatch.setattr(opticlient_undo, "_running", lambda: True)

    with pytest.raises(RuntimeError, match="Close OptiScaler Client"):
        opticlient_undo.remove_opticlient_installation(client["key"])
    assert (client["game"] / "dxgi.dll").is_file()


def test_the_clients_operation_lock_is_respected(client):
    lock = client["state"].parent.parent / "operation.lock"
    with lock.open("a+b") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="still running"):
            opticlient_undo.remove_opticlient_installation(client["key"])
    assert (client["game"] / "dxgi.dll").is_file()


def test_nothing_happens_while_the_game_runs(client, monkeypatch):
    def running(folder):
        raise RuntimeError("Close this game before changing its files.")

    monkeypatch.setattr(helixsr, "_refuse_running", running)
    with pytest.raises(RuntimeError, match="Close this game"):
        opticlient_undo.remove_opticlient_installation(client["key"])
    assert (client["game"] / "dxgi.dll").is_file()


def test_a_failure_half_way_puts_everything_back(client, monkeypatch):
    def broken(source, target, digest):
        raise RuntimeError("Disk full.")

    monkeypatch.setattr(opticlient_undo, "_copy_verified", broken)
    with pytest.raises(RuntimeError, match="Everything was put back"):
        opticlient_undo.remove_opticlient_installation(client["key"])

    for relative, (installed, _original) in FILES.items():
        assert (client["game"] / relative).read_bytes() == installed
    assert (client["state"] / "receipt.json").is_file()
    assert not any((client["data"] / "bc250-control-center" / "opticlient-backups").iterdir())


def test_put_back_refuses_once_the_game_has_files_there_again(client):
    backup = Path(opticlient_undo.remove_opticlient_installation(client["key"])["backup"])
    (client["game"] / "dxgi.dll").write_bytes(b"another mod")

    [saved] = opticlient_undo.opticlient_backups()
    assert saved["state"] == "game-changed"
    with pytest.raises(RuntimeError, match="changed since the backup"):
        opticlient_undo.restore_opticlient_backup(backup.name)
    assert (client["game"] / "dxgi.dll").read_bytes() == b"another mod"
    assert (backup / "files" / "dxgi.dll").is_file()


def test_put_back_refuses_once_the_client_recorded_the_game_again(client):
    backup = Path(opticlient_undo.remove_opticlient_installation(client["key"])["backup"])
    client["state"].mkdir(parents=True)

    [saved] = opticlient_undo.opticlient_backups()
    assert saved["state"] == "client-record"
    with pytest.raises(RuntimeError, match="record of this game again"):
        opticlient_undo.restore_opticlient_backup(backup.name)


def test_a_path_leaving_the_game_folder_is_never_followed(client):
    receipt = json.loads((client["state"] / "receipt.json").read_text())
    receipt["Files"][0]["Path"] = "../outside.dll"
    (client["state"] / "receipt.json").write_text(json.dumps(receipt))

    [record] = opticlient_undo.opticlient_installations()
    assert record["state"] == "unsupported" and not record["removable"]
    with pytest.raises(RuntimeError, match="not one Control Center can read"):
        opticlient_undo.remove_opticlient_installation(client["key"])


def test_a_linked_folder_inside_the_game_is_never_followed(client, tmp_path):
    game = client["game"]
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (game / "OptiScaler" / "plugins" / "OptiPatcher.asi").rename(outside / "OptiPatcher.asi")
    (game / "OptiScaler" / "plugins").rmdir()
    (game / "OptiScaler" / "plugins").symlink_to(outside)

    [record] = opticlient_undo.opticlient_installations()
    assert record["state"] == "changed"
    assert (outside / "OptiPatcher.asi").is_file()


def test_unknown_ids_are_refused():
    with pytest.raises(RuntimeError, match="no record"):
        opticlient_undo.remove_opticlient_installation("../../etc")
    with pytest.raises(RuntimeError, match="Unknown backup"):
        opticlient_undo.restore_opticlient_backup("../escape")


def test_the_client_state_carries_records_even_without_the_client(client):
    state = bc250_opticlient.opticlient_state(machine="x86_64")

    assert not state["current"] and state["games"] == []
    [record] = state["installations"]
    assert record["key"] == client["key"]
    assert state["backups"] == []


def test_the_repository_routes_both_actions(client, tmp_path):
    from tests.desktop.gpu.test_helixsr import _repository

    repository = _repository(tmp_path)
    result = repository.gestionar_fsr4_bc250(f"undo:{client['key']}")
    assert result["files"] == 5
    assert repository.gestionar_fsr4_bc250(f"backup_restore:{Path(result['backup']).name}")["files"] == 5


# ------------------------------------------------------------ the game table


def _record(state="intact", **extra):
    return {"key": "a" * 64, "name": "Space Game", "appid": "100", "state": state,
            "removable": state in {"intact", "partial", "removed"}, "linked_path": "", **extra}


def test_a_recorded_game_offers_removal_beside_its_fsr4_reading():
    fsr4 = [{"appid": "100", "name": "Space Game", "state": "ready", "adapter": "dxgi.dll"}]
    [row] = game_matrix_rows([], fsr4, helixsr_ready=True, fsr4_installations=[_record()])

    text, tone, _tooltip, actions = row["fsr4"]
    assert (text, tone) == ("Active", "green")
    assert actions == (("Remove OptiScaler, keep a backup", f"fsr4_undo:{'a' * 64}", True),)


def test_a_linked_record_says_why_the_client_cannot_undo_it():
    [row] = game_matrix_rows([], [], helixsr_ready=True,
                             fsr4_installations=[_record(linked_path="/home/u/.steam/steam")])
    assert "/home/u/.steam/steam" in row["fsr4"][2]


def test_a_record_without_files_is_shown_and_cleared():
    fsr4 = [{"appid": "100", "name": "Space Game", "state": "not-installed"}]
    [row] = game_matrix_rows([], fsr4, helixsr_ready=True, fsr4_installations=[_record("removed")])

    text, tone, _tooltip, actions = row["fsr4"]
    assert (text, tone) == ("Record left", "orange")
    assert actions[-1] == ("Clear the client's record", f"fsr4_undo:{'a' * 64}", True)


def test_a_changed_record_offers_nothing_it_would_refuse():
    [row] = game_matrix_rows([], [], helixsr_ready=True, fsr4_installations=[_record("changed")])
    assert row["fsr4"][:2] == ("Check the files", "orange")
    assert row["fsr4"][3] == (("Remove OptiScaler, keep a backup", f"fsr4_undo:{'a' * 64}", False),)


def test_a_backup_offers_to_put_optiscaler_back():
    backup = {"id": "space-game-20261020-120000", "name": "Space Game", "appid": "100",
              "state": "ready", "created": "2026-10-20T12:00:00", "path": "/b"}
    [row] = game_matrix_rows([], [], helixsr_ready=True, fsr4_backups=[backup])
    assert row["fsr4"][0] == "In a backup"
    assert row["fsr4"][3] == (("Put OptiScaler back", "fsr4_backup_restore:space-game-20261020-120000", True),)
    # Not while the client records the game again, nor when it cannot.
    assert game_matrix_rows([], [], helixsr_ready=True, fsr4_backups=[{**backup, "state": "game-changed"}]) == []


def test_scaler_waits_until_the_clients_optiscaler_is_out():
    scaler = [{"appid": "100", "name": "Space Game", "state": "available"}]
    [row] = game_matrix_rows([], [], helixsr_ready=True, scaler_games=scaler, scaler_ready=True,
                             fsr4_installations=[_record()])
    assert row["helixsr"] is None
    [row] = game_matrix_rows([], [], helixsr_ready=True, scaler_games=scaler, scaler_ready=True,
                             fsr4_installations=[_record("removed")])
    assert row["helixsr"][3] == (("Add HelixSR Scaler", "helixsr_scaler_install:100", True),)


# ------------------------------------------------------------ the page


def _page(monkeypatch, fsr4: dict, result: dict, *, accept=True):
    from PyQt6.QtWidgets import QDialog

    from frontends.desktop.pages import gpu_governor
    from frontends.desktop.pages.gpu_governor import GpuGovernorPage

    shown, recorded, calls = [], [], []

    class Dialog:
        def __init__(self, title, message, summary=(), confirm_text="", **_):
            shown.append((title, dict(summary), confirm_text))

        def exec(self):
            return QDialog.DialogCode.Accepted if accept else QDialog.DialogCode.Rejected

    monkeypatch.setattr(gpu_governor, "ConfirmDialog", Dialog)
    monkeypatch.setattr(GpuGovernorPage, "_record_preparation_result",
                        staticmethod(lambda _page, _title, message: recorded.append(message)))
    page = type("Page", (), {
        "_manage_opticlient_files": GpuGovernorPage._manage_opticlient_files,
        "current_state": {"tools": {"fsr4": fsr4}},
        "controller": type("C", (), {"gestionar_fsr4_bc250": lambda self, action: calls.append(action) or result})(),
        "_run_backend_action": lambda self, operation, success, *_a, **_k: success(operation()),
    })()
    return page, shown, recorded, calls


def test_the_page_confirms_removal_and_says_where_the_backup_is(monkeypatch):
    fsr4 = {"installations": [_record(files=18)]}
    page, shown, recorded, calls = _page(
        monkeypatch, fsr4, {"game": "Space Game", "files": 18, "backup": "/b/space", "record_only": False})

    page._manage_opticlient_files(f"undo:{'a' * 64}", dialog_parent=None)

    assert shown == [("Remove OptiScaler from this game", {"Game": "Space Game", "Files": "18"},
                      "Remove, keep a backup")]
    assert calls == [f"undo:{'a' * 64}"]
    assert recorded == ["OptiScaler was removed from Space Game. Its 18 files are kept in /b/space."]


def test_the_page_clears_a_record_and_puts_a_backup_back(monkeypatch):
    fsr4 = {"installations": [_record("removed")]}
    page, shown, recorded, _calls = _page(
        monkeypatch, fsr4, {"game": "Space Game", "files": 0, "backup": "/b/r", "record_only": True})
    page._manage_opticlient_files(f"undo:{'a' * 64}", dialog_parent=None)
    assert shown[0][0] == "Clear OptiScaler Client's record" and shown[0][2] == "Clear record"
    assert recorded == ["OptiScaler Client's record of Space Game was cleared. It is kept in /b/r."]

    fsr4 = {"backups": [{"id": "space-1", "name": "Space Game", "files": 5, "path": "/b/space-1"}]}
    page, shown, recorded, calls = _page(monkeypatch, fsr4, {"game": "Space Game", "files": 5})
    page._manage_opticlient_files("backup_restore:space-1", dialog_parent=None)
    assert shown[0][1] == {"Game": "Space Game", "Files": "5", "Backup folder": "/b/space-1"}
    assert calls == ["backup_restore:space-1"]
    assert recorded == ["OptiScaler is back in Space Game."]


def test_a_cancelled_confirmation_changes_nothing(monkeypatch):
    page, _shown, recorded, calls = _page(monkeypatch, {"installations": [_record()]}, {}, accept=False)
    page._manage_opticlient_files(f"undo:{'a' * 64}", dialog_parent=None)
    assert calls == [] and recorded == []


# ------------------------------------------------------------ power cuts and drives


def test_the_manifest_names_each_file_as_soon_as_it_left_the_game(client, monkeypatch):
    """A power cut half way: the manifest already lists what was moved."""
    moved = []
    real_move = opticlient_undo._move_verified

    def cut_after_two(source, target, digest):
        if len(moved) == 2:
            raise KeyboardInterrupt  # the process dies: no rollback runs
        real_move(source, target, digest)
        moved.append(target)

    monkeypatch.setattr(opticlient_undo, "_move_verified", cut_after_two)
    with pytest.raises(KeyboardInterrupt):
        opticlient_undo.remove_opticlient_installation(client["key"])
    monkeypatch.setattr(opticlient_undo, "_move_verified", real_move)

    [backup] = opticlient_undo.opticlient_backups()
    assert backup["state"] == "interrupted" and backup["restorable"] and backup["files"] == 2
    [record] = opticlient_undo.opticlient_installations()
    assert record["state"] == "interrupted" and not record["removable"]
    assert record["backup"] == backup["id"]
    with pytest.raises(RuntimeError, match="interrupted while taking OptiScaler out"):
        opticlient_undo.remove_opticlient_installation(client["key"])

    assert opticlient_undo.restore_opticlient_backup(backup["id"])["files"] == 2
    for relative, (installed, _original) in FILES.items():
        assert (client["game"] / relative).read_bytes() == installed
    assert opticlient_undo.opticlient_backups() == []
    [record] = opticlient_undo.opticlient_installations()
    assert record["state"] == "intact"


def test_a_cut_after_a_replaced_file_left_puts_the_game_file_back_too(client, monkeypatch):
    real_copy = opticlient_undo._copy_verified

    def cut(source, target, digest):
        raise KeyboardInterrupt

    monkeypatch.setattr(opticlient_undo, "_copy_verified", cut)
    with pytest.raises(KeyboardInterrupt):
        opticlient_undo.remove_opticlient_installation(client["key"])
    monkeypatch.setattr(opticlient_undo, "_copy_verified", real_copy)

    # nvngx_dlss.dll left the game and the game's own copy never came back.
    assert not (client["game"] / "nvngx_dlss.dll").exists()
    [backup] = opticlient_undo.opticlient_backups()
    assert backup["state"] == "interrupted"
    opticlient_undo.restore_opticlient_backup(backup["id"])
    assert (client["game"] / "nvngx_dlss.dll").read_bytes() == b"client dlss"


def test_a_game_on_another_drive_needs_room_for_the_copy(client, monkeypatch):
    real_stat = os.stat

    class Other:
        def __init__(self, info):
            self._info = info

        def __getattr__(self, name):
            return 999 if name == "st_dev" else getattr(self._info, name)

    def stat(path, *args, **kwargs):
        info = real_stat(path, *args, **kwargs)
        return Other(info) if str(path) == str(client["game"]) else info

    monkeypatch.setattr(opticlient_undo.os, "stat", stat)
    monkeypatch.setattr(opticlient_undo.shutil, "disk_usage", lambda path: type("U", (), {"free": 1024})())
    with pytest.raises(RuntimeError, match="not enough free space"):
        opticlient_undo.remove_opticlient_installation(client["key"])
    assert (client["game"] / "dxgi.dll").is_file()
    assert opticlient_undo.opticlient_backups() == []


def test_a_game_on_another_drive_is_copied_checked_and_then_removed(client, monkeypatch):
    real_replace = os.replace
    game = str(client["game"])

    def across_drives(source, target):
        if str(source).startswith(game) and not str(target).startswith(game):
            raise OSError(18, "Invalid cross-device link")
        real_replace(source, target)

    monkeypatch.setattr(opticlient_undo.os, "replace", across_drives)
    result = opticlient_undo.remove_opticlient_installation(client["key"])
    assert result["files"] == 5
    assert not (client["game"] / "dxgi.dll").exists()
    assert (Path(result["backup"]) / "files" / "dxgi.dll").read_bytes() == b"optiscaler proxy"
    assert not list(Path(result["backup"]).rglob("*.bc250-part"))


def test_an_interrupted_removal_is_offered_back_in_the_table():
    record = _record("interrupted", backup="space-1")
    [row] = game_matrix_rows([], [{"appid": "100", "name": "Space Game", "state": "ready"}],
                             helixsr_ready=True, fsr4_installations=[record])
    assert row["fsr4"][:2] == ("Interrupted", "orange")
    assert row["fsr4"][3][-1] == ("Put OptiScaler back", "fsr4_backup_restore:space-1", True)
