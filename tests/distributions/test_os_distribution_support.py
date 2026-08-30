from pathlib import Path

import pytest

from bc250cc.platform.packages.strategies.alpine_repository import AlpineRepository
from bc250cc.platform.packages.strategies.arch_repository import (
    ArchRepository,
    CachyOSRepository,
    ManjaroRepository,
)
from bc250cc.platform.packages.strategies.bazzite_repository import BazziteRepository
from bc250cc.platform.packages.strategies.debian_repository import (
    DebianRepository,
    UbuntuRepository,
)
from bc250cc.platform.packages.strategies.detector import detect_os_info
from bc250cc.platform.packages.strategies.factory import create_os_repository
from bc250cc.platform.packages.strategies.fedora_repository import FedoraRepository
from bc250cc.platform.packages.strategies.gentoo_repository import GentooRepository
from bc250cc.platform.packages.strategies.steamos_repository import SteamOSRepository
from bc250cc.platform.packages.strategies.unsupported_repository import (
    UnsupportedOSRepository,
)

DISTROS = (
    ({"ID": "arch", "PRETTY_NAME": "Arch Linux"}, False, "arch", ArchRepository),
    (
        {"ID": "artix", "PRETTY_NAME": "Artix Linux (OpenRC)"},
        False,
        "arch",
        ArchRepository,
    ),
    (
        {"ID": "manjaro", "ID_LIKE": "arch", "PRETTY_NAME": "Manjaro"},
        False,
        "manjaro",
        ManjaroRepository,
    ),
    (
        {"ID": "cachyos", "ID_LIKE": "arch", "PRETTY_NAME": "CachyOS"},
        False,
        "cachyos",
        CachyOSRepository,
    ),
    (
        {"ID": "debian", "PRETTY_NAME": "Debian GNU/Linux"},
        False,
        "debian",
        DebianRepository,
    ),
    (
        {"ID": "devuan", "PRETTY_NAME": "Devuan GNU/Linux (OpenRC)"},
        False,
        "debian",
        DebianRepository,
    ),
    (
        {"ID": "pop", "ID_LIKE": "ubuntu debian", "PRETTY_NAME": "Pop!_OS"},
        False,
        "ubuntu",
        UbuntuRepository,
    ),
    (
        {"ID": "ubuntu", "ID_LIKE": "debian", "PRETTY_NAME": "Ubuntu"},
        False,
        "ubuntu",
        UbuntuRepository,
    ),
    (
        {
            "ID": "linuxmint",
            "ID_LIKE": "ubuntu debian",
            "PRETTY_NAME": "Linux Mint 22.3",
        },
        False,
        "ubuntu",
        UbuntuRepository,
    ),
    (
        {"ID": "fedora", "PRETTY_NAME": "Fedora Linux"},
        False,
        "fedora",
        FedoraRepository,
    ),
    (
        {"ID": "nobara", "ID_LIKE": "fedora", "PRETTY_NAME": "Nobara Linux"},
        False,
        "fedora",
        FedoraRepository,
    ),
    (
        {
            "ID": "bazzite",
            "ID_LIKE": "fedora",
            "VARIANT_ID": "bazzite",
            "PRETTY_NAME": "Bazzite",
        },
        True,
        "bazzite",
        BazziteRepository,
    ),
    (
        {
            "ID": "fedora",
            "ID_LIKE": "fedora",
            "VARIANT_ID": "kinoite",
            "PRETTY_NAME": "Fedora Kinoite",
        },
        True,
        "bazzite",
        BazziteRepository,
    ),
    (
        {"ID": "steamos", "ID_LIKE": "arch", "PRETTY_NAME": "SteamOS"},
        False,
        "steamos",
        SteamOSRepository,
    ),
    (
        {"ID": "gentoo", "PRETTY_NAME": "Gentoo Linux"},
        False,
        "gentoo",
        GentooRepository,
    ),
    (
        {"ID": "funtoo", "ID_LIKE": "gentoo", "PRETTY_NAME": "Funtoo Linux"},
        False,
        "gentoo",
        GentooRepository,
    ),
    (
        {"ID": "alpine", "PRETTY_NAME": "Alpine Linux"},
        False,
        "alpine",
        AlpineRepository,
    ),
)


class FakeHost:
    def __init__(self, release, tmp_path, has_rpm_ostree):
        self.release = release
        self.tmp_path = tmp_path
        self.has_rpm_ostree = has_rpm_ostree

    def _os_release(self):
        return self.release

    def _command_path(self, name):
        if name == "rpm-ostree" and self.has_rpm_ostree:
            return "/usr/bin/rpm-ostree"
        return ""

    def _tool_dir(self):
        return self.tmp_path / "ResourceTools"


@pytest.mark.parametrize(
    ("release", "has_rpm_ostree", "family", "repository_type"),
    DISTROS,
)
def test_supported_distribution_selects_its_isolated_strategy(
    tmp_path,
    release,
    has_rpm_ostree,
    family,
    repository_type,
):
    info = detect_os_info(release, has_rpm_ostree=has_rpm_ostree)
    repository = create_os_repository(
        FakeHost(release, tmp_path, has_rpm_ostree)
    )

    assert info.family == family
    assert isinstance(repository, repository_type)
    assert repository.info.family == family
    command = repository.prepare_dependencies_command("runtime")
    assert "prepare-dependencies.sh" in command
    assert f"BC250_OS_FAMILY={family}" in command
    assert Path(repository.scripts_root / repository.dependency_script).is_file()
    assert Path(repository.scripts_root / repository.fan_script).is_file()


def test_unknown_distribution_fails_with_a_clear_message(tmp_path):
    release = {"ID": "unknown-linux", "PRETTY_NAME": "Unknown Linux"}
    repository = create_os_repository(FakeHost(release, tmp_path, False))

    assert isinstance(repository, UnsupportedOSRepository)
    with pytest.raises(RuntimeError, match="Supported families"):
        repository.prepare_dependencies_command()


def test_explicit_empty_release_is_not_replaced_by_the_host_distribution():
    info = detect_os_info({})

    assert info.family == "unsupported"
    assert info.distro_id == ""


@pytest.mark.parametrize(
    "release",
    (
        {"ID": "bazzite", "ID_LIKE": "fedora", "PRETTY_NAME": "Bazzite"},
        {"ID": "fedora", "VARIANT_ID": "kinoite", "PRETTY_NAME": "Fedora Kinoite"},
        {"ID": "fedora", "VARIANT_ID": "silverblue", "PRETTY_NAME": "Fedora Silverblue"},
    ),
)
def test_known_atomic_images_never_downgrade_to_mutable_fedora_without_rpm_ostree(release):
    info = detect_os_info(release, has_rpm_ostree=False)

    assert info.family == "bazzite"
    assert info.immutable is True
