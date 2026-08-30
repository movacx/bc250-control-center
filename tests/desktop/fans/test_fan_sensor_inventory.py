from pathlib import Path

from bc250cc.infrastructure.fan_repository import FanRepository


class FixtureFanRepository(FanRepository):
    def __init__(self, sensor, modules):
        self.sensor = sensor
        self.modules = modules
        self.module_reads = 0

    def _buscar_sensores(self):
        return None

    def _sensor_nct_principal(self):
        return self.sensor

    def _modulos_nct(self):
        self.module_reads += 1
        return dict(self.modules)


def test_nct_inventory_collects_fan_pwm_and_temperature_once(tmp_path):
    (tmp_path / "name").write_text("nct6686\n", encoding="utf-8")
    (tmp_path / "fan2_input").write_text("1711\n", encoding="utf-8")
    pwm = tmp_path / "pwm2"
    pwm.write_text("163\n", encoding="utf-8")
    pwm.chmod(0o644)
    (tmp_path / "pwm2_enable").write_text("1\n", encoding="utf-8")
    (tmp_path / "temp1_label").write_text("CPU\n", encoding="utf-8")
    (tmp_path / "temp1_input").write_text("52500\n", encoding="utf-8")
    repo = FixtureFanRepository(tmp_path, {"nct6687": True})

    inventory = repo._leer_sensores_nct()

    assert inventory["chip"] == "nct6686"
    assert inventory["path"] == str(tmp_path)
    assert inventory["fans"] == [{
        "index": 2,
        "label": "Pump Fan / J4003 Fan 1",
        "rpm": 1711,
        "pwm": 163,
        "pwm_path": str(pwm),
        "pwm_writable": True,
        "pwm_root_writable": True,
        "pwm_mode": "0o644",
        "pwm_enable": 1,
        "pwm_enable_path": str(tmp_path / "pwm2_enable"),
        "pwm_enable_writable": True,
        "pwm_enable_root_writable": True,
    }]
    assert inventory["pwms"][0]["index"] == 2
    assert inventory["pwms"][0]["value"] == 163
    assert inventory["temps"] == [{"index": 1, "label": "CPU", "temp": 52.5}]
    assert repo.module_reads == 1


def test_nct_inventory_preserves_missing_pwm_and_invalid_sensor_values(tmp_path):
    (tmp_path / "name").write_text("nct6686\n", encoding="utf-8")
    (tmp_path / "fan1_input").write_text("invalid\n", encoding="utf-8")
    (tmp_path / "temp2_label").write_text("VRM MOS\n", encoding="utf-8")
    repo = FixtureFanRepository(tmp_path, {"nct6687": False})

    inventory = repo._leer_sensores_nct()

    assert inventory["fans"][0]["rpm"] is None
    assert inventory["fans"][0]["pwm"] is None
    assert inventory["fans"][0]["pwm_path"] == ""
    assert inventory["fans"][0]["pwm_writable"] is False
    assert inventory["temps"] == [{"index": 2, "label": "VRM MOS", "temp": None}]


def test_nct_inventory_without_sensor_returns_stable_empty_shape():
    repo = FixtureFanRepository(None, {})

    assert repo._leer_sensores_nct() == {
        "chip": "", "path": "", "fans": [], "temps": [], "pwms": [],
    }
    assert repo.module_reads == 0


def test_nct_selector_prefers_writable_pwm_over_earlier_read_only_node(
    tmp_path, monkeypatch
):
    early = tmp_path / "hwmon1"
    ready = tmp_path / "hwmon9"
    early.mkdir()
    ready.mkdir()
    (early / "name").write_text("nct6686\n", encoding="utf-8")
    (early / "fan1_input").write_text("1700\n", encoding="utf-8")
    (early / "pwm1").write_text("120\n", encoding="utf-8")
    (ready / "name").write_text("nct6686\n", encoding="utf-8")
    (ready / "fan2_input").write_text("1800\n", encoding="utf-8")
    (ready / "pwm2").write_text("160\n", encoding="utf-8")
    repo = FanRepository()
    repo._fan_hwmon_root = tmp_path
    repo._root_puede_escribir = lambda path: Path(path).parent == ready
    monkeypatch.setattr(
        "bc250cc.infrastructure.fan_repository.os.access",
        lambda path, _mode: Path(path).parent == ready,
    )

    assert repo._sensor_nct_principal() == ready


def test_nct_selector_prefers_richer_telemetry_then_stable_path(tmp_path, monkeypatch):
    sparse = tmp_path / "hwmon2"
    rich = tmp_path / "hwmon7"
    for sensor in (sparse, rich):
        sensor.mkdir()
        (sensor / "name").write_text("nct6686\n", encoding="utf-8")
    (sparse / "fan1_input").write_text("1000\n", encoding="utf-8")
    for index in (1, 2):
        (rich / f"fan{index}_input").write_text("1200\n", encoding="utf-8")
    (rich / "temp1_input").write_text("50000\n", encoding="utf-8")
    repo = FanRepository()
    repo._fan_hwmon_root = tmp_path
    repo._root_puede_escribir = lambda _path: False
    monkeypatch.setattr("bc250cc.infrastructure.fan_repository.os.access", lambda *_args: False)

    assert repo._sensor_nct_principal() == rich
