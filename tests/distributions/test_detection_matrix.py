"""The detector and the Mesa notice, run on the os-release of real distribution images.

The files in tests/fixtures/os-release were read from the official container image
of each distribution (``podman run <image> cat /etc/os-release``), so what is
checked here is what those systems really report, not what the code expects.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bc250cc.infrastructure.debian_kernel_upgrade import debian_kernel_upgrade_state
from bc250cc.infrastructure.mesa_desktop import mesa_desktop_state, os_release_fields
from bc250cc.platform.packages.strategies.detector import (  # noqa: F401
    detect_os_info,
    read_os_release,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "os-release"

#: fixture -> package family the program should pick.
FAMILY = {
    "almalinux_9": "fedora", "almalinux_10-base_latest": "fedora", "alpine_latest": "alpine",
    "amazonlinux_2023": "fedora", "archlinux_latest": "arch", "blackarchlinux_blackarch_latest": "arch",
    "cachyos_cachyos_latest": "cachyos", "centos_centos_stream9": "fedora", "centos_centos_stream10": "fedora",
    "clearlinux_latest": "unsupported", "debian_bullseye": "debian", "debian_bookworm": "debian",
    "debian_trixie": "debian", "debian_sid": "debian", "devuan_devuan_daedalus": "debian",
    "elementary_docker_stable": "ubuntu", "fedora_42": "fedora", "fedora_43": "fedora", "fedora_44": "fedora",
    "gentoo_stage3_latest": "gentoo", "kalilinux_kali-rolling_latest": "debian",
    "linuxmintd_mint21-amd64_latest": "ubuntu", "linuxmintd_mint22-amd64_latest": "ubuntu",
    "mageia_latest": "fedora", "manjarolinux_base_latest": "manjaro", "opensuse_leap_15.6": "unsupported",
    "opensuse_tumbleweed_latest": "unsupported", "oraclelinux_9": "fedora", "parrotsec_core_latest": "debian",
    "photon_5.0": "unsupported", "rockylinux_9": "fedora", "rockylinux_rockylinux_10": "fedora",
    "ubuntu_22.04": "ubuntu", "ubuntu_24.04": "ubuntu", "ubuntu_25.10": "ubuntu", "ubuntu_26.04": "ubuntu",
    "voidlinux_voidlinux_latest": "unsupported",
}


def _raw(name: str) -> dict[str, str]:
    return os_release_fields((FIXTURES / name).read_text())


def test_every_fixture_is_covered_by_the_table():
    assert {path.name for path in FIXTURES.iterdir()} == set(FAMILY)


@pytest.mark.parametrize(("name", "family"), sorted(FAMILY.items()))
def test_the_detector_picks_the_family_of_each_real_distribution(name, family):
    info = detect_os_info(_raw(name))
    assert info.family == family, f"{name}: ID={info.distro_id!r} ID_LIKE={info.id_like}"
    assert info.distro_id == info.distro_id.strip("'\""), "no shell quotes are left on the id"


@pytest.mark.parametrize("name", sorted(n for n, f in FAMILY.items() if f == "ubuntu"))
def test_ubuntu_and_its_derivatives_are_offered_the_ppa_with_their_ubuntu_release(name):
    raw = _raw(name)
    info = detect_os_info(raw)
    state = mesa_desktop_state(
        family=info.family, distro_id=info.distro_id, mesa_version="25.2.8-0ubuntu0.24.04.4", fields=raw
    )
    assert (state["route"], state["action"]) == ("ppa", "mesa_ppa_install"), name
    assert state["codename"] == (raw.get("UBUNTU_CODENAME") or raw["VERSION_CODENAME"]), name


@pytest.mark.parametrize("name", ["fedora_42", "fedora_43", "fedora_44"])
def test_fedora_is_told_to_change_release_only_when_its_mesa_is_old(name):
    raw = _raw(name)
    info = detect_os_info(raw)
    old = mesa_desktop_state(family=info.family, distro_id=info.distro_id, mesa_version="25.3.6", fields=raw)
    new = mesa_desktop_state(family=info.family, distro_id=info.distro_id, mesa_version="26.2.4", fields=raw)
    assert old["route"] == "release" and not new["offered"]


@pytest.mark.parametrize("name", sorted(
    n for n, f in FAMILY.items() if f in {"arch", "cachyos", "manjaro", "alpine", "gentoo", "unsupported"}
))
def test_no_notice_is_made_up_for_distributions_with_no_route(name):
    raw = _raw(name)
    info = detect_os_info(raw)
    assert not mesa_desktop_state(family=info.family, distro_id=info.distro_id, mesa_version="25.0.7", fields=raw)["offered"]


@pytest.mark.parametrize("name", sorted(n for n, f in FAMILY.items() if f == "debian"))
def test_only_debian_itself_gets_the_backports_route(name):
    raw = _raw(name)
    info = detect_os_info(raw)
    state = debian_kernel_upgrade_state(
        family=info.family, distro_id=info.distro_id, kernel="6.12.111+deb13-amd64",
        codename=raw.get("VERSION_CODENAME", ""), mesa_version="25.0.7-2+deb13u1", boot_dir=Path("/nonexistent"),
    )
    assert state["offered"] is (info.distro_id == "debian" and raw.get("VERSION_CODENAME") == "trixie"), name
