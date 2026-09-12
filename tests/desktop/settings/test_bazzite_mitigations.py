from pathlib import Path
from types import SimpleNamespace

import pytest

from bc250cc.infrastructure.bazzite_mitigations import (
    build_bazzite_mitigations_command,
    probe_bazzite_mitigations,
)


@pytest.mark.parametrize("action", ("disable", "restore", "status"))
def test_bazzite_mitigation_commands_are_closed_and_shell_valid(action, tmp_path):
    command = build_bazzite_mitigations_command(action)
    script = tmp_path / f"{action}.sh"
    script.write_text(command, encoding="utf-8")

    assert "this workflow is available only on Bazzite" in command
    assert "rpm-ostree kargs" in command
    assert "systemctl reboot" not in command
    assert __import__("subprocess").run(
        ["bash", "-n", str(script)], check=False
    ).returncode == 0


def test_disable_saves_original_arguments_and_restore_uses_only_owned_state():
    disable = build_bazzite_mitigations_command("disable")
    restore = build_bazzite_mitigations_command("restore")

    assert "# Managed by BC250 Control Center" in disable
    assert "--append-if-missing=mitigations=off" in disable
    assert "--delete-if-present=$bc250_arg" in disable
    assert "no BC250-owned mitigation state" in restore
    assert "previous mitigation policy was not restored exactly" in restore
    assert restore.index("previous mitigation policy was not restored exactly") < restore.index("sudo unlink")
    assert "sudo unlink" in restore


def test_probe_distinguishes_running_and_next_boot_state(tmp_path: Path):
    cmdline = tmp_path / "cmdline"
    state_file = tmp_path / "original"
    cmdline.write_text("quiet mitigations=off splash\n", encoding="ascii")

    result = SimpleNamespace(returncode=0, stdout="quiet splash\n")
    state = probe_bazzite_mitigations(
        proc_cmdline=cmdline,
        state_file=state_file,
        runner=lambda *_args, **_kwargs: result,
    )

    assert state["active"] is True
    assert state["configured"] is False
    assert state["reboot_required"] is True
    assert state["state"] == "reboot-required"


def test_invalid_action_is_rejected():
    with pytest.raises(ValueError):
        build_bazzite_mitigations_command("automatic")
