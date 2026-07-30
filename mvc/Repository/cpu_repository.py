import shlex
import configparser
from pathlib import Path
import os
import psutil
from mvc.Repository.cpu_telemetry import build_cpu_telemetry
from mvc.Repository.hardware_identity import is_bc250_platform


CORE_UNLOCK_REPOSITORY = 'https://github.com/rw-r-r-0644/bc250-core-unlock'
CORE_UNLOCK_DIRECTORY = 'bc250-core-unlock'
CORE_UNLOCK_SCRIPT = 'bc250-unlock-cores.py'
CORE_UNLOCK_ORIGINS = {
    CORE_UNLOCK_REPOSITORY,
    f'{CORE_UNLOCK_REPOSITORY}.git',
}

class CPURepository:
    def _core_unlock_repository_state(self, repository):
        script = repository / CORE_UNLOCK_SCRIPT
        if not (repository / '.git').is_dir() or not script.is_file():
            return '', False, False
        rc, out, _err = self._ejecutar(
            ['git', '-C', str(repository), 'remote', 'get-url', 'origin'],
            timeout=3,
        )
        origin = out.strip() if rc == 0 else ''
        rc, out, _err = self._ejecutar(
            ['git', '-C', str(repository), 'status', '--porcelain', '--untracked-files=all'],
            timeout=3,
        )
        clean = rc == 0 and not out.strip()
        rc_head, head, _err = self._ejecutar(
            ['git', '-C', str(repository), 'rev-parse', 'HEAD'],
            timeout=3,
        )
        rc_upstream, upstream, _err = self._ejecutar(
            ['git', '-C', str(repository), 'rev-parse', 'refs/remotes/origin/main'],
            timeout=3,
        )
        revision_matches = (
            rc_head == 0
            and rc_upstream == 0
            and bool(head.strip())
            and head.strip() == upstream.strip()
        )
        return origin, clean, revision_matches

    def _core_unlock_helper_path(self):
        candidates = (
            Path('/usr/libexec/bc250-control-center/bc250-core-unlock-helper'),
            Path('/usr/local/libexec/bc250-control-center/bc250-core-unlock-helper'),
        )
        for candidate in candidates:
            try:
                metadata = candidate.stat(follow_symlinks=False)
            except OSError:
                continue
            if candidate.is_symlink() or not candidate.is_file():
                continue
            if metadata.st_uid != 0 or metadata.st_mode & 0o022:
                continue
            if os.access(candidate, os.X_OK):
                return str(candidate)
        return ''

    def estado_desbloqueo_nucleos_cpu(self):
        logical = os.cpu_count() or 0
        physical = psutil.cpu_count(logical=False) or 0
        hardware_detected = is_bc250_platform()
        repository = self._tool_dir() / CORE_UNLOCK_DIRECTORY
        script = repository / CORE_UNLOCK_SCRIPT
        origin, clean, revision_matches = self._core_unlock_repository_state(repository)
        repository_ready = bool(
            origin in CORE_UNLOCK_ORIGINS
            and clean
            and revision_matches
        )
        try:
            cpuinfo_text = Path('/proc/cpuinfo').read_text(encoding='utf-8', errors='replace')
        except OSError:
            cpuinfo_text = ''
        telemetry = build_cpu_telemetry(
            cpuinfo_text,
            psutil.cpu_percent(interval=None, percpu=True),
        )
        governor_service = 'cyan-skillfish-governor-smu.service'
        governor_active = self._systemctl_valor(['is-active', governor_service]) == 'active'
        governor_enabled = self._systemctl_valor(['is-enabled', governor_service]) == 'enabled'
        return {
            'physical_cores': int(physical),
            'logical_cpus': int(logical),
            'unlocked': physical >= 8 and logical >= 16,
            'supported_stock_shape': hardware_detected and physical == 6 and logical == 12,
            'hardware_detected': hardware_detected,
            'helper_ready': bool(self._core_unlock_helper_path()),
            'repository_ready': repository_ready,
            'repository_path': str(repository),
            'script_path': str(script) if script.is_file() else '',
            'repository_origin': origin,
            'repository_clean': clean,
            'repository_revision_matches': revision_matches,
            'reference_url': CORE_UNLOCK_REPOSITORY,
            'integration': 'official-upstream-clone',
            'volatile_after_power_off': True,
            'processor': telemetry['processor'],
            'cores': telemetry['cores'],
            'governor_active': governor_active,
            'governor_enabled': governor_enabled,
        }

    def comando_desbloquear_nucleos_cpu(self):
        helper = self._core_unlock_helper_path()
        if not helper:
            raise RuntimeError(
                'The privileged CPU core unlock helper is not installed. '
                'Reinstall BC250 Control Center before using this action.'
            )
        if not self._command_path('pkexec'):
            raise RuntimeError('polkit/pkexec was not found. It is required for CPU core unlock.')
        repository = self._tool_dir() / CORE_UNLOCK_DIRECTORY
        script = repository / CORE_UNLOCK_SCRIPT
        if not (repository / '.git').is_dir() or not script.is_file():
            raise RuntimeError(
                'The official bc250-core-unlock repository is not prepared. '
                'Clone it from the CPU page before using this action.'
            )
        return ['pkexec', helper, '--repo', str(repository), '--reboot']

    def ejecutar_cpu_oc_temporal(self, frecuencia, vid, temp=90):
        frecuencia = int(frecuencia)
        vid = int(vid)
        temp = int(temp)
        if frecuencia < 3000 or frecuencia > 4200:
            raise ValueError('The UI limits temporary CPU OC to 3000-4200 MHz')
        if vid < 900 or vid > 1375:
            raise ValueError('The UI limits VID to 900-1375 mV')
        if temp < 70 or temp > 90:
            raise ValueError('The UI limits CPU/GPU temperature to 70-90 C')
        tools = self.estado_herramientas_bc250()
        prefijo = ''
        if not tools.get('stress'):
            stress_cmd = self._comando_instalar_stress()
            if not stress_cmd:
                raise RuntimeError('stress is missing. bc250_smu_oc needs it to detect active cores. Install the stress package and try again.')
            if self._es_ostree():
                comando = (
                    'echo "== stress is missing: installing dependency required by bc250_smu_oc =="; '
                    f'{stress_cmd}; '
                    'echo; '
                    'echo "== REBOOT REQUIRED =="; '
                    'echo "Bazzite/rpm-ostree prepared stress for the next boot."; '
                    'echo "Reboot with: systemctl reboot"; '
                    'echo "After reboot, run CPU OC again."'
                )
                return self._abrir_terminal(comando, 'Install stress for CPU OC')
            prefijo = f'echo "== stress is missing: installing dependency required by bc250_smu_oc =="; {stress_cmd}; command -v stress || exit 1; '
        if tools['bc250_detect']:
            cmd = f'{shlex.quote(tools["bc250_detect"])} --frequency {frecuencia} --vid {vid} --temp {temp} --keep'
        elif tools['smu_oc_exists']:
            path = shlex.quote(tools['smu_oc_path'])
            cmd = f'cd {path} && PYTHONPATH=. python bc250_detect.py --frequency {frecuencia} --vid {vid} --temp {temp} --keep'
        else:
            raise RuntimeError('bc250-detect and the local bc250_smu_oc repository were not found')
        return self._abrir_terminal(prefijo + cmd, f'CPU OC {frecuencia} MHz')



    def comando_cpu_oc_temporal_embebido(self, frecuencia, vid, temp=90):
        frecuencia = int(frecuencia)
        vid = int(vid)
        temp = int(temp)
        if frecuencia < 3000 or frecuencia > 4200:
            raise ValueError('The UI limits temporary CPU OC to 3000-4200 MHz')
        if vid < 900 or vid > 1375:
            raise ValueError('The UI limits VID to 900-1375 mV')
        if temp < 70 or temp > 90:
            raise ValueError('The UI limits CPU/GPU temperature to 70-90 C')
        if self._usar_steamos_game_helper():
            return self._comando_steamos_game_helper('cpu-oc-temp', frecuencia, vid, temp)
        if not self._command_path('pkexec'):
            raise RuntimeError('polkit/pkexec was not found. Install polkit to use the embedded console with graphical authentication.')

        tools = self.estado_herramientas_bc250()
        if not tools.get('stress'):
            raise RuntimeError('stress is missing. Press Prepare dependencies or install the stress package before using CPU OC.')

        if tools['bc250_detect']:
            cmd = f'{shlex.quote(tools["bc250_detect"])} --frequency {frecuencia} --vid {vid} --temp {temp} --keep'
        elif tools['smu_oc_exists']:
            path = shlex.quote(tools['smu_oc_path'])
            python_cmd = self._command_path('python3') or self._command_path('python') or 'python3'
            cmd = f'cd {path} && PYTHONPATH=. {shlex.quote(python_cmd)} bc250_detect.py --frequency {frecuencia} --vid {vid} --temp {temp} --keep'
        else:
            raise RuntimeError('bc250-detect and the local bc250_smu_oc repository were not found')

        bash = self._command_path('bash') or '/bin/bash'
        comando = (
            'echo "== Temporary BC250 CPU OC =="; '
            f'echo "Frequency: {frecuencia} MHz | VID: {vid} mV | Temp: {temp} C"; '
            'echo "Authenticated with Polkit. No permanent service is installed."; '
            'echo "Starting bc250-detect. It may take a while while it detects cores and applies parameters."; '
            'echo "Monitor CPU frequency at the top of the app."; '
            'echo; '
            f'{cmd}; '
            'estado=$?; '
            'echo; '
            'echo "== Process finished with exit code $estado =="; '
            'exit $estado'
        )
        return ['pkexec', bash, '-lc', comando]


    def comando_cpu_oc_persistente_embebido(self):
        if not self._command_path('pkexec'):
            raise RuntimeError('polkit/pkexec was not found. Install polkit to authenticate persistent changes.')
        tools = self.estado_herramientas_bc250()
        if not tools.get('smu_oc_exists'):
            raise RuntimeError('The local bc250_smu_oc repository was not found. Use Prepare dependencies first.')

        repo = Path(tools['smu_oc_path'])
        config = repo / 'overclock.conf'
        apply_py = repo / 'bc250_apply.py'
        if not config.exists():
            raise RuntimeError('overclock.conf was not found. First apply and test a temporary CPU OC with bc250-detect.')
        if not apply_py.exists():
            raise RuntimeError('bc250_apply.py was not found inside bc250_smu_oc.')

        datos = configparser.ConfigParser()
        datos.read(config)
        frecuencia = datos.getint('overclock', 'frequency', fallback=0)
        escala = datos.getint('overclock', 'scale', fallback=0)
        temp = datos.getint('overclock', 'max_temperature', fallback=0)
        if frecuencia < 3000 or frecuencia > 4200:
            raise RuntimeError(f'overclock.conf has a frequency outside the UI limit: {frecuencia} MHz')
        if temp < 70 or temp > 90:
            raise RuntimeError(f'overclock.conf has a temperature outside the UI limit: {temp} C')
        if escala < -50 or escala > 0:
            raise RuntimeError(f'overclock.conf has a scale outside the safe limit: {escala}')

        bash = self._command_path('bash') or '/bin/bash'
        python_cmd = self._command_path('python3') or self._command_path('python') or 'python3'
        qrepo = shlex.quote(str(repo))
        qapply = shlex.quote(str(apply_py))
        qconfig = shlex.quote(str(config))
        qpython = shlex.quote(str(python_cmd))
        comando = (
            'echo "== Persistent BC250 CPU OC =="; '
            f'echo "Config validated: {frecuencia} MHz | scale {escala} | temp {temp} C"; '
            'echo "Installing /etc/bc250-smu-oc.conf and bc250-smu-oc.service"; '
            f'cd {qrepo} && PYTHONPATH=. {qpython} {qapply} --install {qconfig}; '
            'estado=$?; '
            'if [ $estado -eq 0 ]; then '
            'systemctl daemon-reload; '
            'systemctl enable bc250-smu-oc.service; '
            'echo "Persistent service enabled: bc250-smu-oc.service"; '
            'echo "It will apply at system boot."; '
            'else echo "Failed to install persistent configuration"; fi; '
            'echo; '
            'echo "== Process finished with exit code $estado =="; '
            'exit $estado'
        )
        return ['pkexec', bash, '-lc', comando]

    def estado_cpu_oc_persistente(self):
        servicio = 'bc250-smu-oc.service'
        existe_servicio = Path('/etc/systemd/system/bc250-smu-oc.service').exists() or Path('/usr/lib/systemd/system/bc250-smu-oc.service').exists()
        existe_config = Path('/etc/bc250-smu-oc.conf').exists()
        activo = self._systemctl_valor(['is-active', servicio])
        habilitado = self._systemctl_valor(['is-enabled', servicio])
        codigo, salida, error = self._ejecutar(['systemctl', 'status', servicio, '--no-pager', '--lines=8'], timeout=3)
        texto = salida or error or ''
        props = self._systemctl_show(servicio)
        result = props.get('Result') or ''
        exec_status = props.get('ExecMainStatus') or ''
        exec_code = props.get('ExecMainCode') or ''
        active_state = props.get('ActiveState') or activo
        sub_state = props.get('SubState') or ''
        oneshot_ok = bool(
            habilitado == 'enabled'
            and active_state == 'inactive'
            and result in ('success', '')
            and exec_status in ('0', '')
            and ('status=0/SUCCESS' in texto or exec_status == '0')
        )
        aplicado = bool(
            active_state == 'active'
            or oneshot_ok
            or (habilitado == 'enabled' and existe_config and result in ('success', ''))
        )
        if active_state == 'failed' or result not in ('', 'success'):
            estado_ui = 'Failed'
            detalle_ui = f'Result {result or active_state}'
        elif oneshot_ok:
            estado_ui = 'Aplicado / enabled'
            detalle_ui = 'One-shot finished successfully; it will repeat at boot'
        elif active_state == 'active':
            estado_ui = 'Active / enabled' if habilitado == 'enabled' else 'Active'
            detalle_ui = 'Running now'
        elif habilitado == 'enabled':
            estado_ui = 'Ready / enabled'
            detalle_ui = 'Enabled for next boot'
        else:
            estado_ui = 'Disabled'
            detalle_ui = 'Does not start automatically'
        return {
            'service': servicio,
            'exists': existe_servicio,
            'config_exists': existe_config,
            'active': activo,
            'enabled': habilitado,
            'active_state': active_state,
            'sub_state': sub_state,
            'result': result,
            'exec_status': exec_status,
            'exec_code': exec_code,
            'oneshot_ok': oneshot_ok,
            'applied': aplicado,
            'ui_state': estado_ui,
            'ui_detail': detalle_ui,
            'last_start': props.get('ExecMainStartTimestamp') or '',
            'last_exit': props.get('ExecMainExitTimestamp') or '',
            'status_code': codigo,
            'status_text': texto,
        }

    def comando_cpu_oc_desactivar_persistente_embebido(self):
        if not self._command_path('pkexec'):
            raise RuntimeError('polkit/pkexec was not found. Install polkit to disable the persistent service.')
        bash = self._command_path('bash') or '/bin/bash'
        comando = (
            'echo "== Disabling persistent BC250 CPU OC =="; '
            'if systemctl list-unit-files bc250-smu-oc.service >/dev/null 2>&1 || [ -f /etc/systemd/system/bc250-smu-oc.service ]; then '
            'systemctl disable --now bc250-smu-oc.service; '
            'estado=$?; '
            'systemctl reset-failed bc250-smu-oc.service >/dev/null 2>&1 || true; '
            'systemctl daemon-reload; '
            'echo "bc250-smu-oc.service stopped/disabled."; '
            'echo "/etc/bc250-smu-oc.conf is not deleted so you can review or reinstall later."; '
            'else '
            'echo "bc250-smu-oc.service does not exist in systemd."; '
            'estado=0; '
            'fi; '
            'echo; '
            'systemctl is-active bc250-smu-oc.service 2>/dev/null | sed "s/^/active: /" || true; '
            'systemctl is-enabled bc250-smu-oc.service 2>/dev/null | sed "s/^/enabled: /" || true; '
            'echo; '
            'echo "== Process finished with exit code $estado =="; '
            'exit $estado'
        )
        return ['pkexec', bash, '-lc', comando]

    def _systemctl_valor(self, argumentos):
        codigo, salida, error = self._ejecutar(['systemctl', *argumentos], timeout=2)
        texto = (salida or error or '').strip()
        if texto:
            return texto.splitlines()[0].strip()
        return 'unknown' if codigo else 'ok'

    def _systemctl_show(self, servicio):
        props = [
            'ActiveState', 'SubState', 'UnitFileState', 'Result',
            'ExecMainStatus', 'ExecMainCode', 'ExecMainStartTimestamp', 'ExecMainExitTimestamp'
        ]
        codigo, salida, error = self._ejecutar(['systemctl', 'show', servicio, '--property=' + ','.join(props)], timeout=2)
        datos = {}
        texto = salida or error or ''
        for linea in texto.splitlines():
            if '=' not in linea:
                continue
            clave, valor = linea.split('=', 1)
            datos[clave.strip()] = valor.strip()
        return datos
