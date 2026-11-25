#!/usr/bin/env python3
"""Copia la web compilada a frontends/web/dist: versión, textos por traducir y nada más."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
APP = RAIZ / "frontends/web/app"
COMPILADO = APP / "webApp/build/dist/wasmJs/productionExecutable"
DESTINO = RAIZ / "frontends/web/dist"
CADENA = r'"((?:[^"\\]|\\.)*)"'


def textos() -> list[str]:
    """Lo que se pide con t("…"), también partido en varias líneas, y los nombres de las secciones."""
    encontrados = set()
    # Lo que el servidor manda en inglés y la web traduce.
    servidor = [RAIZ / "frontends/web/data.py", RAIZ / "src/bc250cc/application/fan/board_view.py"]
    for archivo in [*sorted((APP / "shared/src").rglob("*.kt")), *servidor]:
        codigo = archivo.read_text(encoding="utf-8")
        for inicio in re.finditer(rf"{CADENA}(?:\s*\+\s*{CADENA})*", codigo):
            partes = re.findall(CADENA, inicio.group(0))
            encontrados.add("".join(partes).replace('\\"', '"').replace("\\n", "\n"))
    catalogo = json.loads((RAIZ / "frontends/desktop/i18n/locales/es.json").read_text(encoding="utf-8"))
    return sorted(texto for texto in encontrados if texto in catalogo)


def principal() -> None:
    if DESTINO.exists():
        shutil.rmtree(DESTINO)
    shutil.copytree(COMPILADO, DESTINO, ignore=shutil.ignore_patterns("*.map", "*.LICENSE.txt"))
    (DESTINO / "strings.json").write_text(json.dumps(textos(), ensure_ascii=False, indent=0), encoding="utf-8")
    suma = hashlib.sha256()
    for archivo in sorted(DESTINO.rglob("*")):
        if archivo.is_file() and archivo.name != "index.html":
            suma.update(archivo.read_bytes())
    version = suma.hexdigest()[:16]
    pagina = DESTINO / "index.html"
    texto = pagina.read_text(encoding="utf-8").replace("0" * 16, version)
    # El navegador los pide ya, sin esperar a que el programa diga que los necesita.
    previos = "".join(f'<link rel="preload" href="{archivo.name}" as="fetch" type="application/wasm" crossorigin="anonymous">\n    '
                      for archivo in sorted(DESTINO.glob("*.wasm")))
    texto = texto.replace("<!-- programa -->", previos.rstrip())
    pagina.write_text(texto, encoding="utf-8")
    (DESTINO / "version.json").write_text(json.dumps({"version": version}), encoding="utf-8")


if __name__ == "__main__":
    principal()
