from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QTableWidget, QVBoxLayout, QWidget
)


class HistorialFrame:
    def __init__(self, vista):
        self.vista = vista
        self.contenedor = self._forms()

    def _forms(self):
        v = self.vista
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        top = v.titulo_pagina('Historial', 'Eventos, alertas y acciones importantes de la placa y del sistema.')
        layout.addLayout(top)

        barra = QFrame()
        barra.setObjectName('CommandBar')
        bl = QHBoxLayout(barra)
        bl.setContentsMargins(10, 6, 10, 6)
        bl.setSpacing(8)
        estado = QLabel('Registro local JSONL')
        estado.setObjectName('Muted')
        v.historial_estado = estado
        actualizar = QPushButton('Actualizar')
        actualizar.clicked.connect(v.actualizar_historial)
        limpiar = QPushButton('Limpiar historial')
        limpiar.setObjectName('DangerButton')
        limpiar.clicked.connect(v.limpiar_historial)
        bl.addWidget(estado)
        bl.addStretch(1)
        bl.addWidget(actualizar)
        bl.addWidget(limpiar)
        layout.addWidget(barra)

        tabla = QTableWidget(0, 6)
        v.tabla_historial = tabla
        v.configurar_tabla(tabla)
        tabla.setHorizontalHeaderLabels([v.t('Fecha'), v.t('Tipo'), v.t('Nivel'), v.t('Titulo'), v.t('Detalle'), v.t('Datos')])
        tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        tabla.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        tabla.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        tabla.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        tabla.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        tabla.verticalHeader().setDefaultSectionSize(30)
        layout.addWidget(tabla, 1)
        return page
