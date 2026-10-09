"""The Steam launch option that makes Proton load OptiScaler, set for the user.

A user installed FSR4 through OptiScaler Client, pressed Insert in Hogwarts
Legacy and got nothing: OptiScaler had not been placed in the game, and Steam
had only ``mangohud %command%``. The dashboard now says per game what is
missing and can write the launch option itself -- only with Steam closed,
touching only that game's value, keeping what was there.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bc250cc.infrastructure import bc250_opticlient
from bc250cc.infrastructure.steam_launch_options import (
    SteamConfigError,
    add_dll_override,
    has_dll_override,
    merge_dll_override,
    read_launch_options,
    set_launch_options,
)

LOCALCONFIG = '''"UserLocalConfigStore"
{
\t"Software"
\t{
\t\t"Valve"
\t\t{
\t\t\t"Steam"
\t\t\t{
\t\t\t\t"apps"
\t\t\t\t{
\t\t\t\t\t"990080"
\t\t\t\t\t{
\t\t\t\t\t\t"LastPlayed"\t\t"1790000000"
\t\t\t\t\t\t"LaunchOptions"\t\t"mangohud %command%"
\t\t\t\t\t}
\t\t\t\t\t"814380"
\t\t\t\t\t{
\t\t\t\t\t\t"LastPlayed"\t\t"1780000000"
\t\t\t\t\t}
\t\t\t\t}
\t\t\t}
\t\t}
\t}
\t"friends"
\t{
\t\t"990080"\t\t"not an app block"
\t}
}
'''


@pytest.mark.parametrize("before, after", [
    ("", 'WINEDLLOVERRIDES="dxgi=n,b" %command%'),
    ("mangohud %command%", 'WINEDLLOVERRIDES="dxgi=n,b" mangohud %command%'),
    ("-dx12 -skipintro", 'WINEDLLOVERRIDES="dxgi=n,b" %command% -dx12 -skipintro'),
    ('WINEDLLOVERRIDES="winmm=n,b" %command%', 'WINEDLLOVERRIDES="winmm=n,b;dxgi=n,b" %command%'),
    ('WINEDLLOVERRIDES="dxgi=b" %command%', 'WINEDLLOVERRIDES="dxgi=n,b" %command%'),
    ('WINEDLLOVERRIDES="dxgi=n,b" gamemoderun %command%', 'WINEDLLOVERRIDES="dxgi=n,b" gamemoderun %command%'),
])
def test_the_override_is_merged_with_what_the_user_had(before, after):
    assert merge_dll_override(before, "dxgi") == after
    assert has_dll_override(after, "dxgi")


def test_a_combined_override_entry_counts():
    assert has_dll_override('WINEDLLOVERRIDES="dxgi,dinput8=n,b" %command%', "dxgi")
    assert not has_dll_override('WINEDLLOVERRIDES="dxgi=b" %command%', "dxgi")


def test_only_that_games_value_changes():
    changed = set_launch_options(LOCALCONFIG, "990080", 'WINEDLLOVERRIDES="dxgi=n,b" mangohud %command%')
    assert read_launch_options(changed, "990080") == 'WINEDLLOVERRIDES="dxgi=n,b" mangohud %command%'
    assert '\\"dxgi=n,b\\"' in changed  # Steam's own escaping
    before_lines, after_lines = LOCALCONFIG.splitlines(), changed.splitlines()
    launch_line = next(line for line in before_lines if '"LaunchOptions"' in line)
    assert [a for a, b in zip(before_lines, after_lines) if a != b] == [launch_line]
    # The friends block with the same key is not an app and is left alone.
    assert '"990080"\t\t"not an app block"' in changed


def test_a_missing_value_or_app_is_inserted_where_steam_keeps_it():
    added = set_launch_options(LOCALCONFIG, "814380", 'WINEDLLOVERRIDES="dxgi=n,b" %command%')
    assert read_launch_options(added, "814380") == 'WINEDLLOVERRIDES="dxgi=n,b" %command%'
    fresh = set_launch_options(LOCALCONFIG, "1245620", 'WINEDLLOVERRIDES="dxgi=n,b" %command%')
    assert read_launch_options(fresh, "1245620") == 'WINEDLLOVERRIDES="dxgi=n,b" %command%'
    assert read_launch_options(fresh, "990080") == "mangohud %command%"


def test_a_file_it_cannot_read_is_never_rewritten():
    with pytest.raises(SteamConfigError):
        set_launch_options(LOCALCONFIG[:-3], "990080", "x")
    with pytest.raises(SteamConfigError):
        set_launch_options(LOCALCONFIG.replace('"apps"', "apps [$WIN32]"), "990080", "x")


def _steam_home(tmp_path: Path) -> Path:
    config = tmp_path / ".local/share/Steam/userdata/1094057967/config"
    config.mkdir(parents=True)
    (config / "localconfig.vdf").write_text(LOCALCONFIG, encoding="utf-8")
    return tmp_path


def _proc(tmp_path: Path, *names: str) -> Path:
    proc = tmp_path / "proc"
    for pid, name in enumerate(names, start=100):
        (proc / str(pid)).mkdir(parents=True)
        (proc / str(pid) / "comm").write_text(name + "\n", encoding="utf-8")
    proc.mkdir(exist_ok=True)
    return proc


def test_steam_must_be_closed_and_the_old_file_is_kept(tmp_path):
    home = _steam_home(tmp_path)
    config = home / ".local/share/Steam/userdata/1094057967/config/localconfig.vdf"

    with pytest.raises(RuntimeError, match="Close Steam"):
        add_dll_override("990080", "dxgi", home=home, proc=_proc(tmp_path, "steam", "bash"))
    assert config.read_text(encoding="utf-8") == LOCALCONFIG

    result = add_dll_override("990080", "dxgi", home=home, proc=_proc(tmp_path / "p2", "bash"))
    assert result["changed"][0]["after"] == 'WINEDLLOVERRIDES="dxgi=n,b" mangohud %command%'
    assert read_launch_options(config.read_text(encoding="utf-8"), "990080").startswith("WINEDLLOVERRIDES")
    backups = list(config.parent.glob("localconfig.vdf.bc250-backup-*"))
    assert len(backups) == 1 and backups[0].read_text(encoding="utf-8") == LOCALCONFIG
    # Running it again changes nothing and leaves no second backup.
    assert add_dll_override("990080", "dxgi", home=home, proc=_proc(tmp_path / "p3", "bash"))["changed"] == []


def test_each_game_says_what_is_still_missing(tmp_path, monkeypatch):
    home = _steam_home(tmp_path)
    records = tmp_path / "records"
    records.mkdir()
    game = tmp_path / "steamapps/common/Hogwarts Legacy"
    (game / "Phoenix/Binaries/Win64").mkdir(parents=True)
    (game / "Phoenix/Binaries/Win64/HogwartsLegacy.exe").write_bytes(b"MZ")
    (game / "HogwartsLegacy.exe").write_bytes(b"MZ")  # Unreal's bootstrap, not the game
    (tmp_path / "steamapps/common/Sekiro").mkdir(parents=True)  # no upscaler: not listed
    (records / "games.json").write_text(json.dumps([
        {"Name": "Hogwarts Legacy", "InstallPath": str(game), "AppId": "990080", "ExecutablePath": "", "HasUpscaler": True},
        {"Name": "Sekiro", "InstallPath": str(tmp_path / "steamapps/common/Sekiro"), "AppId": "814380", "HasUpscaler": False},
    ]), encoding="utf-8")
    monkeypatch.setattr(bc250_opticlient, "opticlient_records", lambda: records)

    [entry] = bc250_opticlient.opticlient_games(home=home)
    assert entry["state"] == "not-installed"
    assert entry["suggested_executable"] == "Phoenix/Binaries/Win64/HogwartsLegacy.exe"

    (game / "Phoenix/Binaries/Win64/OptiScaler.ini").write_text("[Upscalers]\n", encoding="utf-8")
    (game / "Phoenix/Binaries/Win64/dxgi.dll").write_bytes(b"MZ")
    [entry] = bc250_opticlient.opticlient_games(home=home)
    assert (entry["state"], entry["adapter"], entry["launch_options"]) == (
        "needs-launch-option", "dxgi.dll", "mangohud %command%",
    )

    add_dll_override("990080", "dxgi", home=home, proc=_proc(tmp_path, "bash"))
    [entry] = bc250_opticlient.opticlient_games(home=home)
    assert entry["state"] == "ready"


def test_a_damaged_profile_is_named_and_left_as_it_was(tmp_path):
    from frontends.desktop.core.error_diagnostics import diagnose_error

    home = _steam_home(tmp_path)
    config = home / ".local/share/Steam/userdata/1094057967/config/localconfig.vdf"
    damaged = LOCALCONFIG[:-3]
    config.write_text(damaged, encoding="utf-8")

    with pytest.raises(SteamConfigError) as raised:
        add_dll_override("990080", "dxgi", home=home, proc=_proc(tmp_path, "bash"))
    assert str(config.resolve()) in str(raised.value)
    assert diagnose_error(str(raised.value)).code == "BC250-CONFIG-001"
    assert config.read_text(encoding="utf-8") == damaged
    assert not list(config.parent.glob("localconfig.vdf.bc250-*"))


@pytest.mark.parametrize(
    ("distribution", "link", "target", "library"),
    [
        # Fedora Atomic (Bazzite, Silverblue, Kinoite): /home and /mnt link into /var.
        ("bazzite-home", "home", "var/home", "home/user/.local/share/Steam"),
        ("bazzite-mnt", "mnt", "var/mnt", "mnt/games/SteamLibrary"),
        # SteamOS: the old SD card mount name links to the labelled one.
        ("steamos-sd", "run/media/mmcblk0p1", "deck/SD", "run/media/mmcblk0p1"),
        # Debian, Ubuntu or Fedora Workstation: a library behind a user symlink.
        ("debian-games", "home/user/Games", "../../data/Games", "home/user/Games/SteamLibrary"),
    ],
)
def test_a_game_behind_a_linked_folder_names_the_real_one(
    tmp_path, monkeypatch, distribution, link, target, library,
):
    root = tmp_path / distribution
    linked = root / link
    real_target = (linked.parent / target)
    real_target.mkdir(parents=True)
    linked.parent.mkdir(parents=True, exist_ok=True)
    linked.symlink_to(target)
    game = root / library / "steamapps/common/Cyberpunk 2077"
    (game / "bin/x64").mkdir(parents=True)
    (game / "bin/x64/Cyberpunk2077.exe").write_bytes(b"MZ")
    records = tmp_path / "records"
    records.mkdir()
    (records / "games.json").write_text(json.dumps([
        {"Name": "Cyberpunk 2077", "InstallPath": str(game), "AppId": "1091500", "HasUpscaler": True},
    ]), encoding="utf-8")
    monkeypatch.setattr(bc250_opticlient, "opticlient_records", lambda: records)

    [entry] = bc250_opticlient.opticlient_games(home=_steam_home(tmp_path))

    assert entry["state"] == "linked-folder"
    assert entry["linked_path"] == str(linked)
    real_library = Path(entry["real_path"])
    assert (real_library / "steamapps/common/Cyberpunk 2077").resolve() == game.resolve()
    assert not any(p.is_symlink() for p in (real_library, *real_library.parents))


def test_a_regular_folder_is_not_flagged(tmp_path, monkeypatch):
    game = tmp_path / "SteamLibrary/steamapps/common/Cyberpunk 2077"
    (game / "bin/x64").mkdir(parents=True)
    records = tmp_path / "records"
    records.mkdir()
    (records / "games.json").write_text(json.dumps([
        {"Name": "Cyberpunk 2077", "InstallPath": str(game), "AppId": "1091500", "HasUpscaler": True},
    ]), encoding="utf-8")
    monkeypatch.setattr(bc250_opticlient, "opticlient_records", lambda: records)

    [entry] = bc250_opticlient.opticlient_games(home=_steam_home(tmp_path))

    assert entry["state"] == "not-installed" and entry["real_path"] == ""


def test_one_game_listed_by_several_paths_is_one_entry(tmp_path, monkeypatch):
    """Seen on a BC-250 with Bazzite: the client had each game twice, as
    /home/... and /var/home/..., and once more added by hand ("Manual_...")
    through ~/.steam/steam. They are one folder, and one row."""
    real = tmp_path / "var/home/user"
    library = real / ".local/share/Steam/steamapps/common"
    racer = library / "Racer"
    racer.mkdir(parents=True)
    (racer / "OptiScaler.ini").write_text("[Upscalers]\n", encoding="utf-8")
    (racer / "dxgi.dll").write_bytes(b"MZ")
    (racer / "racer.exe").write_bytes(b"MZ")
    (library / "Puzzle").mkdir()
    (tmp_path / "home").symlink_to("var/home")
    (real / ".steam").mkdir()
    (real / ".steam/steam").symlink_to(real / ".local/share/Steam")
    linked = tmp_path / "home/user/.local/share/Steam/steamapps/common"
    records = tmp_path / "records"
    records.mkdir()
    (records / "games.json").write_text(json.dumps([
        {"Name": "racer", "AppId": "Manual_1", "InstallPath": str(real / ".steam/steam/steamapps/common/Racer"),
         "HasUpscaler": True},
        {"Name": "Racer", "AppId": "100", "InstallPath": str(linked / "Racer"), "HasUpscaler": True},
        {"Name": "Racer", "AppId": "100", "InstallPath": str(racer), "HasUpscaler": True},
        {"Name": "Puzzle", "AppId": "200", "InstallPath": str(linked / "Puzzle"), "HasUpscaler": True},
        {"Name": "Puzzle", "AppId": "200", "InstallPath": str(library / "Puzzle"), "HasUpscaler": True},
    ]), encoding="utf-8")
    monkeypatch.setattr(bc250_opticlient, "opticlient_records", lambda: records)

    games = bc250_opticlient.opticlient_games(home=_steam_home(tmp_path / "steam-home"))

    assert [(game["appid"], game["name"]) for game in games] == [("100", "Racer"), ("200", "Puzzle")]
    assert games[0]["adapter"] == "dxgi.dll" and games[0]["path"] == str(racer.resolve())
    # The client takes the real folder; the copy through /home would be refused.
    assert games[1]["state"] == "not-installed"


def test_optiscaler_is_found_by_its_ini_when_the_game_has_no_executable(tmp_path, monkeypatch):
    """Seen on a BC-250: an Unreal game whose Binaries/Win64 held OptiScaler
    but no .exe (half installed); the client keeps no executable path."""
    game = tmp_path / "SteamLibrary/steamapps/common/Wukong"
    win64 = game / "b1/Binaries/Win64"
    (win64 / "OptiScaler").mkdir(parents=True)
    (win64 / "OptiScaler/OptiScaler.ini").write_text("not this one\n", encoding="utf-8")
    (win64 / "OptiScaler.ini").write_text("[Upscalers]\n", encoding="utf-8")
    (win64 / "dxgi.dll").write_bytes(b"MZ")
    records = tmp_path / "records"
    records.mkdir()
    (records / "games.json").write_text(json.dumps([
        {"Name": "Wukong", "AppId": "2358720", "InstallPath": str(game), "HasUpscaler": True},
    ]), encoding="utf-8")
    monkeypatch.setattr(bc250_opticlient, "opticlient_records", lambda: records)

    [entry] = bc250_opticlient.opticlient_games(home=_steam_home(tmp_path / "steam-home"))

    assert (entry["adapter"], entry["location"]) == ("dxgi.dll", "b1/Binaries/Win64")
    assert entry["state"] == "needs-launch-option"


def test_every_launch_option_is_read_in_one_pass():
    from bc250cc.infrastructure.steam_launch_options import (
        read_all_launch_options,
        read_launch_options,
    )

    options = read_all_launch_options(LOCALCONFIG)
    assert options and all(read_launch_options(LOCALCONFIG, appid) == value for appid, value in options.items())
