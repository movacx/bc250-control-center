"""VRAM temperature through Hexxeh's bc250-memory driver, built with DKMS.

The card offers it on Arch-based systems only, on the BIOS its SMU payload
was reviewed for, and leaves MastaG's kernels (which carry the driver) alone.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from bc250cc.infrastructure import accessories
from bc250cc.infrastructure.accessories import vram_sensor


@pytest.fixture
def board(tmp_path, monkeypatch):
    """A BC-250 on BIOS P3.00 with no driver anywhere; each test changes one thing."""
    name, bios = tmp_path / "board_name", tmp_path / "bios_version"
    name.write_text("AMD BC-250\n")
    bios.write_text("P3.00\n")
    hwmon = tmp_path / "hwmon"
    hwmon.mkdir()
    monkeypatch.setattr(vram_sensor, "BOARD_NAME_PATH", name)
    monkeypatch.setattr(vram_sensor, "BIOS_VERSION_PATH", bios)
    monkeypatch.setattr(vram_sensor, "HWMON_ROOT", hwmon)
    monkeypatch.setattr(vram_sensor, "SOURCE_DIRECTORY", tmp_path / "usr-src")
    monkeypatch.setattr(vram_sensor, "_module_file", lambda: "")
    return tmp_path


def _sensor(root, celsius):
    device = root / "hwmon" / "hwmon7"
    device.mkdir()
    (device / "name").write_text("bc250_memory\n")
    (device / "temp1_input").write_text(f"{int(celsius * 1000)}\n")


@pytest.mark.parametrize("family", ["arch", "cachyos", "manjaro"])
def test_an_arch_based_bc250_can_install_it(board, family):
    assert vram_sensor.inventory(family)["state"] == "not-installed"


@pytest.mark.parametrize("family", ["fedora", "bazzite", "ubuntu", "debian", "steamos"])
def test_other_distributions_are_told_it_is_not_for_them(board, family):
    assert vram_sensor.inventory(family)["state"] == "unsupported"


def test_another_bios_is_refused_before_anything_is_built(board):
    (board / "bios_version").write_text("P5.00\n")
    info = vram_sensor.inventory("cachyos")
    assert info["state"] == "unsupported" and not info["bios_supported"]


def test_a_kernel_that_carries_the_driver_is_left_alone(board, monkeypatch):
    monkeypatch.setattr(
        vram_sensor, "_module_file",
        lambda: "/lib/modules/7.3.4-cachyos-bc250/kernel/drivers/hwmon/bc250_memory.ko.zst",
    )
    assert vram_sensor.inventory("cachyos")["state"] == "managed-elsewhere"


def test_a_dkms_build_is_ours_not_the_kernels():
    assert not vram_sensor.built_into_kernel(
        "/usr/lib/modules/6.17.8-arch1-1/updates/dkms/bc250_memory.ko.zst"
    )


def test_installed_and_reading_is_active_with_its_temperature(board):
    (board / "usr-src").mkdir()
    (board / "usr-src" / "bc250-control-center.build").write_text(vram_sensor.DRIVER.build_id + "\n")
    assert vram_sensor.inventory("arch")["state"] == "installed"
    _sensor(board, 44)
    info = vram_sensor.inventory("arch")
    assert info["state"] == "active" and info["hotspot_c"] == 44


def test_it_is_part_of_the_accessory_inventory(board, tmp_path):
    assert "vram_sensor" in accessories.ACCESSORIES
    command = accessories.accessory_command("vram_sensor", "install", family="cachyos", tool_dir=tmp_path)
    assert "bc250-memory" in command


def test_the_installer_checks_board_bios_revision_and_every_file():
    script = vram_sensor.install_command("cachyos")
    assert "AMD BC-250" in script and "p3.00" in script
    assert f"rev-parse HEAD)\" = {vram_sensor.REVIEWED_REVISION}" in script
    for name, digest in vram_sensor.SOURCES.items():
        assert digest in script and name in script
    # The checks come before anything is written outside the stage.
    assert script.index("sha256sum --check") < script.index("sudo dkms add")
    # MastaG's kernel already has it: the installer stops before building.
    assert script.index("*/updates/*") < script.index("sudo pacman -S")


def test_upstreams_fixed_clang_build_is_replaced():
    script = vram_sensor.install_command("arch")
    assert "LLVM=1 modules" not in vram_sensor.DKMS_CONF
    assert "CONFIG_CC_IS_CLANG" in vram_sensor.MAKEFILE
    assert "grep -qi clang /proc/version" in script


@pytest.mark.skipif(shutil.which("make") is None, reason="make is not installed")
@pytest.mark.parametrize(("clang", "flag"), [(True, True), (False, False)])
def test_the_makefile_uses_the_compiler_the_kernel_was_built_with(tmp_path, clang, flag):
    kernel = tmp_path / "kernel"
    kernel.mkdir()
    (kernel / ".config").write_text("CONFIG_CC_IS_CLANG=y\n" if clang else "CONFIG_CC_IS_GCC=y\n")
    module = tmp_path / "module"
    module.mkdir()
    (module / "Makefile").write_text(vram_sensor.MAKEFILE)
    # Ask make for the flag it would pass, without building anything.
    chosen = subprocess.run(
        ["make", "--eval=bc250-flag: ; @echo $(LLVM_FLAG)", "bc250-flag", f"KDIR={kernel}"],
        cwd=module, capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert chosen == ("LLVM=1" if flag else "")


@pytest.mark.parametrize("family", ["fedora", "ubuntu"])
def test_other_families_get_a_plain_answer(family):
    with pytest.raises(RuntimeError, match="Arch"):
        vram_sensor.install_command(family)


@pytest.mark.parametrize("action", ["install", "remove"])
def test_the_scripts_parse(tmp_path, action):
    script = (vram_sensor.install_command if action == "install" else vram_sensor.remove_command)("manjaro")
    path = tmp_path / "script.sh"
    path.write_text(script)
    subprocess.run(["bash", "-n", str(path)], check=True)


def test_removing_takes_the_build_and_the_source_away():
    script = vram_sensor.remove_command("cachyos")
    assert "dkms remove bc250-memory/1.0.0 --all" in script
    assert str(vram_sensor.SOURCE_DIRECTORY) in script
