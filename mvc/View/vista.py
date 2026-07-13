from PyQt6.QtCore import Qt, QTimer, QSize, QSettings, QProcess, QUrl
from PyQt6.QtGui import QAction, QActionGroup, QColor, QDesktopServices, QIcon, QTextCursor
import shutil
import os
import subprocess
import time
import html
from pathlib import Path
from collections import deque

from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QInputDialog, QLineEdit, QMainWindow, QMessageBox, QPushButton, QSpinBox, QStackedWidget,
    QPlainTextEdit, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)


QtMessageBox = QMessageBox


def buscar_vista_i18n(parent):
    actual = parent
    while actual is not None:
        if hasattr(actual, 't'):
            return actual
        try:
            actual = actual.parent()
        except Exception:
            return None
    return None


def tr_i18n(parent, texto):
    vista = buscar_vista_i18n(parent)
    if vista is not None:
        return vista.t(texto)
    return str(texto)


def messagebox_i18n(parent, icono, titulo, texto, botones=None):
    caja = QtMessageBox(parent)
    caja.setIcon(icono)
    caja.setWindowTitle(tr_i18n(parent, titulo))
    caja.setText(tr_i18n(parent, texto))
    if botones is None:
        botones = QtMessageBox.StandardButton.Ok
    caja.setStandardButtons(botones)
    etiquetas = {
        QtMessageBox.StandardButton.Ok: 'Aceptar',
        QtMessageBox.StandardButton.Yes: 'Si',
        QtMessageBox.StandardButton.No: 'No',
        QtMessageBox.StandardButton.Cancel: 'Cancelar',
        QtMessageBox.StandardButton.Close: 'Cerrar',
    }
    for boton, clave in etiquetas.items():
        widget = caja.button(boton)
        if widget is not None:
            widget.setText(tr_i18n(parent, clave))
    return caja.exec()


class QMessageBoxI18n:
    StandardButton = QtMessageBox.StandardButton
    Icon = QtMessageBox.Icon

    @staticmethod
    def information(parent, titulo, texto, botones=None):
        return messagebox_i18n(parent, QtMessageBox.Icon.Information, titulo, texto, botones)

    @staticmethod
    def warning(parent, titulo, texto, botones=None):
        return messagebox_i18n(parent, QtMessageBox.Icon.Warning, titulo, texto, botones)

    @staticmethod
    def question(parent, titulo, texto, botones=None):
        return messagebox_i18n(parent, QtMessageBox.Icon.Question, titulo, texto, botones)


QMessageBox = QMessageBoxI18n


from mvc.View.Componentes.componentes import formato_bytes, formato_temp, icono_app, crear_nav_icono, MetricStrip, NavButton
from mvc.View.Idioma.traducciones import LANGUAGES, traducir_texto
from mvc.View.Estilos.estilos import obtener_estilo
from mvc.View.Frame.procesos_frame import ProcesosFrame
from mvc.View.Frame.rendimiento_frame import RendimientoFrame
from mvc.View.Frame.memoria_frame import MemoriaFrame
from mvc.View.Frame.bc250_frame import Bc250Frame
from mvc.View.Frame.historial_frame import HistorialFrame


class Vista(QMainWindow):
    def __init__(self, controlador):
        super().__init__()
        self.controlador = controlador
        self.settings = QSettings('BC250ControlCenter', 'BC250ControlCenter')
        self.legacy_settings = QSettings('ModoJuegoRAM', 'ModoJuegoRAM')
        self.idioma = self.setting_value('idioma', 'en')
        self.tema = self.setting_value('tema', 'light')
        self.gpu_minimo = int(self.setting_value('gpu_minimo', 500))
        self.sidebar_colapsada = str(self.setting_value('sidebar_colapsada', 'false')).lower() == 'true'
        self.recurso_rendimiento = self.setting_value('recurso_rendimiento', 'gpu')
        self.alertas_activas = str(self.setting_value('alertas_activas', 'false')).lower() == 'true'
        self.modo_discreto = str(self.setting_value('modo_discreto', 'true')).lower() == 'true'
        self.ultimo_rendimiento = {}
        self.cpu_oc_process = None
        self.cpu_oc_timer = None
        self.cpu_oc_inicio = 0
        self.ultimo_estado_bc250 = {}
        self.ultimo_bc250_refresh = 0
        self.bc250_refresh_interval = 5.0
        self.historial_alertas = deque(maxlen=180)
        self.ultimo_aviso = {}
        self.procesos_actuales = []
        self.filtrados = []
        self.setWindowTitle(self.t('BC250 Control Center'))
        icono = Path(__file__).resolve().parents[1] / 'Resources' / 'icons' / 'bc250-control-center.png'
        if icono.exists():
            self.setWindowIcon(QIcon(str(icono)))
        self.resize(1320, 830)
        self.setMinimumSize(720, 480)
        self.crear_menu()
        self.crear_interfaz()
        self.aplicar_estilo()
        self.aplicar_traducciones_widget(self)
        self.actualizar_rendimiento()
        self.actualizar_procesos()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.actualizar_rendimiento)
        self.timer.start(2000)

        self.timer_procesos = QTimer(self)
        self.timer_procesos.timeout.connect(self.actualizar_procesos)
        self.timer_procesos.start(10000)

    def setting_value(self, clave, defecto=None):
        valor = self.settings.value(clave, None)
        if valor is not None:
            return valor
        return self.legacy_settings.value(clave, defecto)

    def t(self, texto):
        return traducir_texto(texto, self.idioma)

    def estilo_risk_popup(self):
        if self.tema == 'dark':
            panel2 = '#191c22'
            text = '#f4f4f5'
            border = '#60a5fa'
            hover = '#243044'
            active = '#263a59'
            active_text = '#ffffff'
        else:
            panel2 = '#ffffff'
            text = '#0f172a'
            border = '#60a5fa'
            hover = '#f1f7ff'
            active = '#dcebff'
            active_text = '#075985'
        return f'''
            QListView#RiskComboPopup {{
                background: {panel2};
                background-color: {panel2};
                color: {text};
                border: 1px solid {border};
                outline: 0px;
                padding: 0px;
                margin: 0px;
                selection-background-color: {active};
                selection-color: {active_text};
                alternate-background-color: {panel2};
            }}
            QListView#RiskComboPopup::item {{
                background: {panel2};
                background-color: {panel2};
                color: {text};
                min-height: 26px;
                padding: 4px 8px;
                border: 0px;
            }}
            QListView#RiskComboPopup::item:hover {{
                background: {hover};
                background-color: {hover};
                color: {text};
            }}
            QListView#RiskComboPopup::item:selected {{
                background: {active};
                background-color: {active};
                color: {active_text};
            }}
        '''

    def alerta_gpu_html(self, mensaje):
        titulo = html.escape(self.t('Aviso GPU'))
        compat = html.escape(self.t('Compatibilidad SMU'))
        nota = html.escape(self.t('Requiere cyan-skillfish-governor-smu. El paquete cyan-skillfish-governor sin SMU no es compatible con los controles D-Bus de esta app.'))
        info = html.escape(self.t('Mas informacion GPU y governor:'))
        texto = html.escape(str(mensaje))
        enlace = '<a href="https://github.com/filippor/cyan-skillfish-governor/tree/smu">filippor/cyan-skillfish-governor/tree/smu</a>'
        return (
            f'<div><b>{titulo}:</b> {texto}</div>'
            f'<div style="margin-top:3px;"><b>{compat}:</b> {nota}</div>'
            f'<div style="margin-top:3px;">{info} {enlace}</div>'
        )

    def crear_menu(self):
        barra = self.menuBar()
        barra.clear()
        m_info = barra.addMenu(self.t('Información'))
        about = QAction(self.t('Acerca de'), self)
        about.triggered.connect(self.mostrar_acerca_de)
        m_info.addAction(about)
        repos = QAction(self.t('Repositorios oficiales'), self)
        repos.triggered.connect(self.mostrar_repositorios_oficiales)
        m_info.addAction(repos)

        safe = QAction(self.t('Uso seguro BC250'), self)
        safe.triggered.connect(self.mostrar_ayuda_segura)
        m_info.addAction(safe)

        warn_gpu = QAction(self.t('Advertencias'), self)
        warn_gpu.triggered.connect(self.mostrar_advertencias)
        m_info.addAction(warn_gpu)

        m_opts = barra.addMenu(self.t('Opciones'))
        m_conf = m_opts.addMenu(self.t('Configuración'))
        m_lang = m_conf.addMenu(self.t('Idioma'))
        grupo_lang = QActionGroup(self)
        for codigo, nombre in LANGUAGES.items():
            act = QAction(nombre, self, checkable=True)
            act.setChecked(codigo == self.idioma)
            act.triggered.connect(lambda _=False, c=codigo: self.cambiar_idioma(c))
            grupo_lang.addAction(act)
            m_lang.addAction(act)

        m_theme = m_conf.addMenu(self.t('Tema'))
        grupo_theme = QActionGroup(self)
        for codigo, nombre in [('light', self.t('Claro')), ('dark', self.t('Oscuro'))]:
            act = QAction(nombre, self, checkable=True)
            act.setChecked(codigo == self.tema)
            act.triggered.connect(lambda _=False, c=codigo: self.cambiar_tema(c))
            grupo_theme.addAction(act)
            m_theme.addAction(act)

        act_alertas = QAction(self.t('Alertas inteligentes'), self, checkable=True)
        act_alertas.setChecked(self.alertas_activas)
        act_alertas.triggered.connect(self.cambiar_alertas)
        m_conf.addAction(act_alertas)

        act_discreto = QAction(self.t('Modo discreto'), self, checkable=True)
        act_discreto.setChecked(self.modo_discreto)
        act_discreto.triggered.connect(self.cambiar_modo_discreto)
        m_conf.addAction(act_discreto)

        m_conf.addSeparator()
        act_rutas = QAction(self.t('Rutas locales'), self)
        act_rutas.triggered.connect(self.mostrar_rutas_locales)
        m_conf.addAction(act_rutas)

        act_memoria = QAction(self.t('Evaluar presión de memoria'), self)
        act_memoria.triggered.connect(self.mostrar_presion_memoria)
        m_conf.addAction(act_memoria)

        act_daemon = QAction(self.t('Daemon opcional'), self)
        act_daemon.triggered.connect(self.mostrar_daemon_opcional)
        m_conf.addAction(act_daemon)

    def cambiar_idioma(self, codigo):
        self.idioma = codigo
        self.settings.setValue('idioma', codigo)
        self.recrear_interfaz()

    def cambiar_tema(self, tema):
        self.tema = tema
        self.settings.setValue('tema', tema)
        self.crear_menu()
        self.aplicar_estilo()
        self.aplicar_traducciones_widget(self)

    def cambiar_alertas(self, activo):
        self.alertas_activas = bool(activo)
        self.settings.setValue('alertas_activas', 'true' if self.alertas_activas else 'false')
        try:
            self.controlador.guardar_config_local({'alertas_activas': self.alertas_activas})
        except Exception:
            pass
        estado = self.t('activadas') if self.alertas_activas else self.t('desactivadas')
        mensaje = f'{self.t("Alertas")} {estado}.'
        self.registrar_evento('config', 'info', 'Alertas inteligentes', mensaje, {'alertas_activas': self.alertas_activas})
        if hasattr(self, 'estado_lateral'):
            self.estado_lateral.setText(f'{self.t("Alertas inteligentes")}\n{mensaje}')

    def cambiar_modo_discreto(self, activo):
        self.modo_discreto = bool(activo)
        self.settings.setValue('modo_discreto', 'true' if self.modo_discreto else 'false')
        if hasattr(self, 'bc_servicio'):
            self.actualizar_bc250(silencioso=True)
        estado = self.t('activado') if self.modo_discreto else self.t('desactivado')
        self.notificar_evento(self.t('Modo discreto'), f'{self.t("Modo discreto")} {estado}.', 'normal', 'discreto_toggle', 2)

    def recrear_interfaz(self):
        pagina = self.stack.currentIndex() if hasattr(self, 'stack') else 0
        panel = self.bc_panel_stack.currentIndex() if hasattr(self, 'bc_panel_stack') else 0
        viejo = self.centralWidget()
        if viejo:
            viejo.deleteLater()
        self.setWindowTitle(self.t('BC250 Control Center'))
        self.crear_menu()
        self.crear_interfaz()
        self.aplicar_estilo()
        self.aplicar_traducciones_widget(self)
        self.cambiar_pagina(min(pagina, self.stack.count() - 1))
        if hasattr(self, 'bc_panel_stack'):
            self.cambiar_bc_panel(min(panel, self.bc_panel_stack.count() - 1))
        self.actualizar_rendimiento()
        self.actualizar_procesos()

    def aplicar_traducciones_widget(self, widget):
        if self.idioma == 'es':
            return
        for label in widget.findChildren(QLabel):
            txt = label.text()
            if txt and '<' not in txt:
                label.setText(self.t(txt))
            tip = label.toolTip()
            if tip:
                label.setToolTip(self.t(tip))
        for btn in widget.findChildren(QPushButton):
            txt = btn.text()
            if txt:
                btn.setText(self.t(txt))
            tip = btn.toolTip()
            if tip:
                btn.setToolTip(self.t(tip))
        for chk in widget.findChildren(QCheckBox):
            txt = chk.text()
            if txt:
                chk.setText(self.t(txt))
            tip = chk.toolTip()
            if tip:
                chk.setToolTip(self.t(tip))
        for combo in widget.findChildren(QComboBox):
            tip = combo.toolTip()
            if tip:
                combo.setToolTip(self.t(tip))
            for idx in range(combo.count()):
                combo.setItemText(idx, self.t(combo.itemText(idx)))
        for line in widget.findChildren(QLineEdit):
            ph = line.placeholderText()
            if ph:
                line.setPlaceholderText(self.t(ph))
            tip = line.toolTip()
            if tip:
                line.setToolTip(self.t(tip))
        for texto in widget.findChildren(QPlainTextEdit):
            contenido = texto.toPlainText()
            if contenido and len(contenido) < 220 and not any(x in contenido for x in ['|', '+---', 'MHz /']):
                texto.setPlainText(self.t(contenido))
        for tabla in widget.findChildren(QTableWidget):
            for col in range(tabla.columnCount()):
                item = tabla.horizontalHeaderItem(col)
                if item:
                    item.setText(self.t(item.text()))

    def msg_info(self, titulo, texto):
        QMessageBox.information(self, self.t(titulo), self.t(texto))

    def msg_warn(self, titulo, texto):
        QMessageBox.warning(self, self.t(titulo), self.t(texto))

    def msg_question(self, titulo, texto):
        return QMessageBox.question(self, self.t(titulo), self.t(texto), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

    def pedir_texto(self, titulo, etiqueta):
        dialogo = QInputDialog(self)
        dialogo.setWindowTitle(self.t(titulo))
        dialogo.setLabelText(self.t(etiqueta))
        dialogo.setOkButtonText(self.t('Aceptar'))
        dialogo.setCancelButtonText(self.t('Cancelar'))
        aceptado = dialogo.exec() == QDialog.DialogCode.Accepted
        return dialogo.textValue(), aceptado

    def mostrar_rutas_locales(self):
        try:
            rutas = self.controlador.config_paths()
        except Exception as error:
            self.msg_warn('Rutas locales', f'No se pudieron leer rutas locales: {error}')
            return
        texto = '\n'.join(f'{clave}: {valor}' for clave, valor in rutas.items())
        self.msg_info('Rutas locales', texto)

    def mostrar_presion_memoria(self):
        try:
            resultado = self.controlador.proteccion_memoria(False)
        except Exception as error:
            self.msg_warn('Evaluar presión de memoria', f'No se pudo evaluar memoria: {error}')
            return
        estado = resultado.get('estado', {})
        candidatos = resultado.get('candidatos', [])
        lineas = [
            f"{self.t('Nivel')}: {self.t(str(estado.get('nivel')))}",
            f"RAM: {estado.get('ram_percent')}%",
            f"Swap: {estado.get('swap_percent')}%",
            f"{self.t('Juegos detectados')}: {len(estado.get('juegos_detectados', []))}",
            f"{self.t('Candidatos de cierre')}: {len(candidatos)}",
        ]
        for item in candidatos[:5]:
            lineas.append(f"- {item.get('nombre')} PID {item.get('pid')} {item.get('memoria_mb')} MB")
        self.msg_info('Evaluar presión de memoria', '\n'.join(lineas))

    def mostrar_daemon_opcional(self):
        texto = (
            'El daemon bc250-control-centerd es opcional. Monitorea temperatura, RAM, swap, governor y registra metricas JSONL aunque la GUI este cerrada.\n\n'
            'Activar:\n'
            'systemctl --user enable --now bc250-control-centerd.service\n\n'
            'Desactivar:\n'
            'systemctl --user disable --now bc250-control-centerd.service\n\n'
            'Ver estado:\n'
            'systemctl --user status bc250-control-centerd.service\n\n'
            'No aplica OC automatico.'
        )
        self.msg_info('Daemon opcional', texto)


    def abrir_url_oficial(self, url):
        QDesktopServices.openUrl(QUrl(url))

    def mostrar_repositorios_oficiales(self):
        dialogo = QDialog(self)
        dialogo.setWindowTitle(self.t('Repositorios oficiales'))
        layout = QVBoxLayout(dialogo)
        intro = QLabel(self.t('BC250 Control Center no es propietario de estas herramientas. Se clonan o instalan desde repositorios oficiales y conservan sus creditos upstream.'))
        intro.setWordWrap(True)
        layout.addWidget(intro)
        repos = [
            ('cyan-skillfish-governor', 'filippor/cyan-skillfish-governor/tree/smu', 'https://github.com/filippor/cyan-skillfish-governor/tree/smu'),
            ('bc250_smu_oc', 'bc250-collective/bc250_smu_oc', 'https://github.com/bc250-collective/bc250_smu_oc'),
            ('bc250-cu-live-manager', 'WinnieLV/bc250-cu-live-manager', 'https://github.com/WinnieLV/bc250-cu-live-manager'),
            ('bc250-40cu-unlock', 'duggasco/bc250-40cu-unlock', 'https://github.com/duggasco/bc250-40cu-unlock'),
        ]
        for nombre, repo, url in repos:
            fila = QHBoxLayout()
            etiqueta = QLabel(f'{nombre}  |  {repo}')
            boton = QPushButton(self.t('Abrir'))
            boton.clicked.connect(lambda _=False, u=url: self.abrir_url_oficial(u))
            fila.addWidget(etiqueta, 1)
            fila.addWidget(boton)
            layout.addLayout(fila)
        nota = QLabel(self.t('Si Firefox muestra perfil bloqueado desde una terminal, abre los enlaces desde esta ventana o copia la URL en el navegador ya abierto.'))
        nota.setWordWrap(True)
        layout.addWidget(nota)
        cerrar = QPushButton(self.t('Cerrar'))
        cerrar.clicked.connect(dialogo.accept)
        layout.addWidget(cerrar, alignment=Qt.AlignmentFlag.AlignRight)
        dialogo.resize(620, 260)
        dialogo.exec()

    def mostrar_acerca_de(self):
        texto = (
            'BC250 Control Center es una interfaz grafica para administrar, preparar y supervisar herramientas comunitarias de la placa AMD BC-250.\n\n'
            'Que hace la aplicacion:\n'
            '- Reune en una sola ventana funciones de GPU, CPU, 40CU, procesos, memoria, sensores e historial.\n'
            '- Prepara dependencias en distribuciones compatibles para que una instalacion recien hecha quede lista sin buscar comandos por internet.\n'
            '- Permite usar perfiles y acciones con advertencias, validaciones y limites visuales.\n'
            '- Muestra rutas, estado de servicios y salidas importantes para que el usuario entienda que esta ocurriendo.\n\n'
            'Que usa internamente:\n'
            '- cyan-skillfish-governor-smu para controlar rangos GPU mediante governor/D-Bus.\n'
            '- bc250_smu_oc para CPU OC temporal o persistente cuando el usuario lo decide.\n'
            '- bc250-cu-live-manager para dashboard live y acciones 40CU/24CU.\n'
            '- UMR, lm_sensors, systemd, Polkit y herramientas del sistema cuando hacen falta.\n\n'
            'Credito y alcance del proyecto:\n'
            '- Nuestro trabajo es crear un launcher/centro grafico que integra, organiza y administra estos repositorios de forma mas amigable.\n'
            '- No reclamamos autoria sobre herramientas comunitarias externas; cada una conserva sus creditos, licencia y repositorio oficial.\n'
            '- El objetivo es que el usuario se sienta comodo usando la BC-250 sin depender tanto de la terminal ni navegar entre multiples repositorios.\n\n'
            'Importante:\n'
            '- Overclock, 40CU y cambios de frecuencia pueden causar cuelgues, apagones, perdida de datos o dano de hardware.\n'
            '- Cada BC-250 es distinta; prueba por pasos y bajo tu responsabilidad.'
        )
        dialogo = QDialog(self)
        dialogo.setWindowTitle(self.t('Acerca de'))
        layout = QVBoxLayout(dialogo)
        caja = QPlainTextEdit()
        caja.setReadOnly(True)
        caja.setPlainText(self.t(texto))
        caja.setMinimumSize(560, 360)
        layout.addWidget(caja)
        cerrar = QPushButton(self.t('Cerrar'))
        cerrar.clicked.connect(dialogo.accept)
        layout.addWidget(cerrar, alignment=Qt.AlignmentFlag.AlignRight)
        dialogo.resize(640, 520)
        dialogo.exec()

    def mostrar_ayuda_segura(self):
        self.msg_info('Uso seguro BC250', 'Para bajar frecuencias altas, detén juegos o pruebas de estres primero. Evita saltos bruscos como 2000 MHz a 1000 MHz bajo carga; baja por pasos y monitorea temperatura, voltaje y estabilidad.')

    def mostrar_advertencias(self):
        self.msg_warn('Advertencias', 'Desde 2000 MHz en GPU hay riesgo de apagones, cuelgues o daño. 40CU aumenta consumo y temperatura. CPU OC temporal puede crashear si la placa no es estable.')

    def crear_interfaz(self):
        root = QWidget()
        root.setObjectName('Root')
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(12)

        sidebar = QFrame()
        self.sidebar = sidebar
        sidebar.setObjectName('Sidebar')
        sidebar.setFixedWidth(212)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(12, 14, 12, 14)
        side.setSpacing(6)
        top_side = QHBoxLayout()
        self.btn_toggle_sidebar = QPushButton('☰')
        self.btn_toggle_sidebar.setObjectName('ToggleSidebar')
        self.btn_toggle_sidebar.clicked.connect(self.alternar_sidebar)
        top_side.addWidget(self.btn_toggle_sidebar, 0, Qt.AlignmentFlag.AlignCenter)
        top_side.addStretch(1)
        side.addLayout(top_side)
        app = QLabel('BC250 Control\nCenter')
        self.app_label = app
        app.setObjectName('AppTitle')
        app.setWordWrap(True)
        app.setMinimumHeight(44)
        desc = QLabel('Task Manager')
        self.app_desc = desc
        desc.setObjectName('Muted')
        side.addWidget(app)
        side.addWidget(desc)
        side.addSpacing(14)

        nombres = ['Procesos', 'Rendimiento', 'Memoria', 'BC250', 'Historial']
        self.nav_buttons = []
        for i, nombre in enumerate(nombres):
            btn = NavButton(self.t(nombre), crear_nav_icono(nombre))
            btn.setProperty('base_text', nombre)
            btn.setProperty('full_text', self.t(nombre))
            btn.setProperty('short_text', '')
            btn.clicked.connect(lambda _=False, idx=i: self.cambiar_pagina(idx))
            self.nav_buttons.append(btn)
            side.addWidget(btn)
        side.addStretch(1)
        self.estado_lateral = QLabel('Sistema protegido')
        self.estado_lateral.setObjectName('StatusBox')
        self.estado_lateral.setWordWrap(True)
        side.addWidget(self.estado_lateral)

        self.stack = QStackedWidget()
        self.stack.setObjectName('Stack')
        self.stack.addWidget(self.crear_pagina_procesos())
        self.stack.addWidget(self.crear_pagina_rendimiento())
        self.stack.addWidget(self.crear_pagina_memoria())
        self.stack.addWidget(self.crear_pagina_bc250())
        self.stack.addWidget(self.crear_pagina_historial())

        root_layout.addWidget(sidebar)
        root_layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.aplicar_estado_sidebar()
        self.cambiar_pagina(0)

    def alternar_sidebar(self):
        self.sidebar_colapsada = not self.sidebar_colapsada
        self.settings.setValue('sidebar_colapsada', 'true' if self.sidebar_colapsada else 'false')
        self.aplicar_estado_sidebar()

    def aplicar_estado_sidebar(self):
        if not hasattr(self, 'sidebar'):
            return
        ancho = 66 if self.sidebar_colapsada else 212
        self.sidebar.setFixedWidth(ancho)
        if hasattr(self, 'app_label'):
            self.app_label.setVisible(not self.sidebar_colapsada)
        if hasattr(self, 'app_desc'):
            self.app_desc.setVisible(not self.sidebar_colapsada)
        if hasattr(self, 'estado_lateral'):
            self.estado_lateral.setVisible(not self.sidebar_colapsada)
        for btn in getattr(self, 'nav_buttons', []):
            base_text = btn.property('base_text') or btn.property('full_text') or ''
            full_text = self.t(base_text)
            btn.setProperty('full_text', full_text)
            btn.setText(btn.property('short_text') if self.sidebar_colapsada else full_text)
            btn.setToolTip(full_text)
            btn.setIconSize(QSize(28, 28) if self.sidebar_colapsada else QSize(24, 24))
            btn.setProperty('collapsed', self.sidebar_colapsada)
            if self.sidebar_colapsada:
                btn.setFixedSize(42, 42)
            else:
                btn.setMinimumSize(0, 0)
                btn.setMaximumSize(16777215, 16777215)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        if hasattr(self, 'btn_toggle_sidebar'):
            if self.sidebar_colapsada:
                self.btn_toggle_sidebar.setFixedSize(42, 42)
            else:
                self.btn_toggle_sidebar.setMinimumSize(0, 0)
                self.btn_toggle_sidebar.setMaximumSize(16777215, 16777215)

    def titulo_pagina(self, titulo, subtitulo):
        top = QHBoxLayout()
        box = QVBoxLayout()
        t = QLabel(titulo)
        t.setObjectName('PageTitle')
        s = QLabel(subtitulo)
        s.setObjectName('Muted')
        s.setWordWrap(True)
        box.addWidget(t)
        box.addWidget(s)
        top.addLayout(box, 1)
        return top

    def configurar_tabla(self, tabla):
        tabla.verticalHeader().setVisible(False)
        tabla.setAlternatingRowColors(True)
        tabla.setShowGrid(False)
        tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tabla.verticalHeader().setDefaultSectionSize(36)
        tabla.horizontalHeader().setMinimumHeight(34)

    def crear_stat_label(self, titulo, valor):
        box = QFrame()
        box.setObjectName('StatBox')
        layout = QVBoxLayout(box)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)
        label = QLabel(titulo)
        label.setObjectName('Muted')
        value = QLabel(valor)
        value.setObjectName('StatValue')
        box.titulo_label = label
        box.valor_label = value
        layout.addWidget(label)
        layout.addWidget(value)
        return box

    def actualizar_stat(self, box, valor):
        if hasattr(box, 'valor_label'):
            box.valor_label.setText(str(valor))

    def actualizar_stat_titulo(self, box, titulo):
        if hasattr(box, 'titulo_label'):
            box.titulo_label.setText(str(titulo))

    def seleccionar_recurso_rendimiento(self, recurso):
        self.recurso_rendimiento = recurso
        self.settings.setValue('recurso_rendimiento', recurso)
        self.actualizar_panel_rendimiento(self.ultimo_rendimiento)

    def actualizar_panel_rendimiento(self, datos):
        if not datos or not hasattr(self, 'perf_titulo'):
            return
        recurso = self.recurso_rendimiento
        for clave, card in getattr(self, 'resource_cards', {}).items():
            card.set_activo(clave == recurso)
        mapas = {
            'cpu': ('CPU', f'{datos["cpu"]:.0f}% / {datos.get("cpu_freq") or 0:.0f} MHz', 'Uso total del procesador', datos['cpu'], '#2563eb', '#dbeafe'),
            'memoria': ('Memoria', f'{datos["memoria_porcentaje"]:.0f}%', f'{formato_bytes(datos["memoria_total"] - datos["memoria_disponible"])} / {formato_bytes(datos["memoria_total"])}', datos['memoria_porcentaje'], '#2563eb', '#dbeafe'),
            'swap': ('Swap / zram', f'{datos["swap_porcentaje"]:.0f}%', f'{formato_bytes(datos["swap_usado"])} / {formato_bytes(datos["swap_total"])}', datos['swap_porcentaje'], '#d97706', '#ffedd5'),
            'gpu': ('GPU BC-250', '--', 'Compute / carga GPU', 0, '#8b5cf6', '#eadcff'),
            'disco': ('Disco', f'{datos["disco_porcentaje"]:.0f}%', f'R {formato_bytes(datos["disco_lectura"])} /s - W {formato_bytes(datos["disco_escritura"])} /s', datos['disco_porcentaje'], '#65a30d', '#dcfce7'),
            'fan': ('Ventilador', '--' if datos['fan_rpm'] is None else f'{datos["fan_rpm"]} RPM', 'Sensor nct6686', min(100, (datos['fan_rpm'] or 0) / 50), '#db2777', '#fce7f3'),
        }
        titulo, valor, detalle, grafico, color, relleno = mapas.get(recurso, mapas['gpu'])
        if recurso == 'gpu':
            gpu_busy = getattr(self, 'ultimo_gpu_busy', None)
            gpu_sclk = getattr(self, 'ultimo_gpu_sclk', None)
            gpu_volt = getattr(self, 'ultimo_gpu_volt', None)
            valor = '--' if gpu_busy is None else f'{gpu_busy}%'
            grafico = gpu_busy if gpu_busy is not None else min(100, datos.get('gpu_temp') or 0)
            detalle = 'amdgpu / Cyan Skillfish'
            self.actualizar_stat(self.stat_gpu_sclk, '--' if gpu_sclk is None else f'{gpu_sclk} MHz')
            self.actualizar_stat(self.stat_gpu_volt, '--' if gpu_volt is None else f'{gpu_volt} mV')
        else:
            self.actualizar_stat(self.stat_gpu_sclk, valor)
            self.actualizar_stat(self.stat_gpu_volt, detalle)
        etiquetas = {
            'gpu': ['SCLK', 'Voltaje', 'Temperatura', 'PPT', 'CPU', 'Memoria'],
            'cpu': ['Uso CPU', 'Descripcion', 'Temperatura', 'PPT GPU', 'Frecuencia', 'Memoria'],
            'memoria': ['Uso RAM', 'En uso', 'Temperatura GPU', 'PPT GPU', 'CPU', 'Total RAM'],
            'swap': ['Uso swap', 'Swap usado', 'Temperatura GPU', 'PPT GPU', 'CPU', 'RAM'],
            'disco': ['Uso disco', 'Actividad', 'Temperatura GPU', 'PPT GPU', 'CPU', 'RAM'],
            'fan': ['RPM', 'Sensor', 'Temperatura GPU', 'PPT GPU', 'CPU', 'RAM'],
        }.get(recurso, ['Dato 1', 'Dato 2', 'Temperatura', 'PPT', 'CPU', 'Memoria'])
        for box, etiqueta in zip([self.stat_gpu_sclk, self.stat_gpu_volt, self.stat_gpu_temp, self.stat_gpu_ppt, self.stat_cpu_freq, self.stat_ram], etiquetas):
            self.actualizar_stat_titulo(box, self.t(etiqueta))
        self.perf_titulo.setText(self.t(titulo))
        self.perf_subtitulo.setText(self.t(detalle))
        self.perf_modo.setText(self.t('Historial de uso'))
        self.perf_porcentaje.setText(valor)
        self.perf_grafico.configurar(color, relleno)
        self.perf_grafico.agregar(grafico)
        self.actualizar_stat(self.stat_gpu_temp, formato_temp(datos['gpu_temp']))
        self.actualizar_stat(self.stat_gpu_ppt, '--' if datos['gpu_power'] is None else f'{datos["gpu_power"]:.1f} W')
        self.actualizar_stat(self.stat_cpu_freq, '--' if datos.get('cpu_freq') is None else f'{datos.get("cpu_freq"):.0f} MHz')
        self.actualizar_stat(self.stat_ram, f'{formato_bytes(datos["memoria_total"] - datos["memoria_disponible"])} / {formato_bytes(datos["memoria_total"])}')

    def crear_pagina_procesos(self):
        return ProcesosFrame(self).contenedor
    def crear_pagina_rendimiento(self):
        return RendimientoFrame(self).contenedor
    def crear_pagina_memoria(self):
        return MemoriaFrame(self).contenedor
    def crear_pagina_bc250(self):
        return Bc250Frame(self).contenedor
    def crear_pagina_historial(self):
        return HistorialFrame(self).contenedor

    def cambiar_bc_panel(self, indice):
        if hasattr(self, 'bc_panel_stack'):
            self.bc_panel_stack.setCurrentIndex(indice)
        for i, btn in enumerate(getattr(self, 'bc_mode_buttons', [])):
            btn.setChecked(i == indice)
        if indice == 1:
            self.actualizar_cpu_oc_persistente_status(silencioso=True)

    def minimo_gpu_seleccionado(self):
        return int(getattr(self, 'gpu_minimo', 500) or 500)

    def set_gpu_minimo(self, valor):
        self.gpu_minimo = int(valor)
        self.settings.setValue('gpu_minimo', self.gpu_minimo)
        for btn in getattr(self, 'gpu_min_buttons', []):
            btn.setChecked(int(btn.property('minimo')) == self.gpu_minimo)

    def cambiar_gpu_minimo_aplicado(self, valor):
        if not hasattr(self, 'bc_servicio'):
            return
        minimo_anterior = self.gpu_minimo
        try:
            estado = self.controlador.estado_bc250()
            maximo = estado.get('current_max')
            if not maximo:
                raise RuntimeError('No se pudo detectar el maximo actual del governor')
            maximo = int(maximo)
            minimo = int(valor)
            if minimo > maximo:
                QMessageBox.warning(self, 'BC-250', f'El minimo {minimo} MHz no puede ser mayor que el maximo actual {maximo} MHz.\n\nPrimero aplica un perfil/OC con maximo {minimo} MHz o superior, luego establece este minimo.')
                self.set_gpu_minimo(minimo_anterior)
                return
            safe_freqs = sorted({int(p.get('frequency')) for p in estado.get('safe_points_with_voltage', []) if p.get('frequency')})
            if minimo not in safe_freqs:
                QMessageBox.warning(self, 'BC-250', f'{minimo} MHz no tiene safe-point valido con voltage activo en el TOML.')
                self.set_gpu_minimo(minimo_anterior)
                return
            self.controlador.aplicar_rango_bc250(minimo, maximo)
            self.set_gpu_minimo(valor)
            self.registrar_evento('gpu', 'info', 'Mínimo GPU aplicado', f'Rango GPU actualizado a {minimo}-{maximo} MHz.', {'minimo': minimo, 'maximo': maximo})
            self.actualizar_bc250()
            self.notificar_evento('Mínimo GPU aplicado', f'Rango GPU actualizado a {minimo}-{maximo} MHz.', 'normal', 'gpu_minimo', 20)
        except Exception as error:
            QMessageBox.warning(self, 'BC-250', f'No se pudo aplicar el minimo GPU por D-Bus: {error}')
            self.set_gpu_minimo(minimo_anterior)
            self.actualizar_bc250(silencioso=True)

    def cambiar_pagina(self, indice):
        self.stack.setCurrentIndex(indice)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == indice)
            btn.setProperty('active', i == indice)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        if hasattr(self, 'tabla_historial') and indice == self.stack.count() - 1:
            self.actualizar_historial()
        if indice == 3 and time.monotonic() - getattr(self, 'ultimo_bc250_refresh', 0) >= 1:
            self.actualizar_bc250(silencioso=True)
            self.ultimo_bc250_refresh = time.monotonic()

    def registrar_evento(self, tipo, nivel, titulo, detalle='', datos=None):
        try:
            titulo, detalle, datos = self.normalizar_evento_ingles(titulo, detalle, datos or {})
            self.controlador.registrar_evento(tipo, nivel, titulo, detalle, datos)
            if hasattr(self, 'tabla_historial') and hasattr(self, 'stack') and self.stack.currentIndex() == self.stack.count() - 1:
                self.actualizar_historial()
        except Exception:
            pass

    def normalizar_evento_ingles(self, titulo, detalle='', datos=None):
        mapa_textos = {
            'Mínimo GPU aplicado': 'GPU minimum applied',
            'Minimo GPU aplicado': 'GPU minimum applied',
            'Perfil inteligente seleccionado': 'Smart profile selected',
            'Perfil GPU aplicado': 'GPU profile applied',
            'CPU OC temporal': 'Temporary CPU OC',
            'CPU OC persistente': 'Persistent CPU OC',
            'Acción 40CU': '40CU action',
            'Accion 40CU': '40CU action',
            'Mapa CU actualizado': 'CU map updated',
            'Dashboard 40CU actualizado': '40CU dashboard updated',
            'Preparar dependencias BC250': 'Prepare BC250 dependencies',
            'Preparar bc250-detect': 'Prepare bc250-detect',
            'Instalar UMR': 'Install UMR',
            'Lab voltaje personalizado': 'Custom voltage lab',
            'Lab voltaje aplicado': 'Voltage lab applied',
            'Personalizado': 'Custom',
            'Recomendado': 'Recommended',
            'Muy alto': 'Very high',
            'Alto': 'High',
            'Eco': 'Eco',
            'Balance': 'Balance',
            'Punto medio': 'Middle point',
            'Placa media': 'Average board',
            'Eficiente': 'Efficient',
            'Max seguro UI': 'UI safe max',
            'Recomendado para 40CU': 'Recommended for 40CU',
            'Instalacion de servicio bc250-smu-oc solicitada': 'bc250-smu-oc service installation requested',
            'Desactivacion de servicio bc250-smu-oc solicitada': 'bc250-smu-oc service disable requested',
            'Lectura de cu_map.sh completada': 'cu_map.sh read completed',
            'Lectura de live-manager/cu_map completada': 'live-manager/cu_map read completed',
            'Se abrió terminal para preparar dependencias faltantes.': 'Opened terminal to prepare missing dependencies.',
            'Se abrió terminal para preparar bc250_smu_oc/bc250-detect sin pip.': 'Opened terminal to prepare bc250_smu_oc/bc250-detect without pip.',
            'Se abrió terminal para instalar UMR.': 'Opened terminal to install UMR.',
            'Se abrio terminal para preparar dependencias faltantes.': 'Opened terminal to prepare missing dependencies.',
            'Se abrio terminal para preparar bc250_smu_oc/bc250-detect sin pip.': 'Opened terminal to prepare bc250_smu_oc/bc250-detect without pip.',
            'Se abrio terminal para instalar UMR.': 'Opened terminal to install UMR.',
            'enable40': 'enable40',
            'stock': 'stock',
            'menu': 'menu',
        }
        mapa_claves = {
            'minimo': 'minimum',
            'maximo': 'maximum',
            'perfil': 'profile',
            'frecuencia': 'frequency',
            'vid': 'vid',
            'temp': 'temp',
            'accion': 'action',
            'nivel': 'level',
        }

        def conv_texto(valor):
            texto = str(valor)
            if texto in mapa_textos:
                return mapa_textos[texto]
            for origen, destino in mapa_textos.items():
                texto = texto.replace(origen, destino)
            texto = texto.replace('Rango GPU actualizado a ', 'GPU range updated to ')
            texto = texto.replace('Nivel ', 'Level ')
            return texto

        datos_normalizados = {}
        if isinstance(datos, dict):
            for clave, valor in datos.items():
                clave_en = mapa_claves.get(str(clave), str(clave))
                datos_normalizados[clave_en] = conv_texto(valor) if isinstance(valor, str) else valor
        else:
            datos_normalizados = datos or {}
        return conv_texto(titulo), conv_texto(detalle), datos_normalizados

    def traducir_encabezados_historial(self):
        if hasattr(self, 'tabla_historial'):
            self.tabla_historial.setHorizontalHeaderLabels([
                self.t('Fecha'), self.t('Tipo'), self.t('Nivel'),
                self.t('Titulo'), self.t('Detalle'), self.t('Datos')
            ])

    def actualizar_historial(self):
        if not hasattr(self, 'tabla_historial'):
            return
        self.traducir_encabezados_historial()
        try:
            eventos = self.controlador.obtener_eventos(300)
        except Exception as error:
            self.historial_estado.setText(f'{self.t("No se pudo leer historial:")} {error}')
            return
        self.tabla_historial.setRowCount(len(eventos))
        for fila, evento in enumerate(eventos):
            titulo, detalle, datos_evento = self.normalizar_evento_ingles(
                evento.get('titulo', '--'),
                evento.get('detalle', '--'),
                evento.get('datos') or {}
            )
            datos = evento.get('datos') or {}
            datos = datos_evento if isinstance(datos_evento, dict) else datos
            if isinstance(datos, dict):
                datos_txt = ', '.join(f'{k}={v}' for k, v in list(datos.items())[:5])
            else:
                datos_txt = str(datos)
            valores = [
                evento.get('fecha', '--'),
                evento.get('tipo', '--'),
                evento.get('nivel', '--'),
                titulo,
                detalle,
                datos_txt,
            ]
            for col, valor in enumerate(valores):
                self.tabla_historial.setItem(fila, col, QTableWidgetItem(str(valor)))
        self.historial_estado.setText(f'{len(eventos)} {self.t("eventos locales en JSONL")}')

    def limpiar_historial(self):
        r = QMessageBox.warning(self, self.t('Limpiar historial'), self.t('Se borrara el historial local JSONL. Continuar?'), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        try:
            self.controlador.limpiar_historial()
            self.actualizar_historial()
        except Exception as error:
            QMessageBox.warning(self, self.t('Historial'), f'{self.t("No se pudo limpiar historial:")} {error}')

    def presion_memoria(self, disponible, total, swap_pct):
        ratio = disponible / total if total else 0
        if ratio < 0.12 or swap_pct >= 70:
            return 'alta'
        if ratio < 0.25 or swap_pct >= 35:
            return 'media'
        return 'baja'

    def notificar_evento(self, titulo, mensaje, urgencia='normal', clave='general', cooldown=300):
        if not getattr(self, 'alertas_activas', False):
            return
        ahora = time.monotonic()
        ultimo = self.ultimo_aviso.get(clave, 0)
        if ahora - ultimo < cooldown:
            return
        self.ultimo_aviso[clave] = ahora
        self.registrar_evento('alerta', urgencia, titulo, mensaje, {'clave': clave})
        if hasattr(self, 'estado_lateral'):
            self.estado_lateral.setText(f'{titulo}\n{mensaje[:80]}')
        if shutil.which('notify-send'):
            try:
                subprocess.Popen([
                    'notify-send', '-a', 'BC250 Control Center', '-u', urgencia,
                    '-i', 'utilities-system-monitor', titulo, mensaje
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    def evaluar_alertas(self, datos, estado=None):
        if not getattr(self, 'alertas_activas', False):
            return
        estado = estado or getattr(self, 'ultimo_estado_bc250', {}) or {}
        ahora = time.monotonic()
        gpu_temp = datos.get('gpu_temp')
        cpu_temp = datos.get('cpu_temp')
        gpu_power = datos.get('gpu_power')
        memoria = datos.get('memoria_porcentaje') or 0
        swap = datos.get('swap_porcentaje') or 0
        busy = estado.get('gpu_busy')
        sclk = estado.get('sclk_actual') or 0
        maximo = estado.get('current_max') or 0
        dbus = bool(estado.get('dbus_ok')) if estado else True
        servicio = estado.get('service_active') if estado else 'active'

        self.historial_alertas.append({
            't': ahora,
            'gpu_temp': gpu_temp,
            'cpu_temp': cpu_temp,
            'memoria': memoria,
            'swap': swap,
            'busy': busy,
            'sclk': sclk,
            'maximo': maximo,
            'gpu_power': gpu_power,
        })

        if gpu_temp is not None and gpu_temp >= 85:
            self.notificar_evento('Temperatura GPU crítica', f'GPU edge {gpu_temp:.1f} C. Baja frecuencia/carga y revisa ventilación.', 'critical', 'gpu_temp_critica', 180)
        elif gpu_temp is not None and gpu_temp >= 78:
            self.notificar_evento('Temperatura GPU alta', f'GPU edge {gpu_temp:.1f} C. Vigila OC, 40CU y carga 3D.', 'normal', 'gpu_temp_alta', 300)

        if cpu_temp is not None and cpu_temp >= 90:
            self.notificar_evento('Temperatura CPU crítica', f'CPU Tctl {cpu_temp:.1f} C. Puede provocar throttling o apagado.', 'critical', 'cpu_temp_critica', 180)
        elif cpu_temp is not None and cpu_temp >= 82:
            self.notificar_evento('Temperatura CPU alta', f'CPU Tctl {cpu_temp:.1f} C. Revisa perfil CPU OC y ventilación.', 'normal', 'cpu_temp_alta', 300)

        if memoria >= 92 or swap >= 70:
            self.notificar_evento('Presión de memoria alta', f'RAM {memoria:.0f}% / swap {swap:.0f}%. Riesgo de tirones o congelamiento.', 'critical', 'memoria_alta', 240)
        elif memoria >= 85 or swap >= 45:
            self.notificar_evento('Presión de memoria media', f'RAM {memoria:.0f}% / swap {swap:.0f}%. Conviene cerrar apps pesadas.', 'normal', 'memoria_media', 420)

        if estado and servicio != 'active':
            self.notificar_evento('Governor no activo', f'cyan-skillfish-governor-smu esta en estado {servicio or "--"}.', 'critical', 'governor_inactivo', 180)
        elif estado and not dbus:
            self.notificar_evento('D-Bus del governor no disponible', 'La app puede monitorear, pero no aplicar rangos GPU por D-Bus.', 'critical', 'dbus_no_disponible', 180)

        if maximo and maximo >= 2000 and busy is not None and busy >= 80 and gpu_temp is not None and gpu_temp >= 72:
            self.notificar_evento('OC GPU bajo carga alta', f'GPU {busy}% a max {maximo} MHz y {gpu_temp:.1f} C. Riesgo de inestabilidad si bajas frecuencia bruscamente.', 'normal', 'oc_carga_alta', 240)

        recientes = [x for x in self.historial_alertas if ahora - x['t'] <= 60 and x.get('gpu_temp') is not None]
        if len(recientes) >= 20 and gpu_temp is not None:
            delta = gpu_temp - (recientes[0].get('gpu_temp') or gpu_temp)
            if gpu_temp >= 70 and delta >= 8:
                self.notificar_evento('Subida rápida de temperatura', f'GPU subio {delta:.1f} C en menos de 1 minuto. Posible carga/OC inestable.', 'normal', 'gpu_temp_tendencia', 300)

    def etiqueta_entorno_protegido(self):
        escritorio = (os.environ.get('XDG_CURRENT_DESKTOP') or os.environ.get('DESKTOP_SESSION') or '').lower()
        if 'gnome' in escritorio:
            return self.t('GNOME protegido')
        if 'kde' in escritorio or 'plasma' in escritorio:
            return self.t('KDE protegido')
        if 'cinnamon' in escritorio:
            return self.t('Cinnamon protegido')
        return self.t('Sistema protegido')

    def actualizar_rendimiento(self):
        datos = self.controlador.rendimiento().to_dict()
        disponible_pct = max(0, min(100, 100 - datos['memoria_porcentaje']))
        presion = self.presion_memoria(datos['memoria_disponible'], datos['memoria_total'], datos['swap_porcentaje'])
        self.pill_estado.setText(f'{self.t("Presion")} {self.t(presion)}  |  {formato_bytes(datos["memoria_disponible"])} {self.t("disponibles")}')
        self.estado_lateral.setText(f'{self.t("Presion")} {self.t(presion)}\n{formato_bytes(datos["memoria_disponible"])} {self.t("disponibles")}\n{self.etiqueta_entorno_protegido()}')
        self.m_cpu.actualizar(f'{datos["cpu"]:.0f}%', f'{len(datos["hilos"])} {self.t("hilos")}', datos['cpu'])
        self.m_ram.actualizar(f'{disponible_pct:.0f}%', f'{formato_bytes(datos["memoria_disponible"])} {self.t("libres")}', disponible_pct)
        self.m_swap.actualizar(f'{datos["swap_porcentaje"]:.0f}%', f'{formato_bytes(datos["swap_usado"])} {self.t("usados")}', datos['swap_porcentaje'])
        self.m_disco.actualizar(f'{datos["disco_porcentaje"]:.0f}%', f'R {formato_bytes(datos["disco_lectura"])} /s', datos['disco_porcentaje'])
        gpu_detalle = f'Temp {formato_temp(datos["gpu_temp"])}'
        if datos['gpu_power'] is not None:
            gpu_detalle += f' | {datos["gpu_power"]:.1f} W'
        fan = datos['fan_rpm']
        if hasattr(self, 'card_cpu'):
            self.card_cpu.actualizar(f'{datos["cpu"]:.0f}%  {datos.get("cpu_freq") or 0:.0f} MHz', f'{len(datos["hilos"])} {self.t("hilos")} | {formato_temp(datos["cpu_temp"])}', datos['cpu'])
            self.card_ram.actualizar(f'{datos["memoria_porcentaje"]:.0f}%', f'{formato_bytes(datos["memoria_disponible"])} {self.t("libres")}', datos['memoria_porcentaje'])
            self.card_swap.actualizar(f'{datos["swap_porcentaje"]:.0f}%', f'{formato_bytes(datos["swap_usado"])} {self.t("usados")}', datos['swap_porcentaje'])
            gpu_busy = datos.get('gpu_busy')
            gpu_graph = gpu_busy if gpu_busy is not None else min(100, datos['gpu_temp'] or 0)
            gpu_valor = f'{gpu_busy}%' if gpu_busy is not None else formato_temp(datos['gpu_temp'])
            gpu_detalle_card = gpu_detalle if gpu_busy is None else f'Temp {formato_temp(datos["gpu_temp"])}' + (f' | {datos["gpu_power"]:.1f} W' if datos['gpu_power'] is not None else '')
            self.card_gpu.actualizar(gpu_valor, gpu_detalle_card, gpu_graph)
            self.card_disco.actualizar(f'{datos["disco_porcentaje"]:.0f}%', f'R {formato_bytes(datos["disco_lectura"])} /s', datos['disco_porcentaje'])
            self.card_fan.actualizar('--' if fan is None else f'{fan} RPM', 'nct6686' if fan else 'Sin dato', min(100, (fan or 0) / 50))
            self.ultimo_rendimiento = datos
            self.actualizar_panel_rendimiento(datos)
        self.mem_disponible.actualizar(f'{disponible_pct:.0f}%', f'{formato_bytes(datos["memoria_disponible"])} {self.t("disponibles")}', disponible_pct)
        self.mem_usada.actualizar(f'{datos["memoria_porcentaje"]:.0f}%', f'{formato_bytes(datos["memoria_total"] - datos["memoria_disponible"])} en uso aprox.', datos['memoria_porcentaje'])
        self.mem_swap.actualizar(f'{datos["swap_porcentaje"]:.0f}%', f'{formato_bytes(datos["swap_usado"])} de {formato_bytes(datos["swap_total"])}', datos['swap_porcentaje'])
        self.mem_disco.actualizar(f'{datos["disco_porcentaje"]:.0f}%', f'{formato_bytes(datos["disco_usado"])} de {formato_bytes(datos["disco_total"])}', datos['disco_porcentaje'])
        if hasattr(self, 'bc_cpu_mhz'):
            freq = datos.get('cpu_freq')
            volt = datos.get('cpu_voltage')
            cpu_temp = datos.get('cpu_temp')
            gpu_temp = datos.get('gpu_temp')
            gpu_power = datos.get('gpu_power')
            self.bc_cpu_mhz.actualizar('--' if freq is None else f'{freq:.0f} MHz', f'{self.t("Carga")} {datos["cpu"]:.0f}% | {len(datos["hilos"])} {self.t("hilos")}', datos['cpu'])
            self.bc_cpu_temp.actualizar(formato_temp(cpu_temp), 'Tctl k10temp', min(100, cpu_temp or 0))
            self.bc_cpu_volt.actualizar('--' if volt is None else f'{volt} mV', 'vddnb / sensor amdgpu', min(100, (volt or 0) / 15))
            detalle_gpu = 'edge amdgpu'
            if gpu_power is not None:
                detalle_gpu += f' | {gpu_power:.1f} W'
            self.bc_gpu_temp.actualizar(formato_temp(gpu_temp), detalle_gpu, min(100, gpu_temp or 0))
        filas = [
            ('CPU Tctl', formato_temp(datos['cpu_temp']), 'k10temp'),
            ('GPU edge', formato_temp(datos['gpu_temp']), 'amdgpu'),
            ('GPU PPT', '--' if datos['gpu_power'] is None else f'{datos["gpu_power"]:.1f} W', 'amdgpu'),
            ('Ventilador', '--' if fan is None else f'{fan} RPM', 'nct6686')
        ]
        for nombre, valor in datos['board_temps']:
            filas.append((nombre, formato_temp(valor), 'nct6686'))
        self.tabla_sensores.setRowCount(len(filas))
        for fila, valores in enumerate(filas):
            for col, valor in enumerate(valores):
                self.tabla_sensores.setItem(fila, col, QTableWidgetItem(valor))
        estado_bc250 = self.ultimo_estado_bc250 or {}
        ahora = time.monotonic()
        pagina_bc250 = hasattr(self, 'stack') and self.stack.currentIndex() == 3
        if pagina_bc250 or ahora - getattr(self, 'ultimo_bc250_refresh', 0) >= self.bc250_refresh_interval:
            estado_bc250 = self.actualizar_bc250(silencioso=True) or estado_bc250
            self.ultimo_bc250_refresh = ahora
        self.evaluar_alertas(datos, estado_bc250)

    def texto_estado(self, valor):
        if valor is None or valor == '':
            return '--'
        tabla = {
            'active': 'Activo',
            'inactive': 'Inactivo',
            'enabled': 'Habilitado',
            'disabled': 'Deshabilitado',
            'activating': 'Activando',
            'failed': 'Fallido',
            'unknown': 'Desconocido',
        }
        return self.t(tabla.get(str(valor).lower(), str(valor)))

    def voltaje_minimo_gpu_estable(self, frecuencia):
        tabla = {
            1600: 910,
            1700: 920,
            1850: 975,
            2000: 1000,
            2050: 1020,
            2100: 1035,
            2125: 1050,
            2150: 1085,
            2200: 1110,
            2300: 1110,
            2350: 1130,
            2400: 1150,
        }
        return tabla.get(int(frecuencia))

    def voltajes_safe_points(self, datos):
        voltajes = {}
        for punto in datos.get('safe_points_with_voltage', []) or []:
            try:
                voltajes[int(punto.get('frequency'))] = int(punto.get('voltage'))
            except Exception:
                continue
        return voltajes

    def safe_point_gpu_estable(self, frecuencia, voltajes):
        frecuencia = int(frecuencia)
        if frecuencia <= 1500:
            return True
        minimo = self.voltaje_minimo_gpu_estable(frecuencia)
        if minimo is None:
            return False
        actual = voltajes.get(frecuencia)
        return actual is not None and actual >= minimo

    def actualizar_bc250(self, silencioso=False):
        if not hasattr(self, 'bc_servicio'):
            return None
        try:
            datos = self.controlador.estado_bc250()
        except Exception as error:
            self.placa_pill.setText('Sin datos de placa')
            if not silencioso:
                QMessageBox.warning(self, 'BC-250', f'No se pudo leer estado de la placa: {error}')
            return None
        self.ultimo_estado_bc250 = datos
        active = datos.get('service_active') == 'active'
        dbus = bool(datos.get('dbus_ok'))
        rango = f"{datos.get('current_min') or '--'}-{datos.get('current_max') or '--'} MHz"
        allowed = f"{datos.get('allowed_min') or '--'}-{datos.get('allowed_max') or '--'} MHz"
        max_config = datos.get('config_max_frequency') or datos.get('allowed_max') or 1500
        volt_config = datos.get('config_max_voltage')
        self.gpu_max_config_freq = int(max_config or 1500)
        safe_freqs = sorted({int(p.get('frequency')) for p in datos.get('safe_points_with_voltage', []) if p.get('frequency')})
        safe_voltages = self.voltajes_safe_points(datos)
        oc_experimental = bool(getattr(self, 'gpu_oc_experimental', None) and self.gpu_oc_experimental.isChecked())
        for btn in getattr(self, 'gpu_profile_buttons', []):
            freq = btn.property('freq')
            permitido = int(freq) in safe_freqs if freq else True
            if freq and int(freq) > 2000 and not oc_experimental and not self.safe_point_gpu_estable(freq, safe_voltages):
                permitido = False
            btn.setEnabled(permitido)
        if hasattr(self, 'gpu_risk_combo'):
            seleccion_actual = self.gpu_risk_combo.currentData()
            frecuencias_riesgo = [2050, 2100, 2125, 2150, 2200, 2300, 2350, 2400]
            disponibles_riesgo = [f for f in frecuencias_riesgo if f in safe_freqs] if oc_experimental else []
            self.gpu_risk_combo.blockSignals(True)
            self.gpu_risk_combo.clear()
            for freq in disponibles_riesgo:
                self.gpu_risk_combo.addItem(f'{freq} MHz', freq)
            objetivo = seleccion_actual if seleccion_actual in disponibles_riesgo else (2200 if 2200 in disponibles_riesgo else (disponibles_riesgo[0] if disponibles_riesgo else None))
            if objetivo is not None:
                idx = self.gpu_risk_combo.findData(objetivo)
                if idx >= 0:
                    self.gpu_risk_combo.setCurrentIndex(idx)
            self.gpu_risk_combo.blockSignals(False)
            self.gpu_risk_combo.setEnabled(bool(disponibles_riesgo))
            if hasattr(self, 'gpu_risk_apply'):
                self.gpu_risk_apply.setEnabled(bool(disponibles_riesgo))
        sclk = datos.get('sclk_actual')
        volt = datos.get('voltaje_actual')
        busy = datos.get('gpu_busy')
        self.ultimo_gpu_sclk = sclk
        self.ultimo_gpu_volt = volt
        self.ultimo_gpu_busy = busy
        vram_total = datos.get('vram_total') or 0
        vram_usado = datos.get('vram_usado') or 0
        vram_pct = (vram_usado / vram_total * 100) if vram_total else 0
        self.placa_pill.setText((self.t('Activo') if active else self.texto_estado(datos.get('service_active'))) + (' | D-Bus OK' if dbus else ' | D-Bus no disponible'))
        current_min = datos.get('current_min')
        if current_min in (500, 1000, 2000):
            self.gpu_minimo = int(current_min)
            for btn in getattr(self, 'gpu_min_buttons', []):
                btn.setChecked(int(btn.property('minimo')) == self.gpu_minimo)
        servicio_detalle = self.texto_estado(datos.get('service_enabled'))
        if not getattr(self, 'modo_discreto', True):
            servicio_detalle += f" | PID {datos.get('service_main_pid') or '--'}"
        self.bc_servicio.actualizar(self.t('Activo') if active else self.texto_estado(datos.get('service_active')), servicio_detalle, 100 if active else 0)
        self.bc_rango.actualizar(rango, f'D-Bus {allowed} | config max {max_config} MHz', datos.get('current_max') or 0)
        detalle_sclk = f"{self.t('Voltaje')} {'--' if volt is None else str(volt) + ' mV'} | {self.t('carga')} {'--' if busy is None else str(busy) + '%'}"
        self.bc_sclk.actualizar('--' if sclk is None else f'{sclk} MHz', detalle_sclk, min(100, (sclk or 0) / 20))
        self.bc_vram.actualizar(f'{vram_pct:.0f}%' if vram_total else '--', f'{formato_bytes(vram_usado)} de {formato_bytes(vram_total)}', vram_pct)
        if hasattr(self, 'stat_gpu_sclk'):
            self.actualizar_stat(self.stat_gpu_sclk, '--' if sclk is None else f'{sclk} MHz')
            self.actualizar_stat(self.stat_gpu_volt, '--' if volt is None else f'{volt} mV')
            if hasattr(self, 'perf_grafico') and getattr(self, 'recurso_rendimiento', 'gpu') == 'gpu':
                self.actualizar_panel_rendimiento(self.ultimo_rendimiento)
        faltantes = ', '.join(str(p.get('frequency')) for p in datos.get('safe_points_missing_voltage', []))
        errores_voltaje = datos.get('safe_points_voltage_errors', []) or []
        texto_errores_voltaje = '; '.join(
            f"{e.get('previous_frequency')} MHz/{e.get('previous_voltage')} mV > {e.get('frequency')} MHz/{e.get('voltage')} mV"
            for e in errores_voltaje
        )
        duplicadas = ', '.join(str(f) for f in datos.get('safe_points_duplicate_frequencies', []) or [])
        if hasattr(self, 'alerta_oc'):
            if errores_voltaje:
                mensaje_alerta = self.t('Governor/D-Bus caido: curva de voltage invalida.') + f' ({texto_errores_voltaje}). ' + self.t('El voltaje no puede bajar al subir MHz. La app no modifica el TOML; corrige o comenta ese safe-point y reinicia cyan-skillfish-governor-smu.service.')
            elif not dbus and faltantes:
                mensaje_alerta = self.t('Governor/D-Bus caido: safe-points incompletos sin voltage activo.') + f' ({faltantes}). ' + self.t('La app no modifica el TOML; completa o comenta esos bloques y reinicia cyan-skillfish-governor-smu.service.')
            elif not dbus:
                mensaje_alerta = self.t('Governor/D-Bus no disponible. Revisa systemctl status cyan-skillfish-governor-smu y journalctl antes de aplicar perfiles.')
            elif not oc_experimental:
                mensaje_alerta = self.t('Modo seguro: las frecuencias altas solo se habilitan si el TOML iguala la curva estable conocida. Activa "Mostrar OC alto" para ver el combo de 2050+.')
            else:
                mensaje_alerta = self.t('Modo laboratorio OC: puedes probar frecuencias altas aunque el voltaje este debajo de la curva estable. Hazlo por pasos y sin carga 3D al cambiar.')
            self.alerta_oc.setText(self.alerta_gpu_html(mensaje_alerta))
        safe_items = [f"{p.get('frequency')} MHz / {p.get('voltage', '?')} mV" for p in datos.get('safe_points', [])]
        config_display = datos.get('config_path') or '--'
        if getattr(self, 'modo_discreto', True) and config_display not in ('', '--'):
            config_display = '.../' + config_display.split('/')[-1]
        if hasattr(self, 'bc_detail_labels'):
            detalle = self.bc_detail_labels
            valores_detalle = {
                'service': f"{self.texto_estado(datos.get('service_active'))} / {self.texto_estado(datos.get('service_enabled'))}",
                'dbus': self.t('disponible') if dbus else self.t('no disponible'),
                'range': f'{rango}  |  permitido {allowed}',
                'sclk': '--' if sclk is None else f'{sclk} MHz',
                'volt': '--' if volt is None else f'{volt} mV',
                'busy': '--' if busy is None else f'{busy}%',
                'driver': f"{datos.get('driver') or '--'}  {datos.get('vendor') or '--'} / {datos.get('device') or '--'}",
                'config': config_display,
            }
            for clave, valor in valores_detalle.items():
                if clave in detalle:
                    detalle[clave].setText(str(valor))
        if hasattr(self, 'bc_safe_points_text'):
            grupos_safe = []
            for i in range(0, len(safe_items), 3):
                grupos_safe.append('  ' + '   |   '.join(safe_items[i:i + 3]))
            lineas = [
                self.t('Safe-points del TOML:') ,
                *(grupos_safe if grupos_safe else ['  --']),
                '',
                f'{self.t("Maximo registrado:")} {max_config} MHz' + (f' / {volt_config} mV' if volt_config else ''),
                f'{self.t("Safe-points sin voltage:")} {faltantes or "--"}',
                f'{self.t("Curva voltage invalida:")} {texto_errores_voltaje or "--"}',
                f'{self.t("Frecuencias duplicadas:")} {duplicadas or "--"}',
                f'{self.t("Power state:")} {datos.get("power_state") or "--"}',
            ]
            self.bc_safe_points_text.setPlainText('\n'.join(lineas))
        elif hasattr(self, 'tabla_placa'):
            safe = ', '.join(safe_items) or '--'
            filas = [
                ('GPU path', datos.get('gpu_path') or '--'),
                ('Driver', datos.get('driver') or '--'),
                ('Device/Vendor', f"{datos.get('vendor') or '--'} / {datos.get('device') or '--'}"),
                ('Governor service', f"{datos.get('service_active') or '--'} ({datos.get('service_sub') or '--'}), {datos.get('service_enabled') or '--'}"),
                ('D-Bus', self.t('disponible') if dbus else self.t('no disponible')), 
                ('Rango actual', rango),
                ('Rango permitido D-Bus', allowed),
                ('Maximo registrado en config', f'{max_config} MHz' + (f' / {volt_config} mV' if volt_config else '')),
                ('SCLK actual', '--' if sclk is None else f'{sclk} MHz'),
                ('Voltaje actual', '--' if volt is None else f'{volt} mV'),
                ('GPU busy', '--' if busy is None else f'{busy}%'),
                ('Power state', datos.get('power_state') or '--'),
                ('Safe points config', safe),
                ('Safe points sin voltage', faltantes or '--'),
                ('Curva voltage invalida', texto_errores_voltaje or '--'),
                ('Frecuencias duplicadas', duplicadas or '--'),
                ('Config', config_display),
            ]
            self.tabla_placa.setRowCount(len(filas))
            for fila, (campo, valor) in enumerate(filas):
                self.tabla_placa.setItem(fila, 0, QTableWidgetItem(self.t(str(campo))))
                self.tabla_placa.setItem(fila, 1, QTableWidgetItem(self.t(str(valor))))
        tools = datos.get('tools', {})
        if hasattr(self, 'cpu_card_freq'):
            self.cpu_card_freq.actualizar('4 perfiles', '3500, 3700, 3850, 4000 MHz', 0)
            self.cpu_card_vid.actualizar('1000-1275 mV', 'Sin entrada manual', 0)
            self.cpu_card_tool.actualizar('OK' if tools.get('bc250_detect') else 'Local', tools.get('bc250_detect') or tools.get('smu_oc_path') or 'no encontrado', 100 if (tools.get('bc250_detect') or tools.get('smu_oc_exists')) else 0)
            self.cpu_card_temp.actualizar('90 C', 'Fijo en perfiles UI', 0)
        if hasattr(self, 'cu_estado_labels'):
            cu_kind = tools.get('cu_manager_kind') or 'no encontrado'
            cu_manager = tools.get('cu_manager') or 'no encontrado'
            if getattr(self, 'modo_discreto', True) and cu_manager not in ('', 'no encontrado'):
                cu_manager = '.../' + cu_manager.split('/')[-1]
            datos_cu = {
                'manager': ('OK' if tools.get('cu_manager_exists') else 'Falta', f'{cu_kind} | {cu_manager}'),
                'umr': ('OK' if tools.get('umr') else 'Opcional', tools.get('umr') or 'solo si tu flujo lo requiere'),
                'modo': ('Live temporal' if cu_kind == 'WinnieLV/bc250-cu-live-manager' else '--', self.t('Confirmacion manual requerida')),
                'recomendado': ('1500/900', self.t('Recomendado para 40CU')),
            }
            for clave, (valor, detalle_cu) in datos_cu.items():
                item = self.cu_estado_labels.get(clave)
                if item:
                    item['valor'].setText(self.t(str(valor)))
                    item['detalle'].setText(self.t(str(detalle_cu)))
        return datos

    def validar_rango_bc250(self, minimo, maximo):
        self.aviso_gpu_laboratorio = ''
        if minimo > maximo:
            QMessageBox.warning(self, 'BC-250', self.t('El minimo no puede ser mayor que el maximo.'))
            return False
        try:
            estado = self.controlador.estado_bc250()
            amin = estado.get('allowed_min') or 0
            allowed_max = estado.get('allowed_max') or 0
            errores_voltaje = estado.get('safe_points_voltage_errors', []) or []
            if errores_voltaje:
                texto = '; '.join(
                    f"{e.get('previous_frequency')} MHz/{e.get('previous_voltage')} mV > {e.get('frequency')} MHz/{e.get('voltage')} mV"
                    for e in errores_voltaje
                )
                QMessageBox.warning(self, self.t('TOML rechazado por governor'), f'{self.t("La curva de voltage del TOML es invalida:")} {texto}.\n\n{self.t("No aplico perfiles hasta corregir o comentar ese safe-point y reiniciar cyan-skillfish-governor-smu.service.")}')
                return False
            safe_freqs = sorted({int(p.get('frequency')) for p in estado.get('safe_points_with_voltage', []) if p.get('frequency')})
            if maximo not in safe_freqs:
                QMessageBox.warning(self, 'BC-250', f'{maximo} MHz {self.t("no tiene safe-point valido con voltage activo en el TOML. No lo aplico.")}')
                return False
            voltajes = self.voltajes_safe_points(estado)
            voltaje_actual = voltajes.get(int(maximo))
            voltaje_minimo = self.voltaje_minimo_gpu_estable(maximo)
            oc_experimental = bool(getattr(self, 'gpu_oc_experimental', None) and self.gpu_oc_experimental.isChecked())
            if maximo > 1500 and (voltaje_minimo is None or voltaje_actual is None or voltaje_actual < voltaje_minimo):
                if maximo > 2000 and not oc_experimental:
                    QMessageBox.warning(self, self.t('Voltaje GPU insuficiente'), f'{self.t("Bloqueado por posible undervolt en el TOML.")}\n\n{maximo} MHz {self.t("esta en")} {voltaje_actual or "--"} mV, {self.t("pero la curva estable conocida pide al menos")} {voltaje_minimo or "--"} mV.\n\n{self.t("Para pruebas controladas activa \"Mostrar OC alto\".")}')
                    return False
                self.aviso_gpu_laboratorio = f'{maximo} MHz {self.t("esta en")} {voltaje_actual or "--"} mV; {self.t("la curva estable conocida pide")} {voltaje_minimo or "--"} mV. {self.t("Esto es laboratorio de undervolt.")}'
            limite_min_invalido = bool(amin) and minimo < amin
            limite_max_invalido = bool(allowed_max) and maximo > allowed_max
            if limite_min_invalido or limite_max_invalido:
                faltantes = ', '.join(str(p.get('frequency')) for p in estado.get('safe_points_missing_voltage', []))
                extra = f'\n\nAdemas hay safe-points incompletos sin voltage activo: {faltantes}.' if faltantes else ''
                QMessageBox.warning(self, self.t('Governor no permite esa frecuencia ahora'), f'{self.t("El TOML tiene")} {maximo} MHz {self.t("como safe-point, pero D-Bus actualmente permite")} {amin or "--"}-{allowed_max or "--"} MHz.\n\n{self.t("La app no modificara el TOML. Corrige/reinicia cyan-skillfish-governor-smu.service para usar ese valor.")}{extra}')
                return False
            actual_max = estado.get('current_max') or 0
            sclk = estado.get('sclk_actual') or 0
            busy = estado.get('gpu_busy')
            bajada = actual_max - maximo if actual_max else 0
            carga_alta = busy is not None and busy >= 35
            salto_brusco = bajada >= 500 or (sclk >= 1800 and maximo <= 1500)
            if bajada > 0 and salto_brusco and carga_alta:
                QMessageBox.warning(self, self.t('Bajada brusca bloqueada'), f'{self.t("La GPU parece estar bajo carga")} ({busy}%) {self.t("y quieres bajar de")} {actual_max} MHz {self.t("hacia")} {maximo} MHz.\n\n{self.t("Deten el juego/prueba de estres primero o baja por pasos: 2400->2200->2000->1850->1500->1000. Esto evita saltos fuertes de voltage/frecuencia que pueden congelar la pantalla.")}')
                return False
            if bajada >= 700:
                r = QMessageBox.warning(self, self.t('Bajada brusca de frecuencia'), f'{self.t("Vas a bajar de")} {actual_max} MHz {self.t("hacia")} {maximo} MHz. {self.t("Si hay juego, FurMark o carga 3D activa, detente antes.")}\n\n{self.t("Recomendado: baja por pasos y espera unos segundos entre cambios. Continuar?")}', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if r != QMessageBox.StandardButton.Yes:
                    return False
        except Exception as error:
            QMessageBox.warning(self, 'BC-250', f'{self.t("No se pudo validar contra safe-points del TOML:")} {error}')
            return False
        return True

    def confirmar_zona_riesgo_gpu(self, maximo):
        if maximo <= 1500:
            return True
        texto = (
            f'{self.t("Vas a usar")} {maximo} MHz. '
            f'{self.t("La app verifico que el TOML tenga un voltaje igual o superior a la curva estable conocida, pero sigue siendo OC.")}\n\n'
            f'{self.t("No cambies frecuencias bajo FurMark/juego/carga 3D. Continuar?")}'
        )
        r = QMessageBox.warning(self, self.t('Zona de riesgo GPU'), texto, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return False
        r2 = QMessageBox.question(self, self.t('Confirmacion final'), self.t('Confirmas que no hay prueba de estres activa y que entiendes el riesgo de cuelgue/apagon?'), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r2 != QMessageBox.StandardButton.Yes:
            return False
        r3 = QMessageBox.question(self, self.t('Ultima confirmacion'), self.t('Ultima confirmacion: no hay juego, FurMark ni prueba 3D corriendo y tienes forma de reiniciar si se congela?'), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        return r3 == QMessageBox.StandardButton.Yes


    def aplicar_perfil_inteligente(self, clave):
        perfiles = {
            'seguro': (500, 1500, 'Perfil inteligente Seguro'),
            'gaming': (1000, 1850, 'Perfil inteligente Gaming'),
            'cu40': (self.minimo_gpu_seleccionado(), 1500, 'Perfil inteligente 40CU recomendado'),
            'benchmark': (1000, 2000, 'Perfil inteligente Benchmark controlado'),
            'recuperacion': (500, 1000, 'Perfil inteligente Recuperacion'),
        }
        if clave not in perfiles:
            QMessageBox.warning(self, self.t('Perfiles inteligentes'), f'{self.t("Perfil no reconocido:")} {clave}')
            return
        minimo, maximo, nombre = perfiles[clave]
        self.registrar_evento('perfil', 'info', 'Perfil inteligente seleccionado', nombre, {'perfil': clave, 'minimo': minimo, 'maximo': maximo})
        self.aplicar_perfil_bc250(minimo, maximo, nombre)

    def aplicar_gpu_riesgo_combo(self):
        if not hasattr(self, 'gpu_risk_combo'):
            return
        frecuencia = self.gpu_risk_combo.currentData()
        if frecuencia is None:
            QMessageBox.warning(self, 'BC-250', self.t('No hay frecuencia alta disponible con safe-point y voltage activo en el TOML.'))
            return
        self.aplicar_perfil_bc250(self.minimo_gpu_seleccionado(), int(frecuencia), f'OC alto {int(frecuencia)} MHz')

    def aplicar_perfil_bc250(self, minimo, maximo, nombre):
        if not self.validar_rango_bc250(minimo, maximo):
            return
        if int(maximo) >= 1850 or int(minimo) >= 2000:
            extra = f'\n\n{self.aviso_gpu_laboratorio}' if getattr(self, 'aviso_gpu_laboratorio', '') else ''
            texto = (
                f'{self.t("Perfil")}: {self.t(nombre)}\n'
                f'{self.t("Rango")}: {minimo}-{maximo} MHz\n\n'
                f'{self.t("Se aplicara por D-Bus del governor.")}\n'
                f'{self.t("No cambies frecuencia con FurMark/juego/carga 3D activa.")}\n'
                f'{self.t("Si hay cuelgue, reinicia y sube nivel en Lab voltaje.")}'
                f'{extra}\n\n'
                f'{self.t("Continuar?")}'
            )
            respuesta = QMessageBox.warning(self, self.t('Aplicar perfil GPU'), texto, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if respuesta != QMessageBox.StandardButton.Yes:
                return
        try:
            self.controlador.aplicar_rango_bc250(minimo, maximo)
            self.registrar_evento('gpu', 'warning' if maximo >= 2000 else 'info', 'Perfil GPU aplicado', f'{nombre}: {minimo}-{maximo} MHz', {'minimo': minimo, 'maximo': maximo, 'perfil': nombre})
            self.actualizar_bc250()
        except Exception as error:
            QMessageBox.warning(self, 'BC-250', f'{self.t("No se pudo aplicar el rango:")} {error}')

    def aplicar_cpu_oc(self, frecuencia, vid, temp):
        texto = (
            f'{self.t("Se ejecutara")} bc250-detect --frequency {frecuencia} --vid {vid} --temp {temp} --keep.\n\n'
            f'{self.t("Es temporal, no instala el servicio CPU.")}\n'
            f'{self.t("La UI bloquea mas de 4000 MHz y mas de 1275 mV por seguridad.")}\n'
            f'{self.t("Puede congelar la PC si tu placa no es estable. Deten pruebas pesadas antes de cambiar.")}\n\n'
            f'{self.t("Continuar?")}'
        )
        r = QMessageBox.warning(self, self.t('CPU OC temporal'), texto, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        try:
            self.iniciar_cpu_oc_embebido(frecuencia, vid, temp)
            self.registrar_evento('cpu', 'warning', 'CPU OC temporal', f'bc250-detect {frecuencia} MHz / {vid} mV / temp {temp}', {'frecuencia': frecuencia, 'vid': vid, 'temp': temp})
        except Exception as error:
            QMessageBox.warning(self, 'CPU OC', f'{self.t("No se pudo ejecutar bc250-detect:")} {error}')

    def iniciar_cpu_oc_embebido(self, frecuencia, vid, temp):
        if self.cpu_oc_process and self.cpu_oc_process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.warning(self, 'CPU OC', self.t('Ya hay un proceso CPU OC en ejecucion. Espera a que termine.'))
            return
        comando = self.controlador.comando_cpu_oc_temporal_embebido(frecuencia, vid, temp)
        if not comando:
            raise RuntimeError('No se pudo preparar el comando CPU OC')
        if hasattr(self, 'cpu_oc_console'):
            self.cpu_oc_console.setPlainText('')
            self.cpu_oc_console.appendPlainText(self.t('== Ejecutando CPU OC temporal =='))
            self.cpu_oc_console.appendPlainText(self.t('Se abrira la autenticacion grafica de Polkit si hace falta.'))
            self.cpu_oc_console.appendPlainText(self.t('No cierres la app. El proceso puede tardar varios segundos.'))
            self.cpu_oc_console.appendPlainText(self.t('Monitorea CPU MHz, temperatura y voltaje en el monitor superior.'))
            self.cpu_oc_console.appendPlainText(self.t('Si la salida queda quieta pero la frecuencia sube, el proceso sigue trabajando.'))
            self.cpu_oc_console.appendPlainText('')
        self.cpu_oc_process = QProcess(self)
        self.cpu_oc_process.setProgram(comando[0])
        self.cpu_oc_process.setArguments(comando[1:])
        self.cpu_oc_process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.cpu_oc_process.readyReadStandardOutput.connect(self.leer_salida_cpu_oc)
        self.cpu_oc_process.finished.connect(self.finalizar_cpu_oc_embebido)
        self.cpu_oc_process.start()
        if not self.cpu_oc_process.waitForStarted(3000):
            raise RuntimeError('No se pudo iniciar el proceso CPU OC')
        self.cpu_oc_inicio = time.time()
        self.cpu_oc_timer = QTimer(self)
        self.cpu_oc_timer.timeout.connect(self.pulso_cpu_oc_embebido)
        self.cpu_oc_timer.start(3000)

    def pulso_cpu_oc_embebido(self):
        if not self.cpu_oc_process or self.cpu_oc_process.state() == QProcess.ProcessState.NotRunning:
            return
        segundos = int(time.time() - self.cpu_oc_inicio)
        datos = self.ultimo_rendimiento or {}
        cpu_mhz = datos.get('cpu_freq')
        cpu_temp = datos.get('cpu_temp')
        partes = [f'[{segundos}s] {self.t("CPU OC sigue ejecutandose")}' ]
        if cpu_mhz:
            partes.append(f'CPU {cpu_mhz:.0f} MHz')
        if cpu_temp:
            partes.append(f'Temp {cpu_temp:.1f} C')
        partes.append(self.t('espera a que finalice...'))
        if hasattr(self, 'cpu_oc_console'):
            self.cpu_oc_console.appendPlainText(' | '.join(partes))

    def leer_salida_cpu_oc(self):
        if not self.cpu_oc_process:
            return
        texto = bytes(self.cpu_oc_process.readAllStandardOutput()).decode('utf-8', errors='replace')
        if texto and hasattr(self, 'cpu_oc_console'):
            self.cpu_oc_console.moveCursor(QTextCursor.MoveOperation.End)
            self.cpu_oc_console.insertPlainText(texto)
            self.cpu_oc_console.moveCursor(QTextCursor.MoveOperation.End)

    def finalizar_cpu_oc_embebido(self, codigo, estado):
        if self.cpu_oc_timer:
            self.cpu_oc_timer.stop()
            self.cpu_oc_timer = None
        if hasattr(self, 'cpu_oc_console'):
            self.cpu_oc_console.appendPlainText('')
            self.cpu_oc_console.appendPlainText(f'== CPU OC finalizado con codigo {codigo} ==')
        if codigo == 0:
            QMessageBox.information(self, 'CPU OC', self.t('CPU OC temporal aplicado. Revisa temperaturas y estabilidad.'))
        else:
            QMessageBox.warning(self, 'CPU OC', self.t('CPU OC termino con error. Revisa la consola embebida.'))
        self.actualizar_bc250(silencioso=True)

    def aplicar_cpu_oc_persistente(self):
        texto = (
            'ADVERTENCIA EXTREMA\n\n'
            'Esta accion instala el overclock de CPU como servicio persistente de systemd.\n'
            'Si el overclock no es estable, puedes perder datos, dañar la instalacion o dejar el sistema sin arrancar correctamente.\n\n'
            'Antes de aceptar:\n'
            '- Haz copia de seguridad.\n'
            '- Prueba estabilidad con juegos y pruebas reales.\n'
            '- Verifica temperaturas, voltaje y apagones.\n'
            '- Asegurate de que el overclock temporal funciona bien.\n\n'
            'No nos hacemos responsables por perdida de informacion, corrupcion del sistema o daños.\n\n'
            'Para continuar, en el siguiente cuadro escribe exactamente CONFIRMO.'
        )
        r = QMessageBox.warning(self, self.t('CPU OC persistente'), self.t(texto), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        confirmacion, ok = self.pedir_texto('CPU OC persistente', 'Escribe CONFIRMO para instalar el servicio persistente:')
        if not ok:
            return
        if str(confirmacion).strip() != 'CONFIRMO':
            QMessageBox.warning(self, self.t('CPU OC persistente'), self.t('Confirmacion invalida. Debes escribir exactamente CONFIRMO.'))
            return
        try:
            self.iniciar_cpu_oc_persistente()
            self.registrar_evento('cpu', 'critical', 'CPU OC persistente', 'Instalacion de servicio bc250-smu-oc solicitada', {})
        except Exception as error:
            QMessageBox.warning(self, self.t('CPU OC persistente'), f'{self.t("No se pudo instalar persistencia CPU OC:")} {error}')

    def iniciar_cpu_oc_persistente(self):
        if self.cpu_oc_process and self.cpu_oc_process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.warning(self, 'CPU OC', self.t('Ya hay un proceso CPU OC en ejecucion. Espera a que termine.'))
            return
        comando = self.controlador.comando_cpu_oc_persistente_embebido()
        if hasattr(self, 'cpu_oc_console'):
            self.cpu_oc_console.setPlainText('')
            self.cpu_oc_console.appendPlainText(self.t('== Instalando CPU OC persistente =='))
            self.cpu_oc_console.appendPlainText(self.t('Usando overclock.conf generado por bc250-detect.'))
            self.cpu_oc_console.appendPlainText(self.t('Se abrira Polkit para permisos de administrador.'))
            self.cpu_oc_console.appendPlainText('')
        self.cpu_oc_process = QProcess(self)
        self.cpu_oc_process.setProgram(comando[0])
        self.cpu_oc_process.setArguments(comando[1:])
        self.cpu_oc_process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.cpu_oc_process.readyReadStandardOutput.connect(self.leer_salida_cpu_oc)
        self.cpu_oc_process.finished.connect(self.finalizar_cpu_oc_persistente)
        self.cpu_oc_process.start()
        if not self.cpu_oc_process.waitForStarted(3000):
            raise RuntimeError('No se pudo iniciar la instalacion persistente')

    def finalizar_cpu_oc_persistente(self, codigo, estado):
        if hasattr(self, 'cpu_oc_console'):
            self.cpu_oc_console.appendPlainText('')
            self.cpu_oc_console.appendPlainText(f'== Persistencia CPU OC finalizada con codigo {codigo} ==')
        if codigo == 0:
            QMessageBox.information(self, self.t('CPU OC persistente'), self.t('Servicio persistente instalado. Reinicia solo despues de verificar que entiendes el riesgo.'))
        else:
            QMessageBox.warning(self, self.t('CPU OC persistente'), self.t('La instalacion persistente termino con error. Revisa la consola embebida.'))
        self.actualizar_cpu_oc_persistente_status(silencioso=True)

    def actualizar_cpu_oc_persistente_status(self, silencioso=False):
        if not hasattr(self, 'cpu_persist_estado_valor'):
            return
        try:
            estado = self.controlador.estado_cpu_oc_persistente()
        except Exception as error:
            self.cpu_persist_servicio_valor.setText('Error')
            self.cpu_persist_servicio_detalle.setText(str(error))
            self.cpu_persist_estado_valor.setText('--')
            self.cpu_persist_estado_detalle.setText('--')
            self.cpu_persist_config_valor.setText('--')
            self.cpu_persist_config_detalle.setText('--')
            if not silencioso:
                QMessageBox.warning(self, self.t('CPU OC persistente'), f'{self.t("No se pudo leer status:")} {error}')
            return

        activo = estado.get('active') or 'unknown'
        habilitado = estado.get('enabled') or 'unknown'
        existe = bool(estado.get('exists'))
        config = bool(estado.get('config_exists'))
        servicio = estado.get('service') or 'bc250-smu-oc.service'
        texto_estado = self.t(estado.get('ui_state') or f'{activo} / {habilitado}')
        detalle = 'Servicio systemd encontrado' if existe else 'Servicio no instalado'
        detalle_estado = self.t(estado.get('ui_detail') or ('Se aplicara al iniciar' if habilitado == 'enabled' else 'No arranca automaticamente'))

        self.cpu_persist_servicio_valor.setText(servicio)
        self.cpu_persist_servicio_detalle.setText(self.t(detalle))
        self.cpu_persist_estado_valor.setText(texto_estado)
        self.cpu_persist_estado_detalle.setText(detalle_estado)
        self.cpu_persist_config_valor.setText('/etc/bc250-smu-oc.conf' if config else self.t('No encontrada'))
        self.cpu_persist_config_detalle.setText(self.t('Config persistente presente' if config else 'Primero instala persistencia'))
        if hasattr(self, 'btn_cpu_persist_desactivar'):
            self.btn_cpu_persist_desactivar.setEnabled(existe or habilitado == 'enabled' or activo == 'active')
        if not silencioso:
            resumen = estado.get('status_text') or f'{servicio}: {texto_estado}'
            if hasattr(self, 'cpu_oc_console'):
                self.cpu_oc_console.appendPlainText('')
                self.cpu_oc_console.appendPlainText(self.t('== Status CPU OC persistente =='))
                if estado.get('oneshot_ok'):
                    self.cpu_oc_console.appendPlainText(self.t('Nota: inactive/dead es normal en este servicio one-shot cuando ExecStart termina con SUCCESS.'))
                    self.cpu_oc_console.appendPlainText(self.t('El OC ya fue aplicado en este arranque y volvera a aplicarse al iniciar si sigue enabled.'))
                    self.cpu_oc_console.appendPlainText('')
                self.cpu_oc_console.appendPlainText(resumen)

    def desactivar_cpu_oc_persistente(self):
        texto = (
            'Se detendra y deshabilitara bc250-smu-oc.service.\n\n'
            'Esto evita que el OC de CPU persistente se aplique al iniciar el sistema.\n'
            'No borra /etc/bc250-smu-oc.conf, por si quieres revisar la configuracion despues.\n\n'
            'Continuar?'
        )
        r = QMessageBox.warning(self, self.t('CPU OC persistente'), self.t(texto), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        try:
            self.iniciar_cpu_oc_desactivar_persistente()
            self.registrar_evento('cpu', 'warning', 'CPU OC persistente', 'Desactivacion de servicio bc250-smu-oc solicitada', {})
        except Exception as error:
            QMessageBox.warning(self, self.t('CPU OC persistente'), f'{self.t("No se pudo desactivar persistencia CPU OC:")} {error}')

    def iniciar_cpu_oc_desactivar_persistente(self):
        if self.cpu_oc_process and self.cpu_oc_process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.warning(self, 'CPU OC', self.t('Ya hay un proceso CPU OC en ejecucion. Espera a que termine.'))
            return
        comando = self.controlador.comando_cpu_oc_desactivar_persistente_embebido()
        if hasattr(self, 'cpu_oc_console'):
            self.cpu_oc_console.setPlainText('')
            self.cpu_oc_console.appendPlainText(self.t('== Desactivando CPU OC persistente =='))
            self.cpu_oc_console.appendPlainText(self.t('Se abrira Polkit para permisos de administrador.'))
            self.cpu_oc_console.appendPlainText('')
        self.cpu_oc_process = QProcess(self)
        self.cpu_oc_process.setProgram(comando[0])
        self.cpu_oc_process.setArguments(comando[1:])
        self.cpu_oc_process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.cpu_oc_process.readyReadStandardOutput.connect(self.leer_salida_cpu_oc)
        self.cpu_oc_process.finished.connect(self.finalizar_cpu_oc_desactivar_persistente)
        self.cpu_oc_process.start()
        if not self.cpu_oc_process.waitForStarted(3000):
            raise RuntimeError('No se pudo iniciar la desactivacion persistente')

    def finalizar_cpu_oc_desactivar_persistente(self, codigo, estado):
        if hasattr(self, 'cpu_oc_console'):
            self.cpu_oc_console.appendPlainText('')
            self.cpu_oc_console.appendPlainText(f'== Desactivacion CPU OC persistente finalizada con codigo {codigo} ==')
        if codigo == 0:
            QMessageBox.information(self, self.t('CPU OC persistente'), self.t('Servicio persistente desactivado. No se aplicara al iniciar el sistema.'))
        else:
            QMessageBox.warning(self, self.t('CPU OC persistente'), self.t('La desactivacion persistente termino con error. Revisa la consola embebida.'))
        self.actualizar_cpu_oc_persistente_status(silencioso=True)

    def actualizar_cpu_custom_ui(self):
        activo = bool(getattr(self, 'cpu_custom_enable', None) and self.cpu_custom_enable.isChecked())
        for nombre in ['cpu_custom_freq', 'cpu_custom_vid', 'cpu_custom_temp', 'cpu_custom_apply']:
            if hasattr(self, nombre):
                getattr(self, nombre).setEnabled(activo)

    def aplicar_cpu_oc_personalizado(self):
        if not all(hasattr(self, nombre) for nombre in ['cpu_custom_freq', 'cpu_custom_vid', 'cpu_custom_temp']):
            return
        if not getattr(self, 'cpu_custom_enable', None) or not self.cpu_custom_enable.isChecked():
            QMessageBox.warning(self, self.t('CPU OC temporal'), self.t('Primero marca "Habilitar personalizado" para evitar aplicar un perfil manual por accidente.'))
            return
        frecuencia = int(self.cpu_custom_freq.value())
        vid = int(self.cpu_custom_vid.value())
        temp = int(self.cpu_custom_temp.value())
        self.aplicar_cpu_oc(frecuencia, vid, temp)

    def ejecutar_cu_manager(self, accion):
        textos = {
            'enable40': 'Se ejecutara bc250-cu-live-manager para enrutar todos los WGP/CU en vivo. Es temporal salvo que guardes/instales servicio dentro del manager.',
            'stock': 'Se restaurara en vivo el despacho factory/24CU usando bc250-cu-live-manager.',
            'menu': 'Se abrira el menu oficial de bc250-cu-live-manager para editar tabla, guardar perfil personalizado e instalar el servicio si lo decides.',
        }
        titulo = 'BC-250 40CU'
        tipo = QMessageBox.warning if accion == 'enable40' else QMessageBox.question
        r = tipo(self, self.t(titulo), self.t(textos[accion]) + '\n\n' + self.t('Continuar?'), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        try:
            resultado = self.controlador.ejecutar_cu_manager(accion)
            self.registrar_evento('40cu', 'warning' if accion == 'enable40' else 'info', 'Acción 40CU', accion, {'accion': accion})
            if accion == 'enable40':
                QMessageBox.information(self, self.t(titulo), self.t('40 unidades de computo activadas.'))
            elif accion == 'stock':
                QMessageBox.information(self, self.t(titulo), self.t('Se restauro el perfil de 24 unidades de computo.'))
            if accion in ('enable40', 'stock'):
                if hasattr(self, 'cu_dashboard_text') and resultado:
                    self.cu_dashboard_text.setPlainText(str(resultado).strip())
                self.actualizar_bc250(silencioso=True)
        except Exception as error:
            if self.error_umr_faltante(error):
                self.avisar_umr_faltante()
            else:
                QMessageBox.warning(self, self.t(titulo), f'{self.t("No se pudo ejecutar accion 40CU:")} {self.t(str(error))}')

    def actualizar_mapa_cu(self):
        if not hasattr(self, 'cu_map_text'):
            return
        self.cu_map_text.setPlainText('Leyendo mapa CU...')
        try:
            texto = self.controlador.obtener_mapa_cu()
            self.cu_map_text.setPlainText(texto.strip() or 'El script no devolvio salida.')
            self.registrar_evento('40cu', 'info', 'Mapa CU actualizado', 'Lectura de cu_map.sh completada', {})
        except Exception as error:
            self.cu_map_text.setPlainText(
                self.t('No se pudo leer el mapa CU.') + '\n\n'
                + self.t(str(error)) + '\n\n'
                + self.t('El mapa CU heredado no es necesario para el live-manager. Usa Preparar dependencias si necesitas reinstalar herramientas.')
            )


    def actualizar_dashboard_cu(self):
        if not hasattr(self, 'cu_dashboard_text'):
            return
        self.cu_dashboard_text.setPlainText(self.t('Leyendo dashboard 40CU...'))
        try:
            texto = self.controlador.obtener_dashboard_cu()
            self.cu_dashboard_text.setPlainText(texto.strip() or self.t('El dashboard no devolvio salida.'))
            self.registrar_evento('40cu', 'info', 'Dashboard 40CU actualizado', 'Live-manager dashboard reading completed', {})
        except Exception as error:
            texto_error = str(error)
            if self.error_umr_faltante(texto_error):
                mensaje = self.texto_umr_faltante()
            else:
                mensaje = self.t('No se pudo leer el dashboard 40CU.') + '\n\n' + self.t(texto_error)
            self.cu_dashboard_text.setPlainText(mensaje)

    def error_umr_faltante(self, error):
        texto = str(error).lower()
        pistas = [
            'falta umr',
            'umr not found',
            'command not found: umr',
            'umr: command not found',
            'no such file or directory: umr',
        ]
        return any(pista in texto for pista in pistas)

    def texto_umr_faltante(self):
        return (
            self.t('Falta UMR en el sistema.') + '\n\n'
            + self.t('UMR es la herramienta que bc250-cu-live-manager usa para leer y escribir registros AMD/AMDGPU. Sin UMR no se puede refrescar el dashboard live ni activar/restaurar 40CU desde la interfaz.') + '\n\n'
            + self.t('Solucion: pulsa el boton "Instalar UMR" en el panel 40CU. La app detectara tu distribucion e intentara instalar el paquete correspondiente.')
        )

    def avisar_umr_faltante(self):
        texto = (
            self.texto_umr_faltante()
            + '\n\n'
            + self.t('Quieres abrir el instalador de UMR ahora?')
        )
        r = QMessageBox.question(self, self.t('Instalar UMR'), texto, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r == QMessageBox.StandardButton.Yes:
            self.instalar_umr()

    def instalar_dependencias_bc250(self):
        texto = (
            'Se abrira una terminal para preparar dependencias faltantes.\n\n'
            '- cyan-skillfish-governor-smu: instala paquete si falta.\n'
            '- bc250_smu_oc: clona/actualiza y se ejecuta directo sin pip.\n'
            '- bc250-cu-live-manager: clona/actualiza la herramienta 40CU principal.\n'
            '- UMR: muestra o ejecuta el metodo recomendado si falta.\n\n'
            'La terminal mostrara creditos y enlaces oficiales. BC250 Control Center no es propietario de esas herramientas; cada repositorio pertenece a sus autores.\n\n'
            'No activa CPU OC como servicio, no modifica el TOML y no aplica frecuencias. Continuar?'
        )
        r = QMessageBox.question(self, self.t('Preparar dependencias BC250'), self.t(texto), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        try:
            self.controlador.instalar_dependencias_bc250()
            self.registrar_evento('dependencias', 'info', 'Preparar dependencias BC250', 'Se abrió terminal para preparar dependencias faltantes.', {})
        except Exception as error:
            QMessageBox.warning(self, self.t('Preparar dependencias BC250'), self.t(str(error)))

    def mostrar_status_governor(self):
        try:
            texto = self.controlador.status_governor()
        except Exception as error:
            QMessageBox.warning(self, self.t('Status governor'), f'{self.t("No se pudo leer status:")} {self.t(str(error))}')
            return
        dialogo = QDialog(self)
        dialogo.setWindowTitle(self.t('Status governor'))
        layout = QVBoxLayout(dialogo)
        caja = QPlainTextEdit()
        caja.setObjectName('DetailText')
        caja.setReadOnly(True)
        caja.setPlainText(texto or self.t('Status governor no disponible.'))
        caja.setMinimumSize(680, 360)
        layout.addWidget(caja)
        cerrar = QPushButton(self.t('Cerrar'))
        cerrar.clicked.connect(dialogo.accept)
        layout.addWidget(cerrar, alignment=Qt.AlignmentFlag.AlignRight)
        dialogo.resize(760, 460)
        dialogo.exec()


    def controlar_governor(self, accion):
        if accion == 'activar':
            titulo = 'Activar governor'
            detalle = (
                'Se ejecutara:\n\n'
                'sudo systemctl enable --now cyan-skillfish-governor-smu.service\n\n'
                'Esto inicia el governor ahora y lo deja habilitado para el arranque. '
                'No modifica el TOML ni aplica OC por si solo. Continuar?'
            )
            nivel = 'info'
        elif accion == 'desactivar':
            titulo = 'Desactivar governor'
            detalle = (
                'Se ejecutara:\n\n'
                'sudo systemctl disable --now cyan-skillfish-governor-smu.service\n\n'
                'Esto detiene el governor ahora y evita que arranque automaticamente. '
                'La app no podra aplicar rangos GPU por D-Bus mientras este apagado. Continuar?'
            )
            nivel = 'warning'
        else:
            QMessageBox.warning(self, self.t('Governor'), self.t('Accion governor no valida.'))
            return
        r = QMessageBox.warning(self, self.t(titulo), self.t(detalle), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        try:
            self.controlador.controlar_governor(accion)
            self.ultimo_bc250_refresh = 0
            self.registrar_evento('governor', nivel, titulo, accion, {'accion': accion})
            QTimer.singleShot(1500, lambda: self.actualizar_bc250(silencioso=True))
        except Exception as error:
            QMessageBox.warning(self, titulo, str(error))

    def curva_base_fallo_gpu(self):
        return {
            1850: 930,
            2000: 960,
            2050: 980,
            2100: 1000,
            2125: 1020,
            2150: 1035,
            2200: 1050,
            2300: 1110,
            2350: 1130,
            2400: 1150,
        }

    def curva_estable_gpu(self):
        return {
            1850: 975,
            2000: 1000,
            2050: 1020,
            2100: 1035,
            2125: 1050,
            2150: 1085,
            2200: 1110,
            2300: 1110,
            2350: 1130,
            2400: 1150,
        }

    def voltaje_laboratorio(self, frecuencia, nivel):
        base = self.curva_base_fallo_gpu().get(int(frecuencia))
        estable = self.curva_estable_gpu().get(int(frecuencia))
        if base is None or estable is None:
            return None
        return min(base + int(nivel) * 10, estable)


    def detectar_nivel_laboratorio_gpu(self, voltajes):
        frecuencias = [1850, 2000, 2050, 2100, 2125, 2150, 2200]
        mejor_nivel = 0
        mejor_error = None
        for nivel in range(0, 7):
            error = 0
            muestras = 0
            for freq in frecuencias:
                actual = voltajes.get(freq)
                esperado = self.voltaje_laboratorio(freq, nivel)
                if actual is None or esperado is None:
                    continue
                error += abs(actual - esperado)
                muestras += 1
            if muestras == 0:
                continue
            if mejor_error is None or error < mejor_error:
                mejor_error = error
                mejor_nivel = nivel
        return mejor_nivel

    def abrir_laboratorio_voltaje_gpu(self):
        try:
            estado = self.controlador.estado_bc250()
        except Exception as error:
            QMessageBox.warning(self, self.t('Lab voltaje GPU'), f'{self.t("No se pudo leer el TOML actual:")} {error}')
            return
        dialogo = QDialog(self)
        dialogo.setWindowTitle(self.t('Lab voltaje GPU'))
        dialogo.resize(860, 600)
        layout = QVBoxLayout(dialogo)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        titulo = QLabel(self.t('Laboratorio de voltaje GPU'))
        titulo.setObjectName('PageTitle')
        subtitulo = QLabel(self.t('Nivel 0 usa los valores default del governor. Los niveles suben +10 mV por paso. Personalizado solo modifica mV y tiene limite duro de 1150 mV.'))
        subtitulo.setObjectName('Muted')
        subtitulo.setWordWrap(True)
        layout.addWidget(titulo)
        layout.addWidget(subtitulo)

        controles = QFrame()
        controles.setObjectName('InfoBox')
        cl = QHBoxLayout(controles)
        cl.setContentsMargins(10, 8, 10, 8)
        cl.setSpacing(8)
        cl.addWidget(QLabel(self.t('Nivel')))
        combo = QComboBox()
        combo.addItem(self.t('Nivel 0  (Default governor)'), 0)
        for nivel in range(1, 7):
            combo.addItem(f'{self.t("Nivel")} {nivel}  (Default +{nivel * 10} mV)', nivel)
        combo.addItem(self.t('Personalizado'), -1)
        voltajes = self.voltajes_safe_points(estado)
        nivel_detectado = self.detectar_nivel_laboratorio_gpu(voltajes)
        combo.setCurrentIndex(nivel_detectado)
        cl.addWidget(combo)
        cl.addStretch(1)
        aplicar = QPushButton(self.t('Aplicar'))
        aplicar.setObjectName('DangerButton')
        cl.addWidget(aplicar)
        layout.addWidget(controles)

        tabla = QTableWidget(0, 6)
        tabla.setHorizontalHeaderLabels([self.t('MHz'), self.t('Actual'), self.t('Nivel'), self.t('Personalizado'), self.t('Techo estable'), self.t('Margen')])
        tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(tabla, 1)

        aviso = QLabel(self.t('El Lab no debe cambiar el rango min/max: el script preserva el rango D-Bus anterior tras reiniciar el governor. Cambia voltajes sin FurMark/juego activo.'))
        aviso.setObjectName('WarningTextCompact')
        aviso.setWordWrap(True)
        layout.addWidget(aviso)

        frecuencias = [1850, 2000, 2050, 2100, 2125, 2150, 2200, 2300, 2350, 2400]
        spinboxes = {}
        custom_values = {}

        def llenar_tabla():
            nivel = int(combo.currentData())
            personalizado = nivel == -1
            tabla.setRowCount(len(frecuencias))
            estable = self.curva_estable_gpu()
            for fila, freq in enumerate(frecuencias):
                actual = voltajes.get(freq)
                nivel_base = nivel_detectado if personalizado else nivel
                nuevo = self.voltaje_laboratorio(freq, nivel_base)
                techo = estable.get(freq)
                if freq not in custom_values:
                    custom_values[freq] = actual or nuevo or 900
                if not personalizado and nuevo is not None:
                    custom_values[freq] = nuevo
                elegido = custom_values.get(freq)
                margen = '--' if elegido is None or techo is None else f'{elegido - techo:+d} mV'
                tabla.setItem(fila, 0, QTableWidgetItem(str(freq)))
                tabla.setItem(fila, 1, QTableWidgetItem('--' if actual is None else f'{actual} mV'))
                tabla.setItem(fila, 2, QTableWidgetItem('--' if nuevo is None else f'{nuevo} mV'))
                spin = QSpinBox()
                spin.setRange(600, 1150)
                spin.setSuffix(' mV')
                spin.setSingleStep(5)
                spin.setValue(int(elegido))
                spin.setEnabled(personalizado)
                spin.valueChanged.connect(lambda valor, f=freq: custom_values.__setitem__(f, int(valor)))
                spinboxes[freq] = spin
                tabla.setCellWidget(fila, 3, spin)
                tabla.setItem(fila, 4, QTableWidgetItem('--' if techo is None else f'{techo} mV'))
                tabla.setItem(fila, 5, QTableWidgetItem(margen))

        def aplicar_nivel():
            nivel = int(combo.currentData())
            personalizado = nivel == -1
            if personalizado:
                valores = {freq: int(spinboxes[freq].value()) for freq in frecuencias if freq in spinboxes}
                texto = (
                    'Se aplicara una curva personalizada.\n\n'
                    'Solo se modifican voltajes mV en safe-points existentes del TOML.\n'
                    'No se permite ningun valor mayor a 1150 mV.\n'
                    'El script preserva el rango D-Bus anterior tras reiniciar el governor.\n\n'
                    'Continuar?'
                )
            else:
                valores = None
                etiqueta = 'Default governor' if nivel == 0 else f'Default +{nivel * 10} mV'
                texto = (
                    f'{self.t("Se aplicara Nivel")} {nivel} ({etiqueta}).\n\n'
                    f'{self.t("Solo se modifican voltajes mV en safe-points existentes del TOML.")}\n'
                    f'{self.t("El script preserva el rango D-Bus anterior tras reiniciar el governor.")}\n\n'
                    f'{self.t("Continuar?")}'
                )
            mensaje = self.t(texto) if personalizado else texto
            r = QMessageBox.warning(dialogo, self.t('Aplicar Lab voltaje'), mensaje, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if r != QMessageBox.StandardButton.Yes:
                return
            try:
                if personalizado:
                    self.controlador.aplicar_laboratorio_voltaje_gpu_personalizado(valores)
                    self.registrar_evento('gpu', 'warning', 'Lab voltaje personalizado', 'Personalizado', valores)
                    QMessageBox.information(dialogo, self.t('Lab voltaje GPU'), self.t('Lab voltaje personalizado aplicado correctamente.'))
                else:
                    self.controlador.aplicar_laboratorio_voltaje_gpu(nivel)
                    self.registrar_evento('gpu', 'warning', 'Lab voltaje aplicado', f'Nivel {nivel}', {'nivel': nivel})
                    QMessageBox.information(dialogo, self.t('Lab voltaje GPU'), self.t('Lab voltaje aplicado correctamente.'))
                QTimer.singleShot(1800, lambda: self.actualizar_bc250(silencioso=True))
            except Exception as error:
                QMessageBox.warning(dialogo, self.t('Lab voltaje GPU'), str(error))

        combo.currentIndexChanged.connect(llenar_tabla)
        aplicar.clicked.connect(aplicar_nivel)
        llenar_tabla()
        dialogo.exec()

    def instalar_cpu_oc(self):
        r = QMessageBox.question(self, self.t('Instalar bc250-detect'), self.t('Se preparara la herramienta desde el repo local bc250_smu_oc sin pip. No instala servicios.\n\nContinuar?'), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        try:
            self.controlador.instalar_cpu_oc()
            self.registrar_evento('dependencias', 'info', 'Preparar bc250-detect', 'Se abrió terminal para preparar bc250_smu_oc/bc250-detect sin pip.', {})
        except Exception as error:
            QMessageBox.warning(self, self.t('Preparar bc250-detect'), str(error))

    def instalar_umr(self):
        texto = (
            'UMR permite que bc250-cu-live-manager lea y escriba registros AMD/AMDGPU para mostrar el dashboard live y activar/restaurar 40CU.\n\n'
            'La app detectara tu distribucion e intentara instalarlo con el metodo adecuado:\n'
            '- Arch/Manjaro/CachyOS: yay/paru o pacman.\n'
            '- Fedora/Nobara: dnf.\n'
            '- Bazzite/Fedora Atomic: rpm-ostree; puede requerir reinicio.\n'
            '- Debian/Ubuntu: apt si el paquete esta disponible.\n'
            '- Fallback: bc250-cu-live-manager install-umr.\n\n'
            'Continuar?'
        )
        r = QMessageBox.question(self, self.t('Instalar UMR'), self.t(texto), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r != QMessageBox.StandardButton.Yes:
            return
        try:
            self.controlador.instalar_umr()
            self.registrar_evento('dependencias', 'info', 'Instalar UMR', 'Se abrió terminal para instalar UMR.', {})
        except Exception as error:
            QMessageBox.warning(self, self.t('Instalar UMR'), str(error))

    def actualizar_procesos(self):
        if not hasattr(self, 'tabla'):
            return
        self.procesos_actuales = self.controlador.procesos(self.check_sistema.isChecked())
        self.refrescar_tabla()

    def clave_app_proceso(self, proceso):
        texto = f'{proceso.nombre} {proceso.comando}'.lower()
        mapa = [
            ('firefox', 'Firefox'), ('chrome', 'Chrome'), ('chromium', 'Chromium'),
            ('steam', 'Steam'), ('discord', 'Discord'), ('legcord', 'Legcord'),
            ('code', 'VS Code'), ('codium', 'VS Code'), ('dolphin', 'Dolphin'),
            ('konsole', 'Konsole'), ('wine', 'Wine/Proton'), ('proton', 'Wine/Proton'),
            ('lutris', 'Lutris'), ('heroic', 'Heroic'), ('java', 'Java'),
        ]
        for clave, nombre in mapa:
            if clave in texto:
                return nombre
        nombre = (proceso.nombre or 'App').strip()
        nombre = nombre.split()[0]
        return nombre[:1].upper() + nombre[1:]

    def agrupar_procesos(self, procesos):
        if not getattr(self, 'check_agrupar', None) or not self.check_agrupar.isChecked():
            return procesos
        grupos = {}
        for proceso in procesos:
            clave = self.clave_app_proceso(proceso)
            grupos.setdefault(clave, []).append(proceso)
        salida = []
        for clave, items in grupos.items():
            if len(items) == 1:
                salida.append(items[0])
                continue
            memoria = sum(p.memoria for p in items)
            protegido = all(p.protegido for p in items)
            comando = 'PIDs: ' + ', '.join(str(p.pid) for p in items[:18])
            if len(items) > 18:
                comando += f' +{len(items) - 18}'
            grupo = type(items[0])(f'grupo:{clave}', f'{clave} ({len(items)} procesos)', memoria, comando, protegido, 'grupo')
            grupo.grupo = True
            grupo.procesos = items
            grupo.nombre_base = clave
            salida.append(grupo)
        salida.sort(key=lambda x: x.memoria, reverse=True)
        return salida

    def procesos_reales(self, procesos):
        salida = []
        vistos = set()
        for proceso in procesos:
            for real in getattr(proceso, 'procesos', [proceso]):
                if real.pid not in vistos:
                    vistos.add(real.pid)
                    salida.append(real)
        return salida

    def impacto_proceso(self, proceso):
        if getattr(proceso, 'grupo', False):
            return f"{self.t('Grupo')} x{len(getattr(proceso, 'procesos', []))}"
        if proceso.protegido:
            return self.t('Protegido')
        mb = proceso.memoria_mb()
        if mb >= 1024:
            return self.t('Alto')
        if mb >= 400:
            return self.t('Medio')
        return self.t('Normal')

    def coincide_filtro(self, proceso, texto):
        if not texto:
            return True
        texto = texto.lower().strip()
        base = f'{proceso.nombre} {proceso.pid} {proceso.comando}'.lower()
        if getattr(proceso, 'grupo', False):
            base += ' ' + ' '.join(f'{p.nombre} {p.pid} {p.comando}' for p in proceso.procesos).lower()
        return texto in base

    def refrescar_tabla(self):
        texto = self.busqueda.text() if hasattr(self, 'busqueda') else ''
        seleccion_previa = {p.pid for p in self.seleccionadas()} if hasattr(self, 'tabla') else set()
        base = self.agrupar_procesos(self.procesos_actuales)
        self.filtrados = [p for p in base if self.coincide_filtro(p, texto)]
        self.tabla.setRowCount(len(self.filtrados))
        for fila, proceso in enumerate(self.filtrados):
            check = QCheckBox()
            check.setEnabled(not proceso.protegido)
            check.setChecked(proceso.pid in seleccion_previa and not proceso.protegido)
            check.stateChanged.connect(self.actualizar_resumen_seleccion)
            caja = QWidget()
            lay = QHBoxLayout(caja)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(check)
            self.tabla.setCellWidget(fila, 0, caja)
            items = [
                QTableWidgetItem(icono_app(proceso.nombre, proceso.comando), proceso.nombre),
                QTableWidgetItem(str(proceso.pid)),
                QTableWidgetItem(f'{proceso.memoria_mb():.0f} MB'),
                QTableWidgetItem(self.impacto_proceso(proceso)),
                QTableWidgetItem(self.t('Si') if proceso.protegido else self.t('No')),
                QTableWidgetItem(proceso.comando),
            ]
            for col, item in enumerate(items, start=1):
                if proceso.protegido:
                    item.setForeground(QColor('#64748b'))
                self.tabla.setItem(fila, col, item)
        self.actualizar_resumen_seleccion()

    def get_check(self, fila):
        widget = self.tabla.cellWidget(fila, 0)
        return widget.findChild(QCheckBox) if widget else None

    def set_checks(self, estado):
        for fila, proceso in enumerate(self.filtrados):
            check = self.get_check(fila)
            if check and check.isEnabled() and not proceso.protegido:
                check.setChecked(estado)
        self.actualizar_resumen_seleccion()

    def seleccionadas(self):
        if not hasattr(self, 'tabla'):
            return []
        lista = []
        for fila, proceso in enumerate(self.filtrados):
            check = self.get_check(fila)
            if check and check.isChecked() and not proceso.protegido:
                lista.append(proceso)
        return lista

    def actualizar_resumen_seleccion(self):
        procesos = self.seleccionadas()
        reales = self.procesos_reales(procesos)
        memoria = sum(p.memoria for p in reales)
        self.resumen_seleccion.setText(f'{len(procesos)} {self.t("seleccionados")} | {len(reales)} {self.t("procesos reales")} | {self.t("recuperacion aprox.")} {formato_bytes(memoria)}')

    def cerrar_seleccionadas(self):
        procesos = self.seleccionadas()
        if not procesos:
            QMessageBox.information(self, self.t('BC250 Control Center'), self.t('No hay aplicaciones seleccionadas.'))
            return
        nombres = '\n'.join(f'- {p.nombre} ({p.memoria_mb():.0f} MB)' for p in procesos[:12])
        respuesta = QMessageBox.question(self, self.t('Finalizar tarea'), self.t('Se intentara cerrar limpio con SIGTERM antes de forzar.') + '\n\n' + nombres + '\n\n' + self.t('Continuar?'), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if respuesta != QMessageBox.StandardButton.Yes:
            return
        self.controlador.cerrar(self.procesos_reales(procesos))
        self.actualizar_procesos()
        self.actualizar_rendimiento()

    def limpiar_cache(self):
        respuesta = QMessageBox.question(self, self.t('Liberar cache con aviso'), self.t('Esta accion usa pkexec para ejecutar sync y drop_caches.\n\nNo reemplaza cerrar apps pesadas y puede provocar recarga desde disco.\n\nContinuar?'), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if respuesta != QMessageBox.StandardButton.Yes:
            return
        try:
            self.controlador.limpiar_cache()
            QMessageBox.information(self, self.t('BC250 Control Center'), self.t('Si se pidio contrasena, la accion se aplicara al aceptarla.'))
        except Exception as error:
            QMessageBox.warning(self, self.t('BC250 Control Center'), f'{self.t("No se pudo liberar cache:")} {error}')

    def aplicar_estilo(self):
        self.setStyleSheet(obtener_estilo(self.tema))
        if hasattr(self, 'gpu_risk_combo'):
            self.gpu_risk_combo.view().setStyleSheet(self.estilo_risk_popup())
