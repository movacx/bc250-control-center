"""Lo que es demasiado grande para viajar por la consola de la sesión.

La consola recibe cada petición en una línea de terminal, que admite 4 KiB. Un logo o un reporte
se guarda primero aquí, en la carpeta de estado de la persona (solo ella la lee), y la acción lo abre.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

NOMBRES = {"logo": "logo.jpg", "report": "reporte.json"}


def _ruta(nombre: str) -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    carpeta = base / "bc250-control-center" / "web"
    carpeta.mkdir(parents=True, exist_ok=True, mode=0o700)
    return carpeta / NOMBRES[nombre]


def guardar(nombre: str, contenido: bytes) -> None:
    ruta = _ruta(nombre)
    nueva = ruta.with_name(ruta.name + ".nuevo")
    nueva.unlink(missing_ok=True)
    descriptor = os.open(nueva, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as archivo:
        archivo.write(contenido)
    nueva.replace(ruta)


def leer(nombre: str) -> bytes:
    ruta = _ruta(nombre)
    if ruta.is_symlink():
        raise OSError("link")
    return ruta.read_bytes()


def borrar(nombre: str) -> None:
    _ruta(nombre).unlink(missing_ok=True)


def guardar_json(nombre: str, datos: dict) -> None:
    guardar(nombre, json.dumps(datos, ensure_ascii=False).encode())


def leer_json(nombre: str) -> dict:
    return json.loads(leer(nombre).decode())
