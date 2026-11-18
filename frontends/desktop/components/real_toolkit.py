"""SteamOS providers presented with the app's existing compatibility rows."""
from PyQt6.QtCore import QObject, pyqtSignal

from bc250cc.application.preparation.steamos_providers import (
    ALTERNATIVE_ACTIONS,
    protected_actions,
)

from ..i18n import tr

LABELS = {
    'verify': ('Verify the installed setup', 'Verificar la instalación'),
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
    'aic8800': ('AIC8800 Wi-Fi and Bluetooth drivers', 'Drivers Wi-Fi y Bluetooth AIC8800'),
    'be200': ('Intel BE200 Wi-Fi firmware', 'Firmware Wi-Fi Intel BE200'),
    'dualsense': ('DualSense bridge and button chords', 'DualSense: puente y combinaciones de botones'),
    'xbox-adapter': ('Xbox wireless adapter driver', 'Driver del adaptador inalámbrico Xbox'),
    'openlinkhub-install': ('Install OpenLinkHub', 'Instalar OpenLinkHub'),
    'openlinkhub-revert': ('Remove OpenLinkHub', 'Quitar OpenLinkHub'),
}

# One component per row; secondary operations stay in the native More menu.
# The closed action registry below is preserved in full by the coverage test.
TOOLS = (
    ('toolkit', ('Toolkit management', 'Administración del toolkit'), ('Check the installed toolkit setup.', 'Comprueba la instalación del toolkit.'), ('verify',)),
    ('system', ('ACPI power management', 'Gestión de energía · ACPI'), ('Install or remove the toolkit ACPI correction.', 'Instala o retira la corrección ACPI del toolkit.'), ('acpi-install', 'acpi-revert')),
    ('system', ('Boot recovery · GRUB', 'Recuperación de arranque · GRUB'), ('Manage recovery entries and the boot menu.', 'Gestiona las entradas de recuperación y el menú de arranque.'), ('recovery',)),
    ('system', ('Package signing keys', 'Claves de firma de paquetes'), ('Repair the SteamOS package keyring.', 'Repara el llavero de paquetes de SteamOS.'), ('keyring',)),
    ('graphics', ('Kernel and Mesa · GFX1013', 'Kernel y Mesa · GFX1013'), ('Select kernel patches, graphics, display and audio corrections.', 'Selecciona parches de kernel y correcciones de gráficos, pantalla y audio.'), ('combined-install', 'combined-revert')),
    ('graphics', ('Proton · FSR4', 'Proton · FSR4'), ('Manage the toolkit Proton variants for FSR4.', 'Gestiona las variantes de Proton del toolkit para FSR4.'), ('proton-install', 'proton-revert')),
    ('video', ('Hardware video · VA-API', 'Vídeo por hardware · VA-API'), ('Install or remove the toolkit video driver.', 'Instala o retira el controlador de vídeo del toolkit.'), ('video-install', 'video-revert')),
    ('audio', ('Dolby Digital · AC-3', 'Dolby Digital · AC-3'), ('Configure encoded surround audio over HDMI.', 'Configura audio envolvente codificado por HDMI.'), ('ac3-install', 'ac3-revert')),
    ('audio', ('Dual audio output', 'Salida de audio doble'), ('Install or remove the dual-output audio configuration.', 'Instala o retira la configuración de salida de audio doble.'), ('dual-install', 'dual-revert')),
    ('audio', ('Television control · HDMI-CEC', 'Control del televisor · HDMI-CEC'), ('Configure television control, wake and standby automation.', 'Configura el control del televisor y las automatizaciones de encendido y apagado.'), ('cec-setup', 'cec-status', 'cec', 'cec-wake-install', 'cec-wake-remove', 'cec-poweroff-install', 'cec-poweroff-remove', 'cec-clear-overrides')),
    ('drivers', ('AIC8800 · Wi-Fi / Bluetooth', 'AIC8800 · Wi-Fi / Bluetooth'), ('Select the driver for the connected AIC8800 adapter.', 'Selecciona el controlador del adaptador AIC8800 conectado.'), ('aic8800',)),
    ('drivers', ('Intel BE200', 'Intel BE200'), ('Manage Wi-Fi firmware for Intel BE200.', 'Gestiona el firmware Wi-Fi de Intel BE200.'), ('be200',)),
    ('drivers', ('DualSense', 'DualSense'), ('Configure the controller bridge and button combinations.', 'Configura el puente del mando y sus combinaciones de botones.'), ('dualsense',)),
    ('drivers', ('Xbox wireless adapter', 'Adaptador inalámbrico Xbox'), ('Manage the wireless receiver driver.', 'Gestiona el controlador del receptor inalámbrico.'), ('xbox-adapter',)),
    ('drivers', ('OpenLinkHub', 'OpenLinkHub'), ('Install or remove support for compatible accessories.', 'Instala o retira el soporte para accesorios compatibles.'), ('openlinkhub-install', 'openlinkhub-revert')),
)

ALTERNATIVE_TOOLS = (
    ('graphics', ('Kernel compatibility', 'Compatibilidad del kernel'), ('Prepare the reviewed kernel patch or restore the stock module.', 'Prepara el parche revisado de kernel o restaura el módulo original.'), ('kernel-install', 'kernel-status', 'kernel-rollback')),
    ('graphics', ('Mesa / RADV · GFX1013', 'Mesa / RADV · GFX1013'), ('Maintain the alternative graphics runtime and per-game FSR4 profile.', 'Gestiona el runtime gráfico alternativo y el perfil FSR4 por juego.'), ('graphics-install', 'graphics-status', 'graphics-uninstall-fsr4', 'graphics-uninstall')),
    ('graphics', ('BC-250 GE-Proton', 'BC-250 GE-Proton'), ('Maintain the compatibility tool installed by this provider.', 'Gestiona la herramienta de compatibilidad instalada por este proveedor.'), ('proton-install', 'proton-status', 'proton-uninstall')),
)


def _localized(pair):
    """The English source is the catalog key; the second item (Spanish) is only history.

    Every language reads the same ``locales/*.json`` as the rest of the interface.
    Product names that read the same everywhere have no entry and fall back to the source.
    """
    return tr(pair[0])


def action_label(key):
    return _localized(LABELS[key])


def _primary_label(key):
    if key in {'proton-install', 'gpu-install', 'cpu-install', 'graphics-install', 'kernel-install'}:
        return tr('Install / update')
    if key.endswith('-install') or key == 'decky-plugin-only':
        return tr('Install')
    if key == 'keyring':
        return tr('Repair')
    return _localized(('Configure', 'Configurar'))


REAL_TOOLKIT_SCOPE = 'SteamOS · rpf16rj'
ALTERNATIVE_SCOPE = 'SteamOS · keyboardspecialist'
NATIVE_SCOPE = 'SteamOS · BC250 Control Center'


class ToolRows(QObject):
    """Provider components as ordinary Compatibility rows.

    The rows are not a separate browser: each card is handed to the page that
    owns its topic (System, Kernel and graphics, Video, Audio, Drivers), and the
    scope line under its title names the provider it comes from.
    """
    action_requested = pyqtSignal(object)

    def __init__(self, specifications, labels, namespace, scope_text, parent=None):
        super().__init__(parent)
        from PyQt6.QtWidgets import QWidget

        from .dashboard_widgets import PreparationInfoCard

        # A card without a parent is a top-level window, and showing it opens
        # one. Cards wait here, hidden, until a page places them in its list;
        # a page that never does (the Dashboard) must never show them.
        self._holder = QWidget()
        self._holder.hide()
        self._specifications, self._labels = specifications, labels
        self.namespace, self.scope_text = namespace, scope_text
        #: A row's explanation replacing its description while a state needs one.
        self._notes = {}
        self.buttons, self.cards, self.categories = {}, {}, {}
        for category, names, descriptions, keys in specifications:
            card = PreparationInfoCard(_localized(names), _localized(descriptions),
                                       status_text='', scope_text=scope_text)
            card.setParent(self._holder)
            card.status.hide()
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
            if namespace == 'real_toolkit' and keys == ('verify',):
                card.add_action("What's new", {'action': 'steamos_toolkit_changelog',
                                              'governor': ''}).setAutoDefault(False)
            card.action_requested.connect(self.action_requested.emit)
            self.cards[keys[0]] = card
            self.categories[keys[0]] = category

    def cards_for(self, *categories):
        return [self.cards[keys[0]] for category, _n, _d, keys in self._specifications
                if category in categories]

    def all_cards(self):
        return list(self.cards.values())

    def retranslate_dynamic_copy(self):
        """Refresh component copy without rebuilding or dispatching."""
        for _category, names, descriptions, keys in self._specifications:
            card = self.cards[keys[0]]
            card.title.setText(tr(_localized(names)))
            card.detail.setText(tr(self._notes.get(keys[0]) or _localized(descriptions)))
            for index, key in enumerate(keys):
                source = _primary_label(key) if index == 0 else _localized(self._labels[key])
                button = self.buttons[key]
                button.source_text = source
                button.setText(tr(source))

    def set_enabled(self, enabled):
        for card in self.cards.values():
            card.setEnabled(enabled)

    def set_visible(self, visible):
        for card in self.cards.values():
            card.setVisible(visible)


class RealToolkitRows(ToolRows):
    def __init__(self, parent=None):
        super().__init__(TOOLS, LABELS, 'real_toolkit', REAL_TOOLKIT_SCOPE, parent)
        self._root_status = None

    def set_root_state(self, mode, *, running=False, interrupted=False):
        """Say on the management row whether the system files are locked right now.

        Every action unlocks them for the steps that need it and Control Center
        locks them again afterwards; this is the state the person is looking at.
        """
        text, tone = (('In use', 'blue') if running else ('Interrupted', 'orange') if interrupted
                      else {'enabled': ('Protected', 'green'), 'disabled': ('Writable', 'orange')}.get(mode, (None, None)))
        self._root_status = (text, tone) if text else None
        self._apply_root_status()

    def _apply_root_status(self):
        card = self.cards.get('verify')
        if card is None:
            return
        if self._root_status:
            card.set_status(*self._root_status)
        else:
            card.status.hide()

    def set_provider_state(self, state):
        protected = protected_actions(state.get('native_ownership'))
        # keyboardspecialist's kernel fix or Mesa: the privileged runtime refuses
        # the combined fix over them, so say it here instead of after the password.
        foreign = bool(state.get('foreign_graphics'))
        blocked = protected | (FOREIGN_GRAPHICS_ACTIONS if foreign else frozenset())
        for key, button in self.buttons.items():
            button.setEnabled(key not in blocked)
        self._notes = {'combined-install': FOREIGN_GRAPHICS_NOTE} if foreign else {}
        for _category, _names, descriptions, keys in self._specifications:
            card = self.cards[keys[0]]
            card.detail.setText(tr(self._notes.get(keys[0]) or _localized(descriptions)))
            if keys == ('verify',):
                self._apply_root_status()  # this row reports the system's lock, not ownership
            elif any(key in protected for key in keys):
                card.set_status('BC250 Control Center', 'blue')
            elif keys[0] == 'combined-install' and foreign:
                card.set_status('keyboardspecialist', 'orange')
            elif (evidence := _installed(keys[0], state)) is not None:
                card.set_status(*evidence)
            else:
                card.status.hide()


#: The combined fix replaces the same amdgpu module and RADV library.
FOREIGN_GRAPHICS_ACTIONS = frozenset({'combined-install', 'combined-revert'})
FOREIGN_GRAPHICS_NOTE = (
    "keyboardspecialist's kernel fix or Mesa / RADV is installed. Remove them first with its rows "
    "(Restore the stock module for the running kernel, then Remove Mesa / RADV), restart, and install this one."
)
#: Rows whose installation the toolkit probe can prove from files on disk.
_COMPONENT_EVIDENCE = {'acpi-install': 'acpi', 'video-install': 'video',
                       'dual-install': 'dual-audio', 'recovery': 'recovery'}


def _installed(key, state):
    """(status, tone) from what is on disk, or None when nothing proves either way."""
    if key in _COMPONENT_EVIDENCE:
        present = (state.get('components') or {}).get(_COMPONENT_EVIDENCE[key])
        if present is None:
            return None
        return ('Installed', 'blue') if present else ('Not installed', 'gray')
    if key == 'combined-install':
        graphics = state.get('graphics') or {}
        if graphics.get('state') == 'configured':
            return 'Installed', 'blue'
        if graphics.get('kernel_override_installed'):
            return 'Incomplete', 'orange'
        return ('Not installed', 'gray') if graphics else None
    if key == 'proton-install':
        proton = (state.get('proton') or {}).get('state')
        return {'installed': ('Installed', 'blue'), 'incomplete': ('Incomplete', 'orange'),
                'not-installed': ('Not installed', 'gray')}.get(proton)
    return None


class SteamOSAlternativeRows(ToolRows):
    def __init__(self, parent=None):
        super().__init__(ALTERNATIVE_TOOLS, ALTERNATIVE_ACTIONS, 'steamos_alternative',
                         ALTERNATIVE_SCOPE, parent)

    def set_provider_state(self, state):
        labels = {'ready': 'Installed', 'invalid': 'Incomplete', 'not-installed': 'Not installed'}
        radv = dict(state.get('radv') or {})
        orphaned = bool(state.get('orphaned'))
        self.cards['graphics-install'].set_status(labels.get(radv.get('state'), 'Unknown'),
                                                 'blue' if radv.get('state') == 'ready'
                                                 else 'orange' if orphaned else 'gray')
        self._notes = {'graphics-install': ORPHANED_RUNTIME_NOTE} if orphaned else {}
        for _category, _names, descriptions, keys in self._specifications:
            self.cards[keys[0]].detail.setText(tr(self._notes.get(keys[0]) or _localized(descriptions)))
        kernel = dict(state.get('kernel') or {})
        if kernel.get('reboot_pending'):
            self.cards['kernel-install'].set_status('Reboot required', 'orange')
        elif kernel.get('ready'):
            self.cards['kernel-install'].set_status('Installed', 'blue')
        elif kernel.get('installed'):
            self.cards['kernel-install'].set_status('Incomplete', 'orange')
        else:
            self.cards['kernel-install'].set_status('Not installed', 'gray')


ORPHANED_RUNTIME_NOTE = (
    "Its files are still in the system partition, but its install record in /home is gone "
    "(a SteamOS factory reset erases /home only). Remove Mesa / RADV checks those files and removes them."
)
