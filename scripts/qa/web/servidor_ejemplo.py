#!/usr/bin/env python3
"""La web de verdad con un servicio de ejemplo, para verla y probarla sin tocar el equipo.

Solo atiende en este equipo (127.0.0.1), con la sesión ya abierta y la configuración en una carpeta temporal.
Uso: bwrap --dev-bind / / --tmpfs /sys --chdir $PWD python scripts/qa/web/servidor_ejemplo.py [puerto]
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
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


class TerminalConClave(TerminalEjemplo):
    """Pide una contraseña como sudo: «mala» no vale y cualquier otra sí. Nada se ejecuta."""

    AVISO = "BC250 Linux password: "

    def request(self, operacion, **valores):
        ahora = time.monotonic()
        if operacion == "action":
            super().request(operacion, **valores)
            self.trabajo.update(done=False, ok=None, text=self.AVISO, waiting=True, interactive=True)
            self.desde, self.valida = None, False
            return {"ok": True, "job": self.trabajo["id"]}
        if operacion == "input":
            self.desde, self.valida = ahora, valores["text"] != "mala"
            self.trabajo.update(text=self.AVISO + "\n")  # como sudo: hasta que conteste parece que sigue esperando
            return {"ok": True}
        if operacion == "interrupt":
            self.trabajo.update(done=True, ok=False, cancelled=True, waiting=False, interactive=False)
            return {"ok": True}
        desde = getattr(self, "desde", None)
        if desde and not self.trabajo.get("done") and ahora - desde > (0.4 if self.valida else 1.5):
            if not self.valida:
                self.trabajo.update(waiting=True, interactive=True, text=f"{self.AVISO}\nSorry, try again.\n{self.AVISO}")
                self.desde = None
            else:
                self.trabajo.update(waiting=False, interactive=False, text=self.AVISO + "\nAplicando…")
                if ahora - desde > 2:
                    self.trabajo.update(done=True, ok=True, text=self.AVISO + "\nListo.")
        return self.trabajo


class WebEjemplo(web_server.Web):
    def session(self, _token):
        return "sello-de-ejemplo"


def nunca_se_envia(*_a, **_k):
    raise RuntimeError("ejemplo: un reporte nunca sale de aquí")


def principal() -> int:
    puerto = int(sys.argv[1]) if len(sys.argv) > 1 else 8399
    from bc250cc.infrastructure import problem_report

    problem_report.submit = nunca_se_envia
    contenedor = SimpleNamespace(system_service=ServicioEjemplo(), settings_service=ConfiguracionEjemplo(),
                                 activity_service=ActividadEjemplo(), platform=None)
    con_clave = "--clave" in sys.argv  # para probar el emparejamiento de verdad
    if not con_clave:
        web_server.web_devices.session = lambda _ficha: {"control": True, "id": "ejemplo"}
    clase = web_server.Web if con_clave else WebEjemplo
    web = clase(contenedor, terminal_factory=TerminalConClave if "--pide" in sys.argv else TerminalEjemplo)
    web_server.set_language(web.language)
    certificado = None
    if "--https" in sys.argv:  # para probar la aplicación del teléfono
        from bc250cc.infrastructure import web_tls

        certificado = web_tls.certificate()
        print(web_tls.fingerprint(web_tls.trust_certificate()), flush=True)
    servidor = web_server.Server(("127.0.0.1", puerto), web, certificate=certificado)
    print(f"{'https' if certificado else 'http'}://127.0.0.1:{puerto}", flush=True)
    if con_clave:
        from bc250cc.application.system import web_access, web_pairing

        print(web_access.pairing_link(f"https://10.0.2.2:{puerto}", web_pairing.issue()), flush=True)
    servidor.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
