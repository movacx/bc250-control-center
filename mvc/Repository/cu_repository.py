from pathlib import Path
import re
import shlex
import shutil
import time

class CURepository:
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
        script = tools.get('cu_manager') or ''
        if script and Path(script).exists():
            comandos = [
                {'cmd': ['sudo', '-n', script, 'status'], 'timeout': 12},
                {'cmd': ['pkexec', script, 'status'], 'timeout': 90},
                {'cmd': [script, 'status'], 'timeout': 12},
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
                if rc == 0 and salida:
                    limpio = self._limpiar_dashboard_cu(salida)
                    self._guardar_dashboard_cu_cache(limpio)
                    return limpio
                errores.append((err or out or f'exit code {rc}').strip())
            detalle = '\n'.join(x for x in errores if x)
            if self._error_umr_faltante(detalle):
                raise RuntimeError(self._mensaje_umr_faltante())
            if self._requiere_terminal_sudo(detalle):
                cache = self._leer_dashboard_cu_cache()
                if cache:
                    return cache
                raise RuntimeError(
                    'The live dashboard needs administrator permissions. '
                    'If the Polkit window does not appear, check that your desktop has an active authentication agent.'
                )
            raise RuntimeError(detalle or 'Could not read live-manager dashboard')
        raise RuntimeError('bc250-cu-live-manager was not found. Use Prepare dependencies first.')


    def _dashboard_cu_cache_path(self):
        return self.configuracion.carpeta_data() / 'cu_dashboard_live.txt'


    def _guardar_dashboard_cu_cache(self, texto):
        try:
            ruta = self._dashboard_cu_cache_path()
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_text((texto or '').strip() + '\n', encoding='utf-8')
        except Exception:
            pass


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
        if not tools['cu_manager_exists']:
            raise RuntimeError('bc250-cu-live-manager was not found. Use Prepare dependencies first.')
        if accion == 'status':
            return self.obtener_dashboard_cu()
        elif accion == 'enable40':
            return self._ejecutar_cu_accion_pkexec(['--yes', 'enable', 'all'])
        elif accion == 'stock':
            return self._ejecutar_cu_accion_pkexec(['--yes', 'stock-dispatch'])
        elif accion == 'menu':
            script = shlex.quote(tools['cu_manager'])
            return self._abrir_terminal(f'sudo {script} menu', 'BC-250 40CU live-manager')
        else:
            raise ValueError('Invalid CU action.')


    def _ejecutar_cu_accion_pkexec(self, args):
        if not self._command_path('pkexec'):
            raise RuntimeError('polkit/pkexec was not found. Install polkit or use Service / custom profile from a terminal.')
        tools = self.estado_herramientas_bc250()
        script = tools.get('cu_manager') or ''
        if not script:
            raise RuntimeError('bc250-cu-live-manager was not found. Use Prepare dependencies first.')

        bash = self._command_path('bash') or '/bin/bash'
        accion = ' '.join([shlex.quote(script)] + [shlex.quote(str(x)) for x in args])
        status = f'{shlex.quote(script)} status'
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
            raise RuntimeError(detalle)

        limpio = self._limpiar_dashboard_cu(out)
        self._guardar_dashboard_cu_cache(limpio)
        return limpio


    def _error_umr_faltante(self, texto):
        texto = (texto or '').lower()
        pistas = [
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
