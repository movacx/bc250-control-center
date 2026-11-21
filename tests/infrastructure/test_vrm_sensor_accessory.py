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


def test_it_stays_on_port_0_and_tolerates_the_fan_drivers_idle_reservation():
    """nct6687 reserves port 0 (0x0a20) but drives port 1; bc250-vrm keeps port 0.

    2026-11-20: loaded after the fan driver, upstream failed with "failed to
    request EC port 0x0a20". 2026-11-21: moving to port 1 shared the fan
    driver's registers and wedged the EC.
    """
    script = vrm_sensor.install_command("arch")
    assert "nct6687_ec_base = base + 4;" not in script
    assert "nct6687_ec_reserved = false;" in script
    # Patched only after the source is proven, and checked before it is built.
    assert script.index("sha256sum --check") < script.index("sed -i") < script.index("sudo dkms add")
    assert "changed upstream; Control Center did not patch it" in script


def test_the_patches_apply_to_the_reviewed_source(tmp_path):
    """The three expressions, on the lines of the reviewed nct6687_smbus.c."""
    source = tmp_path / "nct6687_smbus.c"
    source.write_text("\n".join((
        "static u16 nct6687_ec_base = NCT6687_EC_BASE_DEFAULT;",
        '\tif (!request_region(nct6687_ec_base, NCT6687_EC_PORT_LEN, "nct6687_smbus")) {',
        '\t\tpr_err("nct6687_smbus: failed to request EC port 0x%04x\\n", nct6687_ec_base);',
        "\t\treturn -EBUSY;",
        "\t}",
        "\t\trelease_region(nct6687_ec_base, NCT6687_EC_PORT_LEN);",
        "\trelease_region(nct6687_ec_base, NCT6687_EC_PORT_LEN);",
    )) + "\n")
    for _name, expression, expected, *_ in vrm_sensor.DRIVER.patches:
        subprocess.run(["sed", "-i", expression, str(source)], check=True)
        assert expected in source.read_text()
    text = source.read_text()
    assert "return -EBUSY;" not in text and text.count("if (nct6687_ec_reserved)") == 2


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
    assert "Unplug the computer" in script
    assert subprocess.run(["bash", "-n", "-c", script], check=False).returncode == 0


def test_the_driver_stays_on_port_0_beside_the_fan_driver():
    """nct6687 reserves port 0 but drives port 1 (base + 4..6). 1.22.10's first
    build moved bc250-vrm to port 1: same registers, no shared lock, a wedged EC."""
    from bc250cc.infrastructure.accessories import vrm_sensor

    recipe = repr(vrm_sensor.DRIVER.patches) + "".join(vrm_sensor.DRIVER.preflight)
    assert "base + 4" not in recipe and "bc250_ec_port" not in recipe
    assert "nct6687_ec_reserved = false;" in recipe


def test_repair_rebuilds_a_driver_from_the_old_recipe(monkeypatch):
    from bc250cc.infrastructure.accessories import vrm_sensor

    monkeypatch.setattr(vrm_sensor, "_installed_build", lambda: "964b83aa067b6f54")
    assert "dkms install" in vrm_sensor.repair_command("arch")
    monkeypatch.setattr(vrm_sensor, "_installed_build", lambda: vrm_sensor.DRIVER.build_id)
    assert vrm_sensor.repair_command("arch") == vrm_sensor.reload_command()
