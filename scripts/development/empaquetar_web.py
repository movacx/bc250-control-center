#!/usr/bin/env python3
"""Empaqueta la web compilada y anota cuál es en frontends/web/web-build.json. No publica nada.

El archivo se sube después, a mano, a la versión «web-builds» de GitHub, y la anotación se guarda en git:
así cada copia del repositorio sabe qué web le corresponde y con qué huella.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
WEB = RAIZ / "frontends/web"
DESCARGA = "https://github.com/movacx/bc250-control-center/releases/download/web-builds/"


def empaquetar(dist: Path) -> bytes:
    """El mismo contenido da siempre los mismos bytes."""
    salida = io.BytesIO()
    with gzip.GzipFile(fileobj=salida, mode="wb", mtime=0) as comprimido, tarfile.open(fileobj=comprimido, mode="w") as archivo:
        for ruta in sorted(dist.rglob("*")):
            if not ruta.is_file() or ruta.name == ".web-build":
                continue
            dato = tarfile.TarInfo(ruta.relative_to(dist).as_posix())
            dato.size, dato.mode = ruta.stat().st_size, 0o644
            with ruta.open("rb") as contenido:
                archivo.addfile(dato, contenido)
    return salida.getvalue()


def principal() -> int:
    dist = WEB / "dist"
    if not (dist / "webApp.js").is_file():
        print("Primero: scripts/development/build-web.sh", file=sys.stderr)
        return 1
    datos = empaquetar(dist)
    version = json.loads((dist / "version.json").read_text(encoding="utf-8"))["version"]
    nombre = f"bc250-web-{version}.tar.gz"
    destino = RAIZ / "dist" / nombre
    destino.parent.mkdir(exist_ok=True)
    destino.write_bytes(datos)
    anotacion = {"url": DESCARGA + nombre, "sha256": hashlib.sha256(datos).hexdigest()}
    (WEB / "web-build.json").write_text(json.dumps(anotacion, indent=2) + "\n", encoding="utf-8")
    print(f"{destino}\n{anotacion['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
