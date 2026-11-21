"""Power delivery through Hexxeh's bc250-vrm driver, built with DKMS.

Since 1.1.0 the driver reads the regulator through the fan chip, so no wires
are needed. It is offered on Arch-based systems, left alone where the kernel
already carries it, and refused while the wired BC250-Telemetry service runs.
"""

from __future__ import annotations

import subprocess

import pytest

from bc250cc.infrastructure import accessories
from bc250cc.infrastructure.accessories import _dkms, vrm_sensor


@pytest.fixture
def board(tmp_path, monkeypatch):
    name = tmp_path / "board_name"
    name.write_text("AMD BC-250\n")
    (tmp_path / "hwmon").mkdir()
    monkeypatch.setattr(vrm_sensor, "BOARD_NAME_PATH", name)
    monkeypatch.setattr(vrm_sensor, "HWMON_ROOT", tmp_path / "hwmon")
    monkeypatch.setattr(vrm_sensor, "SOURCE_DIRECTORY", tmp_path / "usr-src")
    monkeypatch.setattr(vrm_sensor, "_module_file", lambda: "")
    return tmp_path


def test_an_arch_based_bc250_can_install_it_on_any_bios(board):
    # No SMU patch here: unlike bc250-memory, the BIOS does not matter.
    assert vrm_sensor.inventory("manjaro")["state"] == "not-installed"
    assert not vrm_sensor.DRIVER.bios


def test_other_distributions_cannot(board):
    assert vrm_sensor.inventory("bazzite")["state"] == "unsupported"


def test_mastags_kernel_is_left_alone(board, monkeypatch):
    monkeypatch.setattr(
        vrm_sensor, "_module_file",
        lambda: "/lib/modules/7.3.4-cachyos-bc250/kernel/drivers/hwmon/bc250_vrm.ko.zst",
    )
    assert vrm_sensor.inventory("cachyos")["state"] == "managed-elsewhere"


def test_installed_and_reading_reports_the_cpu_vrm_temperature(board):
    (board / "usr-src").mkdir()
    (board / "usr-src" / _dkms.BUILD_MARKER).write_text(vrm_sensor.DRIVER.build_id + "\n")
    assert vrm_sensor.inventory("arch")["state"] == "installed"
    device = board / "hwmon" / "hwmon4"
    device.mkdir()
    (device / "name").write_text("bc250_vrm\n")
    (device / "temp1_input").write_text("41000\n")
    info = vrm_sensor.inventory("arch")
    assert info["state"] == "active" and info["reading"] == 41


def test_the_build_links_both_upstream_objects():
    assert "bc250_vrm-y := bc250_vrm_core.o nct6687_smbus.o" in vrm_sensor.KBUILD


def test_the_installer_refuses_while_the_wired_service_runs():
    script = vrm_sensor.install_command("cachyos")
    assert "systemctl is-active --quiet apu-telemetry.service" in script
    assert script.index("apu-telemetry.service") < script.index("sudo pacman -S")
    for digest in vrm_sensor.SOURCES.values():
        assert digest in script
    assert f"rev-parse HEAD)\" = {vrm_sensor.REVIEWED_REVISION}" in script


@pytest.mark.parametrize("action", ["install", "remove"])
def test_the_scripts_parse(tmp_path, action):
    script = (vrm_sensor.install_command if action == "install" else vrm_sensor.remove_command)("arch")
    path = tmp_path / "script.sh"
    path.write_text(script)
    subprocess.run(["bash", "-n", str(path)], check=True)


def test_it_is_part_of_the_accessories(tmp_path):
    assert "vrm_sensor" in accessories.ACCESSORIES
    command = accessories.accessory_command("vrm_sensor", "remove", family="arch", tool_dir=tmp_path)
    assert "dkms remove bc250-vrm/1.1.0 --all" in command


def test_both_drivers_share_one_makefile():
    from bc250cc.infrastructure.accessories import vram_sensor

    assert vram_sensor.MAKEFILE == _dkms.MAKEFILE
    assert "LLVM=1 modules" not in vrm_sensor.DKMS_CONF


def test_it_is_built_on_the_ec_port_the_fan_driver_leaves_free():
    """The fan driver (nct6687) holds EC port 0; bc250-vrm moves to port 1.

    Reported 2026-11-20: installed after the fan driver, bc250-vrm logged
    "failed to request EC port 0x0a20" and never read anything.
    """
    script = vrm_sensor.install_command("arch")
    assert "nct6687_ec_base = base + 4;" in script
    # Patched only after the source is proven, and checked before it is built.
    assert script.index("sha256sum --check") < script.index("sed -i") < script.index("sudo dkms add")
    assert "changed upstream; Control Center did not patch it" in script


def test_the_patch_matches_the_reviewed_line(tmp_path):
    """The sed expression changes exactly the upstream line it names."""
    name, expression, expected, _only_on_port_1 = vrm_sensor.DRIVER.patches[0]
    source = tmp_path / name
    source.write_text("\tif (x)\n\t\treturn;\n\tnct6687_ec_base = base;\n\n\t/* Reserve EC Port 0 */\n")
    subprocess.run(["sed", "-i", expression, str(source)], check=True)
    text = source.read_text()
    assert expected in text and "nct6687_ec_base = base;" not in text


def test_the_port_is_chosen_on_the_board_not_assumed():
    """Port 1 unless a fan driver already sits there (mainline nct6683 does)."""
    script = vrm_sensor.install_command("arch")
    assert "bc250_ec_port=1" in script
    # Only a fan driver's region counts, never bc250-vrm's own smbus window.
    assert "0a24-0a27 : nct668[0-9]$" in script
    assert 'if [ "$bc250_ec_port" = 1 ]; then sed -i' in script


def test_an_earlier_build_that_does_not_read_is_offered_as_an_update(board):
    """The copy built before the port fix: installed, no mark, silent."""
    (board / "usr-src").mkdir()
    assert vrm_sensor.inventory("arch")["state"] == "update-available"
    (board / "usr-src" / _dkms.BUILD_MARKER).write_text(vrm_sensor.DRIVER.build_id + "\n")
    assert vrm_sensor.inventory("arch")["state"] == "installed"


def test_a_working_copy_without_the_mark_is_left_alone():
    assert _dkms.is_current(vrm_sensor.DRIVER, "", 41.0)
    assert not _dkms.is_current(vrm_sensor.DRIVER, "", None)
    assert not _dkms.is_current(vrm_sensor.DRIVER, "0123456789abcdef", 41.0)


def test_the_installer_leaves_its_mark_after_the_files():
    script = vrm_sensor.install_command("cachyos")
    assert f"printf '%s\\n' {vrm_sensor.DRIVER.build_id} | sudo tee" in script
    assert script.index(f"/usr/src/bc250-vrm-1.1.0/{_dkms.BUILD_MARKER}") > script.index("sudo install -m 0644")


def test_the_repair_restarts_the_driver_and_checks_the_readings():
    """A wedged bc250_vrm is fixed from the app, not by typing modprobe."""
    import subprocess

    from bc250cc.infrastructure.accessories.vrm_sensor import reload_command

    script = reload_command()
    assert "sudo modprobe -r bc250_vrm" in script and "sudo modprobe bc250_vrm" in script
    # It checks the result, and names the power cycle when a restart is not enough.
    assert "temp1_input" in script and "in0_input" in script
    assert "Turn the computer off completely" in script
    assert subprocess.run(["bash", "-n", "-c", script], check=False).returncode == 0
