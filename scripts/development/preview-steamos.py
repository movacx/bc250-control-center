#!/usr/bin/env python3
"""SteamOS visual preview using the real window and pages, without installers."""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT)]


class PreviewSettings:
    def __init__(self):
        self.values = {'language': 'es', 'appearance': 'light'}

    def read_local_config(self):
        return dict(self.values)

    def save_local_config(self, values):
        self.values.update(values)
        return self.read_local_config()

    def config_paths(self):
        return {}


class PreviewActivity:
    def list(self, *_args, **_kwargs):
        return []

    def __getattr__(self, name):
        return lambda *_args, **_kwargs: None


class PreviewController:
    """Presentation data only; no production repository or privileged service."""
    repo = None

    def estado_herramientas_bc250(self):
        return deepcopy({
            'os_family': 'steamos', 'os_id': 'steamos', 'os_label': 'SteamOS',
            'steamos_fix_applicable': True,
            'system_setup': {'helper_available': True,
                             'acpi': {'available': True, 'installed': False, 'status': 'not-installed'}},
            'vaapi_video': {'supported': True, 'installed': False, 'state': 'not-installed'},
            'steamos_readonly': {'available': True, 'state': 'enabled'},
            'gfx1013_compute': {
                'reason_key': 'steamos-dedicated-backend',
                'steamos_real_toolkit': {
                    'prepared': False, 'native_ownership': {},
                    'graphics': {'state': 'not-installed', 'activation_configured': False, 'active': None},
                    'proton': {'state': 'not-installed', 'tools': []},
                },
            },
            'prepare_components': {},
            # What accessory_inventory() answers on SteamOS: the wired service
            # installs there (it lives under /var/lib), Hexxeh's DKMS drivers
            # are Arch-only and TRCC publishes no SteamOS package.
            'accessories': {
                'thermalright': {'state': 'unsupported', 'device': False},
                'corsair': {'state': 'not-installed', 'device': False},
                'hdmi_ac3': {'state': 'not-installed', 'device': False},
                'hdmi_cec': {'state': 'not-installed', 'device': False},
                'apu_telemetry': {'state': 'not-installed', 'supported': True, 'device': True},
                'vrm_sensor': {'state': 'unsupported', 'device': True},
                'vram_sensor': {'state': 'unsupported', 'device': True, 'bios_supported': True},
            },
        })

    def __getattr__(self, name):
        if name.startswith(('estado_', 'obtener_', 'leer_', 'listar_', 'evaluar_')) or name in {
            'rendimiento', 'metricas_tiempo_real', 'blackbox_estado',
        }:
            return lambda *_args, **_kwargs: {}
        if name in {'procesos', 'procesos_usuario'}:
            return lambda *_args, **_kwargs: []
        raise AttributeError(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--windowed', action='store_true', help='Open a resizable window instead of fullscreen')
    parser.add_argument('--page', choices=('dashboard', 'extras', 'gpu', 'cpu', 'cu', 'fans'), default='extras')
    parser.add_argument('--screenshot', type=Path, help='Save a 1920x1080 preview and exit')
    args = parser.parse_args()
    screenshot = args.screenshot.resolve() if args.screenshot else None
    if not screenshot:
        print('Vista SteamOS: solo interfaz. Salir: Alt+F4. Ventana normal: --windowed.', flush=True)
    with tempfile.TemporaryDirectory(prefix='bc250-steamos-preview-') as folder:
        for variable, directory in [('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'), ('XDG_CACHE_HOME', 'cache')]:
            os.environ[variable] = str(Path(folder) / directory)
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QApplication

        from frontends.desktop import app as desktop
        from frontends.desktop.core import preferences
        from frontends.desktop.onboarding import mark_first_run_done

        application = QApplication([sys.argv[0]])
        # Never migrate/delete legacy preferences from the actual desktop
        # account while creating this disposable presentation profile.
        preferences._migrate_legacy_qt_settings = lambda _settings: None
        settings = preferences.application_settings()
        for key, value in {'settings/language': 'es', 'settings/appearance': 'light',
                           'settings/accent': 'violet', 'settings/density': 'comfortable',
                           'settings/style': 'standard'}.items():
            settings.setValue(key, value)
        mark_first_run_done(settings)
        desktop._is_steamos_gamemode_session = lambda: True
        controller = PreviewController()
        window = desktop.ControlCenterWindow(controller, settings_service=PreviewSettings(), activity_service=PreviewActivity())
        window.setWindowTitle('BC250 Control Center · Vista SteamOS')
        window.remote_page.set_updates_active = lambda _active: None
        from PyQt6.QtWidgets import QAbstractButton

        for button in window.remote_page.findChildren(QAbstractButton):
            button.setEnabled(False)
        # These are real pages. Mutating requests are intercepted in the
        # preview rather than being routed to a host/SteamOS backend.
        from frontends.desktop.components.widgets import InfoDialog
        def preview_only(*_args, **_kwargs):
            InfoDialog('Vista SteamOS', 'Esta vista permite revisar la interfaz. Para instalar y probar los componentes, abre la aplicación normal en SteamOS.', parent=window).exec()
        window._dashboard_dependency_action = preview_only
        window._dashboard_action = preview_only
        for page in window.pages.values():
            for name in ('dependency_action_requested', 'action_requested'):
                signal = getattr(page, name, None)
                if signal is not None:
                    try:
                        signal.disconnect()
                    except TypeError:
                        pass
                    signal.connect(preview_only)
        if args.windowed or screenshot:
            window._apply_gamemode_window_mode = lambda: None
            window.resize(1920, 1080)
        window.show()
        window.navigate(args.page)
        if screenshot:
            def capture():
                screenshot.parent.mkdir(parents=True, exist_ok=True)
                assert window.grab().save(str(screenshot))
                print(screenshot, flush=True)
                window.close()
                application.quit()
            QTimer.singleShot(1200, capture)
        return application.exec()


if __name__ == '__main__':
    raise SystemExit(main())
