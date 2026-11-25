"""Grabación completa, diagnóstico en sus grupos y exportación sin rutas libres."""
import time
from types import SimpleNamespace

import pytest

from frontends.tui.runtime import Context
from frontends.web.actions import Invalid
from frontends.web.modulos import caja_negra
from scripts.qa.web.servicio_ejemplo import ConfiguracionEjemplo, ServicioEjemplo


def ejemplo():
    ctx = Context(service=ServicioEjemplo(), settings=ConfiguracionEjemplo())
    return SimpleNamespace(ctx=ctx, live=None)


def test_lectura_todas_las_columnas_y_todas_las_filas():
    web = ejemplo()
    datos = caja_negra.leer(web.ctx, None)
    assert len(datos["rows"]) == 80
    assert len(datos["columns"]) == 10
    assert set(datos["rows"][0]) == {fila["key"] for fila in datos["columns"]}
    assert "directory" not in datos


@pytest.mark.parametrize("operacion", ["start", "stop", "autostart"])
def test_controles_confirmados_con_el_servicio(operacion):
    web = ejemplo()
    p = {"operation": operacion}
    if operacion == "autostart":
        p["enabled"] = True
    nivel, trabajo = caja_negra.controlar(web.ctx, p, None)
    assert nivel == 1
    trabajo()
    assert web.ctx.service.llamadas[-1][0] == {"start": "blackbox_iniciar", "stop": "blackbox_detener", "autostart": "blackbox_con_la_sesion"}[operacion]


@pytest.mark.parametrize("p", [{"operation": "delete"}, {"operation": "start", "path": "/tmp/x"}, {"operation": "autostart", "enabled": "yes"}])
def test_control_rechaza_parametros(p):
    with pytest.raises(Invalid):
        caja_negra.controlar(ejemplo().ctx, p, None)


def test_diagnostico_completo_sin_recortar_y_descarga():
    web = ejemplo()
    llamadas = []
    def recoger():
        llamadas.append(True)
        return [("GPU", "x" * 20000), ("system", "ok"), ("Journal", "log")]
    web.ctx.service.diagnostico_completo = recoger
    caja_negra.diagnostico(web, {})
    limite = time.monotonic() + 3
    while time.monotonic() < limite:
        datos = caja_negra.diagnostico(web, {})
        if not datos["loading"]:
            break
        time.sleep(0.001)
    assert datos["ready"]
    assert len(datos["sections"][0]["text"]) == 20000
    assert {fila["group"] for fila in datos["sections"]} == {"hardware", "system", "logs"}
    assert len(llamadas) == 1
    assert len(datos["tabs"]) == 4
    assert caja_negra.descargar(web, {"file": "diagnosis"})["text"] == datos["text"]
    assert caja_negra.descargar(web, {"file": "recording"})["filename"] == "bc250-black-box.tsv"
    with pytest.raises(Invalid):
        caja_negra.descargar(web, {"file": "/etc/passwd"})


def test_servicio_ajeno_y_error_del_diagnostico():
    web = ejemplo()
    web.ctx.service.blackbox_estado = lambda: {"autostart": {"supported": True, "foreign": True}}
    _, trabajo = caja_negra.controlar(web.ctx, {"operation": "autostart", "enabled": True}, None)
    with pytest.raises(Invalid):
        trabajo()
    def fallar():
        raise RuntimeError("private path must not escape")
    web.ctx.service.diagnostico_completo = fallar
    caja_negra._recoger(web.ctx)
    estado = web.ctx.state("web_full_diagnosis")
    assert not estado["ready"] and "private" not in estado["error"]


def test_handler_descarga_adjunto_con_nombre_cerrado():
    from frontends.web.server import Handler
    web = ejemplo()
    web.live = SimpleNamespace(touch=lambda: None)
    respuestas = []
    handler = SimpleNamespace(web=web, reply=lambda *args, **kw: respuestas.append((args, kw)),
                              json=lambda *args: pytest.fail("La descarga no es una respuesta JSON"))
    Handler.query(handler, {"name": "supervision.download", "file": "recording"})
    argumentos, opciones = respuestas[0]
    assert argumentos[0].startswith(b"Time\tGPU clock")
    assert opciones["extra"]["Content-Disposition"] == 'attachment; filename="bc250-black-box.tsv"'
