import json

from bc250cc.domain.fan.persistence import (
    fan_curve_percent_for_temp,
    normalize_fan_curve,
    normalize_fan_preset,
    validate_fan_curve_points,
)
from bc250cc.infrastructure.daemon import BC250ControlCenterDaemon
from bc250cc.infrastructure.fan_repository import FanRepository
from bc250cc.infrastructure.persistence.configuracion_local import ConfiguracionLocal


def test_curve_and_preset_survive_config_reload(tmp_path, monkeypatch):
    config = ConfiguracionLocal()
    monkeypatch.setattr(config, "config_dir", lambda: tmp_path)
    curve = normalize_fan_curve({
        "enabled": True,
        "preset": "cool",
        "pwm": 2,
        "t1": 45,
        "s1": 70,
        "t2": 60,
        "s2": 90,
        "t3": 68,
        "s3": 100,
    })
    preset = normalize_fan_preset({
        "enabled": True,
        "preset": "cooling",
        "percent": 70,
        "pwm": 2,
    })
    config.guardar_config({"fan_curve": curve, "fan_preset": preset})
    reloaded = config.leer_config()
    assert reloaded["fan_curve"]["preset"] == "aggressive"
    assert reloaded["fan_curve"]["enabled"] is True
    assert reloaded["fan_preset"]["preset"] == "cooling"
    assert reloaded["fan_preset"]["percent"] == 70


def test_legacy_cool_curve_identifier_migrates_to_aggressive():
    curve = normalize_fan_curve({"preset": "cool"})

    assert curve["preset"] == "aggressive"


def test_daemon_applies_saved_static_preset(monkeypatch):
    daemon = object.__new__(BC250ControlCenterDaemon)
    daemon.ultimo_fan_curve_apply = 0
    daemon.ultimo_fan_curve_percent = None
    daemon.ultimo_fan_curve_error = 0
    applied = []
    daemon.servicio = type("Service", (), {
        "aplicar_pwm_fan": lambda self, pwm, value: applied.append((pwm, value)),
        "registrar_evento": lambda *args, **kwargs: None,
    })()
    monkeypatch.setattr("bc250cc.infrastructure.daemon.time.monotonic", lambda: 10.0)
    daemon.aplicar_ventilador_persistente_si_corresponde(
        {"gpu_temp": 50},
        {
            "fan_curve": {"enabled": False},
            "fan_preset": {"enabled": True, "preset": "balanced", "percent": 70, "pwm": 2},
        },
    )
    assert applied == [(2, round(70 * 255 / 100))]


def test_steamos_background_daemon_uses_dedicated_noninteractive_helper():
    calls = []

    class Repository(FanRepository):
        estado_herramientas_cache = None

        def _usar_steamos_fan_daemon_helper(self):
            return True

        def _usar_steamos_game_helper(self):
            raise AssertionError("interactive Game Mode detection must not be used by the daemon")

        def _ejecutar_steamos_fan_daemon_helper(self, pwm, value, timeout=120):
            calls.append((pwm, value, timeout))
            return "OK PWM"

    result = Repository().aplicar_pwm_fan(3, 170)

    assert calls == [(3, 170, 120)]
    assert result["pwm"] == 3


def test_restore_automatic_mode_uses_explicit_enable_two_and_readback(tmp_path):
    sensor = tmp_path / "hwmon2"
    sensor.mkdir()
    (sensor / "pwm2").write_text("127\n", encoding="ascii")
    (sensor / "pwm2_enable").write_text("1\n", encoding="ascii")

    class Repository(FanRepository):
        estado_herramientas_cache = None

        def _usar_steamos_game_helper(self):
            return False

        def _sensor_nct_principal(self):
            return sensor

    result = Repository().restaurar_pwm_automatico(2)

    assert result["automatic"] is True
    assert result["verified"]["enable"] == 2
    assert (sensor / "pwm2_enable").read_text(encoding="ascii").strip() == "2"


def test_daemon_prefers_enabled_curve_and_curve_survives_restart(monkeypatch):
    daemon = object.__new__(BC250ControlCenterDaemon)
    daemon.ultimo_fan_curve_apply = 0
    daemon.ultimo_fan_curve_percent = None
    daemon.ultimo_fan_curve_error = 0
    applied = []
    daemon.servicio = type("Service", (), {
        "aplicar_pwm_fan": lambda self, pwm, value: applied.append((pwm, value)),
        "registrar_evento": lambda *args, **kwargs: None,
    })()
    curve = normalize_fan_curve({
        "enabled": True, "pwm": 2,
        "t1": 40, "s1": 45, "t2": 60, "s2": 70, "t3": 80, "s3": 100,
    })
    monkeypatch.setattr("bc250cc.infrastructure.daemon.time.monotonic", lambda: 10.0)
    daemon.aplicar_ventilador_persistente_si_corresponde(
        {"gpu_temp": 60},
        {
            "fan_curve": curve,
            "fan_preset": {"enabled": True, "preset": "maximum", "percent": 100, "pwm": 2},
        },
    )
    expected = fan_curve_percent_for_temp(60, curve)
    assert applied == [(2, round(expected * 255 / 100))]


def test_custom_slider_is_explicitly_non_persistent():
    preset = normalize_fan_preset({
        "enabled": False,
        "preset": "",
        "percent": 83,
        "pwm": 2,
    })
    assert preset["enabled"] is False
    assert preset["percent"] == 0


def test_legacy_three_point_curve_is_migrated_to_variable_point_schema():
    curve = normalize_fan_curve({
        "enabled": True,
        "t1": 45,
        "s1": 50,
        "t2": 60,
        "s2": 75,
        "t3": 75,
        "s3": 100,
    })

    assert curve["point_count"] == 3
    assert curve["points"] == [
        {"temperature": 45, "speed": 50},
        {"temperature": 60, "speed": 75},
        {"temperature": 75, "speed": 100},
    ]
    assert curve["t1"] == 45
    assert curve["s3"] == 100


def test_legacy_curve_is_migrated_and_persisted_during_config_load(tmp_path, monkeypatch):
    config = ConfiguracionLocal()
    monkeypatch.setattr(config, "config_dir", lambda: tmp_path)
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "version": 1,
        "fan_curve": {
            "enabled": True,
            "t1": 45, "s1": 50,
            "t2": 60, "s2": 75,
            "t3": 75, "s3": 100,
        },
    }), encoding="utf-8")

    loaded = config.leer_config()
    persisted = json.loads(path.read_text(encoding="utf-8"))

    assert loaded["version"] == 2
    assert loaded["fan_curve"]["point_count"] == 3
    assert persisted["version"] == 2
    assert persisted["fan_curve"]["points"][1] == {"temperature": 60, "speed": 75}


def test_eight_point_curve_is_sorted_and_used_by_daemon_math():
    points = [
        {"temperature": temperature, "speed": speed}
        for temperature, speed in reversed(
            [(35, 25), (40, 30), (45, 40), (50, 50), (60, 65), (70, 80), (80, 90), (90, 100)]
        )
    ]
    curve = normalize_fan_curve({"enabled": True, "points": points})

    assert curve["point_count"] == 8
    assert [point["temperature"] for point in curve["points"]] == [35, 40, 45, 50, 60, 70, 80, 90]
    assert fan_curve_percent_for_temp(75, curve) == 80


def test_fan_curve_validation_rejects_duplicate_temperatures_and_bad_size():
    valid, message = validate_fan_curve_points([(40, 40), (40, 60), (70, 100)])
    assert valid is False
    assert "strictly increasing" in message

    valid, message = validate_fan_curve_points([(40, 40), (70, 100)])
    assert valid is False
    assert "between 3 and 8" in message


def test_daemon_uses_all_custom_curve_points(monkeypatch):
    daemon = object.__new__(BC250ControlCenterDaemon)
    daemon.ultimo_fan_curve_apply = 0
    daemon.ultimo_fan_curve_percent = None
    daemon.ultimo_fan_curve_error = 0
    applied = []
    daemon.servicio = type("Service", (), {
        "aplicar_pwm_fan": lambda self, pwm, value: applied.append((pwm, value)),
        "registrar_evento": lambda *args, **kwargs: None,
    })()
    curve = normalize_fan_curve({
        "enabled": True,
        "pwm": 2,
        "points": [
            {"temperature": 40, "speed": 35},
            {"temperature": 50, "speed": 50},
            {"temperature": 60, "speed": 65},
            {"temperature": 70, "speed": 80},
            {"temperature": 80, "speed": 100},
        ],
    })
    monkeypatch.setattr("bc250cc.infrastructure.daemon.time.monotonic", lambda: 10.0)

    daemon.aplicar_ventilador_persistente_si_corresponde(
        {"gpu_temp": 72},
        {"fan_curve": curve, "fan_preset": {"enabled": False}},
    )

    assert applied == [(2, round(80 * 255 / 100))]


def _daemon_for_write_tests(applied, readback=None):
    daemon = object.__new__(BC250ControlCenterDaemon)
    daemon.ultimo_fan_curve_apply = 0
    daemon.ultimo_fan_curve_percent = None
    daemon.ultimo_fan_target = None
    daemon.ultimo_fan_verify = 0
    daemon.ultimo_fan_sensor_path = ""
    daemon.ultimo_fan_curve_error = 0
    daemon.fan_temp_missing_since = None
    daemon.ultima_fan_temperature = None
    methods = {
        "aplicar_pwm_fan": lambda self, pwm, value: applied.append((pwm, value)),
        "registrar_evento": lambda *args, **kwargs: None,
    }
    if readback is not None:
        methods["leer_pwm_fan"] = lambda self, pwm: readback(pwm)
    daemon.servicio = type("Service", (), methods)()
    return daemon


def test_daemon_same_percent_on_a_different_channel_is_not_skipped(monkeypatch):
    applied = []
    daemon = _daemon_for_write_tests(applied)
    ticks = iter((10.0, 20.0))
    monkeypatch.setattr("bc250cc.infrastructure.daemon.time.monotonic", lambda: next(ticks))
    first = {"fan_curve": {"enabled": False}, "fan_preset": {"enabled": True, "preset": "balanced", "percent": 70, "pwm": 2}}
    second = {"fan_curve": {"enabled": False}, "fan_preset": {"enabled": True, "preset": "balanced", "percent": 70, "pwm": 3}}

    daemon.aplicar_ventilador_persistente_si_corresponde({"gpu_temp": 50}, first)
    daemon.aplicar_ventilador_persistente_si_corresponde({"gpu_temp": 50}, second)

    assert applied == [(2, round(70 * 255 / 100)), (3, round(70 * 255 / 100))]


def test_daemon_periodic_readback_avoids_an_unnecessary_privileged_write(monkeypatch):
    applied = []
    raw = round(70 * 255 / 100)
    daemon = _daemon_for_write_tests(
        applied,
        lambda pwm: {"pwm": pwm, "value": raw, "sensor_path": "/sys/class/hwmon/hwmon2"},
    )
    daemon.ultimo_fan_target = (2, 70, "preset:balanced")
    daemon.ultimo_fan_curve_percent = 70
    daemon.ultimo_fan_sensor_path = "/sys/class/hwmon/hwmon2"
    monkeypatch.setattr("bc250cc.infrastructure.daemon.time.monotonic", lambda: 40.0)

    daemon.aplicar_ventilador_persistente_si_corresponde(
        {"gpu_temp": 50},
        {"fan_curve": {"enabled": False}, "fan_preset": {"enabled": True, "preset": "balanced", "percent": 70, "pwm": 2}},
    )

    assert applied == []
    assert daemon.ultimo_fan_verify == 40.0


def test_daemon_rewrites_when_readback_drifted(monkeypatch):
    applied = []
    daemon = _daemon_for_write_tests(
        applied,
        lambda pwm: {"pwm": pwm, "value": 1, "sensor_path": "/sys/class/hwmon/hwmon2"},
    )
    daemon.ultimo_fan_target = (2, 70, "preset:balanced")
    daemon.ultimo_fan_curve_percent = 70
    daemon.ultimo_fan_sensor_path = "/sys/class/hwmon/hwmon2"
    monkeypatch.setattr("bc250cc.infrastructure.daemon.time.monotonic", lambda: 40.0)

    daemon.aplicar_ventilador_persistente_si_corresponde(
        {"gpu_temp": 50},
        {"fan_curve": {"enabled": False}, "fan_preset": {"enabled": True, "preset": "balanced", "percent": 70, "pwm": 2}},
    )

    assert applied == [(2, round(70 * 255 / 100))]


def test_daemon_uses_failsafe_after_temperature_sensor_timeout(monkeypatch):
    applied = []
    daemon = _daemon_for_write_tests(applied)
    ticks = iter((10.0, 30.0))
    monkeypatch.setattr("bc250cc.infrastructure.daemon.time.monotonic", lambda: next(ticks))
    config = {
        "fan_curve": normalize_fan_curve({"enabled": True, "pwm": 2}),
        "fan_preset": {"enabled": False},
        "fan_daemon_sensor_timeout_seconds": 15,
        "fan_daemon_failsafe_percent": 100,
    }

    daemon.aplicar_ventilador_persistente_si_corresponde({"gpu_temp": None}, config)
    daemon.aplicar_ventilador_persistente_si_corresponde({"gpu_temp": None}, config)

    assert applied == [(2, 255)]


def test_disabling_pwm_setup_also_removes_the_boot_time_fan_restore(monkeypatch):
    """GitHub issue: fan PWM asked to authenticate on every boot.

    The fix restores the last PWM duty at boot through a root systemd unit
    (no pkexec involved). "Disable PWM setup" must undo that too, or a
    disabled setup would keep silently re-applying an old duty on reboot.
    """
    from bc250cc.platform.init.services import InitManagerState

    captured = []

    class Repository(FanRepository):
        def _abrir_terminal(self, command, _title=""):
            captured.append(command)
            return None

        def _os_repository(self):
            return type("OS", (), {"info": type("Info", (), {"family": "arch"})()})()

    monkeypatch.setattr(
        "bc250cc.infrastructure.fan_repository.detect_init_manager",
        lambda: InitManagerState("systemd", True, "systemd unit management is available."),
    )

    Repository().desactivar_nct6687_control_pwm()

    assert len(captured) == 1
    assert "bc250-fan-pwm-restore.service" in captured[0]
    assert "systemctl disable --now bc250-fan-pwm-restore.service" in captured[0]
    assert "/var/lib/bc250-control-center/fan-last-applied.json" in captured[0]


def test_disabling_pwm_setup_removes_the_openrc_fan_restore_service(monkeypatch):
    from bc250cc.platform.init.services import InitManagerState

    captured = []

    class Repository(FanRepository):
        def _abrir_terminal(self, command, _title=""):
            captured.append(command)
            return None

        def _os_repository(self):
            return type("OS", (), {"info": type("Info", (), {"family": "arch"})()})()

    monkeypatch.setattr(
        "bc250cc.infrastructure.fan_repository.detect_init_manager",
        lambda: InitManagerState("openrc", True, "OpenRC runlevel management is available."),
    )

    Repository().desactivar_nct6687_control_pwm()

    assert len(captured) == 1
    assert "bc250-openrc-service-helper remove bc250-fan-pwm-restore" in captured[0]


def test_fan_repository_writable_pwm_path_needs_no_polkit(tmp_path):
    sensor = tmp_path / "hwmon8"
    sensor.mkdir()
    (sensor / "pwm3").write_text("0\n", encoding="utf-8")
    (sensor / "pwm3_enable").write_text("0\n", encoding="utf-8")

    class Repository(FanRepository):
        estado_herramientas_cache = None

        def _usar_steamos_fan_daemon_helper(self):
            return False

        def _usar_steamos_game_helper(self):
            return False

        def _sensor_nct_principal(self):
            return sensor

        def _command_path(self, command):
            raise AssertionError(f"{command} must not be required for a user-writable PWM channel")

    result = Repository().aplicar_pwm_fan(3, 170)

    assert (sensor / "pwm3").read_text(encoding="utf-8") == "170\n"
    assert (sensor / "pwm3_enable").read_text(encoding="utf-8") == "1\n"
    assert result["verified"]["value"] == 170


def test_daemon_health_file_is_atomic_and_private(tmp_path, monkeypatch):
    daemon = object.__new__(BC250ControlCenterDaemon)
    daemon._health_enabled = True
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))

    assert daemon._write_health(status="healthy", fan_pwm=2) is True
    path = tmp_path / "bc250-control-center" / "daemon-health.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["status"] == "healthy"
    assert payload["fan_pwm"] == 2
    assert path.stat().st_mode & 0o077 == 0
