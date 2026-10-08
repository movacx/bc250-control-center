"""HelixSR: the pinned release, its network files, and games.

The release is never bundled: it is fetched on the user's PC, checked by
SHA-256 and unpacked unmodified; HelixSR's own setup builds the NVIDIA-derived
network files there. Per game, the FSR 3.1 DLL is kept as ``*.original.dll``
and every change can be undone.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from bc250cc.infrastructure import helixsr
from bc250cc.infrastructure.dependencias_repository import DependenciasRepository

DLL = b"MZ helixsr test dll"
ORIGINAL = b"MZ the game's own FSR 3.1 dll"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr(helixsr, "HELIXSR_DLL_SHA256", _sha(DLL))
    monkeypatch.setattr(helixsr, "HELIXSR_DLL_DIGESTS", frozenset({_sha(DLL)}))
    return tmp_path


def _release(directory: Path, *, network: bool = True) -> None:
    """An installed, verified release (as the install command leaves it)."""
    directory.mkdir(parents=True)
    (directory / helixsr.HELIXSR_DLL).write_bytes(DLL)
    (directory / helixsr.HELIXSR_SETUP).write_text("#!/bin/sh\n", encoding="utf-8")
    (directory / helixsr.HELIXSR_MARKER).write_text(helixsr.HELIXSR_SHA256 + "\n", encoding="ascii")
    (directory / "helixsr.ini").write_text(
        "[Sharpening]\nMode = off\n\n[Forwarding]\nDll =\nUpscalerDll =\n", encoding="utf-8"
    )
    if network:
        for name in helixsr.HELIXSR_NETWORK_FILES:
            (directory / name).write_bytes(b"network:" + name.encode())


def _steam_game(home: Path, appid: str, name: str, folders: dict[str, tuple[str, ...]]) -> Path:
    """A Steam library with one game; ``folders`` maps a subfolder to its FSR DLLs."""
    steam = home / ".local/share/Steam"
    (steam / "userdata/1/config").mkdir(parents=True, exist_ok=True)
    (steam / "steamapps").mkdir(parents=True, exist_ok=True)
    install = steam / "steamapps/common" / name.replace(" ", "")
    (steam / f"steamapps/appmanifest_{appid}.acf").write_text(
        f'"AppState"\n{{\n\t"appid"\t\t"{appid}"\n\t"name"\t\t"{name}"\n'
        f'\t"installdir"\t\t"{install.name}"\n}}\n',
        encoding="utf-8",
    )
    for folder, dlls in folders.items():
        path = install / folder
        path.mkdir(parents=True, exist_ok=True)
        for dll in dlls:
            (path / dll).write_bytes(ORIGINAL + dll.encode())
    return install


# ------------------------------------------------------------------ state


def test_nothing_installed_is_reported_as_such(home):
    state = helixsr.helixsr_state(machine="x86_64")
    assert state["state"] == "not-installed"
    assert state["installer_available"] and not state["installed"]
    assert state["games"] == [] and state["installed_games"] == 0


def test_other_architectures_are_not_offered(home):
    assert helixsr.helixsr_state(machine="aarch64")["installer_available"] is False


def test_a_release_without_network_files_asks_for_them(home):
    _release(helixsr.helixsr_directory(), network=False)
    state = helixsr.helixsr_state(machine="x86_64")
    assert state["state"] == "needs-network"
    assert state["current"] and not state["network_ready"]


def test_a_verified_release_with_network_files_is_ready(home):
    _release(helixsr.helixsr_directory())
    state = helixsr.helixsr_state(machine="x86_64")
    assert state["state"] == "ready" and state["network_ready"]


def test_a_changed_dll_needs_repair(home):
    _release(helixsr.helixsr_directory())
    (helixsr.helixsr_directory() / helixsr.HELIXSR_DLL).write_bytes(b"changed")
    assert helixsr.helixsr_state(machine="x86_64")["state"] == "invalid"


def test_an_older_release_offers_the_update(home):
    _release(helixsr.helixsr_root() / "1.1.0")
    state = helixsr.helixsr_state(machine="x86_64")
    assert state["state"] == "update-available"
    assert state["other_versions"] == ["1.1.0"]


def test_proton_is_found_where_the_setup_looks(home, monkeypatch):
    monkeypatch.setattr(helixsr.shutil, "which", lambda _name: None)
    assert helixsr.wine_available(home) is False
    wine = home / ".local/share/Steam/steamapps/common/Proton 9.0/files/bin/wine"
    wine.parent.mkdir(parents=True)
    wine.write_text("#!/bin/sh\n", encoding="utf-8")
    wine.chmod(0o755)
    assert helixsr.wine_available(home) is True


# ------------------------------------------------------------------ terminal


def test_the_commands_never_ask_for_root_and_never_skip_the_nvidia_question(home):
    for command in (
        helixsr.build_helixsr_install_command(),
        helixsr.build_helixsr_network_command(),
        helixsr.build_helixsr_remove_command(),
    ):
        for word in ("sudo", "pkexec", "doas", "run0", "--yes"):
            assert word not in command
        result = subprocess.run(["bash", "-n"], input=command, text=True, capture_output=True, check=False)
        assert result.returncode == 0, result.stderr
    install = helixsr.build_helixsr_install_command()
    assert helixsr.HELIXSR_URL in install
    assert helixsr.HELIXSR_SHA256 in install
    assert "HELIXSR_FORCE_PORTABLE" in install, "missing numpy must not reach the setup's sudo branch"


def _release_zip(path: Path, *, extra: str = "") -> Path:
    top = helixsr.HELIXSR_TOP
    setup = (
        "#!/usr/bin/env bash\nset -e\n"
        'test "$HELIXSR_FORCE_PORTABLE" = 0 -o "$HELIXSR_FORCE_PORTABLE" = 1\n'
        'printf "%s\\n" "$@" > "$1/.setup-args"\n'
        'if [ "$2" = --dlss ]; then cmp -s "$3" "$HOME/expected-dlss" || exit 9; fi\n'
        'printf weights > "$1/helixsr_weights.bin"\nprintf kernels > "$1/helixsr_kernels.pak"\n'
    )
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr(f"{top}/{helixsr.HELIXSR_DLL}", DLL)
        bundle.writestr(f"{top}/{helixsr.HELIXSR_SETUP}", setup)
        bundle.writestr(f"{top}/setup/lib/model/launch_synth", b"\x7fELF")
        bundle.writestr(f"{top}/LICENSE", "HelixSR Freeware License")
        if extra:
            bundle.writestr(extra, "x")
    return path


def _run_install(home: Path, archive: Path, monkeypatch, *, pin: bool = True) -> subprocess.CompletedProcess:
    if pin:
        monkeypatch.setattr(helixsr, "HELIXSR_SHA256", _sha(archive.read_bytes()))
    bin_dir = home / "bin"
    bin_dir.mkdir(exist_ok=True)
    curl = bin_dir / "curl"
    curl.write_text(
        '#!/bin/sh\nwhile [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift;; esac; shift; done\n'
        f'cp "{archive}" "$out"\n',
        encoding="utf-8",
    )
    wine = bin_dir / "wine"
    wine.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    for tool in (curl, wine):
        tool.chmod(0o755)
    environment = dict(os.environ, HOME=str(home), XDG_DATA_HOME=str(home / "data"),
                       PATH=f"{bin_dir}:{os.environ['PATH']}", TMPDIR=str(home))
    return subprocess.run(
        ["bash", "-c", helixsr.build_helixsr_install_command()],
        env=environment, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60, check=False,
    )


def test_the_install_verifies_unpacks_and_builds_the_network(home, monkeypatch):
    result = _run_install(home, _release_zip(home / "release.zip"), monkeypatch)
    assert result.returncode == 0, result.stdout + result.stderr
    state = helixsr.helixsr_state(machine="x86_64")
    assert state["state"] == "ready", state
    assert os.access(helixsr.helixsr_directory() / "setup/lib/model/launch_synth", os.X_OK)


@pytest.mark.parametrize("entry", ["../escape.txt", "OtherTop/file.txt", f"{helixsr.HELIXSR_TOP}/../x"])
def test_the_install_refuses_entries_outside_the_release_folder(home, monkeypatch, entry):
    result = _run_install(home, _release_zip(home / "release.zip", extra=entry), monkeypatch)
    assert result.returncode != 0
    assert "unexpected archive entry" in result.stdout + result.stderr
    assert not helixsr.helixsr_directory().exists()
    assert not (home / "escape.txt").exists()


def test_the_install_refuses_a_different_archive(home, monkeypatch):
    monkeypatch.setattr(helixsr, "HELIXSR_SHA256", "0" * 64)
    result = _run_install(home, _release_zip(home / "release.zip"), monkeypatch, pin=False)
    assert result.returncode != 0
    assert "FAILED" in result.stdout + result.stderr
    assert not helixsr.helixsr_directory().exists()


def test_the_install_refuses_a_release_with_another_dll(home, monkeypatch):
    monkeypatch.setattr(helixsr, "HELIXSR_DLL_SHA256", "0" * 64)
    result = _run_install(home, _release_zip(home / "release.zip"), monkeypatch)
    assert result.returncode != 0
    assert "not the reviewed one" in result.stdout + result.stderr
    assert not helixsr.helixsr_directory().exists()


# ------------------------------------------------------------------ games


def _ready(home: Path) -> None:
    _release(helixsr.helixsr_directory())


def test_a_scan_finds_fsr31_games_and_prefers_the_upscaler_dll(home):
    _ready(home)
    install = _steam_game(home, "100", "Space Game", {
        "Game/Binaries/Win64": (helixsr.UPSCALER_DLL, helixsr.LOADER_DLL),
        "Engine/Plugins/FSR/Win64": (helixsr.LOADER_DLL,),
    })
    _steam_game(home, "200", "No FSR", {"bin": ("other.dll",)})

    games = helixsr.scan_helixsr_games()

    assert [game["appid"] for game in games] == ["100"]
    assert sorted(games[0]["files"]) == sorted([
        str(install / "Engine/Plugins/FSR/Win64" / helixsr.LOADER_DLL),
        str(install / "Game/Binaries/Win64" / helixsr.UPSCALER_DLL),
    ])
    rows = helixsr.helixsr_state(machine="x86_64")["games"]
    assert [(row["appid"], row["state"]) for row in rows] == [("100", "available")]


def test_adding_and_removing_helixsr_restores_the_game_exactly(home):
    _ready(home)
    install = _steam_game(home, "100", "Space Game", {"Bin": (helixsr.UPSCALER_DLL, helixsr.LOADER_DLL)})
    folder = install / "Bin"
    before = {path.name: path.read_bytes() for path in folder.iterdir()}

    result = helixsr.install_helixsr_game("100")

    assert result["game"] == "Space Game"
    assert (folder / helixsr.UPSCALER_DLL).read_bytes() == DLL
    assert (folder / "amd_fidelityfx_upscaler_dx12.original.dll").read_bytes() == before[helixsr.UPSCALER_DLL]
    assert (folder / helixsr.LOADER_DLL).read_bytes() == before[helixsr.LOADER_DLL]
    for name in helixsr.HELIXSR_NETWORK_FILES:
        assert (folder / name).is_file()
    state = helixsr.helixsr_state(machine="x86_64")
    assert state["installed_games"] == 1
    assert state["games"][0]["state"] == "installed"

    (folder / helixsr.HELIXSR_LOG).write_text("log", encoding="utf-8")
    helixsr.remove_helixsr_game("100")

    assert {path.name: path.read_bytes() for path in folder.iterdir()} == before
    assert helixsr.helixsr_state(machine="x86_64")["installed_games"] == 0


def test_a_game_update_that_puts_its_file_back_is_shown_and_cleaned(home):
    _ready(home)
    install = _steam_game(home, "100", "Space Game", {"Bin": (helixsr.UPSCALER_DLL,)})
    helixsr.install_helixsr_game("100")
    target = install / "Bin" / helixsr.UPSCALER_DLL
    target.write_bytes(b"new game build")

    assert helixsr.helixsr_state(machine="x86_64")["games"][0]["state"] == "restored"
    result = helixsr.remove_helixsr_game("100")

    assert target.read_bytes() == b"new game build"
    assert result["kept"] == [str(install / "Bin/amd_fidelityfx_upscaler_dx12.original.dll")]
    assert not (install / "Bin/helixsr_weights.bin").exists()


def test_a_failure_halfway_puts_every_file_back(home, monkeypatch):
    _ready(home)
    install = _steam_game(home, "100", "Space Game", {
        "A": (helixsr.UPSCALER_DLL,),
        "B": (helixsr.UPSCALER_DLL,),
    })
    before = {path: path.read_bytes() for path in install.rglob("*") if path.is_file()}
    real_copy = helixsr.shutil.copyfile
    calls = []

    def failing_copy(source, destination):
        calls.append(destination)
        if Path(destination).parent.name == "B" and Path(destination).name == "helixsr_kernels.pak":
            raise OSError("disk full")
        return real_copy(source, destination)

    monkeypatch.setattr(helixsr.shutil, "copyfile", failing_copy)
    with pytest.raises(OSError, match="disk full"):
        helixsr.install_helixsr_game("100")

    after = {path: path.read_bytes() for path in install.rglob("*") if path.is_file()}
    assert after == before
    assert helixsr.helixsr_state(machine="x86_64")["installed_games"] == 0


def test_an_earlier_manual_install_is_left_alone(home):
    _ready(home)
    install = _steam_game(home, "100", "Space Game", {"Bin": (helixsr.UPSCALER_DLL,)})
    (install / "Bin/amd_fidelityfx_upscaler_dx12.original.dll").write_bytes(b"old backup")
    with pytest.raises(RuntimeError, match="original.dll backup"):
        helixsr.install_helixsr_game("100")
    (install / "Bin/amd_fidelityfx_upscaler_dx12.original.dll").unlink()
    (install / "Bin" / helixsr.UPSCALER_DLL).write_bytes(DLL)
    with pytest.raises(RuntimeError, match="copied there by hand"):
        helixsr.install_helixsr_game("100")


def test_games_need_the_network_files_first(home):
    _release(helixsr.helixsr_directory(), network=False)
    _steam_game(home, "100", "Space Game", {"Bin": (helixsr.UPSCALER_DLL,)})
    with pytest.raises(RuntimeError, match="build its network files first"):
        helixsr.install_helixsr_game("100")


# ------------------------------------------------------------------ repository


def _repository(tmp_path: Path) -> DependenciasRepository:
    repository = DependenciasRepository()
    repository._tool_dir = lambda: tmp_path
    repository._abrir_terminal = lambda command, title: (title, command)
    return repository


@pytest.mark.parametrize("family", ["ubuntu", "cachyos", "bazzite", "fedora", "opensuse", "steamos"])
def test_every_distribution_gets_the_same_workflow(home, tmp_path, family):
    repository = _repository(tmp_path)
    repository._os_repository = lambda: SimpleNamespace(info=SimpleNamespace(family=family, distro_id=family))

    title, command = repository.gestionar_helixsr("install")

    assert "HelixSR" in title
    assert helixsr.HELIXSR_SHA256 in command


def test_removal_waits_until_no_game_uses_helixsr(home, tmp_path):
    _ready(home)
    _steam_game(home, "100", "Space Game", {"Bin": (helixsr.UPSCALER_DLL,)})
    helixsr.install_helixsr_game("100")
    repository = _repository(tmp_path)

    with pytest.raises(RuntimeError, match="Remove HelixSR from your games first"):
        repository.gestionar_helixsr("uninstall")
    repository.gestionar_helixsr("game_remove:100")
    title, command = repository.gestionar_helixsr("uninstall")
    assert "remove" in title and str(helixsr.helixsr_cache()) in command


def test_the_network_build_needs_the_release(home, tmp_path):
    with pytest.raises(RuntimeError, match="Install HelixSR first"):
        _repository(tmp_path).gestionar_helixsr("network")


def test_unknown_actions_are_refused(home, tmp_path):
    with pytest.raises(ValueError):
        _repository(tmp_path).gestionar_helixsr("format-disk")


def test_a_refused_removal_changes_nothing(home):
    _ready(home)
    install = _steam_game(home, "100", "Space Game", {
        "A": (helixsr.UPSCALER_DLL,),
        "B": (helixsr.UPSCALER_DLL,),
    })
    helixsr.install_helixsr_game("100")
    (install / "B/amd_fidelityfx_upscaler_dx12.original.dll").unlink()
    before = {path: path.read_bytes() for path in install.rglob("*") if path.is_file()}

    with pytest.raises(RuntimeError, match="original FSR file is missing"):
        helixsr.remove_helixsr_game("100")

    assert {path: path.read_bytes() for path in install.rglob("*") if path.is_file()} == before
    assert helixsr.helixsr_state(machine="x86_64")["installed_games"] == 1


def test_games_stay_listed_when_the_release_folder_is_gone(home):
    _ready(home)
    _steam_game(home, "100", "Space Game", {"Bin": (helixsr.UPSCALER_DLL,)})
    helixsr.install_helixsr_game("100")
    helixsr.shutil.rmtree(helixsr.helixsr_directory())

    state = helixsr.helixsr_state(machine="x86_64")

    assert state["state"] == "not-installed"
    assert state["installed_games"] == 1
    helixsr.remove_helixsr_game("100")


# ------------------------------------------------------------------ OptiScaler

OPTISCALER_INI = (
    "; OptiScaler\r\n[Upscalers]\r\nDx11Upscaler=ffx_12\r\nDx12Upscaler=ffx\r\n\r\n"
    "[Libraries]\r\nOptiDllPath=auto\r\nFfxDx12Path=auto\r\nFfxDx12SRPath=auto\r\n\r\n"
    "[Menu]\r\nScale=auto\r\n"
)
FSR4 = b"MZ BC250 FSR4 INT8"


def _optiscaler_game(home: Path, monkeypatch, *, fsr4: bool = True) -> Path:
    """A game as OptiScaler Client leaves it: dxgi.dll, OptiScaler.ini, the FSR4 DLL."""
    config = home / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    install = home / "games" / "Racer"
    root = install / "Bin"
    (root / "OptiScaler").mkdir(parents=True)
    (root / "dxgi.dll").write_bytes(b"MZ optiscaler")
    (root / "OptiScaler.ini").write_bytes(OPTISCALER_INI.encode())
    if fsr4:
        (root / "OptiScaler" / helixsr.UPSCALER_DLL).write_bytes(FSR4)
    records = config / "OptiscalerClient-BC250"
    records.mkdir(parents=True)
    (records / "games.json").write_text(
        '[{"Name": "Racer", "AppId": "300", "InstallPath": "%s"}]' % install, encoding="utf-8"
    )
    monkeypatch.setattr(helixsr, "_optiscaler_games", lambda: [
        {"appid": "300", "name": "Racer", "adapter": "dxgi.dll", "location": "Bin"}
    ])
    return root


def test_optiscaler_games_are_offered_once_helixsr_is_ready(home, monkeypatch):
    _optiscaler_game(home, monkeypatch)
    assert helixsr.helixsr_state(machine="x86_64")["games"] == []
    _ready(home)
    rows = helixsr.helixsr_state(machine="x86_64")["games"]
    assert [(row["kind"], row["appid"], row["state"]) for row in rows] == [("optiscaler", "300", "available")]


def test_optiscaler_is_pointed_at_helixsr_and_keeps_fsr4_selectable(home, monkeypatch):
    _ready(home)
    root = _optiscaler_game(home, monkeypatch)

    result = helixsr.install_helixsr_optiscaler("300")

    assert result == {"game": "Racer", "fsr4": True}
    folder = root / "HelixSR"
    assert (folder / helixsr.LOADER_DLL).read_bytes() == DLL
    assert (folder / helixsr.UPSCALER_DLL).read_bytes() == DLL
    assert (folder / helixsr.SECOND_UPSCALER).read_bytes() == FSR4
    for name in helixsr.HELIXSR_NETWORK_FILES:
        assert (folder / name).is_file()
    settings = (folder / "helixsr.ini").read_text(encoding="utf-8")
    assert helixsr._ini_get(settings, "Forwarding", "UpscalerDll") == helixsr.SECOND_UPSCALER
    text = (root / "OptiScaler.ini").read_bytes().decode()
    assert "\r\n" in text and "\n[" not in text.replace("\r\n", "")
    assert helixsr._ini_get(text, "Upscalers", "Dx12Upscaler") == "ffx"
    expected = "Z:" + str(folder).replace("/", "\\")
    assert helixsr._ini_get(text, "Libraries", "FfxDx12SRPath") == expected + "\\" + helixsr.UPSCALER_DLL
    assert helixsr._ini_get(text, "Libraries", "FfxDx12Path") == expected + "\\" + helixsr.LOADER_DLL
    assert helixsr._ini_get(text, "Menu", "Scale") == "auto"
    assert (root / "OptiScaler" / helixsr.UPSCALER_DLL).read_bytes() == FSR4, "the client's files stay as they are"
    state = helixsr.helixsr_state(machine="x86_64")
    assert [(row["kind"], row["state"]) for row in state["games"]] == [("optiscaler", "installed")]
    assert state["installed_games"] == 1


def test_removal_puts_optiscaler_ini_back_byte_for_byte(home, monkeypatch):
    _ready(home)
    root = _optiscaler_game(home, monkeypatch)
    helixsr.install_helixsr_optiscaler("300")

    result = helixsr.remove_helixsr_optiscaler("300")

    assert result["restored"] == "exact"
    assert (root / "OptiScaler.ini").read_bytes() == OPTISCALER_INI.encode()
    assert not (root / "HelixSR").exists()
    assert helixsr.helixsr_state(machine="x86_64")["installed_games"] == 0


def test_settings_changed_in_optiscaler_since_are_kept_on_removal(home, monkeypatch):
    _ready(home)
    root = _optiscaler_game(home, monkeypatch)
    helixsr.install_helixsr_optiscaler("300")
    ini = root / "OptiScaler.ini"
    ini.write_bytes(ini.read_bytes().replace(b"Scale=auto", b"Scale=1.5"))

    assert helixsr.remove_helixsr_optiscaler("300")["restored"] == "settings"

    text = ini.read_bytes().decode()
    assert helixsr._ini_get(text, "Menu", "Scale") == "1.5"
    assert helixsr._ini_get(text, "Libraries", "FfxDx12SRPath") == "auto"
    assert helixsr._ini_get(text, "Libraries", "FfxDx12Path") == "auto"


def test_a_client_restore_is_shown_and_left_alone(home, monkeypatch):
    _ready(home)
    root = _optiscaler_game(home, monkeypatch)
    helixsr.install_helixsr_optiscaler("300")
    (root / "OptiScaler.ini").write_bytes(OPTISCALER_INI.encode())

    assert helixsr.helixsr_state(machine="x86_64")["games"][0]["state"] == "restored"
    assert helixsr.remove_helixsr_optiscaler("300")["restored"] == "kept"
    assert (root / "OptiScaler.ini").read_bytes() == OPTISCALER_INI.encode()
    assert not (root / "HelixSR").exists()


def test_without_the_fsr4_dll_helixsr_is_the_only_upscaler(home, monkeypatch):
    _ready(home)
    root = _optiscaler_game(home, monkeypatch, fsr4=False)
    assert helixsr.install_helixsr_optiscaler("300")["fsr4"] is False
    assert not (root / "HelixSR" / helixsr.SECOND_UPSCALER).exists()
    settings = (root / "HelixSR" / "helixsr.ini").read_text(encoding="utf-8")
    assert helixsr._ini_get(settings, "Forwarding", "UpscalerDll") == ""


def test_a_foreign_helixsr_folder_is_never_overwritten(home, monkeypatch):
    _ready(home)
    root = _optiscaler_game(home, monkeypatch)
    (root / "HelixSR").mkdir()
    (root / "HelixSR" / "mine.txt").write_text("user", encoding="utf-8")
    with pytest.raises(RuntimeError, match="HelixSR folder"):
        helixsr.install_helixsr_optiscaler("300")
    assert (root / "OptiScaler.ini").read_bytes() == OPTISCALER_INI.encode()
    assert (root / "HelixSR" / "mine.txt").read_text(encoding="utf-8") == "user"


def test_a_failure_halfway_leaves_optiscaler_untouched(home, monkeypatch):
    _ready(home)
    root = _optiscaler_game(home, monkeypatch)
    monkeypatch.setattr(helixsr, "_write_json", lambda *_args: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        helixsr.install_helixsr_optiscaler("300")
    assert (root / "OptiScaler.ini").read_bytes() == OPTISCALER_INI.encode()
    assert not (root / "HelixSR").exists()


def test_a_running_game_is_refused(tmp_path):
    proc = tmp_path / "proc"
    (proc / "4242").mkdir(parents=True)
    game = tmp_path / "games" / "Racer"
    (proc / "4242" / "cmdline").write_bytes(
        b"/proton\0waitforexitandrun\0Z:" + str(game / "Bin" / "Racer.exe").replace("/", "\\").encode()
    )
    with pytest.raises(RuntimeError, match="Close this game"):
        helixsr._refuse_running(game, proc=proc)
    helixsr._refuse_running(tmp_path / "games" / "Other", proc=proc)


def test_the_repository_routes_optiscaler_actions(home, tmp_path, monkeypatch):
    _ready(home)
    root = _optiscaler_game(home, monkeypatch)
    repository = _repository(tmp_path)
    assert repository.gestionar_helixsr("opti_install:300")["game"] == "Racer"
    repository.gestionar_helixsr("opti_remove:300")
    assert (root / "OptiScaler.ini").read_bytes() == OPTISCALER_INI.encode()


# ------------------------------------------------------------------ updating games

NEW_DLL = b"MZ helixsr next release"


def _age_records(path: Path) -> None:
    """Mark every recorded game as given the release before this one."""
    import json

    records = json.loads(path.read_text(encoding="utf-8"))
    for record in records.values():
        record["version"] = "1.2.0"
    path.write_text(json.dumps(records), encoding="utf-8")


def _next_release(monkeypatch) -> None:
    """The release folder now holds a newer DLL and rebuilt network files."""
    directory = helixsr.helixsr_directory()
    (directory / helixsr.HELIXSR_DLL).write_bytes(NEW_DLL)
    for name in helixsr.HELIXSR_NETWORK_FILES:
        (directory / name).write_bytes(b"rebuilt:" + name.encode())
    monkeypatch.setattr(helixsr, "HELIXSR_DLL_SHA256", _sha(NEW_DLL))
    monkeypatch.setattr(helixsr, "HELIXSR_DLL_DIGESTS", frozenset({_sha(DLL), _sha(NEW_DLL)}))


def test_the_release_pins_the_new_dll_and_still_knows_the_previous_one():
    assert helixsr.HELIXSR_VERSION == "1.3.0"
    assert helixsr.HELIXSR_DLL_SHA256 in helixsr.HELIXSR_DLL_DIGESTS
    assert "745477ee77c5cccd2de4bd251fc950d33895387f411815e889625fbbdc12a7e4" in helixsr.HELIXSR_DLL_DIGESTS


def test_a_game_given_an_earlier_release_is_updated_in_place(home, monkeypatch):
    _ready(home)
    install = _steam_game(home, "100", "Space Game", {"Bin": (helixsr.UPSCALER_DLL,)})
    folder = install / "Bin"
    original = (folder / helixsr.UPSCALER_DLL).read_bytes()
    helixsr.install_helixsr_game("100")
    _age_records(helixsr._records_path())
    _next_release(monkeypatch)
    assert helixsr.helixsr_state(machine="x86_64")["games"][0]["outdated"] is True

    result = helixsr.update_helixsr_game("100")

    assert result == {"game": "Space Game", "version": helixsr.HELIXSR_VERSION}
    assert (folder / helixsr.UPSCALER_DLL).read_bytes() == NEW_DLL
    for name in helixsr.HELIXSR_NETWORK_FILES:
        assert (folder / name).read_bytes() == b"rebuilt:" + name.encode()
    assert (folder / "amd_fidelityfx_upscaler_dx12.original.dll").read_bytes() == original
    assert not any(path.name.endswith(".bc250-helixsr") for path in folder.iterdir())
    assert helixsr.helixsr_state(machine="x86_64")["games"][0]["outdated"] is False
    helixsr.remove_helixsr_game("100")
    assert sorted(path.name for path in folder.iterdir()) == [helixsr.UPSCALER_DLL]
    assert (folder / helixsr.UPSCALER_DLL).read_bytes() == original


def test_an_update_is_refused_when_the_game_put_its_own_file_back(home, monkeypatch):
    _ready(home)
    install = _steam_game(home, "100", "Space Game", {"Bin": (helixsr.UPSCALER_DLL,)})
    helixsr.install_helixsr_game("100")
    _age_records(helixsr._records_path())
    _next_release(monkeypatch)
    (install / "Bin" / helixsr.UPSCALER_DLL).write_bytes(ORIGINAL)
    before = {path.name: path.read_bytes() for path in (install / "Bin").iterdir()}

    with pytest.raises(RuntimeError, match="put its own FSR file back"):
        helixsr.update_helixsr_game("100")

    assert {path.name: path.read_bytes() for path in (install / "Bin").iterdir()} == before


def test_an_optiscaler_route_is_updated_and_its_settings_are_kept(home, monkeypatch):
    _ready(home)
    root = _optiscaler_game(home, monkeypatch)
    repository = _repository(home / "repo")
    repository.gestionar_helixsr("opti_install:300")
    _age_records(helixsr._optiscaler_path() / "games.json")
    _next_release(monkeypatch)
    folder = root / "HelixSR"
    settings = (folder / "helixsr.ini").read_bytes()
    ini = (root / "OptiScaler.ini").read_bytes()

    assert repository.gestionar_helixsr("game_update:300")["game"] == "Racer"

    assert (folder / helixsr.LOADER_DLL).read_bytes() == NEW_DLL
    assert (folder / helixsr.UPSCALER_DLL).read_bytes() == NEW_DLL
    assert (folder / helixsr.SECOND_UPSCALER).read_bytes() == FSR4
    for name in helixsr.HELIXSR_NETWORK_FILES:
        assert (folder / name).read_bytes() == b"rebuilt:" + name.encode()
    assert (folder / "helixsr.ini").read_bytes() == settings
    assert (root / "OptiScaler.ini").read_bytes() == ini
    rows = helixsr.helixsr_state(machine="x86_64")["games"]
    assert [(row["state"], row["outdated"]) for row in rows] == [("installed", False)]
    repository.gestionar_helixsr("opti_remove:300")
    assert (root / "OptiScaler.ini").read_bytes() == OPTISCALER_INI.encode()


def test_an_update_needs_the_network_files_and_a_recorded_game(home):
    with pytest.raises(RuntimeError, match="build its network files first"):
        helixsr.update_helixsr_game("100")
    _ready(home)
    with pytest.raises(RuntimeError, match="not recorded"):
        helixsr.update_helixsr_game("100")


# ------------------------------------------------------------------ local DLSS DLL

DLSS = b"MZ nvngx_dlss 310.7.0"


def _client_dlss(home: Path, monkeypatch, data: bytes) -> Path:
    """OptiScaler Client's payload copy of NVIDIA's DLSS DLL."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "config"))
    monkeypatch.setattr(helixsr, "DLSS_DLL_SHA256", _sha(DLSS))
    payload = home / "config" / "OptiscalerClient-BC250" / "BC250" / "payload" / "nvngx_dlss.dll"
    payload.parent.mkdir(parents=True)
    payload.write_bytes(data)
    (home / "expected-dlss").write_bytes(DLSS)
    return payload


def _setup_args() -> list[str]:
    return (helixsr.helixsr_directory() / ".setup-args").read_text(encoding="utf-8").split()


def test_the_client_copy_of_dlss_spares_the_nvidia_download(home, monkeypatch):
    payload = _client_dlss(home, monkeypatch, DLSS)
    assert helixsr.helixsr_state(machine="x86_64")["local_dlss"] is True

    result = _run_install(home, _release_zip(home / "release.zip"), monkeypatch)

    assert result.returncode == 0, result.stdout + result.stderr
    args = _setup_args()
    assert args[1] == "--dlss" and args[2] != str(payload), "a private, verified copy is handed over"
    assert "Nothing is downloaded from NVIDIA" in result.stdout
    assert payload.read_bytes() == DLSS, "the client's own file stays untouched"
    assert not Path(args[2]).exists(), "the private copy is removed afterwards"


def test_a_changed_client_copy_is_skipped_and_the_setup_asks_as_usual(home, monkeypatch):
    _client_dlss(home, monkeypatch, b"MZ some other dll")

    result = _run_install(home, _release_zip(home / "release.zip"), monkeypatch)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "--dlss" not in _setup_args()
    assert "is not NVIDIA's DLSS 310.7.0 DLL" in result.stdout
    assert "The setup asks before it downloads" in result.stdout


def test_without_the_client_the_setup_asks_before_downloading(home, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "config"))
    assert helixsr.helixsr_state(machine="x86_64")["local_dlss"] is False
    result = _run_install(home, _release_zip(home / "release.zip"), monkeypatch)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _setup_args() == [str(helixsr.helixsr_directory())]


# ------------------------------------------------------- games outside Steam


def _loose_game(home: Path, name: str = "Loose Game") -> Path:
    """A game in a folder of its own, unknown to Steam (GOG, Heroic, by hand)."""
    folder = home / "Games" / name / "bin"
    folder.mkdir(parents=True)
    (folder / helixsr.UPSCALER_DLL).write_bytes(ORIGINAL)
    return home / "Games" / name


def test_a_folder_outside_steam_is_listed_and_handled_like_a_steam_game(home, tmp_path):
    _ready(home)
    game = _loose_game(home)
    dll = game / "bin" / helixsr.UPSCALER_DLL
    repository = _repository(tmp_path)

    added = repository.gestionar_helixsr(f"add_folder:{game}")

    key = added["id"]
    assert key.startswith(helixsr.FOLDER_PREFIX) and added["game"] == "Loose Game"
    rows = helixsr.helixsr_state(machine="x86_64")["games"]
    assert [(row["appid"], row["state"], row["folder"]) for row in rows] == [
        (key, "available", str(game))
    ]

    repository.gestionar_helixsr(f"game_install:{key}")
    assert dll.read_bytes() == DLL
    assert (dll.parent / "amd_fidelityfx_upscaler_dx12.original.dll").read_bytes() == ORIGINAL
    assert helixsr.helixsr_state(machine="x86_64")["games"][0]["state"] == "installed"

    with pytest.raises(RuntimeError, match="Remove HelixSR from this game first"):
        repository.gestionar_helixsr(f"forget_folder:{key}")
    repository.gestionar_helixsr(f"game_remove:{key}")
    assert dll.read_bytes() == ORIGINAL
    assert not (dll.parent / "amd_fidelityfx_upscaler_dx12.original.dll").exists()

    repository.gestionar_helixsr(f"forget_folder:{key}")
    assert helixsr.helixsr_state(machine="x86_64")["games"] == []


def test_a_folder_path_keeps_its_case(home, tmp_path):
    _ready(home)
    game = _loose_game(home, "Mixed Case GAME")
    added = _repository(tmp_path).gestionar_helixsr(f"add_folder:{game}")
    assert helixsr.helixsr_state(machine="x86_64")["games"][0]["folder"] == str(game)
    assert added["game"] == "Mixed Case GAME"


def test_a_folder_without_fsr31_is_refused(home):
    folder = home / "Games" / "Other"
    folder.mkdir(parents=True)
    (folder / "game.exe").write_bytes(b"MZ")
    with pytest.raises(RuntimeError, match="No FSR 3.1 DLL"):
        helixsr.add_helixsr_folder(str(folder))
    assert helixsr.helixsr_state(machine="x86_64")["games"] == []


@pytest.mark.parametrize("which", ["home", "root", "missing", "relative"])
def test_only_a_real_game_folder_is_taken(home, which):
    path = {
        "home": str(home),
        "root": "/",
        "missing": str(home / "nowhere"),
        "relative": "Games/Loose",
    }[which]
    with pytest.raises(RuntimeError):
        helixsr.add_helixsr_folder(path)


def test_a_folder_that_was_deleted_leaves_the_list(home):
    _ready(home)
    game = _loose_game(home)
    helixsr.add_helixsr_folder(str(game))
    (game / "bin" / helixsr.UPSCALER_DLL).unlink()
    assert helixsr.helixsr_state(machine="x86_64")["games"] == []


# ------------------------------------------------------------------ settings

RELEASE_INI = (
    "; helixsr.ini - optional\n\n[Sharpening]\n; off = never sharpen\nMode = off\nSharpness = 0.3\n"
    "MotionAdaptive = true\n\n[Upscaling]\nNetworkResolution = auto\n\n[ModelE]\nNetwork = auto\n"
    "MotionVectorFrontEnd = false\n\n[Forwarding]\nDll =\nUpscalerDll =\n"
)


FULL_INI = RELEASE_INI.replace(
    "MotionVectorFrontEnd = false\n",
    "MotionVectorFrontEnd = false\nUseReactiveMask = false\nDilateDisplayMotionVectors = false\n"
    "InvertJitter = false\nInvertMotionVectors = false\n\n[Log]\nEnabled = true\n\n"
    "[Compatibility]\nWaveSize = auto\n",
)


def test_defaults_leave_the_release_ini_exactly_as_it_is():
    assert helixsr._settings_text(FULL_INI, helixsr.helixsr_defaults()) == FULL_INI
    text = helixsr._settings_text(RELEASE_INI, {**helixsr.helixsr_defaults(), "Sharpening.Mode": "override",
                                                "Compatibility.WaveSize": "32"})
    assert "; off = never sharpen\nMode = override\n" in text, "the comments stay"
    assert helixsr._ini_get(text, "Compatibility", "WaveSize") == "32", "a missing section is added"
    assert helixsr._ini_get(text, "ModelE", "MotionVectorFrontEnd") == "false", "unknown keys are kept"


def test_settings_are_validated_and_saved(home):
    assert helixsr.helixsr_settings() == helixsr.helixsr_defaults()
    result = helixsr.save_helixsr_settings({"Sharpening.Sharpness": "0.55", "Log.Enabled": False})
    assert result == {"settings": helixsr.helixsr_settings(), "games": 0, "skipped": []}
    assert helixsr.helixsr_settings()["Sharpening.Sharpness"] == 0.55
    assert helixsr.helixsr_settings()["Log.Enabled"] is False
    for bad in ({"Sharpening.Mode": "max"}, {"Sharpening.Sharpness": 2}, {"Log.Enabled": "maybe"}):
        with pytest.raises(ValueError, match="Invalid HelixSR settings"):
            helixsr.save_helixsr_settings(bad)
    assert helixsr.helixsr_settings()["Sharpening.Sharpness"] == 0.55, "a refused save changes nothing"


def test_a_new_game_gets_the_settings_and_loses_them_on_removal(home):
    _ready(home)
    (helixsr.helixsr_directory() / "helixsr.ini").write_text(RELEASE_INI, encoding="utf-8")
    helixsr.save_helixsr_settings({"Upscaling.NetworkResolution": "fast"})
    install = _steam_game(home, "100", "Space Game", {"Bin": (helixsr.UPSCALER_DLL,)})
    folder = install / "Bin"
    before = {path.name: path.read_bytes() for path in folder.iterdir()}

    helixsr.install_helixsr_game("100")

    text = (folder / "helixsr.ini").read_text(encoding="utf-8")
    assert helixsr._ini_get(text, "Upscaling", "NetworkResolution") == "fast"
    assert "; off = never sharpen" in text
    helixsr.remove_helixsr_game("100")
    assert {path.name: path.read_bytes() for path in folder.iterdir()} == before


def test_saving_reaches_every_game_with_helixsr(home, monkeypatch):
    _ready(home)
    native = _steam_game(home, "100", "Space Game", {"Bin": (helixsr.UPSCALER_DLL,)}) / "Bin"
    helixsr.install_helixsr_game("100")
    (native / "helixsr.ini").unlink()   # an install from before settings existed
    records = helixsr._records()
    records["100"]["files"][0]["created"].remove("helixsr.ini")
    helixsr._write_json(helixsr._records_path(), records)
    root = _optiscaler_game(home, monkeypatch)
    helixsr.install_helixsr_optiscaler("300")

    result = helixsr.save_helixsr_settings({"Sharpening.Mode": "game", "ModelE.UseReactiveMask": True})

    assert result["games"] == 2 and result["skipped"] == []
    for folder in (native, root / "HelixSR"):
        text = (folder / "helixsr.ini").read_text(encoding="utf-8")
        assert helixsr._ini_get(text, "Sharpening", "Mode") == "game"
        assert helixsr._ini_get(text, "ModelE", "UseReactiveMask") == "true"
    opti = (root / "HelixSR" / "helixsr.ini").read_text(encoding="utf-8")
    assert helixsr._ini_get(opti, "Forwarding", "UpscalerDll") == helixsr.SECOND_UPSCALER, "kept"
    assert "helixsr.ini" in helixsr._records()["100"]["files"][0]["created"], "and removal cleans it"


def test_a_running_game_is_skipped_and_named(home, monkeypatch):
    _ready(home)
    _steam_game(home, "100", "Space Game", {"Bin": (helixsr.UPSCALER_DLL,)})
    helixsr.install_helixsr_game("100")

    def running(_folder, proc=None):
        raise RuntimeError("Close this game before changing its files.")

    monkeypatch.setattr(helixsr, "_refuse_running", running)
    result = helixsr.save_helixsr_settings({"Sharpening.Mode": "game"})
    assert result["games"] == 0 and result["skipped"] == ["Space Game"]


def test_the_repository_saves_settings(home, tmp_path):
    result = _repository(tmp_path).guardar_ajustes_helixsr({"Compatibility.WaveSize": "64"})
    assert result["settings"]["Compatibility.WaveSize"] == "64"
    assert helixsr.helixsr_state(machine="x86_64")["settings"]["Compatibility.WaveSize"] == "64"


# ------------------------------------------------------------------ game states


def test_missing_network_files_are_shown_and_restored_by_the_update(home):
    _ready(home)
    folder = _steam_game(home, "100", "Space Game", {"Bin": (helixsr.UPSCALER_DLL,)}) / "Bin"
    helixsr.install_helixsr_game("100")
    (folder / "helixsr_kernels.pak").unlink()
    row = helixsr.helixsr_state(machine="x86_64")["games"][0]
    assert (row["state"], row["network_missing"]) == ("installed", True)

    helixsr.update_helixsr_game("100")

    assert (folder / "helixsr_kernels.pak").is_file()
    assert helixsr.helixsr_state(machine="x86_64")["games"][0]["network_missing"] is False


def test_a_game_whose_folder_is_gone_is_shown_and_can_be_forgotten(home):
    import shutil

    _ready(home)
    install = _steam_game(home, "100", "Space Game", {"Bin": (helixsr.UPSCALER_DLL,)})
    helixsr.install_helixsr_game("100")
    shutil.rmtree(install)

    assert helixsr.helixsr_state(machine="x86_64")["games"][0]["state"] == "missing"
    helixsr.remove_helixsr_game("100")
    assert helixsr.helixsr_state(machine="x86_64")["games"] == []


def test_a_game_that_ships_dlss_310_7_spares_the_download(home, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "config"))
    monkeypatch.setattr(helixsr, "DLSS_DLL_SHA256", _sha(DLSS))
    monkeypatch.setattr(helixsr, "DLSS_DLL_SIZE", len(DLSS))
    install = _steam_game(home, "100", "Space Game", {"Bin": (helixsr.UPSCALER_DLL,)})
    (install / "Bin" / "nvngx_dlss.dll").write_bytes(DLSS)
    other = _steam_game(home, "200", "Other", {"Bin": ()})
    (other / "Bin" / "nvngx_dlss.dll").write_bytes(b"MZ another version!")   # same size, other DLL

    helixsr.scan_helixsr_games()

    assert helixsr.local_dlss_candidates() == [install / "Bin" / "nvngx_dlss.dll"]
    assert helixsr.helixsr_state(machine="x86_64")["local_dlss"] is True
