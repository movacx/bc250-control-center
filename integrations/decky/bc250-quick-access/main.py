"""Decky backend for BC250 Quick Access.

Decky runs this plugin as root by declaration.  The plugin never receives a
shell command from its frontend; every write is delegated to the root-owned
BC250 helper using a named, finite operation.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import pathlib
import stat
import subprocess
import sys
import time

import decky

# Decky loads plugin modules by filename and does not guarantee that the
# plugin directory is on ``sys.path``. Keep the bundled immutable policy
# runtime importable on every loader version without reaching into the
# user-writable Desktop application tree.
PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from bc250cc.domain.gpu.profiles import profiles_payload  # noqa: E402

HELPER = pathlib.Path("/usr/libexec/bc250-control-center/bc250-quick-access-helper")
CONTRACT_PATH = pathlib.Path(
    "/usr/libexec/bc250-control-center/lib/bc250_contract.py"
)
# Protocol 13 adds the Oberon 2000 MHz Benchmark profile and the conservative
# 1000 MHz clock-only idle fallback used when Fedora omits gpu_busy_percent.
# Protocol 14 adds the read-only "gddr6-sensors" action.
# Protocol 15 adds "gpu-high-points" (Cyan TOML safe-points above 2000 MHz).
# Protocol 16 adds "vram-apply" (write the UMA_SIZE VRAM preset to CMOS; the
# new size activates after the next reboot, exactly like the desktop control).
# Protocol 17 adds "gpu-service" (enable+start or disable+stop the installed
# GPU governor service; never a caller-supplied unit) and the gpu_service_*
# status fields the panel's service buttons read.
# Protocol 18 adds the voltage laboratory ("gpu-voltage-level",
# "gpu-voltage-custom") and the gpu_voltage_* status fields.
#
# Kept as integer literals: the desktop AST-reads HELPER_PROTOCOL out of this
# installed file, without importing it, to notice when the plugin and the root
# helper came from different builds. REQUIRED_CONTRACT_REVISION says which
# shape of the shared contract this file was written against.
# Protocol 19 adds fan_profiles/system_fan_* to the status and "fan-resume",
# which per-game profiles use to hand the fans back after a game.
HELPER_PROTOCOL = 19
REQUIRED_CONTRACT_REVISION = 1
GPU_PROFILES = (
    "balanced", "gaming", "benchmark",
    "oberon-1500", "oberon-1850", "oberon-2000",
)
CU_MODES = tuple(str(value) for value in range(24, 41, 2))
FAN_PRESETS = ("quiet", "balanced", "boost", "automatic")
FAN_CHANNELS = (2, 3, 4, 5)
FAN_MIN_PERCENT = 20
FAN_MAX_PERCENT = 100
# 3100 MHz, the same floor as canon, the desktop and the root helper — not the
# 3500 this used to declare. With that floor, 3100-3450 MHz was unreachable in
# Game Mode, and a profile the user had saved at 3200 on the desktop was
# rounded *up* to 3500 before being re-applied: an overclock nobody asked for.
CPU_FREQUENCIES = tuple(range(3100, 4201, 50))
CPU_VIDS = tuple(range(950, 1326, 5))
CPU_SCALES = tuple(range(-50, 1))
# Same fixed ladder the desktop's own VRAM control offers. Cross-checked
# against the shared contract in _contract_disagreement() before it is ever
# shown, so a stale plugin cannot offer a size the root helper would reject.
VRAM_SIZE_PRESETS_MB = (256, 512, 1024, 2048, 3072, 4096, 5120, 6144, 7168, 8192, 12288)
MAX_RECENT_ACTIONS = 10
#: Passive read of the optional onlinermm/BC250-Telemetry daemon's snapshot —
#: mirrors bc250cc.infrastructure.vrm_telemetry_reader.leer_telemetria_vrm()
#: (not importable here: Decky only receives the files this plugin ships).
#: Never starts, stops or configures that daemon; the file simply never
#: appears without the physical I2C mod its project's hardware.md describes.
VRM_TELEMETRY_PATH = pathlib.Path("/run/apu_telemetry.json")
VRM_TELEMETRY_MAX_AGE_SECONDS = 5.0
VRM_RAIL_MEASUREMENTS = (
    ("temperature_c", "temp"), ("voltage_v", "vout"), ("current_a", "iout"), ("power_w", "pout"),
)


def _vrm_number(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if number != number or number < 0 else number


def _read_vrm_telemetry(path: pathlib.Path = VRM_TELEMETRY_PATH) -> dict[str, object]:
    empty: dict[str, object] = {"vrm_available": False, "vrm_input_voltage_v": None, "vrm_total_power_w": None}
    for rail in ("cpu", "gpu"):
        for field, _source in VRM_RAIL_MEASUREMENTS:
            empty[f"vrm_{rail}_{field}"] = None
    try:
        mtime = path.stat().st_mtime
        if time.time() - mtime > VRM_TELEMETRY_MAX_AGE_SECONDS:
            return empty
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty
    hardware = payload.get("hardware") if isinstance(payload, dict) else None
    if not isinstance(hardware, dict):
        return empty
    result = dict(empty)
    input_voltages: list[float] = []
    for rail in ("cpu", "gpu"):
        data = hardware.get(rail)
        if not isinstance(data, dict) or not data.get("valid"):
            continue
        for field, source in VRM_RAIL_MEASUREMENTS:
            result[f"vrm_{rail}_{field}"] = _vrm_number(data.get(source))
        inbound = _vrm_number(data.get("vin"))
        if inbound is not None:
            input_voltages.append(inbound)
    result["vrm_input_voltage_v"] = max(input_voltages) if input_voltages else None
    if hardware.get("total_power_valid"):
        result["vrm_total_power_w"] = _vrm_number(hardware.get("total_power"))
    result["vrm_available"] = any(
        result[f"vrm_{rail}_temperature_c"] is not None for rail in ("cpu", "gpu")
    )
    return result


def _apply_custom_profile_names(
    profiles: list[dict[str, object]],
    custom: object,
    allowed_min: int,
    allowed_max: int,
) -> list[dict[str, object]]:
    """Overlay the Desktop's renamed/re-ranged profile cards onto the ladder.

    ``custom`` is the helper's own already-validated ``gpu_custom_profiles``
    (see ``_load_gpu_profile_overrides`` there); this only clamps display
    values to the range the hardware reports as allowed right now, exactly
    like ``profiles_for_allowed_range`` already does for the built-in ladder.
    Applying a profile still goes through ``apply_gpu_profile`` -> the
    root helper -> the live D-Bus envelope check, so a stale override can be
    displayed here but never applied outside what is actually allowed.
    """
    if not isinstance(custom, list) or not custom:
        return profiles
    overrides: dict[str, dict[str, object]] = {}
    for entry in custom:
        if not isinstance(entry, dict):
            continue
        key = entry.get("key")
        name, minimum, maximum = entry.get("name"), entry.get("min"), entry.get("max")
        if (
            not isinstance(key, str)
            or not isinstance(name, str)
            or isinstance(minimum, bool) or not isinstance(minimum, int)
            or isinstance(maximum, bool) or not isinstance(maximum, int)
        ):
            continue
        overrides[key] = {"name": name, "min": minimum, "max": maximum}
    if not overrides:
        return profiles
    updated: list[dict[str, object]] = []
    for profile in profiles:
        override = overrides.get(profile.get("key"))
        if override is None:
            updated.append(profile)
            continue
        bounded_min = max(allowed_min, int(override["min"]))
        bounded_max = min(allowed_max, int(override["max"]))
        if bounded_min > bounded_max:
            updated.append(profile)
            continue
        updated.append({
            "key": profile["key"], "name": override["name"],
            "min": bounded_min, "max": bounded_max,
        })
    return updated


#: Per-core CPU usage needs two samples spaced in time. The privileged helper
#: is a fresh process on every call and cannot hold that state, but this
#: plugin's own Plugin object is long-lived across polls, so it keeps the
#: previous /proc/stat snapshot itself and reports usage as a delta since the
#: last status() call — the same 5 s cadence the panel already polls at.
CPU_STAT_PATH = pathlib.Path("/proc/stat")
CPUFREQ_ROOT = pathlib.Path("/sys/devices/system/cpu")


def _read_cpu_times(path: pathlib.Path = CPU_STAT_PATH) -> dict[int, tuple[int, int]]:
    times: dict[int, tuple[int, int]] = {}
    try:
        lines = path.read_text(encoding="ascii", errors="strict").splitlines()
    except OSError:
        return times
    for line in lines:
        if not line.startswith("cpu") or len(line) <= 3 or line[3] == " ":
            continue
        parts = line.split()
        try:
            index = int(parts[0][3:])
            fields = [int(value) for value in parts[1:11]]
        except (ValueError, IndexError):
            continue
        if len(fields) < 4:
            continue
        idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
        times[index] = (idle, sum(fields))
    return times


CPUINFO_PATH = pathlib.Path("/proc/cpuinfo")


def _read_core_frequencies_from_cpuinfo(path: pathlib.Path = CPUINFO_PATH) -> dict[int, int]:
    """Fallback used when the board has no cpufreq scaling directory at all.

    A stock BC-250 runs without a cpufreq governor, so
    /sys/devices/system/cpu/cpuN/cpufreq never exists — this is the same
    /proc/cpuinfo "cpu MHz" fallback psutil.cpu_freq() uses on Linux when the
    sysfs path is absent, kept dependency-free since Decky's embedded Python
    is not guaranteed to ship psutil.
    """
    frequencies: dict[int, int] = {}
    try:
        text = path.read_text(encoding="ascii", errors="ignore")
    except OSError:
        return frequencies
    index: int | None = None
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "processor":
            try:
                index = int(value)
            except ValueError:
                index = None
        elif key == "cpu mhz" and index is not None:
            try:
                frequencies[index] = round(float(value))
            except ValueError:
                continue
    return frequencies


def _read_core_frequencies_mhz(root: pathlib.Path = CPUFREQ_ROOT) -> dict[int, int]:
    frequencies: dict[int, int] = {}
    try:
        cpu_dirs = sorted(root.glob("cpu[0-9]*"))
    except OSError:
        cpu_dirs = []
    for cpu_dir in cpu_dirs:
        try:
            index = int(cpu_dir.name[3:])
            raw = (cpu_dir / "cpufreq" / "scaling_cur_freq").read_text(encoding="ascii").strip()
            frequencies[index] = round(int(raw) / 1000)
        except (OSError, ValueError):
            continue
    if not frequencies:
        frequencies = _read_core_frequencies_from_cpuinfo()
    return frequencies


CPU_PROFILE_KEYS = ("board_average", "mid_point", "safe_maximum")


def _validated_cpu_profiles(custom: object) -> list[dict[str, object]]:
    """Defensively re-check the helper's own already-validated CPU presets.

    Membership in CPU_FREQUENCIES/CPU_VIDS enforces the exact same ladder
    apply_cpu_tuning() requires, so a preset built from this list can never
    be rejected by that check — but it also means a stale export naming a
    value outside the current ladder is silently dropped here rather than
    shown as a button that would fail when pressed.
    """
    if not isinstance(custom, list):
        return []
    profiles: list[dict[str, object]] = []
    for entry in custom:
        if not isinstance(entry, dict):
            continue
        key, name = entry.get("key"), entry.get("name")
        frequency, vid = entry.get("frequency"), entry.get("vid")
        if (
            key not in CPU_PROFILE_KEYS
            or not isinstance(name, str) or not name
            or isinstance(frequency, bool) or frequency not in CPU_FREQUENCIES
            or isinstance(vid, bool) or vid not in CPU_VIDS
        ):
            continue
        profiles.append({"key": key, "name": name, "frequency": frequency, "vid": vid})
    return profiles



# ---------------------------------------------------------------- per game
#: The player's per-game choices: which GPU profile and which fan preset a
#: game runs with. Only names that already exist on the panel are stored —
#: never a frequency, a duty or a voltage — so the root helper validates each
#: one again exactly as if the player had pressed the button. The CPU is not
#: part of it on purpose: its overclock is only trusted after a stress test
#: of up to fifteen minutes, which cannot run every time a game starts.
GAME_PROFILES_FILENAME = "game-profiles.json"
GAME_PROFILES_SCHEMA = 1
MAX_GAME_PROFILES = 200
MAX_GAME_NAME = 80
GAME_FAN_PRESETS = FAN_PRESETS
MAX_APP_ID = 2 ** 64 - 1


def _app_id(value: object) -> str | None:
    """A Steam app id (or a non-Steam shortcut's) as a canonical string."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and value.isdigit() and len(value) <= 20:
        number = int(value)
    else:
        return None
    return str(number) if 0 < number <= MAX_APP_ID else None


def _game_name(value: object) -> str:
    text = " ".join(str(value or "").split())
    return text[:MAX_GAME_NAME]


def _game_entry(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    gpu = value.get("gpu")
    fan = value.get("fan")
    gpu = gpu if gpu in GPU_PROFILES else None
    fan = fan if fan in GAME_FAN_PRESETS else None
    if gpu is None and fan is None:
        return None
    return {"name": _game_name(value.get("name")), "gpu": gpu, "fan": fan}


def _game_snapshot(value: object) -> dict[str, object]:
    source = value if isinstance(value, dict) else {}
    gpu = source.get("gpu")
    safe_point = source.get("gpu_safe_point")
    fan = source.get("fan")
    return {
        "gpu": gpu if gpu in GPU_PROFILES else None,
        "gpu_safe_point": safe_point if type(safe_point) is int and 100 <= safe_point <= 3000 else None,
        "fan": fan if fan in GAME_FAN_PRESETS else None,
        "fan_service": source.get("fan_service") is True,
    }


def _empty_game_store() -> dict[str, object]:
    return {"schema": GAME_PROFILES_SCHEMA, "enabled": True, "games": {}, "session": None}


def _load_game_store(path: pathlib.Path) -> dict[str, object]:
    """Everything on disk re-checked; a damaged file becomes an empty store."""
    store = _empty_game_store()
    try:
        if path.stat().st_size > 256 * 1024:
            return store
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return store
    if not isinstance(document, dict) or document.get("schema") != GAME_PROFILES_SCHEMA:
        return store
    store["enabled"] = document.get("enabled") is not False
    games = document.get("games")
    if isinstance(games, dict):
        for raw_id, raw_entry in list(games.items())[:MAX_GAME_PROFILES]:
            app_id = _app_id(raw_id)
            entry = _game_entry(raw_entry)
            if app_id and entry:
                store["games"][app_id] = entry
    session = document.get("session")
    if isinstance(session, dict) and _app_id(session.get("app_id")):
        applied = session.get("applied") if isinstance(session.get("applied"), dict) else {}
        store["session"] = {
            "app_id": _app_id(session.get("app_id")),
            "name": _game_name(session.get("name")),
            "snapshot": _game_snapshot(session.get("snapshot")),
            "applied": {
                "gpu": applied.get("gpu") if applied.get("gpu") in GPU_PROFILES else None,
                "fan": applied.get("fan") if applied.get("fan") in GAME_FAN_PRESETS else None,
            },
        }
    return store


def _save_game_store(path: pathlib.Path, store: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(store, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o644)
    os.replace(temporary, path)


def _current_gpu_choice(status: dict) -> tuple[str | None, int | None]:
    """The panel profile (or TOML safe point) the live GPU range matches."""
    live = status.get("gpu_range")
    if not isinstance(live, (list, tuple)) or len(live) != 2:
        return None, None
    for profile in status.get("gpu_profiles") or []:
        if isinstance(profile, dict) and [profile.get("min"), profile.get("max")] == list(live):
            key = profile.get("key")
            if key in GPU_PROFILES:
                return str(key), None
    ceilings = {
        point.get("frequency") for point in status.get("gpu_safe_point_ceilings") or []
        if isinstance(point, dict)
    }
    if live[0] == 1000 and live[1] in ceilings and type(live[1]) is int:
        return None, int(live[1])
    return None, None


# ---------------------------------------------------------------- ACE usage
#: How often /proc is searched for processes that opened the GPU since, and
#: how often everything is searched again. Between searches only the few
#: DRM fdinfo files already found are read: a Proton game holds tens of
#: thousands of descriptors, and walking them all every poll is the cost the
#: desktop's Performance page learned to avoid.
ACE_REDISCOVER_SECONDS = 15.0
ACE_YOUNG_PROCESS_SECONDS = 120.0
ACE_FULL_RESCAN_SECONDS = 300.0


def _compute_counters(text: str) -> tuple[str | None, int] | None:
    """(client id, compute-engine ns) from one amdgpu fdinfo, else None."""
    client: str | None = None
    amdgpu = False
    compute = 0
    for line in text.splitlines():
        if line.startswith("drm-driver:"):
            amdgpu = line.partition(":")[2].strip() == "amdgpu"
        elif line.startswith("drm-client-id:"):
            client = line.partition(":")[2].strip() or None
        elif line.startswith("drm-engine-compute:"):
            fields = line.partition(":")[2].split()
            if len(fields) >= 2 and fields[1] == "ns" and fields[0].isdigit():
                compute = int(fields[0])
    return (client, compute) if amdgpu else None


class AceSampler:
    """How busy the compute (ACE) queues were between two polls, and for whom.

    ``drm-engine-compute`` in amdgpu's per-client fdinfo only advances while
    work runs on the compute rings: a game's client moving it is the proof it
    really uses async compute, not merely that the driver exposes it.
    """

    def __init__(self, proc: str = "/proc", clock=time.monotonic) -> None:
        self._proc = proc
        self._clock = clock
        self._paths: list[str] = []
        self._by_pid: dict[str, tuple[float | None, list[str]]] = {}
        self._discovered_at: float | None = None
        self._full_scan_at: float | None = None
        self._previous: tuple[float, dict[str, int]] | None = None
        self._owners: dict[str, str] = {}

    def _read(self, path: str) -> str | None:
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                return handle.read()
        except OSError:
            return None

    def _uptime(self) -> float | None:
        text = self._read(f"{self._proc}/uptime")
        try:
            return float(text.split()[0]) if text else None
        except (IndexError, ValueError):
            return None

    def _started(self, pid: str) -> float | None:
        text = self._read(f"{self._proc}/{pid}/stat")
        fields = text.rpartition(")")[2].split() if text else []
        try:
            return int(fields[19]) / os.sysconf("SC_CLK_TCK")
        except (IndexError, ValueError, OSError):
            return None

    def _scan_pid(self, pid: str) -> list[str]:
        paths: list[str] = []
        fd_dir = f"{self._proc}/{pid}/fd"
        try:
            descriptors = os.listdir(fd_dir)
        except OSError:
            return paths
        for descriptor in descriptors:
            try:
                target = os.readlink(f"{fd_dir}/{descriptor}")
            except OSError:
                continue
            if target.startswith("/dev/dri/"):
                paths.append(f"{self._proc}/{pid}/fdinfo/{descriptor}")
        return paths

    def _discover(self, now: float) -> list[str]:
        try:
            pids = [name for name in os.listdir(self._proc) if name.isdigit()]
        except OSError:
            return []
        if self._full_scan_at is None or now - self._full_scan_at >= ACE_FULL_RESCAN_SECONDS:
            self._full_scan_at = now
            self._by_pid = {}
        uptime = self._uptime()
        by_pid: dict[str, tuple[float | None, list[str]]] = {}
        for pid in pids:
            known = self._by_pid.get(pid)
            if known is None:
                by_pid[pid] = (self._started(pid), self._scan_pid(pid))
                continue
            started, paths = known
            young = started is not None and uptime is not None and uptime - started < ACE_YOUNG_PROCESS_SECONDS
            by_pid[pid] = (started, self._scan_pid(pid)) if not paths and young else known
        self._by_pid = by_pid
        return [path for _started, paths in by_pid.values() for path in paths]

    def sample(self) -> dict[str, object]:
        now = self._clock()
        if self._discovered_at is None or now - self._discovered_at >= ACE_REDISCOVER_SECONDS:
            self._paths = self._discover(now)
            self._discovered_at = now
        counters: dict[str, int] = {}
        owners: dict[str, str] = {}
        alive: list[str] = []
        amdgpu_seen = False
        for path in self._paths:
            text = self._read(path)
            if text is None:
                continue
            alive.append(path)
            parsed = _compute_counters(text)
            if parsed is None:
                continue
            amdgpu_seen = True
            client, compute = parsed
            key = client or path
            if compute >= counters.get(key, 0):
                counters[key] = compute
                owners[key] = path[len(self._proc) + 1:].partition("/")[0]
        self._paths = alive
        result: dict[str, object] = {
            "ace_available": amdgpu_seen,
            "ace_busy_percent": None,
            "ace_process": "",
        }
        previous = self._previous
        self._previous = (now, counters)
        if previous is None:
            self._owners = owners
            return result
        elapsed_ns = (now - previous[0]) * 1_000_000_000
        moved = {
            client: counters[client] - before
            for client, before in previous[1].items()
            if client in counters and counters[client] > before
        }
        if elapsed_ns > 0:
            busy = sum(moved.values()) / elapsed_ns * 100
            result["ace_busy_percent"] = int(max(0, min(100, round(busy))))
        if moved:
            busiest = max(moved, key=moved.__getitem__)
            pid = owners.get(busiest) or self._owners.get(busiest, "")
            comm = self._read(f"{self._proc}/{pid}/comm") if pid.isdigit() else None
            result["ace_process"] = (comm or "").strip()
        self._owners = owners
        return result


class Plugin:
    def __init__(self) -> None:
        self._operation_lock = asyncio.Lock()
        # Serialize every helper subprocess, including passive status reads.
        # Polling therefore waits behind a write instead of racing UMR/hwmon,
        # while the operation lock still rejects duplicate action clicks.
        self._helper_lock = asyncio.Lock()
        # Session-only feedback for the player.  It is intentionally bounded
        # and in-memory: QAM must not create a second persistent tuning store.
        self._recent_actions: list[dict[str, object]] = []
        self._last_cpu_times: dict[int, tuple[int, int]] = {}
        self._ace = AceSampler()
        # One game start or stop at a time; they may wait behind a running
        # board operation, never interleave with each other.
        self._game_lock = asyncio.Lock()
        # Decky keeps each plugin's settings beside the plugins directory.
        settings = getattr(decky, "DECKY_PLUGIN_SETTINGS_DIR", "") or ""
        self._settings_dir = (
            pathlib.Path(settings) if settings
            else PLUGIN_ROOT.parent.parent / "settings" / PLUGIN_ROOT.name
        )

    def _cpu_usage_snapshot(self) -> dict[str, object]:
        times = _read_cpu_times()
        previous = self._last_cpu_times
        self._last_cpu_times = times
        per_core_percent: dict[int, float] = {}
        for index, (idle, total) in times.items():
            before = previous.get(index)
            if before is None:
                continue
            idle_delta = idle - before[0]
            total_delta = total - before[1]
            if total_delta <= 0:
                continue
            busy = max(0.0, min(100.0, 100.0 * (1 - idle_delta / total_delta)))
            per_core_percent[index] = round(busy, 1)
        frequencies = _read_core_frequencies_mhz()
        cores = sorted(set(times) | set(frequencies))
        aggregate = (
            round(sum(per_core_percent.values()) / len(per_core_percent), 1)
            if per_core_percent else None
        )
        return {
            "cpu_usage_percent": aggregate,
            "cpu_cores": [
                {"core": index, "percent": per_core_percent.get(index), "frequency_mhz": frequencies.get(index)}
                for index in cores
            ],
        }

    def _record_action(self, module: str, target: str, result: dict) -> dict:
        succeeded = result.get("ok") is not False
        self._recent_actions.append({
            "module": module,
            "target": target,
            "ok": succeeded,
            # Frontend dates use Date.now(), so publish Unix milliseconds.
            # The UI also accepts legacy seconds during a hot reload.
            "at": int(time.time() * 1000),
        })
        del self._recent_actions[:-MAX_RECENT_ACTIONS]
        # Keep an evidence trail in plugin_loader.service without logging raw
        # helper output, register dumps, or user-provided strings.
        decky.logger.info(
            "BC250 operation module=%s target=%s result=%s",
            module,
            target,
            "verified" if succeeded else "failed",
        )
        return result

    async def _main(self):
        decky.logger.info("BC250 Quick Access plugin ready")

    async def _unload(self):
        decky.logger.info("BC250 Quick Access plugin unloaded")

    @staticmethod
    def _trusted_helper() -> bool:
        """Do not execute a replaced Decky helper, even from a root plugin."""
        try:
            metadata = HELPER.lstat()
        except OSError:
            return False
        return (
            stat.S_ISREG(metadata.st_mode)
            and not stat.S_ISLNK(metadata.st_mode)
            and metadata.st_uid == 0
            and not metadata.st_mode & 0o022
            and bool(metadata.st_mode & stat.S_IXUSR)
        )

    @staticmethod
    def _contract_disagreement() -> str:
        """Read the shared contract and check this file was built against it.

        Called from ``_run``, not at import time, and that matters: Decky
        Loader imports this module, so an exception here at module scope means
        the BC250 panel never appears at all, with nothing on screen to say
        why. From inside ``_run`` the same problem reaches the panel as one
        sentence with one recovery action.

        Returns an empty string when everything agrees.
        """
        try:
            metadata = CONTRACT_PATH.lstat()
        except OSError:
            return ("BC250 shared contract is not installed. "
                    "Reinstall BC250 Control Center from Desktop Mode.")
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_mode & 0o022
        ):
            return ("BC250 shared contract is not a protected root-owned file. "
                    "Reinstall BC250 Control Center from Desktop Mode.")
        try:
            # ``-B`` is not implied here; avoid leaving a root-owned cache in
            # /usr/libexec.
            sys.dont_write_bytecode = True
            spec = importlib.util.spec_from_file_location("bc250_contract", CONTRACT_PATH)
            if spec is None or spec.loader is None:
                raise ImportError(CONTRACT_PATH)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except (OSError, ImportError, SyntaxError, ValueError):
            return ("BC250 shared contract could not be read. "
                    "Reinstall BC250 Control Center from Desktop Mode.")
        if module.CONTRACT_REVISION != REQUIRED_CONTRACT_REVISION:
            return (f"BC250 Quick Access was built for contract revision "
                    f"{REQUIRED_CONTRACT_REVISION} and this system has "
                    f"{module.CONTRACT_REVISION}. Reinstall both from Desktop Mode.")
        if module.QUICK_ACCESS_PROTOCOL != HELPER_PROTOCOL:
            return ("BC250 Quick Access and the installed helper are different "
                    "versions. Reinstall both from Desktop Mode.")
        if tuple(CPU_FREQUENCIES) != module.cpu_frequency_ladder():
            return ("BC250 Quick Access disagrees with this system about the CPU "
                    "frequency range. Reinstall both from Desktop Mode.")
        if tuple(CU_MODES) != tuple(str(value) for value in module.cu_targets()):
            return ("BC250 Quick Access disagrees with this system about the "
                    "Compute Units range. Reinstall both from Desktop Mode.")
        if VRAM_SIZE_PRESETS_MB != tuple(module.VRAM_SIZE_PRESETS_MB):
            return ("BC250 Quick Access disagrees with this system about the "
                    "VRAM presets. Reinstall both from Desktop Mode.")
        return ""

    def _run(self, *args: str, timeout: int = 190) -> dict:
        if not self._trusted_helper():
            return {"ok": False, "error": "BC250 helper is missing or not protected. Reinstall BC250 Quick Access from Desktop Mode."}
        disagreement = self._contract_disagreement()
        if disagreement:
            return {"ok": False, "error": disagreement}
        try:
            result = subprocess.run(
                [str(HELPER), *args], text=True, capture_output=True,
                timeout=timeout, check=False,
                env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "BC250 operation timed out; verify state in the full application."}
        output = (result.stdout or "").strip()
        if result.returncode:
            return {"ok": False, "error": (result.stderr or output or "BC250 helper failed.").strip()[-4000:]}
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            payload = {"ok": True, "message": output[-4000:]}
        return payload if isinstance(payload, dict) else {"ok": True, "value": payload}

    def _verified_status(self) -> dict:
        result = self._run("status", timeout=20)
        if result.get("ok") is False:
            return result
        if type(result.get("protocol")) is not int or result["protocol"] != HELPER_PROTOCOL:
            return {
                "ok": False,
                "error": (
                    "BC250 Quick Access helper protocol is incompatible. "
                    "Reinstall BC250 Control Center from Desktop Mode."
                ),
            }
        return result

    def _run_verified(self, *args: str, timeout: int = 190) -> dict:
        status = self._verified_status()
        if status.get("ok") is False:
            return status
        return self._run(*args, timeout=timeout)

    async def status(self) -> dict:
        async with self._helper_lock:
            result = await asyncio.to_thread(self._verified_status)
        if result.get("ok") is not False:
            self._decorate_status(result)
            result["recent_actions"] = list(reversed(self._recent_actions))
            result["helper_protected"] = True
        return result

    @staticmethod
    def _decorate_status(result: dict) -> dict:
        """The panel's profile ladders, from the helper's raw state."""
        if result.get("ok") is not False:
            allowed = result.get("gpu_allowed_range")
            governor = result.get("gpu_governor", "cyan")
            if isinstance(allowed, (list, tuple)) and len(allowed) == 2:
                try:
                    profiles = profiles_payload(
                        int(allowed[0]), int(allowed[1]), governor=governor,
                    )
                    result["gpu_profiles"] = _apply_custom_profile_names(
                        profiles, result.get("gpu_custom_profiles"), int(allowed[0]), int(allowed[1]),
                    )
                except (TypeError, ValueError, OverflowError):
                    result.pop("gpu_profiles", None)
            result.pop("gpu_custom_profiles", None)
            result["cpu_profiles"] = _validated_cpu_profiles(result.get("cpu_custom_profiles"))
            result.pop("cpu_custom_profiles", None)
        return result

    async def cpu_telemetry(self) -> dict:
        """Read CPU clocks during a long tuning action without queuing.

        The normal status route intentionally shares the helper lock with
        writes.  This endpoint is a separate read-only helper action and must
        remain outside both operation locks so the Decky panel stays alive
        while bc250-detect is running.
        """
        result = await asyncio.to_thread(self._run, "cpu-telemetry", timeout=5)
        if result.get("ok") is False:
            return result
        if type(result.get("protocol")) is not int or result["protocol"] != HELPER_PROTOCOL:
            return {
                "ok": False,
                "error": "BC250 CPU telemetry protocol is incompatible. Reinstall BC250 Control Center from Desktop Mode.",
            }
        return result

    async def gddr6_sensors(self) -> dict:
        """Read the last per-chip GDDR6 sample, outside every write lock.

        Same reasoning as cpu_telemetry(): this is a separate, independent
        subprocess (its own advisory lock on the shared SMU/SMN interface),
        never the SMU patch itself -- applying that patch stays desktop-only,
        pkexec-gated. Polled on its own cadence since a cold read (git/stat
        checks inside the reader) is slower than the other passive reads.
        """
        result = await asyncio.to_thread(self._run, "gddr6-sensors", timeout=20)
        if result.get("ok") is False:
            return result
        if type(result.get("protocol")) is not int or result["protocol"] != HELPER_PROTOCOL:
            return {
                "ok": False,
                "error": "BC250 GDDR6 sensor protocol is incompatible. Reinstall BC250 Control Center from Desktop Mode.",
            }
        return result

    async def monitor_snapshot(self) -> dict:
        """Read the passive GPU/board/fan/memory bundle without the write lock.

        The Monitorización and Memoria y Video tabs poll this instead of
        status(): a CU or GPU write can hold the helper lock for status()'s
        own UMR/D-Bus pass for a long time (cpu-detect up to ~920s), and
        before this endpoint existed those tabs simply froze on stale data
        for the whole duration — this is the fix for that, mirroring the
        same reasoning cpu_telemetry() already uses for CPU clocks.
        """
        result = await asyncio.to_thread(self._run, "qam-sensors", timeout=10)
        if result.get("ok") is False:
            return result
        if type(result.get("protocol")) is not int or result["protocol"] != HELPER_PROTOCOL:
            return {
                "ok": False,
                "error": "BC250 Quick Access sensor protocol is incompatible. Reinstall BC250 Control Center from Desktop Mode.",
            }
        # Both are plain /run and /proc reads with no helper subprocess at
        # all, so they belong beside qam-sensors rather than inside status():
        # a status() call cannot even acquire the helper lock while a write
        # holds it, so anything computed after that lock was previously
        # frozen for the same ~920s a cpu-detect can take.
        result.update(await asyncio.to_thread(_read_vrm_telemetry))
        result.update(await asyncio.to_thread(self._cpu_usage_snapshot))
        # The same amdgpu counter the desktop's Performance › Async compute
        # view reads: busy share of the compute queues since the last poll.
        result.update(await asyncio.to_thread(self._ace.sample))
        return result

    async def _run_single_operation(self, *args: str, timeout: int = 190) -> dict:
        """Run one protected helper operation at a time, never queue clicks."""
        if self._operation_lock.locked():
            return {
                "ok": False,
                "error": "BC250 Quick Access is already applying an operation. Wait for its verified result before choosing another control.",
            }
        async with self._operation_lock, self._helper_lock:
            return await asyncio.to_thread(self._run_verified, *args, timeout=timeout)

    async def apply_gpu_profile(self, profile: str) -> dict:
        if profile not in GPU_PROFILES:
            return {"ok": False, "error": "Unsupported GPU Quick Access profile."}
        if self._operation_lock.locked():
            return {
                "ok": False,
                "error": "A BC250 operation is still running. Wait for the verified result before changing the GPU range.",
            }
        async with self._operation_lock:
            async with self._helper_lock:
                # The root helper accepts only a named profile and performs
                # its own active-governor validation and backend-specific
                # read-back. Running a
                # complete status scan before it added 5–10 seconds of CPU,
                # CU and fan reads to every GPU press without improving this
                # hardware boundary.
                result = await asyncio.to_thread(self._run, "gpu-profile", profile, timeout=30)
            return self._record_action("gpu", profile, result)

    async def apply_gpu_safe_point(self, frequency: int) -> dict:
        """Apply one ceiling advertised by the selected protected governor.

        The helper validates Cyan TOML or Oberon's reviewed curve immediately
        before the backend-specific operation.
        This outer boundary keeps arbitrary numeric ranges out of the Decky
        RPC contract without performing an extra, slow whole-panel status scan.
        """
        if isinstance(frequency, bool) or type(frequency) not in {int, str}:
            return {"ok": False, "error": "Unsupported GPU safe-point."}
        try:
            normalized = int(frequency)
        except (TypeError, ValueError, OverflowError):
            return {"ok": False, "error": "Unsupported GPU safe-point."}
        if str(normalized) != str(frequency):
            return {"ok": False, "error": "Unsupported GPU safe-point."}
        if self._operation_lock.locked():
            return {
                "ok": False,
                "error": "A BC250 operation is still running. Wait for its verified result before changing the GPU range.",
        }
        async with self._operation_lock:
            async with self._helper_lock:
                result = await asyncio.to_thread(
                    self._run, "gpu-safe-point", str(normalized), timeout=30,
                )
            return self._record_action("gpu", f"toml-{normalized}", result)

    async def set_gpu_high_frequency_points(self, enabled: bool) -> dict:
        """Comment/uncomment the Cyan TOML safe-points above 2000 MHz.

        Mirrors the Desktop's "Enable/Disable +2000 MHz TOML points" button.
        A persistent-file edit only: it never restarts Cyan or changes the
        live GPU range, so it does not need cpu-detect's long timeout.
        """
        if self._operation_lock.locked():
            return {
                "ok": False,
                "error": "A BC250 operation is still running. Wait for its verified result before changing the GPU TOML.",
            }
        async with self._operation_lock:
            async with self._helper_lock:
                result = await asyncio.to_thread(
                    self._run, "gpu-high-points", "1" if enabled else "0", timeout=30,
                )
            return self._record_action("gpu", f"toml-high-points-{'on' if enabled else 'off'}", result)

    async def set_gpu_governor_service(self, enabled: bool) -> dict:
        """Enable and start, or disable and stop, the installed GPU governor.

        The helper chooses the unit itself — the running governor, else the
        one enabled for boot, else the only one installed — refuses while both
        governors run, and reads systemd back before it reports success.
        """
        if type(enabled) is not bool:
            return {"ok": False, "error": "Unsupported GPU governor service request."}
        if self._operation_lock.locked():
            return {
                "ok": False,
                "error": "A BC250 operation is still running. Wait for its verified result before changing the GPU governor service.",
            }
        async with self._operation_lock:
            async with self._helper_lock:
                result = await asyncio.to_thread(
                    self._run, "gpu-service", "enable" if enabled else "disable", timeout=60,
                )
            return self._record_action("gpu", f"service-{'on' if enabled else 'off'}", result)

    async def apply_gpu_voltage_level(self, level: int) -> dict:
        """Governor curve (0) or +10/+20/+30 mV above 2000 MHz (1-3).

        The helper restarts Cyan so it reads the new curve and puts the live
        range back afterwards, which is why the timeout is longer than a
        plain range change.
        """
        if isinstance(level, bool) or type(level) is not int or level not in (0, 1, 2, 3):
            return {"ok": False, "error": "Unsupported GPU voltage level."}
        if self._operation_lock.locked():
            return {
                "ok": False,
                "error": "A BC250 operation is still running. Wait for its verified result before changing the GPU voltage curve.",
            }
        async with self._operation_lock:
            async with self._helper_lock:
                result = await asyncio.to_thread(
                    self._run, "gpu-voltage-level", str(level), timeout=90,
                )
            return self._record_action("gpu", f"voltage-level-{level}", result)

    async def apply_gpu_voltage_points(self, points: list[dict]) -> dict:
        """Set a few TOML points; the helper bounds each one again."""
        if not isinstance(points, list) or not 1 <= len(points) <= 17:
            return {"ok": False, "error": "Unsupported GPU voltage request."}
        arguments: list[str] = []
        for point in points:
            if not isinstance(point, dict):
                return {"ok": False, "error": "Unsupported GPU voltage request."}
            frequency, voltage = point.get("frequency"), point.get("voltage")
            if (
                isinstance(frequency, bool) or isinstance(voltage, bool)
                or type(frequency) is not int or type(voltage) is not int
                or not 100 <= frequency <= 3000 or not 600 <= voltage <= 1210
            ):
                return {"ok": False, "error": "Unsupported GPU voltage request."}
            arguments.append(f"{frequency}={voltage}")
        if self._operation_lock.locked():
            return {
                "ok": False,
                "error": "A BC250 operation is still running. Wait for its verified result before changing the GPU voltage curve.",
            }
        async with self._operation_lock:
            async with self._helper_lock:
                result = await asyncio.to_thread(
                    self._run, "gpu-voltage-custom", *arguments, timeout=90,
                )
            return self._record_action("gpu", "voltage-custom", result)

    async def apply_cu_mode(self, mode: str) -> dict:
        aliases = {"stock": "24", "full": "40"}
        mode = aliases.get(str(mode), str(mode))
        if mode not in CU_MODES:
            return {"ok": False, "error": "Unsupported CU Quick Access mode."}
        result = await self._run_single_operation("cu-mode", mode, timeout=480)
        return self._record_action("cu", mode, result)

    async def apply_cu_table(self, masks: list[int] | tuple[int, ...]) -> dict:
        """Apply exactly four bounded WGP row masks through the closed helper."""
        if not isinstance(masks, (list, tuple)) or len(masks) != 4:
            return {"ok": False, "error": "A CU table must contain exactly four row masks."}
        if any(type(mask) is not int or not 0 <= mask <= 0x1F for mask in masks):
            return {"ok": False, "error": "Every CU row mask must be an integer from 0 through 31."}
        active_cus = sum(mask.bit_count() * 2 for mask in masks)
        if active_cus not in range(24, 41, 2):
            return {"ok": False, "error": "Quick Access CU tables must route 24 through 40 CUs in WGP pairs."}
        normalized = tuple(str(mask) for mask in masks)
        result = await self._run_single_operation("cu-table", *normalized, timeout=480)
        target = f"{active_cus}cu:{'-'.join(f'{mask:02x}' for mask in masks)}"
        return self._record_action("cu", target, result)

    async def save_cu_table(self, masks: list[int] | tuple[int, ...]) -> dict:
        """Apply and persist exactly one bounded four-row WGP table."""
        if not isinstance(masks, (list, tuple)) or len(masks) != 4:
            return {"ok": False, "error": "A CU table must contain exactly four row masks."}
        if any(type(mask) is not int or not 0 <= mask <= 0x1F for mask in masks):
            return {"ok": False, "error": "Every CU row mask must be an integer from 0 through 31."}
        active_cus = sum(mask.bit_count() * 2 for mask in masks)
        if active_cus not in range(24, 41, 2):
            return {"ok": False, "error": "Quick Access CU tables must route 24 through 40 CUs in WGP pairs."}
        result = await self._run_single_operation(
            "cu-save", *(str(mask) for mask in masks), timeout=660,
        )
        target = f"saved-{active_cus}cu:{'-'.join(f'{mask:02x}' for mask in masks)}"
        return self._record_action("cu", target, result)

    async def install_cu_service(self) -> dict:
        result = await self._run_single_operation("cu-service", "install", timeout=240)
        return self._record_action("cu", "service-install", result)

    async def remove_cu_service(self) -> dict:
        result = await self._run_single_operation("cu-service", "remove", timeout=90)
        return self._record_action("cu", "service-remove", result)

    async def apply_system_fan_preset(self, preset: str) -> dict:
        if preset not in FAN_PRESETS:
            return {"ok": False, "error": "Unsupported system-fan preset."}
        result = await self._run_single_operation("fan-system", preset, timeout=30)
        return self._record_action("fan", preset, result)

    async def apply_fan_channel(self, channel: int, target: int | str) -> dict:
        """Apply one temporary setting without exposing a generic root argv."""
        if isinstance(channel, bool) or type(channel) not in {int, str}:
            return {"ok": False, "error": "Unsupported Quick Access fan channel."}
        try:
            normalized_channel = int(channel)
        except (TypeError, ValueError, OverflowError):
            return {"ok": False, "error": "Unsupported Quick Access fan channel."}
        if str(normalized_channel) != str(channel) or normalized_channel not in FAN_CHANNELS:
            return {"ok": False, "error": "Unsupported Quick Access fan channel."}

        if target == "automatic":
            normalized_target = "automatic"
        else:
            if isinstance(target, bool) or type(target) not in {int, str}:
                return {"ok": False, "error": "Fan speed must be Automatic or 20–100%."}
            try:
                percent = int(target)
            except (TypeError, ValueError, OverflowError):
                return {"ok": False, "error": "Fan speed must be Automatic or 20–100%."}
            if str(percent) != str(target) or not FAN_MIN_PERCENT <= percent <= FAN_MAX_PERCENT:
                return {"ok": False, "error": "Fan speed must be Automatic or 20–100%."}
            normalized_target = str(percent)

        result = await self._run_single_operation(
            "fan-channel", str(normalized_channel), normalized_target, timeout=30,
        )
        return self._record_action("fan", f"pwm{normalized_channel}:{normalized_target}", result)

    async def apply_saved_cpu_profile(self) -> dict:
        result = await self._run_single_operation("cpu-apply-saved", timeout=920)
        return self._record_action("cpu", "saved", result)

    @staticmethod
    def _cpu_value(value: int, allowed: tuple[int, ...], label: str) -> int:
        if isinstance(value, bool) or type(value) not in {int, str}:
            raise ValueError(f"Unsupported CPU {label}.")
        try:
            normalized = int(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"Unsupported CPU {label}.") from exc
        if str(normalized) != str(value) or normalized not in allowed:
            raise ValueError(f"Unsupported CPU {label}.")
        return normalized

    async def apply_cpu_tuning(self, frequency: int, vid: int) -> dict:
        try:
            frequency = self._cpu_value(frequency, CPU_FREQUENCIES, "frequency")
            vid = self._cpu_value(vid, CPU_VIDS, "maximum VID")
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        result = await self._run_single_operation(
            "cpu-detect", str(frequency), str(vid), timeout=920,
        )
        return self._record_action("cpu", f"detect-{frequency}:{vid}", result)

    async def apply_cpu_scale(self, frequency: int, scale: int) -> dict:
        try:
            frequency = self._cpu_value(frequency, CPU_FREQUENCIES, "frequency")
            scale = self._cpu_value(scale, CPU_SCALES, "scale")
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        result = await self._run_single_operation(
            "cpu-scale", str(frequency), str(scale), timeout=200,
        )
        return self._record_action("cpu", f"manual-{frequency}:{scale}", result)

    async def install_cpu_service(self) -> dict:
        # The root CPU helper, not Decky's process memory, validates that the
        # detector result is protected, exact, applied live and from this boot.
        result = await self._run_single_operation(
            "cpu-service", "install", timeout=180,
        )
        return self._record_action("cpu", "service-install-detected", result)

    async def remove_cpu_service(self) -> dict:
        result = await self._run_single_operation(
            "cpu-service", "remove", timeout=90,
        )
        return self._record_action("cpu", "service-remove", result)

    async def apply_vram_size(self, size_mb: int) -> dict:
        """Write one VRAM (UMA_SIZE) preset to CMOS. Activates on next reboot."""
        if isinstance(size_mb, bool) or type(size_mb) not in {int, str}:
            return {"ok": False, "error": "Unsupported VRAM size."}
        try:
            normalized = int(size_mb)
        except (TypeError, ValueError, OverflowError):
            return {"ok": False, "error": "Unsupported VRAM size."}
        if str(normalized) != str(size_mb) or normalized not in VRAM_SIZE_PRESETS_MB:
            return {"ok": False, "error": "Unsupported VRAM size."}
        result = await self._run_single_operation("vram-apply", str(normalized), timeout=30)
        return self._record_action("vram", str(normalized), result)

    # ------------------------------------------------------------ per game
    def _game_store_path(self) -> pathlib.Path:
        return self._settings_dir / GAME_PROFILES_FILENAME

    def _public_games(self, store: dict) -> dict:
        session = store.get("session")
        games = sorted(
            ({"app_id": app_id, **entry} for app_id, entry in store["games"].items()),
            key=lambda entry: str(entry.get("name") or "").lower(),
        )
        return {
            "ok": True,
            "enabled": bool(store.get("enabled")),
            "games": games,
            "session": (
                {"app_id": session["app_id"], "name": session["name"], "applied": session["applied"]}
                if session else None
            ),
        }

    async def game_profiles(self) -> dict:
        store = await asyncio.to_thread(_load_game_store, self._game_store_path())
        return self._public_games(store)

    async def save_game_profile(self, app_id: int | str, name: str, gpu: str | None, fan: str | None) -> dict:
        key = _app_id(app_id)
        if key is None:
            return {"ok": False, "error": "Unsupported game id."}
        gpu = gpu or None
        fan = fan or None
        if gpu is not None and gpu not in GPU_PROFILES:
            return {"ok": False, "error": "Unsupported GPU Quick Access profile."}
        if fan is not None and fan not in GAME_FAN_PRESETS:
            return {"ok": False, "error": "Unsupported system-fan preset."}
        entry = _game_entry({"name": name, "gpu": gpu, "fan": fan})
        if entry is None:
            return {"ok": False, "error": "Choose a GPU profile or a fan preset for this game."}
        async with self._game_lock:
            path = self._game_store_path()
            store = await asyncio.to_thread(_load_game_store, path)
            if key not in store["games"] and len(store["games"]) >= MAX_GAME_PROFILES:
                return {"ok": False, "error": "The per-game profile list is full. Remove a game first."}
            store["games"][key] = entry
            await asyncio.to_thread(_save_game_store, path, store)
        decky.logger.info("BC250 game profile saved app=%s gpu=%s fan=%s", key, gpu, fan)
        return self._public_games(store)

    async def remove_game_profile(self, app_id: int | str) -> dict:
        key = _app_id(app_id)
        if key is None:
            return {"ok": False, "error": "Unsupported game id."}
        async with self._game_lock:
            path = self._game_store_path()
            store = await asyncio.to_thread(_load_game_store, path)
            store["games"].pop(key, None)
            await asyncio.to_thread(_save_game_store, path, store)
        return self._public_games(store)

    async def set_game_profiles_enabled(self, enabled: bool) -> dict:
        if type(enabled) is not bool:
            return {"ok": False, "error": "Unsupported per-game profile request."}
        async with self._game_lock:
            path = self._game_store_path()
            store = await asyncio.to_thread(_load_game_store, path)
            store["enabled"] = enabled
            await asyncio.to_thread(_save_game_store, path, store)
        return self._public_games(store)

    async def game_started(self, app_id: int | str, name: str = "", refresh: bool = False) -> dict:
        """Apply the game's saved GPU profile and fan preset, remembering what
        they replaced so ``game_stopped`` can put it back.

        ``refresh`` re-applies a profile the player just edited while that
        game runs: the board goes back to what it was first, then takes the
        new choice, so the remembered state stays the pre-game one.
        """
        key = _app_id(app_id)
        if key is None or type(refresh) is not bool:
            return {"ok": False, "applied": False, "error": "Unsupported game id."}
        async with self._game_lock:
            path = self._game_store_path()
            store = await asyncio.to_thread(_load_game_store, path)
            session = store.get("session")
            if session and session["app_id"] == key and not refresh:
                # Decky reloaded mid-game, or the notice came twice.
                return {"ok": True, "applied": False, "reason": "already-applied"}
            if session:
                # The previous game never reported its end: put the board
                # back before this one takes it.
                await self._restore_game_session(store)
            entry = store["games"].get(key)
            if not store.get("enabled") or entry is None:
                return {"ok": True, "applied": False, "reason": "no-profile"}
            if self._operation_lock.locked():
                return {
                    "ok": False, "applied": False,
                    "error": "A BC250 operation is still running; this game's profile was not applied.",
                }
            async with self._operation_lock, self._helper_lock:
                result = await asyncio.to_thread(
                    self._apply_game_profile, key, _game_name(name) or str(entry["name"]), entry,
                )
            store["session"] = result.pop("session")
            await asyncio.to_thread(_save_game_store, path, store)
            return result

    async def game_stopped(self, app_id: int | str) -> dict:
        key = _app_id(app_id)
        if key is None:
            return {"ok": False, "restored": False, "error": "Unsupported game id."}
        async with self._game_lock:
            store = await asyncio.to_thread(_load_game_store, self._game_store_path())
            session = store.get("session")
            if not session or session["app_id"] != key:
                return {"ok": True, "restored": False}
            return await self._restore_game_session(store)

    async def _restore_game_session(self, store: dict) -> dict:
        session = store["session"]
        # Waits behind a board operation already running rather than skip:
        # leaving the game's profile on after the game is the worse outcome.
        async with self._operation_lock, self._helper_lock:
            result = await asyncio.to_thread(self._restore_game_state, session)
        store["session"] = None
        await asyncio.to_thread(_save_game_store, self._game_store_path(), store)
        return result

    def _apply_game_profile(self, app_id: str, name: str, entry: dict) -> dict:
        status = self._verified_status()
        if status.get("ok") is False:
            return {"ok": False, "applied": False, "error": status.get("error"), "session": None}
        self._decorate_status(status)
        gpu_key, safe_point = _current_gpu_choice(status)
        live_fan = status.get("system_fan_preset")
        snapshot = {
            "gpu": gpu_key,
            "gpu_safe_point": safe_point,
            "fan": live_fan if live_fan in GAME_FAN_PRESETS else None,
            "fan_service": status.get("system_fan_policy") is True,
        }
        applied: dict[str, str | None] = {"gpu": None, "fan": None}
        errors: list[str] = []
        if entry.get("gpu") and entry["gpu"] != gpu_key:
            result = self._record_action("gpu", f"game-{entry['gpu']}", self._run("gpu-profile", str(entry["gpu"]), timeout=30))
            if result.get("ok") is False:
                errors.append(str(result.get("error") or "GPU profile failed."))
            else:
                applied["gpu"] = str(entry["gpu"])
        if entry.get("fan") and entry["fan"] != snapshot["fan"]:
            result = self._record_action("fan", f"game-{entry['fan']}", self._run("fan-system", str(entry["fan"]), timeout=30))
            if result.get("ok") is False:
                errors.append(str(result.get("error") or "Fan preset failed."))
            else:
                applied["fan"] = str(entry["fan"])
        session = (
            {"app_id": app_id, "name": name, "snapshot": snapshot, "applied": applied}
            if applied["gpu"] or applied["fan"] else None
        )
        return {
            "ok": not errors, "applied": session is not None, "name": name,
            "gpu": applied["gpu"], "fan": applied["fan"],
            "error": " ".join(errors), "session": session,
        }

    def _restore_game_state(self, session: dict) -> dict:
        snapshot = _game_snapshot(session.get("snapshot"))
        applied = session.get("applied") or {}
        errors: list[str] = []
        status = self._verified_status()
        if status.get("ok") is False:
            return {"ok": False, "restored": False, "name": session.get("name", ""), "error": status.get("error")}
        operations: list[tuple[str, tuple[str, ...]]] = []
        if applied.get("gpu"):
            if snapshot["gpu"]:
                operations.append(("gpu", ("gpu-profile", str(snapshot["gpu"]))))
            elif snapshot["gpu_safe_point"]:
                operations.append(("gpu", ("gpu-safe-point", str(snapshot["gpu_safe_point"]))))
        if applied.get("fan"):
            if snapshot["fan_service"]:
                # The desktop's fan service follows its curve or preset again.
                operations.append(("fan", ("fan-resume",)))
            elif snapshot["fan"]:
                operations.append(("fan", ("fan-system", str(snapshot["fan"]))))
            else:
                # The fans ran on a custom duty set elsewhere: the safe
                # return is the board's own automatic control.
                operations.append(("fan", ("fan-system", "automatic")))
        for module, arguments in operations:
            result = self._record_action(module, f"restore-{arguments[-1]}", self._run(*arguments, timeout=30))
            if result.get("ok") is False:
                errors.append(str(result.get("error") or "Restore failed."))
        return {"ok": not errors, "restored": True, "name": session.get("name", ""), "error": " ".join(errors)}
