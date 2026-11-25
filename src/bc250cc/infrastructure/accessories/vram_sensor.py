"""VRAM (GDDR6) temperature through the kernel, for Arch-based systems.

Hexxeh's bc250-memory driver (Liam McLoughlin, GPL-2.0-or-later, with
pan-Rijovich's MIT SMU payload) reads the eight GDDR6 chips through the SMU
and publishes them as an ordinary hwmon sensor: ``sensors``, MangoHud,
CoolerControl and this app all see it. Built with ``_dkms``.

The driver patches the SMU firmware in memory at fixed addresses, and
upstream checks only that the BIOS allows it. The payload was reviewed for
one BIOS (P3.00), the same gate the app's own GDDR6 reading uses, so the
installer refuses any other.
"""

from __future__ import annotations

from pathlib import Path

from ..memory_autoload import DENYLIST
from . import _dkms

REPOSITORY = "https://github.com/Hexxeh/bc250-memory-dkms"
AUTHOR = "Liam McLoughlin (Hexxeh)"
REVIEWED_REVISION = "de4740c9b60b93c36f3ff6c85789e4aea3cefe31"
PACKAGE = "bc250-memory"
VERSION = "1.0.0"
MODULE = "bc250_memory"
HWMON_NAME = "bc250_memory"
SOURCE_DIRECTORY = Path(f"/usr/src/{PACKAGE}-{VERSION}")

#: Every upstream file that ends up in the build, with its reviewed SHA-256.
SOURCES = {
    "bc250_memory.c": "3df821cf60c46f45b84149b12b5aa792e0fd076c8acaa1768d3b1b0a1b3a8f85",
    "bc250_smu.c": "39c59b3232fae15060a8b44bdc7ff9635bee8da683345aff648feb5e62c242d6",
    "bc250_smu.h": "adec1d93e94c943ae93a8d113e0dc3c4adb6eb0f764544a55d8b00da527bd661",
    "bc250_smu_patch.c": "f3b2306162cdfdd26e85547f304b936cbfec13fe6ab232780c21330274406301",
    "LICENSE": "edaef632cbb643e4e7a221717a6c441a4c1a7c918e6e4d56debc3d8739b233f6",
}

FAMILIES = _dkms.FAMILIES
BOARD_NAME = _dkms.BOARD_NAME
#: The BIOS the SMU payload was reviewed against (gddr6_memory_temp_repository).
SUPPORTED_BIOS = frozenset({"p3.0", "p3.00"})

BOARD_NAME_PATH = Path("/sys/class/dmi/id/board_name")
BIOS_VERSION_PATH = Path("/sys/class/dmi/id/bios_version")
HWMON_ROOT = Path("/sys/class/hwmon")

KBUILD = "obj-m += bc250_memory.o\n"
MAKEFILE = _dkms.MAKEFILE

DRIVER = _dkms.Driver(
    title="VRAM temperature",
    package=PACKAGE,
    version=VERSION,
    module=MODULE,
    hwmon=HWMON_NAME,
    repository=REPOSITORY,
    revision=REVIEWED_REVISION,
    sources=SOURCES,
    kbuild=KBUILD,
    reading=("temp1_input", 1000, "°C"),
    bios=SUPPORTED_BIOS,
    silent_hint=(
        '"SMU debug access is locked" means this BIOS does not let the driver patch the SMU. Press '
        "Monitor live on the dashboard once after each power-on: Control Center patches the SMU and "
        "reloads the driver, which then reads until the board is switched off."
    ),
)
DKMS_CONF = DRIVER.dkms_conf()


def hotspot_celsius() -> float | None:
    """The hottest chip right now, or None when the driver is not reading."""
    return _dkms.hwmon_reading(HWMON_ROOT, HWMON_NAME, "temp1_input", 1000)


def _module_file() -> str:
    return _dkms.module_file(MODULE)


def built_into_kernel(filename: str | None = None) -> bool:
    """The running kernel ships the driver itself (MastaG's kernels do)."""
    return _dkms.built_into_kernel(_module_file() if filename is None else filename)


def inventory(family: str) -> dict:
    """Read-only state for the card and the power readings window."""
    family = str(family or "").strip().lower()
    board = _dkms.read(BOARD_NAME_PATH) == BOARD_NAME
    bios = _dkms.read(BIOS_VERSION_PATH)
    bios_ok = bios.lower() in SUPPORTED_BIOS
    reading = hotspot_celsius()
    return {
        "supported": family in FAMILIES and board and bios_ok,
        "version": VERSION,
        "device": board,
        "bios": bios,
        "bios_supported": bios_ok,
        "hotspot_c": reading,
        "reading": reading,
        "state": _dkms.state(
            family=family, board=board, bios_ok=bios_ok, built_in=built_into_kernel(),
            installed=SOURCE_DIRECTORY.is_dir(), reading=reading,
            current=_dkms.is_current(
                DRIVER, _dkms.read(SOURCE_DIRECTORY / _dkms.BUILD_MARKER).split(" ")[0], reading,
            ),
        ),
    }


def install_command(family: str) -> str:
    command = _dkms.install_command(
        DRIVER, family, board_name_path=BOARD_NAME_PATH, bios_version_path=BIOS_VERSION_PATH,
        hwmon_root=HWMON_ROOT,
    )
    # Installing it is asking for it at boot again, after "Stop loading at boot".
    return f"{command}\nsudo rm -f -- {DENYLIST}"


def remove_command(family: str) -> str:
    return _dkms.remove_command(DRIVER, family, after=(
        f"sudo rm -f -- {DENYLIST}",
        "echo 'OK: the VRAM temperature driver was removed. The SMU patch it applied lasts until the next full "
        "power-off; nothing reads it meanwhile.'",
    ))
