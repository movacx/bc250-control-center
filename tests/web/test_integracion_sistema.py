"""Regresiones de integración del sistema, sin red, procesos ni hardware reales."""

import base64
import json
from dataclasses import dataclass, replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from bc250cc.application.fan.calibration import CalibrationResult
from frontends.tui.content import Panel
from frontends.tui.i18n import current_language, set_language, tr, tr_format
from frontends.tui.runtime import Context
from frontends.web.actions import Invalid
from frontends.web.modulos import (
    acceso_remoto,
    ajustes_adicionales,
    caja_negra,
    configuracion,
    firmware,
    procesos,
    soporte,
    ventiladores,
)
from frontends.web.modulos.ajustes_adicionales_compat import Action, Fila
from scripts.qa.web.servicio_ejemplo import (
    PROCESOS,
    ConfiguracionEjemplo,
    ServicioEjemplo,
)


@pytest.fixture
def contexto():
    return Context(service=ServicioEjemplo(), settings=ConfiguracionEjemplo())


@pytest.fixture
def espanol():
    anterior = current_language()
    set_language("es")
    yield
    set_language(anterior)


def test_caja_negra_traduce_estado_columnas_y_exportacion(contexto, espanol):
    contexto.service.blackbox_estado = Mock(return_value={"state": "recording", "rows": []})
    datos = caja_negra.leer(contexto, None)
    assert datos["message"] == tr(caja_negra.ESTADOS["recording"])
    assert datos["message"] != caja_negra.ESTADOS["recording"]
    assert datos["columns"][0]["label"] == tr(caja_negra.COLUMNS[0][0])
    web = SimpleNamespace(ctx=contexto, live=None)
    descarga = caja_negra.descargar(web, {"file": "recording"})
    assert descarga["text"].split("\t")[0] == datos["columns"][0]["label"]


def test_firmware_no_expone_excepcion_de_lectura(contexto, monkeypatch, espanol):
    monkeypatch.setattr(firmware, "snapshot", Mock(side_effect=RuntimeError("detalle privado")))
    assert firmware.leer(contexto, None) == {"error": tr("Unavailable")}


def test_firmware_traduce_pasos_y_aviso_codec(contexto, monkeypatch, espanol):
    @dataclass
    class PlacaSimulada:
        is_bc250: bool = True

    estado = SimpleNamespace(board=PlacaSimulada(), installed=PlacaSimulada(), drives=[])
    monkeypatch.setattr(firmware, "snapshot", Mock(return_value=estado))
    monkeypatch.setattr(firmware, "almacen", Mock(return_value=None))
    monkeypatch.setattr(firmware, "catalogo", Mock(return_value=[]))
    monkeypatch.setattr(firmware, "servicio", Mock(return_value=True))
    monkeypatch.setattr(firmware.lzma1, "available", Mock(return_value="detalle privado"))
    datos = firmware.leer(contexto, None)
    assert datos["logo_codec"] == tr(firmware.AVISO_CODEC)
    assert datos["steps"][0]["title"] == tr(firmware.PASOS["download"])


def test_logo_rechaza_codec_ausente_antes_de_leer_archivo(monkeypatch, espanol):
    monkeypatch.setattr(firmware.lzma1, "available", Mock(return_value="ruta interna"))
    leer = Mock(side_effect=AssertionError("No debe leer el logo"))
    monkeypatch.setattr(firmware.temporales, "leer", leer)
    familia = SimpleNamespace(logo_replaceable=True)
    with pytest.raises(Invalid) as error:
        firmware.logo({"logo": True}, familia)
    assert str(error.value) == tr(firmware.AVISO_CODEC)
    leer.assert_not_called()
    assert firmware.logo({"logo": False}, familia) is None


def test_logo_malformado_muestra_mensaje_del_catalogo(contexto, espanol):
    with pytest.raises(Invalid) as error:
        firmware.guardar_logo(contexto, {"logo": "!!!!"})
    assert str(error.value) == tr("The file is not a picture this system can read.")


def test_logo_con_cabecera_inconsistente_no_expone_indexerror(contexto, espanol):
    segmento = bytes([8, 1, 122, 2, 160, 255]) + bytes(9)
    datos = b"\xff\xd8\xff\xc0\x00\x11" + segmento + b"\xff\xd9"
    with pytest.raises(Invalid) as error:
        firmware.guardar_logo(contexto, {"logo": base64.b64encode(datos).decode("ascii")})
    assert str(error.value) == tr("The file is not a picture this system can read.")


def test_usb_revalida_unidad_bloqueada_sin_preparar(contexto, monkeypatch, espanol):
    unidad = SimpleNamespace(eligible=False, blocker=Mock(return_value="Choose a USB drive"))
    monkeypatch.setattr(firmware, "snapshot", Mock(return_value=SimpleNamespace(drives=[unidad])))
    monkeypatch.setattr(firmware, "identidad", Mock(return_value="a" * 64))
    plan = Mock(side_effect=AssertionError("No debe preparar una unidad bloqueada"))
    monkeypatch.setattr(firmware, "plan_kit", plan)
    familia = firmware.DEFAULT_FAMILY
    _, trabajo = firmware.preparar(contexto, {
        "family": familia.key, "image": familia.image().key, "drive": "a" * 64, "logo": False,
    }, None)
    with pytest.raises(Invalid) as error:
        trabajo()
    assert str(error.value) == tr("Choose a USB drive")
    plan.assert_not_called()


@pytest.mark.parametrize("inicio", [{}, {"supported": False}, {"supported": True, "foreign": True}])
def test_acceso_remoto_revalida_autoinicio(contexto, monkeypatch, inicio, espanol):
    api = SimpleNamespace(status=Mock(return_value={"autostart": inicio}), set_autostart=Mock())
    monkeypatch.setattr(acceso_remoto, "servicio", Mock(return_value=api))
    _, trabajo = acceso_remoto.configurar(contexto, {"field": "autostart", "value": True}, None)
    with pytest.raises(Invalid) as error:
        trabajo()
    assert str(error.value) == tr("Not available here")
    api.set_autostart.assert_not_called()


def test_acceso_remoto_autoinicio_valido(contexto, monkeypatch):
    api = SimpleNamespace(status=Mock(return_value={"autostart": {"supported": True}}), set_autostart=Mock())
    monkeypatch.setattr(acceso_remoto, "servicio", Mock(return_value=api))
    _, trabajo = acceso_remoto.configurar(contexto, {"field": "autostart", "value": False}, None)
    trabajo()
    api.set_autostart.assert_called_once_with(False)


def test_certificado_rechaza_parametros_antes_del_servicio(contexto):
    with pytest.raises(Invalid):
        acceso_remoto.certificado(SimpleNamespace(ctx=contexto), {"path": "otro"})
    assert not contexto.service.llamadas


def test_certificado_admite_nombre_de_consulta_del_handler(contexto, monkeypatch):
    certificado = SimpleNamespace(read_text=Mock(return_value="certificado publico"))
    api = SimpleNamespace(trust_certificate=Mock(return_value=certificado))
    monkeypatch.setattr(acceso_remoto, "servicio", Mock(return_value=api))
    datos = acceso_remoto.certificado(SimpleNamespace(ctx=contexto), {"name": "remote.certificate"})
    assert datos == {"text": "certificado publico", "filename": "BC250-local-authority.crt"}


@pytest.mark.parametrize("control,permanente,duracion,aprobado", [
    (True, True, None, True), (True, True, 3600, True),
    (False, True, None, False), (True, False, None, False),
])
def test_dispositivo_aprobado_sigue_regla_del_escritorio(control, permanente, duracion, aprobado):
    datos = acceso_remoto.dispositivo({
        "id": "a" * 64, "control": control, "permanent": permanente, "duration_seconds": duracion,
    })
    assert datos["approved"] is aprobado


@pytest.mark.parametrize("error", [ValueError("dato privado"), RuntimeError("ruta privada"), TypeError("tipo interno")])
def test_extras_oculta_excepciones(contexto, monkeypatch, espanol, error):
    monkeypatch.setattr(ajustes_adicionales, "resolver", Mock(side_effect=error))
    respuesta = ajustes_adicionales.consultar(SimpleNamespace(ctx=contexto), {"request": "{}"})
    assert respuesta == {"kind": "error", "error": tr("Unavailable")}


def test_extras_usa_contexto_de_consulta_y_traduce_rechazo(contexto, monkeypatch, espanol):
    resolver = Mock(side_effect=Invalid("Operation no longer available"))
    monkeypatch.setattr(ajustes_adicionales, "resolver", resolver)
    respuesta = ajustes_adicionales.consultar(SimpleNamespace(ctx=contexto), {"request": "{}"})
    resolver.assert_called_once_with(contexto, {})
    assert respuesta == {"kind": "error", "error": tr("Not available here")}


def test_extras_no_habilita_acciones_de_fila_bloqueada():
    fila = Fila(label="Controlador", enabled=False, acciones=[Action(label="Instalar", work=Mock())])
    panel = ajustes_adicionales.describir_panel(Panel("Controladores", [fila]))
    assert panel["rows"][0]["actions"][0]["enabled"] is False


@pytest.mark.parametrize("constructor,parametros", [
    (configuracion.guardar_preferencia, {"key": "scale", "value": 100}),
    (configuracion.intervalo_daemon, {"value": "2"}),
])
def test_ajustes_rechazan_parametros_adicionales(contexto, constructor, parametros):
    with pytest.raises(Invalid):
        constructor(contexto, {**parametros, "command": "otro"})


@pytest.mark.parametrize("constructor,parametros", [
    (configuracion.cambiar_gobernador, {"value": "auto"}),
    (configuracion.servicio_telemetria, {"action": "install"}),
    (configuracion.controlador, {"key": "vrm_sensor", "action": "install"}),
    (configuracion.memoria_al_arrancar, {"enable": True}),
    (configuracion.daemon, {"enable": True}),
])
def test_acciones_de_configuracion_son_cerradas(contexto, constructor, parametros):
    with pytest.raises(Invalid):
        constructor(contexto, {**parametros, "command": "otro"}, None)
    assert not contexto.service.llamadas


@pytest.mark.parametrize("estado", [
    {"state": "external", "managed": True, "supported": True},
    {"state": "not-installed", "supported": False},
])
def test_telemetria_no_instala_en_estado_bloqueado(contexto, monkeypatch, estado):
    monkeypatch.setattr(configuracion, "_telemetria_apu", Mock(return_value=estado))
    _, trabajo = configuracion.servicio_telemetria(contexto, {"action": "install"}, None)
    with pytest.raises(Invalid):
        trabajo()
    assert not contexto.service.llamadas


@pytest.mark.parametrize("accion,estado", [("install", {"supported": True}), ("uninstall", {"managed": True})])
def test_telemetria_conserva_operaciones_disponibles(contexto, monkeypatch, accion, estado):
    monkeypatch.setattr(configuracion, "_telemetria_apu", Mock(return_value=estado))
    _, trabajo = configuracion.servicio_telemetria(contexto, {"action": accion}, None)
    trabajo()
    assert contexto.service.llamadas[-1][0:2] == ("gestionar_apu_telemetry", (accion,))


@pytest.mark.parametrize("estado,accion,permitida", [
    ("managed-elsewhere", "remove", False), ("unsupported", "install", False),
    ("installed", "install", False), ("update-available", "install", True),
    ("installed", "remove", True), ("not-installed", "install", True),
])
def test_controlador_valida_estado_actual(contexto, monkeypatch, estado, accion, permitida):
    monkeypatch.setattr(configuracion, "_controladores", Mock(return_value={"vrm_sensor": {"state": estado}}))
    _, trabajo = configuracion.controlador(contexto, {"key": "vrm_sensor", "action": accion}, None)
    if permitida:
        trabajo()
        assert contexto.service.llamadas[-1][0:2] == ("manage_accessory", ("vrm_sensor", accion))
    else:
        with pytest.raises(Invalid):
            trabajo()
        assert not contexto.service.llamadas


def test_memoria_arranque_no_toca_opcion_externa(contexto):
    contexto.service.estado_herramientas_bc250 = Mock(return_value={"system_setup": {
        "helper_available": True, "kernel_options": {
            "available": True, "arguments": {configuracion.MEMORY_SENSOR_OPTION: {"external": True}},
        },
    }})
    _, trabajo = configuracion.memoria_al_arrancar(contexto, {"enable": False}, None)
    with pytest.raises(Invalid):
        trabajo()
    assert not contexto.service.llamadas


def test_daemon_no_muestra_stderr_crudo(contexto, monkeypatch, espanol):
    monkeypatch.setattr(configuracion, "_systemctl", Mock(return_value=SimpleNamespace(returncode=1, stderr="privado")))
    _, trabajo = configuracion.daemon(contexto, {"enable": True}, None)
    with pytest.raises(RuntimeError) as error:
        trabajo()
    assert str(error.value) == tr("Failed")


def test_daemon_sin_systemd_muestra_aviso_traducido(monkeypatch, espanol):
    monkeypatch.setattr(configuracion, "detect_init_manager", Mock(return_value=SimpleNamespace(kind="openrc")))
    with pytest.raises(RuntimeError) as error:
        configuracion._systemctl("is-active", configuracion.SERVICIO_DAEMON)
    esperado = tr("The optional daemon requires an active systemd user manager; "
                  "live hardware monitoring in the open application remains available.")
    assert str(error.value) == esperado


def test_carpeta_inaccesible_no_expone_error_interno(monkeypatch, espanol):
    monkeypatch.setattr(configuracion.Path, "is_dir", Mock(return_value=True))
    monkeypatch.setattr(configuracion.Path, "iterdir", Mock(side_effect=OSError("ruta privada")))
    assert configuracion._contenido("carpeta de prueba") == tr("Unavailable")


def test_novedades_no_expone_error_de_red(contexto, monkeypatch, espanol):
    monkeypatch.setattr("bc250cc.application.system.updates.fetch_latest_release", Mock(side_effect=RuntimeError("privado")))
    respuesta = configuracion.novedades(SimpleNamespace(ctx=contexto), {})
    assert respuesta["error"] == tr("Unavailable")


def test_importacion_y_aplicacion_fan_rechazan_campos_extra(contexto):
    with pytest.raises(Invalid):
        ventiladores.importar(contexto, {"text": "{}", "replace": False, "command": "otro"})
    with pytest.raises(Invalid):
        ventiladores.aplicar(contexto, {"pwm": 2, "entry": None, "label": "APU", "command": "otro"}, None)
    assert not contexto.service.llamadas


def test_importacion_y_validacion_fan_muestran_mensajes_traducidos(contexto, espanol):
    with pytest.raises(Invalid) as error:
        ventiladores.importar(contexto, {"text": "{", "replace": False})
    assert str(error.value) == tr("Could not import fan profiles")
    resultado = ventiladores.validar(None, {"entry": json.dumps({"mode": "fixed", "percent": 101})})
    assert resultado == {"valid": False, "error": tr("Could not save fan curve")}


def test_calibracion_traduce_y_oculta_error_en_accion_y_lectura(contexto, monkeypatch, espanol):
    monkeypatch.setattr(ventiladores.vista, "is_writable", Mock(return_value=True))
    resultado = CalibrationResult(None, None, 0, 0, (), "calibration failed: ruta privada")
    monkeypatch.setattr(ventiladores, "calibrate", Mock(return_value=resultado))
    _, trabajo = ventiladores.calibrar(contexto, {"pwm": 2}, None)
    with pytest.raises(Invalid) as error:
        trabajo()
    esperado = tr_format("calibration failed: {error}", error=tr("Unavailable"))
    assert str(error.value) == esperado
    assert contexto.settings.read_local_config()["web_fan_calibration"]["aborted"] == esperado


def test_procesos_consulta_cerrada_y_revalida_identidad(contexto, espanol):
    with pytest.raises(Invalid):
        procesos.consultar(SimpleNamespace(ctx=contexto), {"command": "otro"})
    original = PROCESOS[0]
    contexto.service.inventario_procesos = Mock(return_value={"processes": [replace(original, protegido=True)]})
    _, trabajo = procesos.actuar(contexto, {"operation": "end", "targets": [
        {"pid": original.pid, "created": original.create_time},
    ]}, None)
    with pytest.raises(Invalid) as error:
        trabajo()
    assert str(error.value) == tr("No applications selected")
    assert not contexto.service.llamadas


def test_procesos_admite_nombre_de_consulta_del_handler(contexto):
    contexto.service.inventario_procesos = Mock(return_value={"processes": []})
    datos = procesos.consultar(SimpleNamespace(ctx=contexto), {"name": "processes.rows"})
    assert datos["rows"] == []


@pytest.mark.parametrize("parametros", [[], None, {"values": {}, "seen": ["x"] * 100}])
def test_soporte_rechaza_documentos_malformados(parametros):
    with pytest.raises(Invalid):
        soporte._borrador(parametros)
