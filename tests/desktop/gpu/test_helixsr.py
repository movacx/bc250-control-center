"""HelixSR: the picked release, its network files, and games.

The release is never bundled: it is fetched on the user's PC, checked by
SHA-256 and unpacked unmodified; HelixSR's own setup builds the NVIDIA-derived
network files there. Per game, the FSR 3.1 DLL is kept as ``*.original.dll``
and every change can be undone.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from bc250cc.infrastructure import helixsr
from bc250cc.infrastructure.dependencias_repository import DependenciasRepository

needs_cmp = pytest.mark.skipif(shutil.which("cmp") is None, reason="the fake DLL check uses cmp (diffutils)")

DLL = b"MZ helixsr test dll"
ORIGINAL = b"MZ the game's own FSR 3.1 dll"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    # One reviewed release, the default, with the test DLL in it.
    monkeypatch.setattr(helixsr, "HELIXSR_REVIEWED", {helixsr.HELIXSR_TAG: {
        "archive": f"HelixSR-{helixsr.HELIXSR_VERSION}.zip", "sha256": _sha(b"archive"),
        "size": 1_000_000, "dll_sha256": _sha(DLL),
    }})
    monkeypatch.setattr(helixsr, "HELIXSR_DLL_DIGESTS", frozenset({_sha(DLL)}))
    # The NVIDIA DLL the fake download hands out.
    monkeypatch.setattr(helixsr, "DLSS_DLL_SHA256", _sha(DLSS))
    return tmp_path


def _pinned() -> dict:
    """The reviewed default release of the test."""
    return helixsr.HELIXSR_REVIEWED[helixsr.HELIXSR_TAG]


def _pin(**fields) -> None:
    _pinned().update(fields)


def _release(directory: Path, *, network: bool = True) -> None:
    """An installed, verified release (as the install command leaves it)."""
    directory.mkdir(parents=True)
    (directory / helixsr.HELIXSR_DLL).write_bytes(DLL)
    (directory / helixsr.HELIXSR_SETUP).write_text("#!/bin/sh\n", encoding="utf-8")
    (directory / helixsr.HELIXSR_MARKER).write_text(_pinned()["sha256"] + "\n", encoding="ascii")
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
        helixsr.build_helixsr_releases_command(),
        helixsr.build_helixsr_remove_command(),
    ):
        for word in ("sudo", "pkexec", "doas", "run0", "--yes"):
            assert word not in command
        result = subprocess.run(["bash", "-n"], input=command, text=True, capture_output=True, check=False)
        assert result.returncode == 0, result.stderr
    install = helixsr.build_helixsr_install_command()
    assert helixsr.helixsr_url(helixsr.helixsr_release()) in install
    assert _pinned()["sha256"] in install
    assert "HELIXSR_FORCE_PORTABLE" in install, "missing numpy must not reach the setup's sudo branch"


def _release_zip(path: Path, *, extra: str = "", top: str = "", embed: bool = False) -> Path:
    """A release as upstream ships it. Its setup builds the network beside
    the DLL (1.2 to 1.7) or, with ``embed``, appends it to the DLL (1.8)."""
    top = top or f"HelixSR-{helixsr.HELIXSR_VERSION}"
    build = (
        'printf weightskernels >> "$here/amd_fidelityfx_dx12.dll"\n'
        "printf 'HXSRNET1\\007\\0\\0\\0\\0\\0\\0\\0\\007\\0\\0\\0\\0\\0\\0\\0\\001\\0\\0\\0\\0\\0\\0\\0'"
        ' >> "$here/amd_fidelityfx_dx12.dll"\n'
        if embed else
        'printf weights > "$here/helixsr_weights.bin"\nprintf kernels > "$here/helixsr_kernels.pak"\n'
    )
    setup = (
        "#!/usr/bin/env bash\nset -e\n"
        'here="$(cd "$(dirname "$0")" && pwd)"\n'
        'test "$HELIXSR_FORCE_PORTABLE" = 0 -o "$HELIXSR_FORCE_PORTABLE" = 1\n'
        # The setup's own game list (1.7 and newer) must find no input.
        'if read -r _line; then exit 8; fi\n'
        'printf "%s\\n" "$@" > "$here/.setup-args"\n'
        'printf "%s" "$TMPDIR" > "$here/.setup-tmpdir"\n'
        'test "$1" = --dlss || exit 7\n'
        'cmp -s "$2" "$HOME/expected-dlss" || exit 9\n'
        + build
    )
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr(f"{top}/{helixsr.HELIXSR_DLL}", DLL)
        bundle.writestr(f"{top}/{helixsr.HELIXSR_SETUP}", setup)
        bundle.writestr(f"{top}/setup/lib/model/launch_synth", b"\x7fELF")
        bundle.writestr(f"{top}/LICENSE", "HelixSR Freeware License")
        if extra:
            bundle.writestr(extra, "x")
    return path


def _run_install(home: Path, archive: Path, monkeypatch, *, pin: bool = True,
                 answer: str = "y\n") -> subprocess.CompletedProcess:
    """The install command, with ``answer`` typed at the DLSS question."""
    if pin:
        _pin(sha256=_sha(archive.read_bytes()))
    if not (home / "expected-dlss").exists():
        (home / "expected-dlss").write_bytes(DLSS)
    bin_dir = home / "bin"
    bin_dir.mkdir(exist_ok=True)
    curl = bin_dir / "curl"
    # NVIDIA's GitHub hands out the DLSS DLL, HelixSR's the release.
    curl.write_text(
        '#!/bin/sh\nwhile [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift;; -*) ;; *) url="$1";; esac; shift; done\n'
        f'case "$url" in *nvngx_dlss.dll) cp "{home}/expected-dlss" "$out";; *) cp "{archive}" "$out";; esac\n',
        encoding="utf-8",
    )
    wine = bin_dir / "wine"
    wine.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    for tool in (curl, wine):
        tool.chmod(0o755)
    # sha256sum's messages are read below; they follow the locale.
    environment = dict(os.environ, HOME=str(home), XDG_DATA_HOME=str(home / "data"),
                       PATH=f"{bin_dir}:{os.environ['PATH']}", TMPDIR=str(home), LC_ALL="C")
    return subprocess.run(
        ["bash", "-c", helixsr.build_helixsr_install_command()],
        env=environment, input=answer, capture_output=True, text=True, timeout=60, check=False,
    )


@needs_cmp
def test_the_install_verifies_unpacks_and_builds_the_network(home, monkeypatch):
    result = _run_install(home, _release_zip(home / "release.zip"), monkeypatch)
    assert result.returncode == 0, result.stdout + result.stderr
    state = helixsr.helixsr_state(machine="x86_64")
    assert state["state"] == "ready", state
    assert os.access(helixsr.helixsr_directory() / "setup/lib/model/launch_synth", os.X_OK)


@needs_cmp
def test_the_long_shader_step_is_announced_and_its_progress_watched(home, monkeypatch):
    """Step 5/5 prints nothing for ~10 minutes: the setup's own temp folder
    is ours, so its finished shaders can be counted, and both go at the end."""
    result = _run_install(home, _release_zip(home / "release.zip"), monkeypatch)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "several minutes" in result.stdout
    work = Path((helixsr.helixsr_directory() / ".setup-tmpdir").read_text())
    assert work.name.startswith("bc250-helixsr-build.")
    assert not work.exists(), "the build folder is removed afterwards"
    command = helixsr.build_helixsr_install_command()
    assert command.index("bc250_progress=$!") < command.index('TMPDIR="$bc250_work"')
    assert command.count('kill "$bc250_progress"') == 2, "stopped on success and on failure"


@pytest.mark.parametrize("entry, message", [
    ("../escape.txt", "not one HelixSR folder"),
    ("OtherTop/file.txt", "not one HelixSR folder"),
    (f"HelixSR-{helixsr.HELIXSR_VERSION}/../x", "unexpected archive entry"),
])
def test_the_install_refuses_entries_outside_the_release_folder(home, monkeypatch, entry, message):
    result = _run_install(home, _release_zip(home / "release.zip", extra=entry), monkeypatch)
    assert result.returncode != 0
    assert message in result.stdout + result.stderr
    assert not helixsr.helixsr_directory().exists()
    assert not (home / "escape.txt").exists()


def test_the_install_refuses_a_different_archive(home, monkeypatch):
    _pin(sha256="0" * 64)
    result = _run_install(home, _release_zip(home / "release.zip"), monkeypatch, pin=False)
    assert result.returncode != 0
    assert "FAILED" in result.stdout + result.stderr
    assert not helixsr.helixsr_directory().exists()


def test_the_install_refuses_a_release_with_another_dll(home, monkeypatch):
    _pin(dll_sha256="0" * 64)
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
    assert _pinned()["sha256"] in command


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
    _pin(dll_sha256=_sha(NEW_DLL))
    monkeypatch.setattr(helixsr, "HELIXSR_DLL_DIGESTS", frozenset({_sha(DLL), _sha(NEW_DLL)}))


def test_the_default_is_the_newest_reviewed_stable_release_and_every_dll_is_known():
    assert helixsr.HELIXSR_VERSION == "1.8.1"
    assert helixsr.HELIXSR_TAG == max(helixsr.HELIXSR_REVIEWED, key=helixsr._version)
    for release in helixsr.HELIXSR_REVIEWED.values():
        assert release["dll_sha256"] in helixsr.HELIXSR_DLL_DIGESTS
        assert release["archive"].startswith("HelixSR-") and release["size"] > 0
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


@needs_cmp
def test_the_client_copy_of_dlss_spares_the_nvidia_download(home, monkeypatch):
    payload = _client_dlss(home, monkeypatch, DLSS)
    assert helixsr.helixsr_state(machine="x86_64")["local_dlss"] is True

    result = _run_install(home, _release_zip(home / "release.zip"), monkeypatch, answer="")

    assert result.returncode == 0, result.stdout + result.stderr
    args = _setup_args()
    assert args[0] == "--dlss" and args[1] != str(payload), "a private, verified copy is handed over"
    assert "already on this PC" in result.stdout and "Download it now?" not in result.stdout
    assert payload.read_bytes() == DLSS, "the client's own file stays untouched"
    assert not Path(args[1]).exists(), "the private copy is removed afterwards"


def test_a_changed_client_copy_is_skipped_and_nothing_is_downloaded_without_a_yes(home, monkeypatch):
    _client_dlss(home, monkeypatch, b"MZ some other dll")

    result = _run_install(home, _release_zip(home / "release.zip"), monkeypatch, answer="n\n")

    assert result.returncode == 1, result.stdout + result.stderr
    assert "is not NVIDIA's DLSS 310.7.0 DLL" in result.stdout
    assert "Download it now?" in result.stdout + result.stderr
    assert "Nothing was downloaded" in result.stdout
    assert not (helixsr.helixsr_directory() / ".setup-args").exists(), "the setup never ran"
    assert helixsr.helixsr_state(machine="x86_64")["state"] == "needs-network"


@needs_cmp
def test_without_the_client_the_dll_is_downloaded_after_a_yes_and_checked(home, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "config"))
    monkeypatch.setattr(helixsr, "DLSS_DLL_SHA256", _sha(DLSS))
    assert helixsr.helixsr_state(machine="x86_64")["local_dlss"] is False

    result = _run_install(home, _release_zip(home / "release.zip"), monkeypatch)

    assert result.returncode == 0, result.stdout + result.stderr
    args = _setup_args()
    assert args[0] == "--dlss" and len(args) == 2, "no target and no --yes: the setup uses its own folder"
    assert not Path(args[1]).exists(), "NVIDIA's DLL is removed afterwards"


def test_a_download_that_is_not_nvidias_dll_is_refused(home, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "config"))
    monkeypatch.setattr(helixsr, "DLSS_DLL_SHA256", "0" * 64)

    result = _run_install(home, _release_zip(home / "release.zip"), monkeypatch)

    assert result.returncode == 29, result.stdout + result.stderr
    assert "not NVIDIA's DLSS 310.7.0 DLL" in result.stdout
    assert not (helixsr.helixsr_directory() / ".setup-args").exists()


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
    "; helixsr.ini - optional\n\n[Sharpening]\n; off = never sharpen\nSharpener = off\nSharpness = 0.3\n"
    "MotionAdaptive = true\n\n[Upscaling]\nNetworkResolution = auto\n\n[ModelE]\nNetwork = auto\n"
    "MotionVectorFrontEnd = false\n\n[Forwarding]\nDll =\nUpscalerDll =\n"
)


FULL_INI = RELEASE_INI.replace(
    "MotionAdaptive = true\n",
    "MotionAdaptive = true\nUseGameSlider = false\nMotionThreshold = 2\nMotionLimit = 16\n"
    "MotionReduction = 0.6\nMode = off\n",
).replace(
    "NetworkResolution = auto\n", "NetworkResolution = auto\nInt8 = auto\n",
).replace(
    "MotionVectorFrontEnd = false\n",
    "MotionVectorFrontEnd = false\nUseReactiveMask = false\nDilateDisplayMotionVectors = false\n"
    "InvertJitter = false\nInvertMotionVectors = false\n\n[Log]\nEnabled = true\n\n"
    "[Compatibility]\nWaveSize = auto\n",
)


def test_defaults_leave_the_release_ini_exactly_as_it_is():
    assert helixsr._settings_text(FULL_INI, helixsr.helixsr_defaults()) == FULL_INI
    text = helixsr._settings_text(RELEASE_INI, {**helixsr.helixsr_defaults(), "Sharpening.Sharpener": "nvidia",
                                                "Compatibility.WaveSize": "32"})
    assert "; off = never sharpen\nSharpener = nvidia\n" in text, "the comments stay"
    assert helixsr._ini_get(text, "Sharpening", "Mode") == "override", "releases before 1.7 sharpen too"
    assert helixsr._ini_get(text, "Compatibility", "WaveSize") == "32", "a missing section is added"
    assert helixsr._ini_get(text, "Forwarding", "UpscalerDll") == "", "keys not on the form are kept"


def test_settings_are_validated_and_saved(home):
    assert helixsr.helixsr_settings() == helixsr.helixsr_defaults()
    result = helixsr.save_helixsr_settings({"Sharpening.Sharpness": "0.55", "Log.Enabled": False})
    assert result == {"settings": helixsr.helixsr_settings(), "games": 0, "skipped": []}
    assert helixsr.helixsr_settings()["Sharpening.Sharpness"] == 0.55
    assert helixsr.helixsr_settings()["Log.Enabled"] is False
    for bad in ({"Sharpening.Sharpener": "max"}, {"Upscaling.Int8": "yes"}, {"Sharpening.Sharpness": 2},
                {"Log.Enabled": "maybe"}):
        with pytest.raises(ValueError, match="Invalid HelixSR settings"):
            helixsr.save_helixsr_settings(bad)
    assert helixsr.helixsr_settings()["Sharpening.Sharpness"] == 0.55, "a refused save changes nothing"
    with pytest.raises(ValueError, match="Invalid HelixSR settings"):
        # The reduction fades in between the two speeds: the start comes first.
        helixsr.save_helixsr_settings({"Sharpening.MotionThreshold": 16, "Sharpening.MotionLimit": 8})
    helixsr.save_helixsr_settings({"Sharpening.MotionThreshold": 4, "Sharpening.MotionLimit": 32,
                                   "ModelE.MotionVectorFrontEnd": True})
    assert helixsr.helixsr_settings()["Sharpening.MotionLimit"] == 32.0
    assert helixsr.helixsr_settings()["ModelE.MotionVectorFrontEnd"] is True


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

    result = helixsr.save_helixsr_settings({"Sharpening.Sharpener": "rcas", "Sharpening.UseGameSlider": True,
                                            "ModelE.UseReactiveMask": True})

    assert result["games"] == 2 and result["skipped"] == []
    for folder in (native, root / "HelixSR"):
        text = (folder / "helixsr.ini").read_text(encoding="utf-8")
        assert helixsr._ini_get(text, "Sharpening", "Sharpener") == "rcas"
        assert helixsr._ini_get(text, "Sharpening", "UseGameSlider") == "true"
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
    result = helixsr.save_helixsr_settings({"Sharpening.Sharpener": "nvidia"})
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


# ------------------------------------------------------- OptiScaler added by hand


def _manual_optiscaler(home: Path, *, fsr4: bool = True) -> tuple[Path, Path]:
    """A game where OptiScaler was copied in by hand: no OptiScaler Client record."""
    game = home / "Games" / "Hand Racer"
    root = game / "Bin" / "Win64"
    (root / "OptiScaler").mkdir(parents=True)
    (root / "dxgi.dll").write_bytes(b"MZ optiscaler")
    (root / "OptiScaler.ini").write_bytes(OPTISCALER_INI.encode())
    if fsr4:
        (root / "OptiScaler" / helixsr.UPSCALER_DLL).write_bytes(FSR4)
    return game, root


def test_a_hand_installed_optiscaler_is_found_from_the_game_folder(home):
    game, root = _manual_optiscaler(home)

    result = helixsr.add_optiscaler_folder(str(game))

    assert result["game"] == "Hand Racer" and result["root"] == str(root)
    rows = [row for row in helixsr.helixsr_state(machine="x86_64")["games"] if row["kind"] == "optiscaler"]
    assert [(row["appid"], row["state"], row["folder"]) for row in rows] == [(result["id"], "available", str(root))]


def test_a_hand_installed_optiscaler_gets_helixsr_and_is_put_back_exactly(home, tmp_path):
    _ready(home)
    game, root = _manual_optiscaler(home)
    key = helixsr.add_optiscaler_folder(str(game))["id"]
    repository = _repository(tmp_path)

    assert repository.gestionar_helixsr(f"opti_install:{key}") == {"game": "Hand Racer", "fsr4": True}

    folder = root / "HelixSR"
    assert (folder / helixsr.UPSCALER_DLL).read_bytes() == DLL
    assert (folder / helixsr.SECOND_UPSCALER).read_bytes() == FSR4
    text = (root / "OptiScaler.ini").read_bytes().decode()
    assert helixsr._ini_get(text, "Libraries", "FfxDx12SRPath").endswith("HelixSR\\" + helixsr.UPSCALER_DLL)
    rows = [row for row in helixsr.helixsr_state(machine="x86_64")["games"] if row["kind"] == "optiscaler"]
    assert [(row["state"], row["folder"]) for row in rows] == [("installed", str(root))]
    with pytest.raises(RuntimeError, match="Remove HelixSR from this game first"):
        repository.gestionar_helixsr(f"forget_folder:{key}")

    repository.gestionar_helixsr(f"opti_remove:{key}")
    assert (root / "OptiScaler.ini").read_bytes() == OPTISCALER_INI.encode()
    assert not folder.exists()
    assert repository.gestionar_helixsr(f"forget_folder:{key}") == {"game": "Hand Racer"}
    assert [row for row in helixsr.helixsr_state(machine="x86_64")["games"] if row["kind"] == "optiscaler"] == []


def test_the_repository_keeps_the_case_of_an_optiscaler_folder(home, tmp_path):
    game, _root = _manual_optiscaler(home)
    upper = game.parent / "UPPER Case"
    game.rename(upper)
    assert _repository(tmp_path).gestionar_helixsr(f"add_opti_folder:{upper}")["game"] == "UPPER Case"


@pytest.mark.parametrize("problem", ["none", "two", "missing", "home"])
def test_a_folder_without_one_clear_optiscaler_is_refused(home, problem):
    game, root = _manual_optiscaler(home)
    if problem == "none":
        (root / "OptiScaler.ini").unlink()
    elif problem == "two":
        (game / "Other").mkdir()
        (game / "Other" / "OptiScaler.ini").write_text("[Upscalers]\n", encoding="utf-8")
    target = {"missing": home / "nowhere", "home": home}.get(problem, game)
    with pytest.raises(RuntimeError):
        helixsr.add_optiscaler_folder(str(target))
    assert helixsr._optiscaler_folders() == {}


# ------------------------------------------------------------------ games with OptiScaler


def test_the_search_leaves_optiscaler_and_its_fsr4_dll_alone(home):
    """OptiScaler Client keeps its FSR4 DLL in OptiScaler/, beside OptiScaler.ini,
    under the same name as the game's own: it is never a target (seen on a
    BC-250 with Forza Horizon 6)."""
    install = _steam_game(home, "400", "Racer", {
        ".": (helixsr.UPSCALER_DLL,),
        "OptiScaler": (helixsr.UPSCALER_DLL,),
        "HelixSR": (helixsr.UPSCALER_DLL,),
        "Engine/Plugins": (helixsr.UPSCALER_DLL,),
    })
    (install / "OptiScaler.ini").write_bytes(OPTISCALER_INI.encode())
    targets = helixsr._fsr_folders(install)
    assert targets == sorted([install / helixsr.UPSCALER_DLL,
                              install / "Engine/Plugins" / helixsr.UPSCALER_DLL])


def test_a_folder_named_optiscaler_is_searched_when_no_optiscaler_ini_is_beside_it(home):
    install = _steam_game(home, "401", "Odd", {"OptiScaler": (helixsr.UPSCALER_DLL,)})
    assert helixsr._fsr_folders(install) == [install / "OptiScaler" / helixsr.UPSCALER_DLL]


def test_the_repository_keeps_the_case_of_a_client_game_added_by_hand(home, tmp_path, monkeypatch):
    """OptiScaler Client names a game added by hand "Manual_<hex>"."""
    seen = []
    from bc250cc.infrastructure import dependencias_repository

    monkeypatch.setattr(dependencias_repository, "install_helixsr_optiscaler",
                        lambda appid: seen.append(appid) or {"game": appid})
    _repository(tmp_path).gestionar_helixsr("OPTI_INSTALL:Manual_327959e9")
    assert seen == ["Manual_327959e9"]


@pytest.mark.parametrize("steam", [
    ".var/app/com.valvesoftware.Steam/.local/share/Steam",  # Flatpak
    "snap/steam/common/.local/share/Steam",                # Snap, Ubuntu
])
def test_proton_of_any_steam_install_is_handed_to_the_setup(home, steam):
    """Upstream's setup knows only native Steam's folders, then wine on PATH."""
    root = home / steam
    (root / "userdata").mkdir(parents=True)
    wine = root / "steamapps/common/Proton 11.0/files/bin/wine"
    wine.parent.mkdir(parents=True)
    wine.write_text("#!/bin/sh\n", encoding="utf-8")
    wine.chmod(0o755)
    assert helixsr._wine_candidates(home) == [wine.resolve()]
    assert helixsr.wine_available(home)
    command = helixsr.build_helixsr_network_command()
    assert str(wine.resolve()) in command
    assert 'PATH="$bc250_shim:$PATH"' in command


def test_a_game_installed_in_steam_is_found_without_pressing_find(home):
    _ready(home)
    assert helixsr.refresh_helixsr_scan(home=home) is True, "first look"
    assert helixsr.refresh_helixsr_scan(home=home) is False, "nothing changed"
    _steam_game(home, "500", "New Game", {"Bin": (helixsr.UPSCALER_DLL,)})
    rows = helixsr.helixsr_state(machine="x86_64")["games"]
    assert [(row["appid"], row["state"]) for row in rows] == [("500", "available")]
    assert helixsr.refresh_helixsr_scan(home=home) is False


# ------------------------------------------------------------------ releases


def _github(home: Path, *entries: dict) -> None:
    """GitHub's release list as Check for new releases saves it."""
    helixsr._write_json(helixsr._releases_path(), {"time": 1, "releases": list(entries)})


def _listed(tag: str, archive: bytes | str, *, prerelease: bool = False, name: str = "",
            **extra) -> dict:
    digest = _sha(archive) if isinstance(archive, bytes) else archive
    version = tag.removeprefix("v")
    return {"tag_name": tag, "draft": False, "prerelease": prerelease, "assets": [
        {"name": name or f"HelixSR-{version}.zip", "size": 1234, "digest": f"sha256:{digest}"},
    ], **extra}


def test_without_a_check_the_reviewed_releases_are_offered_and_the_default_picked(home):
    state = helixsr.helixsr_state(machine="x86_64")
    assert [r["tag"] for r in state["releases"]] == [helixsr.HELIXSR_TAG]
    assert state["tag"] == helixsr.HELIXSR_TAG and state["reviewed"] and not state["releases_checked"]


def test_githubs_list_adds_newer_releases_and_drops_withdrawn_ones(home, monkeypatch):
    reviewed = {**_pinned()}
    monkeypatch.setattr(helixsr, "HELIXSR_REVIEWED", {
        helixsr.HELIXSR_TAG: reviewed,
        "v1.3.0": {"archive": "HelixSR-1.3.0.zip", "sha256": "3" * 64, "size": 1, "dll_sha256": "4" * 64},
    })
    _github(
        home,
        _listed("v2.0.0", b"new", prerelease=True),
        _listed("v1.9.9", b"draft", draft=True),
        _listed("v1.1.0", b"too old"),
        _listed("v1.9.8", "not a digest"),
        _listed("v1.9.7", b"x", name="setup.exe"),
        # Another archive under a reviewed tag: the reviewed digest stays.
        _listed(helixsr.HELIXSR_TAG, b"replaced upstream"),
    )

    releases = helixsr.helixsr_releases()

    assert [(r["tag"], r["prerelease"], r["reviewed"]) for r in releases] == [
        ("v2.0.0", True, False), (helixsr.HELIXSR_TAG, False, True),
    ], "v1.3.0 was withdrawn from GitHub"
    assert releases[1]["sha256"] == reviewed["sha256"]
    assert releases[0]["sha256"] == _sha(b"new") and releases[0]["dll_sha256"] == ""


def test_the_scaler_app_published_beside_a_release_is_not_its_archive(home):
    """Since 1.9 each release also carries HelixSR-Scaler-*.zip (and a desktop
    app); those used to make the release look like it had two archives."""
    release = _listed("v1.9.3", b"helixsr 1.9.3")
    release["assets"] += [
        {"name": "HelixSR-Scaler-1.0.6.zip", "size": 99, "digest": "sha256:" + "a" * 64},
        {"name": "HelixSR-Scaler-1.0.6-linux.tar.gz", "size": 99, "digest": "sha256:" + "b" * 64},
        {"name": "SHA256SUMS.txt", "size": 9, "digest": "sha256:" + "c" * 64},
    ]
    _github(home, release, _listed(helixsr.HELIXSR_TAG, _pinned()["sha256"]))

    newest = helixsr.helixsr_releases()[0]

    assert (newest["tag"], newest["archive"], newest["sha256"]) == (
        "v1.9.3", "HelixSR-1.9.3.zip", _sha(b"helixsr 1.9.3"),
    )


def test_a_pick_is_saved_and_falls_back_to_the_default_once_withdrawn(home):
    _github(home, _listed("v2.0.0", b"new", prerelease=True), _listed(helixsr.HELIXSR_TAG, _pinned()["sha256"]))
    with pytest.raises(ValueError, match="not on offer"):
        helixsr.select_helixsr_release("v9.9.9")
    assert helixsr.select_helixsr_release("v2.0.0") == {"tag": "v2.0.0", "version": "2.0.0"}
    state = helixsr.helixsr_state(machine="x86_64")
    assert (state["tag"], state["prerelease"], state["reviewed"]) == ("v2.0.0", True, False)
    assert helixsr.helixsr_directory().name == "2.0.0"
    assert "(pre-release)" in helixsr.build_helixsr_install_command()

    _github(home, _listed(helixsr.HELIXSR_TAG, _pinned()["sha256"]))

    assert helixsr.helixsr_release()["tag"] == helixsr.HELIXSR_TAG


@needs_cmp
def test_a_release_from_githubs_list_is_checked_by_its_published_digest(home, monkeypatch):
    """1.9.0's archive is HelixSR-1.9.0.2.zip with HelixSR-1.9.0 inside."""
    other = b"MZ helixsr from github"
    archive = home / "github.zip"
    _release_zip(archive, top="HelixSR-1.9.0")
    with zipfile.ZipFile(archive, "a") as bundle:
        bundle.writestr("HelixSR-1.9.0/" + helixsr.HELIXSR_DLL + ".tmp", b"")
    # The zip's DLL is the test DLL; give it another one, as a new release would have.
    rebuilt = home / "github2.zip"
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(rebuilt, "w") as bundle:
        for item in source.infolist():
            if item.filename.endswith(".tmp"):
                continue
            data = other if item.filename.endswith(helixsr.HELIXSR_DLL) else source.read(item)
            bundle.writestr(item, data)
    _github(home, _listed("v1.9.0", rebuilt.read_bytes(), prerelease=True, name="HelixSR-1.9.0.2.zip"),
            _listed(helixsr.HELIXSR_TAG, _pinned()["sha256"]))
    helixsr.select_helixsr_release("v1.9.0")

    result = _run_install(home, rebuilt, monkeypatch, pin=False)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "GitHub published" in result.stdout
    state = helixsr.helixsr_state(machine="x86_64")
    assert (state["state"], state["version"]) == ("ready", "1.9.0")
    assert _sha(other) in helixsr._known_digests(), "games given it stay known after a switch"


def test_a_tampered_release_from_githubs_list_is_refused(home, monkeypatch):
    archive = _release_zip(home / "release.zip", top="HelixSR-2.0.0")
    _github(home, _listed("v2.0.0", b"what github published"), _listed(helixsr.HELIXSR_TAG, _pinned()["sha256"]))
    helixsr.select_helixsr_release("v2.0.0")

    result = _run_install(home, archive, monkeypatch, pin=False)

    assert result.returncode != 0
    assert not helixsr.helixsr_directory().exists()


def test_picking_an_older_release_is_not_called_an_update(home, monkeypatch):
    monkeypatch.setattr(helixsr, "HELIXSR_REVIEWED", {
        helixsr.HELIXSR_TAG: _pinned(),
        "v1.3.0": {"archive": "HelixSR-1.3.0.zip", "sha256": "3" * 64, "size": 1, "dll_sha256": "4" * 64},
    })
    _ready(home)
    helixsr.select_helixsr_release("v1.3.0")
    assert helixsr.helixsr_state(machine="x86_64")["state"] == "other-version"
    _release(helixsr.helixsr_root() / "1.2.0")
    import shutil
    shutil.rmtree(helixsr.helixsr_root() / helixsr.HELIXSR_VERSION)
    assert helixsr.helixsr_state(machine="x86_64")["state"] == "update-available"


def test_the_release_list_is_read_in_the_terminal_and_kept_small(home):
    command = helixsr.build_helixsr_releases_command()
    assert helixsr.HELIXSR_RELEASES_API in command
    bin_dir = home / "bin"
    bin_dir.mkdir()
    answer = home / "answer.json"
    import json
    answer.write_text(json.dumps([
        {**_listed("v2.0.0", b"new", prerelease=True), "body": "notes " * 1000, "author": {"login": "x"}},
        _listed("v1.9.9", b"x", name="setup.exe"),
    ]), encoding="utf-8")
    curl = bin_dir / "curl"
    curl.write_text(
        '#!/bin/sh\nwhile [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift;; esac; shift; done\n'
        f'cp "{answer}" "$out"\n', encoding="utf-8",
    )
    curl.chmod(0o755)
    environment = dict(os.environ, HOME=str(home), XDG_DATA_HOME=str(home / "data"),
                       PATH=f"{bin_dir}:{os.environ['PATH']}", TMPDIR=str(home), LC_ALL="C")

    result = subprocess.run(["bash", "-c", command], env=environment, capture_output=True, text=True,
                            timeout=60, check=False)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "v2.0.0  (pre-release)\n" in result.stdout
    assert "v1.9.9  (no single HelixSR archive: not offered)" in result.stdout
    saved = json.loads(helixsr._releases_path().read_text(encoding="utf-8"))
    assert set(saved["releases"][0]) == {"tag_name", "draft", "prerelease", "assets"}
    assert "v2.0.0" in [r["tag"] for r in helixsr.helixsr_releases()]


@needs_cmp
def test_a_built_network_inside_the_dll_is_recognised_and_copied_alone(home, monkeypatch):
    """1.8 appends the network to HelixSR's DLL: the DLL is still the
    reviewed one once that part is set aside, and no network files follow."""
    result = _run_install(home, _release_zip(home / "release.zip", embed=True), monkeypatch)
    assert result.returncode == 0, result.stdout + result.stderr
    assert helixsr.helixsr_state(machine="x86_64")["state"] == "ready"
    folder = _steam_game(home, "100", "Space Game", {"Bin": (helixsr.UPSCALER_DLL,)}) / "Bin"

    helixsr.install_helixsr_game("100")

    assert (folder / helixsr.UPSCALER_DLL).read_bytes().startswith(DLL)
    assert not any((folder / name).exists() for name in helixsr.HELIXSR_NETWORK_FILES)
    row = helixsr.helixsr_state(machine="x86_64")["games"][0]
    assert (row["state"], row["network_missing"]) == ("installed", False)
    helixsr.remove_helixsr_game("100")
    assert sorted(path.name for path in folder.iterdir()) == [helixsr.UPSCALER_DLL]


def test_an_update_to_a_dll_with_its_network_removes_the_old_network_files(home, monkeypatch):
    _ready(home)
    folder = _steam_game(home, "100", "Space Game", {"Bin": (helixsr.UPSCALER_DLL,)}) / "Bin"
    helixsr.install_helixsr_game("100")
    assert all((folder / name).is_file() for name in helixsr.HELIXSR_NETWORK_FILES)
    directory = helixsr.helixsr_directory()
    footer = b"HXSRNET1" + (7).to_bytes(8, "little") + (7).to_bytes(8, "little") + (1).to_bytes(8, "little")
    (directory / helixsr.HELIXSR_DLL).write_bytes(DLL + b"weightskernels" + footer)
    for name in helixsr.HELIXSR_NETWORK_FILES:
        (directory / name).unlink()

    helixsr.update_helixsr_game("100")

    assert not any((folder / name).exists() for name in helixsr.HELIXSR_NETWORK_FILES)
    assert helixsr._records()["100"]["files"][0]["created"] == ["helixsr.ini"]
    helixsr.remove_helixsr_game("100")
    assert sorted(path.name for path in folder.iterdir()) == [helixsr.UPSCALER_DLL]


def test_a_footer_that_claims_more_than_the_file_is_not_a_network(tmp_path):
    dll = tmp_path / "x.dll"
    dll.write_bytes(DLL + b"HXSRNET1" + (1 << 40).to_bytes(8, "little") + bytes(16))
    assert helixsr._dll_digest(dll) == _sha(dll.read_bytes())
    assert not helixsr._has_embedded_network(dll)


def test_a_setup_that_builds_nothing_is_reported(home, monkeypatch):
    archive = home / "release.zip"
    _release_zip(archive)
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(home / "empty.zip", "w") as bundle:
        for item in source.infolist():
            data = source.read(item)
            if item.filename.endswith(helixsr.HELIXSR_SETUP):
                data = b"#!/usr/bin/env bash\nexit 0\n"
            bundle.writestr(item, data)

    result = _run_install(home, home / "empty.zip", monkeypatch)

    assert result.returncode == 1
    assert "without building the network" in result.stdout


def test_settings_saved_for_13_are_carried_over():
    assert helixsr._migrated_settings({"Sharpening.Mode": "game"}) == {
        "Sharpening.Sharpener": "rcas", "Sharpening.UseGameSlider": True,
    }
    assert helixsr._migrated_settings({"Sharpening.Mode": "override"}) == {"Sharpening.Sharpener": "rcas"}
    assert helixsr._migrated_settings({"Sharpening.Mode": "off", "Sharpening.Sharpener": "nvidia"}) == {
        "Sharpening.Sharpener": "nvidia",
    }


def test_the_repository_routes_the_version_actions(home, tmp_path):
    repository = _repository(tmp_path)
    assert repository.gestionar_helixsr(f"select:{helixsr.HELIXSR_TAG}")["tag"] == helixsr.HELIXSR_TAG
    title, command = repository.gestionar_helixsr("releases")
    assert title == "HelixSR · releases" and helixsr.HELIXSR_RELEASES_API in command


# ------------------------------------------------------- non-Steam games in Steam


def _binary_vdf(value: dict) -> bytes:
    """Steam's binary KeyValues, as shortcuts.vdf holds them."""
    out = b""
    for key, item in value.items():
        name = key.encode() + b"\0"
        if isinstance(item, dict):
            out += b"\x00" + name + _binary_vdf(item) + b"\x08"
        elif isinstance(item, int):
            out += b"\x02" + name + (item & 0xFFFFFFFF).to_bytes(4, "little")
        else:
            out += b"\x01" + name + str(item).encode() + b"\0"
    return out


def _shortcuts(home: Path, *entries: dict) -> Path:
    path = home / ".local/share/Steam/userdata/1/config/shortcuts.vdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    shortcuts = {str(index): entry for index, entry in enumerate(entries)}
    path.write_bytes(_binary_vdf({"shortcuts": shortcuts}) + b"\x08")
    return path


def _cyberpunk(home: Path) -> Path:
    """A game copied by hand, its .exe and FSR 3.1 loader in bin/x64."""
    folder = home / "Games" / "Cyberpunk 2077" / "bin" / "x64"
    folder.mkdir(parents=True)
    (folder / "Cyberpunk2077.exe").write_bytes(b"MZ")
    (folder / helixsr.LOADER_DLL).write_bytes(ORIGINAL)
    return home / "Games" / "Cyberpunk 2077"


def test_a_non_steam_game_added_to_steam_is_found_and_handled_like_a_steam_game(home):
    from bc250cc.infrastructure.steam_launch_options import steam_shortcut_game_folders

    _ready(home)
    game = _cyberpunk(home)
    exe = game / "bin/x64/Cyberpunk2077.exe"
    _shortcuts(
        home,
        {"appid": -381695011, "AppName": "Cyberpunk2077.exe", "Exe": f'"{exe}"', "StartDir": f"{exe.parent}/"},
        {"appid": 7, "appname": "Heroic", "exe": "/usr/bin/heroic", "StartDir": "/usr/bin"},
        {"appid": 8, "AppName": "Whole home", "Exe": f'"{home}/x.exe"', "StartDir": str(home)},
    )
    assert [(g["appid"], g["name"], g["path"]) for g in steam_shortcut_game_folders(home)] == [
        ("shortcut-3913272285", "Cyberpunk 2077", game.resolve()),
    ], "Steam's signed id is unsigned; bin/x64 leads to the game; nothing outside a game's folder"

    rows = helixsr.helixsr_state(machine="x86_64")["games"]
    assert [(r["appid"], r["name"], r["state"]) for r in rows] == [("shortcut-3913272285", "Cyberpunk 2077", "available")]

    helixsr.install_helixsr_game("shortcut-3913272285")
    assert (game / "bin/x64" / helixsr.LOADER_DLL).read_bytes() == DLL
    assert helixsr.helixsr_state(machine="x86_64")["games"][0]["state"] == "installed"
    helixsr.remove_helixsr_game("shortcut-3913272285")
    assert (game / "bin/x64" / helixsr.LOADER_DLL).read_bytes() == ORIGINAL


def test_a_new_shortcut_is_searched_without_pressing_find(home):
    _ready(home)
    assert helixsr.helixsr_state(machine="x86_64")["games"] == []
    exe = _cyberpunk(home) / "bin/x64/Cyberpunk2077.exe"
    path = _shortcuts(home, {"appid": 5, "AppName": "Cyberpunk", "Exe": f'"{exe}"', "StartDir": ""})
    os.utime(path, ns=(1, 1))   # a different stamp from any earlier search
    assert [r["name"] for r in helixsr.helixsr_state(machine="x86_64")["games"]] == ["Cyberpunk"]


def test_a_shortcut_to_a_folder_added_by_hand_is_not_listed_twice(home):
    _ready(home)
    game = _cyberpunk(home)
    helixsr.add_helixsr_folder(str(game))
    exe = game / "bin/x64/Cyberpunk2077.exe"
    _shortcuts(home, {"appid": 5, "AppName": "Cyberpunk", "Exe": f'"{exe}"', "StartDir": ""})
    rows = helixsr.helixsr_state(machine="x86_64")["games"]
    assert [r["appid"][:7] for r in rows] == ["folder-"]


def test_a_broken_shortcuts_file_is_ignored(home):
    from bc250cc.infrastructure.steam_launch_options import steam_shortcut_game_folders

    path = home / ".local/share/Steam/userdata/1/config/shortcuts.vdf"
    path.parent.mkdir(parents=True)
    for data in (b"\x00shortcuts\x00\x00", b"\x09bad", b"\x00shortcuts\x00\x00 0\x00\x02appid\x00\x01"):
        path.write_bytes(data)
        assert steam_shortcut_game_folders(home) == []


def test_a_shortcut_that_left_steam_cannot_be_given_helixsr(home):
    _ready(home)
    with pytest.raises(RuntimeError, match="no longer in Steam"):
        helixsr.install_helixsr_game("shortcut-123")


def test_only_1_9_and_newer_read_the_int8_setting(home):
    assert helixsr.helixsr_state(machine="x86_64")["int8_supported"] is False
    assert [helixsr._reads_int8(tag) for tag in ("v1.8.1", "v1.3.0", "v1.9.0", "v2.0.0", "v1.10.0")] == [
        False, False, True, True, True]
