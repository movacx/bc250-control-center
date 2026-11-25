"""Las selecciones del navegador nunca sustituyen las identidades del servicio."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from frontends.tui.runtime import Context
from frontends.web.actions import Invalid
from frontends.web.modulos import procesos
from scripts.qa.web.servicio_ejemplo import (
    PROCESOS,
    ConfiguracionEjemplo,
    ServicioEjemplo,
)


def contexto():
    return Context(service=ServicioEjemplo(), settings=ConfiguracionEjemplo())


def test_consulta_agrupa_busca_ordena_y_conserva_todas_las_filas():
    ctx = contexto()
    web = SimpleNamespace(ctx=ctx)
    inventario = [*PROCESOS, replace(PROCESOS[0], pid=3000), replace(PROCESOS[1], pid=3001, protegido=True)]
    ctx.service.inventario_procesos = lambda: {"processes": inventario}
    datos = procesos.consultar(web, {"sort": "name", "descending": "0"})
    assert datos["count"] == 5
    assert sum(fila["process_count"] for fila in datos["rows"]) == 7
    firefox = next(fila for fila in datos["rows"] if fila["key"] == "firefox")
    assert len(firefox["targets"]) == 2
    steam = next(fila for fila in datos["rows"] if fila["key"] == "steam")
    assert len(steam["targets"]) == 1
    assert procesos.consultar(web, {"search": "3000", "grouped": "0"})["count"] == 1
    assert procesos.consultar(web, {"search": "no existe"})["rows"] == []


@pytest.mark.parametrize("operacion,metodo", [("end", "cerrar_procesos"), ("pause", "pausar_procesos"), ("resume", "pausar_procesos")])
def test_acciones_vuelven_a_comprobar_proteccion_y_nacimiento(operacion, metodo):
    ctx = contexto()
    inventario = [replace(PROCESOS[0], protegido=True), PROCESOS[1], replace(PROCESOS[2], create_time=5)]
    ctx.service.inventario_procesos = lambda: {"processes": inventario}
    nivel, trabajo = procesos.actuar(ctx, {"operation": operacion, "targets": [
        {"pid": proceso.pid, "created": proceso.create_time} for proceso in PROCESOS[:3]]}, None)
    assert nivel == 1
    trabajo()
    nombre, argumentos, opciones = ctx.service.llamadas[-1]
    assert nombre == metodo
    assert [proceso.pid for proceso in argumentos[0]] == [PROCESOS[1].pid]
    if operacion != "end":
        assert opciones["pausar"] == (operacion == "pause")


@pytest.mark.parametrize("objetivos", [[], [{"pid": True, "created": 1}], [{"pid": 1, "created": float("nan")}],
    [{"pid": 1, "created": 1, "comando": "rm"}], [{"pid": -1, "created": 1}]])
def test_rechaza_identidades_malformadas(objetivos):
    ctx = contexto()
    with pytest.raises(Invalid):
        procesos.actuar(ctx, {"operation": "end", "targets": objetivos}, None)
    assert not ctx.service.llamadas


def test_objetivo_desaparecido_y_parametros_cerrados():
    ctx = contexto()
    _, trabajo = procesos.actuar(ctx, {"operation": "end", "targets": [{"pid": 123, "created": 9}]}, None)
    with pytest.raises(Invalid):
        trabajo()
    with pytest.raises(Invalid):
        procesos.consultar(SimpleNamespace(ctx=ctx), {"view": "root"})
    with pytest.raises(Invalid):
        procesos.cache(ctx, {"path": "/tmp"}, None)
    nivel, trabajo = procesos.cache(ctx, {}, None)
    assert nivel == 1
    trabajo()
    assert ctx.service.llamadas[-1][0] == "limpiar_cache"
