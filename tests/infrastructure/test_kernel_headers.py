"""Kernel headers and DKMS: detected per distribution family, repaired in one workflow.

2026-11-21: a driver install pulled linux-headers 7.3.5 onto linux 7.3.4; the
DKMS hook then dropped every module built for the running kernel (fans too).
"""

from __future__ import annotations

import subprocess

import pytest

from bc250cc.infrastructure import kernel_headers as headers

KERNEL = "7.3.4-arch1-2"


def _release(tmp_path, text):
    path = tmp_path / "os-release"
    path.write_text(text)
    return path


@pytest.mark.parametrize("text, manager", [
    ("ID=arch\n", "pacman"),
    ("ID=cachyos\nID_LIKE=arch\n", "pacman"),
    ('ID=manjaro\nID_LIKE="arch"\n', "pacman"),
    ("ID=fedora\n", "dnf"),
    ("ID=nobara\nID_LIKE=fedora\n", "dnf"),
    ("ID=ubuntu\nID_LIKE=debian\n", "apt"),
    ('ID=linuxmint\nID_LIKE="ubuntu debian"\n', "apt"),
    ("ID=debian\n", "apt"),
    ("ID=steamos\nID_LIKE=arch\n", ""),
    ("ID=opensuse-tumbleweed\n", ""),
])
def test_the_package_manager_follows_the_distribution(tmp_path, text, manager):
    assert headers.package_manager(_release(tmp_path, text), tmp_path / "no-ostree") == manager


def test_an_atomic_fedora_is_left_alone(tmp_path):
    booted = tmp_path / "ostree-booted"
    booted.touch()
    assert headers.package_manager(_release(tmp_path, "ID=bazzite\nID_LIKE=fedora\n"), booted) == ""


def _state(tmp_path, *, build=True, tree=True, dkms=None, release="ID=fedora\n"):
    modules = tmp_path / "modules"
    if tree:
        (modules / KERNEL).mkdir(parents=True)
        if build:
            (modules / KERNEL / "build").mkdir()
    dkms_root = tmp_path / "dkms"
    for module, kernels in (dkms or {}).items():
        for kernel in kernels:
            (dkms_root / module / "1.0" / kernel).mkdir(parents=True)
        (dkms_root / module / "1.0").mkdir(parents=True, exist_ok=True)
    return headers.headers_state(
        KERNEL, modules_root=modules, dkms_root=dkms_root,
        os_release=_release(tmp_path, release), ostree_booted=tmp_path / "no-ostree",
    )


def test_matching_headers_with_every_module_built_are_ready(tmp_path):
    assert _state(tmp_path, dkms={"nct6687d": [KERNEL]})["state"] == headers.OK


def test_missing_headers_are_reported(tmp_path):
    assert _state(tmp_path, build=False)["state"] == headers.MISSING


def test_a_module_not_built_for_this_kernel_is_named(tmp_path):
    state = _state(tmp_path, dkms={"nct6687d": ["6.0-old"], "bc250-vrm": [KERNEL]})
    assert state["state"] == headers.MODULES_MISSING and state["modules"] == ("nct6687d",)


def test_a_replaced_running_kernel_asks_for_a_restart(tmp_path):
    assert _state(tmp_path, tree=False)["state"] == headers.REBOOT_PENDING


def test_on_arch_headers_of_another_version_are_a_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(headers, "_arch_versions",
                        lambda kernel, root: ("linux", "7.3.4.arch1-2", "7.3.5.arch1-1"))
    state = _state(tmp_path, build=False, release="ID=arch\n")
    assert state["state"] == headers.MISMATCH
    assert state["kernel_package"] == "linux 7.3.4.arch1-2" and state["headers"] == "linux-headers 7.3.5.arch1-1"


@pytest.mark.parametrize("manager", ["pacman", "dnf", "apt"])
def test_each_repair_is_valid_shell_and_rebuilds_dkms_for_the_running_kernel(manager):
    script = headers.repair_command(manager)
    assert subprocess.run(["bash", "-n", "-c", script], check=False).returncode == 0
    assert 'dkms autoinstall -k "$bc250_kernel"' in script


def test_arch_repair_never_installs_newer_headers_alone():
    script = headers.repair_command("pacman")
    # The exact version when the repository has it; otherwise kernel and headers together.
    assert 'sudo pacman -S --noconfirm "$bc250_owner-headers"' in script
    assert "sudo pacman -Syu --noconfirm" in script
    assert script.index('[ "$bc250_repo" = "$bc250_kver" ]') < script.index("sudo pacman -Syu")


def test_fedora_and_debian_install_the_running_kernels_own_headers():
    assert 'kernel-devel-$bc250_kernel' in headers.repair_command("dnf")
    assert 'linux-headers-$bc250_kernel' in headers.repair_command("apt")


def test_no_repair_where_it_does_not_apply():
    with pytest.raises(ValueError):
        headers.repair_command("")


def test_a_driver_install_checks_the_headers_before_installing_anything():
    """The DKMS installer only adds the headers when the repository has the running kernel's version."""
    from bc250cc.infrastructure.accessories import vrm_sensor

    script = vrm_sensor.install_command("arch")
    assert "bc250_packages=(dkms git base-devel)" in script
    assert script.index('if [ "$bc250_repo" != "$bc250_kver" ]') < script.index("sudo pacman -S --needed")
    assert "Compatibility › Kernel headers" in script
