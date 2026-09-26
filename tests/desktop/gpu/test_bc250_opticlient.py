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
