"""Datos de ejemplo, siempre iguales, para dibujar el escritorio y la web y compararlos.

Nunca toca el equipo: ninguna operación llega al sistema.
"""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(RAIZ / "src"), str(RAIZ)]

from bc250cc.infrastructure.process_inventory import ProcessRecord  # noqa: E402
from tests.tui.fakes import FANS, GPU_STATE, METRICS  # noqa: E402

METRICAS = deepcopy(METRICS)
METRICAS["cpu"].update(
    frequency_mhz=1503.0, temperature_c=52.0, usage_percent=16.0,
    per_core_percent=[18.0, 5.0, 27.0, 14.0, 20.0, 14.0],
    per_core_frequency_mhz=[3640.0, 1210.0, 1370.0, 1040.0, 2240.0, 1270.0],
)
NUCLEOS = [
    {"index": i, "frequency_mhz": f, "usage_percent": u}
    for i, (f, u) in enumerate(zip(METRICAS["cpu"]["per_core_frequency_mhz"], METRICAS["cpu"]["per_core_percent"]))
]
DESBLOQUEO = {
    "physical_cores": 6, "logical_cpus": 12, "unlocked": False, "supported": True, "cores": NUCLEOS,
    "processor": {
        "model_name": "AMD BC-250", "topology": "6 cores / 12 threads", "microcode": "0x8407007",
        "features": "AVX2 · AES · SHA_NI · SVM", "architecture": "x86_64",
        "platform_process": "Zen 2 · TSMC N7FF", "cache": "L1D 6×32K · L1I 6×32K · L2 6×512K · L3 2×4M",
        "total_usage_percent": 16.0,
    },
}
GPU = {
    **GPU_STATE,
    "config_path": "/etc/cyan-skillfish-governor-smu/config.toml",
    "dbus_connected": True,
    "cyan_telemetry": {"set_method": "smu", "method": "busy-flag", "temp_read": "drm",
                       "fix_metrics": True, "fix_frequency": False, "temp_read_supported": True},
    "safe_points": [{"frequency": f, "voltage": v} for f, v in (
        (500, 700), (1000, 800), (1175, 850), (1500, 900), (1700, 950), (1850, 975), (2000, 1000))],
    "high_frequency_points": {"available": True, "frequencies": [2050, 2400], "enabled_frequencies": []},
}
CU = {
    "available": True, "driver_topology_available": True, "masks": [31] * 4, "active_cus": 40,
    "service_installed": True, "service_enabled": True, "boot_sync": "Synchronized", "asic": "cyan_skillfish", "privileged_backend_ready": True, "source": "live", "raw": "tabla de ejemplo",
    "rows": [{"name": f"SE{i // 2}.SH{i % 2}", "mask": 31, "driver_mask": 31, "spi": "0x1f", "cc": "0xfffe",
              "tokens": ["D+", "D+", "D+", "S+", "S+"]} for i in range(4)],
}
PROCESOS = [
    ProcessRecord(pid=1000 + i, nombre=n, comando=n, memoria=int(m * 2**20), rss=int(m * 2**20), pss=int(m * 2**20),
                  cpu_percent=c, gpu_percent=g, vram=int(m * 2**18), threads=8, app_key=n, app_name=n.capitalize(), create_time=1.0)
    for i, (n, c, g, m) in enumerate((("firefox", 12.5, 3.0, 900), ("steam", 4.2, 0.5, 520), ("plasmashell", 1.5, 1.0, 310),
                                      ("kwin_wayland", 0.9, 4.0, 190), ("dolphin", 0.2, 0.0, 120)))
]


class ServicioEjemplo:
    """Responde a todo lo que leen las páginas; una operación solo queda anotada."""

    repo = None

    def __init__(self, *, gpu=None, cu=None, metricas=None):
        self.datos_gpu = gpu
        self.datos_cu = cu
        self.datos_metricas = metricas
        self.llamadas: list[tuple] = []
        self.grabando = False
        self.inicio_caja = False

    def __getattr__(self, nombre):
        if nombre.startswith("__"):
            raise AttributeError(nombre)
        lectura = nombre.startswith(("estado_", "obtener_", "leer_", "evaluar_", "ultima_", "blackbox_", "diagnostico"))
        if lectura:
            return lambda *a, **k: {}
        if nombre.startswith(("listar_", "procesos")):
            return lambda *a, **k: []

        def operacion(*args, **kwargs):
            self.llamadas.append((nombre, args, kwargs))
            return f"{nombre}: ejemplo"
        return operacion

    def tv_control_status(self):
        return {"adapter": "/dev/cec0", "daemon": True, "tv": "on", "receiver": "standby", "address": "1.0.0.0"}

    def tv_control_automation(self):
        return {"wake": "installed", "poweroff": "absent"}

    def tv_control_action(self, boton):
        self.llamadas.append(("tv_control_action", (boton,), {}))
        return {"ok": True, "code": "sent", "detail": ""}

    def metricas_tiempo_real(self):
        return deepcopy(self.datos_metricas if self.datos_metricas is not None else METRICAS)

    def rendimiento(self):
        return deepcopy(self.datos_metricas if self.datos_metricas is not None else METRICAS)

    def estado_bc250(self):
        return deepcopy(self.datos_gpu if self.datos_gpu is not None else GPU)

    def estado_bc250_daemon(self):
        return {"service_active": "active", "current_min": 1000, "current_max": 1850}

    def estado_herramientas_bc250(self):
        from frontends.web.modulos.panel import CLAVES
        return {"os_family": "bazzite", "os_label": "Bazzite", "bios_version": "P3.00",
                "prepare_components": {key: {"available": True, "installed": key in ("runtime", "governor"),
                                             "selected": True} for key in CLAVES},
                "quick_access": {"supported": True, "decky_detected": True, "decky_frontend_compatible": True,
                                 "decky_plugin_root_safe": True, "ready": False}}

    def estado_gddr6_memory_temp(self):
        return {"hardware_supported": True, "repository_ready": False, "helper_ready": False}

    def estado_fans_bc250(self):
        return deepcopy(FANS)

    def estado_control_fan_sistema(self):
        return {"state": "off", "enabled": False, "available": True}

    def obtener_estado_cu(self):
        return deepcopy(self.datos_cu if self.datos_cu is not None else CU)

    obtener_estado_cu_cache = obtener_estado_cu

    def estado_desbloqueo_nucleos_cpu(self):
        return deepcopy(DESBLOQUEO)

    def estado_cpu_oc_persistente(self):
        return {"enabled": "enabled", "persistent": "enabled", "frequency": 3650, "scale": -19, "temperature": 90}

    def driver_inventory(self):
        return {"supported_components": ["network", "printing"], "network": [], "bluetooth_controllers": [], "printing": {}}

    def inventario_procesos(self):
        return {"processes": deepcopy(PROCESOS)}

    def procesos(self, *_a, **_k):
        return deepcopy(PROCESOS)

    procesos_usuario = procesos

    def blackbox_estado(self, filas=None):
        registros = [{"time": f"12:30:{59 - i:02d}.000", "clock": "1850MHz", "busy": "65", "t_gpu": "61.0",
                      "t_cpu": "52.0", "volts": "975", "watts": "82.5", "rpm": "fan2=1700",
                      "cpu": "3640", "mem": "8240"} for i in range(80)]
        return {"supported": True, "running": self.grabando, "state": "recording" if self.grabando else "stopped",
                "rows": registros if filas is None else registros[:filas],
                "autostart": {"supported": True, "enabled": self.inicio_caja, "foreign": False}}

    def blackbox_iniciar(self):
        self.llamadas.append(("blackbox_iniciar", (), {}))
        self.grabando = True

    def blackbox_detener(self):
        self.llamadas.append(("blackbox_detener", (), {}))
        self.grabando = False

    def blackbox_con_la_sesion(self, activar):
        self.llamadas.append(("blackbox_con_la_sesion", (activar,), {}))
        self.inicio_caja = activar

    def diagnostico_completo(self):
        return [("GPU", "AMD BC-250 · 1850 MHz"), ("System", "Linux · example"),
                ("Journal", "Example log"), ("Black box", "80 samples")]


class ConfiguracionEjemplo:
    def __init__(self, idioma="es"):
        self.valores = {"idioma": idioma, "language": idioma, "appearance": "dark",
                        "web_prefs": {"welcome_done": True}}

    def read_local_config(self):
        return dict(self.valores)

    def save_local_config(self, valores):
        self.valores.update(valores)
        return self.read_local_config()

    def config_paths(self):
        return {}


class ActividadEjemplo:
    def list(self, *_a, **_k):
        return []

    def __getattr__(self, nombre):
        return lambda *a, **k: None


class InventarioSensoresEjemplo:
    """Nunca examina /sys: devuelve canales estables y uno sin uso para probar el filtro."""

    def read(self, _sample):
        from bc250cc.application.system.sensors import (
            CLOCK,
            DATA,
            GROUP_CPU,
            GROUP_GDDR6,
            GROUP_GPU,
            GROUP_MEMORY,
            TEMPERATURE,
            USAGE,
            SensorReading,
        )
        lecturas = [
            SensorReading("cpu/usage", GROUP_CPU, "CPU", "CPU usage", USAGE, "%", 16.0),
            SensorReading("hwmon/k10temp/temp1", GROUP_CPU, "CPU", "Core temperature", TEMPERATURE, "°C", 52.0),
            SensorReading("gpu/usage", GROUP_GPU, "GPU", "GPU load", USAGE, "%", 42.0),
            SensorReading("gpu/mclk", GROUP_GPU, "GPU", "MCLK", CLOCK, "MHz", 875.0),
            SensorReading("gpu/unused", GROUP_GPU, "GPU", "Unused", USAGE, "%", 0.0),
            SensorReading("memory/used", GROUP_MEMORY, "RAM", "Used", DATA, "B", 4 * 2**30),
        ]
        for indice in range(6):
            lecturas.append(SensorReading(f"cpu/core{indice}/usage", GROUP_CPU, "CPU", f"Core {indice}", USAGE, "%", 10.0 + indice))
            lecturas.append(SensorReading(f"cpu/core{indice}/clock", GROUP_CPU, "CPU", f"Core {indice}", CLOCK, "MHz", 1500.0 + indice * 100))
            for hilo in range(2):
                lecturas.append(SensorReading(f"cpu/core{indice}/t{hilo}/usage", GROUP_CPU, "CPU", f"C{indice}·T{hilo}", USAGE, "%", 10.0 + hilo))
        for indice in range(8):
            lecturas.append(SensorReading(f"gddr6/chip{indice}", GROUP_GDDR6, "GDDR6", f"Chip {indice}", TEMPERATURE, "°C", 60.0 + indice, fields=(("chip", indice),)))
        return lecturas
