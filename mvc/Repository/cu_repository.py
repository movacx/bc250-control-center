from pathlib import Path
import os
import logging
import re
import shlex
import time

logger = logging.getLogger(__name__)


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
            detalle = err or out or f'exit code {rc}'
            raise RuntimeError(detalle)
        lineas = []
        for linea in out.splitlines():
            texto = linea.strip()
            if re.search(r'\d+/\d+\s+CUs\s+active', texto, re.IGNORECASE):
                continue
            lineas.append(linea)
        return '\n'.join(lineas).strip()


    def obtener_dashboard_cu(self):
        tools = self.estado_herramientas_bc250()
        script = self._cu_manager_script_or_raise(tools)
        if script:
            if self._usar_steamos_game_helper():
                salida = self._ejecutar_steamos_game_helper('cu', 'status', timeout=25)
                if salida and self._dashboard_cu_tiene_tabla(salida):
                    limpio = self._limpiar_dashboard_cu(salida)
                    self._guardar_dashboard_cu_cache(limpio)
                    return limpio
            bash = self._command_path('bash') or '/bin/bash'
            env_args = self._env_args_cu(tools)
            export_env = self._exportar_env_cu(tools)
            comandos = [
                {'cmd': ['sudo', '-n', 'env'] + env_args + [script, 'status'], 'timeout': 12},
                {'cmd': ['pkexec', bash, '-lc', f'{export_env}{shlex.quote(script)} status'], 'timeout': 90},
                {'cmd': ['env'] + env_args + [script, 'status'], 'timeout': 12},
            ]
            errores = []
            for item in comandos:
                comando = item['cmd']
                if comando[0] == 'pkexec' and not self._command_path('pkexec'):
                    continue
                try:
                    rc, out, err = self._ejecutar(comando, timeout=item['timeout'])
                except Exception as error:
                    errores.append(str(error))
                    continue
                salida = (out or '').strip()
                if rc == 0 and salida and self._dashboard_cu_tiene_tabla(salida):
                    limpio = self._limpiar_dashboard_cu(salida)
                    self._guardar_dashboard_cu_cache(limpio)
                    return limpio
                errores.append((err or out or f'exit code {rc}').strip())
            detalle = '\n'.join(x for x in errores if x)
            if self._error_umr_faltante(detalle):
                raise RuntimeError(self._mensaje_umr_faltante())
            if self._error_steamos_umr_selector(detalle):
                raise RuntimeError(self._mensaje_steamos_umr_selector())
            if self._requiere_terminal_sudo(detalle):
                cache = self._leer_dashboard_cu_cache()
                if cache:
                    return cache
                raise RuntimeError(
                    'The live dashboard needs administrator permissions. '
                    'If the Polkit window does not appear, check that your desktop has an active authentication agent.'
                )
            raise RuntimeError(detalle or 'Could not read live-manager dashboard')


    def _dashboard_cu_cache_path(self):
        return self.configuracion.carpeta_data() / 'cu_dashboard_live.txt'


    def _guardar_dashboard_cu_cache(self, texto):
        try:
            ruta = self._dashboard_cu_cache_path()
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_text((texto or '').strip() + '\n', encoding='utf-8')
        except OSError:
            logger.warning("Could not update the authorized CU dashboard cache", exc_info=True)


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
        ansi = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')
        lineas = []
        for linea in texto.splitlines():
            limpia = ansi.sub('', linea).rstrip()
            if limpia.strip() in ('', '== Process finished with exit code 0 =='):
                continue
            lineas.append(limpia)
        return '\n'.join(lineas).strip()


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
        script = self._cu_manager_script_or_raise(tools)
        if accion == 'status':
            return self.obtener_dashboard_cu()
        elif accion == 'enable40':
            return self._ejecutar_cu_accion_pkexec(['--yes', 'enable', 'all'])
        elif accion == 'stock':
            return self._ejecutar_cu_accion_pkexec(['--yes', 'stock-dispatch'])
        elif accion == 'menu':
            script = shlex.quote(script)
            export_env = self._exportar_env_cu(tools)
            return self._abrir_terminal(f'{export_env}sudo -E {script} menu', 'BC-250 40CU live-manager')
        else:
            raise ValueError('Invalid CU action.')


    def _ejecutar_cu_accion_pkexec(self, args):
        tools = self.estado_herramientas_bc250()
        script = self._cu_manager_script_or_raise(tools)
        if self._usar_steamos_game_helper():
            action_name = self._cu_helper_action_name(args)
            texto = self._ejecutar_steamos_game_helper('cu', 'action', action_name, timeout=70)
            limpio = self._limpiar_dashboard_cu(texto)
            if limpio:
                self._guardar_dashboard_cu_cache(limpio)
            return limpio
        if not self._command_path('pkexec'):
            raise RuntimeError('polkit/pkexec was not found. Install polkit or use Service / custom profile from a terminal.')

        bash = self._command_path('bash') or '/bin/bash'
        export_env = self._exportar_env_cu(tools)
        accion = export_env + ' '.join([shlex.quote(script)] + [shlex.quote(str(x)) for x in args])
        status = export_env + f'{shlex.quote(script)} status'
        comando = (
            f'{accion}; '
            'resultado=$?; '
            'echo; '
            'echo "== Current state =="; '
            f'{status}; '
            'exit $resultado'
        )
        rc, out, err = self._ejecutar(['pkexec', bash, '-lc', comando], timeout=180)
        if rc != 0:
            detalle = err or out or f'exit code {rc}'
            if self._error_umr_faltante(detalle):
                raise RuntimeError(self._mensaje_umr_faltante())
            if self._error_steamos_umr_selector(detalle):
                raise RuntimeError(self._mensaje_steamos_umr_selector())
            raise RuntimeError(detalle)

        limpio = self._limpiar_dashboard_cu(out)
        self._guardar_dashboard_cu_cache(limpio)
        return limpio


    def _cu_helper_action_name(self, args):
        normalized = [str(item) for item in args]
        mapping = {
            ('--yes', 'enable', 'all'): 'full',
            ('--yes', 'stock-dispatch'): 'factory',
            ('--yes', 'disable', 'all'): 'disable_all',
            ('--yes', 'write-service-table'): 'save_boot',
            ('--yes', 'install-service'): 'install_service',
            ('--yes', 'apply-service'): 'apply_saved',
            ('--yes', 'uninstall-service'): 'remove_service',
        }
        key = tuple(normalized)
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


    def _cu_manager_env(self, tools):
        env = {}
        if tools.get('cu_manager_backend') == 'steamos' or tools.get('is_steamos'):
            # SteamOS uses a generated compatibility copy of the F5GO backend.
            # UMR can expose PCI ID 1002:13fe as the generic model ``amd13fe``;
            # using cyan_skillfish.gfx1013 as the register namespace does not
            # rebind the active ASIC model.  The generated runtime therefore forces
            # the static cyan_skillfish model for every UMR read/write while keeping
            # the upstream F5GO register sequence intact.
            env['UMR_DATABASE_PATH'] = tools.get('cu_steamos_umr_database') or str(self._tool_dir() / 'umr-steamos' / 'database')
            env['UMR_ASIC'] = os.environ.get('UMR_ASIC') or 'cyan_skillfish.gfx1010'
            if os.environ.get('UMR_INSTANCE'):
                env['UMR_INSTANCE'] = os.environ['UMR_INSTANCE']
        return env


    def _env_args_cu(self, tools):
        return [f'{clave}={valor}' for clave, valor in self._cu_manager_env(tools).items() if valor]


    def _steamos_cu_env_probe_shell(self, tools):
        # The UMR database itself declares the graphics register block as
        # gfx1010. Older builds tried gfx1013 and up to eight DRI instances on
        # every click, which made the page look frozen for minutes. The patched
        # backend already auto-detects the concrete DRI instance, so only export
        # the validated database and exact register namespace here.
        return self._exportar_env_cu_simple(tools)



    def _exportar_env_cu_simple(self, tools):
        partes = []
        for clave, valor in self._cu_manager_env(tools).items():
            if valor:
                partes.append(f'export {clave}={shlex.quote(str(valor))}; ')
        return ''.join(partes)


    def _exportar_env_cu(self, tools):
        return self._exportar_env_cu_simple(tools)


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
            'database-defined cyan_skillfish.gfx1010 selector. That caused partial databases, long selector scans, '
            'and the page remaining in Working state.\n\n'
            'This build stores the SteamOS-only database under /home, uses cyan_skillfish.gfx1010 directly, and '
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
            'asic': 'cyan_skillfish.gfx1010',
            'amdgpu_mode': 'not exposed',
            'amdgpu_active_cus': 'unknown',
            'service': 'Not installed',
            'service_installed': False,
            'service_enabled': False,
            'boot_sync': 'Not saved',
            'boot_sync_key': 'not_saved',
            'driver_topology_available': False,
            'updated_at': '--:--:--',
        }


    def parsear_dashboard_cu(self, texto, source='live'):
        estado = self._estado_cu_base()
        limpio = self._limpiar_dashboard_cu(texto or '')
        estado['raw'] = limpio
        estado['source'] = source
        estado['fresh'] = source == 'live'
        estado['updated_at'] = time.strftime('%H:%M:%S')

        metadata = {
            'umr': r'^\s*UMR\s*:\s*(.+?)\s*$',
            'umr_instance': r'^\s*UMR inst\s*:\s*(.+?)\s*$',
            'asic': r'^\s*ASIC\s*:\s*(.+?)\s*$',
            'service': r'^\s*Service\s*:\s*(.+?)\s*$',
        }
        for key, pattern in metadata.items():
            match = re.search(pattern, limpio, re.IGNORECASE | re.MULTILINE)
            if match:
                estado[key] = match.group(1).strip()

        amdgpu = re.search(
            r'^\s*amdgpu\s*:\s*bc250_cc_write_mode=([^,]+),\s*active_cu_number=(.+?)\s*$',
            limpio,
            re.IGNORECASE | re.MULTILINE,
        )
        if amdgpu:
            estado['amdgpu_mode'] = amdgpu.group(1).strip()
            estado['amdgpu_active_cus'] = amdgpu.group(2).strip()

        service_text = str(estado.get('service') or '').strip()
        lowered_service = service_text.lower()
        estado['service_installed'] = bool(service_text and lowered_service not in {'not installed', 'missing', 'unknown'})
        estado['service_enabled'] = lowered_service in {'enabled', 'active', 'running'}
        if not estado['service_installed']:
            estado['service'] = 'Not installed'

        lowered = limpio.lower()
        if 'pending changes' in lowered:
            estado['boot_sync'] = 'Pending changes'
            estado['boot_sync_key'] = 'pending'
        elif 'current table saved' in lowered or 'saved boot table' in lowered:
            estado['boot_sync'] = 'Current table saved'
            estado['boot_sync_key'] = 'saved'
        elif 'no saved table' in lowered:
            estado['boot_sync'] = 'No saved table'
            estado['boot_sync_key'] = 'not_saved'
        elif estado['service_installed']:
            estado['boot_sync'] = 'Unknown'
            estado['boot_sync_key'] = 'unknown'

        row_pattern = re.compile(
            r'\|\s*(SE[01]\.SH[01])\s*\|\s*'
            r'(D\+|S\+|D!|--)\s*\|\s*'
            r'(D\+|S\+|D!|--)\s*\|\s*'
            r'(D\+|S\+|D!|--)\s*\|\s*'
            r'(D\+|S\+|D!|--)\s*\|\s*'
            r'(D\+|S\+|D!|--)\s*\|\s*'
            r'(0x[0-9a-fA-F]+)\s*\|\s*'
            r'([^|]+?)\s*\|\s*(\d+)\s*/\s*10\s*\|',
            re.IGNORECASE,
        )
        parsed_rows = {}
        for match in row_pattern.finditer(limpio):
            name = match.group(1).upper()
            tokens = [match.group(i).upper() for i in range(2, 7)]
            mask = 0
            driver_mask = 0
            for wgp, token in enumerate(tokens):
                if token in {'D+', 'S+'}:
                    mask |= 1 << wgp
                if token in {'D+', 'D!'}:
                    driver_mask |= 1 << wgp
            parsed_rows[name] = {
                'name': name,
                'tokens': tokens,
                'mask': mask,
                'driver_mask': driver_mask,
                'spi': match.group(7).lower(),
                'cc': match.group(8).strip(),
                'cus': int(match.group(9)),
            }

        if len(parsed_rows) == 4:
            rows = []
            for index, name in enumerate(self._CU_ROW_NAMES):
                row = dict(parsed_rows[name])
                row['index'] = index
                rows.append(row)
            estado['rows'] = rows
            estado['masks'] = [row['mask'] for row in rows]
            estado['driver_masks'] = [row['driver_mask'] for row in rows]
            estado['active_cus'] = sum(row['cus'] for row in rows)
            estado['routed_wgps'] = estado['active_cus'] // 2
            estado['driver_topology_available'] = any(row['driver_mask'] for row in rows)
            estado['available'] = True
        else:
            total_match = re.search(
                r'CUs\s+active\s*&?\s*routed\s*:\s*(\d+)\s*/\s*40',
                limpio,
                re.IGNORECASE,
            )
            if total_match:
                estado['active_cus'] = int(total_match.group(1))
                estado['routed_wgps'] = estado['active_cus'] // 2

        active = int(estado.get('active_cus') or 0)
        masks = list(estado.get('masks') or [])
        driver_masks = list(estado.get('driver_masks') or [])
        if active >= 40 and masks == [0x1f, 0x1f, 0x1f, 0x1f]:
            estado['mode'] = 'Full 40 CUs'
            estado['mode_key'] = 'full'
        elif estado.get('driver_topology_available') and masks == driver_masks:
            estado['mode'] = 'Factory 24 CUs'
            estado['mode_key'] = 'factory'
        elif active == 24 and masks == [0x07, 0x07, 0x07, 0x07]:
            estado['mode'] = 'Factory 24 CUs'
            estado['mode_key'] = 'factory'
        else:
            estado['mode'] = f'Custom {active} CUs'
            estado['mode_key'] = 'custom'

        return estado


    def obtener_estado_cu_cache(self):
        texto = self._leer_dashboard_cu_cache()
        if not texto:
            return self._estado_cu_base()
        estado = self.parsear_dashboard_cu(texto, source='authorized cache')
        estado['fresh'] = False
        try:
            ruta = self._dashboard_cu_cache_path()
            estado['updated_at'] = time.strftime('%H:%M:%S', time.localtime(ruta.stat().st_mtime))
        except OSError:
            logger.debug("Could not read the CU cache modification time", exc_info=True)
        return estado


    def obtener_estado_cu(self):
        return self.parsear_dashboard_cu(self.obtener_dashboard_cu(), source='live')


    def _validar_mascaras_cu(self, masks):
        if not isinstance(masks, (list, tuple)) or len(masks) != 4:
            raise ValueError('The WGP table must contain exactly four shader rows.')
        validated = []
        for value in masks:
            try:
                mask = int(value)
            except (TypeError, ValueError):
                raise ValueError('Every WGP row mask must be an integer between 0 and 31.')
            if mask < 0 or mask > 0x1f:
                raise ValueError('Every WGP row mask must be between 0x00 and 0x1f.')
            validated.append(mask)
        return validated


    def _comandos_tabla_cu(self, masks, script, export_env):
        enabled = []
        disabled = []
        for row_index, mask in enumerate(masks):
            se = row_index // 2
            sh = row_index % 2
            for wgp in range(5):
                item = f'{se}.{sh}.{wgp}'
                if mask & (1 << wgp):
                    enabled.append(item)
                else:
                    disabled.append(item)

        commands = ['set -e']
        # Apply removals before additions. This avoids the unsafe transient
        # "enable everything first" state that can leave the board at 40 CUs
        # if a later disable command fails or the backend rejects part of the
        # request.
        if disabled:
            command = [script, '--yes', 'disable-wgp'] + disabled
            commands.append(export_env + ' '.join(shlex.quote(str(part)) for part in command))
        if enabled:
            command = [script, '--yes', 'enable-wgp'] + enabled
            commands.append(export_env + ' '.join(shlex.quote(str(part)) for part in command))
        return commands


    def _ejecutar_tabla_cu(self, masks, *, save_boot=False):
        masks = self._validar_mascaras_cu(masks)
        tools = self.estado_herramientas_bc250()
        script = self._cu_manager_script_or_raise(tools)
        if self._usar_steamos_game_helper():
            helper_args = ['cu', 'table']
            if save_boot:
                helper_args.append('--save-boot')
            helper_args.extend(f'0x{mask:02x}' for mask in masks)
            texto = self._ejecutar_steamos_game_helper(*helper_args, timeout=70)
            limpio = self._limpiar_dashboard_cu(texto)
            if not self._dashboard_cu_tiene_tabla(limpio):
                raise RuntimeError('The WGP table was written, but the live state could not be verified.')
            estado = self.parsear_dashboard_cu(limpio, source='live')
            applied_masks = list(estado.get('masks') or [])
            if applied_masks != masks:
                expected = ', '.join(f'0x{mask:02x}' for mask in masks)
                actual = ', '.join(f'0x{int(mask):02x}' for mask in applied_masks) if applied_masks else 'unverified'
                raise RuntimeError(
                    'The WGP table was applied, but verification did not match the selected target. '
                    f'Expected masks: {expected}. Current masks: {actual}.'
                )
            self._guardar_dashboard_cu_cache(limpio)
            return estado
        if not self._command_path('pkexec'):
            raise RuntimeError('polkit/pkexec was not found. Install polkit before applying a graphical WGP table.')

        bash = self._command_path('bash') or '/bin/bash'
        export_env = self._exportar_env_cu(tools)
        commands = self._comandos_tabla_cu(masks, script, export_env)
        if save_boot:
            command = [script, '--yes', 'write-service-table']
            commands.append(export_env + ' '.join(shlex.quote(str(part)) for part in command))
        commands.append('echo')
        commands.append('echo "== Current state =="')
        commands.append(export_env + f'{shlex.quote(script)} status')
        shell_command = '; '.join(commands)

        rc, out, err = self._ejecutar(['pkexec', bash, '-lc', shell_command], timeout=240)
        if rc != 0:
            detalle = err or out or f'exit code {rc}'
            if self._error_umr_faltante(detalle):
                raise RuntimeError(self._mensaje_umr_faltante())
            if self._error_steamos_umr_selector(detalle):
                raise RuntimeError(self._mensaje_steamos_umr_selector())
            raise RuntimeError(detalle)

        limpio = self._limpiar_dashboard_cu(out)
        if not self._dashboard_cu_tiene_tabla(limpio):
            raise RuntimeError('The WGP table was written, but the live state could not be verified.')
        estado = self.parsear_dashboard_cu(limpio, source='live')
        applied_masks = list(estado.get('masks') or [])
        if applied_masks != masks:
            expected = ', '.join(f'0x{mask:02x}' for mask in masks)
            actual = ', '.join(f'0x{int(mask):02x}' for mask in applied_masks) if applied_masks else 'unverified'
            raise RuntimeError(
                'The WGP table was applied, but verification did not match the selected target. '
                f'Expected masks: {expected}. Current masks: {actual}.'
            )
        self._guardar_dashboard_cu_cache(limpio)
        return estado


    def aplicar_tabla_cu(self, masks):
        return self._ejecutar_tabla_cu(masks, save_boot=False)


    def guardar_tabla_cu(self, masks):
        return self._ejecutar_tabla_cu(masks, save_boot=True)


    def ejecutar_accion_cu_grafica(self, accion):
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
        texto = self._ejecutar_cu_accion_pkexec(acciones[accion])
        if not self._dashboard_cu_tiene_tabla(texto):
            # Some service operations may complete even if their appended status
            # cannot be read. Try a separate authorized state refresh before
            # reporting a verification failure.
            return self.obtener_estado_cu()
        return self.parsear_dashboard_cu(texto, source='live')
