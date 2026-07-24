from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)

from mvc.View.Componentes.componentes import MetricStrip


class MemoriaFrame:
    def __init__(self, vista):
        self.vista = vista
        self.contenedor = self._forms()

    def _forms(self):
        v = self.vista
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addLayout(v.titulo_pagina('Memoria', 'Linux usa cache; se prioriza memoria disponible, swap y procesos recuperables.'))
        grid = QGridLayout()
        grid.setSpacing(8)
        v.mem_disponible = MetricStrip('Disponible', '#16a34a')
        v.mem_usada = MetricStrip('RAM usada', '#2563eb')
        v.mem_swap = MetricStrip('Swap / zram', '#d97706')
        v.mem_disco = MetricStrip('Disco sistema', '#7c3aed')
        for idx, w in enumerate([v.mem_disponible, v.mem_usada, v.mem_swap, v.mem_disco]):
            grid.addWidget(w, idx // 2, idx % 2)
        layout.addLayout(grid)
        box = QFrame()
        box.setObjectName('InfoBox')
        bx = QVBoxLayout(box)
        bx.setContentsMargins(14, 12, 14, 12)
        t = QLabel('Acciones recomendadas')
        t.setObjectName('SectionTitle')
        d = QLabel('Primero cierra apps pesadas desde Procesos. Usa liberar cache solo como accion avanzada.')
        d.setObjectName('Muted')
        d.setWordWrap(True)
        btn = QPushButton('Liberar cache con aviso')
        btn.clicked.connect(v.limpiar_cache)
        bx.addWidget(t)
        bx.addWidget(d)
        bx.addWidget(btn, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(box)
        layout.addStretch(1)
        return page

