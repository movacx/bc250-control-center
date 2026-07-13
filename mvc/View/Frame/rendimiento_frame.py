from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QSizePolicy, QTableWidget, QVBoxLayout, QWidget
)

from mvc.View.Componentes.componentes import GraficoGrande, ResourceCard


class RendimientoFrame:
    def __init__(self, vista):
        self.vista = vista
        self.contenedor = self._forms()

    def _forms(self):
        v = self.vista
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        top = v.titulo_pagina('Rendimiento', 'Monitor compacto: recursos, grafica, metricas y sensores visibles.')
        layout.addLayout(top)

        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(10)

        lista = QFrame()
        lista.setObjectName('ResourceList')
        lista_layout = QVBoxLayout(lista)
        lista_layout.setContentsMargins(8, 8, 8, 8)
        lista_layout.setSpacing(6)

        v.card_cpu = ResourceCard('CPU', '#2563eb')
        v.card_ram = ResourceCard('Memoria', '#2563eb')
        v.card_swap = ResourceCard('Swap/zram', '#d97706')
        v.card_gpu = ResourceCard('GPU BC-250', '#8b5cf6')
        v.card_disco = ResourceCard('Disco', '#65a30d')
        v.card_fan = ResourceCard('Ventilador', '#db2777')

        cards = [
            ('cpu', v.card_cpu),
            ('memoria', v.card_ram),
            ('swap', v.card_swap),
            ('gpu', v.card_gpu),
            ('disco', v.card_disco),
            ('fan', v.card_fan),
        ]
        v.resource_cards = dict(cards)
        for recurso, card in cards:
            card.set_callback(recurso, v.seleccionar_recurso_rendimiento)
            card.setMaximumHeight(74)
            card.setMinimumWidth(0)
            lista_layout.addWidget(card)
        lista_layout.addStretch(1)
        cuerpo.addWidget(lista, 0)

        panel = QFrame()
        panel.setObjectName('PerformancePanel')
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(14, 12, 14, 12)
        panel_layout.setSpacing(6)

        encabezado = QHBoxLayout()
        titulo_box = QVBoxLayout()
        v.perf_titulo = QLabel('GPU BC-250')
        v.perf_titulo.setObjectName('HeroTitleCompact')
        v.perf_subtitulo = QLabel('amdgpu / Cyan Skillfish')
        v.perf_subtitulo.setObjectName('Muted')
        titulo_box.addWidget(v.perf_titulo)
        titulo_box.addWidget(v.perf_subtitulo)
        encabezado.addLayout(titulo_box, 1)
        v.perf_porcentaje = QLabel('--')
        v.perf_porcentaje.setObjectName('HeroValueCompact')
        encabezado.addWidget(v.perf_porcentaje)
        panel_layout.addLayout(encabezado)

        v.perf_modo = QLabel('Compute / carga GPU')
        v.perf_modo.setObjectName('Muted')
        panel_layout.addWidget(v.perf_modo)
        v.perf_grafico = GraficoGrande('#8b5cf6', '#eadcff')
        v.perf_grafico.setMinimumHeight(150)
        v.perf_grafico.setMaximumHeight(245)
        v.perf_grafico.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        panel_layout.addWidget(v.perf_grafico, 1)

        stats = QGridLayout()
        stats.setHorizontalSpacing(8)
        stats.setVerticalSpacing(4)
        v.stat_gpu_sclk = v.crear_stat_label('SCLK', '--')
        v.stat_gpu_volt = v.crear_stat_label('Voltaje', '--')
        v.stat_gpu_temp = v.crear_stat_label('Temperatura', '--')
        v.stat_gpu_ppt = v.crear_stat_label('PPT', '--')
        v.stat_cpu_freq = v.crear_stat_label('CPU', '--')
        v.stat_ram = v.crear_stat_label('Memoria', '--')
        for idx, widget in enumerate([v.stat_gpu_sclk, v.stat_gpu_volt, v.stat_gpu_temp, v.stat_gpu_ppt, v.stat_cpu_freq, v.stat_ram]):
            widget.setObjectName('CompactStatBox')
            widget.setMaximumHeight(48)
            widget.setMinimumWidth(0)
            widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            widget.layout().setContentsMargins(6, 3, 6, 3)
            widget.layout().setSpacing(0)
            if hasattr(widget, 'valor_label'):
                widget.valor_label.setObjectName('CompactStatValue')
            stats.addWidget(widget, 0, idx)
        panel_layout.addLayout(stats)

        label = QLabel('Sensores detectados')
        label.setObjectName('SectionTitleCompact')
        panel_layout.addWidget(label)
        v.tabla_sensores = QTableWidget(0, 3)
        v.configurar_tabla(v.tabla_sensores)
        v.tabla_sensores.setMinimumHeight(150)
        v.tabla_sensores.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        v.tabla_sensores.verticalHeader().setDefaultSectionSize(28)
        v.tabla_sensores.horizontalHeader().setMinimumHeight(28)
        v.tabla_sensores.setHorizontalHeaderLabels(['Sensor', 'Valor', 'Fuente'])
        v.tabla_sensores.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        v.tabla_sensores.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        v.tabla_sensores.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        panel_layout.addWidget(v.tabla_sensores, 2)

        cuerpo.addWidget(panel, 1)
        layout.addLayout(cuerpo, 1)
        return page
