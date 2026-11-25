"""Stop loading at boot also stops the DKMS copy that the board's alias loads."""

import os
import subprocess

from bc250cc.infrastructure import memory_autoload as autoload
from bc250cc.infrastructure.dependencias_repository import DependenciasRepository
from bc250cc.infrastructure.system_setup import MEMORY_SENSOR_OPTION as OPTION


def board(tmp_path, *, alias=True, denied="", loaded=True):
    modules = tmp_path / "usr/lib/modules" / os.uname().release
    modules.mkdir(parents=True)
    (modules / "modules.alias").write_text("alias dmi*:rn*AMDBC-250*: bc250_memory\n" if alias else "alias x y\n")
    (tmp_path / "etc/modprobe.d").mkdir(parents=True)
    if denied:
        (tmp_path / denied).write_text("blacklist bc250_memory\n")
    if loaded:
        (tmp_path / "sys/module/bc250_memory").mkdir(parents=True)
    return tmp_path


def options():
    off = {"active": False, "managed": False, "configured": False, "external": False}
    return {"arguments": {OPTION: dict(off), "nosmt": dict(off)}}


def test_the_row_says_it_loads_even_when_the_command_line_does_not(tmp_path):
    row = autoload.corrected(options(), OPTION, board(tmp_path))["arguments"]
    assert row[OPTION] == {"active": True, "managed": True, "configured": True, "external": False}
    assert not row["nosmt"]["managed"]


def test_a_denied_driver_still_in_memory_is_shown_as_pending(tmp_path):
    root = board(tmp_path, denied=autoload.DENYLIST[1:])
    row = autoload.corrected(options(), OPTION, root)["arguments"][OPTION]
    assert row["active"] and not row["managed"] and not row["configured"]


def test_without_an_alias_the_kernel_option_is_what_counts(tmp_path):
    root = board(tmp_path, alias=False)
    assert autoload.corrected(options(), OPTION, root) == options()
    assert autoload.steps(False, root) == "" == autoload.steps(True, root)


def test_stopping_blocks_the_boot_and_unloads_now(tmp_path):
    text = autoload.steps(False, board(tmp_path))
    assert "blacklist bc250_memory" in text and autoload.DENYLIST in text and "sudo modprobe -r bc250_memory" in text
    assert subprocess.run(["bash", "-n", "-c", text]).returncode == 0


def test_nothing_changes_twice_and_loading_again_removes_only_our_file(tmp_path):
    root = board(tmp_path, denied=autoload.DENYLIST[1:])
    assert autoload.steps(False, root) == ""
    assert f"rm -f -- {autoload.DENYLIST}" in autoload.steps(True, root)


def test_another_tools_block_is_named_and_left(tmp_path):
    text = autoload.steps(True, board(tmp_path, denied="etc/modprobe.d/mine.conf"))
    assert "/etc/modprobe.d/mine.conf" in text and "rm -f" not in text


def test_the_workflow_carries_the_steps_and_never_the_boot_argument(monkeypatch):
    opened = []

    class Repository(DependenciasRepository):
        def __init__(self):
            pass

        def _os_repository(self):
            return type("OS", (), {"family": "cachyos"})()

        def _abrir_terminal(self, command, title):
            opened.append(command)

    monkeypatch.setattr(autoload, "loads_by_alias", lambda *a: True)
    monkeypatch.setattr(autoload, "denied_by", lambda *a: "")
    Repository().gestionar_opciones_kernel(("nosmt",))
    Repository().gestionar_opciones_kernel(("nosmt", OPTION))
    assert "modprobe -r bc250_memory" in opened[0] and "modprobe -r" not in opened[1]
    assert all("modules-load=" not in command for command in opened)
