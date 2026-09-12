from __future__ import annotations

import logging
import math
import re
import subprocess
import threading
import time
import weakref
from dataclasses import dataclass, field, replace
from typing import Any

from bc250cc.domain.telemetry import voltage_mv
from bc250cc.infrastructure.telemetry_policy import (
    passive_probe_budget,
    run_passive_probe,
)
from frontends.desktop.core.dashboard_presenter import (
    present_activities,
    present_cu_labels,
    present_dashboard_fan,
)

logger = logging.getLogger(__name__)


def collect_named_sources(loaders):
    """Read independent UI data sources without turning one failure global.

    ``loaders`` is an iterable of ``(name, callable)`` pairs.  Every successful
    value is returned in ``payload``; failures are returned separately in
    ``errors``.  This small Qt-free helper keeps passive pages useful when an
    optional subsystem such as systemd, a community tool, or a sensor backend
    is temporarily unavailable.
    """
    payload = {}
    errors = {}
    for name, loader in loaders:
        key = str(name)
        try:
            payload[key] = loader()
        except Exception as error:
            payload[key] = {}
            errors[key] = str(error) or error.__class__.__name__
    return payload, errors


def _dashboard_sources(cache: "ControllerStateCache") -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    list[dict[str, Any]],
]:
    payload, errors = collect_named_sources(
        (
            ("performance", cache.performance),
            ("gpu", cache.gpu),
            ("tools", cache.tools),
            ("fans", cache.fans),
            ("cu_cache", cache.cu_cache),
            ("cpu_tuning", cache.cpu_boot_tuning),
            ("events", lambda: cache.events(8)),
        )
    )
    for name, error in errors.items():
        logger.warning("Dashboard source '%s' could not be read: %s", name, error)

    def mapping(name: str) -> dict[str, Any]:
        value = payload.get(name)
        return dict(value) if isinstance(value, dict) else {}

    raw_events = payload.get("events")
    events = [dict(item) for item in raw_events if isinstance(item, dict)] if isinstance(raw_events, (list, tuple)) else []
    return (
        mapping("performance"),
        mapping("gpu"),
        mapping("tools"),
        mapping("fans"),
        mapping("cu_cache"),
        mapping("cpu_tuning"),
        events,
    )


def _number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError, OverflowError):
        return default


def _integer(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return default


def _voltage_millivolts(value: Any) -> int:
    return voltage_mv(value) or 0


def _format_binary_bytes(value: int) -> str:
    value = max(0, int(value or 0))
    if value <= 0:
        return "Not detected"
    gib = value / (1024 ** 3)
    if gib >= 1:
        return f"{gib:.1f} GB"
    mib = value / (1024 ** 2)
    return f"{mib:.0f} MB"


def _pump_fan_from_sensors_command() -> tuple[int, str]:
    """Fallback reader for environments where hwmon access is incomplete.

    Some systems expose the pump sensor only through the ``sensors`` command,
    so this helper keeps Dashboard refresh passive and does not use
    sudo or pkexec.
    """
    try:
        result = run_passive_probe(["sensors"], timeout=3)
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
        match = re.search(r"(\d+)\s*RPM", line, re.IGNORECASE)
        if match:
            return _integer(match.group(1), 0), "Pump Fan J4003"
    return 0, ""


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


class ControllerStateCache:
    """Thread-safe, short-lived cache shared by all interface pages."""

    def __init__(self, controller: Any, *, activity_service: Any | None = None, settings_service: Any | None = None):
        self.controller = controller
        self.activity_service = activity_service
        self.settings_service = settings_service
        self._lock = threading.RLock()
        self._entries: dict[str, _CacheEntry] = {}
        self._inflight: dict[str, threading.Event] = {}
        self._generations: dict[str, int] = {}

    def invalidate(self, *keys: str) -> None:
        with self._lock:
            if not keys:
                invalidated = set(self._entries) | set(self._inflight) | set(self._generations)
                self._entries.clear()
                for key in invalidated:
                    self._generations[key] = self._generations.get(key, 0) + 1
                for event in self._inflight.values():
                    event.set()
                self._inflight.clear()
                return
            for key in keys:
                key = str(key)
                self._entries.pop(key, None)
                self._generations[key] = self._generations.get(key, 0) + 1
                event = self._inflight.pop(key, None)
                if event is not None:
                    event.set()

    def get(
        self,
        key: str,
        loader,
        ttl: float,
        *,
        coalesce_timeout: float = 2.0,
    ) -> Any:
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
                    generation = self._generations.get(key, 0)
                    owner = True
                else:
                    owner = False
            if owner:
                break
            if event.wait(timeout=max(0.01, float(coalesce_timeout))):
                continue
            with self._lock:
                stale = self._entries.get(key)
                if stale is not None:
                    return stale.value
            raise TimeoutError(f"State source '{key}' is still loading")

        try:
            value = loader()
        except Exception:
            with self._lock:
                if self._inflight.get(key) is event:
                    self._inflight.pop(key, None)
                    event.set()
            raise
        with self._lock:
            if self._generations.get(key, 0) == generation:
                self._entries[key] = _CacheEntry(
                    value,
                    time.monotonic() + max(0.05, float(ttl)),
                )
            if self._inflight.get(key) is event:
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
        if self.activity_service is None:
            raise RuntimeError("ControllerStateCache requires an activity service for event reads")
        return list(self.get(key, lambda: list(self.activity_service.list(limit) or []), 2.0) or [])

    def cpu_persistence(self) -> dict[str, Any]:
        return dict(self.get("cpu_persistence", lambda: dict(self.controller.estado_cpu_oc_persistente() or {}), 6.0) or {})

    def cpu_boot_tuning(self) -> dict[str, Any]:
        """Return only a profile verified as applied by boot persistence.

        A temporary Desktop or Quick Access test is intentionally excluded:
        the Dashboard label describes the registered startup OC, not every
        transient CPU setting used during the current session.
        """

        def load() -> dict[str, Any]:
            persistent = self.cpu_persistence()
            config = persistent.get("config")
            config = dict(config) if isinstance(config, dict) else {}
            if not (persistent.get("applied_this_boot") and config.get("valid")):
                return {}
            return {
                "source": "boot",
                "frequency": config.get("frequency"),
                "scale": config.get("scale"),
            }

        return dict(self.get("cpu_boot_tuning", load, 2.0) or {})

    def core_unlock(self) -> dict[str, Any]:
        """Return the unlock eligibility snapshot without repeatedly probing services.

        The probe checks the CPU shape, the reviewed checkout and both GPU
        governor services.  It is heavier than normal telemetry and a
        transient systemd/OpenRC response must not make the UI flicker from
        ready to unavailable between refresh ticks.
        """
        return dict(
            self.get(
                "core_unlock",
                lambda: dict(self.controller.estado_desbloqueo_nucleos_cpu() or {}),
                4.0,
            )
            or {}
        )

    def cu_cache(self) -> dict[str, Any]:
        return dict(self.get("cu_cache", lambda: dict(self.controller.obtener_estado_cu_cache() or {}), 2.0) or {})

    def config(self) -> dict[str, Any]:
        if self.settings_service is None:
            raise RuntimeError("ControllerStateCache requires a settings service for configuration reads")
        return dict(self.get("config", lambda: dict(self.settings_service.read_local_config() or {}), 10.0) or {})

    def paths(self) -> dict[str, str]:
        if self.settings_service is None:
            raise RuntimeError("ControllerStateCache requires a settings service for path reads")
        value = self.get("paths", lambda: dict(self.settings_service.config_paths() or {}), 30.0)
        return {str(key): str(item) for key, item in dict(value or {}).items()}

    def pump_fan_fallback(self) -> tuple[int, str]:
        return tuple(self.get("sensors:pump_fan", _pump_fan_from_sensors_command, 10.0))


_CACHE_LOCK = threading.RLock()
_CONTROLLER_CACHES: weakref.WeakKeyDictionary[Any, ControllerStateCache] = weakref.WeakKeyDictionary()
_FALLBACK_CACHES: dict[int, ControllerStateCache] = {}


def state_cache_for(controller: Any, *, activity_service: Any | None = None, settings_service: Any | None = None) -> ControllerStateCache:
    with _CACHE_LOCK:
        try:
            cache = _CONTROLLER_CACHES.get(controller)
            if cache is None:
                cache = ControllerStateCache(controller, activity_service=activity_service, settings_service=settings_service)
                _CONTROLLER_CACHES[controller] = cache
            return cache
        except TypeError:
            key = id(controller)
            cache = _FALLBACK_CACHES.get(key)
            if cache is None:
                cache = ControllerStateCache(controller, activity_service=activity_service, settings_service=settings_service)
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
    cpu_physical_cores: int = 0
    cpu_logical_cores: int = 0
    cpu_oc_active: bool = False
    cpu_oc_frequency_mhz: int = 0
    cpu_oc_scale: int | None = None
    cpu_oc_source: str = ""
    cpu_per_core_percent: tuple[float, ...] = field(default_factory=tuple)
    cpu_per_core_frequency_mhz: tuple[float, ...] = field(default_factory=tuple)

    governor_running: bool = False
    governor_frequency_mhz: int = 0
    governor_min_mhz: int = 0
    governor_max_mhz: int = 0
    gpu_temperature_c: float = 0.0
    gpu_utilization_percent: int = 0
    gpu_voltage_mv: int = 0
    gpu_memory_frequency_mhz: int = 0
    gpu_gtt_used_bytes: int = 0
    gpu_gtt_total_bytes: int = 0
    gpu_dpm_force_level: str = ""
    gpu_dpm_state: str = ""
    gpu_telemetry_invalid: bool = False
    gpu_metrics_layout_mismatch: bool = False
    gpu_telemetry_repair_pending: bool = False
    gpu_telemetry_repair_available: bool = True

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
    cpu_tools_ready: bool = False
    core_unlock_ready: bool = False
    cu_manager_ready: bool = False
    nct_ready: bool = False
    sensors_ready: bool = False
    governor_backend: str = ""
    preparation_tools: dict[str, Any] = field(default_factory=dict)

    performance_available: bool = False
    gpu_state_available: bool = False
    cu_state_available: bool = False
    fan_state_available: bool = False
    tools_state_available: bool = False

    gpu_name: str = "BC250"
    gpu_driver: str = ""
    vram_used_bytes: int = 0
    vram_total_bytes: int = 0
    nvme_temperature_c: float = 0.0
    nvme_hotspot_temperature_c: float = 0.0
    board_temperature_c: float = 0.0
    vrm_temperature_c: float = 0.0

    activities: tuple[ActivityItem, ...] = field(default_factory=tuple)

    def with_live_metrics(self, metrics: dict[str, Any]) -> DashboardState:
        """Update sensors only, without replacing control/governor evidence.

        An absent clock stays unavailable, never substituted with the requested
        frequency. Zero utilization is a valid sample, not a missing value.
        """
        cpu = metrics.get("cpu") or {}
        gpu = metrics.get("gpu") or {}
        power = metrics.get("power") or {}
        sensors = metrics.get("sensors") or {}
        # Real-time providers can return a partial sample (for example, a
        # sensor-only refresh after the CPU probe has already completed).
        # Preserve the last fresh value for omitted groups; an entirely empty
        # sample still clears live telemetry as before.
        if metrics:
            cpu = {
                "frequency_mhz": self.cpu_frequency_mhz,
                "temperature_c": self.cpu_temperature_c,
                "usage_percent": self.cpu_utilization_percent,
                "physical_cores": self.cpu_physical_cores,
                "logical_cores": self.cpu_logical_cores,
                "per_core_percent": self.cpu_per_core_percent,
                "per_core_frequency_mhz": self.cpu_per_core_frequency_mhz,
                **cpu,
            }
            gpu = {
                "frequency_mhz": self.governor_frequency_mhz,
                "temperature_c": self.gpu_temperature_c,
                "usage_percent": self.gpu_utilization_percent,
                "voltage_mv": self.gpu_voltage_mv,
                "memory_frequency_mhz": self.gpu_memory_frequency_mhz,
                "gtt_used": self.gpu_gtt_used_bytes,
                "gtt_total": self.gpu_gtt_total_bytes,
                "dpm_force_level": self.gpu_dpm_force_level,
                "dpm_state": self.gpu_dpm_state,
                "vram_used": self.vram_used_bytes,
                "vram_total": self.vram_total_bytes,
                **gpu,
            }
            power = {
                "value_w": self.power_w,
                "gpu_w": self.gpu_power_w,
                "scope": self.power_scope,
                "label": self.power_label,
                "source": self.power_source,
                "is_total": self.power_is_total,
                **power,
            }
            sensors = {
                "nvme_temperature_c": self.nvme_temperature_c,
                "nvme_hotspot_temperature_c": self.nvme_hotspot_temperature_c,
                "board_temperature_c": self.board_temperature_c,
                "vrm_temperature_c": self.vrm_temperature_c,
                **sensors,
            }
        return replace(
            self,
            cpu_frequency_mhz=max(0, _integer(cpu.get("frequency_mhz"))),
            cpu_temperature_c=_number(cpu.get("temperature_c")),
            cpu_utilization_percent=max(-1, min(100, _integer(cpu.get("usage_percent"), -1))),
            cpu_physical_cores=max(0, _integer(cpu.get("physical_cores"))),
            cpu_logical_cores=max(0, _integer(cpu.get("logical_cores"))),
            cpu_per_core_percent=tuple(
                max(0.0, min(100.0, float(value)))
                for value in (cpu.get("per_core_percent") or ())
                if isinstance(value, (int, float))
            ),
            cpu_per_core_frequency_mhz=tuple(
                max(0.0, float(value))
                for value in (cpu.get("per_core_frequency_mhz") or ())
                if isinstance(value, (int, float))
            ),
            governor_frequency_mhz=max(0, _integer(gpu.get("frequency_mhz"))),
            gpu_temperature_c=_number(gpu.get("temperature_c")),
            gpu_utilization_percent=max(-1, min(100, _integer(gpu.get("usage_percent"), -1))),
            gpu_voltage_mv=_voltage_millivolts(gpu.get("voltage_mv")),
            gpu_memory_frequency_mhz=max(
                0, _integer(gpu.get("memory_frequency_mhz"))
            ),
            gpu_gtt_used_bytes=max(0, _integer(gpu.get("gtt_used"))),
            gpu_gtt_total_bytes=max(0, _integer(gpu.get("gtt_total"))),
            gpu_dpm_force_level=str(gpu.get("dpm_force_level") or ""),
            gpu_dpm_state=str(gpu.get("dpm_state") or ""),
            vram_used_bytes=max(0, _integer(gpu.get("vram_used"))),
            vram_total_bytes=max(0, _integer(gpu.get("vram_total"))),
            power_w=_number(power.get("value_w")),
            gpu_power_w=_number(power.get("gpu_w")),
            power_scope=str(power.get("scope") or "unavailable"),
            power_label=str(power.get("label") or "Power sensor unavailable"),
            power_source=str(power.get("source") or ""),
            power_is_total=bool(power.get("is_total")),
            nvme_temperature_c=_number(sensors.get("nvme_temperature_c")),
            nvme_hotspot_temperature_c=_number(
                sensors.get("nvme_hotspot_temperature_c")
            ),
            board_temperature_c=_number(sensors.get("board_temperature_c")),
            vrm_temperature_c=_number(sensors.get("vrm_temperature_c")),
            performance_available=bool(cpu or gpu or power),
        )

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
    def gtt_summary(self) -> str:
        total = _format_binary_bytes(self.gpu_gtt_total_bytes)
        if self.gpu_gtt_used_bytes > 0 and self.gpu_gtt_total_bytes > 0:
            return f"{_format_binary_bytes(self.gpu_gtt_used_bytes)} / {total}"
        return total

    @property
    def dpm_summary(self) -> str:
        force = self.gpu_dpm_force_level.strip()
        state = self.gpu_dpm_state.strip()
        return force or state or "Not detected"

    @property
    def power_tooltip(self) -> str:
        if self.power_is_total:
            return "Dedicated total-board power sensor detected."
        if self.power_scope == "gpu_soc":
            return "AMDGPU hwmon reports SoC package power; total board power is not exposed."
        return "No live power sensor is exposed by the current kernel drivers."

    @classmethod
    def from_controller(cls, controller: Any, cache: ControllerStateCache | None = None) -> DashboardState:
        """Build a passive, read-only snapshot from existing R64 APIs.

        This adapter intentionally avoids ``obtener_dashboard_cu()`` because
        that privileged method may start pkexec to read UMR registers. Automatic
        Dashboard refreshes must never ask for the administrator password.
        CU information therefore comes only from the last authorized cache.
        Missing backend data remains explicitly unavailable; this adapter never
        fabricates telemetry or assumes a healthy hardware state.
        """
        cache = cache or state_cache_for(controller)
        with passive_probe_budget(1):
            return cls._from_controller_with_budget(controller, cache)

    @classmethod
    def _from_controller_with_budget(
        cls, controller: Any, cache: ControllerStateCache
    ) -> DashboardState:
        """Internal implementation executed inside the passive probe budget."""
        perf, gpu, tools, fan, cu_state, cpu_tuning, events = _dashboard_sources(cache)

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
        cu_mode, boot_sync = present_cu_labels(cu_state)
        fan_view = present_dashboard_fan(fan, performance_rpm=perf.get("fan_rpm"))
        if fan_view.needs_fallback:
            fallback_rpm, fallback_label = cache.pump_fan_fallback()
            fan_view = fan_view.with_fallback(fallback_rpm, fallback_label)
        fan_state_available = fan_view.available
        activity_items = tuple(ActivityItem(*item) for item in present_activities(events))
        cpu_freq = _integer(perf.get("cpu_freq"), 0)
        cpu_voltage = _voltage_millivolts(perf.get("cpu_voltage"))
        gpu_voltage = _voltage_millivolts(perf.get("gpu_voltage"))
        raw_cpu_utilization = perf.get("cpu")
        cpu_utilization = (
            max(0, min(100, int(round(_number(raw_cpu_utilization, 0.0)))))
            if raw_cpu_utilization is not None
            else -1
        )
        cpu_oc_frequency = _integer(cpu_tuning.get("frequency"), 0)
        cpu_oc_scale = _integer(cpu_tuning.get("scale"), 999)
        cpu_oc_source = str(cpu_tuning.get("source") or "")
        cpu_oc_active = bool(
            cpu_oc_source
            and cpu_oc_frequency > 0
            and -50 <= cpu_oc_scale <= 0
        )

        gpu_driver = str(gpu.get("driver") or "")
        gpu_name = str(gpu.get("device") or gpu.get("device_name") or "BC250")
        apu_telemetry = gpu.get("apu_telemetry")
        apu_telemetry = apu_telemetry if isinstance(apu_telemetry, dict) else {}
        system_setup_tools = tools.get("system_setup")
        system_setup_tools = system_setup_tools if isinstance(system_setup_tools, dict) else {}
        telemetry_repair = system_setup_tools.get("telemetry")
        telemetry_repair = telemetry_repair if isinstance(telemetry_repair, dict) else {}

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
            cpu_oc_active=cpu_oc_active,
            cpu_oc_frequency_mhz=cpu_oc_frequency if cpu_oc_active else 0,
            cpu_oc_scale=cpu_oc_scale if cpu_oc_active else None,
            cpu_oc_source=cpu_oc_source if cpu_oc_active else "",
            governor_running=governor_running,
            governor_frequency_mhz=current_freq,
            governor_min_mhz=current_min,
            governor_max_mhz=current_max,
            gpu_temperature_c=_number(perf.get("gpu_temp"), 0.0),
            gpu_utilization_percent=_integer(
                gpu.get("gpu_busy") if gpu.get("gpu_busy") is not None else perf.get("gpu_busy"), -1
            ),
            gpu_voltage_mv=gpu_voltage,
            gpu_memory_frequency_mhz=max(
                0,
                _integer(
                    perf.get("memory_frequency_mhz"),
                    _integer(gpu.get("mclk_actual"), 0),
                ),
            ),
            gpu_gtt_used_bytes=max(0, _integer(perf.get("gtt_used"), 0)),
            gpu_gtt_total_bytes=max(0, _integer(perf.get("gtt_total"), 0)),
            gpu_dpm_force_level=str(
                perf.get("dpm_force_level") or gpu.get("power_level") or ""
            ),
            gpu_dpm_state=str(
                perf.get("dpm_state") or gpu.get("power_state") or ""
            ),
            gpu_telemetry_invalid=apu_telemetry.get("status") == "invalid",
            gpu_metrics_layout_mismatch=bool(
                apu_telemetry.get("layout_mismatch_suspected")
            ),
            gpu_telemetry_repair_pending=bool(
                telemetry_repair.get("reboot_required")
                and not telemetry_repair.get("active")
            ),
            gpu_telemetry_repair_available=bool(
                telemetry_repair.get("available", True)
            ),
            active_cus=active_cus,
            total_cus=40,
            cu_mode=cu_mode,
            cu_boot_sync=boot_sync,
            umr_ready=bool(tools.get("umr")),
            pwm_ready=fan_view.pwm_ready,
            pump_fan_rpm=fan_view.rpm,
            pump_fan_duty_percent=fan_view.duty_percent,
            fan_mode=fan_view.mode,
            fan_controller_label=fan_view.label,
            dependencies_ready=all(
                [
                    bool(tools.get("governor_cmd")),
                    bool(tools.get("umr")),
                    bool(tools.get("bc250_detect") or tools.get("smu_oc_exists")),
                ]
            ),
            governor_tool_ready=bool(tools.get("governor_cmd")),
            cpu_tools_ready=bool(
                tools.get("bc250_detect") or tools.get("smu_oc_exists")
            ),
            core_unlock_ready=bool(tools.get("core_unlock_script")),
            cu_manager_ready=bool(tools.get("cu_manager_exists")),
            nct_ready=bool(fan),
            sensors_ready=bool(perf),
            # The preparation target defaults to Cyan even on a clean system.
            # Dashboard status must use installation evidence instead of that
            # desired target, otherwise an uninstalled governor looks present.
            governor_backend=str(tools.get("governor_detected_backend") or ""),
            preparation_tools=dict(tools),
            performance_available=performance_available,
            gpu_state_available=gpu_state_available,
            cu_state_available=cu_state_available,
            fan_state_available=fan_state_available,
            tools_state_available=tools_state_available,
            gpu_name=gpu_name,
            gpu_driver=gpu_driver,
            vram_used_bytes=_integer(gpu.get("vram_usado"), 0),
            vram_total_bytes=_integer(gpu.get("vram_total"), 0),
            activities=activity_items,
        )
