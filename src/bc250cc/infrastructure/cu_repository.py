import json
import logging
import os
import re
import shlex
import stat
import tempfile
import time
from pathlib import Path

from bc250cc.infrastructure.cu_dashboard import clean_dashboard, parse_dashboard
from bc250cc.infrastructure.cu_operations import (
    plan_cu_mask_operations,
    validate_cu_masks,
)
from bc250cc.infrastructure.polkit_session import pkexec_argv
from bc250cc.platform.init.services import (
    detect_init_manager,
    parse_openrc_runlevel,
)
from bc250cc.shared import contract
from bc250cc.shared.failure_text import describe_failure

logger = logging.getLogger(__name__)


# The Decky helper is root-owned and cannot safely update a path below the
# desktop user's home.  It publishes one *ephemeral* verified reading here
# instead.  This file is intentionally not a second persistent CU profile:
# /run is cleared at boot and the desktop cache remains the fallback.
QUICK_ACCESS_CU_RUNTIME_STATE = Path('/run/bc250-control-center/cu-live-state.json')
# Both numbers come from the shared contract now. This one was pinned at 9
# while the helper published 13, so every snapshot was rejected and
# ``obtener_estado_cu_cache`` fell through to the stale on-disk cache without
# a log line — the Compute Units page has been showing old data since the
# protocol moved to 10.
QUICK_ACCESS_CU_RUNTIME_SCHEMA = contract.QUICK_ACCESS_CU_RUNTIME_SCHEMA
QUICK_ACCESS_CU_RUNTIME_HELPER_PROTOCOL = contract.QUICK_ACCESS_PROTOCOL
QUICK_ACCESS_CU_RUNTIME_MAX_BYTES = 128 * 1024
DESKTOP_CU_HELPER = Path('/usr/libexec/bc250-control-center/bc250-cu-helper')


class CURepository:
    def _mensaje_cu_manager_no_disponible(self, tools):
        if tools.get('is_steamos'):
            return (
                'SteamOS 40CU actions are locked because the required F5GO SteamOS backend is not ready.\n\n'
                'The standard WinnieLV live manager is intentionally ignored on SteamOS, even if it is installed, '
                'because it can use an incompatible UMR database or register workflow.\n\n'
                'Use "Prepare dependencies" or "Prepare Live Manager", then retry. The required script is expected at:\n'
                '~/.local/share/bc250-control-center/ResourceTools/bc250-cu-live-manager-steamos/'
                'bc250-cu-live-manager-bc250.sh'
            )
        return 'bc250-cu-live-manager was not found. Use Prepare dependencies first.'

    def _cu_manager_script_or_raise(self, tools):
        script = str(tools.get('cu_manager') or '')
        if tools.get('is_steamos'):
            if tools.get('cu_manager_backend') != 'steamos':
                raise RuntimeError(self._mensaje_cu_manager_no_disponible(tools))
            if not script or not Path(script).exists():
                raise RuntimeError(self._mensaje_cu_manager_no_disponible(tools))
            return script
        if not tools.get('cu_manager_exists') or not script:
            raise RuntimeError(self._mensaje_cu_manager_no_disponible(tools))
        return script

    def obtener_mapa_cu(self):
        tools = self.estado_herramientas_bc250()
        script = tools.get('cu_map_script') or ''
        if not script:
            raise RuntimeError('cu_map.sh was not found. This legacy fallback is not required by the live 40CU manager.')
        ruta = Path(script)
        if not ruta.exists():
            self.estado_herramientas_cache = None
            raise RuntimeError(f'cu_map.sh does not exist at {ruta}')
        rc, out, err = self._ejecutar(['bash', str(ruta), '--no-health'], timeout=10)
        if rc != 0:
            raise RuntimeError(describe_failure(rc, out, err))
        lineas = []
        for linea in out.splitlines():
            texto = linea.strip()
            if re.search(r'\d+/\d+\s+CUs\s+active', texto, re.IGNORECASE):
                continue
            lineas.append(linea)
        return '\n'.join(lineas).strip()


    def obtener_dashboard_cu(self):
        tools = self.estado_herramientas_bc250()
        self._cu_manager_script_or_raise(tools)
        if not tools.get('cu_privileged_backend_ready'):
            raise RuntimeError(str(tools.get('cu_privileged_backend_reason') or self._cu_backend_untrusted_message()))
        return self._ejecutar_cu_accion_pkexec(['status'])


    @staticmethod
    def _autorizacion_cancelada(texto):
        normalizado = str(texto or '').strip().lower()
        return any(fragmento in normalizado for fragmento in (
            'request dismissed',
            'authentication cancelled',
            'authentication canceled',
            'cancelled by user',
            'canceled by user',
            'not authorized',
            'org.freedesktop.policykit1.error.cancelled',
        ))


    def _dashboard_cu_cache_path(self):
        return self.configuracion.carpeta_data() / 'cu_dashboard_live.txt'

    @staticmethod
    def _quick_access_cu_runtime_boot_id_path():
        return Path('/proc/sys/kernel/random/boot_id')

    def _quick_access_cu_runtime_state_path(self):
        return QUICK_ACCESS_CU_RUNTIME_STATE

    @staticmethod
    def _root_owned_mode(path, metadata, *, directory=False):
        """Validate the complete read boundary for QAM's root runtime state."""
        return (
            not stat.S_ISLNK(metadata.st_mode)
            and (stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode))
            and metadata.st_uid == 0
            and stat.S_IMODE(metadata.st_mode) == (0o755 if directory else 0o644)
            and path.parent != path
        )

    def _quick_access_cu_runtime_metadata(self):
        """Return trusted path metadata or ``None`` without following links."""
        path = self._quick_access_cu_runtime_state_path()
        try:
            directory = path.parent.lstat()
            payload = path.lstat()
        except OSError:
            return None
        if not self._root_owned_mode(path.parent, directory, directory=True):
            return None
        if not self._root_owned_mode(path, payload):
            return None
        if payload.st_size <= 0 or payload.st_size > QUICK_ACCESS_CU_RUNTIME_MAX_BYTES:
            return None
        return path, payload

    def _quick_access_cu_runtime_boot_id(self):
        try:
            value = self._quick_access_cu_runtime_boot_id_path().read_text(
                encoding='ascii', errors='strict'
            ).strip()
        except (OSError, UnicodeError):
            return ''
        return value if re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', value) else ''

    @staticmethod
    def _opened_quick_access_runtime_file_is_safe(metadata, expected):
        """Revalidate the descriptor opened with ``O_NOFOLLOW``.

        Comparing the descriptor to the earlier ``lstat`` closes the small
        check/use window without trusting a path lookup twice.
        """
        return (
            stat.S_ISREG(metadata.st_mode)
            and metadata.st_uid == 0
            and stat.S_IMODE(metadata.st_mode) == 0o644
            and 0 < metadata.st_size <= QUICK_ACCESS_CU_RUNTIME_MAX_BYTES
            and metadata.st_dev == getattr(expected, 'st_dev', metadata.st_dev)
            and metadata.st_ino == getattr(expected, 'st_ino', metadata.st_ino)
        )

    def _read_quick_access_runtime_bytes(self, path, expected):
        flags = os.O_RDONLY | getattr(os, 'O_CLOEXEC', 0) | getattr(os, 'O_NOFOLLOW', 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if not self._opened_quick_access_runtime_file_is_safe(opened, expected):
                return None
            chunks = []
            total = 0
            while total <= QUICK_ACCESS_CU_RUNTIME_MAX_BYTES:
                chunk = os.read(
                    descriptor,
                    min(64 * 1024, QUICK_ACCESS_CU_RUNTIME_MAX_BYTES + 1 - total),
                )
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
            if total > QUICK_ACCESS_CU_RUNTIME_MAX_BYTES:
                return None
            return b''.join(chunks)
        finally:
            os.close(descriptor)

    @staticmethod
    def _runtime_masks(value, *, live=False):
        if not isinstance(value, list) or len(value) != 4 or any(type(item) is not int for item in value):
            return None
        masks = tuple(value)
        if any(mask < 0 or mask > 0x1F for mask in masks):
            return None
        active = sum(mask.bit_count() * 2 for mask in masks)
        if live and active not in range(24, 41, 2):
            return None
        return masks

    @staticmethod
    def _runtime_tokens(value):
        if not isinstance(value, list) or len(value) != 4:
            return None
        normalized = []
        for row in value:
            if not isinstance(row, list) or len(row) != 5 or any(type(token) is not str for token in row):
                return None
            tokens = tuple(token.upper() for token in row)
            if any(token not in {'D+', 'S+', 'D!', '--'} for token in tokens):
                return None
            normalized.append(tokens)
        return tuple(normalized)

    def _leer_dashboard_cu_quick_access_runtime(self):
        """Read one QAM-produced CU snapshot after independent validation.

        Treat the JSON as untrusted even though it is root-owned: re-parsing
        the raw dashboard keeps the exact same topology boundary as Desktop
        Mode and prevents one inconsistent summary field from changing UI
        state or unlocking a write action.
        """
        metadata = self._quick_access_cu_runtime_metadata()
        boot_id = self._quick_access_cu_runtime_boot_id()
        if metadata is None or not boot_id:
            return None
        path, stat_result = metadata
        try:
            raw_payload = self._read_quick_access_runtime_bytes(path, stat_result)
            if raw_payload is None:
                return None
            payload = json.loads(raw_payload.decode('utf-8', errors='strict'))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        if (
            type(payload.get('schema')) is not int
            or payload.get('schema') != QUICK_ACCESS_CU_RUNTIME_SCHEMA
            or payload.get('producer') != 'bc250-quick-access-helper'
            or type(payload.get('helper_protocol')) is not int
            or payload.get('boot_id') != boot_id
            or type(payload.get('observed_at_unix_ms')) is not int
            or payload['observed_at_unix_ms'] < 0
            or payload['observed_at_unix_ms'] > time.time_ns() // 1_000_000 + 60_000
            or not isinstance(payload.get('raw_dashboard'), str)
        ):
            return None
        if payload.get('helper_protocol') != QUICK_ACCESS_CU_RUNTIME_HELPER_PROTOCOL:
            # Separated from the shape checks above so it can say something.
            # This branch returned a bare None for three protocol bumps while
            # the caller fell through to a stale cache, so the Compute Units
            # page quietly showed old data and nothing anywhere said why.
            logger.warning(
                'Ignoring the Quick Access CU snapshot: it declares helper '
                'protocol %r and this build expects %r. The Desktop and Decky '
                'components are from different installs.',
                payload.get('helper_protocol'),
                QUICK_ACCESS_CU_RUNTIME_HELPER_PROTOCOL,
            )
            return None
        live_masks = self._runtime_masks(payload.get('cu_masks'), live=True)
        driver_masks = self._runtime_masks(payload.get('cu_driver_masks'))
        tokens = self._runtime_tokens(payload.get('cu_tokens'))
        saved_masks_raw = payload.get('cu_saved_masks')
        saved_masks = None if saved_masks_raw is None else self._runtime_masks(saved_masks_raw, live=True)
        if live_masks is None or driver_masks is None or tokens is None or saved_masks_raw is not None and saved_masks is None:
            return None
        if (
            type(payload.get('cu_active_cus')) is not int
            or type(payload.get('cu_total_cus')) is not int
            or payload['cu_total_cus'] != 40
            or payload['cu_active_cus'] != sum(mask.bit_count() * 2 for mask in live_masks)
            or any(type(payload.get(key)) is not bool for key in (
                'cu_service_installed', 'cu_service_enabled', 'cu_service_active', 'cu_boot_saved',
            ))
            or bool(payload['cu_service_enabled']) and not bool(payload['cu_service_installed'])
            or bool(payload['cu_service_active']) and not bool(payload['cu_service_installed'])
            or bool(payload['cu_boot_saved']) != (saved_masks is not None)
        ):
            return None

        state = self.parsear_dashboard_cu(payload['raw_dashboard'], source='quick access runtime')
        rows = list(state.get('rows') or [])
        parsed_tokens = tuple(tuple(str(token) for token in row.get('tokens') or ()) for row in rows)
        if not (
            state.get('available')
            and tuple(state.get('masks') or ()) == live_masks
            and tuple(state.get('driver_masks') or ()) == driver_masks
            and parsed_tokens == tokens
            and int(state.get('active_cus') or -1) == payload['cu_active_cus']
            and int(state.get('total_cus') or -1) == payload['cu_total_cus']
        ):
            return None

        installed = bool(payload['cu_service_installed'])
        enabled = bool(payload['cu_service_enabled'])
        state.update({
            'source': 'Quick Access verified snapshot',
            'source_kind': 'quick_access',
            'fresh': False,
            'service': 'Enabled' if enabled else 'Installed' if installed else 'Not installed',
            'service_installed': installed,
            'service_enabled': enabled,
            'service_active': bool(payload['cu_service_active']),
            'boot_sync': (
                'Current table saved' if saved_masks == live_masks
                else 'Pending changes' if saved_masks is not None else 'Not saved'
            ),
            'boot_sync_key': 'saved' if saved_masks == live_masks else 'pending' if saved_masks is not None else 'not_saved',
            'quick_access_observed_at_unix_ms': payload['observed_at_unix_ms'],
            'updated_at': time.strftime(
                '%H:%M:%S', time.localtime(payload['observed_at_unix_ms'] / 1000)
            ),
        })
        return state, stat_result.st_mtime


    def _guardar_dashboard_cu_cache(self, texto):
        temporary = None
        try:
            ruta = self._dashboard_cu_cache_path()
            ruta.parent.mkdir(parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(prefix='.cu-dashboard-', dir=ruta.parent)
            temporary = Path(name)
            with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
                handle.write((texto or '').strip() + '\n')
                handle.flush()
                os.fsync(handle.fileno())
            temporary.chmod(0o600)
            os.replace(temporary, ruta)
        except OSError:
            logger.warning("Could not update the authorized CU dashboard cache", exc_info=True)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


    def _actualizar_persistencia_dashboard_cu_cache(self, accion):
        try:
            ruta = self._dashboard_cu_cache_path()
            texto = self._limpiar_dashboard_cu(
                ruta.read_text(encoding='utf-8', errors='ignore')
            )
        except (AttributeError, OSError):
            return
        if not self._dashboard_cu_tiene_tabla(texto):
            return
        lines = [
            line for line in texto.splitlines()
            if not re.match(r'^\s*(Service|Boot sync)\s*:', line, re.IGNORECASE)
        ]
        if accion == 'save_boot':
            lines.append('  Boot sync  : current table saved')
        elif accion == 'install_service':
            lines.extend(('  Service    : enabled', '  Boot sync  : current table saved'))
        elif accion == 'remove_service':
            lines.extend(('  Service    : not installed', '  Boot sync  : no saved table'))
        else:
            return
        self._guardar_dashboard_cu_cache('\n'.join(lines))


    def _leer_dashboard_cu_cache(self):
        ruta = self._dashboard_cu_cache_path()
        if not ruta.exists():
            return ''
        try:
            texto = self._limpiar_dashboard_cu(ruta.read_text(encoding='utf-8', errors='ignore'))
            if not texto:
                return ''
            fecha = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ruta.stat().st_mtime))
            return (
                f'Last saved authorized reading: {fecha}\n'
                'To update it, use "Refresh dashboard" and authorize the Polkit window if it appears.\n\n'
                f'{texto}'
            )
        except Exception:
            return ''

    def _reconcile_cached_service_state(self, state):
        """Reconcile persistence without changing validated live topology.

        ``active_cus`` and the WGP rows are hardware evidence.  An unavailable
        service backend must never replace them with the factory fallback.
        """
        init_manager = detect_init_manager()
        state['init_manager'] = init_manager.kind
        state['persistence_supported'] = init_manager.persistence_supported
        state['persistence_detail'] = init_manager.persistence_detail
        if init_manager.kind == 'openrc':
            try:
                _rc, out, _err = self._ejecutar(['rc-update', 'show', 'default'], timeout=5)
                exists = (Path('/etc/init.d') / 'bc250-cu-live-manager').is_file()
                enabled = parse_openrc_runlevel(out, 'bc250-cu-live-manager')
            except Exception:
                return state
            state['service'] = 'Enabled' if enabled else 'Installed' if exists else 'Not installed'
            state['service_installed'] = exists
            state['service_enabled'] = enabled
            if (not exists or not enabled) and state.get('boot_sync_key') != 'saved':
                state['boot_sync'] = 'Not saved' if not exists else state.get('boot_sync', 'Not saved')
                state['boot_sync_key'] = 'not_saved' if not exists else state.get('boot_sync_key', 'not_saved')
            return state
        if init_manager.kind != 'systemd':
            state['service'] = f'Unsupported on {init_manager.display_name}'
            state['service_installed'] = False
            state['service_enabled'] = False
            state['service_active'] = False
            state['boot_sync'] = 'Persistence unsupported'
            state['boot_sync_key'] = 'unsupported'
            return state
        try:
            rc, out, _err = self._ejecutar(
                ['systemctl', 'is-enabled', 'bc250-cu-live-manager.service'], timeout=5
            )
        except Exception:
            return state
        status = (out or '').strip().lower()
        if rc == 0 and status == 'enabled':
            state['service'] = 'Enabled'
            state['service_installed'] = True
            state['service_enabled'] = True
            return state
        if rc == 0 or status in {'disabled', 'masked', 'not-found', 'indirect'}:
            state['service'] = 'Not installed' if status == 'not-found' else 'Disabled'
            state['service_installed'] = status != 'not-found'
            state['service_enabled'] = False
            if status == 'not-found':
                # Saving the table intentionally happens before installing the
                # service.  systemd therefore reports ``not-found`` during
                # the interval between those actions.  Do not erase the
                # authoritative ``saved`` marker just because the service is
                # not installed yet; doing so disables the Install service
                # button on the next passive refresh.
                if state.get('boot_sync_key') != 'saved':
                    state['boot_sync'] = 'Not saved'
                    state['boot_sync_key'] = 'not_saved'
        return state


    def _requiere_terminal_sudo(self, texto):
        texto = (texto or '').lower()
        pistas = [
            'a password is required',
            'a terminal is required',
            'sudo:',
            'contraseña',
            'password',
        ]
        return any(pista in texto for pista in pistas)


    def _limpiar_dashboard_cu(self, texto):
        return clean_dashboard(texto)


    def _dashboard_fallback_mapa(self, mapa, error=''):
        lineas = [
            '| BC-250 CU Dashboard / legacy map fallback |',
            '+--------------------------------------------------------------+',
            'Source     : bc250-40cu-unlock/cu_map.sh',
            'Note       : this map shows the harvest/boot map; it does not confirm current live routing.',
        ]
        if error:
            lineas.extend(['', 'Live-manager unavailable without authorization:', error[:600]])
        lineas.extend(['', mapa or '--'])
        return '\n'.join(lineas).strip()


    def ejecutar_cu_manager(self, accion):
        tools = self.estado_herramientas_bc250()
        self._cu_manager_script_or_raise(tools)
        if accion == 'status':
            return self.obtener_dashboard_cu()
        elif accion == 'enable40':
            return self._ejecutar_cu_accion_pkexec(['--yes', 'enable', 'all'])
        elif accion == 'stock':
            return self._ejecutar_cu_accion_pkexec(['--yes', 'stock-dispatch'])
        elif accion == 'menu':
            raise RuntimeError(self._cu_backend_untrusted_message())
        else:
            raise ValueError('Invalid CU action.')


    def _ejecutar_cu_accion_pkexec(self, args):
        if args and args[0] == 'batch':
            operations = json.loads(args[1]) if len(args) == 2 else []
            if not isinstance(operations, list) or not 1 <= len(operations) <= 8:
                raise ValueError('Invalid CU batch operation count.')
            for operation in operations:
                self._cu_helper_action_name(operation)
        else:
            self._cu_helper_action_name(args)
        tools = self.estado_herramientas_bc250()
        remove_service = tuple(str(item) for item in args) == ('--yes', 'uninstall-service')
        if not tools.get('cu_privileged_backend_ready') and not remove_service:
            raise RuntimeError(str(tools.get('cu_privileged_backend_reason') or self._cu_backend_untrusted_message()))
        if getattr(self, '_usar_steamos_cu_helper', lambda: False)():
            # Game Mode/Desktop SteamOS actions use the narrow helper instead
            # of pkexec. Persist every complete authorized table, including a
            # status-only read, exactly like the pkexec path. Otherwise a live
            # refresh can show the right topology and navigation immediately
            # reloads the older snapshot.
            text = self._ejecutar_steamos_game_helper('cu', *args, timeout=240)
            if text and self._dashboard_cu_tiene_tabla(text):
                self._guardar_dashboard_cu_cache(text)
            return text
        pkexec = self._command_path('pkexec')
        if not pkexec:
            raise RuntimeError('polkit/pkexec was not found. Install polkit and retry from Desktop Mode.')
        try:
            metadata = DESKTOP_CU_HELPER.lstat()
        except OSError as exc:
            raise RuntimeError('CU_HELPER_MISSING: Reinstall Control Center to enable single-prompt CU actions.') from exc
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_mode & 0o022 or not metadata.st_mode & 0o111:
            raise RuntimeError('CU_BACKEND_UNTRUSTED: the desktop CU helper is not protected.')
        command = pkexec_argv(pkexec, str(DESKTOP_CU_HELPER), *args)
        rc, out, err = self._ejecutar(command, timeout=240)
        if rc != 0:
            detail = describe_failure(rc, out, err)
            if self._autorizacion_cancelada(detail):
                raise RuntimeError('CU_AUTHORIZATION_CANCELLED')
            raise RuntimeError(detail)
        text = (out or '').strip()
        if text:
            if self._dashboard_cu_tiene_tabla(text):
                self._guardar_dashboard_cu_cache(text)
        return text

    def _ejecutar_openrc_cu_service(self, action):
        """Install/remove only the native OpenRC wrapper around a staged backend."""
        if action not in {'install', 'remove'}:
            raise ValueError('Invalid OpenRC CU service action.')
        tools = self.estado_herramientas_bc250()
        if action == 'install' and not tools.get('cu_privileged_backend_ready'):
            raise RuntimeError(str(tools.get('cu_privileged_backend_reason') or self._cu_backend_untrusted_message()))
        helper = Path('/usr/libexec/bc250-control-center/bc250-openrc-service-helper')
        try:
            metadata = helper.stat(follow_symlinks=False)
        except OSError as exc:
            raise RuntimeError('The protected OpenRC service helper is missing. Reinstall Control Center.') from exc
        if helper.is_symlink() or not helper.is_file() or metadata.st_uid != 0 or metadata.st_mode & 0o022:
            raise RuntimeError('The protected OpenRC service helper has unsafe ownership or permissions.')
        pkexec = self._command_path('pkexec')
        if not pkexec:
            raise RuntimeError('polkit/pkexec was not found. Install polkit to manage the OpenRC CU service.')
        rc, out, err = self._ejecutar(
            pkexec_argv(pkexec, str(helper), action, 'bc250-cu-live-manager'), timeout=120
        )
        if rc != 0:
            raise RuntimeError(err or out or 'OpenRC CU service action failed.')
        return (out or '').strip()

    @staticmethod
    def _cu_backend_untrusted_message():
        return (
            'CU_BACKEND_UNTRUSTED: Control Center will not execute a user-writable '
            'ResourceTools script, including status because the upstream manager can '
            'self-elevate through sudo. CU reads and writes remain disabled '
            'until the packaged root-owned backend and its UMR database pass independent '
            'provenance and hardware recovery validation.'
        )


    def _cu_helper_action_name(self, args):
        normalized = [str(item) for item in args]
        mapping = {
            ('status',): 'status',
            ('--yes', 'enable', 'all'): 'full',
            ('--yes', 'stock-dispatch'): 'factory',
            ('--yes', 'disable', 'all'): 'disable_all',
            ('--yes', 'write-service-table'): 'save_boot',
            ('--yes', 'install-service'): 'install_service',
            ('--yes', 'apply-service'): 'apply_saved',
            ('--yes', 'uninstall-service'): 'remove_service',
        }
        key = tuple(normalized)
        if (
            len(normalized) >= 3
            and tuple(normalized[:2]) in {
                ('--yes', 'enable-wgp'),
                ('--yes', 'disable-wgp'),
            }
            and all(re.fullmatch(r'[01]\.[01]\.[0-4]', item) for item in normalized[2:])
        ):
            return normalized[1].replace('-', '_')
        if key not in mapping:
            raise ValueError('Invalid CU helper action.')
        return mapping[key]


    def _error_umr_faltante(self, texto):
        texto = (texto or '').lower()
        pistas = [
            'cu_umr_missing',
            'umr not found',
            'no such file or directory: umr',
            'command not found: umr',
            'umr: command not found',
            'falta umr',
        ]
        return any(pista in texto for pista in pistas)


    def _mensaje_umr_faltante(self):
        return (
            'UMR is missing from the system.\n\n'
            'UMR is the tool that bc250-cu-live-manager uses to read and write AMD/AMDGPU registers. '
            'Without UMR, the live dashboard and enable/restore 40CU actions cannot run from the interface.\n\n'
            'Solution: press the "Install UMR" button in the 40CU panel. '
            'The app will detect your distribution and try to install the matching package.'
        )


    @staticmethod
    def _steamos_umr_selector_from_database(database):
        """Return the GC register namespace declared by cyan_skillfish.asic.

        UMR's marketing/physical ASIC name (gfx1013) is not guaranteed to be
        the register block name shipped by a particular database revision.
        Derive it from the same model file validated during dependency prep so
        Desktop Mode, Game Mode and the boot service cannot disagree.
        """
        try:
            root = Path(database).expanduser()
            model = root / 'cyan_skillfish.asic'
            if model.is_symlink() or not model.is_file():
                return ''
            root_resolved = root.resolve(strict=True)
            lines = model.read_text(encoding='utf-8', errors='replace').splitlines()
            required = (
                'mmCC_GC_SHADER_ARRAY_CONFIG',
                'mmSPI_PG_ENABLE_STATIC_WGP_MASK',
                'mmRLC_PG_ALWAYS_ON_WGP_MASK',
            )
            for line in lines[1:]:
                fields = line.split()
                if len(fields) != 4:
                    continue
                ip_common, ip_soc, _instance, regfile = fields
                if not (ip_common.startswith('gfx') or ip_soc == 'GC'):
                    continue
                candidate = (root / regfile).resolve(strict=True)
                candidate.relative_to(root_resolved)
                if candidate.is_symlink() or not candidate.is_file():
                    continue
                text = candidate.read_text(encoding='utf-8', errors='replace')
                if all(register in text for register in required):
                    return f'cyan_skillfish.{ip_common}'
        except (OSError, RuntimeError, ValueError):
            return ''
        return ''

    def _cu_manager_env(self, tools):
        env = {}
        if tools.get('cu_manager_backend') == 'steamos' or tools.get('is_steamos'):
            # SteamOS uses a generated compatibility copy of the F5GO backend.
            # Force the static cyan_skillfish model, but derive its GC register
            # namespace from the validated database rather than hard-coding a
            # gfx1010/gfx1013 spelling that may change between UMR revisions.
            database = tools.get('cu_steamos_umr_database') or str(self._tool_dir() / 'umr-steamos' / 'database')
            env['UMR_DATABASE_PATH'] = database
            selector = os.environ.get('UMR_ASIC') or self._steamos_umr_selector_from_database(database)
            if selector:
                env['UMR_ASIC'] = selector
            if os.environ.get('UMR_INSTANCE'):
                env['UMR_INSTANCE'] = os.environ['UMR_INSTANCE']
        return env


    def _env_args_cu(self, tools):
        return [f'{clave}={valor}' for clave, valor in self._cu_manager_env(tools).items() if valor]


    def _steamos_cu_env_probe_shell(self, tools):
        # Export the database-defined GC namespace and let the patched backend
        # auto-detect the concrete DRI instance. This keeps every click bounded
        # without assuming whether a future UMR database calls the block gfx1010
        # or gfx1013.
        return self._exportar_env_cu_simple(tools)



    def _exportar_env_cu_simple(self, tools):
        partes = []
        for clave, valor in self._cu_manager_env(tools).items():
            if valor:
                partes.append(f'export {clave}={shlex.quote(str(valor))}; ')
        return ''.join(partes)


    def _exportar_env_cu(self, tools):
        exported = self._exportar_env_cu_simple(tools)
        if tools.get('cu_manager_backend') == 'steamos' or tools.get('is_steamos'):
            return exported
        # WinnieLV's current standard backend tests only its default selector.
        # Port the bounded `umr -lb` fallback from rpf16rj's toolkit without
        # modifying or replacing the cloned upstream manager.
        umr = shlex.quote(str(tools.get('umr') or self._command_path('umr') or 'umr'))
        register = 'mmSPI_PG_ENABLE_STATIC_WGP_MASK'
        return exported + (
            'if [ -z "${UMR_ASIC:-}" ]; then '
            'bc250_default_asic=cyan_skillfish.gfx1013; '
            f'if {umr} -r "$bc250_default_asic.{register}" 2>/dev/null | '
            "grep -Eq '0x[0-9a-fA-F]+'; then export UMR_ASIC=\"$bc250_default_asic\"; "
            'else while IFS= read -r bc250_candidate; do '
            'case "$bc250_candidate" in *cyan_skillfish*|*gfx1013*) ;; *) continue ;; esac; '
            f'if {umr} -r "$bc250_candidate.{register}" 2>/dev/null | '
            "grep -Eq '0x[0-9a-fA-F]+'; then export UMR_ASIC=\"$bc250_candidate\"; break; fi; "
            f"done < <({umr} -lb 2>/dev/null | awk '/^[[:space:]]*[a-zA-Z0-9_.-]+/{{print $1}}'); fi; "
            'fi; '
        )


    def _error_steamos_umr_selector(self, texto):
        texto = (texto or '').lower()
        pistas = [
            'cu_umr_database_invalid',
            'invalid asic header line',
            'cyan_skillfish.asic is empty',
            'invalid cyan_skillfish.asic header',
            'missing or empty soc15',
            'missing: mmspi_pg_enable_static_wgp_mask',
            'cu_umr_asic_binding',
            'cu_umr_version',
            'cu_umr_register_access',
            'unknown asic [amd13fe]',
            'should be added to pci.did',
            'regspi_pg_enable_static_wgp_mask',
            'path <cyan_skillfish',
            'failed to bind/read cyan_skillfish.gfx1013',
            'failed to bind/read cyan_skillfish.gfx1010',
            'cu_umr_storage_full',
            'no space left on device',
            'no queda espacio en el dispositivo',
            'mmspi_pg_enable_static_wgp_mask',
            'static cyan_skillfish model',
        ]
        return any(pista in texto for pista in pistas)


    def _mensaje_steamos_umr_selector(self):
        tools = self.estado_herramientas_bc250()
        database = tools.get('cu_steamos_umr_database') or '~/.local/share/bc250-control-center/ResourceTools/umr-steamos/database'
        return (
            'SteamOS Game Mode was verified, but UMR could not read the BC-250 CU registers.\n\n'
            "The previous build used two wrong assumptions: it stored the full UMR database on SteamOS' tiny "
            '/var partition, and it tried the nonexistent register namespace cyan_skillfish.gfx1013 before the '
            'database-defined GC register selector. That caused partial databases, long selector scans, '
            'and the page remaining in Working state.\n\n'
            'This build stores the SteamOS-only database under /home, derives the cyan_skillfish GC selector from that validated database, and '
            'performs at most one bounded fallback. Other Linux distribution backends are unchanged.\n\n'
            'From Desktop Mode, run Prepare dependencies once. The expected database is:\n'
            f'{database}\n\n'
            'If preparation reports CU_UMR_STORAGE_FULL, free space on /home. The obsolete /var database copies '
            'are removed only after the new database validates successfully.'
        )



    _CU_ROW_NAMES = ('SE0.SH0', 'SE0.SH1', 'SE1.SH0', 'SE1.SH1')


    def _dashboard_cu_tiene_tabla(self, texto):
        limpio = self._limpiar_dashboard_cu(texto or '')
        return bool(
            re.search(r'CUs\s+active\s*&?\s*routed\s*:\s*\d+\s*/\s*40', limpio, re.IGNORECASE)
            and re.search(r'\|\s*SE[01]\.SH[01]\s*\|', limpio)
        )


    def _estado_cu_base(self):
        rows = []
        for index, name in enumerate(self._CU_ROW_NAMES):
            rows.append({
                'index': index,
                'name': name,
                'tokens': ['D+', 'D+', 'D+', '--', '--'],
                'mask': 0x07,
                'driver_mask': 0x07,
                'spi': '0x07',
                'cc': '--',
                'cus': 6,
            })
        return {
            'available': False,
            'fresh': False,
            'source': 'factory fallback',
            'source_kind': 'fallback',
            'raw': '',
            'rows': rows,
            'masks': [0x07, 0x07, 0x07, 0x07],
            'driver_masks': [0x07, 0x07, 0x07, 0x07],
            'active_cus': 24,
            'total_cus': 40,
            'routed_wgps': 12,
            'total_wgps': 20,
            'mode': 'Factory 24 CUs',
            'mode_key': 'factory',
            'umr': '',
            'umr_instance': '',
            'asic': 'unknown',
            'amdgpu_mode': 'not exposed',
            'amdgpu_active_cus': 'unknown',
            'service': 'Not installed',
            'service_installed': False,
            'service_enabled': False,
            'boot_sync': 'Not saved',
            'boot_sync_key': 'not_saved',
            'privileged_backend_ready': False,
            'privileged_backend_reason': self._cu_backend_untrusted_message(),
            'driver_topology_available': False,
            'updated_at': '--:--:--',
            'parse_error': '',
        }


    def parsear_dashboard_cu(self, texto, source="live"):
        return parse_dashboard(
            texto,
            base_state=self._estado_cu_base(),
            row_names=self._CU_ROW_NAMES,
            source=source,
            updated_at=time.strftime("%H:%M:%S"),
        )


    def obtener_estado_cu_cache(self):
        runtime_snapshot = self._leer_dashboard_cu_quick_access_runtime()
        texto = self._leer_dashboard_cu_cache()
        local_state = None
        local_mtime = -1.0
        if texto:
            local_state = self.parsear_dashboard_cu(texto, source='authorized cache')
            local_state['source_kind'] = 'authorized_cache'
            local_state['fresh'] = False
            try:
                ruta = self._dashboard_cu_cache_path()
                local_mtime = ruta.stat().st_mtime
                local_state['updated_at'] = time.strftime('%H:%M:%S', time.localtime(local_mtime))
            except OSError:
                logger.debug("Could not read the CU cache modification time", exc_info=True)

        # The newest valid snapshot wins.  This makes Quick Access changes
        # immediately visible to Qt while allowing a later explicit Desktop
        # live read/action to replace an older /run snapshot.
        if runtime_snapshot is not None and (
            local_state is None or runtime_snapshot[1] >= local_mtime
        ):
            estado = runtime_snapshot[0]
        elif local_state is not None:
            estado = local_state
        else:
            state = self._estado_cu_base()
            tools = self.estado_herramientas_bc250()
            state['privileged_backend_ready'] = bool(tools.get('cu_privileged_backend_ready'))
            state['privileged_backend_reason'] = str(tools.get('cu_privileged_backend_reason') or '')
            return self._reconcile_cached_service_state(state)

        tools = self.estado_herramientas_bc250()
        estado['privileged_backend_ready'] = bool(tools.get('cu_privileged_backend_ready'))
        estado['privileged_backend_reason'] = str(tools.get('cu_privileged_backend_reason') or '')
        return self._reconcile_cached_service_state(estado)


    def obtener_estado_cu(self):
        return self._estado_cu_autorizado(self.obtener_dashboard_cu())


    def _estado_cu_autorizado(self, texto):
        estado = self.parsear_dashboard_cu(texto, source='live')
        estado['source_kind'] = 'live'
        if not estado.get('available'):
            raise RuntimeError(
                estado.get('parse_error')
                or 'The 40CU live-manager output did not contain a validated topology table.'
            )
        tools = self.estado_herramientas_bc250()
        estado['privileged_backend_ready'] = bool(tools.get('cu_privileged_backend_ready'))
        estado['privileged_backend_reason'] = str(tools.get('cu_privileged_backend_reason') or '')
        return self._reconcile_cached_service_state(estado)

    @staticmethod
    def _require_cu_persistence_backend(action):
        init_manager = detect_init_manager()
        if init_manager.persistence_supported:
            return init_manager
        raise RuntimeError(
            f'CU boot persistence is not supported on {init_manager.display_name}. '
            f'The {action} action was not run; live CU status and temporary routing remain available.'
        )


    def _validar_mascaras_cu(self, masks):
        return list(validate_cu_masks(masks))


    def _ejecutar_tabla_cu(self, masks, *, save_boot=False):
        # Removals are intentionally applied first so a partial failure cannot
        # leave a board at an unexpectedly larger CU topology.
        operations = plan_cu_mask_operations(masks, save_boot=save_boot)
        if getattr(self, '_usar_steamos_cu_helper', lambda: False)():
            estado = self._ejecutar_lote_cu_steamos(operations)
            if save_boot:
                estado['boot_sync'], estado['boot_sync_key'] = 'Current table saved', 'saved'
                self._actualizar_persistencia_dashboard_cu_cache('save_boot')
            return estado
        # One typed request includes every mask operation and its final readback.
        texto = self._ejecutar_cu_accion_pkexec([
            'batch', json.dumps(operations, separators=(',', ':')),
        ])
        estado = self._estado_cu_autorizado(texto)
        if save_boot:
            estado['boot_sync'], estado['boot_sync_key'] = 'Current table saved', 'saved'
            self._actualizar_persistencia_dashboard_cu_cache('save_boot')
        return estado


    def _ejecutar_lote_cu_steamos(self, operations):
        normalized = []
        for operation in operations:
            self._cu_helper_action_name(operation)
            normalized.append([str(item) for item in operation])
        if not normalized or len(normalized) > 8:
            raise ValueError('Invalid CU batch operation count.')
        payload = json.dumps(normalized, separators=(',', ':'))
        texto = self._ejecutar_steamos_game_helper('cu', 'batch', payload, timeout=240)
        if not self._dashboard_cu_tiene_tabla(texto):
            raise RuntimeError(
                'The authorized CU batch completed without a validated topology table.'
            )
        self._guardar_dashboard_cu_cache(texto)
        return self._estado_cu_autorizado(texto)


    def aplicar_tabla_cu(self, masks):
        return self._ejecutar_tabla_cu(masks, save_boot=False)


    def guardar_tabla_cu(self, masks):
        return self._ejecutar_tabla_cu(masks, save_boot=True)


    def ejecutar_accion_cu_grafica(self, accion):
        if accion in {
            'factory_repair', 'save_boot', 'install_service',
            'apply_saved', 'remove_service',
        }:
            self._require_cu_persistence_backend(accion)
        if accion == 'factory_repair':
            # A stale systemd unit can still point at a removed
            # /usr/local/bin manager. Factory recovery must remove that unit
            # before restoring the amdgpu table; otherwise the next boot can
            # replay the broken unit and undo the recovery.
            operations = (
                ('--yes', 'uninstall-service'),
                ('--yes', 'stock-dispatch'),
            )
            if getattr(self, '_usar_steamos_cu_helper', lambda: False)():
                return self._ejecutar_lote_cu_steamos(operations)
            if detect_init_manager().kind == 'openrc':
                self._ejecutar_openrc_cu_service('remove')
            else:
                self._ejecutar_cu_accion_pkexec(list(operations[0]))
            texto = self._ejecutar_cu_accion_pkexec(list(operations[1]))
            if not self._dashboard_cu_tiene_tabla(texto):
                return self.obtener_estado_cu()
            return self.parsear_dashboard_cu(texto, source='live')
        acciones = {
            'full': ['--yes', 'enable', 'all'],
            'factory': ['--yes', 'stock-dispatch'],
            'disable_all': ['--yes', 'disable', 'all'],
            'save_boot': ['--yes', 'write-service-table'],
            'install_service': ['--yes', 'install-service'],
            'apply_saved': ['--yes', 'apply-service'],
            'remove_service': ['--yes', 'uninstall-service'],
        }
        if accion not in acciones:
            raise ValueError('Invalid graphical CU action.')
        openrc = detect_init_manager().kind == 'openrc'
        if openrc and accion == 'install_service':
            texto = self._ejecutar_openrc_cu_service('install')
        elif openrc and accion == 'remove_service':
            texto = self._ejecutar_openrc_cu_service('remove')
        else:
            texto = self._ejecutar_cu_accion_pkexec(acciones[accion])
        if self._dashboard_cu_tiene_tabla(texto):
            estado = self.parsear_dashboard_cu(texto, source='live')
        elif accion in {'save_boot', 'install_service', 'remove_service'}:
            # These operations do not alter live routing. Reuse the last
            # authorized snapshot and update only the action-authoritative
            # persistence fields below; never open a second Polkit prompt.
            estado = self.obtener_estado_cu_cache()
        else:
            raise RuntimeError(
                'The authorized CU action completed without a validated topology table.'
            )
        # Some reviewed manager revisions omit service/config metadata from
        # their post-action status output. The action itself is authoritative
        # for these telemetry fields, so keep the cards consistent immediately
        # after Save/Install/Remove instead of showing stale "Optional" data.
        if accion == 'save_boot':
            estado['boot_sync'], estado['boot_sync_key'] = 'Current table saved', 'saved'
        elif accion == 'install_service':
            estado['service'] = 'Enabled'
            estado['service_installed'] = True
            estado['service_enabled'] = True
        elif accion == 'remove_service':
            estado['service'] = 'Not installed'
            estado['service_installed'] = False
            estado['service_enabled'] = False
            estado['boot_sync'], estado['boot_sync_key'] = 'Not saved', 'not_saved'
        if accion in {'save_boot', 'install_service', 'remove_service'}:
            self._actualizar_persistencia_dashboard_cu_cache(accion)
        # parse_dashboard starts from a conservative base state. Preserve the
        # trust result for the staged backend in action responses as well;
        # otherwise Install service/Save replace a writable page state with a
        # state that appears untrusted and every other button becomes disabled.
        tools = self.estado_herramientas_bc250()
        estado['privileged_backend_ready'] = bool(tools.get('cu_privileged_backend_ready'))
        estado['privileged_backend_reason'] = str(tools.get('cu_privileged_backend_reason') or '')
        return estado
