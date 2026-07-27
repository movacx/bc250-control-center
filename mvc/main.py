from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from mvc.Controller.controlador import Controlador
from mvc.logging_config import configure_logging
from mvc.Repository.sistema_repository import SistemaRepository
from mvc.View import ControlCenterWindow
from mvc.service.sistema_service import SistemaService


def build_controller() -> Controlador:
    return Controlador(SistemaService(SistemaRepository()))


def main() -> int:
    configure_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("BC250 Control Center")
    app.setApplicationDisplayName("BC250 Control Center")
    app.setDesktopFileName("io.github.movacx.bc250-control-center")
    window = ControlCenterWindow(build_controller())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
