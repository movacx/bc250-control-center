"""A service and a screen that record what the pages ask of them."""

from __future__ import annotations

from types import SimpleNamespace

from frontends.tui.runtime import Context

METRICS = {
    "cpu": {"usage_percent": 12.0, "per_core_percent": [10.0, 20.0], "per_core_frequency_mhz": [3500.0, 3400.0],
            "frequency_mhz": 3450.0, "temperature_c": 55.0, "logical_cores": 12, "physical_cores": 6,
            "load_average": [0.5, 0.6, 0.7]},
    "gpu": {"usage_percent": 40.0, "frequency_mhz": 1500, "temperature_c": 60.0, "voltage_mv": 900,
            "power_w": 55.0, "vram_used": 2**29, "vram_total": 2**30, "gtt_used": 2**28, "gtt_total": 2**32,
            "memory_frequency_mhz": 1750},
    "power": {"value_w": 55.0},
    "sensors": {"vrm_temperature_c": 70.0, "board_temperature_c": 50.0, "nvme_temperature_c": 40.0},
    "memory": {"usage_percent": 50.0, "swap_used": 1, "swap_total": 4, "swap_percent": 25.0, "zram_active": True,
               "ttm_limit_bytes": 2**33, "supported_ttm_gib_presets": (8, 10, 12)},
    "network": {"download_bps": 10.0, "upload_bps": 5.0},
}
GPU_STATE = {"allowed_min": 500, "allowed_max": 2000, "current_min": 1000, "current_max": 1850,
             "governor_backend": "cyan-skillfish-governor-smu", "service_active": "active",
             "service_enabled": "enabled", "sclk_actual": 1500, "mclk_actual": 1750, "voltaje_actual": 900}
CU_STATE = {"rows": [{"name": f"SE{i // 2}.SH{i % 2}", "mask": 31} for i in range(4)], "source": "live", "raw": "table"}
FANS = {"sensores": {"chip": "nct6686", "fans": [
    {"index": 2, "label": "Pump Fan", "rpm": 1700, "pwm": 127, "pwm_root_writable": True}]}}


class FakeService:
    def __init__(self):
        self.calls: list[tuple] = []

    def __getattr__(self, name):
        if name.startswith(("estado_", "ultima_")):
            return lambda *a, **k: {}

        def call(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return f"{name} ok"
        return call

    def metricas_tiempo_real(self):
        return METRICS

    def estado_bc250(self):
        return dict(GPU_STATE)

    def estado_bc250_daemon(self):
        return {"service_active": "active", "current_min": 1000, "current_max": 1850}

    def estado_fans_bc250(self):
        return FANS

    def estado_control_fan_sistema(self):
        return {"state": "off", "enabled": False}

    def obtener_estado_cu_cache(self):
        return dict(CU_STATE)

    def procesos(self, ocultar_sistema=True):
        return [SimpleNamespace(pid=10, nombre="game", memoria=2**30, protegido=False),
                SimpleNamespace(pid=1, nombre="systemd", memoria=2**20, protegido=True)]

    def blackbox_estado(self, rows=None):
        return {"running": False, "state_text": "stopped", "directory": "/tmp/bb", "autostart": {"supported": True},
                "rows": [{"time": "00:00:01", "clock": "1500Mhz"}]}

    def estado_herramientas_bc250(self):
        return {"governor_pkg": True, "umr": False, "stress": True}

    def driver_inventory(self):
        return {"supported_components": ("connectivity",)}

    def estado_cpu_oc_persistente(self):
        return {"ui_state": "Disabled"}

    def estado_desbloqueo_nucleos_cpu(self):
        return {"physical_cores": 6, "logical_cpus": 12, "unlocked": False}


class FakeUI:
    """Answers dialogs from a script and records notifications."""

    def __init__(self, *, confirm=True, ints=(), choices=()):
        self.confirm_answer = confirm
        self.ints = list(ints)
        self.choices = list(choices)
        self.texts: list[str] = []
        self.notes: list[tuple[str, str]] = []
        self.ran: list[str] = []
        self.confirmations: list[tuple[str, bool]] = []
        self.refreshed = 0
        self.theme = None
        self.unicode = True

    def confirm(self, message, *, danger=False):
        self.confirmations.append((message, danger))
        return self.confirm_answer

    def ask_int(self, label, minimum, maximum, default):
        return self.ints.pop(0) if self.ints else default

    def ask_text(self, label, default=""):
        return default

    def choose(self, title, options):
        return self.choices.pop(0) if self.choices else None

    def notify(self, message, tone=""):
        self.notes.append((message, tone))

    def run(self, label, work):
        self.ran.append(label)
        try:
            return True, work()
        except Exception as error:
            return False, error

    def show_text(self, title, text):
        self.texts.append(text)

    def refresh(self):
        self.refreshed += 1

    def apply_theme(self, theme):
        self.theme = theme


def make_context(service=None) -> Context:
    ctx = Context(service=service or FakeService(), settings=SimpleNamespace(
        read_local_config=lambda: {"idioma": "en", "alertas_activas": True},
        save_local_config=lambda config: None), activity=None)
    ctx.metrics = METRICS
    ctx.state("ui")["touch"] = False  # the desktop layout unless a test asks for the touch one
    for name, value in (("gpu_clock", 1500), ("gpu_temp", 60), ("cpu_load", 12), ("ram", 50)):
        ctx.record(name, value)
    return ctx
