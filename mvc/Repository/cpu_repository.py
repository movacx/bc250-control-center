import shlex
import configparser
from pathlib import Path

class CPURepository:
    def ejecutar_cpu_oc_temporal(self, frecuencia, vid, temp=90):
        frecuencia = int(frecuencia)
        vid = int(vid)
        temp = int(temp)
        if frecuencia < 3000 or frecuencia > 4000:
            raise ValueError('The UI limits temporary CPU OC to 3000-4000 MHz')
        if vid < 900 or vid > 1275:
            raise ValueError('The UI limits VID to 900-1275 mV')
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
        if frecuencia < 3000 or frecuencia > 4000:
            raise ValueError('The UI limits temporary CPU OC to 3000-4000 MHz')
        if vid < 900 or vid > 1275:
            raise ValueError('The UI limits VID to 900-1275 mV')
        if temp < 70 or temp > 90:
            raise ValueError('The UI limits CPU/GPU temperature to 70-90 C')
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
        if frecuencia < 3000 or frecuencia > 4000:
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
