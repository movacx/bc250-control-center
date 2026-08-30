from bc250cc.application.system.daemon_policy import (
    build_runtime_metric,
    governor_warning_needed,
    plan_daemon_cycle,
    safe_bool,
    safe_number,
)
from bc250cc.infrastructure.daemon import BC250ControlCenterDaemon


def test_cycle_plan_clamps_intervals_and_marks_only_due_lanes():
    plan = plan_daemon_cycle(
        {
            "daemon_governor_interval_seconds": 1,
            "daemon_metrics_interval_seconds": 999,
            "daemon_memory_interval_seconds": "invalid",
            "alertas_activas": "yes",
            "gpu_temp_warning": 999,
            "cpu_temp_warning": 20,
        },
        now=100,
        last_governor=98,
        last_metrics=0,
        last_memory=80,
        last_health=95,
    )
    assert plan.governor_due is True
    assert plan.metrics_due is False
    assert plan.memory_due is False
    assert plan.health_due is False
    assert plan.alerts_enabled is False
    assert (plan.gpu_temp_warning, plan.cpu_temp_warning) == (120.0, 30.0)


def test_cycle_policy_normalization_preserves_legacy_daemon_contract():
    assert safe_number(float("nan"), 5, 1, 10) == 5.0
    assert safe_number("7", 2, 1, 10, integer=True) == 7
    assert safe_bool("disabled", True) is False
    assert safe_bool("unexpected", True) is True


def test_runtime_metric_exposes_only_bounded_gpu_slow_lane_fields():
    metric = build_runtime_metric(
        {"cpu": 10, "gpu_temp": 55, "extra": "ignored"},
        {
            "service_active": "active",
            "dbus_ok": True,
            "current_min": 1000,
            "current_max": 1850,
            "sclk_actual": 1500,
            "tools": {"must": "not leak"},
        },
    )
    assert metric["gpu_temp"] == 55
    assert metric["bc250"] == {
        "service_active": "active",
        "dbus_ok": True,
        "current_min": 1000,
        "current_max": 1850,
        "sclk_actual": 1500,
    }


def test_governor_warning_policy_ignores_disabled_and_unknown_states():
    assert governor_warning_needed(True, {"service_active": "failed"}) is True
    assert governor_warning_needed(False, {"service_active": "failed"}) is False
    assert governor_warning_needed(True, {"service_active": "active"}) is False
    assert governor_warning_needed(True, {}) is False


def test_real_daemon_cycle_uses_dedicated_snapshot_and_pure_metric(monkeypatch):
    calls = []
    service = type(
        "Service",
        (),
        {
            "rendimiento": lambda self: {"cpu": 12, "gpu_temp": 50},
            "leer_config_local": lambda self: {
                "daemon_governor_interval_seconds": 10,
                "daemon_metrics_interval_seconds": 5,
                "daemon_memory_interval_seconds": 30,
                "alertas_activas": False,
            },
            "estado_bc250_daemon": lambda self: calls.append("bounded-gpu") or {
                "service_active": "active", "dbus_ok": True,
                "current_min": 1000, "current_max": 1850, "sclk_actual": 1500,
            },
            "estado_bc250": lambda self: (_ for _ in ()).throw(
                AssertionError("full UI state must not enter the daemon cycle")
            ),
            "registrar_metrica_runtime": lambda self, metric: calls.append(("metric", metric)),
            "proteccion_memoria": lambda self, **kwargs: calls.append(("memory", kwargs)) or {
                "estado": {"nivel": "normal"}
            },
        },
    )()
    daemon = object.__new__(BC250ControlCenterDaemon)
    daemon.servicio = service
    daemon.settings_service = type(
        "Settings",
        (), {
            "read_local_config": lambda self: service.leer_config_local(),
            "record_runtime_metric": lambda self, metric: service.registrar_metrica_runtime(metric),
        },
    )()
    daemon.activity_service = type(
        "Activity", (), {"record": lambda *args, **kwargs: calls.append("event")}
    )()
    daemon.estado_bc250_cache = {}
    daemon.ultimo_governor_read = 0
    daemon.ultimo_metrics_write = 0
    daemon.ultimo_memory_check = 0
    daemon._last_health_write = 100
    daemon.aplicar_ventilador_persistente_si_corresponde = lambda metric, config: calls.append("fan")
    daemon._write_health = lambda **updates: calls.append(("health", updates))
    monkeypatch.setattr("bc250cc.infrastructure.daemon.time.monotonic", lambda: 100.0)

    daemon.ciclo()

    assert calls[0] == "bounded-gpu"
    assert calls[1][0] == "metric"
    assert calls[1][1]["bc250"]["current_max"] == 1850
    assert calls[2] == "fan"
    assert calls[3] == ("memory", {"aplicar": True})
    assert not any(isinstance(call, tuple) and call[0] == "health" for call in calls)
