#!/usr/bin/env python3
"""Dibuja cada página del escritorio con datos de ejemplo y anota la medida de cada pieza.

Es la referencia de la web: para cada página deja ``pagina.png`` y ``pagina.json``
(posición, tamaño, texto, letra y colores de cada pieza visible).

Uso, siempre con /sys oculto:
    bwrap --dev-bind / / --tmpfs /sys --chdir $PWD python scripts/qa/web/referencia_escritorio.py SALIDA [página…]
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = f"offscreen:configfile={Path(__file__).with_name('pantalla.json')}"
from servicio_ejemplo import (  # noqa: E402
    ActividadEjemplo,
    ConfiguracionEjemplo,
    ServicioEjemplo,
)

ANCHO = 1920
ALTO = int(os.environ.get("BC250_REF_ALTO", 1000))


def medidas(ventana) -> list[dict]:
    """Las piezas visibles, de arriba abajo, con su nombre de estilo."""
    from PyQt6.QtCore import QPoint
    from PyQt6.QtWidgets import QWidget

    salida = []
    for pieza in ventana.findChildren(QWidget):
        if not pieza.isVisible() or pieza.width() <= 0 or pieza.height() <= 0:
            continue
        punto = pieza.mapTo(ventana, QPoint(0, 0))
        dato = {"clase": type(pieza).__name__, "nombre": pieza.objectName(), "x": punto.x(), "y": punto.y(),
                "ancho": pieza.width(), "alto": pieza.height()}
        for lector in ("text", "title", "placeholderText"):
            if hasattr(pieza, lector):
                try:
                    valor = getattr(pieza, lector)()
                except TypeError:
                    continue
                if isinstance(valor, str) and valor:
                    dato["texto"] = valor
                    letra = pieza.font()
                    dato["letra"] = [pieza.fontInfo().pixelSize(), int(letra.weight())]
                    dato["color"] = pieza.palette().windowText().color().name()
                    break
        padre = pieza.parentWidget()
        dato["padre"] = padre.objectName() if padre else ""
        salida.append(dato)
    return salida


def guardar_ajustes(escritorio, ventana, QDialog, esperar, guardar) -> None:
    """Configuración, sección por sección."""
    from frontends.desktop.pages.settings import SettingsDialog

    dialogo = SettingsDialog(ventana.controller, settings_service=ventana.settings_service,
                             activity_service=ventana.activity_service, app_settings=ventana.settings, parent=ventana)
    dialogo.fit_to_content = lambda *_a, **_k: None
    dialogo.setVisible(True)
    dialogo.setFixedSize(1216, 816)
    esperar(1)
    pagina = dialogo.page
    for seccion in (*pagina.section_order, *pagina.SUBPAGES):
        try:
            pagina.select_section(seccion)
        except Exception as error:  # noqa: BLE001 - una sección que pide datos no impide las demás
            print("  sin", seccion, error, flush=True)
            continue
        esperar(2)
        guardar(f"settings__{seccion}", dialogo)


def principal() -> int:
    destino = Path(sys.argv[1]).resolve()
    destino.mkdir(parents=True, exist_ok=True)
    pedidas = sys.argv[2:]
    with tempfile.TemporaryDirectory(prefix="bc250-referencia-") as carpeta:
        for variable in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "HOME"):
            os.environ[variable] = carpeta
        from PyQt6.QtCore import QThreadPool
        from PyQt6.QtGui import QFont
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import QAbstractButton, QApplication, QDialog

        from frontends.desktop import app as escritorio
        from frontends.desktop.core import preferences
        from frontends.desktop.i18n import tr
        from frontends.desktop.onboarding import mark_first_run_done

        aplicacion = QApplication([sys.argv[0]])
        letra = QFont("Noto Sans")
        letra.setPixelSize(13)  # la de un escritorio normal: 10 puntos a 96 ppp
        aplicacion.setFont(letra)
        preferences._migrate_legacy_qt_settings = lambda _destino: None
        ajustes = preferences.application_settings()
        for clave, valor in {"settings/language": os.environ.get("BC250_REF_IDIOMA", "es"), "settings/appearance": os.environ.get("BC250_REF_TEMA", "dark"),
                             "settings/accent": "green",
                             "settings/gpu_interface": os.environ.get("BC250_REF_GPU", "modern"), "settings/density": "comfortable",
                             "settings/style": "formal"}.items():
            ajustes.setValue(clave, valor)
        mark_first_run_done(ajustes)
        # Un aviso encima taparía la página: se anota y no se abre.
        def sin_dialogo(dialogo, *_a):
            print("  dialogo:", type(dialogo).__name__, dialogo.windowTitle(), flush=True)
            return 0
        for nombre in ("exec", "open", "show"):
            setattr(QDialog, nombre, sin_dialogo)
        escritorio.ControlCenterWindow.start_tour = lambda *_a, **_k: None
        for tour in (nombre for nombre in dir(escritorio.ControlCenterWindow) if "tour" in nombre and "start" in nombre):
            setattr(escritorio.ControlCenterWindow, tour, lambda *_a, **_k: None)
        from frontends.desktop.components import toast
        for nombre in [n for n in dir(toast) if n.startswith("Toast") or n == "show_toast"]:
            pieza = getattr(toast, nombre)
            if hasattr(pieza, "show"):
                pieza.show = lambda *_a, **_k: None
        escritorio.TourGuide.start = lambda _guia: None
        ventana = escritorio.ControlCenterWindow(ServicioEjemplo(), settings_service=ConfiguracionEjemplo(),
                                                 activity_service=ActividadEjemplo())
        ventana.remote_page.set_updates_active = lambda _activo: None
        ventana.resize(ANCHO, ALTO)
        ventana.show()
        def esperar(veces=5):
            for _ in range(veces):
                QTest.qWait(300)
                QThreadPool.globalInstance().waitForDone(200)

        def guardar(nombre, pieza=ventana):
            pieza.grab().save(str(destino / f"{nombre}.png"))
            (destino / f"{nombre}.json").write_text(json.dumps(medidas(pieza), ensure_ascii=False, indent=0))
            print(nombre, flush=True)

        if pedidas == ["bienvenida"]:
            ventana.open_welcome()
            esperar(2)
            for paso in range(ventana.welcome.STEP_COUNT):
                ventana.welcome._reach(paso)
                esperar(2)
                guardar(f"bienvenida__{paso + 1}")
            os._exit(0)

        from frontends.desktop.core.performance_model import RESOURCE_DEFINITIONS

        for clave in pedidas or [*ventana.pages, "settings"]:
            if clave == "settings":
                guardar_ajustes(escritorio, ventana, QDialog, esperar, guardar)
                continue
            ventana.navigate(clave)
            esperar()
            guardar(clave)
            pestanas = []
            if clave == "extras":
                pestanas = list(ventana.extras_page.panel.tab_buttons)
            elif clave == "performance":
                pestanas = [boton for boton in ventana.performance_page.findChildren(QAbstractButton)
                            if boton.text() in {tr(item.title) for item in RESOURCE_DEFINITIONS}]
            for numero, boton in enumerate(pestanas):
                if boton.isVisible():
                    boton.click()
                    esperar(3)
                    guardar(f"{clave}__{numero}")
        aplicacion.processEvents()
        os._exit(0)


if __name__ == "__main__":
    raise SystemExit(principal())
