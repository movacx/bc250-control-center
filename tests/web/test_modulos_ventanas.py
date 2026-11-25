"""Configuración, soporte, archivos temporales, acceso remoto, firmware y ajustes adicionales."""

import base64
import os
import stat
from types import SimpleNamespace

import pytest

from bc250cc.domain.firmware.catalog import FAMILIES_BY_KEY
from frontends.tui.runtime import Context
from frontends.web.actions import Invalid
from frontends.web.modulos import (
    acceso_remoto,
    ajustes_adicionales,
    configuracion,
    firmware,
    soporte,
    temporales,
)
from scripts.qa.web.servicio_ejemplo import ConfiguracionEjemplo, ServicioEjemplo
from tests.web.test_web_server import Client, web  # noqa: F401 - el servidor de las demás pruebas


@pytest.fixture
def ctx():
    return Context(service=ServicioEjemplo(), settings=ConfiguracionEjemplo())


@pytest.fixture(autouse=True)
def carpeta_de_estado(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    return tmp_path


# -- configuración ------------------------------------------------------------------------------------

@pytest.mark.parametrize("p", [
    {"key": "no_existe", "value": True},
    {"key": "scale", "value": 1000},
    {"key": "scale", "value": True},
    {"key": "theme", "value": "../../etc/passwd"},
    {"key": "embedded_terminal", "value": 1},
    {"key": "density", "value": {"a": 1}},
    {"key": "density"},
])
def test_preferencia_fuera_de_lista(ctx, p):
    antes = configuracion.preferencias(ctx.settings.read_local_config())
    with pytest.raises(Invalid):
        configuracion.guardar_preferencia(ctx, p)
    assert configuracion.preferencias(ctx.settings.read_local_config()) == antes


def test_preferencia_se_guarda_y_se_reinicia(ctx):
    configuracion.guardar_preferencia(ctx, {"key": "density", "value": "compact"})
    assert configuracion.preferencias(ctx.settings.read_local_config())["density"] == "compact"
    configuracion.reiniciar_preferencias(ctx, {})
    assert configuracion.preferencias(ctx.settings.read_local_config())["density"] == "comfortable"


def test_configuracion_dañada_vuelve_al_valor_inicial():
    valores = configuracion.preferencias({"web_prefs": {"scale": "grande", "theme": 7, "style": None}})
    assert valores["scale"] == 100 and valores["theme"] == "dark" and valores["style"] == "formal"


@pytest.mark.parametrize("valor", [1, "3", "", None, "10; reboot"])
def test_intervalo_del_daemon(ctx, valor):
    with pytest.raises(Invalid):
        configuracion.intervalo_daemon(ctx, {"value": valor})


# -- temporales ---------------------------------------------------------------------------------------

def test_lo_temporal_solo_lo_lee_su_dueño(carpeta_de_estado):
    temporales.guardar("logo", b"uno")
    temporales.guardar("logo", b"dos")
    assert temporales.leer("logo") == b"dos"
    ruta = carpeta_de_estado / "bc250-control-center" / "web" / "logo.jpg"
    assert stat.S_IMODE(ruta.stat().st_mode) == 0o600


def test_lo_temporal_no_sigue_enlaces(carpeta_de_estado):
    ajeno = carpeta_de_estado / "ajeno"
    ajeno.write_text("secreto")
    temporales.guardar("logo", b"uno")
    ruta = carpeta_de_estado / "bc250-control-center" / "web" / "logo.jpg"
    ruta.unlink()
    os.symlink(ajeno, ruta)
    with pytest.raises(OSError):
        temporales.leer("logo")
    temporales.guardar("logo", b"dos")
    assert ajeno.read_text() == "secreto"


# -- soporte ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("cambio", [
    {"path": "/etc/shadow"},
    {"kind": "otro"},
    {"values": "texto"},
    {"values": {"desconocido": "x"}},
    {"values": {"summary": 1}},
    {"seen": ["inventado"]},
    {"attach": "sí"},
])
def test_reporte_mal_formado_no_se_guarda(ctx, cambio):
    p = {"kind": "problem", "values": {}, "seen": [], "other_tools": [], "attach": False, **cambio}
    with pytest.raises(Invalid):
        soporte.guardar_borrador(ctx, p)
    with pytest.raises(OSError):
        temporales.leer("report")


def test_reporte_enorme_se_rechaza(ctx):
    for clave, largo in soporte.LARGOS.items():
        with pytest.raises(Invalid):
            soporte._borrador({"kind": "problem", "values": {clave: "x" * (largo + 1)}, "attach": False})


def test_enviar_sin_borrador_no_envia(ctx, monkeypatch):
    def prohibido(*_args):
        raise AssertionError("no se envía")
    monkeypatch.setattr(soporte.formulario, "submit", prohibido)
    with pytest.raises(Invalid):
        soporte.enviar_reporte(ctx, {}, None)


# -- firmware -----------------------------------------------------------------------------------------

def test_catalogo_y_familia_por_defecto(ctx):
    datos = firmware.leer(ctx, None)
    assert datos.get("error") is None
    claves = [familia["key"] for familia in datos["families"]]
    assert datos["default_family"] in claves
    assert {familia["origin"] for familia in datos["families"]} == {"modded", "stock"}


@pytest.mark.parametrize("p", [
    {"logo": "no es base64"}, {"logo": 5}, {"logo": "A" * 10_000_000},
    {"logo": base64.b64encode(b"\x89PNG....").decode()}, {"logo": "", "name": "x"},
])
def test_logo_invalido(ctx, p):
    with pytest.raises(Invalid):
        firmware.guardar_logo(ctx, p)


@pytest.mark.parametrize("unidad", ["/dev/sda", "", "a" * 63, "Z" * 64, None])
def test_solo_se_prepara_una_unidad_identificada(ctx, unidad):
    clave, familia = next(iter(FAMILIES_BY_KEY.items()))
    with pytest.raises(Invalid):
        firmware.preparar(ctx, {"family": clave, "image": familia.image().key, "drive": unidad, "logo": False}, None)


# -- ajustes adicionales --------------------------------------------------------------------------------

def test_preguntar_nunca_ejecuta():
    ejecutadas = []

    class Servicio:
        def manage_accessory(self, *_args):
            ejecutadas.append("manage")

        def estado_algo(self):
            return "leído"

    seguro = ajustes_adicionales.SoloLectura(Servicio())
    assert seguro.estado_algo() == "leído"
    with pytest.raises(ajustes_adicionales.Pendiente):
        seguro.manage_accessory("vrm_sensor", "install")
    assert ejecutadas == []


@pytest.mark.parametrize("p", [
    {"tab": "otra", "row": "a" * 24, "operation": "a" * 24},
    {"tab": "memory", "row": "corta", "operation": "a" * 24},
    {"tab": "memory", "row": "a" * 24, "operation": "a" * 24, "command": "reboot"},
    {"tab": "memory", "row": "a" * 24, "operation": "a" * 24, "answers": ["x"] * 9},
    {"tab": "memory", "row": "a" * 24, "operation": "a" * 24, "answers": "x"},
])
def test_operacion_mal_formada(ctx, p):
    with pytest.raises(Invalid):
        ajustes_adicionales.actuar(ctx, p, None)


# -- acceso remoto --------------------------------------------------------------------------------------

@pytest.mark.parametrize("p", [
    {"field": "port", "value": 80}, {"field": "port", "value": True}, {"field": "port", "value": "8399"},
    {"field": "lan", "value": "si"}, {"field": "pin", "value": "1234"}, {"field": "lan", "value": True, "tls": False},
])
def test_acceso_remoto_mal_formado(ctx, p):
    with pytest.raises(Invalid):
        acceso_remoto.configurar(ctx, p, None)


def test_el_certificado_es_el_publico(monkeypatch, tmp_path):
    ruta = tmp_path / "authority.crt"
    ruta.write_text("-----BEGIN CERTIFICATE-----\n")
    monkeypatch.setattr(acceso_remoto, "servicio", lambda _ctx: SimpleNamespace(trust_certificate=lambda: ruta))
    datos = acceso_remoto.certificado(SimpleNamespace(ctx=None), {})
    assert datos == {"text": ruta.read_text(), "filename": "BC250-local-authority.crt"}


def test_quien_solo_mira_no_lee_la_clave(web):  # noqa: F811
    from bc250cc.infrastructure import web_devices

    cliente = Client(web)
    assert cliente.login()[0].status == 200
    ficha = cliente.cookie.split("=", 1)[1].split(";")[0]
    web_devices.set_control(web_devices.identity(ficha), False)
    for ruta in ("/api/page?name=remote", "/api/query?name=remote.qr&address=x"):
        respuesta, datos = cliente.call("GET", ruta)
        assert respuesta.status == 403
        assert "pin" not in datos
