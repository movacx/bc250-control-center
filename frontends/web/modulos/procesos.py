"""Inventario compartido y operaciones sobre identidades verificadas, sin Qt."""
import json
from math import isfinite
from types import SimpleNamespace

from frontends.desktop.core.process_entries import build_entries, formato_bytes
from frontends.desktop.i18n import count_label
from frontends.tui.i18n import tr, tr_format
from frontends.web.actions import Invalid, choice

VISTAS = ("apps", "background", "system", "all")
ORDENES = ("name", "cpu", "gpu", "memory", "vram")


def _opcion(p, clave, opciones, defecto):
    return choice({clave: p.get(clave, defecto)}, clave, opciones)


def _porcentaje(valor):
    if valor is None:
        return "—"
    if valor < 0.05:
        return "0 %"
    return f"{valor:.1f} %" if valor < 10 else f"{valor:.0f} %"


def _fila(entrada):
    estado, tono, detalle = entrada.status()
    return {
        "key": entrada.key, "name": entrada.name, "kind": entrada.kind,
        "subtitle": entrada.subtitle, "cpu": entrada.cpu, "gpu": entrada.gpu,
        "memory": formato_bytes(entrada.memory), "vram": formato_bytes(entrada.vram) if entrada.vram else "—",
        "cpu_text": _porcentaje(entrada.cpu), "gpu_text": _porcentaje(entrada.gpu),
        "memory_bytes": entrada.memory, "memory_hint": entrada.memory_tooltip(),
        "vram_hint": entrada.gpu_memory_tooltip(), "process_count": len(entrada.processes), "status": tr(estado), "tone": tono,
        "detail": detalle, "protected": entrada.fully_protected, "paused": entrada.paused,
        "targets": [{"pid": proceso.pid, "created": proceso.create_time}
                    for proceso in entrada.closable if proceso.create_time],
    }


def consultar(web, p):
    if set(p) - {"name", "view", "sort", "grouped", "descending", "search", "selected"}:
        raise Invalid("params")
    if "name" in p:
        choice(p, "name", ("processes.rows",))
    vista = _opcion(p, "view", VISTAS, "apps")
    orden = _opcion(p, "sort", ORDENES, "memory")
    grupo = _opcion(p, "grouped", ("0", "1"), "1") == "1"
    descendente = _opcion(p, "descending", ("0", "1"), "1") == "1"
    buscar = p.get("search", "")
    if not isinstance(buscar, str) or len(buscar) > 256:
        raise Invalid("search")
    inventario = web.ctx.service.inventario_procesos() or {}
    procesos = inventario.get("processes") or []
    entradas = build_entries(procesos, grouped=grupo, view=vista, query=buscar)
    def valor_orden(entrada):
        return entrada.sort_value(orden)

    entradas.sort(key=valor_orden, reverse=descendente)
    escogidas = p.get("selected", "[]")
    if not isinstance(escogidas, str) or len(escogidas) > 32768:
        raise Invalid("selected")
    try:
        claves = json.loads(escogidas)
    except ValueError as error:
        raise Invalid("selected") from error
    if not isinstance(claves, list) or len(claves) > 4096 or any(not isinstance(clave, str) for clave in claves):
        raise Invalid("selected")
    elegidas = [entrada for entrada in entradas if entrada.key in claves]
    reales = [proceso for entrada in elegidas for proceso in entrada.closable]
    resumen = tr_format("{applications} · {processes} · approx. {memory}",
        applications=count_label(len(elegidas), "application"), processes=count_label(len(reales), "process"),
        memory=formato_bytes(sum(int(proceso.memoria or 0) for proceso in reales))) if elegidas else ""
    juegos = build_entries(procesos, grouped=True, view="all")
    juego = next((entrada for entrada in juegos if entrada.kind == "game"), None)
    return {"rows": [_fila(entrada) for entrada in entradas], "game": _fila(juego) if juego else {},
            "oomd": bool(inventario.get("oomd")), "count": len(entradas), "selection": resumen,
            "summary": tr_format("{rows} · {processes}", rows=count_label(len(entradas), "row"),
                                 processes=count_label(sum(len(entrada.processes) for entrada in entradas), "process"))}


def actuar(ctx, p, shell):
    operacion = choice(p, "operation", ("end", "pause", "resume"))
    if set(p) != {"operation", "targets"}:
        raise Invalid("params")
    objetivos = p.get("targets")
    if not isinstance(objetivos, list) or not 1 <= len(objetivos) <= 4096:
        raise Invalid("targets")
    identidades = set()
    for objetivo in objetivos:
        if not isinstance(objetivo, dict) or set(objetivo) != {"pid", "created"}:
            raise Invalid("targets")
        pid, creado = objetivo["pid"], objetivo["created"]
        if (type(pid) is not int or not 1 <= pid <= 2**22 or type(creado) not in (int, float)
                or not isfinite(creado) or creado <= 0):
            raise Invalid("targets")
        identidades.add((pid, creado))

    def ejecutar():
        # Inventario nuevo en el trabajador. Nunca reconstruir un proceso con datos
        # del navegador: el servicio vuelve a comprobar dueño, PID y nacimiento.
        inventario = ctx.service.inventario_procesos() or {}
        seleccion = [proceso for proceso in inventario.get("processes", [])
                     if (proceso.pid, proceso.create_time) in identidades and not proceso.protegido]
        if not seleccion:
            raise Invalid(tr("No applications selected"))
        if operacion == "end":
            return ctx.service.cerrar_procesos(seleccion)
        return ctx.service.pausar_procesos(seleccion, pausar=operacion == "pause")
    return 1, ejecutar


def cache(ctx, p, shell):
    if p:
        raise Invalid("params")
    return 1, ctx.service.limpiar_cache


def leer(ctx, live):
    return consultar(SimpleNamespace(ctx=ctx), {})


LECTURAS = {"processes": (2, leer)}
CONSULTAS = {"processes.rows": consultar}
ACCIONES = {"processes.tasks": actuar, "processes.cache": cache}
