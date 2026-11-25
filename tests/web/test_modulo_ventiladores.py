"""Tablero compartido, curvas, mezcla, herramientas y calibración protegida."""
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from bc250cc.application.fan.calibration import CalibrationResult
from frontends.tui.runtime import Context
from frontends.web.actions import Invalid, all_actions
from frontends.web.modulos import ventiladores
from scripts.qa.web.servicio_ejemplo import ConfiguracionEjemplo, ServicioEjemplo


def ejemplo():
    return Context(service=ServicioEjemplo(), settings=ConfiguracionEjemplo())


def test_tablero_es_el_del_escritorio_sin_qt():
    ctx = ejemplo()
    datos = ventiladores.leer(ctx, None)
    assert len(datos["channels"]) >= 5
    assert datos["profiles"]["builtin"]
    assert datos["default_curve"]
    assert len(datos["speed_profiles"]) == 3
    assert datos["service"]["available"]


@pytest.mark.parametrize("entrada", [
    {"mode": "firmware"}, {"mode": "fixed", "percent": 60},
    {"mode": "curve", "source": "hottest", "points": [[30, 30], [80, 100]]},
    {"mode": "mix", "mix": [{"source": "gpu", "points": [[30, 30], [80, 100]]},
                              {"source": "cpu", "points": [[30, 40], [85, 100]]}]},
])
def test_motor_valida_los_cuatro_modos(entrada):
    resultado = ventiladores.validar(None, {"entry": json.dumps(entrada)})
    assert resultado["valid"], resultado
    assert resultado["entry"]["mode"] == entrada["mode"]


@pytest.mark.parametrize("entrada", [{"mode": "fixed", "percent": 101}, {"mode": "fixed", "role": "pump", "percent": 0},
    {"mode": "curve", "source": "shell", "points": [[30, 30], [80, 100]]},
    {"mode": "curve", "source": "cpu", "points": [[30, 50], [30, 100]]}])
def test_curvas_invalidas_no_son_aplicables(entrada):
    assert not ventiladores.validar(None, {"entry": json.dumps(entrada)})["valid"]


def test_importar_exportar_no_cambia_la_politica_activa():
    ctx = ejemplo()
    web = SimpleNamespace(ctx=ctx)
    config = {"fan_channels": {"2": {"mode": "fixed", "percent": 60}}}
    ctx.settings.save_local_config(config)
    exportado = ventiladores.diagnostico(web, {"view": "export"})["text"]
    documento = json.loads(exportado)
    documento["channels"]["2"]["percent"] = 80
    ventiladores.importar(ctx, {"text": json.dumps(documento), "replace": False})
    despues = ctx.settings.read_local_config()
    assert despues["fan_channels"] == config["fan_channels"]
    assert despues["fan_modes"]
    assert not ctx.service.llamadas
    with pytest.raises(Invalid):
        ventiladores.importar(ctx, {"text": "{}", "replace": False})


@pytest.mark.parametrize("operacion,metodo", [("prepare", "preparar_nct6687_control_pwm"),
    ("readonly", "cargar_nct6683_solo_lectura"), ("disable", "desactivar_nct6687_control_pwm"),
    ("handoff", "ceder_fan_a_otro_programa"), ("decky", "exportar_perfiles_fan_decky")])
def test_herramientas_solo_llaman_servicios(operacion, metodo):
    ctx = ejemplo()
    parametros = {"operation": operacion}
    if operacion == "handoff":
        parametros["enabled"] = True
    nivel, trabajo = ventiladores.herramientas(ctx, parametros, None)
    assert nivel in (1, 2)
    trabajo()
    assert ctx.service.llamadas[-1][0] == metodo
    with pytest.raises(Invalid):
        ventiladores.herramientas(ctx, {**parametros, "command": "anything"}, None)


def test_calibracion_rechaza_bombas_y_control_externo(monkeypatch):
    ctx = ejemplo()
    for opciones in ({"external": True},):
        ctx.service.estado_control_fan_sistema = lambda: opciones
        _, trabajo = ventiladores.calibrar(ctx, {"pwm": 2}, None)
        with pytest.raises(Invalid):
            trabajo()
    ctx.service.estado_control_fan_sistema = lambda: {}
    ctx.settings.save_local_config({"fan_channels": {"2": {"mode": "fixed", "role": "pump", "percent": 60}}})
    _, trabajo = ventiladores.calibrar(ctx, {"pwm": 2}, None)
    with pytest.raises(Invalid):
        trabajo()
    assert not ctx.service.llamadas


def test_calibracion_solo_propone_no_guarda_canal(monkeypatch):
    ctx = ejemplo()
    from bc250cc.application.fan import board_view
    monkeypatch.setattr(board_view, "is_writable", lambda fila: True)
    resultado = CalibrationResult(20, 30, 25, 35, (), "")
    monkeypatch.setattr(ventiladores, "calibrate", lambda **opciones: resultado)
    nivel, trabajo = ventiladores.calibrar(ctx, {"pwm": 2}, None)
    assert nivel == 2
    trabajo()
    config = ctx.settings.read_local_config()
    assert config["web_fan_calibration"]["proposed_min"] == 25
    assert "fan_channels" not in config


def test_registro_conserva_acciones_existentes():
    acciones = all_actions()
    for nombre in ("fan.channel", "fan.label", "fan.profile", "fan.service", "fans.apply", "fans.calibrate", "fans.tools"):
        assert nombre in acciones
    for pwm in (True, 0, 13, "2"):
        with pytest.raises(Invalid):
            ventiladores.calibrar(ejemplo(), {"pwm": pwm}, None)


def test_rutas_tienen_las_tres_pestanas_y_no_inventan_hwmon(monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(Path, "is_file", lambda ruta: False)
    monkeypatch.setattr("bc250cc.platform.init.services.detect_init_manager", lambda: SimpleNamespace(
        available=True, kind="openrc", display_name="OpenRC", detail="example"))
    pestañas = ventiladores.rutas_pwm({"sensores": {"pwms": [{"path": "/reported/pwm2"}]}})
    assert [fila["key"] for fila in pestañas] == ["detected", "persistence", "verification"]
    assert "/reported/pwm2" in pestañas[0]["text"]
    assert "hwmon0" not in pestañas[0]["text"]
    assert "rc-service" in pestañas[1]["text"]
    assert "systemctl" not in pestañas[1]["text"]


def test_aplicar_valida_nombre_canal_y_confirma_baja_velocidad(monkeypatch):
    llamadas = []
    class Tablero:
        def __init__(self, *args):
            pass
        def apply_channel(self, pwm, entrada):
            from bc250cc.application.fan.board_actions import Outcome
            llamadas.append((pwm, entrada))
            return Outcome("Saved", "Saved")
        def rename(self, pwm, nombre):
            llamadas.append((pwm, nombre))
    monkeypatch.setattr(ventiladores, "FanBoardActions", Tablero)
    ctx = ejemplo()
    nivel, trabajo = ventiladores.aplicar(ctx, {"pwm": 2, "entry": {"mode": "fixed", "percent": 20}, "label": "APU"}, None)
    assert nivel == 2
    trabajo()
    assert llamadas[-1] == (2, "APU")
    with pytest.raises(Invalid):
        ventiladores.aplicar(ctx, {"pwm": 2, "entry": {"mode": "fixed", "percent": 120}, "label": "APU"}, None)
