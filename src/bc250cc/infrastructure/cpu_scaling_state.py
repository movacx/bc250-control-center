"""Whether the kernel can scale CPU frequency on this board.

The BC-250 firmware ships processor power-management tables that declare idle
states but **no** performance states: its SSDT exposes `_CST` entries and zero
`_PSS`/`_PCT`. Without `_PSS` the `acpi-cpufreq` driver has nothing to
register, so `/sys/devices/system/cpu/cpu0/cpufreq` never appears and every
core runs pinned near its base clock, in idle as well as under load.

The reviewed ACPI override supplies those tables. Until it is applied the
board simply has no frequency scaling, and nothing in the interface said so —
the machine looks healthy while drawing full power at idle.

Read-only: this reports state, it never loads modules or touches boot files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

CPU_ROOT = "sys/devices/system/cpu"
# Firmware tables live here; the fix's own tables identify themselves by OEM.
ACPI_TABLES = "sys/firmware/acpi/tables"
FIX_TABLE_MARKERS = (b"HACK", b"PSTATES", b"STUBS")


@dataclass(frozen=True)
class CpuScalingState:
    scaling_available: bool
    scaling_driver: str
    governor: str
    acpi_override_active: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "scaling_available": self.scaling_available,
            "scaling_driver": self.scaling_driver,
            "governor": self.governor,
            "acpi_override_active": self.acpi_override_active,
        }


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="ascii", errors="replace").strip()
    except OSError:
        return ""


def _override_active(root: Path) -> bool:
    """True when a loaded SSDT carries the reviewed fix's own identifiers."""
    tables = root / ACPI_TABLES
    try:
        candidates = sorted(tables.glob("SSDT*"))
    except OSError:
        return False
    for table in candidates:
        try:
            # The OEM id and table id sit in the first 40 bytes of the header.
            header = table.open("rb").read(40)
        except OSError:
            continue
        if any(marker in header for marker in FIX_TABLE_MARKERS):
            return True
    return False


def detect_cpu_scaling(*, root: Path | str = "/") -> dict[str, object]:
    """Report whether CPU frequency scaling is available, without changing it."""
    base = Path(root)
    cpufreq = base / CPU_ROOT / "cpu0/cpufreq"
    driver = _read(cpufreq / "scaling_driver")
    governor = _read(cpufreq / "scaling_governor")
    return CpuScalingState(
        scaling_available=bool(driver),
        scaling_driver=driver,
        governor=governor,
        acpi_override_active=_override_active(base),
    ).to_dict()
