"""Acceso remoto: estado y operaciones cerradas, sin dependencias de Qt.

El QR contiene una ficha de un uso; jamás contiene la clave de acceso.
Las operaciones se vuelven a validar en el trabajador de la consola.
"""
from __future__ import annotations

import time
from datetime import datetime

from bc250cc.application.system import remote_access, web_access, web_pairing, web_setup
from frontends.tui.i18n import tr
from frontends.web.actions import Invalid, choice, flag

AVISO_FIREWALL = "Allow this web port only from the connected private networks? Existing firewall rules are preserved. Administrator authorization is required."
AVISO_NOMBRE = "Repair local name discovery and lookup? This may install Avahi and its resolver module, enable the Avahi service and update the system resolver configuration. A configuration backup is saved and failed resolver changes are reverted. Administrator authorization is required."
AVISO_SESION = "A paired device keeps hardware control until you disconnect it or create a new access key."
MENSAJES_NOMBRE = {
    "ready": "The local address works on this computer. Other devices must support local network name resolution.",
    "resolver_failed": "The local address is advertised, but this computer cannot resolve it. Use the numeric address or repair name resolution.",
    "publication_failed": "The local address is not advertised yet. Use the numeric address or repair local name discovery.",
    "conflict": "The local address points to another device. Use the numeric address.",
    "unavailable": "Local name resolution could not be checked. Use the numeric address.",
    "disabled": "Start web access to check the local address.",
}
MENSAJES_FIREWALL = {
    "blocked": "The firewall may block access from other devices. Configure LAN access below.",
    "needs_check": "The firewall needs an administrator check before LAN access can be configured.",
    "ready": "Firewall rules allow this port on the detected LAN networks. Connect your phone to the same network.",
    "inactive": "UFW is inactive. If connection fails, check Wi-Fi isolation and other network filters.",
    "unknown": "The firewall could not be checked. LAN connectivity is not verified.",
    "unsupported": "Custom or multiple firewall managers detected. Automatic changes are unavailable.",
    "no_network": "No connected private IPv4 network was detected.",
    "update_helper": "Update or reinstall Control Center to install the LAN firewall helper.",
}


def servicio(ctx):
    """La misma fachada de aplicación; el ejemplo puede sustituirla sin tocar el equipo."""
    fabrica = getattr(type(ctx.service), "acceso_remoto_web", None)
    return fabrica(ctx.service) if fabrica else web_access


def ssh(ctx):
    fabrica = getattr(type(ctx.service), "ssh_web", None)
    return fabrica(ctx.service) if fabrica else remote_access


def fecha(valor):
    return datetime.fromtimestamp(float(valor)).astimezone().strftime("%d/%m/%Y %H:%M") if valor else "—"


def dispositivo(item):
    agente = str(item.get("agent") or "")
    plataforma = next((nombre for marca, nombre in (("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"),
        ("Windows", "Windows"), ("Macintosh", "macOS"), ("Linux", "Linux")) if marca in agente), tr("Browser"))
    navegador = next((nombre for marca, nombre in (("Edg/", "Edge"), ("Firefox/", "Firefox"), ("Chrome/", "Chrome"),
        ("Safari/", "Safari")) if marca in agente), "")
    permanente = web_access.is_permanent(item) and not item.get("duration_seconds")
    return {"id": item["id"], "name": " · ".join(filter(None, (plataforma, navegador))),
        "address": item.get("address") or "—", "control": bool(item.get("control")),
        "permanent": permanente, "seen_text": fecha(item.get("seen")), "created_text": fecha(item.get("created")),
        "expiry_text": tr("Permanent") if permanente else fecha(web_access.deadline(item)),
        "label": "Active" if item.get("seen") and time.time() - float(item["seen"]) <= 15 else "Idle"}


def leer(ctx, live):
    estado = servicio(ctx).status()
    pasos = web_setup.pending(estado)
    pregunta = tr("Control Center does these steps in order and stops at the first that fails:")
    pregunta += "\n" + "\n".join(f"{i}. {tr(web_setup.LABELS[paso])}" for i, paso in enumerate(pasos, 1))
    if web_setup.may_follow(pasos):
        pregunta += "\n" + tr("Firewall and local address are checked at the end and fixed only if needed.")
    pregunta += "\n" + tr(AVISO_FIREWALL) + "\n" + tr(AVISO_NOMBRE)
    firewall, nombre = estado.get("firewall") or {}, estado.get("name_health") or {}
    # Solo las lecturas autorizadas por server.py pueden entregar la clave y las fichas.
    return {"web": {k: v for k, v in estado.items() if k != "devices"}, "ssh": ssh(ctx).status(),
        "devices": [dispositivo(item) for item in estado.get("devices") or []],
        "prepare": bool(pasos), "prepare_message": pregunta,
        "name_message": tr(MENSAJES_NOMBRE.get(nombre.get("status"), MENSAJES_NOMBRE["unavailable"])),
        "firewall_message": tr(MENSAJES_FIREWALL.get(firewall.get("state"), MENSAJES_FIREWALL["unknown"])),
        "firewall_warning": tr(AVISO_FIREWALL), "name_warning": tr(AVISO_NOMBRE)}


def matriz(web, p):
    estado = servicio(web.ctx).status()
    direcciones = [u for u in estado.get("urls") or [] if u.startswith("https://")]
    direccion = p.get("address", "")
    if direccion not in direcciones or not estado.get("running") or not estado.get("lan"):
        return {"matrix": []}
    memoria = web.ctx.state("remote")
    ficha = memoria.get("pair", "")
    edad = web_pairing.age(ficha) if ficha else None
    if edad is None or edad > web_pairing.RENEW_SECONDS:
        ficha = web_pairing.issue()
        memoria["pair"] = ficha
    return {"matrix": web_access.pairing_matrix(f"{direccion}#pair={ficha}")}


def sin_parametros(p):
    if p:
        raise Invalid("params")


def simple(nombre, nivel=1):
    def construir(ctx, p, shell):
        sin_parametros(p)
        def ejecutar():
            getattr(servicio(ctx), nombre)()
            return tr("Done")
        return nivel, ejecutar
    return construir


def configurar(ctx, p, shell):
    campo = choice(p, "field", ("lan", "autostart", "port"))
    if set(p) != {"field", "value"}:
        raise Invalid("params")
    valor = p.get("value")
    if campo == "port":
        if isinstance(valor, bool) or not isinstance(valor, int) or not 1024 <= valor <= 65535:
            raise Invalid("port")
    else:
        valor = flag(p, "value")
    def ejecutar():
        api = servicio(ctx)
        if campo == "autostart":
            api.set_autostart(valor)
        elif campo == "lan":
            api.configure(lan=valor, tls=True)
        else:
            api.configure(port=valor)
        return tr("Done")
    return 1, ejecutar


def clave(ctx, p, shell):
    sin_parametros(p)
    def renovar():
        servicio(ctx).access_key(renew=True)  # nunca se imprime en la consola
        return tr("Done")
    return 2, renovar


def preparar(ctx, p, shell):
    sin_parametros(p)
    def ejecutar():
        fabrica = getattr(type(ctx.service), "preparar_acceso_web", None)
        if fabrica:
            fabrica(ctx.service)
        else:
            web_setup.apply(lambda paso: print(tr(web_setup.LABELS[paso]), flush=True))
        return tr("The connection is ready: scan the code with your phone.")
    return 2, ejecutar


def cambiar_dispositivo(ctx, p, shell):
    operacion = choice(p, "operation", ("approve", "control", "lifetime", "revoke"))
    identificador = p.get("id")
    if not isinstance(identificador, str) or len(identificador) != 64 or any(c not in "0123456789abcdef" for c in identificador):
        raise Invalid("id")
    permitidas = {"operation", "id"}
    valor = None
    if operacion == "control":
        permitidas.add("value")
        valor = flag(p, "value")
    if operacion == "lifetime":
        permitidas.add("minutes")
        valor = p.get("minutes")
        if isinstance(valor, bool) or not isinstance(valor, int) or not 0 <= valor <= 525600:
            raise Invalid("minutes")
    if set(p) != permitidas:
        raise Invalid("params")
    def ejecutar():
        api = servicio(ctx)
        if identificador not in {d["id"] for d in api.devices()}:
            raise Invalid("This browser session has expired")
        if operacion == "control":
            api.set_control(identificador, valor)
        elif operacion == "lifetime" and valor:
            api.set_lifetime(identificador, valor * 60)
        elif operacion == "revoke":
            api.revoke(identificador)
        else:
            api.approve(identificador)
        return tr("Done")
    return 2, ejecutar


def configurar_ssh(ctx, p, shell):
    campo = choice(p, "field", ("active", "boot"))
    valor = flag(p, "value")
    if set(p) != {"field", "value"}:
        raise Invalid("params")
    def ejecutar():
        ssh(ctx).configure(**{campo: valor})
        return tr("Done")
    return 2, ejecutar


LECTURAS = {"remote": (3, leer)}
def certificado(web, p):
    """El certificado público de la autoridad local; la clave privada nunca sale de la placa."""
    ruta = servicio(web.ctx).trust_certificate()
    return {"text": ruta.read_text(encoding="ascii"), "filename": "BC250-local-authority.crt"}


CONSULTAS = {"remote.qr": matriz, "remote.certificate": certificado}
ACCIONES = {"remote.start": simple("start"), "remote.stop": simple("stop"),
    "remote.configure": configurar, "remote.key": clave, "remote.prepare": preparar,
    "remote.firewall": simple("repair_firewall", 2), "remote.name": simple("repair_local_name", 2),
    "remote.device": cambiar_dispositivo, "remote.revoke_all": simple("revoke_all", 2), "remote.ssh": configurar_ssh}
