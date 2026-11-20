"""Power delivery readings through the kernel, without the I2C wires.

Hexxeh's bc250-vrm driver (Liam McLoughlin, GPL-2.0-or-later) reads the
board's voltage regulator (PMIC) through the SMBus master of the fan chip
(NCT6687), so since 1.1.0 it needs none of the I2C modification's wiring. It
publishes the 12 V input, both rails' voltage, current, power and the VRM
temperatures as an ordinary hwmon device, which the Dashboard already reads
(``vrm_telemetry_reader``). Built with ``_dkms``.

The fan chip's embedded controller has two equal register windows, port 0
(base) and port 1 (base + 4). Upstream takes port 0, assuming the fan driver
uses port 1, but the nct6687 driver that Control Center installs for fan
control uses port 0 too. Loaded after it, bc250-vrm could not reserve the
port and gave up (``failed to request EC port 0x0a20``); loaded before it,
the fan driver failed instead, and once both were up they drove the same
registers without a shared lock. So the installer looks at which window a
fan driver already holds (/proc/ioports, read with sudo) and builds
bc250-vrm on the other one: port 1 as a rule, port 0 where a fan driver
already sits on port 1 (mainline nct6683 does). One line, changed after the
source's checksum and checked. The fan driver is never touched.

What must not run beside it is the BC250-Telemetry service on the wired bus:
two masters paging the same regulator mix up each other's readings, so the
installer refuses while that service is active.
"""

from __future__ import annotations

from pathlib import Path

from . import _dkms

REPOSITORY = "https://github.com/Hexxeh/bc250-vrm-dkms"
AUTHOR = "Liam McLoughlin (Hexxeh)"
REVIEWED_REVISION = "67aea0d9416eec93ec058af3ff519e81af283950"
PACKAGE = "bc250-vrm"
VERSION = "1.1.0"
MODULE = "bc250_vrm"
HWMON_NAME = "bc250_vrm"
SOURCE_DIRECTORY = Path(f"/usr/src/{PACKAGE}-{VERSION}")

SOURCES = {
    "bc250_vrm_core.c": "42f04046ff91ba65157ea8b5542239a9e4ba0fbaedd1bf82ab50dcc638745286",
    "nct6687_smbus.c": "97e173681bbea5fdf7beb4dba70c82519aad46eef915e32d5f078d9d893b6499",
    "nct6687_smbus.h": "ef2c061be372c845a2efee7856c2b4847875fbd0c6de614c08420eeb00a04c17",
    "LICENSE": "edaef632cbb643e4e7a221717a6c441a4c1a7c918e6e4d56debc3d8739b233f6",
}

FAMILIES = _dkms.FAMILIES
BOARD_NAME_PATH = Path("/sys/class/dmi/id/board_name")
BIOS_VERSION_PATH = Path("/sys/class/dmi/id/bios_version")
HWMON_ROOT = Path("/sys/class/hwmon")
TELEMETRY_SERVICE = "apu-telemetry.service"

KBUILD = "obj-m += bc250_vrm.o\nbc250_vrm-y := bc250_vrm_core.o nct6687_smbus.o\n"

DRIVER = _dkms.Driver(
    title="Power delivery readings",
    package=PACKAGE,
    version=VERSION,
    module=MODULE,
    hwmon=HWMON_NAME,
    repository=REPOSITORY,
    revision=REVIEWED_REVISION,
    sources=SOURCES,
    kbuild=KBUILD,
    # The CPU VRM temperature: the one value every board reports at idle.
    reading=("temp1_input", 1000, "°C"),
    preflight=(
        # The fan chip has two equal EC windows: take the one no fan driver holds.
        "bc250_ec_port=1",
        "if sudo grep -qE '^[[:space:]]*0a24-0a27 : nct668[0-9]$' /proc/ioports; then bc250_ec_port=0; fi",
        'echo "bc250-vrm uses EC port $bc250_ec_port of the fan chip; the fan driver keeps the other one."',
        f"if systemctl is-active --quiet {TELEMETRY_SERVICE} 2>/dev/null; then "
        "echo 'ERROR: the BC250-Telemetry service is running and reads the same regulator over the I2C "
        "modification. Two readers on one regulator mix up each other'\"'\"'s readings: remove the service "
        "in Settings › Telemetry, then press Install again.'; exit 68; fi",
    ),
    patches=(
        (
            "nct6687_smbus.c",
            r"s|^\tnct6687_ec_base = base;$|\tnct6687_ec_base = base + 4; /* EC port 1: the fan driver owns port 0 */|",
            "nct6687_ec_base = base + 4;",
            '[ "$bc250_ec_port" = 1 ]',
        ),
    ),
    silent_hint=(
        "The voltage regulator did not answer through the fan chip. Send a report from Support with "
        "these lines; the rest of the board is not affected."
    ),
)
DKMS_CONF = DRIVER.dkms_conf()


def cpu_vrm_celsius() -> float | None:
    return _dkms.hwmon_reading(HWMON_ROOT, HWMON_NAME, "temp1_input", 1000)


def _module_file() -> str:
    return _dkms.module_file(MODULE)


def inventory(family: str) -> dict:
    """Read-only state for the card and the power readings window."""
    family = str(family or "").strip().lower()
    board = _dkms.read(BOARD_NAME_PATH) == _dkms.BOARD_NAME
    reading = cpu_vrm_celsius()
    return {
        "supported": family in FAMILIES and board,
        "version": VERSION,
        "device": board,
        "reading": reading,
        "state": _dkms.state(
            family=family, board=board, bios_ok=True,
            built_in=_dkms.built_into_kernel(_module_file()),
            installed=SOURCE_DIRECTORY.is_dir(), reading=reading,
            current=_dkms.is_current(DRIVER, _installed_build(), reading),
        ),
    }


def _installed_build() -> str:
    return _dkms.read(SOURCE_DIRECTORY / _dkms.BUILD_MARKER).split(" ")[0]


def install_command(family: str) -> str:
    return _dkms.install_command(
        DRIVER, family, board_name_path=BOARD_NAME_PATH, bios_version_path=BIOS_VERSION_PATH,
        hwmon_root=HWMON_ROOT,
    )


def remove_command(family: str) -> str:
    return _dkms.remove_command(DRIVER, family, after=(
        "echo 'OK: the power delivery driver was removed. The Dashboard stops showing the rails until it is "
        "installed again.'",
    ))
