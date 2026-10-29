"""nosmt on Bazzite: the argument and the state its transaction reports."""
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from bc250cc.infrastructure.bazzite_smt import build_bazzite_smt_command, probe_bazzite_smt


@pytest.mark.parametrize("action", ("disable", "restore", "status"))
def test_the_smt_commands_are_closed_and_shell_valid(action, tmp_path):
    command = build_bazzite_smt_command(action)
    script = tmp_path / f"{action}.sh"
    script.write_text(command, encoding="utf-8")
    assert "this workflow is available only on Bazzite" in command
    assert "systemctl reboot" not in command
    assert subprocess.run(["bash", "-n", str(script)], check=False).returncode == 0


def test_only_nosmt_is_staged_and_the_other_arguments_are_never_named():
    command = build_bazzite_smt_command("disable")
    assert "--append-if-missing=nosmt" in command
    assert "mitigations" not in command and "loglevel" not in command


def test_the_probe_tells_the_running_kernel_from_the_next_boot(tmp_path: Path):
    cmdline = tmp_path / "cmdline"
    cmdline.write_text("quiet nosmt\\n".replace("\\n", "\n"), encoding="ascii")
    result = SimpleNamespace(returncode=0, stdout="quiet\n")
    state = probe_bazzite_smt(proc_cmdline=cmdline, state_file=tmp_path / "x", runner=lambda *_a, **_k: result)
    assert state["active"] is True and state["configured"] is False
    assert state["reboot_required"] is True and state["state"] == "reboot-required"


def test_an_unknown_action_is_refused():
    with pytest.raises(ValueError):
        build_bazzite_smt_command("hide")
