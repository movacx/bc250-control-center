"""Passive amdgpu clock readings; configured OD limits are not telemetry."""

from pathlib import Path


def read_hwmon_clock_mhz(device):
    if device is None:
        return None
    for hwmon in sorted((Path(device) / "hwmon").glob("hwmon*")):
        try:
            if (hwmon / "name").read_text().strip() != "amdgpu":
                continue
            inputs = []
            for label in sorted(hwmon.glob("freq*_label")):
                if label.read_text().strip().lower() in {"sclk", "gfxclk"}:
                    inputs.append(label.with_name(label.name.replace("_label", "_input")))
            # The amdgpu ABI uses freq1 for SCLK even on kernels without labels.
            if not (hwmon / "freq1_label").exists():
                inputs.append(hwmon / "freq1_input")
            for sensor in inputs:
                try:
                    hz = int(sensor.read_text().strip())
                    if 100_000_000 <= hz <= 5_000_000_000:
                        return round(hz / 1_000_000)
                except (OSError, ValueError):
                    continue
        except OSError:
            continue
    return None
