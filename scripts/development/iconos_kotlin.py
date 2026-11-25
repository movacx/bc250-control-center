#!/usr/bin/env python3
"""Pasa los iconos SVG del escritorio a vectores de Compose (los que entiende Android también)."""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
ORIGEN = RAIZ / "frontends/desktop/theme/icons"
DESTINO = RAIZ / "frontends/web/app/shared/src/commonMain/composeResources/drawable"
HEREDADOS = ("fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "opacity")


def trazo(nodo, etiqueta: str) -> str:
    """La forma como una ruta: los vectores de Android solo conocen rutas."""
    def n(nombre, defecto=0.0):
        return float(nodo.get(nombre, defecto))

    if etiqueta == "path":
        return nodo.get("d", "")
    if etiqueta == "circle":
        x, y, r = n("cx"), n("cy"), n("r")
        return f"M{x - r},{y}a{r},{r} 0 1,0 {2 * r},0a{r},{r} 0 1,0 {-2 * r},0z"
    if etiqueta == "ellipse":
        x, y, a, b = n("cx"), n("cy"), n("rx"), n("ry")
        return f"M{x - a},{y}a{a},{b} 0 1,0 {2 * a},0a{a},{b} 0 1,0 {-2 * a},0z"
    if etiqueta == "line":
        return f"M{n('x1')},{n('y1')}L{n('x2')},{n('y2')}"
    if etiqueta in ("polyline", "polygon"):
        return "M" + " L".join(nodo.get("points", "").split()) + ("z" if etiqueta == "polygon" else "")
    if etiqueta == "rect":
        x, y, w, h = n("x"), n("y"), n("width"), n("height")
        r = min(n("rx", nodo.get("ry", 0)), w / 2, h / 2)
        if not r:
            return f"M{x},{y}h{w}v{h}h{-w}z"
        return (f"M{x + r},{y}h{w - 2 * r}a{r},{r} 0 0,1 {r},{r}v{h - 2 * r}a{r},{r} 0 0,1 {-r},{r}"
                f"h{-(w - 2 * r)}a{r},{r} 0 0,1 {-r},{-r}v{-(h - 2 * r)}a{r},{r} 0 0,1 {r},{-r}z")
    return ""


def color(valor: str) -> str:
    if valor in ("", "none"):
        return ""
    valor = {"white": "#FFFFFF", "black": "#000000", "currentColor": "#64748B"}.get(valor, valor)
    if len(valor) == 4:
        valor = "#" + "".join(c * 2 for c in valor[1:])
    return valor if valor.startswith("#") else ""


def convertir(archivo: Path) -> str | None:
    raiz = ET.parse(archivo).getroot()
    caja = [float(v) for v in raiz.get("viewBox", f"0 0 {raiz.get('width', 24)} {raiz.get('height', 24)}").replace(",", " ").split()]
    lineas = []

    def recorrer(nodo, estilo):
        estilo = {**estilo, **{k: nodo.get(k) for k in HEREDADOS if nodo.get(k) is not None}}
        etiqueta = nodo.tag.split("}")[-1]
        if etiqueta in ("text", "defs", "linearGradient", "style", "use"):
            raise ValueError(etiqueta)
        giro = re.fullmatch(r"rotate\(([-\d.]+)[ ,]+([-\d.]+)[ ,]+([-\d.]+)\)", nodo.get("transform", ""))
        if nodo.get("transform") and not giro:
            raise ValueError("transform")
        if giro:
            lineas.append(f'    <group android:rotation="{giro[1]}" android:pivotX="{giro[2]}" android:pivotY="{giro[3]}">')
        ruta = trazo(nodo, etiqueta)
        if ruta:
            partes = [f'android:pathData="{" ".join(ruta.split())}"']
            relleno, linea = color(estilo.get("fill", "#000000")), color(estilo.get("stroke", ""))
            alfa = estilo.get("opacity")
            if relleno:
                partes.append(f'android:fillColor="{relleno}"')
                if alfa:
                    partes.append(f'android:fillAlpha="{alfa}"')
            if linea:
                partes += [f'android:strokeColor="{linea}"', f'android:strokeWidth="{estilo.get("stroke-width", 1)}"',
                           f'android:strokeLineCap="{estilo.get("stroke-linecap", "butt")}"',
                           f'android:strokeLineJoin="{estilo.get("stroke-linejoin", "miter")}"']
                if alfa:
                    partes.append(f'android:strokeAlpha="{alfa}"')
            if relleno or linea:
                lineas.append("    <path " + " ".join(partes) + "/>")
        for hijo in nodo:
            recorrer(hijo, estilo)
        if giro:
            lineas.append("    </group>")

    recorrer(raiz, {})
    return (f'<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="{caja[2]:g}dp" '
            f'android:height="{caja[3]:g}dp" android:viewportWidth="{caja[2]:g}" android:viewportHeight="{caja[3]:g}">\n'
            + "\n".join(lineas) + "\n</vector>\n")


def principal() -> int:
    DESTINO.mkdir(parents=True, exist_ok=True)
    omitidos = []
    for archivo in sorted(ORIGEN.glob("*.svg")):
        try:
            texto = convertir(archivo)
        except ValueError as motivo:
            omitidos.append(f"{archivo.stem} ({motivo})")
            continue
        (DESTINO / f"{archivo.stem.replace('-', '_')}.xml").write_text(texto, encoding="utf-8")
    print("omitidos:", ", ".join(omitidos) or "ninguno")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
