"""The written guides, as plain text a terminal can page through."""

from __future__ import annotations

from frontends.desktop.i18n import project_overview

from ..i18n import tr

NEEDS = (
    "Two wires with a 2-pin connector. The cable of an old PC case's power or reset button works well.",
    "A 2.0 mm connector for the TPMS1 end: standard 2.54 mm Dupont plugs sit loose on it.",
    "Nothing to solder and no ground wire: both headers already share the board's ground.",
    "The board switched off, with the power supply unplugged.",
)
TROUBLESHOOTING = (
    "SCL and SDA swapped. It damages nothing, but the bus stays silent: swap them and try again.",
    "A loose connector on TPMS1. A 2.54 mm plug moves on 2.0 mm pins.",
    "The wrong pins on TPMS1. Count from the triangle: pin 1 is bottom left, pins 4 and 6 are the second and third of the top row.",
    "A kernel that reads the regulator itself (bc250_vrm). It keeps the bus to itself; use the bc250-vrm tab instead.",
)
WIRING = (("SCL (red)", "Pin 4", "SMB_CLK_MAIN"), ("SDA (blue)", "Pin 6", "SMB_DATA_MAIN"))


def _bullets(items) -> list[str]:
    return [f"  • {tr(item)}" for item in items]


def i2c() -> str:
    return "\n".join([
        tr("Two wires between I2C_HEADER1 and TPMS1 let Linux read the board's voltage regulator: the 12 V input, the CPU and "
           "GPU rails, their current and power, and the VRM temperatures. The BC250-Telemetry service then publishes them for "
           "the dashboard."), "",
        tr("What you need"), *_bullets(NEEDS), "",
        tr("Work with the board switched off and the power supply unplugged. This is a community modification with no "
           "warranty: check every pin before powering on."), "",
        "1. " + tr("Find I2C_HEADER1"),
        tr("I2C_HEADER1, beside the heatsink. Red is SCL (middle pin), blue is SDA (the pin closer to the power connectors)."), "",
        "2. " + tr("Find TPMS1"),
        tr("TPMS1: 18 pins, 2.0 mm apart. The triangle marks pin 1 (bottom row, left). Pin 4 (red, to SCL) and pin 6 (blue, to "
           "SDA) are the second and third pins of the top row."), "",
        "3. " + tr("Connect the two wires"),
        tr("SCL to pin 4 and SDA to pin 6. Swapping them damages nothing, but the bus stays silent. The 2-pin cable of an old PC "
           "case's power or reset button fits well. Standard Dupont connectors are 2.54 mm and sit loose on TPMS1, so give "
           "that end a 2.0 mm connector."), "",
        *[f"      {tr(a):<14} {tr(b):<10} {c}" for a, b, c in WIRING], "",
        "4. " + tr("Install the service"),
        tr("Power the board on. Control Center builds BC250-Telemetry from its reviewed source and installs only the service "
           "that reads the regulator; it asks for your password once."), "",
        "5. " + tr("Check it"),
        tr("The readings appear on the dashboard within a few seconds, and Telemetry › Detection says the regulator answers. To "
           "check the bus by hand, this should show a device at 0x60:"), "", "      sudo i2cdetect -y 4", "",
        tr("If nothing shows up"), *_bullets(TROUBLESHOOTING), "",
        "https://github.com/onlinermm/BC250-Telemetry/blob/main/hardware.md"])


def driver(vrm: bool) -> str:
    return "\n".join([
        tr("bc250-vrm is a kernel driver by Liam McLoughlin (Hexxeh). It reads the board's voltage regulator through the fan "
           "chip, so it needs none of the I2C wiring: the 12 V input, the CPU and GPU rails and the VRM temperatures show up "
           "on the Dashboard and in sensors.") if vrm else
        tr("bc250-memory is the same author's driver for the video memory. It reads the temperature of the eight GDDR6 chips "
           "through the SMU and shows it as a normal sensor: the hottest chip, the average and each chip."), "",
        tr("How it is installed"),
        tr("Control Center downloads the reviewed source, builds it with DKMS for your kernel and loads it. When the kernel "
           "updates, DKMS builds it again by itself. It needs Arch, CachyOS, Manjaro or another Arch-based system; MastaG's "
           "BC-250 kernels already include it."), "",
        tr("Use one way, not both: if you already have the I2C wires with the BC250-Telemetry service, remove the service "
           "first. Two readers on the same regulator mix up each other's readings.") if vrm else
        tr("On a BIOS that keeps the SMU locked (stock P3.00), the driver waits until the SMU is patched. Press Monitor live on "
           "the dashboard once after each power-on: Control Center patches the SMU and the driver reads from then on."), "",
        tr("Check it"), tr("Once it is installed, this lists the driver's readings:"), "",
        "      sensors 'bc250_vrm-*'" if vrm else "      sensors 'bc250_memory-*'"])


#: (title, summary, the text) of each guide.
GUIDES = (
    ("Project overview", "", project_overview),
    ("Board sensors guide: I2C wiring, bc250-vrm and bc250-memory",
     "Power delivery readings over the I2C modification. Needs the wires on the board.", i2c),
    ("Power delivery readings (kernel driver)", "Regulator temperatures read through the fan chip. No wires needed.", lambda: driver(True)),
    ("VRAM temperature (kernel driver)", "GDDR6 temperature read through the SMU. BIOS P3.00 only.", lambda: driver(False)),
)
