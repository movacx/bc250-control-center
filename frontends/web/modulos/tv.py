"""El mando de la TV: lo que dice cecd, cada botón y las dos automatizaciones."""

from __future__ import annotations

from frontends.tui.i18n import tr, tr_format
from frontends.web.actions import Invalid, choice, flag

BOTONES = ("tv-on", "tv-off", "switch", "amp-on", "amp-off", "volume-up", "volume-down", "mute")
ESTADOS = {
    "on": "Powered on", "standby": "Standby", "waking": "Waking up", "going-to-standby": "Going to standby",
    "unknown": "Unknown", "no-reply": "No reply",
}
MENSAJES = {
    "sent": "Sent.",
    "amp-awake": "The receiver is awake.",
    "no-adapter": "No CEC adapter is connected. CEC needs a DisplayPort-to-HDMI adapter that passes it.",
    "no-daemon": "cecd is not running. Install TV control first.",
    "no-busctl": "busctl (systemd) is required.",
    "no-address": "This adapter has no address yet; the receiver may still be negotiating. Try again in a few seconds.",
    "failed": "The command was not accepted. If nothing happened, the TV or the adapter does not pass CEC.",
}
AUTOMATICO = (
    ("wake", "Turn the TV on when this computer starts",
     "Wakes the TV and switches it to this input once per session. A TV that is on and showing another device is left alone."),
    ("poweroff", "Turn the TV off when this computer shuts down",
     "A real power-off only, not a reboot or a suspend. Needs cec-ctl (v4l-utils). A TV showing another device is left alone."),
)


def _estado(valor) -> str:
    return tr(ESTADOS[valor]) if valor in ESTADOS else "--"


def consultar(web, parametros) -> dict:
    servicio = web.ctx.service
    estado = servicio.tv_control_status() or {}
    automatico = servicio.tv_control_automation() or {}
    adaptador = str(estado.get("adapter") or "")
    if not adaptador:
        aviso = tr(MENSAJES["no-adapter"])
    elif not estado.get("daemon"):
        aviso = tr(MENSAJES["no-daemon"])
    else:
        aviso = ""
    filas = []
    for clave, titulo, detalle in AUTOMATICO:
        situacion = str(automatico.get(clave) or "absent")
        ajena = situacion == "foreign"
        filas.append({"key": clave, "title": tr(titulo), "detail": tr(detalle), "installed": situacion == "installed",
                      "foreign": ajena,
                      "note": tr("Another toolkit already does this. Remove it first to manage it here.") if ajena else ""})
    return {"tv": _estado(estado.get("tv")), "receiver": _estado(estado.get("receiver")),
            "address": str(estado.get("address") or "--"), "ready": bool(adaptador and estado.get("daemon")),
            "notice": aviso, "through": aviso or tr_format("Talking to cecd through {adapter}.", adapter=adaptador),
            "automation": filas}


def pulsar(ctx, p) -> dict:
    if set(p) != {"button"}:
        raise Invalid("params")
    resultado = ctx.service.tv_control_action(choice(p, "button", BOTONES)) or {}
    codigo = str(resultado.get("code") or "failed")
    mensaje = tr(MENSAJES.get(codigo, MENSAJES["failed"]))
    detalle = str(resultado.get("detail") or "")
    if codigo == "amp-awake" and detalle:
        mensaje += " " + tr_format("System audio: {state}.", state=tr("on" if detalle == "on" else "off"))
    return {"sent": bool(resultado.get("ok")), "text": mensaje}


def automatizar(ctx, p, shell):
    if set(p) != {"key", "enable"}:
        raise Invalid("params")
    clave = choice(p, "key", ("wake", "poweroff"))
    orden = f"{clave}-{'install' if flag(p, 'enable') else 'remove'}"
    return 1, lambda: ctx.service.manage_accessory("hdmi_cec", orden)


CONSULTAS = {"tv.status": consultar}
ACCIONES = {"tv.automation": automatizar}
AJUSTES = {"tv.press": pulsar}
