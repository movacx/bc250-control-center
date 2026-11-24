"""What a fan calibration reads while it runs, from files only."""

from __future__ import annotations

from pathlib import Path


def read_int(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return None


def hottest_temperature(base: Path = Path("/sys/class/hwmon")) -> float | None:
    """Read APU and board/VRM temperatures directly, even while UI refresh is paused.

    At least one APU sensor must be available; board readings alone cannot
    prove that it is safe to slow the APU fan.
    """
    values = []
    apu_available = False
    for hwmon in sorted(base.glob("hwmon*")):
        try:
            name = (hwmon / "name").read_text(encoding="utf-8").strip()
        except OSError:
            continue
        apu = name in {"k10temp", "zenpower", "amdgpu"}
        if not apu and not name.startswith("nct"):
            continue
        for temp in hwmon.glob("temp*_input"):
            value = read_int(temp)
            if value is not None and 0 < value <= 130000:
                values.append(value / 1000.0)
                apu_available = apu_available or apu
    return max(values) if values and apu_available else None
