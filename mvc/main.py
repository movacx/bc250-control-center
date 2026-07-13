import os
import sys
from PyQt6.QtWidgets import QApplication

raiz = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if raiz not in sys.path:
    sys.path.insert(0, raiz)

from mvc.Controller.controlador import Controlador
from mvc.Repository.sistema_repository import SistemaRepository
from mvc.service.sistema_service import SistemaService
from mvc.View.vista import Vista


def main():
    repo = SistemaRepository()
    servicio = SistemaService(repo)
    controlador = Controlador(servicio)

    app = QApplication(sys.argv)
    ventana = Vista(controlador)
    ventana.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
