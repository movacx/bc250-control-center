"""Hiding the kernel's boot messages (the BC-250's RDSEED warning) on Bazzite."""
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from bc250cc.infrastructure.bazzite_boot_messages import (
    build_bazzite_boot_messages_command,
    probe_bazzite_boot_messages,
)


@pytest.mark.parametrize("action", ("hide", "restore", "status"))
def test_bazzite_boot_message_commands_are_closed_and_shell_valid(action, tmp_path):
    command = build_bazzite_boot_messages_command(action)
    script = tmp_path / f"{action}.sh"
    script.write_text(command, encoding="utf-8")

    assert "this workflow is available only on Bazzite" in command
    assert "rpm-ostree kargs" in command
    assert "systemctl reboot" not in command
    assert subprocess.run(["bash", "-n", str(script)], check=False).returncode == 0


def test_hide_saves_the_original_levels_and_restore_uses_only_owned_state():
    hide = build_bazzite_boot_messages_command("hide")
    restore = build_bazzite_boot_messages_command("restore")

    assert "# Managed by BC250 Control Center" in hide
    assert "--append-if-missing=loglevel=0" in hide
    # A level the image already had is taken out first, so only one is left.
    assert "--delete-if-present=$bc250_arg" in hide
    assert "no BC250-owned boot-messages state" in restore
    assert "previous boot-messages level was not restored exactly" in restore
    assert restore.index("previous boot-messages level was not restored exactly") < restore.index("sudo unlink")


def test_it_never_touches_the_mitigation_state_or_quiet():
    command = build_bazzite_boot_messages_command("hide")
    assert "mitigations" not in command
    assert "quiet" not in command


def test_probe_distinguishes_running_and_next_boot_state(tmp_path: Path):
    cmdline = tmp_path / "cmdline"
    cmdline.write_text("quiet loglevel=0 splash\n", encoding="ascii")
    result = SimpleNamespace(returncode=0, stdout="quiet splash\n")

    state = probe_bazzite_boot_messages(
        proc_cmdline=cmdline, state_file=tmp_path / "original", runner=lambda *_a, **_k: result,
    )

    assert state["active"] is True and state["configured"] is False
    assert state["reboot_required"] is True
    assert state["state"] == "reboot-required"


def test_probe_reports_a_setting_owned_by_nobody_here(tmp_path: Path):
    cmdline = tmp_path / "cmdline"
    cmdline.write_text("quiet loglevel=0\n", encoding="ascii")
    result = SimpleNamespace(returncode=0, stdout="quiet loglevel=0\n")

    state = probe_bazzite_boot_messages(
        proc_cmdline=cmdline, state_file=tmp_path / "missing", runner=lambda *_a, **_k: result,
    )

    assert state["configured"] is True and state["managed"] is False
    assert state["state"] == "hidden"


def test_invalid_action_is_rejected():
    with pytest.raises(ValueError):
        build_bazzite_boot_messages_command("automatic")
