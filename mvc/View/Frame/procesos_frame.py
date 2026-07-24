from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPushButton, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)

from mvc.View.Componentes.componentes import MetricStrip


class ProcesosFrame:
    def __init__(self, vista):
        self.vista = vista
        self.contenedor = self._forms()

    def _forms(self):
        v = self.vista
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        top = v.titulo_pagina('Procesos', 'Vista compacta: procesos agrupados, busqueda rapida y acciones seguras.')
        v.pill_estado = QLabel('--')
        v.pill_estado.setObjectName('InfoPill')
        v.pill_estado.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.pill_estado.setMinimumWidth(0)
        v.pill_estado.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        top.addWidget(v.pill_estado)
        layout.addLayout(top)

        metricas = QGridLayout()
        metricas.setSpacing(6)
        v.m_cpu = MetricStrip('CPU', '#2563eb')
        v.m_ram = MetricStrip('Memoria', '#16a34a')
        v.m_swap = MetricStrip('Swap/zram', '#d97706')
        v.m_disco = MetricStrip('Disco', '#7c3aed')
        for i, w in enumerate([v.m_cpu, v.m_ram, v.m_swap, v.m_disco]):
            w.spark.setVisible(False)
            w.setMaximumHeight(58)
            w.setMinimumWidth(0)
            w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            metricas.addWidget(w, 0, i)
        layout.addLayout(metricas)

        barra = QFrame()
        barra.setObjectName('CommandBar')
        b = QHBoxLayout(barra)
        b.setContentsMargins(8, 5, 8, 5)
        b.setSpacing(6)
        v.busqueda = QLineEdit()
        v.busqueda.setObjectName('Search')
        v.busqueda.setPlaceholderText('Buscar proceso, PID o comando')
        v.busqueda.setMinimumWidth(110)
        v.busqueda.textChanged.connect(v.refrescar_tabla)
        v.check_sistema = QCheckBox('Ocultar sistema')
        v.check_sistema.setChecked(True)
        v.check_sistema.stateChanged.connect(v.actualizar_procesos)
        v.check_agrupar = QCheckBox('Agrupar apps')
        v.check_agrupar.setChecked(True)
        v.check_agrupar.stateChanged.connect(v.refrescar_tabla)
        v.btn_actualizar = QPushButton('Actualizar')
        v.btn_actualizar.setToolTip('Actualizar lista de procesos')
        v.btn_actualizar.clicked.connect(v.actualizar_procesos)
        v.btn_seleccionar = QPushButton('Seguras')
        v.btn_seleccionar.setToolTip('Seleccionar apps seguras')
        v.btn_seleccionar.clicked.connect(lambda: v.set_checks(True))
        v.btn_limpiar = QPushButton('Limpiar')
        v.btn_limpiar.setToolTip('Quitar seleccion')
        v.btn_limpiar.clicked.connect(lambda: v.set_checks(False))
        v.btn_cerrar = QPushButton('Finalizar')
        v.btn_cerrar.setToolTip('Finalizar tarea seleccionada')
        v.btn_cerrar.setObjectName('DangerButton')
        v.btn_cerrar.clicked.connect(v.cerrar_seleccionadas)
        for w in [v.busqueda, v.check_sistema, v.check_agrupar, v.btn_actualizar, v.btn_seleccionar, v.btn_limpiar, v.btn_cerrar]:
            w.setMinimumWidth(0)
            b.addWidget(w)
        b.setStretch(0, 1)
        layout.addWidget(barra)

        v.tabla = QTableWidget(0, 7)
        v.configurar_tabla(v.tabla)
        v.tabla.setIconSize(QSize(16, 16))
        v.tabla.setMinimumSize(0, 0)
        v.tabla.setHorizontalHeaderLabels(['', 'Nombre', 'PID/Grupo', 'Memoria', 'Impacto', 'Protegido', 'Comando'])
        v.tabla.verticalHeader().setDefaultSectionSize(28)
        v.tabla.horizontalHeader().setMinimumSectionSize(18)
        for i in range(6):
            v.tabla.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        v.tabla.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(v.tabla, 1)

        footer = QHBoxLayout()
        v.resumen_seleccion = QLabel('0 seleccionados')
        v.resumen_seleccion.setObjectName('Muted')
        footer.addWidget(v.resumen_seleccion)
        footer.addStretch(1)
        cache = QPushButton('Liberar cache')
        cache.setToolTip('Liberar cache con aviso')
        cache.setMinimumWidth(0)
        cache.clicked.connect(v.limpiar_cache)
        footer.addWidget(cache)
        layout.addLayout(footer)
        return page

