#!/usr/bin/env python3
"""La web de verdad con un servicio de ejemplo, para verla y probarla sin tocar el equipo.

Solo atiende en este equipo (127.0.0.1), con la sesión ya abierta y la configuración en una carpeta temporal.
Uso: bwrap --dev-bind / / --tmpfs /sys --chdir $PWD python scripts/qa/web/servidor_ejemplo.py [puerto]
"""

from __future__ import annotations

import os
import sys
import tempfile
from types import SimpleNamespace

CARPETA = tempfile.mkdtemp(prefix="bc250-web-ejemplo-")
for variable in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "HOME"):
    os.environ[variable] = CARPETA

from servicio_ejemplo import (  # noqa: E402
    ActividadEjemplo,
    ConfiguracionEjemplo,
    ServicioEjemplo,
)

from frontends.web import server as web_server  # noqa: E402


class TerminalEjemplo:
    """Anota la operación que se pidió, como si la consola ya la hubiera terminado."""

    ready, closed = True, False

    def __init__(self, **_kw):
        self.trabajo = {"id": 0}

    def request(self, operacion, **valores):
        if operacion == "action":
            texto = f"$ {valores['action']} {valores['params']}\nEjemplo: no se tocó el equipo."
            self.trabajo = {"id": self.trabajo["id"] + 1, "label": valores["title"], "done": True, "ok": True, "text": texto}
            return {"ok": True, "job": self.trabajo["id"]}
        return self.trabajo if operacion == "job" else {"ok": True}

    def view(self):
        return self.trabajo

    def close(self):
        self.closed = True


class WebEjemplo(web_server.Web):
    def session(self, _token):
        return "sello-de-ejemplo"


def principal() -> int:
    puerto = int(sys.argv[1]) if len(sys.argv) > 1 else 8399
    contenedor = SimpleNamespace(system_service=ServicioEjemplo(), settings_service=ConfiguracionEjemplo(),
                                 activity_service=ActividadEjemplo(), platform=None)
    web_server.web_devices.session = lambda _ficha: {"control": True, "id": "ejemplo"}
    web = WebEjemplo(contenedor, terminal_factory=TerminalEjemplo)
    servidor = web_server.Server(("127.0.0.1", puerto), web)
    print(f"http://127.0.0.1:{puerto}", flush=True)
    servidor.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
