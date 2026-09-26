import threading
from pathlib import Path
from types import SimpleNamespace

from bc250cc.infrastructure.sistema_repository import SistemaRepository


def test_realtime_sampler_builds_one_coherent_passive_snapshot(monkeypatch):
    repo = SistemaRepository.__new__(SistemaRepository)
    repo._metricas_rt_lock = threading.Lock()
    repo._metricas_rt_time = 8.0
    repo._metricas_rt_disk = (
        "nvme0n1",
        SimpleNamespace(read_bytes=100, write_bytes=200, busy_time=10),
    )
    repo._metricas_rt_network = {
        "eth0": SimpleNamespace(bytes_recv=1000, bytes_sent=500),
    }
    disk = SimpleNamespace(read_bytes=300, write_bytes=500, busy_time=30)
    network = SimpleNamespace(bytes_recv=1400, bytes_sent=700)
    monkeypatch.setattr("bc250cc.infrastructure.sistema_repository.time.monotonic", lambda: 10.0)
    monkeypatch.setattr(
        "bc250cc.infrastructure.sistema_repository.psutil.cpu_percent",
        lambda interval=None, percpu=False: [25, 125] if percpu else 50,
    )
    monkeypatch.setattr(
        "bc250cc.infrastructure.sistema_repository.psutil.cpu_freq",
        lambda percpu=False: (
            [SimpleNamespace(current=3400), SimpleNamespace(current=3600)]
            if percpu
            else SimpleNamespace(current=3500)
        ),
    )
    monkeypatch.setattr("bc250cc.infrastructure.sistema_repository.psutil.cpu_count", lambda logical=True: 4 if logical else 2)
    monkeypatch.setattr(
        "bc250cc.infrastructure.sistema_repository.psutil.virtual_memory",
        lambda: SimpleNamespace(percent=75, total=1000, available=250),
    )
    monkeypatch.setattr(
        "bc250cc.infrastructure.sistema_repository.psutil.swap_memory",
        lambda: SimpleNamespace(percent=10, used=100, total=1000),
    )
    monkeypatch.setattr(
        "bc250cc.infrastructure.sistema_repository.psutil.disk_usage",
        lambda _path: SimpleNamespace(percent=60, used=600, total=1000),
    )
    monkeypatch.setattr(
        "bc250cc.infrastructure.sistema_repository.psutil.net_io_counters",
        lambda **_kwargs: {"eth0": network},
    )
    monkeypatch.setattr("bc250cc.infrastructure.sistema_repository.os.getloadavg", lambda: (1.0, 2.0, 3.0))
    repo._contador_disco_raiz = lambda: ("nvme0n1", disk)
    repo._interfaz_red_predeterminada = lambda: "eth0"
    repo._gpu_device_path = lambda: Path("/mock/card0/device")
    repo._gpu_busy_percent = lambda _path: 130
    repo._parse_dpm_actual = lambda _text: 1750
    repo._leer_texto = lambda _path: "1: 1750Mhz *"
    repo._leer_entero = lambda path: 800 if path.name.endswith("used") else 1000
    repo.lectura_potencia = lambda: {
        "value_w": 70,
        "gpu_w": 45,
        "scope": "gpu_soc",
        "label": "GPU SoC",
        "source": "hwmon",
        "is_total": False,
    }
    repo.temperatura_cpu = lambda: 55
    repo.temperatura_chip = lambda _chip, _label: 60
    repo.voltaje_chip = lambda _chip, label: 799 if label == 'vddgfx' else 1206
    repo.temperaturas_auxiliares = lambda: {
        'nvme_temperature_c': 42.5,
        'board_temperature_c': 47.0,
        'vrm_temperature_c': 49.0,
    }

    sample = repo.obtener_metricas_tiempo_real()

    assert sample["sample_interval"] == 2.0
    assert sample["cpu"]["usage_percent"] == 50.0
    assert sample["cpu"]["per_core_percent"] == [25.0, 100.0]
    assert sample["cpu"]["per_core_frequency_mhz"] == [3400.0, 3600.0]
    assert sample["gpu"]["usage_percent"] == 100.0
    assert sample["gpu"]["vram_used"] == 800
    assert sample["memory"]["used"] == 750
    assert sample["disk"]["read_bps"] == 100.0
    assert sample["network"]["download_bps"] == 200.0
    assert sample["power"]["scope"] == "gpu_soc"
    assert sample["sensors"] == {
        'nvme_temperature_c': 42.5,
        'board_temperature_c': 47.0,
        'vrm_temperature_c': 49.0,
    }
    assert repo._metricas_rt_time == 10.0
    assert repo._metricas_rt_disk == ("nvme0n1", disk)
    assert repo._metricas_rt_network == {"eth0": network}


def test_auxiliary_temperature_prefers_nvme_and_ignores_disconnected_inputs(tmp_path, monkeypatch):
    repo = SistemaRepository.__new__(SistemaRepository)
    repo.hwmons = []
    repo._hwmon_root = tmp_path
    repo._aux_temperature_cache = {}
    repo._aux_temperature_cache_time = 0.0
    monkeypatch.setattr(
        "bc250cc.infrastructure.sistema_repository.time.monotonic", lambda: 20.0
    )

    nvme = tmp_path / "hwmon0"
    nvme.mkdir()
    (nvme / "name").write_text("nvme\n", encoding="utf-8")
    (nvme / "temp1_input").write_text("46850\n", encoding="utf-8")
    (nvme / "temp3_input").write_text("68850\n", encoding="utf-8")
    nct = tmp_path / "hwmon1"
    nct.mkdir()
    (nct / "name").write_text("nct6686\n", encoding="utf-8")
    (nct / "temp2_label").write_text("System\n", encoding="utf-8")
    (nct / "temp2_input").write_text("49000\n", encoding="utf-8")
    (nct / "temp7_label").write_text("M2_1\n", encoding="utf-8")
    (nct / "temp7_input").write_text("0\n", encoding="utf-8")

    reading = repo.temperaturas_auxiliares()

    assert reading["nvme_temperature_c"] == 46.85
    assert reading["nvme_hotspot_temperature_c"] == 68.85
    assert reading["board_temperature_c"] == 49.0
    assert reading["vrm_temperature_c"] is None
    # No PMBus daemon and no channel the Nuvoton calls VRM: no source to name.
    assert reading["vrm_source"] == ""


def test_auxiliary_temperatures_keep_labelled_board_and_vrm_independent(tmp_path, monkeypatch):
    repo = SistemaRepository.__new__(SistemaRepository)
    repo.hwmons = []
    repo._hwmon_root = tmp_path
    repo._aux_temperature_cache = {}
    repo._aux_temperature_cache_time = 0.0
    monkeypatch.setattr(
        "bc250cc.infrastructure.sistema_repository.time.monotonic", lambda: 30.0
    )
    nct = tmp_path / "hwmon0"
    nct.mkdir()
    (nct / "name").write_text("nct6686\n", encoding="utf-8")
    (nct / "temp2_label").write_text("System\n", encoding="utf-8")
    (nct / "temp2_input").write_text("48500\n", encoding="utf-8")
    (nct / "temp3_label").write_text("VRM MOS\n", encoding="utf-8")
    (nct / "temp3_input").write_text("51000\n", encoding="utf-8")

    reading = repo.temperaturas_auxiliares()

    assert reading["nvme_temperature_c"] is None
    assert reading["nvme_hotspot_temperature_c"] is None
    assert reading["board_temperature_c"] == 48.5
    assert reading["vrm_temperature_c"] == 51.0
    # It came from the Nuvoton "VRM MOS" channel, not from the PMIC, and the
    # reading says so rather than passing itself off as a rail measurement.
    assert reading["vrm_source"] == "nct"
    assert reading["vrm_cpu_temperature_c"] is None
    assert reading["vrm_gpu_temperature_c"] is None


class _CpuTimes(tuple):
    """psutil's scputimes: a tuple whose fields are also attributes."""

    _fields = ("user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal", "guest", "guest_nice")

    def __new__(cls, user, idle, *, iowait=0.0, guest=0.0):
        values = (user, 0.0, 0.0, idle, iowait, 0.0, 0.0, 0.0, guest, 0.0)
        instance = super().__new__(cls, values)
        for name, value in zip(cls._fields, values):
            setattr(instance, name, value)
        return instance


def test_cpu_usage_is_measured_over_the_samplers_own_interval(monkeypatch):
    """Another page calling psutil.cpu_percent must not bend this graph.

    psutil measures since the last call made by anyone in the process. The
    CPU page and the dashboard call it too, and one of them landing a few
    milliseconds before the monitor left it an interval of almost nothing:
    the line plunged to 0 %.
    """
    repo = SistemaRepository.__new__(SistemaRepository)
    readings = iter(
        [
            [_CpuTimes(100.0, 900.0), _CpuTimes(100.0, 900.0)],
            # One second later: CPU0 half busy, CPU1 fully busy, guest time
            # inside user as on Linux (it must not be counted twice).
            [_CpuTimes(100.5, 900.5), _CpuTimes(101.0, 900.0, guest=0.2)],
        ]
    )
    monkeypatch.setattr(
        "bc250cc.infrastructure.sistema_repository.psutil.cpu_times",
        lambda percpu=False: next(readings),
    )
    monkeypatch.setattr(
        "bc250cc.infrastructure.sistema_repository.psutil.cpu_percent",
        lambda interval=None, percpu=False: [0.0, 0.0] if percpu else 0.0,
    )

    assert repo._uso_cpu_propio() is None  # nothing to compare with yet
    total, threads = repo._uso_cpu_propio()

    assert threads[0] == 50.0
    assert threads[1] == 100.0
    # 1.5 busy seconds out of 2: the guest 0.2 s is not a third CPU second.
    assert total == 75.0
