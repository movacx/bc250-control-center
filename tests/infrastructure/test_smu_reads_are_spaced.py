"""The readings that share the SMU's channel are not asked for every second."""

import threading

from bc250cc.infrastructure import vrm_telemetry_reader as reader
from bc250cc.infrastructure.sensor_inventory import SensorInventory


def memory_driver(root, value=60000):
    device = root / "hwmon3"
    device.mkdir(parents=True)
    (device / "name").write_text("bc250_memory\n")
    for index in range(1, 11):
        (device / f"temp{index}_input").write_text(f"{value}\n")
    return device


def test_the_sensor_list_reads_the_memory_chips_every_fifteen_seconds(tmp_path):
    device, now = memory_driver(tmp_path), [100.0]
    inventory = SensorInventory(hwmon_root=tmp_path, clock=lambda: now[0])

    def chip():
        return next(item.value for item in inventory.read({}) if item.key == "hwmon/bc250_memory/temp3")

    assert chip() == 60
    (device / "temp3_input").write_text("70000\n")
    now[0] += 10
    assert chip() == 60
    now[0] += 6
    assert chip() == 70


def test_the_dashboard_keeps_its_sample_and_stands_aside_during_a_cpu_run(tmp_path, monkeypatch):
    reader._memory_cache.clear()
    device = memory_driver(tmp_path)
    monkeypatch.setattr(reader, "_smu_run_in_progress", lambda _lock: False)
    assert len(reader._kernel_memory_chips(tmp_path)) == 8
    (device / "temp3_input").write_text("70000\n")
    assert reader._kernel_memory_chips(tmp_path)[0]["temperature_c"] == 60
    reader._memory_cache.clear()
    monkeypatch.setattr(reader, "_smu_run_in_progress", lambda _lock: True)
    assert reader._kernel_memory_chips(tmp_path) == []


def test_a_hung_read_is_not_repeated_at_once(monkeypatch):
    from frontends.tui import runtime

    waits = []
    ctx = runtime.Context(service=type("S", (), {"metricas_tiempo_real": lambda self: {}})())
    poller = runtime.Poller(ctx, {})
    clock = iter([0.0, 5.0, 5.0, 5.0, 5.0, 5.0])
    monkeypatch.setattr(runtime.time, "monotonic", lambda: next(clock, 5.0))

    class Stop(threading.Event):
        def wait(self, timeout=None):
            waits.append(timeout)
            self.set()

    poller._stop = Stop()
    poller._metrics_loop()
    assert waits == [runtime.BACK_OFF]
