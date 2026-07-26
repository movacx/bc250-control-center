from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import logging
import re
import subprocess
import threading
import time
import weakref


logger = logging.getLogger(__name__)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _integer(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _system_uptime_seconds() -> int:
    """Read Linux uptime without invoking external commands or authentication."""
    try:
        raw = Path("/proc/uptime").read_text(encoding="utf-8", errors="ignore").split()[0]
        return max(0, int(float(raw)))
    except (OSError, IndexError, TypeError, ValueError):
        return 0


def _format_binary_bytes(value: int) -> str:
    value = max(0, int(value or 0))
    if value <= 0:
        return "Not detected"
    gib = value / (1024 ** 3)
    if gib >= 1:
        return f"{gib:.1f} GB"
    mib = value / (1024 ** 2)
    return f"{mib:.0f} MB"


def _format_uptime(seconds: int) -> str:
    seconds = max(0, int(seconds or 0))
    if seconds <= 0:
        return "Not detected"
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"

def _pump_fan_from_sensors_command() -> tuple[int, str]:
    """Fallback reader for environments where hwmon access is incomplete.

    Some systems expose the pump sensor only through the ``sensors`` command,
    so this helper keeps Dashboard refresh passive and does not use
    sudo or pkexec.
    """
    try:
        result = subprocess.run(["sensors"], text=True, capture_output=True, timeout=3)
        output = (result.stdout or "") + "\n" + (result.stderr or "")
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("Passive pump sensor fallback failed: %s", exc)
        return 0, ""
    if not output:
        return 0, ""
    for line in output.splitlines():
        lowered = line.lower().strip()
        if not lowered.startswith("pump fan"):
            continue
        match = re.search(r"(\d+)\s*RPM", line, re.I)
        if match:
            return _integer(match.group(1), 0), "Pump Fan J4003"
    return 0, ""


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


class ControllerStateCache:
    """Thread-safe, short-lived cache shared by all interface pages."""

    def __init__(self, controller: Any):
        self.controller = controller
        self._lock = threading.RLock()
        self._entries: dict[str, _CacheEntry] = {}
        self._inflight: dict[str, threading.Event] = {}

    def invalidate(self, *keys: str) -> None:
        with self._lock:
            if not keys:
                self._entries.clear()
                return
            for key in keys:
                self._entries.pop(str(key), None)

    def get(self, key: str, loader, ttl: float) -> Any:
        key = str(key)
        while True:
            now = time.monotonic()
            with self._lock:
                entry = self._entries.get(key)
                if entry is not None and entry.expires_at > now:
                    return entry.value
                event = self._inflight.get(key)
                if event is None:
                    event = threading.Event()
                    self._inflight[key] = event
                    owner = True
                else:
                    owner = False
            if owner:
                break
            event.wait(timeout=max(1.0, float(ttl) + 5.0))

        try:
            value = loader()
        except Exception:
            with self._lock:
                self._inflight.pop(key, None)
                event.set()
            raise
        with self._lock:
            self._entries[key] = _CacheEntry(value, time.monotonic() + max(0.05, float(ttl)))
            self._inflight.pop(key, None)
            event.set()
        return value

    def performance(self) -> dict[str, Any]:
        def load() -> dict[str, Any]:
            value = self.controller.rendimiento()
            return value.to_dict() if hasattr(value, "to_dict") else dict(value or {})
        return dict(self.get("performance", load, 1.25) or {})

    def realtime_metrics(self) -> dict[str, Any]:
        """Return one short-lived real-time sample shared by UI consumers.

        Performance graphs and smart alerts can fire close together.  Without a
        shared sample they both enumerate sensors, disks and network counters,
        creating avoidable subprocess/sysfs pressure.  A sub-second TTL keeps the
        display live while coalescing coincident reads.
        """
        return dict(
            self.get(
                "realtime_metrics",
                lambda: dict(self.controller.metricas_tiempo_real() or {}),
                0.75,
            )
            or {}
        )

    def gpu(self) -> dict[str, Any]:
        return dict(self.get("gpu", lambda: dict(self.controller.estado_bc250() or {}), 1.5) or {})

    def tools(self) -> dict[str, Any]:
        return dict(self.get("tools", lambda: dict(self.controller.estado_herramientas_bc250() or {}), 8.0) or {})

    def fans(self) -> dict[str, Any]:
        return dict(self.get("fans", lambda: dict(self.controller.estado_fans_bc250() or {}), 1.75) or {})

    def events(self, limit: int = 100) -> list[dict[str, Any]]:
        key = f"events:{int(limit)}"
        return list(self.get(key, lambda: list(self.controller.obtener_eventos(limit) or []), 2.0) or [])

    def cpu_persistence(self) -> dict[str, Any]:
        return dict(self.get("cpu_persistence", lambda: dict(self.controller.estado_cpu_oc_persistente() or {}), 6.0) or {})

    def cu_cache(self) -> dict[str, Any]:
        return dict(self.get("cu_cache", lambda: dict(self.controller.obtener_estado_cu_cache() or {}), 2.0) or {})

    def config(self) -> dict[str, Any]:
        return dict(self.get("config", lambda: dict(self.controller.leer_config_local() or {}), 10.0) or {})

    def paths(self) -> dict[str, str]:
        value = self.get("paths", lambda: dict(self.controller.config_paths() or {}), 30.0)
        return {str(key): str(item) for key, item in dict(value or {}).items()}

    def pump_fan_fallback(self) -> tuple[int, str]:
        return tuple(self.get("sensors:pump_fan", _pump_fan_from_sensors_command, 10.0))


_CACHE_LOCK = threading.RLock()
_CONTROLLER_CACHES: "weakref.WeakKeyDictionary[Any, ControllerStateCache]" = weakref.WeakKeyDictionary()
_FALLBACK_CACHES: dict[int, ControllerStateCache] = {}


def state_cache_for(controller: Any) -> ControllerStateCache:
    with _CACHE_LOCK:
        try:
            cache = _CONTROLLER_CACHES.get(controller)
            if cache is None:
                cache = ControllerStateCache(controller)
                _CONTROLLER_CACHES[controller] = cache
            return cache
        except TypeError:
            key = id(controller)
            cache = _FALLBACK_CACHES.get(key)
            if cache is None:
                cache = ControllerStateCache(controller)
                _FALLBACK_CACHES[key] = cache
            return cache


@dataclass(frozen=True)
class ActivityItem:
    title: str
    when: str
    level: str = "success"


@dataclass(frozen=True)
class DashboardState:
    cpu_frequency_mhz: int = 0
    cpu_voltage_mv: int = 0
    cpu_temperature_c: float = 0.0
    cpu_utilization_percent: int = -1
    power_w: float = 0.0
    gpu_power_w: float = 0.0
    power_scope: str = "unavailable"
    power_label: str = "Power sensor unavailable"
    power_source: str = ""
    power_is_total: bool = False
    cpu_profile: str = "Not detected"

    governor_running: bool = False
    governor_frequency_mhz: int = 0
    governor_min_mhz: int = 0
    governor_max_mhz: int = 0
    gpu_temperature_c: float = 0.0
    gpu_utilization_percent: int = 0

    active_cus: int = 0
    total_cus: int = 40
    cu_mode: str = "Not verified"
    cu_boot_sync: str = "Not detected"
    umr_ready: bool = False

    pwm_ready: bool = False
    pump_fan_rpm: int = 0
    pump_fan_duty_percent: int = 0
    fan_mode: str = "Not detected"
    fan_controller_label: str = "Not detected"

    dependencies_ready: bool = False
    governor_tool_ready: bool = False
    nct_ready: bool = False
    sensors_ready: bool = False

    performance_available: bool = False
    gpu_state_available: bool = False
    cu_state_available: bool = False
    fan_state_available: bool = False
    tools_state_available: bool = False

    gpu_name: str = "BC250"
    gpu_driver: str = ""
    vram_used_bytes: int = 0
    vram_total_bytes: int = 0
    uptime_seconds: int = 0

    activities: tuple[ActivityItem, ...] = field(default_factory=tuple)

    @property
    def cu_percent(self) -> int:
        if self.total_cus <= 0:
            return 0
        return max(0, min(100, round(self.active_cus * 100 / self.total_cus)))

    @property
    def gpu_summary(self) -> str:
        name = (self.gpu_name or "BC250").strip()
        driver = (self.gpu_driver or "").strip()
        return f"{name} • {driver}" if driver else name

    @property
    def vram_summary(self) -> str:
        total = _format_binary_bytes(self.vram_total_bytes)
        if self.vram_used_bytes > 0 and self.vram_total_bytes > 0:
            return f"{_format_binary_bytes(self.vram_used_bytes)} / {total}"
        return total

    @property
    def uptime_summary(self) -> str:
        return _format_uptime(self.uptime_seconds)

    @property
    def power_tooltip(self) -> str:
        if self.power_is_total:
            return "Dedicated total-board power sensor detected."
        if self.power_scope == "gpu_soc":
            return "AMDGPU hwmon reports SoC package power; total board power is not exposed."
        return "No live power sensor is exposed by the current kernel drivers."

    @classmethod
    def from_controller(cls, controller: Any, cache: ControllerStateCache | None = None) -> "DashboardState":
        """Build a passive, read-only snapshot from existing R64 APIs.

        This adapter intentionally avoids ``obtener_dashboard_cu()`` because
        that privileged method may start pkexec to read UMR registers. Automatic
        Dashboard refreshes must never ask for the administrator password.
        CU information therefore comes only from the last authorized cache.
        Missing backend data remains explicitly unavailable; this adapter never
        fabricates telemetry or assumes a healthy hardware state.
        """
        cache = cache or state_cache_for(controller)
        perf: dict[str, Any] = {}
        gpu: dict[str, Any] = {}
        tools: dict[str, Any] = {}
        fan: dict[str, Any] = {}
        events: list[dict[str, Any]] = []
        cu_state: dict[str, Any] = {}

        readers = (
            ("performance", cache.performance, perf),
            ("gpu", cache.gpu, gpu),
            ("tools", cache.tools, tools),
            ("fans", cache.fans, fan),
            ("cu_cache", cache.cu_cache, cu_state),
        )
        for name, reader, target in readers:
            try:
                target.update(reader())
            except (OSError, RuntimeError, TypeError, ValueError, AttributeError) as exc:
                logger.warning("Dashboard source '%s' could not be read: %s", name, exc)
                continue
        try:
            events = cache.events(8)
        except (OSError, RuntimeError, TypeError, ValueError, AttributeError) as exc:
            logger.warning("Dashboard event history could not be read: %s", exc)
            events = []

        performance_available = bool(perf)
        gpu_state_available = bool(gpu)
        tools_state_available = bool(tools)
        fan_state_available = bool(fan)
        cu_state_available = bool(cu_state)

        service_active = str(gpu.get("service_active") or "").lower()
        governor_running = service_active in {"active", "running"}
        current_min = _integer(gpu.get("current_min"), 0)
        current_max = _integer(gpu.get("current_max"), 0)
        current_freq = _integer(gpu.get("sclk_actual"), 0)

        active_cus = _integer(cu_state.get("active_cus"), 0)
        mode_key = str(cu_state.get("mode_key") or "").lower()
        cu_mode = {"full": "full dispatch", "custom": "custom", "factory": "factory"}.get(
            mode_key,
            mode_key.replace("_", " ") if mode_key else "Not verified",
        )
        boot_key = str(cu_state.get("boot_sync_key") or "").lower()
        boot_sync = {"saved": "saved", "pending": "pending", "not_saved": "not saved"}.get(
            boot_key,
            boot_key.replace("_", " ") if boot_key else "Not detected",
        )

        fan_rpm = _integer(perf.get("fan_rpm"), 0)
        fan_duty = 0
        fan_mode = "Not detected"
        fan_label = "Not detected"
        pwm_ready = False
        if fan:
            pwm_ready = bool(
                fan.get("control_disponible")
                or fan.get("pwm_writable")
                or fan.get("driver_control")
                or fan.get("nct6687_loaded")
            )
            fan_mode = str(fan.get("modo") or fan.get("mode") or ("manual" if pwm_ready else "read only"))
            fan_rpm = _integer(fan.get("fan2_rpm") or fan.get("pump_fan_rpm") or fan_rpm, fan_rpm)
            raw_pwm = _integer(fan.get("pwm2") or fan.get("pump_fan_pwm"), 0)
            fan_duty = round(raw_pwm * 100 / 255) if raw_pwm > 0 else 0

            sensors = fan.get("sensores") if isinstance(fan.get("sensores"), dict) else {}
            fan_rows = sensors.get("fans") if isinstance(sensors, dict) else []
            if isinstance(fan_rows, list):
                for row in fan_rows:
                    if not isinstance(row, dict):
                        continue
                    label = str(row.get("label") or row.get("canal") or row.get("name") or "")
                    lowered = label.lower()
                    if "pump" in lowered or "j4003" in lowered or "fan2" in lowered:
                        fan_label = label.replace(" / ", " · ") or fan_label
                        fan_rpm = _integer(row.get("rpm") or row.get("input") or fan_rpm, fan_rpm)
                        raw_pwm = _integer(row.get("pwm") or raw_pwm, raw_pwm)
                        if raw_pwm > 0:
                            fan_duty = round(raw_pwm * 100 / 255)
                        break

        if fan_rpm <= 0:
            fallback_rpm, fallback_label = cache.pump_fan_fallback()
            if fallback_rpm > 0:
                fan_rpm = fallback_rpm
                fan_state_available = True
            if fallback_label:
                fan_label = fallback_label
        if fan_state_available and fan_mode.lower() in {"unavailable", "unknown", "not detected", ""}:
            fan_mode = "manual" if pwm_ready else "read only"

        activity_items: list[ActivityItem] = []
        for item in events[:5]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("titulo") or item.get("title") or item.get("detalle") or "System event")
            timestamp = str(item.get("fecha") or item.get("timestamp") or item.get("hora") or "")
            when = timestamp[-8:] if timestamp else "recent"
            level = str(item.get("nivel") or item.get("level") or "success")
            activity_items.append(ActivityItem(title[:78], when, level))
        cpu_freq = _integer(perf.get("cpu_freq"), 0)
        cpu_voltage = _integer(perf.get("cpu_voltage"), 0)
        if cpu_voltage and cpu_voltage < 10:
            cpu_voltage = round(cpu_voltage * 1000)
        raw_cpu_utilization = perf.get("cpu")
        cpu_utilization = (
            max(0, min(100, int(round(_number(raw_cpu_utilization, 0.0)))))
            if raw_cpu_utilization is not None
            else -1
        )

        gpu_driver = str(gpu.get("driver") or "")
        gpu_name = str(gpu.get("device") or gpu.get("device_name") or "BC250")

        return cls(
            cpu_frequency_mhz=cpu_freq,
            cpu_voltage_mv=cpu_voltage,
            cpu_temperature_c=_number(perf.get("cpu_temp"), 0.0),
            cpu_utilization_percent=cpu_utilization,
            power_w=_number(perf.get("power_w"), 0.0),
            gpu_power_w=_number(perf.get("gpu_power"), 0.0),
            power_scope=str(perf.get("power_scope") or "unavailable"),
            power_label=str(perf.get("power_label") or "Power sensor unavailable"),
            power_source=str(perf.get("power_source") or ""),
            power_is_total=bool(perf.get("power_is_total")),
            cpu_profile="current" if performance_available else "Not detected",
            governor_running=governor_running,
            governor_frequency_mhz=current_freq,
            governor_min_mhz=current_min,
            governor_max_mhz=current_max,
            gpu_temperature_c=_number(perf.get("gpu_temp"), 0.0),
            gpu_utilization_percent=_integer(gpu.get("gpu_busy") or perf.get("gpu_busy"), 0),
            active_cus=active_cus,
            total_cus=40,
            cu_mode=cu_mode,
            cu_boot_sync=boot_sync,
            umr_ready=bool(tools.get("umr")),
            pwm_ready=pwm_ready,
            pump_fan_rpm=fan_rpm,
            pump_fan_duty_percent=max(0, min(100, fan_duty)),
            fan_mode=fan_mode,
            fan_controller_label=fan_label,
            dependencies_ready=all(
                [
                    bool(tools.get("governor_cmd")),
                    bool(tools.get("umr")),
                    bool(tools.get("bc250_detect") or tools.get("smu_oc_exists")),
                ]
            ),
            governor_tool_ready=bool(tools.get("governor_cmd")),
            nct_ready=bool(fan),
            sensors_ready=bool(perf),
            performance_available=performance_available,
            gpu_state_available=gpu_state_available,
            cu_state_available=cu_state_available,
            fan_state_available=fan_state_available,
            tools_state_available=tools_state_available,
            gpu_name=gpu_name,
            gpu_driver=gpu_driver,
            vram_used_bytes=_integer(gpu.get("vram_usado"), 0),
            vram_total_bytes=_integer(gpu.get("vram_total"), 0),
            uptime_seconds=_system_uptime_seconds(),
            activities=tuple(activity_items),
        )
