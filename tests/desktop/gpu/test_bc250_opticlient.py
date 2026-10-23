"""FSR4 INT8 through the BC250 build of OptiScaler Client.

The client (daniel-h-0/bc250-fsr4-fork) patches games itself and keeps its own
backups; Control Center downloads the pinned release, verifies it, installs it
in the user's folder, opens it, and removes it -- on every distribution, with
no root and no kernel requirement.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from bc250cc.infrastructure import bc250_opticlient as opticlient
from bc250cc.infrastructure.dependencias_repository import DependenciasRepository


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(opticlient, "_running", lambda: False)
    return tmp_path


def _install_fake(directory: Path, *, marker: str = opticlient.OPTICLIENT_SHA256) -> None:
    directory.mkdir(parents=True)
    for name in (opticlient.OPTICLIENT_LAUNCHER, opticlient.OPTICLIENT_BINARY):
        (directory / name).write_text("#!/bin/sh\n", encoding="utf-8")
    if marker:
        (directory / opticlient.OPTICLIENT_MARKER).write_text(marker + "\n", encoding="ascii")


def test_nothing_installed_is_reported_as_such(home):
    state = opticlient.opticlient_state(machine="x86_64")
    assert state["state"] == "not-installed"
    assert state["installer_available"] and not state["installed"]
    assert state["steam_launch_option"] == 'WINEDLLOVERRIDES="dxgi=n,b" %command%'


def test_a_verified_install_is_ready(home):
    _install_fake(opticlient.opticlient_directory())
    state = opticlient.opticlient_state(machine="x86_64")
    assert state["state"] == "ready" and state["current"]


def test_a_changed_folder_needs_repair(home):
    _install_fake(opticlient.opticlient_directory(), marker="0" * 64)
    assert opticlient.opticlient_state(machine="x86_64")["state"] == "invalid"


def test_an_older_release_offers_the_update(home):
    _install_fake(opticlient.opticlient_root() / "1.0.7-bc250.2")
    state = opticlient.opticlient_state(machine="x86_64")
    assert state["state"] == "update-available"
    assert state["other_versions"] == ["1.0.7-bc250.2"]


def test_other_architectures_are_not_offered(home):
    assert opticlient.opticlient_state(machine="aarch64")["installer_available"] is False


def test_the_install_verifies_twice_and_never_asks_for_root(home):
    command = opticlient.build_opticlient_install_command()
    assert opticlient.OPTICLIENT_URL in command
    assert opticlient.OPTICLIENT_SHA256 in command
    assert "sha256sum -c -" in command
    assert "sha256sum --quiet -c SHA256SUMS" in command
    assert "*/../*" in command, "archive paths escaping the folder are refused"
    for word in ("sudo", "pkexec", "doas", "run0"):
        assert word not in command
    result = subprocess.run(["bash", "-n"], input=command, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr


def test_removal_keeps_every_game_backup(home):
    command = opticlient.build_opticlient_remove_command()
    records = str(opticlient.opticlient_records())
    assert not any(records in line and "rm " in line for line in command.splitlines())
    assert "pgrep -x OptiscalerClient" in command
    result = subprocess.run(["bash", "-n"], input=command, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr


def test_desktop_entry_paths_use_desktop_quoting():
    assert opticlient._desktop_exec(Path("/home/ab/run.sh")) == "/home/ab/run.sh"
    assert opticlient._desktop_exec(Path("/home/a b/run.sh")) == '"/home/a b/run.sh"'
    assert opticlient._desktop_exec(Path('/x"$/run.sh')) == '"/x\\"\\$/run.sh"'


def test_launching_before_installing_is_refused(home):
    with pytest.raises(RuntimeError, match="Install OptiScaler Client first"):
        opticlient.launch_opticlient()


def _atomic_home(tmp_path: Path) -> tuple[Path, Path]:
    """Fedora Atomic layout: /home is a symlink to var/home."""
    real = tmp_path / "var" / "home" / "user"
    real.mkdir(parents=True)
    (tmp_path / "home").symlink_to(Path("var") / "home")
    return tmp_path / "home" / "user", real


def test_the_client_sees_real_home_folders_on_atomic_distributions(tmp_path):
    linked, real = _atomic_home(tmp_path)
    environment = opticlient._client_environment({
        "HOME": str(linked),
        "XDG_CONFIG_HOME": str(linked / ".config"),
        "XDG_DATA_HOME": str(linked / ".local" / "share"),
        "PYTHONPATH": "/app",
        "LANG": "es_ES.UTF-8",
    })
    assert environment["HOME"] == str(real)
    assert environment["XDG_CONFIG_HOME"] == str(real / ".config")
    assert environment["XDG_DATA_HOME"] == str(real / ".local" / "share")
    assert "PYTHONPATH" not in environment and environment["LANG"] == "es_ES.UTF-8"


def test_launch_starts_the_client_outside_linked_folders(tmp_path, monkeypatch):
    linked, real = _atomic_home(tmp_path)
    monkeypatch.setenv("HOME", str(linked))
    monkeypatch.setenv("XDG_DATA_HOME", str(linked / ".local" / "share"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(linked / ".config"))
    monkeypatch.setattr(opticlient, "_running", lambda: False)
    _install_fake(opticlient.opticlient_directory())
    started = {}
    monkeypatch.setattr(
        opticlient.subprocess, "Popen",
        lambda args, **kwargs: started.update(args=args, **kwargs),
    )

    opticlient.launch_opticlient()

    expected = real / ".local" / "share" / "bc250-control-center" / "opticlient" / opticlient.OPTICLIENT_VERSION
    assert started["args"] == [str(expected / opticlient.OPTICLIENT_LAUNCHER)]
    assert started["cwd"] == str(expected)
    assert started["env"]["HOME"] == str(real)
    assert started["env"]["XDG_CONFIG_HOME"] == str(real / ".config")


def test_the_desktop_entry_also_uses_real_home_folders(tmp_path, monkeypatch):
    linked, real = _atomic_home(tmp_path)
    monkeypatch.setenv("HOME", str(linked))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(linked / ".local" / "share"))
    command = opticlient.build_opticlient_install_command()
    assert f"Exec=env HOME={real} XDG_CONFIG_HOME={real / '.config'} {real}/" in command
    assert f"Path={real}/" in command


@pytest.mark.parametrize("family", ["ubuntu", "cachyos", "bazzite", "fedora", "opensuse", "steamos"])
def test_every_distribution_gets_the_same_workflow(home, tmp_path, family):
    repository = DependenciasRepository()
    repository._os_repository = lambda: SimpleNamespace(info=SimpleNamespace(family=family, distro_id=family))
    repository._tool_dir = lambda: tmp_path
    repository._abrir_terminal = lambda command, title: (title, command)

    title, command = repository.gestionar_fsr4_bc250("install")

    assert "OptiScaler Client" in title
    assert opticlient.OPTICLIENT_SHA256 in command


def test_the_old_v3_runtime_can_still_be_removed(home, tmp_path):
    repository = DependenciasRepository()
    repository._tool_dir = lambda: tmp_path
    repository._abrir_terminal = lambda command, title: (title, command)

    title, command = repository.gestionar_fsr4_bc250("legacy_uninstall")

    assert "uninstall-v3.sh" in command
    assert "V3" in title


def test_open_goes_through_the_verified_launcher(home, monkeypatch):
    repository = DependenciasRepository()
    calls = []
    monkeypatch.setattr(
        "bc250cc.infrastructure.dependencias_repository.launch_opticlient",
        lambda: calls.append(True) or {"launched": True},
    )
    assert repository.gestionar_fsr4_bc250("launch") == {"launched": True}
    assert calls == [True]


# ------------------------------------------------------------------ versions


def _listed(version: str, digest: str = "a" * 64, *, name: str = "", prerelease: bool = True,
            prefix: str = "opticlient-v", **extra) -> dict:
    return {"tag_name": prefix + version, "draft": False, "prerelease": prerelease, "assets": [
        {"name": name or f"bc250-opticlient-{version}-linux-x64.tar.gz", "size": 1234,
         "digest": f"sha256:{digest}"},
        {"name": "bc250-fsr4-dll-4.0.0-rc11-docs2.zip", "size": 9, "digest": "sha256:" + "f" * 64},
        {"name": "SHA256SUMS", "size": 9, "digest": "sha256:" + "e" * 64},
    ], **extra}


def _github(*entries: dict) -> None:
    """GitHub's release list as Check for new releases saves it."""
    import json

    path = opticlient._releases_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"time": 1, "releases": list(entries)}), encoding="utf-8")


def test_without_a_check_only_the_reviewed_build_is_offered(home):
    state = opticlient.opticlient_state(machine="x86_64", games=False)
    assert [r["tag"] for r in state["releases"]] == [opticlient.OPTICLIENT_TAG]
    assert state["tag"] == opticlient.OPTICLIENT_TAG and not state["releases_checked"]


def test_githubs_list_adds_client_builds_and_skips_everything_else(home):
    _github(
        _listed("1.0.8-bc250.1", "b" * 64),
        _listed("1.0.7-bc250.5", "c" * 64),  # another archive under the reviewed tag
        _listed("1.0.7-bc250.4", "d" * 64),
        _listed("4.0.0-rc11", prefix="v"),  # the older runtime, not a client build
        _listed("1.0.9-bc250.1", "not a digest"),
        _listed("1.0.9-bc250.2", name="setup.exe"),
        _listed("1.1.0-bc250.1", draft=True),
        _listed("latest"),
    )

    releases = opticlient.opticlient_releases()

    assert [(r["version"], r["reviewed"], r["default"]) for r in releases] == [
        ("1.0.8-bc250.1", False, False),
        (opticlient.OPTICLIENT_VERSION, True, True),
        ("1.0.7-bc250.4", False, False),
    ]
    assert releases[1]["sha256"] == opticlient.OPTICLIENT_SHA256, "the reviewed digest stays"
    assert releases[0]["archive"] == "bc250-opticlient-1.0.8-bc250.1-linux-x64.tar.gz"


def test_a_picked_build_is_what_install_downloads_and_checks(home):
    _github(_listed("1.0.8-bc250.1", "b" * 64), _listed(opticlient.OPTICLIENT_VERSION))
    with pytest.raises(ValueError, match="not on offer"):
        opticlient.select_opticlient_release("opticlient-v9.9.9-bc250.1")

    assert opticlient.select_opticlient_release("opticlient-v1.0.8-bc250.1") == {
        "tag": "opticlient-v1.0.8-bc250.1", "version": "1.0.8-bc250.1",
    }
    command = opticlient.build_opticlient_install_command()

    assert opticlient.opticlient_directory().name == "1.0.8-bc250.1"
    assert ("releases/download/opticlient-v1.0.8-bc250.1/"
            "bc250-opticlient-1.0.8-bc250.1-linux-x64.tar.gz") in command
    assert "b" * 64 in command and opticlient.OPTICLIENT_SHA256 not in command
    assert "bc250-opticlient-1.0.8-bc250.1-linux-x64|bc250-opticlient-1.0.8-bc250.1-linux-x64/*" in command
    assert "newer than the ones Control Center was reviewed with" in command
    result = subprocess.run(["bash", "-n"], input=command, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr

    _github(_listed(opticlient.OPTICLIENT_VERSION))  # upstream withdrew 1.0.8
    assert opticlient.opticlient_release()["tag"] == opticlient.OPTICLIENT_TAG


def test_picking_an_older_build_is_not_called_an_update(home):
    _github(_listed(opticlient.OPTICLIENT_VERSION), _listed("1.0.7-bc250.4", "d" * 64))
    _install_fake(opticlient.opticlient_directory())
    assert opticlient.opticlient_state(machine="x86_64", games=False)["state"] == "ready"

    opticlient.select_opticlient_release("opticlient-v1.0.7-bc250.4")
    state = opticlient.opticlient_state(machine="x86_64", games=False)

    assert (state["state"], state["version"], state["current"]) == ("other-version", "1.0.7-bc250.4", False)


def test_the_release_list_is_read_in_the_terminal_and_kept_small(home):
    import json
    import os

    command = opticlient.build_opticlient_releases_command()
    assert opticlient.OPTICLIENT_RELEASES_API in command
    bin_dir = home / "bin"
    bin_dir.mkdir()
    answer = home / "answer.json"
    answer.write_text(json.dumps([
        {**_listed("1.0.8-bc250.1", "b" * 64), "body": "notes " * 1000, "author": {"login": "x"}},
        _listed("4.0.0-rc11", prefix="v"),
        _listed("1.0.9-bc250.2", name="setup.exe"),
    ]), encoding="utf-8")
    curl = bin_dir / "curl"
    curl.write_text(
        '#!/bin/sh\nwhile [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift;; esac; shift; done\n'
        f'cp "{answer}" "$out"\n', encoding="utf-8",
    )
    curl.chmod(0o755)
    environment = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", TMPDIR=str(home), LC_ALL="C")

    result = subprocess.run(["bash", "-c", command], env=environment, capture_output=True, text=True,
                            timeout=60, check=False)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "1.0.8-bc250.1  (pre-release)\n" in result.stdout
    assert "4.0.0-rc11" not in result.stdout, "the older runtime is not listed as a client build"
    assert "1.0.9-bc250.2  (pre-release)  (no client archive: not offered)" in result.stdout
    saved = json.loads(opticlient._releases_path().read_text(encoding="utf-8"))
    assert set(saved["releases"][0]) == {"tag_name", "draft", "prerelease", "assets"}
    assert "opticlient-v1.0.8-bc250.1" in [r["tag"] for r in opticlient.opticlient_releases()]


def test_the_backend_saves_a_pick_and_opens_the_release_list(home, monkeypatch):
    _github(_listed("1.0.8-bc250.1", "b" * 64), _listed(opticlient.OPTICLIENT_VERSION))
    repository = object.__new__(DependenciasRepository)
    opened = []
    monkeypatch.setattr(repository, "_abrir_terminal", lambda command, title: opened.append(title) or {}, raising=False)

    assert repository.gestionar_fsr4_bc250("select:opticlient-v1.0.8-bc250.1")["version"] == "1.0.8-bc250.1"
    repository.gestionar_fsr4_bc250("releases")

    assert opticlient.opticlient_release()["tag"] == "opticlient-v1.0.8-bc250.1"
    assert opened == ["FSR4 · releases"]


def test_a_newer_build_from_githubs_list_installs_end_to_end(home):
    """The terminal script itself: download, digest, layout, SHA256SUMS, install."""
    import hashlib
    import os
    import tarfile

    version = "1.0.8-bc250.1"
    top = f"bc250-opticlient-{version}-linux-x64"
    stage = home / "build" / top
    stage.mkdir(parents=True)
    for name in (opticlient.OPTICLIENT_BINARY, opticlient.OPTICLIENT_LAUNCHER):
        (stage / name).write_text("#!/bin/sh\n", encoding="utf-8")
        (stage / name).chmod(0o755)
    sums = "".join(
        f"{hashlib.sha256((stage / name).read_bytes()).hexdigest()}  {name}\n"
        for name in (opticlient.OPTICLIENT_BINARY, opticlient.OPTICLIENT_LAUNCHER)
    )
    (stage / "SHA256SUMS").write_text(sums, encoding="utf-8")
    archive = home / f"{top}.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(stage, arcname=top)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    _github(_listed(version, digest), _listed(opticlient.OPTICLIENT_VERSION))
    opticlient.select_opticlient_release(f"opticlient-v{version}")
    _install_fake(opticlient.opticlient_root() / opticlient.OPTICLIENT_VERSION)
    assert opticlient.opticlient_state(machine="x86_64", games=False)["state"] == "update-available"

    bin_dir = home / "bin"
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    curl.write_text(
        '#!/bin/sh\nwhile [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift;; esac; shift; done\n'
        f'cp "{archive}" "$out"\n', encoding="utf-8",
    )
    curl.chmod(0o755)
    environment = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", TMPDIR=str(home), LC_ALL="C")

    result = subprocess.run(["bash", "-c", opticlient.build_opticlient_install_command()],
                            env=environment, capture_output=True, text=True, timeout=60, check=False)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "newer than the ones Control Center was reviewed with" in result.stdout
    state = opticlient.opticlient_state(machine="x86_64", games=False)
    assert (state["state"], state["version"], state["other_versions"]) == ("ready", version, [])
