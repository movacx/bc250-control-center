"""Read-only fixtures and script inspection: never invoke upstream workflows."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from bc250cc.infrastructure.accessories import real_sleep


def write(root: Path, name: str, content: str = "") -> Path:
    path = root / name.lstrip("/")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


@pytest.fixture
def board(tmp_path):
    write(tmp_path, "sys/class/dmi/id/board_name", "AMD BC-250\n")
    write(tmp_path, "sys/class/dmi/id/bios_version", "P3.00\n")
    write(tmp_path, "sys/devices/system/cpu/present", "0-11\n")
    write(tmp_path, "proc/swaps", "Filename\tType\tSize\tUsed\tPriority\n")
    return tmp_path


def installed(root):
    for path in (real_sleep.BOOT_UNIT, real_sleep.DROPIN):
        write(root, path)
    for path in ("bc250-sleep", "bc250-update", "system.sh", "setvar.py", "src/bc250_pm.ko"):
        write(root, f"{real_sleep.DIRECTORY}/{path}")
    write(root, f"{real_sleep.DIRECTORY}/VERSION", "1.2.3\n")
    write(root, f"{real_sleep.DIRECTORY}/mode", "s3\n")


@pytest.mark.parametrize("family", ["steamos", "bazzite", "cachyos", " SteamOS "])
def test_supported_board_without_installation(board, family):
    assert real_sleep.inventory(family, root=board) == {
        "state": "not-installed", "reason": "", "version": "1.2.3", "mode": "",
        "s3_supported": True, "spare_cores_blocked": False, "conflicts": (), "needs_swap": True,
    }


def test_unsupported_family_and_board(board):
    assert real_sleep.inventory("arch", root=board)["state"] == "unsupported"
    write(board, "sys/class/dmi/id/board_name", "Another board")
    info = real_sleep.inventory("steamos", root=board)
    assert info["state"] == "unsupported" and info["reason"]


def test_missing_files_are_safe(tmp_path):
    info = real_sleep.inventory("steamos", root=tmp_path)
    assert info["state"] == "unsupported"
    assert not info["s3_supported"] and info["needs_swap"]


@pytest.mark.parametrize("mode", ["s3", "hibernate"])
def test_complete_installation(board, mode):
    installed(board)
    write(board, f"{real_sleep.DIRECTORY}/mode", mode)
    info = real_sleep.inventory("bazzite", root=board)
    assert info["state"] == "installed" and info["mode"] == mode


@pytest.mark.parametrize("path,content", [
    ("VERSION", "0.1"), ("mode", "fast"), ("src/bc250_pm.ko", None), ("system.sh", None),
])
def test_incomplete_installation_is_broken(board, path, content):
    installed(board)
    target = board / real_sleep.DIRECTORY.lstrip("/") / path
    if content is None:
        target.unlink()
    else:
        target.write_text(content)
    info = real_sleep.inventory("cachyos", root=board)
    assert info["state"] == "broken" and info["reason"]


def test_partial_units_and_uninstall_leftovers(board):
    installed(board)
    (board / real_sleep.BOOT_UNIT.lstrip("/")).unlink()
    assert real_sleep.inventory("steamos", root=board)["state"] == "broken"
    (board / real_sleep.DROPIN.lstrip("/")).unlink()
    # Upstream deliberately retains /etc/bc250-sleep after uninstalling.
    assert real_sleep.inventory("steamos", root=board)["state"] == "not-installed"


@pytest.mark.parametrize("mask,blocked", [(None, True), (0x77, False), (0xFF, True), (0, True)])
def test_sixteen_threads_require_known_mask(board, mask, blocked):
    write(board, "sys/devices/system/cpu/present", "0-15")
    info = real_sleep.inventory("steamos", root=board, core_mask=mask)
    assert info["state"] == "not-installed"
    assert info["spare_cores_blocked"] is blocked
    assert bool(info["reason"]) is blocked
    if blocked:
        assert info["reason"] == real_sleep.REASON_CORES


def test_count_injection_and_sparse_present_cpus(board):
    assert real_sleep.inventory("steamos", root=board, logical_cpus=13)["spare_cores_blocked"]
    write(board, "sys/devices/system/cpu/present", "0-5,8-13")
    assert not real_sleep.inventory("steamos", root=board)["spare_cores_blocked"]
    (board / "sys/devices/system/cpu/present").unlink()
    write(board, "proc/cpuinfo", "processor : 0\n" * 16)
    assert real_sleep.inventory("steamos", root=board)["spare_cores_blocked"]


@pytest.mark.parametrize("home", ["home/deck", "var/home/player", "srv/player", "root"])
def test_lethe_conflict_in_any_home(board, home):
    write(board, "etc/passwd", f"player:x:1001:1001::/{home}:/bin/bash\n")
    write(board, f"{home}/homebrew/plugins/bc250-sleep/plugin.json",
          '{"name":"BC-250 Sleep","author":"lethe-bc250 contributors"}')
    info = real_sleep.inventory("cachyos", root=board)
    assert info["conflicts"] == ("lethe",)
    assert info["state"] == "not-installed" and info["reason"]


@pytest.mark.parametrize("metadata", ["{", "[]", '{"name":"BC-250 Sleep","author":"someone else"}'])
def test_unrelated_or_invalid_plugin_is_not_lethe(board, metadata):
    write(board, "home/deck/homebrew/plugins/bc250-sleep/plugin.json", metadata)
    assert real_sleep.inventory("steamos", root=board)["conflicts"] == ()


@pytest.mark.parametrize("path", ["boot/bc250-acpi.cpio", "etc/default/grub.d/92-bc250-acpi.cfg"])
def test_acpi_conflicts_only_on_steamos(board, path):
    write(board, path)
    assert real_sleep.inventory("steamos", root=board)["conflicts"] == ("acpi",)
    assert real_sleep.inventory("bazzite", root=board)["conflicts"] == ()


@pytest.mark.parametrize("swap,needed", [
    ("", True), ("/dev/zram0 partition 100 0 100", True),
    ("/swapfile file 100 0 -2", False),
    ("/dev/zram0 partition 100 0 100\n/dev/nvme0n1p3 partition 100 0 -2", False),
])
def test_only_persistent_swap_counts(board, swap, needed):
    write(board, "proc/swaps", "Filename Type Size Used Priority\n" + swap)
    assert real_sleep.inventory("steamos", root=board)["needs_swap"] is needed


def test_bios_support_is_exact(board):
    write(board, "sys/class/dmi/id/bios_version", "P2.00")
    assert not real_sleep.inventory("steamos", root=board)["s3_supported"]


def test_pinned_checkout_precedes_privileged_actions():
    for builder in (real_sleep.install_command, real_sleep.remove_command):
        script = builder("steamos")
        assert real_sleep.UPSTREAM in script
        assert f"checkout --detach {real_sleep.REVIEWED_REVISION}" in script
        verification = f'$(git rev-parse HEAD)" = {real_sleep.REVIEWED_REVISION}'
        assert verification in script
        assert script.index(verification) < script.index("sudo ")
        assert 'chmod 700 "$bc250_stage"' in script
        assert '${HOME}/.bc250-real-sleep.XXXXXX' in script
        assert "ERROR:" in script and "trap " in script


def test_bios_record_and_restore_order_and_validation():
    install = real_sleep.install_command("steamos")
    remove = real_sleep.remove_command("steamos")
    assert install.index("sudo python3 - record") < install.index("sudo ./install.sh")
    assert remove.index("sudo ./install.sh --uninstall") < remove.index("sudo python3 - restore")
    assert real_sleep.BACKUP in install and real_sleep.BACKUP in remove
    assert 'if backup.exists() or backup.is_symlink():' in install
    assert 'subprocess.check_output(["python3", "tools/setvar.py"]' in install
    assert "Never guess" in remove and "0x6f6=0x0f" not in remove
    assert "if read_bytes() != values:" in remove
    assert "os.O_EXCL" in install and "0o600" in install and "os.fsync" in install
    assert "flock" in install and "re.fullmatch" in remove


def test_bios_and_mask_guards_and_explicit_subcommands():
    script = real_sleep.install_command("cachyos", core_mask=0x77)
    assert script.index("S3 requires BIOS P3.00") < script.index("git -c")
    assert "core_mask=119" in script and 'info["spare_cores_blocked"]' in script
    assert 'info["conflicts"]' in script
    assert "S3 requires BIOS P3.00" not in real_sleep.install_command("bazzite", mode="hibernate")
    assert "S3 requires BIOS P3.00" in real_sleep.set_mode_command("s3")
    assert f"sudo {real_sleep.DIRECTORY}/bc250-sleep mode hibernate" in real_sleep.set_mode_command("hibernate")
    assert real_sleep.status_command().endswith("/bc250-sleep status")


def test_invalid_inputs_are_refused():
    for builder in (real_sleep.install_command, real_sleep.remove_command):
        with pytest.raises(RuntimeError):
            builder("arch")
    with pytest.raises(ValueError):
        real_sleep.install_command("steamos", mode="reboot")
    with pytest.raises(ValueError):
        real_sleep.set_mode_command("sleep")


@pytest.mark.parametrize("family", sorted(real_sleep.FAMILIES))
def test_scripts_parse_without_executing_workflows(tmp_path, family):
    scripts = [real_sleep.remove_command(family), real_sleep.status_command()]
    for mode in ("s3", "hibernate"):
        scripts += [real_sleep.install_command(family, mode=mode), real_sleep.set_mode_command(mode)]
    for index, script in enumerate(scripts):
        path = tmp_path / f"{index}.sh"
        path.write_text(script)
        subprocess.run(["bash", "-n", str(path)], check=True)
        assert "systemctl reboot" not in script
        assert "systemctl suspend" not in script
        assert "systemctl hibernate" not in script
