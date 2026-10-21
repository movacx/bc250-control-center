"""HelixSR Scaler: HelixSR 2.0's own OptiScaler, driven through its bridge.

The bridge is the command line HelixSR's app uses: Control Center hands it a
Steam game and keeps its own short record, so the games table can show the
state without scanning every library on each refresh. A game has one
OptiScaler and one HelixSR: Scaler never goes over OptiScaler Client's, nor
next to HelixSR added another way.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bc250cc.infrastructure import helixsr
from frontends.desktop.components.dashboard_widgets import game_matrix_rows
from tests.desktop.gpu.test_helixsr import _release_2, _steam_game, home  # noqa: F401 - fixture

FAKE_BRIDGE = r'''
import json, os, pathlib, sys
argv = sys.argv[1:]
release, command = pathlib.Path(argv[0]), argv[1]
with open(release / "bridge.log", "a", encoding="utf-8") as log:
    log.write(json.dumps(argv[1:]) + "\n")
args = dict(zip(argv[2::2], argv[3::2]))
if os.environ.get("FAKE_BRIDGE_ERROR"):
    print(json.dumps({"ok": False, "error": os.environ["FAKE_BRIDGE_ERROR"]}))
    sys.exit(1)
game = pathlib.Path(args.get("--game", "."))
exe = game / "Bin"
name = os.environ.get("FAKE_SCALER_DLL", "dxgi.dll")
if command == "install":
    exe.mkdir(exist_ok=True)
    (exe / "HelixSR-Scaler.files").write_text("dxgi.dll\n")
    fg = args.get("--fg", "off")
elif command == "scaler-fg":
    fg = "on" if args.get("--on") == "true" else "off"
elif command == "remove":
    (exe / "HelixSR-Scaler.files").unlink()
    print(json.dumps({"ok": True, "game": {"installed": None}, "messages": []}))
    sys.exit(0)
else:
    fg = "off"
options = None if name == "dxgi.dll" else f'WINEDLLOVERRIDES="{name[:-4]}=n,b" %command%'
print("a line the bridge's caller must skip")
print(json.dumps({"ok": True, "messages": ["done"], "game": {
    "exe_folder": str(exe), "scaler_dll": name, "frame_generation": fg, "fg_possible": True,
    "launch_options": options, "version": "2.0.0"}}))
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


def _fg_built(directory: Path) -> None:
    folder = directory / helixsr.HELIXSR_BUILD_FOLDER / helixsr.HELIXSR_FG_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "_nvngx.dll").write_bytes(b"ngx")


# ------------------------------------------------------------ availability


def test_a_release_before_2_0_offers_no_scaler(home):  # noqa: F811
    from tests.desktop.gpu.test_helixsr import _ready

    _ready(home)
    assert not helixsr.helixsr_scaler_supported()
    assert helixsr.helixsr_scaler_rows() == []
    assert helixsr.helixsr_state(machine="x86_64")["scaler_supported"] is False


def test_every_steam_game_can_be_offered_scaler(home, release):  # noqa: F811
    _steam_game(home, "100", "Space Game", {"Bin": ("game.exe",)})

    state = helixsr.helixsr_state(machine="x86_64")

    assert state["scaler_supported"] is True and state["fg_ready"] is False
    assert [(row["appid"], row["state"]) for row in state["scaler_games"]] == [("100", "available")]


# ------------------------------------------------------------ install / remove


def test_scaler_goes_in_through_the_bridge_and_is_recorded(home, release, monkeypatch):  # noqa: F811
    install = _steam_game(home, "100", "Space Game", {"Bin": ("game.exe",)})
    overrides = []
    monkeypatch.setattr(helixsr, "add_dll_override", lambda *args: overrides.append(args))

    result = helixsr.install_helixsr_scaler("100")

    assert result["game"] == "Space Game" and result["frame_generation"] == "off"
    assert _calls(release) == [[
        "install", "--game", str(install), "--way", "scaler",
        "--scaler", str(release / helixsr.HELIXSR_SCALER), "--fg", "off",
    ]]
    assert overrides == [], "Proton loads dxgi.dll from the game folder by itself"
    rows = helixsr.helixsr_state(machine="x86_64")["scaler_games"]
    assert [(row["appid"], row["state"]) for row in rows] == [("100", "installed")]
    assert helixsr.helixsr_state(machine="x86_64")["installed_games"] == 1


def test_another_dll_name_gets_steams_override(home, release, monkeypatch):  # noqa: F811
    _steam_game(home, "100", "Space Game", {"Bin": ("game.exe",)})
    monkeypatch.setenv("FAKE_SCALER_DLL", "winmm.dll")
    overrides = []
    monkeypatch.setattr(helixsr, "add_dll_override", lambda appid, dll: overrides.append((appid, dll)))

    result = helixsr.install_helixsr_scaler("100")

    assert overrides == [("100", "winmm")] and result["launch_option_added"]


def test_a_steam_that_is_running_leaves_the_option_to_the_user(home, release, monkeypatch):  # noqa: F811
    _steam_game(home, "100", "Space Game", {"Bin": ("game.exe",)})
    monkeypatch.setenv("FAKE_SCALER_DLL", "winmm.dll")

    def running(*_args):
        raise RuntimeError("Close Steam completely first")

    monkeypatch.setattr(helixsr, "add_dll_override", running)

    result = helixsr.install_helixsr_scaler("100")

    assert not result["launch_option_added"]
    assert "Close Steam" in result["launch_option_error"]
    assert result["launch_options"] == 'WINEDLLOVERRIDES="winmm=n,b" %command%'


def test_removal_goes_through_the_bridge_and_forgets_the_game(home, release):  # noqa: F811
    install = _steam_game(home, "100", "Space Game", {"Bin": ("game.exe",)})
    helixsr.install_helixsr_scaler("100")

    assert helixsr.remove_helixsr_scaler("100") == {"game": "Space Game"}

    assert _calls(release)[-1] == ["remove", "--game", str(install)]
    assert helixsr._scaler_records() == {}


def test_a_game_whose_files_were_put_back_is_forgotten_without_the_bridge(home, release):  # noqa: F811
    install = _steam_game(home, "100", "Space Game", {"Bin": ("game.exe",)})
    helixsr.install_helixsr_scaler("100")
    (install / "Bin" / helixsr.SCALER_FILES).unlink()  # Steam's file check

    assert helixsr.helixsr_scaler_rows()[0]["state"] == "restored"
    helixsr.remove_helixsr_scaler("100")
    assert [call[0] for call in _calls(release)] == ["install"]


def test_the_bridges_own_error_reaches_the_user(home, release, monkeypatch):  # noqa: F811
    _steam_game(home, "100", "Space Game", {"Bin": ("game.exe",)})
    monkeypatch.setenv("FAKE_BRIDGE_ERROR", "Space Game has anti-cheat (EasyAntiCheat)")

    with pytest.raises(RuntimeError, match="anti-cheat"):
        helixsr.install_helixsr_scaler("100")
    assert helixsr._scaler_records() == {}


# ------------------------------------------------------------ one of each per game


def test_scaler_never_goes_over_optiscaler_clients_optiscaler(home, release):  # noqa: F811
    install = _steam_game(home, "100", "Space Game", {"Bin": ("game.exe",)})
    (install / "Bin" / helixsr.OPTISCALER_INI).write_text("[Upscalers]\n")

    with pytest.raises(RuntimeError, match="already has OptiScaler"):
        helixsr.install_helixsr_scaler("100")
    assert _calls(release) == []


def test_scaler_never_goes_next_to_the_fsr_drop_in(home, release):  # noqa: F811
    _steam_game(home, "100", "Space Game", {"Bin": (helixsr.UPSCALER_DLL,)})
    helixsr.install_helixsr_game("100")

    with pytest.raises(RuntimeError, match="FSR drop-in"):
        helixsr.install_helixsr_scaler("100")


# ------------------------------------------------------------ frame generation


def test_frame_generation_needs_it_built_first(home, release):  # noqa: F811
    _steam_game(home, "100", "Space Game", {"Bin": ("game.exe",)})
    with pytest.raises(RuntimeError, match="Build HelixSR's frame generation first"):
        helixsr.install_helixsr_scaler("100", frame_generation=True)
    helixsr.install_helixsr_scaler("100")
    with pytest.raises(RuntimeError, match="Build HelixSR's frame generation first"):
        helixsr.set_helixsr_scaler_frame_generation("100", True)


def test_frame_generation_is_switched_per_game(home, release):  # noqa: F811
    install = _steam_game(home, "100", "Space Game", {"Bin": ("game.exe",)})
    _fg_built(release)
    helixsr.install_helixsr_scaler("100")

    assert helixsr.set_helixsr_scaler_frame_generation("100", True)["frame_generation"] == "on"
    assert _calls(release)[-1] == ["scaler-fg", "--game", str(install), "--on", "true"]
    assert helixsr.helixsr_scaler_rows()[0]["frame_generation"] is True
    assert helixsr.set_helixsr_scaler_frame_generation("100", False)["frame_generation"] == "off"
    # Turning it off never needs the build.
    (release / helixsr.HELIXSR_BUILD_FOLDER / helixsr.HELIXSR_FG_FOLDER / "_nvngx.dll").unlink()
    helixsr.set_helixsr_scaler_frame_generation("100", False)


def test_the_build_asks_the_setup_for_frame_generation_only(home, release):  # noqa: F811
    command = helixsr.build_helixsr_fg_command()

    assert f"setup/helixsr_setup.py {release / helixsr.HELIXSR_BUILD_FOLDER} --dxc" in command
    assert "--fg-only" in command and "--yes" not in command, "the setup asks before each download"
    assert 'rm -rf -- "$bc250_data/wineprefix"' in command
    assert f"{helixsr.HELIXSR_FG_FOLDER}/_nvngx.dll" in command


# ------------------------------------------------------------ the games table


def _scaler(appid="100", state="available", **extra):
    return {"appid": appid, "name": "Space Game", "state": state, "frame_generation": False,
            "fg_possible": None, "launch_options": "", **extra}


def test_a_game_without_helixsr_offers_scaler():
    [row] = game_matrix_rows([], [], helixsr_ready=True, scaler_games=[_scaler()], scaler_ready=True)
    assert row["helixsr"][3] == (("Add HelixSR Scaler", "helixsr_scaler_install:100", True),)


def test_a_game_with_fsr31_offers_both_ways():
    games = [{"appid": "100", "name": "Space Game", "state": "available", "kind": "game", "files": ["/g/a.dll"]}]
    [row] = game_matrix_rows(games, [], helixsr_ready=True, scaler_games=[_scaler()], scaler_ready=True)
    assert [label for label, _action, _enabled in row["helixsr"][3]] == ["Add HelixSR", "Add HelixSR Scaler"]


def test_a_game_with_optiscaler_clients_optiscaler_is_not_offered_scaler():
    fsr4 = [{"appid": "100", "name": "Space Game", "state": "ready"}]
    [row] = game_matrix_rows([], fsr4, helixsr_ready=True, scaler_games=[_scaler()], scaler_ready=True)
    assert row["helixsr"] is None


def test_a_game_with_scaler_shows_it_and_its_frame_generation():
    [row] = game_matrix_rows([], [], helixsr_ready=True, scaler_games=[_scaler(state="installed")],
                             scaler_ready=True, fg_ready=False)
    text, tone, _tooltip, actions = row["helixsr"]
    assert (text, tone) == ("Active via HelixSR Scaler", "green")
    assert actions == (
        ("Turn on frame generation", "helixsr_scaler_fg_on:100", False),
        ("Remove HelixSR Scaler", "helixsr_scaler_remove:100", True),
    )
    [row] = game_matrix_rows([], [], helixsr_ready=True,
                             scaler_games=[_scaler(state="installed", frame_generation=True)],
                             scaler_ready=True, fg_ready=True)
    # The switch, not the text, says frame generation is on.
    assert row["helixsr"][0] == "Active via HelixSR Scaler"
    assert row["helixsr"][3][0] == ("Turn off frame generation", "helixsr_scaler_fg_off:100", True)


def test_nothing_is_offered_while_the_release_cannot_add_scaler():
    rows = game_matrix_rows([], [], helixsr_ready=True, scaler_games=[_scaler()], scaler_ready=False)
    assert rows == []


# ------------------------------------------------------------ the dispatcher


def test_the_repository_routes_every_scaler_action(home, release, tmp_path, monkeypatch):  # noqa: F811
    from tests.desktop.gpu.test_helixsr import _repository

    install = _steam_game(home, "100", "Space Game", {"Bin": ("game.exe",)})
    _fg_built(release)
    repository = _repository(tmp_path)

    assert repository.gestionar_helixsr("scaler_install:100")["game"] == "Space Game"
    assert repository.gestionar_helixsr("scaler_fg_on:100")["frame_generation"] == "on"
    assert repository.gestionar_helixsr("scaler_fg_off:100")["frame_generation"] == "off"
    repository.gestionar_helixsr("scaler_remove:100")
    assert repository.gestionar_helixsr("scaler_install_fg:100")["frame_generation"] == "on"
    assert [call[0] for call in _calls(release)] == ["install", "scaler-fg", "scaler-fg", "remove", "install"]
    assert _calls(release)[-1][-2:] == ["--fg", "on"]
    assert (install / "Bin" / helixsr.SCALER_FILES).is_file()


def test_the_frame_generation_build_opens_in_the_terminal(home, release, tmp_path, monkeypatch):  # noqa: F811
    from tests.desktop.gpu.test_helixsr import _repository

    repository = _repository(tmp_path)
    opened = []
    monkeypatch.setattr(repository, "_abrir_terminal", lambda command, title: opened.append((command, title)) or True)

    repository.gestionar_helixsr("fg")

    assert opened and opened[0][1] == "HelixSR · frame generation" and "--fg-only" in opened[0][0]


def test_a_game_without_dlss_frame_generation_offers_no_switch():
    [row] = game_matrix_rows([], [], helixsr_ready=True,
                             scaler_games=[_scaler(state="installed", fg_possible=False)],
                             scaler_ready=True, fg_ready=True)
    assert row["helixsr"][3] == (("Remove HelixSR Scaler", "helixsr_scaler_remove:100", True),)
