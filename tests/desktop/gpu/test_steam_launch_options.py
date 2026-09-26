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
