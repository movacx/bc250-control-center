"""Consultas del grabador compartido. No lee sensores ni ejecuta órdenes por su cuenta."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta

from frontends.desktop.core.performance_model import KIND_FILTERS, RESOURCE_BY_KEY
from frontends.desktop.core.performance_views import VIEW_BY_KEY, views_for
from frontends.tui.i18n import tr, tr_format
from frontends.web.actions import Invalid

VENTANAS = (60, 120, 300, 600, 1800)


def consultar(web, parametros):
    # Importación diferida: data incorpora las tablas de módulos al arrancar.
    from frontends.web.data import _chart, performance

    tab = parametros.get("tab", "sensors")
    if tab != "sensors" and tab not in RESOURCE_BY_KEY:
        raise Invalid("tab")
    vista = parametros.get("view", tab)
    permitidas = {item.key for item in views_for(tab)} | {tab}
    if vista not in permitidas:
        raise Invalid("view")
    escala = parametros.get("scale", "auto")
    if escala not in ("auto", "fixed"):
        raise Invalid("scale")
    try:
        ventana = int(parametros.get("window", "120"))
        tipo = int(parametros.get("kind", "0"))
    except (ValueError, TypeError) as error:
        raise Invalid("window/kind") from error
    if ventana not in VENTANAS or tipo not in range(len(KIND_FILTERS)):
        raise Invalid("window/kind")
    if parametros.get("hide", "1") not in ("0", "1"):
        raise Invalid("hide")
    if len(parametros.get("q", "")) > 160 or len(parametros.get("ticked", "")) > 16384:
        raise Invalid("filter")
    tipos = parametros.get("kinds", str(tipo))
    try:
        elegidos = {int(item) for item in tipos.split(",") if item}
    except ValueError as error:
        raise Invalid("kinds") from error
    if not elegidos.issubset(set(range(len(KIND_FILTERS)))):
        raise Invalid("kinds")
    recorder = web.live.recorder
    with web.ctx.lock:
        ampliar_historial(recorder)
        anterior = recorder.window
        try:
            recorder.window = ventana
            resultado = performance(web.live, dict(parametros, tab=tab, view=vista, scale=escala, kind="0" if "kinds" in parametros else str(tipo)))
        finally:
            recorder.window = anterior
        # Las trazas de sensores también respetan la ventana, como los recursos.
        for traza in resultado.get("traces", []):
            grafica = traza["chart"]
            indices = [i for i, edad in enumerate(grafica["ages"]) if edad <= ventana]
            series = [(item["name"], [item["values"][i] for i in indices]) for item in grafica["series"]]
            traza["chart"] = _chart(series, [grafica["ages"][i] for i in indices], grafica["unit"], False, grafica["rate"])
        if tab == "sensors":
            if "kinds" in parametros and elegidos and 0 not in elegidos:
                clases = {kind for indice in elegidos for kind in KIND_FILTERS[indice][1]}
                filas, grupo, añadido = [], None, False
                for fila in resultado.get("rows", []):
                    if "group" in fila:
                        grupo, añadido = fila, False
                    elif recorder.log.entries[fila["key"]].reading.kind in clases:
                        if grupo is not None and not añadido:
                            filas.append(grupo)
                            añadido = True
                        filas.append(fila)
                resultado["rows"] = filas
                resultado["count"] = tr_format("{shown} of {count} sensors", shown=sum("key" in fila for fila in filas), count=len(recorder.log.order))
            # Como el escritorio, una gráfica marcada se oculta con su fila filtrada.
            visibles = {fila["key"] for fila in resultado.get("rows", []) if "key" in fila}
            resultado["traces"] = [traza for traza in resultado.get("traces", []) if traza["key"] in visibles]
            resultado["missing_traces"] = [traza for traza in resultado.get("missing_traces", []) if traza["key"] in visibles]
            inicio = datetime.now() - timedelta(seconds=max(0, recorder.log._clock() - recorder.log.started_at))
            resultado["footer"] = tr_format("Minimum, average and maximum since {time} · 1 s cadence · double-click a row to draw it", time=inicio.strftime("%H:%M:%S"))
        for opcion in resultado.get("views", []):
            definicion = VIEW_BY_KEY.get(opcion["key"])
            if not opcion["available"] and definicion and definicion.unavailable_hint:
                opcion["hint"] = tr(definicion.unavailable_hint)
        resultado["window"] = ventana
        resultado["error"] = web.ctx.metrics_error
        return resultado


def reiniciar(ctx, parametros):
    if parametros:
        raise Invalid("params")
    with ctx.lock:
        recorder = ctx.state("performance").get("recorder")
        if recorder is not None:
            recorder.log.reset_statistics()


CONSULTAS = {"performance": consultar}
AJUSTES = {"performance.reset": reiniciar}
LECTURAS = {"performance": (1, lambda ctx, live: {"error": ctx.metrics_error, "sampled": live.recorder.sampled_at})}


def ampliar_historial(recorder):
    """Conservar treinta minutos sin perder muestras ya recogidas al abrir la página."""
    profundidad = VENTANAS[-1] + 1
    if recorder.depth >= profundidad:
        return
    recorder.depth = profundidad
    for historia in (*recorder.histories.values(), *recorder.views.values(), *recorder.volume_histories.values()):
        historia.times = deque(historia.times, maxlen=profundidad)
        historia.values = {nombre: deque(valores, maxlen=profundidad) for nombre, valores in historia.values.items()}
    recorder.log._trace_points = profundidad
    for entrada in recorder.log.entries.values():
        entrada.trace = deque(entrada.trace, maxlen=profundidad)


def leer_preferencias(ctx, live):
    config = ctx.settings.read_local_config() if ctx.settings else {}
    return {"preferences": config.get("web_performance") or {}, "error": ctx.metrics_error,
            "sampled": live.recorder.sampled_at}


def guardar_preferencias(ctx, parametros):
    from frontends.web.actions import choice, flag
    layout = choice(parametros, "layout", ("list", "split", "graphs"))
    hide = flag(parametros, "hide")
    window = parametros.get("window")
    if isinstance(window, bool) or not isinstance(window, int) or window not in VENTANAS:
        raise Invalid("window")
    kinds = parametros.get("kinds")
    if not isinstance(kinds, list) or len(kinds) > len(KIND_FILTERS) or any(
        isinstance(item, bool) or not isinstance(item, int) or item not in range(1, len(KIND_FILTERS)) for item in kinds):
        raise Invalid("kinds")
    ticked = parametros.get("ticked")
    if ticked is not None and (not isinstance(ticked, list) or len(ticked) > 256 or any(
            not isinstance(item, str) or len(item) > 256 for item in ticked)):
        raise Invalid("ticked")
    ctx.settings.save_local_config({"web_performance": {"layout": layout, "hide": hide, "window": window,
                                                       "kinds": kinds, "ticked": ticked}})


LECTURAS["performance"] = (0, leer_preferencias)
AJUSTES["performance.preferences"] = guardar_preferencias
