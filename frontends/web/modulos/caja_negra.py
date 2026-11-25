"""Grabador y diagnóstico completo: lecturas y controles cerrados sin Qt."""
import threading

from bc250cc.application.system.privacy import redact_machine
from frontends.desktop.core.diagnosis_groups import (
    TABS,
    as_text,
    section_group,
    size_kb,
)
from frontends.tui.i18n import tr, tr_format
from frontends.web.actions import Invalid, choice, flag
from frontends.web.blackbox import COLUMNS

ESTADOS = {
    "none": "Nothing was recorded yet. Start the black box before playing to catch a freeze.",
    "recording": "Recording now. The newest row is at the top.",
    "stopped": "Stopped. These are the last rows it recorded.",
    "stopped-before-restart": "It was stopped normally before the last restart. These are the last rows it recorded.",
    "cut-off": "Cut off by a restart or a freeze. The top rows are the board's last seconds.",
}

#: Las columnas que el escritorio alinea a la izquierda; los números van a la derecha.
IZQUIERDA = ("time", "clock", "rpm")


def leer(ctx, live):
    estado = ctx.service.blackbox_estado() or {}
    # Solo sensores. No devolver directorios de la cuenta ni otros metadatos.
    return {"supported": bool(estado.get("supported")), "running": bool(estado.get("running")),
            "state": estado.get("state", "none"), "message": ESTADOS.get(estado.get("state"), ESTADOS["none"]),
            "autostart": {clave: bool((estado.get("autostart") or {}).get(clave))
                          for clave in ("supported", "enabled", "foreign")},
            "columns": [{"key": clave, "label": titulo, "left": clave in IZQUIERDA} for titulo, clave in COLUMNS],
            "rows": [{clave: str(fila.get(clave, "–")) for _, clave in COLUMNS}
                     for fila in estado.get("rows", [])]}


def controlar(ctx, p, shell):
    operacion = choice(p, "operation", ("start", "stop", "autostart"))
    if set(p) != ({"operation", "enabled"} if operacion == "autostart" else {"operation"}):
        raise Invalid("params")
    activo = flag(p, "enabled") if operacion == "autostart" else False

    def ejecutar():
        estado = ctx.service.blackbox_estado() or {}
        if operacion == "autostart":
            inicio = estado.get("autostart") or {}
            if not inicio.get("supported") or inicio.get("foreign"):
                raise Invalid("Start with the session")
            return ctx.service.blackbox_con_la_sesion(activo)
        if not estado.get("supported"):
            raise Invalid("Black box")
        if operacion == "start":
            return ctx.service.blackbox_iniciar()
        return ctx.service.blackbox_detener()
    return 1, ejecutar


def diagnostico(web, p):
    refrescar = choice({"refresh": p.get("refresh", "0")}, "refresh", ("0", "1")) == "1"
    # Una colección por sesión de servidor, nunca una por cada tick del grabador.
    with web.ctx.lock:
        estado = web.ctx.state("web_full_diagnosis")
        if "loading" not in estado or refrescar and not estado["loading"]:
            estado.update(loading=True, ready=False, error="")
            threading.Thread(target=_recoger, args=(web.ctx,), daemon=True).start()
        return {**estado, "tabs": [{"key": clave, "label": titulo} for clave, titulo in TABS]}


def _recoger(ctx):
    try:
        # El colector del servicio anonimiza también los adjuntos antes de devolverlos.
        secciones = [(str(titulo), redact_machine(str(cuerpo)))
                     for titulo, cuerpo in ctx.service.diagnostico_completo()]
        filas = [{"title": titulo, "text": cuerpo, "group": section_group(titulo), "size": size_kb(cuerpo)}
                 for titulo, cuerpo in secciones]
        resultado = {"loading": False, "ready": True, "sections": filas, "text": as_text(secciones), "error": ""}
    except Exception:
        resultado = {"loading": False, "ready": False, "sections": [],
                     "error": tr_format("Could not collect the diagnosis: {reason}", reason=tr("Unavailable")), "text": ""}
    with ctx.lock:
        ctx.state("web_full_diagnosis").update(resultado)


LECTURAS = {"black_box": (1, leer)}
CONSULTAS = {"black_box.diagnosis": diagnostico}
ACCIONES = {"black_box.control": controlar}


def descargar(web, p):
    tipo = choice(p, "file", ("diagnosis", "recording", "fans"))
    if tipo == "fans":
        from frontends.web.modulos.ventiladores import diagnostico
        return {"filename": "bc250-fan-profiles.json", "text": diagnostico(web, {"view": "export"})["text"]}
    if tipo == "diagnosis":
        with web.ctx.lock:
            estado = web.ctx.state("web_full_diagnosis")
            if not estado.get("ready") or estado.get("loading"):
                raise Invalid("Not checked yet")
            return {"filename": "bc250-diagnosis.txt", "text": estado["text"]}
    datos = leer(web.ctx, web.live)
    encabezado = "\t".join(titulo for titulo, _ in COLUMNS)
    filas = ["\t".join(fila[clave] for _, clave in COLUMNS) for fila in datos["rows"]]
    return {"filename": "bc250-black-box.tsv", "text": "\n".join([encabezado, *filas])}


CONSULTAS["supervision.download"] = descargar
