#!/usr/bin/env python3
"""Recorta las letras de chino, japonés, coreano y tailandés a los caracteres que usan las traducciones.

La web lleva Noto Sans dentro, que no tiene esos alfabetos. Cada archivo se descarga solo con su idioma.
Necesita fonttools y las letras Noto (licencia OFL) del sistema: noto-fonts y noto-fonts-cjk.
"""

from __future__ import annotations

import json
import string
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

RAIZ = Path(__file__).resolve().parents[2]
TEXTOS = RAIZ / "frontends/desktop/i18n/locales"
DESTINO = RAIZ / "frontends/web/app/shared/src/commonMain/composeResources/font"
CJK = Path("/usr/share/fonts/noto-cjk/NotoSansCJK-Medium.ttc")
TAILANDES = Path("/usr/share/fonts/noto/NotoSansThai-Medium.ttf")
#: idioma -> (archivo de salida, letra, número dentro de la colección)
IDIOMAS = {
    "ja": ("letra_ja", CJK, 0), "ko": ("letra_ko", CJK, 1), "zh-CN": ("letra_zh_cn", CJK, 2),
    "zh-TW": ("letra_zh_tw", CJK, 3), "th": ("letra_th", TAILANDES, -1),
}
#: Algunos signos se forman uniendo otros que no aparecen en los textos: el alfabeto va entero.
ENTEROS = {"th": range(0x0E01, 0x0E5C), "ja": range(0x3040, 0x3100)}
#: Los nombres de los idiomas se ven siempre, en el selector.
NOMBRES = "简体中文繁體中文日本語한국어"


def caracteres(idioma: str) -> set[str]:
    textos = json.loads((TEXTOS / f"{idioma}.json").read_text(encoding="utf-8"))
    return {letra for valor in textos.values() for letra in str(valor)}


def recortar(origen: Path, numero: int, letras: set[str], destino: Path) -> None:
    letra = TTFont(origen, fontNumber=numero) if numero >= 0 else TTFont(origen)
    opciones = subset.Options()
    opciones.layout_features = ["*"] if numero < 0 else ["kern", "palt"]
    opciones.hinting = False
    opciones.desubroutinize = True
    recorte = subset.Subsetter(opciones)
    recorte.populate(unicodes=[ord(letra_suelta) for letra_suelta in letras])
    recorte.subset(letra)
    letra.save(destino)
    print(destino.name, destino.stat().st_size // 1024, "KB", len(letras), "caracteres")


def principal() -> None:
    ya_incluidos = set(string.printable)
    for idioma, (nombre, origen, numero) in IDIOMAS.items():
        recortar(origen, numero, caracteres(idioma) - ya_incluidos | {chr(codigo) for codigo in ENTEROS.get(idioma, ())}, DESTINO / f"{nombre}.otf")
    recortar(CJK, 2, set(NOMBRES), DESTINO / "letra_nombres.otf")


if __name__ == "__main__":
    principal()
