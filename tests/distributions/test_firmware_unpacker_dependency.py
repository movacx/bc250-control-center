"""Prepare dependencies installs a 7z unpacker for the Firmware page.

The BIOS images are 7z archives. Arch and SteamOS always have bsdtar, because
pacman depends on libarchive; a fresh Ubuntu had neither 7-Zip nor bsdtar, and
the Firmware page asked for one after dependencies were already prepared.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "packaging" / "common" / "os-scripts"


def test_debian_and_ubuntu_install_bsdtar_without_making_it_fatal():
    text = (SCRIPTS / "debian" / "prepare-dependencies.sh").read_text(encoding="utf-8")
    assert "runtime_optional_tools=(libarchive-tools)" in text
    assert 'apt-get install -y "${runtime_optional_tools[@]}" || warn' in text
    assert '"${runtime_optional_tools[@]}" pkexec' in text  # listed in the plan


def test_fedora_installs_bsdtar_without_making_it_fatal():
    text = (SCRIPTS / "fedora" / "prepare-dependencies.sh").read_text(encoding="utf-8")
    assert "dnf install -y bsdtar || warn" in text
    assert "PLAN optional=glx-utils bsdtar" in text


def test_the_firmware_store_accepts_bsdtar():
    from bc250cc.infrastructure.firmware.store import SEVEN_ZIP_TOOLS

    assert "bsdtar" in SEVEN_ZIP_TOOLS
