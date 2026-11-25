#!/usr/bin/env python3
"""Fotografía una página de la web de ejemplo y la pone junto a la del escritorio.

Uso: python scripts/qa/web/captura.py REFERENCIA SALIDA página [página…]   (con servidor_ejemplo.py encendido)
Deja ``web_página.png`` y ``dif_página.png``: escritorio, web y diferencia, una debajo de otra.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

DIRECCION = os.environ.get("BC250_WEB", "http://127.0.0.1:8399")
ANCHO, ALTO = (int(v) for v in os.environ.get("BC250_TAMANO", "1920x1000").split("x"))


def principal() -> int:
    referencia, salida, paginas = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
    with sync_playwright() as motor:
        navegador = motor.chromium.launch(executable_path="/usr/bin/chromium", args=["--use-gl=angle", "--use-angle=swiftshader"])
        for pagina in paginas:
            hoja = navegador.new_page(viewport={"width": ANCHO, "height": ALTO})
            hoja.on("console", lambda m: print("  consola:", m.text[:300]) if m.type == "error" else None)
            hoja.on("pageerror", lambda e: print("  error:", str(e)[:400]))
            hoja.goto(f"{DIRECCION}/#{pagina}")
            time.sleep(float(os.environ.get("BC250_ESPERA", 7)))
            foto = salida / f"web_{pagina}.png"
            hoja.screenshot(path=str(foto))
            hoja.close()
            original = referencia / f"{pagina}.png"
            if original.exists() and (ANCHO, ALTO) == Image.open(original).size:
                a, b = Image.open(original).convert("RGB"), Image.open(foto).convert("RGB")
                resta = ImageChops.difference(a, b).point(lambda v: min(255, v * 3))
                distintos = sum(1 for p in resta.convert("L").resize((480, 250)).getdata() if p > 60) / (480 * 250)
                junta = Image.new("RGB", (ANCHO, ALTO * 3))
                for lugar, imagen in enumerate((a, b, resta)):
                    junta.paste(imagen, (0, ALTO * lugar))
                junta.save(salida / f"dif_{pagina}.png")
                print(f"{pagina}: {distintos:.2%} distinto")
        navegador.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
