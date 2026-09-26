import subprocess
from pathlib import Path

import pytest

from bc250cc.infrastructure.drivers_repository import (
    DriversRepository,
    build_driver_support_command,
    supported_driver_components,
)


@pytest.mark.parametrize(
    ("family", "manager", "package_command", "service_command"),
    (
        ("arch", "openrc", "pacman -S --needed", "rc-service bluetooth start"),
        (
            "arch",
            "systemd",
            "pacman -S --needed",
            "systemctl enable --now bluetooth.service",
        ),
        (
            "ubuntu",
            "systemd",
            "apt-get install --no-install-recommends",
            "systemctl enable --now bluetooth.service",
        ),
        (
            "fedora",
            "systemd",
            "dnf install -y",
            "systemctl enable --now bluetooth.service",
        ),
    ),
)
def test_connectivity_package_manager_and_init_backend_are_independent(
    family, manager, package_command, service_command
):
    command = build_driver_support_command("connectivity", family, manager)
    assert package_command in command
    assert service_command in command
    assert "git clone" not in command
    assert "curl " not in command
    assert "modprobe" not in command


def test_artix_openrc_printing_uses_pacman_and_openrc_without_systemctl():
    command = build_driver_support_command("printing", "arch", "openrc")
    assert "pacman -S --needed" in command
    assert "rc-update add cupsd default" in command
    assert "rc-service cupsd start" in command
    assert "systemctl" not in command


def test_unknown_init_installs_packages_but_never_invents_persistence():
    command = build_driver_support_command("printing", "debian", "unknown")
    assert "apt-get install" in command
    assert "service persistence is not automated for unknown" in command
    assert "systemctl" not in command
    assert "rc-service" not in command


def test_bazzite_layers_only_missing_packages_and_requests_reboot_conditionally():
    command = build_driver_support_command("printing", "bazzite", "systemd")
    assert "rpm -q" in command
    assert 'rpm-ostree install --idempotent "${missing[@]}"' in command
    assert "BC250_REBOOT_REQUIRED=1" in command
    assert "systemctl" not in command


def test_printing_workflow_never_upgrades_or_removes_existing_configuration():
    for family in ("arch", "ubuntu", "fedora", "bazzite"):
        command = build_driver_support_command("printing", family, "systemd")
        assert "pacman -Syu" not in command
        assert " lpadmin " not in command
        assert " remove " not in command
        assert " uninstall " not in command


def test_unsupported_distribution_and_component_fail_closed():
    assert supported_driver_components("steamos") == ()
    with pytest.raises(RuntimeError):
        build_driver_support_command("printing", "steamos", "systemd")
    with pytest.raises(ValueError):
        build_driver_support_command("aic8800", "arch", "systemd")


@pytest.mark.parametrize(
    "family", ("arch", "manjaro", "cachyos", "fedora", "bazzite", "ubuntu", "debian")
)
@pytest.mark.parametrize(
    "manager", ("systemd", "openrc", "runit", "s6", "dinit", "sysvinit", "unknown")
)
@pytest.mark.parametrize("component", ("connectivity", "printing"))
def test_every_generated_driver_workflow_is_valid_bash(family, manager, component):
    command = build_driver_support_command(component, family, manager)
    parsed = subprocess.run(
        ["bash", "-n"], input=command, text=True, capture_output=True, check=False
    )
    assert parsed.returncode == 0, parsed.stderr


def test_network_inventory_reports_the_actual_bound_kernel_driver(tmp_path: Path):
    root = tmp_path / "net"
    interface = root / "wlan0"
    device = interface / "device"
    driver = tmp_path / "drivers" / "mt7921u"
    driver.mkdir(parents=True)
    device.mkdir(parents=True)
    (device / "driver").symlink_to(driver, target_is_directory=True)
    (interface / "wireless").mkdir()
    (interface / "address").write_text("00:11:22:33:44:55\n", encoding="utf-8")
    (interface / "operstate").write_text("up\n", encoding="utf-8")

    assert DriversRepository._network_inventory(root) == [
        {
            "name": "wlan0",
            "kind": "wifi",
            "driver": "mt7921u",
            "address": "00:11:22:33:44:55",
            "state": "up",
        }
    ]


def test_usb_printer_class_is_read_from_sibling_interface_directory(tmp_path: Path):
    device = tmp_path / "1-2"
    interface = tmp_path / "1-2:1.0"
    device.mkdir()
    interface.mkdir()
    (device / "idVendor").write_text("1234\n", encoding="utf-8")
    (device / "idProduct").write_text("5678\n", encoding="utf-8")
    (device / "product").write_text("Test Printer\n", encoding="utf-8")
    (interface / "bInterfaceClass").write_text("07\n", encoding="utf-8")

    inventory = DriversRepository._usb_inventory(tmp_path)
    assert inventory[0]["id"] == "1234:5678"
    assert inventory[0]["printer"] is True


# ----------------------------------------------------- Debian and Ubuntu
#
# Asked to validate: both families had catalogs, but one package a release
# lacked (ipp-usb before Debian 11, firmware-mediatek before 13) failed the
# whole apt-get install, and Debian got no Wi-Fi or Bluetooth firmware at
# all because it lives in non-free-firmware.


@pytest.mark.parametrize("family", ("ubuntu", "debian"))
@pytest.mark.parametrize("component", ("connectivity", "printing"))
def test_apt_installs_only_what_the_release_offers(family, component):
    command = build_driver_support_command(component, family, "systemd")
    assert "apt-cache policy" in command
    assert 'apt-get install --no-install-recommends "${resolved[@]}"' in command
    assert "skipped:" in command
    # Resolving comes after the index refresh it depends on.
    assert command.index("apt-get update") < command.index("bc250_resolve ")


def test_debian_connectivity_offers_the_non_free_firmware_and_asks_before_adding_a_source():
    command = build_driver_support_command("connectivity", "debian", "systemd")
    for package in ("firmware-realtek", "firmware-iwlwifi", "firmware-mediatek", "firmware-atheros"):
        assert package in command
    assert "read -r -p" in command
    # The only write to APT's configuration is its own file, in the yes branch.
    source = "/etc/apt/sources.list.d/bc250-non-free-firmware.sources"
    assert command.count(f"tee {source}") == 1
    yes_branch = command[command.index("[yY]*)"):command.index("*) echo")]
    assert f"tee {source}" in yes_branch
    assert "/etc/apt/sources.list " not in command and "sed -i" not in command
    # Only on Debian itself; derivatives get the explanation alone.
    assert '[ "$distro" = debian ]' in command


def test_ubuntu_and_printing_never_touch_apt_sources():
    for component, family in (("connectivity", "ubuntu"), ("printing", "debian"), ("printing", "ubuntu")):
        command = build_driver_support_command(component, family, "systemd")
        assert "sources.list" not in command
        assert "read -r -p" not in command
