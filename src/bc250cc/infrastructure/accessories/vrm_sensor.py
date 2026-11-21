"""Power delivery readings through the kernel, without the I2C wires.

Hexxeh's bc250-vrm driver (Liam McLoughlin, GPL-2.0-or-later) reads the
board's voltage regulator (PMIC) through the SMBus master of the fan chip
(NCT6687), so since 1.1.0 it needs none of the I2C modification's wiring. It
publishes the 12 V input, both rails' voltage, current, power and the VRM
temperatures as an ordinary hwmon device, which the Dashboard already reads
(``vrm_telemetry_reader``). Built with ``_dkms``.

The fan chip's embedded controller has two equal register windows, port 0
(base) and port 1 (base + 4). Upstream takes port 0, and that is right: the
nct6687 fan driver reserves the port 0 range but drives port 1 (all its
accesses are at base + 4, + 5, + 6). 1.22.10's first build went by the
reservation, moved bc250-vrm to port 1 and so put both drivers on the same
registers without a shared lock: readings turned to one repeated word (797
everywhere), then the EC's SMBus master stopped answering (2026-11-21). So
bc250-vrm stays on port 0, and the fan driver's idle reservation of it no
longer stops it loading (it is noted, and not released on unload). Patched
after the source's checksum and checked. The fan driver is never touched.

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
        f"if systemctl is-active --quiet {TELEMETRY_SERVICE} 2>/dev/null; then "
        "echo 'ERROR: the BC250-Telemetry service is running and reads the same regulator over the I2C "
        "modification. Two readers on one regulator mix up each other'\"'\"'s readings: remove the service "
        "in Settings › Telemetry, then press Install again.'; exit 68; fi",
    ),
    # Port 0, as upstream; only the fan driver's idle reservation of it is
    # made non-fatal, and released only if this driver took it.
    patches=(
        (
            "nct6687_smbus.c",
            r"s|^static u16 nct6687_ec_base = NCT6687_EC_BASE_DEFAULT;$|&\nstatic bool nct6687_ec_reserved = true;|",
            "static bool nct6687_ec_reserved = true;",
        ),
        (
            "nct6687_smbus.c",
            r"/failed to request EC port/{s|pr_err(\"nct6687_smbus: failed to request EC port 0x%04x\\n\"|"
            r"pr_info(\"nct6687_smbus: EC port 0x%04x is reserved by the fan driver, which uses the other port\\n\"|;"
            r"n;s|^\t\treturn -EBUSY;$|\t\tnct6687_ec_reserved = false;|}",
            "nct6687_ec_reserved = false;",
        ),
        (
            "nct6687_smbus.c",
            r"s|^\(\t*\)release_region(nct6687_ec_base, NCT6687_EC_PORT_LEN);$|\1if (nct6687_ec_reserved)\n\1\trelease_region(nct6687_ec_base, NCT6687_EC_PORT_LEN);|",
            "if (nct6687_ec_reserved)",
        ),
    ),
    silent_hint=(
        "The voltage regulator did not answer through the fan chip. Send a report from Support with "
        "these lines; the rest of the board is not affected."
    ),
)
DKMS_CONF = DRIVER.dkms_conf()


def cpu_vrm_celsius() -> float | None:
    """The CPU rail's temperature, or None when the regulator gave an impossible word."""
    reading = _dkms.hwmon_reading(HWMON_ROOT, HWMON_NAME, "temp1_input", 1000)
    return reading if reading is not None and 1.0 <= reading <= 150.0 else None


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


def reload_command() -> str:
    """Restart a wedged bc250_vrm, then check that the readings are real again.

    The driver talks to the regulator through the fan chip's SMBus master;
    when that master wedges it hands back one stale word for every register
    (2026-11-21: 797 for VIN, VOUT, IOUT and TEMP alike). Unloading and
    loading the driver resets it. Plausible means what a BC-250 rail can
    produce; when it still is not, only a full power cycle resets the chip.
    """
    module = MODULE
    return "\n".join((
        "set -u",
        'echo "== Power sensor (bc250_vrm): restart the driver =="',
        f"if ! grep -q '^{module} ' /proc/modules; then",
        '  echo "ERROR: the bc250_vrm driver is not loaded, so there is nothing to restart."',
        '  echo "Install it in Additional settings › Compatibility › Board sensors."',
        "  exit 1",
        "fi",
        f"sudo modprobe -r {module} || {{",
        '  echo "ERROR: the driver could not be stopped. Unplug the computer for 30 seconds to reset the sensor."',
        "  exit 1",
        "}",
        "sleep 1",
        f"sudo modprobe {module} || {{",
        '  echo "ERROR: the driver did not start again. Unplug the computer for 30 seconds and start it again."',
        "  exit 1",
        "}",
        "sleep 2",
        "bc250_dir=''",
        "for bc250_hwmon in /sys/class/hwmon/hwmon*; do",
        f'  [ "$(cat "$bc250_hwmon/name" 2>/dev/null)" = {module} ] && bc250_dir="$bc250_hwmon" && break',
        "done",
        'if [ -z "$bc250_dir" ]; then',
        '  echo "ERROR: the driver started but no regulator answered. Unplug the computer for 30 seconds and start it again."',
        "  exit 2",
        "fi",
        'bc250_temp="$(cat "$bc250_dir/temp1_input" 2>/dev/null || echo -1)"',
        'bc250_vin="$(cat "$bc250_dir/in0_input" 2>/dev/null || echo -1)"',
        'if [ "$bc250_temp" -ge 1000 ] && [ "$bc250_temp" -le 150000 ] '
        '&& [ "$bc250_vin" -ge 9000 ] && [ "$bc250_vin" -le 14000 ]; then',
        '  echo "OK: the power sensor reads again: $((bc250_temp / 1000)) °C on the CPU rail, '
        '$((bc250_vin / 1000)).$(( (bc250_vin % 1000) / 10 )) V input."',
        "  exit 0",
        "fi",
        'if [ "$bc250_temp" -lt 0 ]; then',
        '  echo "ERROR: the sensor still does not answer after the restart."',
        "else",
        '  echo "ERROR: the sensor still returns impossible values ($((bc250_temp / 1000)) °C, $bc250_vin mV input)."',
        "fi",
        'echo "Shut down, unplug the computer (or switch the power supply off) for 30 seconds and start it again. The chip the sensor is read through stays powered while the computer is only turned off."',
        "exit 2",
    ))


def needs_rebuild() -> bool:
    """The installed build is not this version's (1.22.10's first build shared
    the fan driver's EC port, which is what wedges the sensor)."""
    installed = _installed_build()
    return bool(installed) and installed != DRIVER.build_id


def repair_command(family: str) -> str:
    """Repair sensor: rebuild an out-of-date driver, otherwise restart it."""
    if needs_rebuild():
        return "\n".join((
            'echo "The installed power sensor driver shares a port with the fan driver; rebuilding it on its own port."',
            install_command(family),
            'echo "If the readings do not come back, unplug the computer for 30 seconds and start it again: '
            'the old driver left the fan chip stuck."',
        ))
    return reload_command()
