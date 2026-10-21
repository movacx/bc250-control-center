"""Keeping HelixSR current without a new Control Center for every release.

HelixSR and OptiScaler Client publish often. Their release lists are read on
their own (twice a day at most), a newer release is offered as the card's
next step, every game on another release can be updated in one go (HelixSR
Scaler included, keeping the version it had to go back to), and settings a
release adds reach the form from the release itself.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bc250cc.infrastructure import bc250_opticlient, helixsr, upscaler_releases
from frontends.desktop.components.dashboard_widgets import game_matrix_rows
from tests.desktop.gpu.test_helixsr import _release_2, _steam_game, home  # noqa: F401 - fixture

#: A bridge that keeps one version per game, the one before it, and the
#: settings it was sent; its version is the release folder's name unless
#: FAKE_VERSION says otherwise.
FAKE_BRIDGE = r'''
import json, os, pathlib, sys
SCALER_SETTINGS = {
    'HelixSR.WaveSize': ('auto', '64', '32'),
    'HelixSR.FGPreset': ('c', 'full'),
    'HelixSR.QuickFlow': ('off', 'fast', 'fastest'),
}
SCALER_DEFAULTS = {'HelixSR.WaveSize': 'auto', 'HelixSR.FGPreset': 'c', 'HelixSR.QuickFlow': 'off'}
argv = sys.argv[1:]
release, command = pathlib.Path(argv[0]), argv[1]
with open(release / "bridge.log", "a", encoding="utf-8") as log:
    log.write(json.dumps(argv[1:]) + "\n")
args = dict(zip(argv[2::2], argv[3::2]))
game = pathlib.Path(args.get("--game", "."))
exe = game / "Bin"
state = exe / "fake-state.json"
saved = json.loads(state.read_text()) if state.exists() else {}
if command == "install":
    exe.mkdir(exist_ok=True)
    (exe / "HelixSR-Scaler.files").write_text("dxgi.dll\n")
    new = os.environ.get("FAKE_VERSION") or release.name
    if saved.get("version") and saved["version"] != new:
        saved["previous"] = saved["version"]
    saved["version"] = new
    saved["fg"] = args.get("--fg", "off")
elif command == "rollback":
    saved["version"], saved["previous"] = saved["previous"], saved["version"]
elif command == "scaler-fg":
    saved["fg"] = "on" if args.get("--on") == "true" else "off"
elif command == "settings-set":
    saved["settings"] = json.loads(args["--values"])
state.write_text(json.dumps(saved))
print(json.dumps({"ok": True, "messages": [], "game": {
    "exe_folder": str(exe), "scaler_dll": "dxgi.dll", "frame_generation": saved.get("fg", "off"),
    "fg_possible": True, "launch_options": None, "version": saved.get("version"),
    "previous": {"version": saved["previous"]} if saved.get("previous") else None}}))
'''


@pytest.fixture
def release(home):  # noqa: F811 - the imported fixture
    directory = helixsr.helixsr_directory()
    _release_2(directory)
    (directory / "setup").mkdir()
    (directory / helixsr.HELIXSR_BRIDGE).write_text(FAKE_BRIDGE, encoding="utf-8")
    (directory / helixsr.HELIXSR_SCALER).mkdir()
    (directory / helixsr.HELIXSR_SCALER / "OptiScaler.dll").write_bytes(b"MZ scaler")
    return directory


def _calls(directory: Path) -> list[list[str]]:
    log = directory / "bridge.log"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def _scaler_game(home: Path, appid: str, name: str, monkeypatch, version: str = "1.9.2") -> Path:  # noqa: F811 - the fixture name
    install = _steam_game(home, appid, name, {"Bin": ("game.exe",)})
    monkeypatch.setenv("FAKE_VERSION", version)
    helixsr.install_helixsr_scaler(appid)
    monkeypatch.delenv("FAKE_VERSION")
    return install


def _row(appid: str) -> dict:
    state = helixsr.helixsr_state(machine="x86_64")
    return next(row for row in state["scaler_games"] if row["appid"] == appid)


# ------------------------------------------------------------ HelixSR Scaler


def test_a_game_on_another_release_says_so(home, release, monkeypatch):  # noqa: F811
    _scaler_game(home, "100", "Space Game", monkeypatch)

    row = _row("100")
    # The test release is 1.8.1: 1.9.2 is another release, not an older one.
    assert (row["version"], row["outdated"], row["older"], row["previous"]) == ("1.9.2", True, False, "")
    assert helixsr.helixsr_state(machine="x86_64")["outdated_games"] == 1


def test_an_update_gives_the_installed_release_and_keeps_the_old_one(home, release, monkeypatch):  # noqa: F811
    _scaler_game(home, "100", "Space Game", monkeypatch)

    result = helixsr.update_helixsr_scaler("100")

    assert result == {"game": "Space Game", "version": release.name, "previous": "1.9.2"}
    assert _calls(release)[-1][:5] == ["install", "--game", _calls(release)[-1][2], "--way", "scaler"]
    row = _row("100")
    assert (row["outdated"], row["previous"]) == (False, "1.9.2")


def test_an_update_keeps_frame_generation_on(home, release, monkeypatch):  # noqa: F811
    folder = release / helixsr.HELIXSR_BUILD_FOLDER / helixsr.HELIXSR_FG_FOLDER
    folder.mkdir(parents=True)
    (folder / "_nvngx.dll").write_bytes(b"ngx")
    _scaler_game(home, "100", "Space Game", monkeypatch)
    helixsr.set_helixsr_scaler_frame_generation("100", True)

    helixsr.update_helixsr_scaler("100")

    assert _calls(release)[-1][-2:] == ["--fg", "on"]


def test_going_back_restores_the_kept_version_and_can_be_undone(home, release, monkeypatch):  # noqa: F811
    _scaler_game(home, "100", "Space Game", monkeypatch)
    helixsr.update_helixsr_scaler("100")

    result = helixsr.rollback_helixsr_scaler("100")

    assert (result["version"], result["previous"]) == ("1.9.2", release.name)
    assert _calls(release)[-1][0] == "rollback"


def test_going_back_needs_a_kept_version(home, release, monkeypatch):  # noqa: F811
    _scaler_game(home, "100", "Space Game", monkeypatch, version=release.name)
    with pytest.raises(RuntimeError, match="no earlier HelixSR version"):
        helixsr.rollback_helixsr_scaler("100")


def test_update_all_skips_an_open_game_and_names_it(home, release, monkeypatch):  # noqa: F811
    _scaler_game(home, "100", "Space Game", monkeypatch)
    open_game = _scaler_game(home, "200", "Open Game", monkeypatch)
    real_refuse = helixsr._refuse_running

    def refuse(folder, *args):
        if Path(folder) == open_game:
            raise RuntimeError("Close this game before changing its files.")
        return real_refuse(folder, *args)

    monkeypatch.setattr(helixsr, "_refuse_running", refuse)
    result = helixsr.update_all_helixsr_games()

    assert result["updated"] == ["Space Game"] and result["skipped"] == ["Open Game"]
    assert _row("100")["outdated"] is False and _row("200")["outdated"] is True


def test_the_table_offers_update_and_going_back():
    game = {"appid": "100", "name": "Space Game", "state": "installed", "frame_generation": True,
            "fg_possible": True, "outdated": True, "older": True, "version": "1.9.2", "previous": "1.9.0"}
    [row] = game_matrix_rows([], [], helixsr_ready=True, scaler_games=[game], scaler_ready=True, fg_ready=True)
    text, tone, tooltip, actions = row["helixsr"]
    assert (text, tone) == ("Update available", "orange")
    assert "1.9.2" in tooltip
    assert [label for label, _action, _enabled in actions] == [
        "Update HelixSR", "Turn off frame generation", "Go back to the previous version", "Remove HelixSR Scaler",
    ]
    assert actions[0][1] == "helixsr_scaler_update:100" and actions[2][1] == "helixsr_scaler_rollback:100"


# ------------------------------------------------------------ settings a release brings


def test_scaler_settings_come_from_the_bridge(home, release):  # noqa: F811
    rows = helixsr.helixsr_scaler_settings()

    assert [row["name"] for row in rows] == ["HelixSR.WaveSize", "HelixSR.FGPreset", "HelixSR.QuickFlow"]
    assert rows[1]["choices"] == ("c", "full") and rows[1]["default"] == "c"
    assert helixsr.helixsr_settings()["Scaler:HelixSR.FGPreset"] == "c"


def test_saving_reaches_scaler_games_through_the_bridge(home, release, monkeypatch):  # noqa: F811
    install = _scaler_game(home, "100", "Space Game", monkeypatch)
    values = {**helixsr.helixsr_settings(), "Scaler:HelixSR.QuickFlow": "fast"}

    result = helixsr.save_helixsr_settings(values)

    assert result["games"] == 1
    sent = json.loads((install / "Bin" / "fake-state.json").read_text())["settings"]
    # QuickFlow runs only with the full preset, so it is sent off.
    assert sent == {"HelixSR.WaveSize": "auto", "HelixSR.FGPreset": "c", "HelixSR.QuickFlow": "off"}
    with pytest.raises(ValueError):
        helixsr.save_helixsr_settings({"Scaler:HelixSR.FGPreset": "turbo"})


def test_a_setting_the_form_does_not_know_comes_from_the_release(home, release):  # noqa: F811
    ini = release / helixsr.HELIXSR_BUILD_FOLDER / helixsr.HELIXSR_INI
    ini.write_text(
        "[Upscaling]\nInt8 = auto\n"
        "; Faster tiles: auto (default), small or large\nTiles = auto\n"
        "; Strength 0.0 - 2.0\nGlow = 0.5\n"
        "; true = draw a frame counter\nCounter = false\n"
        "; m = one thing; q = the other\nMode = m\n"
        "[DlssFrameGeneration]\nPreset = c\n",
        encoding="utf-8",
    )

    rows = {row["id"]: row for row in helixsr.helixsr_extra_settings()}

    assert set(rows) == {"Upscaling.Tiles", "Upscaling.Glow", "Upscaling.Counter", "Upscaling.Mode"}
    assert (rows["Upscaling.Tiles"]["kind"], rows["Upscaling.Tiles"]["choices"]) == ("choice", ("auto", "small", "large"))
    assert (rows["Upscaling.Glow"]["kind"], rows["Upscaling.Glow"]["choices"]) == ("float", (0.0, 2.0))
    assert rows["Upscaling.Counter"]["kind"] == "bool" and rows["Upscaling.Counter"]["default"] is False
    assert rows["Upscaling.Mode"]["choices"] == ("m", "q")
    saved = helixsr.save_helixsr_settings({**helixsr.helixsr_settings(), "Upscaling.Tiles": "large"})
    assert saved["settings"]["Upscaling.Tiles"] == "large"
    assert "Tiles = large" in helixsr._settings_text(helixsr._release_ini(), saved["settings"])
    with pytest.raises(ValueError):
        helixsr.save_helixsr_settings({"Upscaling.Tiles": "huge\n[Log]"})


# ------------------------------------------------------------ newer releases


def _list_releases(*tags: tuple[str, bool]) -> None:
    listed = [{
        "tag_name": tag, "draft": False, "prerelease": pre,
        "assets": [{"name": f"HelixSR-{tag[1:]}.zip", "size": 1000, "digest": "sha256:" + "a" * 64}],
    } for tag, pre in tags]
    helixsr.helixsr_root().mkdir(parents=True, exist_ok=True)
    (helixsr.helixsr_root() / "releases.json").write_text(json.dumps({"time": 0, "releases": listed}))


def test_a_newer_release_is_offered_but_not_a_pre_release(home, release):  # noqa: F811
    _list_releases((helixsr.HELIXSR_TAG, False), ("v9.0.0", True))
    assert helixsr.helixsr_state(machine="x86_64")["newer"] is None

    _list_releases((helixsr.HELIXSR_TAG, False), ("v9.0.0", True), ("v8.1.0", False))
    newer = helixsr.helixsr_state(machine="x86_64")["newer"]
    assert newer == {"tag": "v8.1.0", "version": "8.1.0", "reviewed": False}


def test_the_repository_routes_the_new_actions(home, release, tmp_path, monkeypatch):  # noqa: F811
    from tests.desktop.gpu.test_helixsr import _repository

    _scaler_game(home, "100", "Space Game", monkeypatch)
    repository = _repository(tmp_path)
    assert repository.gestionar_helixsr("scaler_update:100")["previous"] == "1.9.2"
    assert repository.gestionar_helixsr("scaler_rollback:100")["version"] == "1.9.2"
    assert repository.gestionar_helixsr("update_all")["updated"] == ["Space Game"]
    _list_releases((helixsr.HELIXSR_TAG, False), ("v8.1.0", False))
    title, _command = repository.gestionar_helixsr("upgrade:v8.1.0")
    assert title == "HelixSR · install"
    assert helixsr.helixsr_release()["tag"] == "v8.1.0"


def test_a_newer_client_build_is_offered(home, monkeypatch):  # noqa: F811
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "config"))
    root = bc250_opticlient.opticlient_root()
    root.mkdir(parents=True)
    version = bc250_opticlient.OPTICLIENT_VERSION
    listed = [{"tag_name": tag, "draft": False, "prerelease": True, "assets": [
        {"name": f"bc250-opticlient-{tag.removeprefix('opticlient-v')}-linux-x64.tar.gz",
         "size": 1000, "digest": "sha256:" + "b" * 64}]}
        for tag in (bc250_opticlient.OPTICLIENT_TAG, "opticlient-v9.0.0-bc250.1")]
    (root / "releases.json").write_text(json.dumps({"time": 0, "releases": listed}))
    release = bc250_opticlient.opticlient_release()
    assert release["version"] == version
    assert bc250_opticlient._newer_build(release) == {
        "tag": "opticlient-v9.0.0-bc250.1", "version": "9.0.0-bc250.1", "reviewed": False,
    }


def test_helixsr_scalers_own_optiscaler_is_not_the_clients(tmp_path):
    folder = tmp_path / "game"
    folder.mkdir()
    (folder / "OptiScaler.ini").write_text("[x]\n")
    (folder / "dxgi.dll").write_bytes(b"MZ")
    assert bc250_opticlient._adapter_in(folder) == "dxgi.dll"
    (folder / bc250_opticlient.HELIXSR_SCALER_MARKER).write_text("dxgi.dll\n")
    assert bc250_opticlient._adapter_in(folder) == ""


# ------------------------------------------------------------ reading the lists on its own


@pytest.fixture
def fresh_checks(monkeypatch):
    monkeypatch.setattr(upscaler_releases, "_attempted", set())


def test_a_stale_list_is_read_and_saved_as_the_terminal_saves_it(home, release, fresh_checks):  # noqa: F811
    calls = []

    def fetch(url, limit):
        calls.append(url)
        return [{"tag_name": "v8.1.0", "draft": False, "prerelease": False, "body": "notes",
                 "assets": [{"name": "HelixSR-8.1.0.zip", "size": 5, "digest": "sha256:x", "url": "u"}]}]

    changed = upscaler_releases.refresh_release_lists(now=1_000_000, fetch=fetch)

    assert changed == ["helixsr"] and calls == [helixsr.HELIXSR_RELEASES_API]
    saved = json.loads((helixsr.helixsr_root() / "releases.json").read_text())
    assert saved == {"time": 1_000_000, "releases": [{
        "tag_name": "v8.1.0", "draft": False, "prerelease": False,
        "assets": [{"name": "HelixSR-8.1.0.zip", "size": 5, "digest": "sha256:x"}]}]}


def test_a_fresh_list_and_a_second_attempt_stay_offline(home, release, fresh_checks):  # noqa: F811
    calls = []
    _list_releases((helixsr.HELIXSR_TAG, False))
    (helixsr.helixsr_root() / "releases.json").write_text(json.dumps({"time": 1_000_000, "releases": []}))

    upscaler_releases.refresh_release_lists(now=1_000_000 + 60, fetch=lambda *a: calls.append(a) or [])
    assert calls == []
    upscaler_releases.refresh_release_lists(now=1_000_000 + 13 * 3600, fetch=lambda *a: calls.append(a) or [])
    upscaler_releases.refresh_release_lists(now=1_000_000 + 26 * 3600, fetch=lambda *a: calls.append(a) or [])
    assert len(calls) == 1


def test_a_tool_that_is_not_installed_is_never_asked_about(home, fresh_checks):  # noqa: F811
    calls = []
    assert upscaler_releases.refresh_release_lists(fetch=lambda *a: calls.append(a) or []) == []
    assert calls == []


def test_an_unreachable_github_keeps_the_list_there_was(home, release, fresh_checks):  # noqa: F811
    _list_releases((helixsr.HELIXSR_TAG, False))
    before = (helixsr.helixsr_root() / "releases.json").read_text()
    assert upscaler_releases.refresh_release_lists(fetch=lambda *a: None) == []
    assert (helixsr.helixsr_root() / "releases.json").read_text() == before


def test_only_githubs_api_over_https_is_read():
    assert upscaler_releases._fetch("http://api.github.com/repos/x", 10) is None
    assert upscaler_releases._fetch("https://example.com/releases", 10) is None


def test_an_odd_literal_in_a_downloaded_bridge_is_skipped(tmp_path, monkeypatch):
    from bc250cc.infrastructure import helixsr as module

    bridge = tmp_path / module.HELIXSR_BRIDGE
    bridge.parent.mkdir(parents=True, exist_ok=True)
    bridge.write_text("BAD = {[1]: 2}\nGOOD = ('c', 'full')\n", encoding="utf-8")
    monkeypatch.setattr(module, "helixsr_directory", lambda: tmp_path)
    module._BRIDGE_LITERALS.clear()
    assert module._bridge_constant("BAD") is None
    assert module._bridge_constant("GOOD") == ("c", "full")
