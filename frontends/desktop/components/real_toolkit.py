"""SteamOS providers presented with the app's existing compatibility rows."""
from collections import OrderedDict

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from bc250cc.infrastructure.steamos_alternative import ALTERNATIVE_ACTIONS
from bc250cc.infrastructure.steamos_real_toolkit import ACTIONS, guarded_component
from bc250cc.infrastructure.steamos_toolkit_conflicts import BULK_COMPONENTS
from bc250cc.shared.known_errors import normalize

from ..i18n import current_language, tr
from .wheel_guard import GuardedComboBox

LABELS = {
    'install-all': ('Install all components', 'Instalar todos los componentes'),
    'manual': ('Install or revert individual components', 'Instalar o revertir componentes'),
    'revert-all': ('Revert all toolkit changes', 'Revertir todos los cambios del toolkit'),
    'verify': ('Verify the installed setup', 'Verificar la instalación'),
    'profiles': ('CPU and GPU performance profiles', 'Perfiles de rendimiento de CPU y GPU'),
    'cpu-install': ('Install CPU governor', 'Instalar gobernador de CPU'),
    'cpu-revert': ('Remove CPU governor', 'Quitar gobernador de CPU'),
    'gpu-install': ('Install GPU governor', 'Instalar gobernador de GPU'),
    'gpu-revert': ('Remove GPU governor', 'Quitar gobernador de GPU'),
    'cu': ('Live CU and WGP manager', 'Gestor de CU y WGP en vivo'),
    'cores-install': ('Unlock CPU cores', 'Desbloquear núcleos de CPU'),
    'cores-revert': ('Remove CPU core boot unlock', 'Quitar desbloqueo de CPU al arrancar'),
    'swap': ('Configure swap', 'Configurar swap'),
    'swap-revert': ('Restore default swap', 'Restaurar swap predeterminado'),
    'zswap-install': ('Replace ZRAM with ZSWAP', 'Sustituir ZRAM por ZSWAP'),
    'zswap-revert': ('Restore ZRAM', 'Restaurar ZRAM'),
    'uma-install': ('Configure RAM and VRAM split', 'Configurar reparto de RAM y VRAM'),
    'uma-revert': ('Restore RAM and VRAM split', 'Restaurar reparto de RAM y VRAM'),
    'mitigations-disable': ('Disable CPU mitigations', 'Desactivar mitigaciones de CPU'),
    'mitigations-restore': ('Restore CPU mitigations', 'Restaurar mitigaciones de CPU'),
    'acpi-install': ('Install ACPI fix', 'Instalar corrección ACPI'),
    'acpi-revert': ('Remove ACPI fix', 'Quitar corrección ACPI'),
    'recovery': ('GRUB recovery entries and boot menu', 'Entradas de recuperación y menú GRUB'),
    'keyring': ('Repair package signing keys', 'Reparar claves de paquetes'),
    'combined-install': ('Install combined display, audio and graphics fixes', 'Instalar correcciones de pantalla, audio y gráficos'),
    'combined-revert': ('Revert combined graphics fix', 'Revertir correcciones de gráficos'),
    'proton-install': ('Install or update FSR4 Proton variants', 'Instalar o actualizar variantes de Proton FSR4'),
    'proton-revert': ('Remove FSR4 Proton', 'Quitar Proton FSR4'),
    'video-install': ('Install VA-API video driver', 'Instalar driver de vídeo VA-API'),
    'video-revert': ('Remove VA-API video driver', 'Quitar driver de vídeo VA-API'),
    'ac3-install': ('Install Dolby Digital AC-3 audio', 'Instalar audio Dolby Digital AC-3'),
    'ac3-revert': ('Remove Dolby Digital AC-3 audio', 'Quitar audio Dolby Digital AC-3'),
    'dual-install': ('Install dual-output audio', 'Instalar audio con salida doble'),
    'dual-revert': ('Remove dual-output audio', 'Quitar audio con salida doble'),
    'cec-setup': ('Set up television and receiver control', 'Configurar control del televisor y receptor'),
    'cec-status': ('Check HDMI-CEC configuration', 'Verificar configuración HDMI-CEC'),
    'cec-wake-install': ('Wake the TV at session start', 'Encender el televisor al iniciar sesión'),
    'cec-wake-remove': ('Remove TV wake automation', 'Quitar encendido automático del televisor'),
    'cec-poweroff-install': ('Standby TV at console power-off', 'Apagar televisor al apagar la consola'),
    'cec-poweroff-remove': ('Remove TV power-off automation', 'Quitar apagado automático del televisor'),
    'cec-clear-overrides': ('Restore Steam HDMI-CEC toggles', 'Restaurar opciones HDMI-CEC de Steam'),
    'cec': ('HDMI-CEC television control', 'Control del televisor por HDMI-CEC'),
    'sensors': ('Sensors, PWM fan control and VRM telemetry', 'Sensores, control PWM y telemetría VRM'),
    'sensors-readonly': ('Install read-only fan sensors', 'Instalar sensores de ventiladores sin control PWM'),
    'sensors-pwm': ('Install PWM fan control', 'Instalar control PWM de ventiladores'),
    'sensors-revert': ('Remove sensor driver', 'Quitar driver de sensores'),
    'coolercontrol': ('CoolerControl fan curves', 'Curvas de ventiladores con CoolerControl'),
    'aic8800': ('AIC8800 Wi-Fi and Bluetooth drivers', 'Drivers Wi-Fi y Bluetooth AIC8800'),
    'be200': ('Intel BE200 Wi-Fi firmware', 'Firmware Wi-Fi Intel BE200'),
    'dualsense': ('DualSense bridge and button chords', 'DualSense: puente y combinaciones de botones'),
    'xbox-adapter': ('Xbox wireless adapter driver', 'Driver del adaptador inalámbrico Xbox'),
    'openlinkhub-install': ('Install OpenLinkHub', 'Instalar OpenLinkHub'),
    'openlinkhub-revert': ('Remove OpenLinkHub', 'Quitar OpenLinkHub'),
    'extras': ('Additional toolkit options', 'Opciones adicionales del toolkit'),
    'emulators': ('Emulators and native recompilations', 'Emuladores y recompilaciones nativas'),
    'decky-install': ('Install Toolkit SteamOS Control for Decky', 'Instalar Toolkit SteamOS Control para Decky'),
    'decky-plugin-only': ('Install Toolkit plugin in existing Decky', 'Instalar plugin Toolkit en Decky existente'),
    'launch-coach-install': ('Install Launch Coach for Decky', 'Instalar Launch Coach para Decky'),
    'fsr4-launch-options-install': ('Install FSR4 Launch Options for Decky', 'Instalar FSR4 Launch Options para Decky'),
    'kyty-install': ('Install KytyPS5-Native', 'Instalar KytyPS5-Native'),
    'kyty-status': ('Check KytyPS5-Native', 'Verificar KytyPS5-Native'),
    'kyty-revert': ('Remove KytyPS5-Native', 'Quitar KytyPS5-Native'),
    'lichii-install': ('Install Lichii BC-250', 'Instalar Lichii BC-250'),
    'lichii-shortcut': ('Create a Lichii game shortcut', 'Crear acceso directo de Lichii'),
    'lichii-revert': ('Remove Lichii BC-250', 'Quitar Lichii BC-250'),
    'emudeck-install': ('Open EmuDeck installer', 'Abrir instalador de EmuDeck'),
}

# One component per row; secondary operations stay in the native More menu.
# The closed action registry below is preserved in full by the coverage test.
TOOLS = (
    ('toolkit', ('Toolkit management', 'Administración del toolkit'), ('Choose components, check the setup or run a complete installation.', 'Selecciona componentes, comprueba la instalación o ejecuta una instalación completa.'), ('manual', 'verify', 'install-all', 'revert-all')),
    ('performance', ('CPU governor', 'Gobernador de CPU'), ('Install or remove the toolkit CPU overclock service.', 'Instala o retira el servicio de overclock de CPU del toolkit.'), ('cpu-install', 'cpu-revert')),
    ('performance', ('GPU governor · Cyan', 'Gobernador de GPU · Cyan'), ('Manage the toolkit GPU governor installation.', 'Gestiona la instalación del gobernador de GPU del toolkit.'), ('gpu-install', 'gpu-revert')),
    ('performance', ('Compute units · CU / WGP', 'Unidades de cómputo · CU / WGP'), ('Inspect routing, choose a mask and manage boot persistence.', 'Consulta las unidades, elige una máscara y gestiona su persistencia al arrancar.'), ('cu',)),
    ('performance', ('CPU core unlock', 'Desbloqueo de núcleos de CPU'), ('Manage the toolkit boot-time core unlock service.', 'Gestiona el servicio de desbloqueo de núcleos al arrancar del toolkit.'), ('cores-install', 'cores-revert')),
    ('performance', ('CPU and GPU profiles', 'Perfiles de CPU y GPU'), ('Select a preset or configure CPU and GPU parameters separately.', 'Selecciona un perfil o configura los parámetros de CPU y GPU por separado.'), ('profiles',)),
    ('memory', ('Swap', 'Swap'), ('Configure swap space or restore the previous setup.', 'Configura el espacio de swap o restaura la configuración anterior.'), ('swap', 'swap-revert')),
    ('memory', ('ZRAM / ZSWAP', 'ZRAM / ZSWAP'), ('Change the toolkit compressed-memory configuration.', 'Cambia la configuración de memoria comprimida del toolkit.'), ('zswap-install', 'zswap-revert')),
    ('memory', ('RAM and VRAM allocation', 'Reparto de RAM y VRAM'), ('Choose the RAM / VRAM split and TTM configuration.', 'Elige el reparto de RAM y VRAM y la configuración de TTM.'), ('uma-install', 'uma-revert')),
    ('system', ('ACPI power management', 'Gestión de energía · ACPI'), ('Install or remove the toolkit ACPI correction.', 'Instala o retira la corrección ACPI del toolkit.'), ('acpi-install', 'acpi-revert')),
    ('system', ('CPU security mitigations', 'Mitigaciones de seguridad de CPU'), ('Disable CPU mitigations or restore the default boot policy.', 'Desactiva las mitigaciones de CPU o restaura la política de arranque predeterminada.'), ('mitigations-disable', 'mitigations-restore')),
    ('system', ('Boot recovery · GRUB', 'Recuperación de arranque · GRUB'), ('Manage recovery entries and the boot menu.', 'Gestiona las entradas de recuperación y el menú de arranque.'), ('recovery',)),
    ('system', ('Package signing keys', 'Claves de firma de paquetes'), ('Repair the SteamOS package keyring.', 'Repara el llavero de paquetes de SteamOS.'), ('keyring',)),
    ('graphics', ('Kernel and Mesa · GFX1013', 'Kernel y Mesa · GFX1013'), ('Select kernel patches, graphics, display and audio corrections.', 'Selecciona parches de kernel y correcciones de gráficos, pantalla y audio.'), ('combined-install', 'combined-revert')),
    ('graphics', ('Proton · FSR4', 'Proton · FSR4'), ('Manage the toolkit Proton variants for FSR4.', 'Gestiona las variantes de Proton del toolkit para FSR4.'), ('proton-install', 'proton-revert')),
    ('graphics', ('Hardware video · VA-API', 'Vídeo por hardware · VA-API'), ('Install or remove the toolkit video driver.', 'Instala o retira el controlador de vídeo del toolkit.'), ('video-install', 'video-revert')),
    ('audio', ('Dolby Digital · AC-3', 'Dolby Digital · AC-3'), ('Configure encoded surround audio over HDMI.', 'Configura audio envolvente codificado por HDMI.'), ('ac3-install', 'ac3-revert')),
    ('audio', ('Dual audio output', 'Salida de audio doble'), ('Install or remove the dual-output audio configuration.', 'Instala o retira la configuración de salida de audio doble.'), ('dual-install', 'dual-revert')),
    ('audio', ('Television control · HDMI-CEC', 'Control del televisor · HDMI-CEC'), ('Configure television control, wake and standby automation.', 'Configura el control del televisor y las automatizaciones de encendido y apagado.'), ('cec-setup', 'cec-status', 'cec', 'cec-wake-install', 'cec-wake-remove', 'cec-poweroff-install', 'cec-poweroff-remove', 'cec-clear-overrides')),
    ('accessories', ('Sensors and PWM driver', 'Sensores y controlador PWM'), ('Choose read-only monitoring or a driver with fan control.', 'Elige supervisión de sensores o un controlador con control de ventiladores.'), ('sensors', 'sensors-readonly', 'sensors-pwm', 'sensors-revert')),
    ('accessories', ('CoolerControl', 'CoolerControl'), ('Manage the external fan-curve application.', 'Gestiona la aplicación externa de curvas de ventiladores.'), ('coolercontrol',)),
    ('accessories', ('AIC8800 · Wi-Fi / Bluetooth', 'AIC8800 · Wi-Fi / Bluetooth'), ('Select the driver for the connected AIC8800 adapter.', 'Selecciona el controlador del adaptador AIC8800 conectado.'), ('aic8800',)),
    ('accessories', ('Intel BE200', 'Intel BE200'), ('Manage Wi-Fi firmware for Intel BE200.', 'Gestiona el firmware Wi-Fi de Intel BE200.'), ('be200',)),
    ('accessories', ('DualSense', 'DualSense'), ('Configure the controller bridge and button combinations.', 'Configura el puente del mando y sus combinaciones de botones.'), ('dualsense',)),
    ('accessories', ('Xbox wireless adapter', 'Adaptador inalámbrico Xbox'), ('Manage the wireless receiver driver.', 'Gestiona el controlador del receptor inalámbrico.'), ('xbox-adapter',)),
    ('accessories', ('OpenLinkHub', 'OpenLinkHub'), ('Install or remove support for compatible accessories.', 'Instala o retira el soporte para accesorios compatibles.'), ('openlinkhub-install', 'openlinkhub-revert')),
    ('extras', ('Additional tools', 'Herramientas adicionales'), ('Open the upstream tools menu.', 'Abre el menú de herramientas del proyecto.'), ('extras',)),
    ('extras', ('Decky · Toolkit SteamOS Control', 'Decky · Toolkit SteamOS Control'), ('Install the additional plugin with an existing or new Decky Loader.', 'Instala el plugin adicional en un Decky Loader existente o nuevo.'), ('decky-plugin-only', 'decky-install')),
    ('extras', ('Decky · FSR4 Launch Options', 'Decky · FSR4 Launch Options'), ('Manage FSR4 game launch options from Decky.', 'Gestiona las opciones de lanzamiento FSR4 de los juegos desde Decky.'), ('fsr4-launch-options-install',)),
    ('extras', ('Decky · Launch Coach', 'Decky · Launch Coach'), ('Install the upstream game launch assistant.', 'Instala el asistente de lanzamiento de juegos del proyecto.'), ('launch-coach-install',)),
    ('extras', ('Emulators', 'Emuladores'), ('Open the emulator and native-recompilation menu.', 'Abre el menú de emuladores y recompilaciones nativas.'), ('emulators', 'emudeck-install')),
    ('extras', ('KytyPS5-Native', 'KytyPS5-Native'), ('Install, inspect or remove KytyPS5-Native.', 'Instala, comprueba o retira KytyPS5-Native.'), ('kyty-install', 'kyty-status', 'kyty-revert')),
    ('extras', ('Lichii BC-250', 'Lichii BC-250'), ('Manage the native game and its launch shortcut.', 'Gestiona el juego nativo y su acceso directo.'), ('lichii-install', 'lichii-shortcut', 'lichii-revert')),
)

ALTERNATIVE_TOOLS = (
    ('graphics', ('Kernel compatibility', 'Compatibilidad del kernel'), ('Prepare the reviewed kernel patch or restore the stock module.', 'Prepara el parche revisado de kernel o restaura el módulo original.'), ('kernel-install', 'kernel-status', 'kernel-rollback')),
    ('graphics', ('Mesa / RADV · GFX1013', 'Mesa / RADV · GFX1013'), ('Maintain the alternative graphics runtime and per-game FSR4 profile.', 'Gestiona el runtime gráfico alternativo y el perfil FSR4 por juego.'), ('graphics-install', 'graphics-status', 'graphics-install-fsr4', 'graphics-uninstall-fsr4', 'graphics-uninstall')),
    ('graphics', ('BC-250 GE-Proton', 'BC-250 GE-Proton'), ('Maintain the compatibility tool installed by this provider.', 'Gestiona la herramienta de compatibilidad instalada por este proveedor.'), ('proton-install', 'proton-status', 'proton-uninstall')),
)


def _localized(pair):
    return pair[1 if current_language().startswith('es') else 0]


def action_label(key):
    return _localized(LABELS[key])


def _primary_label(key):
    if key in {'proton-install', 'gpu-install', 'cpu-install', 'graphics-install', 'kernel-install'}:
        return tr('Install / update')
    if key.endswith('-install') or key == 'decky-plugin-only':
        return tr('Install')
    if key == 'mitigations-disable':
        return action_label(key)
    if key == 'keyring':
        return _localized(('Repair', 'Reparar'))
    return _localized(('Configure', 'Configurar'))


class _SearchField(QLineEdit):
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.returnPressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class _ToolsIndex(QWidget):
    action_requested = pyqtSignal(object)

    def __init__(self, specifications, labels, namespace, title, parent=None, *, show_title=True):
        super().__init__(parent)
        # Loaded here because PreparationInfoCard and this index share the
        # preparation-page construction path. The actual row renderer is the
        # same one used by Additional Settings, not a separately styled copy.
        from .compat_browser import CompatibilityBrowser
        from .dashboard_widgets import PreparationInfoCard

        self._specifications, self._labels = specifications, labels
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        heading = QLabel(title)
        heading.setProperty('compatGroupTitle', True)
        heading.setVisible(show_title)
        layout.addWidget(heading)
        filters = QHBoxLayout()
        self.search = _SearchField()
        self.search.setPlaceholderText(tr('Search'))
        self.search.setAccessibleName(tr('Search'))
        self.search.setClearButtonEnabled(True)
        filters.addWidget(self.search, 1)
        self.category = GuardedComboBox()
        self.category.addItem(tr('All modules'), '')
        for category in dict.fromkeys(spec[0] for spec in specifications):
            self.category.addItem(tr(category.capitalize()), category)
        self.category.setAccessibleName(tr('Modules'))
        filters.addWidget(self.category)
        layout.addLayout(filters)
        self.buttons, self.cards = {}, {}
        groups = OrderedDict()
        for category, names, descriptions, keys in specifications:
            card = PreparationInfoCard(_localized(names), _localized(descriptions),
                                       status_text='', scope_text='SteamOS')
            for index, key in enumerate(keys):
                label = _primary_label(key) if index == 0 else _localized(labels[key])
                button = card.add_action(label, {'action': namespace + ':' + key, 'governor': ''},
                                         danger=('revert' in key or 'uninstall' in key or key == 'kernel-rollback'))
                button.setAutoDefault(False)
                self.buttons[key] = button
            card.add_action('Open upstream project', {
                'action': 'steamos_graphics_upstream' if namespace == 'real_toolkit' else 'steamos_alternative_upstream',
                'governor': '',
            }).setAutoDefault(False)
            if namespace == 'real_toolkit' and keys[0] == 'manual':
                card.add_action("What's new", {'action': 'steamos_toolkit_changelog',
                                              'governor': ''}).setAutoDefault(False)
            card.action_requested.connect(self.action_requested.emit)
            self.cards[keys[0]] = card
            groups.setdefault(tr(category.capitalize()), []).append(card)
        self.browser = CompatibilityBrowser(tuple(groups.items()), show_scope=False)
        layout.addWidget(self.browser)
        self.rows = {key: self.browser._rows[id(self.cards[keys[0]])]
                     for _category, _names, _descriptions, keys in specifications for key in keys}
        self.empty = QLabel(tr('No results'))
        layout.addWidget(self.empty)
        self.search.textChanged.connect(self._filter)
        self.category.currentIndexChanged.connect(self._filter)
        self._filter()

    def retranslate_dynamic_copy(self):
        """Refresh upstream component copy without rebuilding or dispatching."""
        for _category, names, descriptions, keys in self._specifications:
            card = self.cards[keys[0]]
            card.title.setText(tr(_localized(names)))
            card.detail.setText(tr(_localized(descriptions)))
            for index, key in enumerate(keys):
                source = _primary_label(key) if index == 0 else _localized(self._labels[key])
                button = self.buttons[key]
                button.source_text = source
                button.setText(tr(source))
        blocked = self.category.blockSignals(True)
        try:
            self.category.setItemText(0, tr('All modules'))
            for index in range(1, self.category.count()):
                self.category.setItemText(index, tr(self.category.itemData(index).capitalize()))
        finally:
            self.category.blockSignals(blocked)
        categories = dict.fromkeys(specification[0] for specification in self._specifications)
        for (heading, _cards, _group), category in zip(self.browser._captions, categories):
            heading.setText(tr(category.capitalize()))
        self.search.setPlaceholderText(tr('Search'))
        self.search.setAccessibleName(tr('Search'))
        self.category.setAccessibleName(tr('Modules'))
        self.empty.setText(tr('No results'))
        self._filter()

    def _filter(self):
        words = normalize(self.search.text()).split()
        visible = 0
        for category, names, descriptions, keys in self._specifications:
            text = normalize(' '.join((*names, *descriptions, *keys,
                                       *(label for key in keys for label in self._labels[key]))))
            matches = not self.category.currentData() or self.category.currentData() == category
            matches = matches and all(word in text for word in words)
            self.cards[keys[0]].setVisible(matches)
            visible += matches
        self.browser.refresh()
        self.empty.setVisible(not visible)


class RealToolkitPanel(_ToolsIndex):
    def __init__(self, parent=None, *, show_title=True):
        super().__init__(TOOLS, LABELS, 'real_toolkit', 'SteamOS Real Toolkit', parent, show_title=show_title)

    def set_provider_state(self, state):
        ownership = dict(state.get('native_ownership') or {})
        protected = {}
        for action in ACTIONS:
            component = guarded_component(action.key)
            components = (BULK_COMPONENTS if component == 'all' else
                          ('cpu', 'gpu', 'cu') if component == 'performance' else (component,))
            protected[action.key] = any(ownership.get(key) for key in components)
            self.buttons[action.key].setEnabled(not protected[action.key])
        for _category, _names, _description, keys in self._specifications:
            card = self.cards[keys[0]]
            if any(protected[key] for key in keys):
                card.set_status('BC250 Control Center', 'blue')
            else:
                card.status.hide()
        self.browser.refresh()


class SteamOSAlternativePanel(_ToolsIndex):
    def __init__(self, parent=None, *, show_title=True):
        super().__init__(ALTERNATIVE_TOOLS, ALTERNATIVE_ACTIONS, 'steamos_alternative',
                         'SteamOS · keyboardspecialist', parent, show_title=show_title)

    def set_provider_state(self, state):
        labels = {'ready': 'Installed', 'invalid': 'Incomplete', 'not-installed': 'Not installed'}
        radv = dict(state.get('radv') or {})
        self.cards['graphics-install'].set_status(labels.get(radv.get('state'), 'Unknown'),
                                                 'blue' if radv.get('state') == 'ready' else 'gray')
