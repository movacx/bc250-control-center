from bc250cc.infrastructure.fan_repository import FanRepository


def test_loaded_nct6687_without_writable_pwm_is_not_control_ready():
    repo = FanRepository()
    repo._leer_sensores_nct = lambda: {
        "pwms": [{"writable": False, "root_writable": False}],
        "fans": [{"pwm_writable": False, "pwm_root_writable": False}],
    }
    repo._modulos_nct = lambda: {"nct6683": False, "nct6687": True}
    repo._resumen_fan = lambda *_args: "nct6687 loaded; PWM unavailable"

    state = repo.estado_fans_bc250()

    assert state["modulos"]["nct6687"] is True
    assert state["driver_control"] is False


def test_root_writable_pwm_marks_control_ready():
    repo = FanRepository()
    repo._leer_sensores_nct = lambda: {
        "pwms": [{"writable": False, "root_writable": True}],
        "fans": [],
    }
    repo._modulos_nct = lambda: {"nct6683": False, "nct6687": True}
    repo._resumen_fan = lambda *_args: "PWM ready"

    assert repo.estado_fans_bc250()["driver_control"] is True
