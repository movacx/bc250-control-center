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

    def __init__(self):
        self.llamadas: list[tuple] = []

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

    def metricas_tiempo_real(self):
        return deepcopy(METRICAS)

    def rendimiento(self):
        return deepcopy(METRICAS)

    def estado_bc250(self):
        return deepcopy(GPU)

    def estado_bc250_daemon(self):
        return {"service_active": "active", "current_min": 1000, "current_max": 1850}

    def estado_fans_bc250(self):
        return deepcopy(FANS)

    def estado_control_fan_sistema(self):
        return {"state": "off", "enabled": False, "available": True}

    def obtener_estado_cu(self):
        return deepcopy(CU)

    obtener_estado_cu_cache = obtener_estado_cu

    def estado_desbloqueo_nucleos_cpu(self):
        return deepcopy(DESBLOQUEO)

    def estado_cpu_oc_persistente(self):
        return {"enabled": "enabled", "persistent": "enabled", "frequency": 3650, "scale": -19, "temperature": 90}

    def inventario_procesos(self):
        return {"processes": deepcopy(PROCESOS)}

    def procesos(self, *_a, **_k):
        return deepcopy(PROCESOS)

    procesos_usuario = procesos


class ConfiguracionEjemplo:
    def __init__(self, idioma="es"):
        self.valores = {"idioma": idioma, "language": idioma, "appearance": "dark"}

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
