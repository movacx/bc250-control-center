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
