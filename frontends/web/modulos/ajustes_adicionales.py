"""Ajustes adicionales: presentación sin Qt y operaciones con opciones cerradas.

LECTURAS entrega las cinco pestañas. CONSULTAS resuelve los selectores sin
cambiar el sistema. ACCIONES reconstruye la fila con un inventario nuevo y
valida todas las respuestas antes de llamar al servicio en action_worker.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from frontends.desktop.i18n import tr
from frontends.tui.content import Buttons, Choice, Field, Note
from frontends.tui.pages.base import os_family
from frontends.tui.runtime import Context
from frontends.web.actions import Invalid, choice

from .ajustes_adicionales_compat import Action, Fila
from .ajustes_adicionales_presentacion import (
    GOVERNORS,
    MEMORY_POLICIES,
    SWAP_POLICIES,
    AdditionalSettingsPage,
)
from .ajustes_adicionales_suplementos import (
    alcance,
    completar,
    enlaces,
    opciones_helixsr,
)

#: Lo que hace cada política, con las palabras del escritorio (``dashboard_widgets``).
DETALLES_MEMORIA = {
    "current": "The current ZRAM, ZSWAP and backing-swap configuration would be preserved.",
    "preserve": "The current ZRAM, ZSWAP and backing-swap configuration would be preserved.",
    "zram": "ZRAM would remain the compressed in-memory swap device; no disk swapfile would be created.",
    "zram-swap-16": "ZRAM remains primary and a verified 16 GiB disk swapfile is used only as an emergency fallback.",
    "swap-16": "Creates or reuses a verified 16 GiB disk swapfile as backing swap.",
    "swap-32": "Creates or reuses a verified 32 GiB disk swapfile as backing swap.",
    "zswap-16": "A verified 16 GiB backing swapfile would be required before enabling ZSWAP and disabling ZRAM.",
    "zswap-32": "A verified 32 GiB backing swapfile would be required before enabling ZSWAP and disabling ZRAM.",
    "restore": "Reverts every BC250 memory change back to what it was before.",
}
PESTANAS = (("compatibility", "Compatibility"), ("upscaling", "Upscaling"),
            ("memory", "Memory & Swap"), ("drivers", "Drivers"), ("decky", "Decky"))


def identidad(texto):
    return hashlib.sha256(texto.encode()).hexdigest()[:24]


def contexto(ctx):
    # Los borradores de un dispositivo nunca se comparten con otro.
    copia = Context(service=ctx.service, settings=ctx.settings, config=ctx.settings.read_local_config())
    copia.page_state = {"system": dict(ctx.state("system"))}
    return copia


class SoloLectura:
    """El servicio mientras se describe o se pregunta: una operación nunca llega a ejecutarse."""

    PERMITIDAS = {"driver_inventory", "tv_control_status", "accessory_configure_argv"}

    def __init__(self, servicio):
        self._servicio = servicio

    def __getattr__(self, nombre):
        if nombre.startswith(("estado_", "ultima_", "diagnostico_")) or nombre in self.PERMITIDAS:
            return getattr(self._servicio, nombre)

        def operacion(*_args, **_kwargs):
            raise Pendiente({"kind": "confirm", "title": "Additional settings", "detail": tr("Continue"), "danger": True})
        return operacion


def inventario(ctx):
    pagina = AdditionalSettingsPage()
    return pagina.load(ctx)


def paneles(ctx, datos, pestaña):
    pagina = AdditionalSettingsPage()
    familia, _ = os_family(ctx)
    if pestaña == "decky":
        resultado = []
    else:
        resultado = pagina.build(ctx, datos, pestaña, None)
    if pestaña == "compatibility":
        resultado += pagina._boot_options(ctx, datos, familia)
    return completar(ctx, datos, pestaña, resultado)


def filas(panel):
    for elemento in panel.blocks:
        if isinstance(elemento, Buttons):
            yield from elemento.choices
        elif isinstance(elemento, Choice):
            yield elemento


def operaciones(fila):
    if isinstance(fila, Fila):
        return fila.acciones or []
    if fila.handler and fila.enabled:
        return [Action(fila.label, show=fila.handler)]
    return []


def clave_fila(panel, fila):
    return identidad(panel.title + "\n" + fila.identity)


def clave_operacion(operacion):
    return identidad(operacion.label)


def sin_alcance(titulo, detalle):
    """La TUI repite al final del detalle dónde se puede usar; aquí ya hay una línea para eso."""
    for _clave, nombre, donde, _texto in GOVERNORS:
        if titulo == tr(nombre):
            return detalle.removesuffix(tr(donde)).strip()
    return detalle


def describir_panel(panel):
    retiradas = {tr(nombre) for nombre in ("Remove", "Uninstall")}
    elementos = []
    for fila in filas(panel):
        info = asdict(fila.info) if fila.info else {}
        acciones = []
        for operacion in operaciones(fila):
            acciones.append({"id": clave_operacion(operacion), "label": operacion.label,
                             "danger": operacion.danger, "enabled": getattr(operacion, "enabled", True),
                             "removal": operacion.label in retiradas,
                             "window": "tv" if operacion.label == tr("Open TV control") else ""})
        elementos.append({"id": clave_fila(panel, fila), "title": fila.label,
                          "value": fila.badge or fila.detail, "tone": fila.badge_tone,
                          "detail": sin_alcance(fila.label, info.get("summary", "")), "risk": info.get("risk", ""),
                          "undo": info.get("undo", ""), "blocked": info.get("blocked", ""),
                          "enabled": fila.enabled, "on": getattr(fila, "encendida", None),
                          "actions": acciones, "links": enlaces(fila.label), "scope": alcance(fila.label)})
        if not isinstance(fila, Fila) and fila.handler:
            try:
                fila.handler(Selector([]))
            except Pendiente as paso:
                elementos[-1]["form"] = paso.formulario
    lecturas = []
    for elemento in panel.blocks:
        if isinstance(elemento, Field):
            lecturas.append({"label": elemento.label, "value": elemento.value, "tone": elemento.tone})
        elif isinstance(elemento, Note):
            lecturas.append({"label": "", "value": elemento.text, "tone": elemento.tone})
    return {"title": panel.title, "detail": panel.subtitle, "value": panel.badge,
            "rows": elementos, "readings": lecturas}


def leer(ctx, live):
    ctx = contexto(ctx)
    ctx.service = SoloLectura(ctx.service)
    datos = inventario(ctx)
    familia, nombre = os_family(ctx)
    politicas = MEMORY_POLICIES if familia == "bazzite" else SWAP_POLICIES
    vistas = {}
    for clave, titulo in PESTANAS:
        vistas[clave] = {"title": titulo, "panels": [describir_panel(p) for p in paneles(ctx, datos, clave)]}
    return {"system": nombre, "tabs": vistas, "keep_policy": politicas[0][0],
            "swap_policies": [{"value": clave, "title": tr(titulo), "detail": tr(DETALLES_MEMORIA.get(clave, ""))}
                              for clave, titulo in politicas], "helixsr_settings": opciones_helixsr(datos),
            "memory": datos.get("tools", {}).get("memory_runtime", {}),
            "tools": {k: datos.get("tools", {}).get(k, {}) for k in ("fsr4", "helixsr")}}


class Pendiente(BaseException):
    """Detiene un selector antes de que pueda realizar una operación."""
    def __init__(self, formulario):
        self.formulario = formulario


class Selector:
    """Reproduce los diálogos de la TUI con respuestas comprobadas una a una."""
    unicode = True

    def __init__(self, respuestas, *, ejecutar=False, shell=None, carpetas=()):
        self.respuestas = list(respuestas)
        self.ejecutar = ejecutar
        self.shell = shell
        self.carpetas = carpetas
        self.resultado = None

    def choose(self, title, options):
        if not options:
            raise Invalid("No options")
        if not self.respuestas:
            raise Pendiente({"kind": "choice", "title": title,
                             "options": [{"value": valor, "label": etiqueta} for valor, etiqueta in options]})
        valor = self.respuestas.pop(0)
        for permitido, _ in options:
            # True no debe pasar por 1; las tuplas viajan como listas JSON.
            if json.dumps(valor, sort_keys=True) == json.dumps(permitido, sort_keys=True):
                return permitido
        raise Invalid("choice")

    def ask_text(self, label, default=""):
        # Nunca se acepta una ruta escrita por el cliente. Los juegos vienen
        # del inventario o del selector de carpetas con raíces autorizadas.
        if "folder" in label.lower() or not default:
            return self.choose(label, [(p, p) for p in self.carpetas])
        raise Invalid("text")

    def confirm(self, message, *, danger=False):
        if self.respuestas:
            raise Invalid("answers")
        if not self.ejecutar:
            raise Pendiente({"kind": "confirm", "title": "Additional settings", "detail": message, "danger": danger})
        return True

    def run(self, label, work):
        # El mando de TV consulta el estado antes de ofrecer sus siete botones.
        if getattr(work, "__name__", "") == "tv_control_status":
            return True, work()
        if self.respuestas:
            raise Invalid("answers")
        if not self.ejecutar:
            raise Pendiente({"kind": "confirm", "title": label, "detail": label, "danger": True})
        self.resultado = work()
        return True, self.resultado

    def show_text(self, title, text):
        if self.respuestas:
            raise Invalid("answers")
        raise Pendiente({"kind": "text", "title": title, "detail": text})

    def notify(self, message, tone=""):
        if not self.ejecutar:
            raise Pendiente({"kind": "text", "title": "Additional settings", "detail": message})

    def refresh(self):
        pass


def parametros(p):
    if set(p) - {"tab", "row", "operation", "answers"}:
        raise Invalid("params")
    pestaña = choice(p, "tab", tuple(k for k, _ in PESTANAS))
    for clave in ("row", "operation"):
        if not isinstance(p.get(clave), str) or len(p[clave]) != 24:
            raise Invalid(clave)
    respuestas = p.get("answers", [])
    if not isinstance(respuestas, list) or len(respuestas) > 8 or len(json.dumps(respuestas)) > 8192:
        raise Invalid("answers")
    return pestaña, respuestas


def resolver(ctx, p, *, ejecutar=False, shell=None):
    from .ajustes_adicionales_carpetas import carpetas_disponibles

    pestaña, respuestas = parametros(p)
    ctx = contexto(ctx)
    if not ejecutar:
        ctx.service = SoloLectura(ctx.service)
    datos = inventario(ctx)
    for panel in paneles(ctx, datos, pestaña):
        for fila in filas(panel):
            if clave_fila(panel, fila) != p["row"] or not fila.enabled:
                continue
            for operacion in operaciones(fila):
                if clave_operacion(operacion) != p["operation"] or not getattr(operacion, "enabled", True):
                    continue
                selector = Selector(respuestas, ejecutar=ejecutar, shell=shell,
                                    carpetas=carpetas_disponibles(datos))
                try:
                    if operacion.show:
                        operacion.show(selector)
                    elif operacion.work:
                        selector.confirm(operacion.question or operacion.label, danger=operacion.danger)
                        selector.run(operacion.label, operacion.work)
                    else:
                        raise Invalid("operation")
                except Pendiente as paso:
                    if ejecutar:
                        raise Invalid("incomplete operation") from None
                    return paso.formulario
                return selector.resultado if ejecutar else {"kind": "text", "title": fila.label, "detail": fila.detail}
    raise Invalid("Operation no longer available")


def consultar(web, p):
    try:
        recibidos = json.loads(p.get("request", "{}"))
        if not isinstance(recibidos, dict):
            raise Invalid("request")
        return resolver(web.live.ctx, recibidos)
    except (ValueError, TypeError, KeyError) as error:
        return {"kind": "error", "error": str(error)}


def actuar(ctx, p, shell):
    parametros(p)
    # También las operaciones sin privilegios pasan por la consola heredada.
    return 2, lambda: resolver(ctx, p, ejecutar=True, shell=shell)


def guardar_helixsr(ctx, p, shell):
    from .ajustes_adicionales_suplementos import validar_helixsr
    if set(p) != {"values"}:
        raise Invalid("params")
    valores = validar_helixsr(inventario(ctx), p["values"])
    return 1, lambda: ctx.service.guardar_ajustes_helixsr(validar_helixsr(inventario(ctx), valores))


LECTURAS = {"extras": (6, leer)}
CONSULTAS = {"extras.dialog": consultar}
ACCIONES = {"extras.run": actuar, "extras.helixsr_settings": guardar_helixsr}
AJUSTES = {}
