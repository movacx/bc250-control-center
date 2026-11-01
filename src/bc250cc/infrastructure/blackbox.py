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
import signal
import time
from datetime import datetime
from pathlib import Path

INTERVAL_S = 0.25
ROTATE_BYTES = 512 * 1024
#: Lines of the last session the report carries.
REPORT_LINES = 40
_HEADER = "# boot="
PID_FILE = "current.pid"
#: The programs whose ``black-box`` argument starts a recorder.
_RECORDER_PROGRAMS = ("bc250-control-center-cli", "cli.py", "frontends.cli")
#: A recording written this recently is still being written.
FRESH_SECONDS = 4.0


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


def _is_recorder(argv: list[str]) -> bool:
    """Whether a command line is a recorder: the CLI's ``black-box`` or this module run as a script.

    ``tail -f .../black-box/current.log`` or an editor with that file open is
    not one: the word has to be the last argument of one of the programs.
    """
    if not argv:
        return False
    if "-m" in argv:
        position = argv.index("-m")
        if position + 1 < len(argv) and argv[position + 1] == "bc250cc.infrastructure.blackbox":
            return True
    return argv[-1] == "black-box" and any(
        part in os.path.basename(argument) for argument in argv[:-1] for part in _RECORDER_PROGRAMS
    )


def recorder_pids(*, proc: Path = Path("/proc")) -> list[int]:
    """Every recorder of this user running now, however it was started.

    A recorder from an older release writes no pid file, and a terminal one and
    the button's can run at once, so the processes themselves are what counts.
    """
    uid = os.getuid()
    found: list[int] = []
    try:
        entries = list(proc.iterdir())
    except OSError:
        return found
    for entry in entries:
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            if entry.stat().st_uid != uid:
                continue
            argv = [part.decode(errors="replace") for part in (entry / "cmdline").read_bytes().split(b"\0") if part]
        except OSError:
            continue
        if _is_recorder(argv):
            found.append(int(entry.name))
    return sorted(found)


def running_pid(directory: Path | None = None, *, proc: Path = Path("/proc")) -> int | None:
    """The pid of a recorder that is running now, or None.

    The pid file is believed only while that process is alive and is a
    recorder; a pid the system reused, or a file a freeze left behind, is not
    "recording". Without a usable pid file the processes are looked at.
    """
    directory = directory or log_directory()
    try:
        pid = int((directory / PID_FILE).read_text(encoding="ascii").split()[0])
        argv = [part.decode(errors="replace") for part in (proc / str(pid) / "cmdline").read_bytes().split(b"\0") if part]
        if _is_recorder(argv):
            return pid
    except (OSError, ValueError, IndexError):
        pass
    pids = recorder_pids(proc=proc)
    return pids[0] if pids else None


def recently_written(directory: Path | None = None, *, seconds: float = FRESH_SECONDS) -> bool:
    """Whether the recording was written to a moment ago, and did not end with "# stopped".

    The last resort for something that records but is not a process this user
    can see (another account's, a container's).
    """
    path = (directory or log_directory()) / "current.log"
    try:
        if time.time() - path.stat().st_mtime > seconds:
            return False
        with path.open("rb") as handle:
            handle.seek(max(0, path.stat().st_size - 200))
            tail = handle.read().decode(errors="replace").strip().splitlines()
    except OSError:
        return False
    return bool(tail) and not tail[-1].startswith("# stopped")


def record(*, interval: float = INTERVAL_S, samples: int | None = None, out=None) -> int:
    """Write samples until stopped (Ctrl+C or SIGTERM), flushing each to disk."""
    sensors = Sensors()
    if not sensors.device:
        print("The BC-250 GPU (1002:13fe) was not found in /sys/class/drm.", file=out)
        return 1
    directory = log_directory()
    directory.mkdir(parents=True, exist_ok=True)
    other = running_pid(directory)
    if other is not None and other != os.getpid():
        print(f"The black box is already recording (pid {other}).", file=out)
        return 3
    pid_path = directory / PID_FILE
    pid_path.write_text(f"{os.getpid()} {boot_id()}\n", encoding="ascii")
    # systemctl stop and kill send SIGTERM: end it like Ctrl+C, so the file says
    # "stopped" and the next report does not call a normal stop a freeze.
    previous_term = None
    try:
        previous_term = signal.signal(signal.SIGTERM, signal.default_int_handler)
    except ValueError:  # not the main thread (tests)
        pass
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
        try:
            pid_path.unlink()
        except OSError:
            pass
        if previous_term is not None:
            signal.signal(signal.SIGTERM, previous_term)
    return 0


NOT_RUNNING = "(the black box was not running; start it before playing to catch a freeze)"
#: How the last recording ended: the key says it, the text is what a report reads.
_STATES = {
    "stopped-before-restart": "stopped normally before the last restart",
    "cut-off": "CUT OFF BY A RESTART OR FREEZE — the last lines are the board's last seconds",
    "stopped": "stopped this boot",
    "recording": "still recording this boot",
}


def read_session(directory: Path | None = None, *, lines: int | None = REPORT_LINES) -> dict:
    """The last recording: how it ended, its header and its samples.

    ``lines`` keeps only the end of it (a report carries 40 rows); None keeps
    every row both files hold, which is what the window shows.
    """
    directory = directory or log_directory()
    text = ""
    for name in ("previous.log", "current.log"):
        try:
            text += (directory / name).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    if not text.strip():
        return {"state": "none", "text": NOT_RUNNING, "header": "", "rows": []}
    rows = text.splitlines()
    start = max((i for i, row in enumerate(rows) if row.startswith(_HEADER)), default=0)
    session = rows[start:]
    header = session[0] if session and session[0].startswith(_HEADER) else ""
    recorded_boot = header[len(_HEADER):].split(" ", 1)[0] if header else "?"
    stopped = any(row.startswith("# stopped") for row in session)
    if recorded_boot != boot_id():
        state = "stopped-before-restart" if stopped else "cut-off"
    else:
        state = "stopped" if stopped else "recording"
    body = [row for row in session[1:] if not row.startswith("# stopped")]
    if lines is not None:
        body = body[-lines:]
    return {"state": state, "text": _STATES[state], "header": header, "rows": body}


def last_session(directory: Path | None = None, *, lines: int = REPORT_LINES) -> str:
    """The end of the last recording, saying whether a restart cut it off."""
    session = read_session(directory, lines=lines)
    if session["state"] == "none":
        return NOT_RUNNING
    return "\n".join([f"[{session['text']}]", session["header"], *session["rows"]])


def parse_sample(row: str) -> dict | None:
    """One line of ``current.log`` as columns, or None for anything else.

    ``HH:MM:SS.mmm 2000Mhz busy=99% t_gpu=62 t_cpu=58 v=1050 w=140 rpm=fan1:2400 cpu=3500 mem=9000``
    """
    parts = row.split()
    if len(parts) < 2 or row.startswith("#") or ":" not in parts[0]:
        return None
    values = dict(part.split("=", 1) for part in parts[1:] if "=" in part)
    clock = next((part for part in parts[1:2] if "=" not in part), "-")
    return {
        "time": parts[0], "clock": clock,
        "busy": "-" if values.get("busy", "-") == "-%" else values.get("busy", "-"), "t_gpu": values.get("t_gpu", "-"), "t_cpu": values.get("t_cpu", "-"),
        "volts": values.get("v", "-"), "watts": values.get("w", "-"), "rpm": values.get("rpm", "-"),
        "cpu": values.get("cpu", "-"), "mem": values.get("mem", "-"),
    }


if __name__ == "__main__":
    raise SystemExit(record())
