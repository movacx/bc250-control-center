"""Prepara la web desde una terminal, sin el escritorio: ``bc250-control-center web setup``.

Hace lo mismo que «Prepare the connection»: red local con HTTPS, servidor, firewall y
dirección local, solo lo que falte. Al final muestra la dirección, la clave y un código QR.
"""

from __future__ import annotations

import os
import sys

from bc250cc.application.system import web_access, web_pairing, web_setup
from bc250cc.application.system.workflow_console import TERMINAL_AUTH_ENV
from bc250cc.shared.errors import BoundaryError
from frontends.desktop.i18n import normalize_language, set_language, tr
from frontends.tui.runtime import describe_error


def dibujar_qr(matriz: list[list[bool]]) -> str:
    """El código con medios bloques: dos filas por renglón y un margen en blanco."""
    margen = 2
    ancho = len(matriz) + 2 * margen
    blanca = [False] * ancho
    filas = [blanca] * margen
    for fila in matriz:
        filas.append([False] * margen + list(fila) + [False] * margen)
    filas += [blanca] * margen
    if len(filas) % 2:
        filas.append(blanca)
    renglones = []
    for arriba, abajo in zip(filas[::2], filas[1::2]):
        letras = []
        for oscuro_arriba, oscuro_abajo in zip(arriba, abajo):
            if oscuro_arriba and oscuro_abajo:
                letras.append(" ")
            elif oscuro_arriba:
                letras.append("▄")
            elif oscuro_abajo:
                letras.append("▀")
            else:
                letras.append("█")
        renglones.append("".join(letras))
    return "\n".join(renglones)


def mostrar_acceso(estado: dict) -> None:
    direcciones = estado.get("urls") or [estado.get("local_url", "")]
    print()
    for direccion in direcciones:
        print("  " + direccion)
    print(f"  {tr('Access key')}: {estado.get('key', '')}")
    if estado.get("urls") and sys.stdout.isatty():
        ficha = web_pairing.issue()
        enlace = web_access.pairing_link(direcciones[0], ficha)
        print()
        print(dibujar_qr(web_access.pairing_matrix(enlace)))
        print(tr("Scan to pair. The code works once and renews by itself."))


def preparar(arranque: bool) -> int:
    os.environ.setdefault(TERMINAL_AUTH_ENV, "1")

    def decir(paso: str) -> None:
        print(f"· {tr(web_setup.LABELS[paso])}", flush=True)

    try:
        estado = web_setup.apply(decir)
        if arranque:
            web_access.set_autostart(True)
    except BoundaryError as error:
        print(tr(error.detail.message), file=sys.stderr)
        return 1
    except Exception as error:  # noqa: BLE001 - se explica en una frase
        print(describe_error(error), file=sys.stderr)
        return 1
    mostrar_acceso(estado)
    return 0


def main(orden: str, opciones: list[str]) -> int:
    set_language(normalize_language(os.environ.get("LANG", "en").split(".")[0].replace("_", "-")))
    if orden == "setup":
        return preparar(arranque="--no-autostart" not in opciones)
    if orden == "status":
        estado = web_access.status()
        print(tr("Running") if estado.get("running") else tr("Stopped"))
        if estado.get("running"):
            mostrar_acceso(estado)
        return 0
    web_access.stop()
    print(tr("Stopped"))
    return 0
