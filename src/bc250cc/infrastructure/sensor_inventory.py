"""Every sensor the board exposes, read in one pass, with nothing guessed.

The Performance page charts six summaries. People tuning a BC-250 also want
the raw list a hardware monitor shows: each hwmon channel with its kernel
label, each core's clock and each thread's load, the GPU's own clocks and
rails, the fan, the drive, the PMIC over I2C when the board has that mod and
the GDDR6 chips when a reading session is running. This module builds that
list; the page keeps the statistics and draws it.

Rules it keeps:

* Passive only. Everything is a sysfs or procfs read, no helper, no prompt.
* Nothing invented. A channel that is not there is not listed; a channel
  that reads 0 is listed as 0 (the view decides whether to hide it).
* Stable keys. A sensor keeps its key across samples and across a rescan, so
  statistics and plotted selections survive a hot-plugged drive.
* Cheap. Channel files are discovered once and rescanned every half minute;
  a sample is one small read per channel.
"""

from __future__ import annotations

import math
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

#: Kinds a reading can be. The view colours and filters by them.
TEMPERATURE = "temperature"
CLOCK = "clock"
USAGE = "usage"
POWER = "power"
VOLTAGE = "voltage"
CURRENT = "current"
FAN = "fan"
DATA = "data"
RATE = "rate"

KINDS = (TEMPERATURE, CLOCK, USAGE, POWER, VOLTAGE, CURRENT, FAN, DATA, RATE)

#: How the GPU appears in the list, whatever its hwmon driver is called.
GPU_DEVICE = "Cyan Skillfish (amdgpu)"

#: Groups, in the order a hardware monitor lists them.
GROUP_CPU = "cpu"
GROUP_GPU = "gpu"
GROUP_GDDR6 = "gddr6"
GROUP_VRM = "vrm"
GROUP_MEMORY = "memory"
GROUP_STORAGE = "storage"
GROUP_NETWORK = "network"
GROUP_ORDER = (
    GROUP_CPU, GROUP_GPU, GROUP_GDDR6, GROUP_VRM, GROUP_MEMORY, GROUP_STORAGE, GROUP_NETWORK,
)


@dataclass(frozen=True)
class SensorReading:
    """One sensor at one moment.

    ``label`` is either the kernel's own name for the channel (shown as is,
    the way every hardware monitor does) or a template with ``{core}`` and
    ``{thread}`` fields for the few names this module makes up.
    """

    key: str
    group: str
    device: str
    label: str
    kind: str
    unit: str
    value: float | None
    #: Filled into ``label`` by the view after translation.
    fields: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class _Channel:
    key: str
    group: str
    device: str
    label: str
    kind: str
    unit: str
    path: Path
    scale: float


# hwmon channel prefix -> (kind, unit, divisor to reach the unit)
_HWMON_TYPES = {
    "temp": (TEMPERATURE, "°C", 1000.0),
    "in": (VOLTAGE, "V", 1000.0),
    "fan": (FAN, "RPM", 1.0),
    "power": (POWER, "W", 1_000_000.0),
    "curr": (CURRENT, "A", 1000.0),
    "freq": (CLOCK, "MHz", 1_000_000.0),
}

#: hwmon drivers that describe a part of the CPU or GPU group rather than a
#: chip of their own.
_HWMON_GROUPS = {"k10temp": GROUP_CPU, "zenpower": GROUP_CPU, "amdgpu": GROUP_GPU}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _read_number(path: Path) -> float | None:
    text = _read_text(path)
    if not text:
        return None
    try:
        value = float(text.split()[0])
    except (ValueError, IndexError):
        return None
    return value if math.isfinite(value) else None


def _finite(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _hwmon_device_name(directory: Path, driver: str) -> str:
    """A name a person recognises: the drive's model, else the driver."""
    model = _read_text(directory / "device" / "model")
    if model:
        return f"{model} ({driver})"
    return driver


def discover_hwmon(root: Path = Path("/sys/class/hwmon")) -> list[_Channel]:
    """Every readable channel of every hwmon device, in a stable order."""
    channels: list[_Channel] = []
    seen_drivers: dict[str, int] = {}
    try:
        directories = sorted(root.iterdir(), key=lambda item: item.name)
    except OSError:
        return channels
    for directory in directories:
        driver = _read_text(directory / "name") or directory.name
        # Two devices of one driver (two drives) keep apart by their order.
        index = seen_drivers.get(driver, 0)
        seen_drivers[driver] = index + 1
        device_key = driver if index == 0 else f"{driver}{index}"
        group = _HWMON_GROUPS.get(driver, f"hwmon:{device_key}")
        device = _hwmon_device_name(directory, driver)
        try:
            names = sorted(entry.name for entry in directory.iterdir())
        except OSError:
            continue
        taken: set[str] = set()
        for name in names:
            stem, _sep, suffix = name.partition("_")
            if suffix not in {"input", "average"}:
                continue
            prefix = stem.rstrip("0123456789")
            if prefix not in _HWMON_TYPES or stem in taken:
                continue
            # A power channel can offer both; the average is the steadier one.
            if suffix == "input" and prefix == "power" and f"{stem}_average" in names:
                continue
            taken.add(stem)
            kind, unit, scale = _HWMON_TYPES[prefix]
            label = _read_text(directory / f"{stem}_label") or stem
            channels.append(
                _Channel(
                    key=f"hwmon/{device_key}/{stem}",
                    group=group,
                    device=device,
                    label=label,
                    kind=kind,
                    unit=unit,
                    path=directory / name,
                    scale=scale,
                )
            )
    return channels


def cpu_topology(root: Path = Path("/sys/devices/system/cpu")) -> list[list[int]]:
    """Logical CPUs grouped by physical core, cores ordered by their first CPU.

    Read from the kernel rather than assumed: siblings are adjacent on the
    BC-250 (0-1, 2-3...) but not on every AMD part.
    """
    cores: dict[tuple[str, str], list[int]] = {}
    try:
        entries = [entry for entry in root.iterdir() if entry.name[3:].isdigit() and entry.name.startswith("cpu")]
    except OSError:
        return []
    for entry in entries:
        number = int(entry.name[3:])
        package = _read_text(entry / "topology" / "physical_package_id") or "0"
        core = _read_text(entry / "topology" / "core_id")
        if not core:
            # Offline CPUs have no topology; keep them out of the table.
            continue
        cores.setdefault((package, core), []).append(number)
    groups = [sorted(members) for members in cores.values()]
    return sorted(groups, key=lambda members: members[0])


class _CpuTimes:
    """Per-thread busy share from /proc/stat, with its own baseline.

    psutil keeps one global baseline for ``cpu_percent``; another caller
    resetting it would skew these numbers, so the deltas are kept here.
    """

    def __init__(self, stat_path: Path = Path("/proc/stat")) -> None:
        self._path = stat_path
        self._previous: dict[int, tuple[float, float]] = {}

    def sample(self) -> dict[int, float]:
        text = _read_text(self._path)
        current: dict[int, tuple[float, float]] = {}
        for line in text.splitlines():
            if not line.startswith("cpu") or line.startswith("cpu "):
                continue
            name, *fields = line.split()
            try:
                number = int(name[3:])
                values = [float(field) for field in fields[:8]]
            except ValueError:
                continue
            if len(values) < 4:
                continue
            idle = values[3] + (values[4] if len(values) > 4 else 0.0)
            current[number] = (sum(values), idle)
        usage: dict[int, float] = {}
        for number, (total, idle) in current.items():
            previous = self._previous.get(number)
            if previous is None:
                continue
            elapsed = total - previous[0]
            if elapsed <= 0:
                continue
            busy = elapsed - (idle - previous[1])
            usage[number] = max(0.0, min(100.0, 100.0 * busy / elapsed))
        self._previous = current
        return usage


class SensorInventory:
    """Reads the whole list; one instance per sampler, used from one thread."""

    RESCAN_SECONDS = 30.0

    def __init__(
        self,
        *,
        hwmon_root: Path = Path("/sys/class/hwmon"),
        cpu_root: Path = Path("/sys/devices/system/cpu"),
        stat_path: Path = Path("/proc/stat"),
        cpuinfo_path: Path = Path("/proc/cpuinfo"),
        clock=time.monotonic,
    ) -> None:
        self._hwmon_root = hwmon_root
        self._cpu_root = cpu_root
        self._cpuinfo_path = cpuinfo_path
        self._clock = clock
        self._channels: list[_Channel] = []
        self._topology: list[list[int]] = []
        self._scanned_at: float | None = None
        self._cpu_times = _CpuTimes(stat_path)
        self._cpu_name = ""

    # --------------------------------------------------------------- discovery

    def _rescan_if_due(self) -> None:
        now = self._clock()
        if self._scanned_at is not None and now - self._scanned_at < self.RESCAN_SECONDS:
            return
        self._scanned_at = now
        self._channels = discover_hwmon(self._hwmon_root)
        self._topology = cpu_topology(self._cpu_root)
        if not self._cpu_name:
            for line in _read_text(self._cpuinfo_path).splitlines():
                if line.lower().startswith("model name"):
                    self._cpu_name = line.partition(":")[2].strip()
                    break

    @property
    def cpu_name(self) -> str:
        return self._cpu_name or "CPU"

    # ----------------------------------------------------------------- reading

    def read(
        self,
        realtime: Mapping[str, object] | None = None,
        *,
        gddr6_chips: Sequence[tuple[int, float]] = (),
    ) -> list[SensorReading]:
        """One sample of everything, grouped and ordered for display.

        ``realtime`` is the shared real-time sample the rest of the page uses;
        GPU usage, memory, drive and network come from it rather than being
        read a second time. ``gddr6_chips`` are the chips of a GDDR6 reading
        session, when one is running.
        """
        self._rescan_if_due()
        sample = _mapping(realtime)
        readings: list[SensorReading] = []
        readings += self._cpu_readings(_mapping(sample.get("cpu")))
        readings += self._gpu_readings(_mapping(sample.get("gpu")))
        readings += self._gddr6_readings(gddr6_chips)
        readings += self._vrm_readings(_mapping(sample.get("sensors")))
        readings += self._memory_readings(_mapping(sample.get("memory")))
        readings += self._storage_readings(_mapping(sample.get("disk")))
        readings += self._network_readings(_mapping(sample.get("network")))
        readings += self._board_readings()
        return readings

    def _hwmon(self, group: str, device: str | None = None) -> Iterable[SensorReading]:
        """The group's hwmon channels; ``device`` names the part they belong to."""
        for channel in self._channels:
            if channel.group != group:
                continue
            raw = _read_number(channel.path)
            yield SensorReading(
                key=channel.key,
                group=channel.group,
                device=device or channel.device,
                label=channel.label,
                kind=channel.kind,
                unit=channel.unit,
                value=None if raw is None else raw / channel.scale,
            )

    def _thread_clocks(self, numbers: Iterable[int]) -> dict[int, float]:
        """MHz per logical CPU: cpufreq when a driver is loaded, else cpuinfo.

        The BC-250 often runs with no cpufreq driver at all; the kernel still
        reports each CPU's effective clock in /proc/cpuinfo, which is where
        psutil reads it from too.
        """
        clocks: dict[int, float] = {}
        for number in numbers:
            value = _read_number(self._cpu_root / f"cpu{number}" / "cpufreq" / "scaling_cur_freq")
            if value is not None:
                clocks[number] = value / 1000.0
        if clocks:
            return clocks
        current = None
        for line in _read_text(self._cpuinfo_path).splitlines():
            key, _sep, value = line.partition(":")
            key = key.strip().lower()
            if key == "processor":
                current = int(value) if value.strip().isdigit() else None
            elif key == "cpu mhz" and current is not None:
                number = _finite(value.strip())
                if number is not None:
                    clocks[current] = number
        return clocks

    def _cpu_readings(self, cpu: Mapping[str, object]) -> list[SensorReading]:
        device = self.cpu_name
        readings = list(self._hwmon(GROUP_CPU, device))
        threads = self._cpu_times.sample()
        topology = self._topology or [[number] for number in sorted(threads)]
        clocks = self._thread_clocks(members[0] for members in topology)
        readings.append(
            SensorReading("cpu/usage", GROUP_CPU, device, "CPU usage", USAGE, "%", _finite(cpu.get("usage_percent")))
        )
        for core, members in enumerate(topology):
            readings.append(
                SensorReading(
                    f"cpu/core{core}/clock", GROUP_CPU, device, "Core {core} clock", CLOCK, "MHz",
                    clocks.get(members[0]), (("core", core),),
                )
            )
        for core, members in enumerate(topology):
            loads = [threads[number] for number in members if number in threads]
            readings.append(
                SensorReading(
                    f"cpu/core{core}/usage", GROUP_CPU, device, "Core {core} usage", USAGE, "%",
                    sum(loads) / len(loads) if loads else None, (("core", core),),
                )
            )
        for core, members in enumerate(topology):
            for thread, number in enumerate(members):
                readings.append(
                    SensorReading(
                        f"cpu/core{core}/t{thread}/usage", GROUP_CPU, device,
                        "Core {core} T{thread} usage", USAGE, "%", threads.get(number),
                        (("core", core), ("thread", thread)),
                    )
                )
        return readings

    def _gpu_readings(self, gpu: Mapping[str, object]) -> list[SensorReading]:
        device = GPU_DEVICE
        readings = [
            SensorReading("gpu/usage", GROUP_GPU, device, "GPU usage", USAGE, "%", _finite(gpu.get("usage_percent"))),
            # Time on the compute (ACE) rings, from amdgpu's per-client
            # counters: above zero only while a game really uses async compute.
            SensorReading(
                "gpu/compute", GROUP_GPU, device, "Async compute (ACE)", USAGE, "%",
                _finite(gpu.get("compute_busy_percent")),
            ),
        ]
        for key, label, field in (
            ("gpu/mclk", "Memory clock", "memory_frequency_mhz"),
            ("gpu/socclk", "SoC clock", "soc_frequency_mhz"),
            ("gpu/fclk", "Fabric clock", "fabric_frequency_mhz"),
        ):
            readings.append(SensorReading(key, GROUP_GPU, device, label, CLOCK, "MHz", _finite(gpu.get(field))))
        readings += list(self._hwmon(GROUP_GPU, device))
        for key, label, used, total in (
            ("gpu/vram", "VRAM used", "vram_used", "vram_total"),
            ("gpu/gtt", "GTT used", "gtt_used", "gtt_total"),
        ):
            used_bytes = _finite(gpu.get(used))
            readings.append(SensorReading(key, GROUP_GPU, device, label, DATA, "B", used_bytes))
            total_bytes = _finite(gpu.get(total))
            share = (
                100.0 * used_bytes / total_bytes
                if used_bytes is not None and total_bytes and total_bytes > 0
                else None
            )
            readings.append(
                SensorReading(f"{key}_percent", GROUP_GPU, device, f"{label} (%)", USAGE, "%", share)
            )
        return readings

    @staticmethod
    def _gddr6_readings(chips: Sequence[tuple[int, float]]) -> list[SensorReading]:
        if not chips:
            return []
        device = "GDDR6 (SMU)"
        readings = [
            SensorReading(
                f"gddr6/chip{index}", GROUP_GDDR6, device, "Chip {chip}", TEMPERATURE, "°C",
                _finite(value), (("chip", int(index)),),
            )
            for index, value in chips
        ]
        values = [value for _index, value in chips if _finite(value) is not None]
        if values:
            readings.append(SensorReading("gddr6/average", GROUP_GDDR6, device, "Average", TEMPERATURE, "°C", sum(values) / len(values)))
            readings.append(SensorReading("gddr6/hotspot", GROUP_GDDR6, device, "Hotspot", TEMPERATURE, "°C", max(values)))
        return readings

    @staticmethod
    def _vrm_readings(sensors: Mapping[str, object]) -> list[SensorReading]:
        """The PMIC rails over I2C; only on boards with that mod."""
        if str(sensors.get("vrm_source") or "") != "pmbus":
            return []
        device = "VRM · PMBus"
        rows = (
            ("vrm/input", "12V in", VOLTAGE, "V", "vrm_input_voltage_v"),
            ("vrm/total_power", "VRM power", POWER, "W", "vrm_total_power_w"),
            ("vrm/cpu_voltage", "CPU rail voltage", VOLTAGE, "V", "vrm_cpu_voltage_v"),
            ("vrm/cpu_current", "CPU current", CURRENT, "A", "vrm_cpu_current_a"),
            ("vrm/cpu_power", "CPU rail power", POWER, "W", "vrm_cpu_power_w"),
            ("vrm/cpu_temperature", "CPU rail temperature", TEMPERATURE, "°C", "vrm_cpu_temperature_c"),
            ("vrm/gpu_voltage", "GPU rail voltage", VOLTAGE, "V", "vrm_gpu_voltage_v"),
            ("vrm/gpu_current", "GPU current", CURRENT, "A", "vrm_gpu_current_a"),
            ("vrm/gpu_power", "GPU rail power", POWER, "W", "vrm_gpu_power_w"),
            ("vrm/gpu_temperature", "GPU rail temperature", TEMPERATURE, "°C", "vrm_gpu_temperature_c"),
        )
        return [
            SensorReading(key, GROUP_VRM, device, label, kind, unit, _finite(sensors.get(field)))
            for key, label, kind, unit, field in rows
        ]

    @staticmethod
    def _memory_readings(memory: Mapping[str, object]) -> list[SensorReading]:
        if not memory:
            return []
        device = "System memory"
        return [
            SensorReading("memory/used", GROUP_MEMORY, device, "Physical memory used", DATA, "B", _finite(memory.get("used"))),
            SensorReading("memory/available", GROUP_MEMORY, device, "Physical memory available", DATA, "B", _finite(memory.get("available"))),
            SensorReading("memory/load", GROUP_MEMORY, device, "Physical memory load", USAGE, "%", _finite(memory.get("usage_percent"))),
            SensorReading("memory/swap_used", GROUP_MEMORY, device, "Swap used", DATA, "B", _finite(memory.get("swap_used"))),
            SensorReading("memory/swap_load", GROUP_MEMORY, device, "Swap load", USAGE, "%", _finite(memory.get("swap_percent"))),
        ]

    @staticmethod
    def _storage_readings(disk: Mapping[str, object]) -> list[SensorReading]:
        if not disk:
            return []
        device = str(disk.get("device") or "Root drive")
        return [
            SensorReading("disk/read", GROUP_STORAGE, device, "Read rate", RATE, "B/s", _finite(disk.get("read_bps"))),
            SensorReading("disk/write", GROUP_STORAGE, device, "Write rate", RATE, "B/s", _finite(disk.get("write_bps"))),
            SensorReading("disk/active", GROUP_STORAGE, device, "Active time", USAGE, "%", _finite(disk.get("active_percent"))),
            SensorReading("disk/space", GROUP_STORAGE, device, "Space used", USAGE, "%", _finite(disk.get("usage_percent"))),
        ]

    @staticmethod
    def _network_readings(network: Mapping[str, object]) -> list[SensorReading]:
        if not network:
            return []
        device = str(network.get("interface") or "Network")
        return [
            SensorReading("net/download", GROUP_NETWORK, device, "Download rate", RATE, "B/s", _finite(network.get("download_bps"))),
            SensorReading("net/upload", GROUP_NETWORK, device, "Upload rate", RATE, "B/s", _finite(network.get("upload_bps"))),
        ]

    def _board_readings(self) -> list[SensorReading]:
        """Every other hwmon chip: the Nuvoton, the drive, the Wi-Fi card..."""
        groups: list[str] = []
        for channel in self._channels:
            if channel.group.startswith("hwmon:") and channel.group not in groups:
                groups.append(channel.group)
        readings: list[SensorReading] = []
        for group in groups:
            readings += list(self._hwmon(group))
        return readings
