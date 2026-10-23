"""The black box: the last seconds of the GPU before a freeze or a reset.

A hard hang leaves nothing in the kernel journal; the board simply stops. Run
before playing, this writes the real GPU clock, its load, the temperatures,
the GFX voltage and the fan speed four times a second, and flushes every line
to disk, so after the restart the end of the file shows what the board was
doing in its last seconds. The next problem report attaches that end.

Based on the community ``gpu-log.sh``. Everything read here is plain sysfs, so
it needs no root. The file is bounded: when it reaches ``ROTATE_BYTES`` it
becomes ``previous.log`` and a new one starts, so it never fills the disk.
"""

from __future__ import annotations

import glob
import os
import time
from datetime import datetime
from pathlib import Path

INTERVAL_S = 0.25
ROTATE_BYTES = 512 * 1024
#: Lines of the last session the report carries.
REPORT_LINES = 40
_HEADER = "# boot="


def log_directory() -> Path:
    state = os.environ.get("XDG_STATE_HOME", "").strip()
    root = Path(state) if state else Path.home() / ".local" / "state"
    return root / "bc250-control-center" / "black-box"


def boot_id() -> str:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
    except OSError:
        return "?"


def _read(path: str) -> str:
    try:
        with open(path, encoding="ascii", errors="replace") as handle:
            return handle.read().strip()
    except OSError:
        return ""


class Sensors:
    """The files one sample reads, found once."""

    def __init__(self):
        self.device = ""
        for device in sorted(glob.glob("/sys/class/drm/card*/device")):
            if _read(f"{device}/vendor") == "0x1002" and _read(f"{device}/device") == "0x13fe":
                self.device = os.path.realpath(device)
                break
        self.t_gpu = self.t_cpu = self.v_gfx = self.power = ""
        self.fans: list[str] = []
        for hwmon in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
            name = _read(f"{hwmon}/name")
            if name == "amdgpu":
                self.t_gpu = f"{hwmon}/temp1_input"
                self.v_gfx = f"{hwmon}/in0_input" if os.path.exists(f"{hwmon}/in0_input") else ""
                for power in ("power1_average", "power1_input"):
                    if os.path.exists(f"{hwmon}/{power}"):
                        self.power = f"{hwmon}/{power}"
                        break
            elif name == "k10temp":
                self.t_cpu = f"{hwmon}/temp1_input"
            elif name.startswith("nct") or name.startswith("it87"):
                fans = sorted(glob.glob(f"{hwmon}/fan[0-9]_input"))
                # Only the headers with a fan on them; all of them when none spins yet.
                self.fans = [fan for fan in fans if _read(fan) not in {"", "0"}] or fans
        self.cpu_clocks = sorted(glob.glob("/sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq"))

    def describe(self) -> str:
        return (f"gpu={self.device or 'not found'} t_gpu={self.t_gpu or '-'} t_cpu={self.t_cpu or '-'} "
                f"v_gfx={self.v_gfx or '-'} power={self.power or '-'} fans={len(self.fans)}")

    def sample(self) -> str:
        clock = "-"
        for line in _read(f"{self.device}/pp_dpm_sclk").splitlines():
            if "*" in line:
                clock = line.split(":", 1)[-1].replace("*", "").strip()
                break

        def milli(path: str, scale: int = 1000) -> str:
            raw = _read(path) if path else ""
            return str(int(raw) // scale) if raw.lstrip("-").isdigit() else "-"

        busy = _read(f"{self.device}/gpu_busy_percent") or "-"
        volts = (_read(self.v_gfx) if self.v_gfx else "") or "-"
        rpm = ",".join(
            f"{Path(path).name[:-6]}:{_read(path) or '-'}" for path in self.fans
        ) or "-"
        stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        return (f"{stamp} {clock} busy={busy}% t_gpu={milli(self.t_gpu)} t_cpu={milli(self.t_cpu)} "
                f"v={volts} w={milli(self.power, 1_000_000)} rpm={rpm} cpu={self._cpu_mhz()} mem={_available_mib()}")

    def _cpu_mhz(self) -> str:
        """The fastest core right now: a stuck or runaway clock shows here."""
        values = [_read(path) for path in self.cpu_clocks]
        numbers = [int(value) // 1000 for value in values if value.isdigit()]
        if not numbers:
            # No cpufreq driver (the stock BC-250): the kernel still reports
            # each core's clock in /proc/cpuinfo.
            for line in _read("/proc/cpuinfo").splitlines():
                if line.startswith("cpu MHz"):
                    try:
                        numbers.append(int(float(line.split(":", 1)[1])))
                    except ValueError:
                        continue
        return str(max(numbers)) if numbers else "-"



def _available_mib() -> str:
    for line in _read("/proc/meminfo").splitlines():
        if line.startswith("MemAvailable:"):
            return str(int(line.split()[1]) // 1024)
    return "-"


def _rotate(current: Path) -> None:
    try:
        if current.stat().st_size >= ROTATE_BYTES:
            current.replace(current.with_name("previous.log"))
    except OSError:
        pass


def record(*, interval: float = INTERVAL_S, samples: int | None = None, out=None) -> int:
    """Write samples until stopped (Ctrl+C), flushing each to disk."""
    sensors = Sensors()
    if not sensors.device:
        print("The BC-250 GPU (1002:13fe) was not found in /sys/class/drm.", file=out)
        return 1
    directory = log_directory()
    directory.mkdir(parents=True, exist_ok=True)
    current = directory / "current.log"
    print(f"Black box on: {current} (Ctrl+C to stop)\n{sensors.describe()}", file=out)
    header = f"{_HEADER}{boot_id()} start={datetime.now().astimezone().isoformat(timespec='seconds')} {sensors.describe()}\n"
    written = 0
    handle = None
    try:
        while samples is None or written < samples:
            if handle is None or handle.tell() >= ROTATE_BYTES:
                if handle is not None:
                    handle.close()
                _rotate(current)
                handle = open(current, "a", encoding="utf-8")  # noqa: SIM115 - reopened on rotation
                handle.write(header)
            handle.write(sensors.sample() + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            written += 1
            if samples is None or written < samples:
                time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        if handle is not None:
            handle.write(f"# stopped {datetime.now().astimezone().isoformat(timespec='seconds')}\n")
            handle.close()
    return 0


def last_session(directory: Path | None = None, *, lines: int = REPORT_LINES) -> str:
    """The end of the last recording, saying whether a restart cut it off."""
    directory = directory or log_directory()
    text = ""
    for name in ("previous.log", "current.log"):
        try:
            text += (directory / name).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    if not text.strip():
        return "(the black box was not running; start it before playing to catch a freeze)"
    rows = text.splitlines()
    start = max((i for i, row in enumerate(rows) if row.startswith(_HEADER)), default=0)
    session = rows[start:]
    header = session[0] if session and session[0].startswith(_HEADER) else ""
    recorded_boot = header[len(_HEADER):].split(" ", 1)[0] if header else "?"
    stopped = any(row.startswith("# stopped") for row in session)
    if recorded_boot != boot_id():
        state = ("stopped normally before the last restart" if stopped
                 else "CUT OFF BY A RESTART OR FREEZE — the last lines are the board's last seconds")
    else:
        state = "stopped this boot" if stopped else "still recording this boot"
    body = [row for row in session[1:] if not row.startswith("# stopped")][-lines:]
    return "\n".join([f"[{state}]", header, *body])


if __name__ == "__main__":
    raise SystemExit(record())
