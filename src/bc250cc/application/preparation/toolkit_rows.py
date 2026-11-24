"""The SteamOS providers' rows: what each is called, what it offers and what its state says.

Qt-free: the desktop draws these as cards and the terminal as rows.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from bc250cc.infrastructure.steamos_real_toolkit import (
    COMBINED_GLIBC_REASON as COMBINED_GLIBC_REASON,
)
from bc250cc.infrastructure.steamos_real_toolkit import (
    COMBINED_NATIVE_ROUTE as COMBINED_NATIVE_ROUTE,
)
from bc250cc.infrastructure.steamos_real_toolkit_recovery import (
    RECOVERY_REMOVE as RECOVERY_REMOVE,
)

from .steamos_providers import protected_actions

REAL_TOOLKIT_SCOPE = 'SteamOS · rpf16rj'
ALTERNATIVE_SCOPE = 'SteamOS · keyboardspecialist'
NATIVE_SCOPE = 'SteamOS · BC250 Control Center'

LABELS = {
    'verify': ('Verify the installed setup', 'Verificar la instalación'),
    'acpi-install': ('Install ACPI fix', 'Instalar corrección ACPI'),
    'acpi-revert': ('Remove ACPI fix', 'Quitar corrección ACPI'),
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
    'cec-install': ('Install link retrain', 'Instalar reentrenamiento del enlace'),
    'cec-remove': ('Remove link retrain', 'Quitar reentrenamiento del enlace'),
    'cec-retrain-status': ('Check link retrain', 'Comprobar reentrenamiento del enlace'),
    'recovery-remove': ('Remove', 'Quitar'),
    'recovery-status': ('Check status', 'Comprobar estado'),
    'recovery-toggle': ('Show or hide the boot menu', 'Mostrar u ocultar el menú de arranque'),
    'recovery-timeout': ('Boot menu wait time', 'Tiempo de espera del menú de arranque'),
    'aic8800-install': ('Install', 'Instalar'),
    'aic8800-legacy-install': ('Install for the older chip (MCU1)', 'Instalar para el chip antiguo (MCU1)'),
    'aic8800-remove': ('Remove', 'Quitar'),
    'aic8800-status': ('Check status', 'Comprobar estado'),
    'be200-install': ('Install', 'Instalar'),
    'be200-remove': ('Remove', 'Quitar'),
    'be200-status': ('Check status', 'Comprobar estado'),
    'dualsense-install': ('Install', 'Instalar'),
    'dualsense-remove': ('Remove', 'Quitar'),
    'dualsense-status': ('Check status', 'Comprobar estado'),
    'dualsense-chords-install': ('Install button combinations', 'Instalar combinaciones de botones'),
    'dualsense-chords-remove': ('Remove button combinations', 'Quitar combinaciones de botones'),
    'dualsense-chords-status': ('Check button combinations', 'Comprobar combinaciones de botones'),
    'xbox-adapter-install': ('Install', 'Instalar'),
    'xbox-adapter-remove': ('Remove', 'Quitar'),
    'xbox-adapter-status': ('Check status', 'Comprobar estado'),
    'put-back': ('Put back what the update removed', 'Reponer lo que quitó la actualización'),
    'openlinkhub-install': ('Install OpenLinkHub', 'Instalar OpenLinkHub'),
    'openlinkhub-revert': ('Remove OpenLinkHub', 'Quitar OpenLinkHub'),
}

# One component per row; secondary operations stay in the native More menu.
# The closed action registry below is preserved in full by the coverage test.
TOOLS = (
    ('toolkit', ('Toolkit management', 'Administración del toolkit'), ('Check the installed toolkit setup.', 'Comprueba la instalación del toolkit.'), ('verify', 'put-back')),
    ('system', ('ACPI power management', 'Gestión de energía · ACPI'), ('Install or remove the toolkit ACPI correction.', 'Instala o retira la corrección ACPI del toolkit.'), ('acpi-install', 'acpi-revert')),
    ('system', ('Boot recovery · GRUB', 'Recuperación de arranque · GRUB'), ('Remove recovery entries and adjust the boot menu. They are not installed from here: their boot script can be changed without administrator rights.', 'Retira las entradas de recuperación y ajusta el menú de arranque. No se instalan desde aquí: su script de arranque se puede cambiar sin permisos de administrador.'), ('recovery-remove', 'recovery-status', 'recovery-toggle', 'recovery-timeout')),
    ('system', ('Package signing keys', 'Claves de firma de paquetes'), ('Repair the SteamOS package keyring.', 'Repara el llavero de paquetes de SteamOS.'), ('keyring',)),
    ('graphics', ('Kernel and Mesa · GFX1013', 'Kernel y Mesa · GFX1013'), ('Select kernel patches, graphics, display and audio corrections.', 'Selecciona parches de kernel y correcciones de gráficos, pantalla y audio.'), ('combined-install', 'combined-revert')),
    ('graphics', ('Proton · FSR4', 'Proton · FSR4'), ('Manage the toolkit Proton variants for FSR4.', 'Gestiona las variantes de Proton del toolkit para FSR4.'), ('proton-install', 'proton-revert')),
    ('video', ('Hardware video · VA-API', 'Vídeo por hardware · VA-API'), ('Install or remove the toolkit video driver.', 'Instala o retira el controlador de vídeo del toolkit.'), ('video-install', 'video-revert')),
    ('audio', ('Dolby Digital · AC-3', 'Dolby Digital · AC-3'), ('Configure encoded surround audio over HDMI.', 'Configura audio envolvente codificado por HDMI.'), ('ac3-install', 'ac3-revert')),
    ('audio', ('Dual audio output', 'Salida de audio doble'), ('Install or remove the dual-output audio configuration.', 'Instala o retira la configuración de salida de audio doble.'), ('dual-install', 'dual-revert')),
    ('audio', ('Television control · HDMI-CEC', 'Control del televisor · HDMI-CEC'), ('Configure television control, wake and standby automation.', 'Configura el control del televisor y las automatizaciones de encendido y apagado.'), ('cec-setup', 'cec-status', 'cec-install', 'cec-remove', 'cec-retrain-status', 'cec-wake-install', 'cec-wake-remove', 'cec-poweroff-install', 'cec-poweroff-remove', 'cec-clear-overrides')),
    ('drivers', ('AIC8800 · Wi-Fi / Bluetooth', 'AIC8800 · Wi-Fi / Bluetooth'), ('Select the driver for the connected AIC8800 adapter.', 'Selecciona el controlador del adaptador AIC8800 conectado.'), ('aic8800-install', 'aic8800-legacy-install', 'aic8800-remove', 'aic8800-status')),
    ('drivers', ('Intel BE200', 'Intel BE200'), ('Manage Wi-Fi firmware for Intel BE200.', 'Gestiona el firmware Wi-Fi de Intel BE200.'), ('be200-install', 'be200-remove', 'be200-status')),
    ('drivers', ('DualSense', 'DualSense'), ('Configure the controller bridge and button combinations.', 'Configura el puente del mando y sus combinaciones de botones.'), ('dualsense-install', 'dualsense-chords-install', 'dualsense-remove', 'dualsense-chords-remove', 'dualsense-status', 'dualsense-chords-status')),
    ('drivers', ('Xbox wireless adapter', 'Adaptador inalámbrico Xbox'), ('Manage the wireless receiver driver.', 'Gestiona el controlador del receptor inalámbrico.'), ('xbox-adapter-install', 'xbox-adapter-remove', 'xbox-adapter-status')),
    ('drivers', ('OpenLinkHub', 'OpenLinkHub'), ('Install or remove support for compatible accessories.', 'Instala o retira el soporte para accesorios compatibles.'), ('openlinkhub-install', 'openlinkhub-revert')),
)

ALTERNATIVE_TOOLS = (
    ('graphics', ('Kernel compatibility', 'Compatibilidad del kernel'), ('Prepare the reviewed kernel patch or restore the stock module.', 'Prepara el parche revisado de kernel o restaura el módulo original.'), ('kernel-install', 'kernel-status', 'kernel-rollback')),
    ('graphics', ('Mesa / RADV · GFX1013', 'Mesa / RADV · GFX1013'), ('Maintain the alternative graphics runtime and per-game FSR4 profile.', 'Gestiona el runtime gráfico alternativo y el perfil FSR4 por juego.'), ('graphics-install', 'graphics-status', 'graphics-uninstall-fsr4', 'graphics-uninstall')),
    ('graphics', ('BC-250 GE-Proton', 'BC-250 GE-Proton'), ('Maintain the compatibility tool installed by this provider.', 'Gestiona la herramienta de compatibilidad instalada por este proveedor.'), ('proton-install', 'proton-status', 'proton-uninstall')),
)


#: Its build takes Python from Valve's newest branch, made for a newer glibc
#: than the installed SteamOS has (R-6d239d09; upstream issue 57).
COMBINED_GLIBC_NOTE = (
    "On this SteamOS version the kernel part may stop while building, because the toolkit downloads build "
    "tools made for a newer system. Nothing is changed when that happens."
)
#: A hint only: nothing is started, and it is shown only where that route has the kernel.
COMBINED_OTHER_ROUTE = (
    "keyboardspecialist's Kernel compatibility supports this kernel and builds with this system's own tools. "
    "Use one of the two, not both."
)
AC3_NEEDS_COMBINED_NOTE = (
    "Needs the combined display, audio and graphics fixes first: install them from Kernel and Mesa and restart."
)
#: The combined fix replaces the same amdgpu module and RADV library.
FOREIGN_GRAPHICS_ACTIONS = frozenset({'combined-install', 'combined-revert'})
FOREIGN_GRAPHICS_NOTE = (
    "keyboardspecialist's kernel fix or Mesa / RADV is installed. Remove them first with its rows "
    "(Restore the stock module for the running kernel, then Remove Mesa / RADV), restart, and install this one."
)
TOOLKIT_RADV_NOTE = (
    "Needs this toolkit's own patched Mesa / RADV, which is not set up: install Kernel and Mesa · GFX1013 "
    "first. keyboardspecialist's Mesa does not count."
)
#: Rows whose installation the toolkit probe can prove from files on disk.
_COMPONENT_EVIDENCE = {'acpi-install': 'acpi', 'video-install': 'video',
                       'dual-install': 'dual-audio', 'recovery-remove': 'recovery',
                       'aic8800-install': 'aic8800', 'be200-install': 'be200',
                       'dualsense-install': 'dualsense', 'xbox-adapter-install': 'xbox-adapter'}


def installed_status(key, state):
    """(status, tone) from what is on disk, or None when nothing proves either way."""
    if key in _COMPONENT_EVIDENCE:
        present = (state.get('components') or {}).get(_COMPONENT_EVIDENCE[key])
        if present is None:
            return None
        return ('Installed', 'blue') if present else ('Not installed', 'gray')
    if key == 'combined-install':
        graphics = state.get('graphics') or {}
        # Both halves: Mesa alone is what a kernel update leaves behind.
        if graphics.get('state') == 'configured' and graphics.get('kernel_override_installed') is not False:
            return 'Installed', 'blue'
        if graphics.get('state') == 'configured' or graphics.get('kernel_override_installed'):
            return 'Incomplete', 'orange'
        return ('Not installed', 'gray') if graphics else None
    if key == 'proton-install':
        proton = (state.get('proton') or {}).get('state')
        return {'installed': ('Installed', 'blue'), 'incomplete': ('Incomplete', 'orange'),
                'not-installed': ('Not installed', 'gray')}.get(proton)
    return None


@dataclass(frozen=True)
class ToolkitState:
    """What the probe's reading means for the rows."""

    protected: frozenset[str] = frozenset()
    blocked: frozenset[str] = frozenset()
    foreign: bool = False
    notes: Mapping[str, object] = field(default_factory=dict)


def toolkit_presentation(state: Mapping) -> ToolkitState:
    protected = frozenset(protected_actions(state.get('native_ownership')))
    # keyboardspecialist's kernel fix or Mesa: the privileged runtime refuses
    # the combined fix over them, so say it here instead of after the password.
    foreign = bool(state.get('foreign_graphics'))
    # The toolkit's FSR4 Proton refuses to install without its own RADV.
    needs_radv = (state.get('proton') or {}).get('radv_ready') is False
    # AC-3 refuses without the combined fix's amdgpu, minutes into the run.
    needs_combined = (state.get('graphics') or {}).get('kernel_override_installed') is False
    blocked = (protected | (FOREIGN_GRAPHICS_ACTIONS if foreign else frozenset())
               | ({'proton-install'} if needs_radv else frozenset())
               | ({'ac3-install'} if needs_combined else frozenset()))
    notes = {'combined-install': FOREIGN_GRAPHICS_NOTE} if foreign else {}
    if not foreign and state.get('old_glibc'):
        notes['combined-install'] = (
            (COMBINED_GLIBC_NOTE, COMBINED_OTHER_ROUTE) if state.get('alternative_kernel') else COMBINED_GLIBC_NOTE
        )
    if needs_combined:
        notes['ac3-install'] = AC3_NEEDS_COMBINED_NOTE
    if needs_radv:
        notes['proton-install'] = TOOLKIT_RADV_NOTE
    return ToolkitState(protected, frozenset(blocked), foreign, notes)


def primary_label(key: str) -> str:
    """The row's first button, in English (a catalog key)."""
    if key in {'proton-install', 'gpu-install', 'cpu-install', 'graphics-install', 'kernel-install'}:
        return 'Install / update'
    if key.endswith('-install') or key == 'decky-plugin-only':
        return 'Install'
    if key == 'recovery-remove':
        return 'Remove'
    if key == 'keyring':
        return 'Repair'
    return 'Configure'


def is_removal(key: str) -> bool:
    return 'revert' in key or '-remove' in key or 'uninstall' in key or key == 'kernel-rollback'


def reads_only(key: str) -> bool:
    return key == 'verify' or key.endswith('-status')
