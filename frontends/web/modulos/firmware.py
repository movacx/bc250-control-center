"""Catálogo BIOS y preparación USB. Nunca graba la BIOS ni la NVRAM.

La identidad opaca liga la confirmación a la unidad completa (no a una ruta
que mande el navegador). UsbPreparation comprueba otra vez esa identidad
inmediatamente antes de borrar. SIGINT solo cancela antes de tocar el USB.
"""
from __future__ import annotations

import base64
import hashlib
import json
import signal
import threading
from dataclasses import asdict
from datetime import datetime

from bc250cc.application.firmware import firmware_snapshot
from bc250cc.domain.firmware.boot_logo import MAX_LOGO_BYTES, check_logo_jpeg
from bc250cc.domain.firmware.catalog import (
    DEFAULT_FAMILY,
    FAMILIES_BY_KEY,
    FIRMWARE_FAMILIES,
    archives_of,
    sources_for,
)
from bc250cc.domain.firmware.usb import format_size
from bc250cc.domain.firmware.usb_kit import plan_kit
from bc250cc.infrastructure.firmware import lzma1, udisks
from bc250cc.infrastructure.firmware.board import record_prepared_kit
from bc250cc.infrastructure.firmware.preparation import (
    PreparationCancelled,
    UsbPreparation,
)
from bc250cc.infrastructure.firmware.store import FirmwareStore
from bc250cc.shared.operation_contract import OperationCancelled
from frontends.tui.i18n import tr, tr_format
from frontends.web.actions import Invalid, choice, flag
from frontends.web.modulos import temporales

AVISO_CMOS = "After flashing, the board can show no picture until the CMOS is cleared: unplug it and take the coin battery out for a minute."
PASOS = {
    "download": "Download and verify the firmware", "logo": "Add your boot logo", "check": "Check the USB drive",
    "erase": "Erase the USB drive", "format": "Format it FAT32", "copy": "Copy the update kit", "verify": "Read back and verify every file",
}
PESOS = {"download": 45, "logo": 4, "check": 2, "erase": 5, "format": 5, "copy": 25, "verify": 18}
DESTRUCTIVOS = {"erase", "format", "copy", "verify"}


def servicio(ctx, nombre, fabrica):
    metodo = getattr(type(ctx.service), nombre, None)
    return metodo(ctx.service) if metodo else fabrica()


def snapshot(ctx):
    return servicio(ctx, "firmware_web", firmware_snapshot)


def almacen(ctx):
    return servicio(ctx, "almacen_firmware_web", FirmwareStore)


def identidad(unidad):
    return hashlib.sha256(json.dumps(unidad.identity, ensure_ascii=True).encode()).hexdigest()


def faltan(store, familia, imagen):
    pendientes = {}
    for fuente in sources_for(familia, imagen):
        if not store.is_cached(fuente):
            archivo = archives_of(fuente)
            pendientes[archivo.sha256] = archivo.size
    return sum(pendientes.values())


def catalogo(store):
    familias = []
    for familia in FIRMWARE_FAMILIES:
        imagenes = []
        for imagen in familia.images:
            cantidad = faltan(store, familia, imagen)
            disponible = store.can_unpack(imagen.rom)
            detalle = tr_format("{size} to download.", size=f"{cantidad / 1000 ** 2:.1f} MB") if cantidad else tr("Already downloaded")
            if not disponible:
                detalle = tr("Needs 7-Zip or bsdtar to unpack.")
            imagenes.append({"key": imagen.key, "label": imagen.label, "detail": detalle,
                "missing": cantidad, "available": disponible, "sha256": imagen.rom.sha256, "file": imagen.rom.name})
        familias.append({"key": familia.key, "title": familia.title, "version": familia.version,
            "origin": familia.origin, "summary": tr(familia.summary), "caution": tr(familia.caution),
            "recommended": familia.recommended, "default_image": familia.image().key,
            "variant_title": tr(familia.variant_title), "images": imagenes, "cores": familia.cpu_cores,
            "vram_menu": familia.vram_menu, "boot_logos": familia.boot_logos,
            "logo_replaceable": familia.logo_replaceable, "highlights": [tr(h) for h in familia.highlights],
            "download": tr_format("{size} to download.", size=f"{faltan(store, familia, familia.image()) / 1000 ** 2:.1f} MB")
            if faltan(store, familia, familia.image()) else tr("Already downloaded"),
            "project": familia.project, "project_url": familia.project_url})
    return familias


def leer(ctx, live):
    try:
        estado = snapshot(ctx)
        unidades = []
        for unidad in estado.drives:
            unidades.append({"id": identidad(unidad), "name": unidad.display_name, "path": unidad.path,
                "size_text": format_size(unidad.size), "labels": list(unidad.volume_labels),
                "eligible": unidad.eligible, "blocker": tr(unidad.blocker()), "warning": tr(unidad.warning())})
        return {"board": {**asdict(estado.board), "is_bc250": estado.board.is_bc250},
            "installed": asdict(estado.installed), "drives": unidades, "families": catalogo(almacen(ctx)),
            "default_family": DEFAULT_FAMILY.key, "steps": [{"key": k, "title": v} for k, v in PASOS.items()],
            "udisks": servicio(ctx, "udisks_firmware_web", udisks.available), "cmos_warning": tr(AVISO_CMOS),
            "logo_codec": lzma1.available()}
    except Exception as error:
        return {"error": str(error)}


def seleccion(p):
    clave = choice(p, "family", tuple(FAMILIES_BY_KEY))
    familia = FAMILIES_BY_KEY[clave]
    imagen = choice(p, "image", tuple(i.key for i in familia.images))
    return familia, familia.image(imagen)


def guardar_logo(ctx, p):
    """El logo que eligió la persona, ya convertido a JPEG por su navegador; vacío lo quita."""
    valor = p.get("logo")
    if set(p) != {"logo"} or not isinstance(valor, str) or len(valor) > MAX_LOGO_BYTES * 4 // 3 + 8:
        raise Invalid("logo")
    if not valor:
        temporales.borrar("logo")
        return
    try:
        datos = base64.b64decode(valor, validate=True)
        check_logo_jpeg(datos)
    except ValueError as error:
        raise Invalid(f"logo: {error}") from error
    temporales.guardar("logo", datos)


def logo(p, familia):
    if not flag(p, "logo"):
        return None
    if not familia.logo_replaceable:
        raise Invalid("This firmware cannot take a custom logo. The USB gets it as published.")
    try:
        datos = temporales.leer("logo")
        check_logo_jpeg(datos)
    except (OSError, ValueError) as error:
        raise Invalid("logo") from error
    return datos


def descargar(ctx, p, shell):
    if set(p) != {"family", "image"}:
        raise Invalid("params")
    familia, imagen = seleccion(p)
    def ejecutar():
        store = almacen(ctx)
        for fuente in sources_for(familia, imagen):
            store.ensure(fuente, progress=lambda recibido, total: print(f"{recibido}/{total}", flush=True))
        return tr("Already downloaded")
    return 1, ejecutar


def preparar(ctx, p, shell):
    if set(p) != {"family", "image", "drive", "logo"}:
        raise Invalid("params")
    familia, imagen = seleccion(p)
    dibujo = logo(p, familia)
    identificador = p.get("drive")
    if not isinstance(identificador, str) or len(identificador) != 64 or any(c not in "0123456789abcdef" for c in identificador):
        raise Invalid("drive")
    def ejecutar():
        estado = snapshot(ctx)
        unidad = next((u for u in estado.drives if identidad(u) == identificador), None)
        if unidad is None or not unidad.eligible:
            raise Invalid(unidad.blocker() if unidad else "The selected USB drive is no longer connected.")
        plan = plan_kit(familia, imagen, prepared=f"{datetime.now():%Y-%m-%d %H:%M}, BC250 Control Center", logo=dibujo)
        cancelado = threading.Event()
        paso_actual = [""]
        pasos = [p for p in PASOS if p != "logo" or dibujo is not None]
        total = sum(PESOS[p] for p in pasos)
        def interrumpir(signum, frame):
            if paso_actual[0] not in DESTRUCTIVOS:
                cancelado.set()
            else:
                print(tr("A USB drive is being written. Closing now would leave it unusable. Wait until it is ready; it takes about a minute."), flush=True)
        def progreso(paso, fraccion, detalle):
            paso_actual[0] = paso
            anteriores = pasos[:pasos.index(paso)]
            porcentaje = (sum(PESOS[p] for p in anteriores) + PESOS[paso] * fraccion) / total * 100
            print(f"{porcentaje:.1f}% · {tr(PASOS[paso])} · {detalle}", flush=True)
        previo = signal.signal(signal.SIGINT, interrumpir)
        try:
            metodo = getattr(type(ctx.service), "preparar_firmware_web", None)
            if metodo:
                informe = metodo(ctx.service, plan, unidad, progreso, cancelado.is_set)
            else:
                informe = UsbPreparation(almacen(ctx), udisks.UDisksClient()).run(plan, unidad, progress=progreso, cancelled=cancelado.is_set)
                record_prepared_kit(familia.key, familia.version, estado.board.version)
        except PreparationCancelled as error:
            raise OperationCancelled() from error
        finally:
            signal.signal(signal.SIGINT, previo)
        return f"{tr('Done')}: {informe.files} · {format_size(informe.bytes_written)}\n{tr(AVISO_CMOS)}"
    return 2, ejecutar


LECTURAS = {"firmware": (3, leer)}
ACCIONES = {"firmware.prepare": preparar, "firmware.download": descargar}
AJUSTES = {"firmware.logo": guardar_logo}
