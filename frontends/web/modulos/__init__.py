"""Lo que cada página de la web lee y puede hacer, un archivo por página.

Un módulo define las tablas que necesite:

- ``LECTURAS``: nombre -> ``(segundos, leer)``; ``leer(ctx, live)`` devuelve un diccionario. Se pide en ``/api/page``.
- ``CONSULTAS``: nombre -> ``consultar(web, parametros)``; una lectura con parámetros. Se pide en ``/api/query``.
- ``ACCIONES``: nombre -> ``construir(ctx, parametros, shell)``, que valida y devuelve ``(nivel, trabajo)`` como en
  ``actions.py``. Corre en la consola, con confirmación si el nivel no es 0.
- ``AJUSTES``: nombre -> ``guardar(ctx, parametros)``; una preferencia, sin consola ni privilegios.

Ninguno arma un comando con lo que llega del navegador: se valida y se llama al servicio de siempre.
"""

from __future__ import annotations

from importlib import import_module

MODULOS = ("panel", "rendimiento", "gpu", "unidades", "ventiladores", "procesos", "caja_negra", "ajustes_adicionales",
           "acceso_remoto", "firmware", "configuracion", "soporte")


def _juntar(tabla: str) -> dict:
    juntas: dict = {}
    for nombre in MODULOS:
        try:
            modulo = import_module(f"{__name__}.{nombre}")
        except ModuleNotFoundError as error:
            if error.name != f"{__name__}.{nombre}":
                raise
            continue  # la página todavía no está escrita
        juntas.update(getattr(modulo, tabla, {}))
    return juntas


LECTURAS, CONSULTAS = _juntar("LECTURAS"), _juntar("CONSULTAS")
ACCIONES, AJUSTES = _juntar("ACCIONES"), _juntar("AJUSTES")
