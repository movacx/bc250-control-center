import os
import shlex
import time
from pathlib import Path

from mvc.Repository.governor_conflicts import ensure_no_incompatible_governors
from mvc.Repository.governor_toml import (
    CUSTOM_VOLTAGE_MAX_MV,
    CUSTOM_VOLTAGE_MIN_MV,
    SUPPORTED_VOLTAGE_LEVELS,
    VOLTAGE_BOOST_START_MHZ,
    GovernorTomlEditor,
    voltage_profile,
)


class GPURepository:
    _GOVERNOR_CONFIG = Path('/etc/cyan-skillfish-governor-smu/config.toml')
    _GOVERNOR_SERVICE = 'cyan-skillfish-governor-smu.service'
    _GOVERNOR_RANGE_INTERFACE = 'com.cyanskillfish.Governor.Range'

    def controlar_governor(self, accion, confirmar_conflictos=False, desactivar_conflictos=False):
        servicio = 'cyan-skillfish-governor-smu.service'
        if not self._command_path('cyan-skillfish-governor-smu'):
            raise RuntimeError('cyan-skillfish-governor-smu is not installed. Use Prepare dependencies first.')
        conflicts = []
        prefix = ''
        if accion in {'activar', 'reiniciar'}:
            conflicts = ensure_no_incompatible_governors(
                self,
                confirmed=bool(confirmar_conflictos or desactivar_conflictos),
            )
            if desactivar_conflictos and conflicts:
                prefix = self._comando_desactivar_gobernadores_incompatibles(conflicts) + '; '
        if accion == 'activar':
            comando = prefix + f'sudo systemctl enable --now {servicio}; systemctl status {servicio} --no-pager'
            titulo = 'Activar governor'
        elif accion == 'desactivar':
            comando = f'sudo systemctl disable --now {servicio}; systemctl status {servicio} --no-pager'
            titulo = 'Desactivar governor'
        elif accion == 'reiniciar':
            comando = prefix + f'sudo systemctl restart {servicio}; systemctl status {servicio} --no-pager'
            titulo = 'Reiniciar governor'
        else:
            raise ValueError('Invalid governor action.')
        self.estado_bc250_cache = None
        self.estado_herramientas_cache = None
        return self._abrir_terminal(comando, titulo)

    def _governor_config_helper_path(self):
        candidates = (
            Path('/usr/libexec/bc250-control-center/bc250-governor-config-helper'),
            Path('/usr/local/libexec/bc250-control-center/bc250-governor-config-helper'),
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

    def _editar_governor_toml(self, action):
        helper = self._governor_config_helper_path()
        if not helper:
            raise RuntimeError(
                'The privileged governor configuration helper is not installed. '
                'Reinstall BC250 Control Center locally or from its package before editing /etc.'
            )
        if action not in {'clear-frequency-range', 'enable-high-points', 'disable-high-points'}:
            raise ValueError('Invalid governor TOML action.')
        rc, out, err = self._ejecutar(['pkexec', helper, action], timeout=120)
        if rc != 0:
            raise RuntimeError(err or out or f'Governor configuration helper exited with code {rc}.')
        self.estado_bc250_cache = None
        return (out or '').strip()

    def aplicar_perfil_gpu(self, minimo, maximo):
        self._validar_curva_oc_alta(maximo)
        self._editar_governor_toml('clear-frequency-range')
        return self.aplicar_rango_bc250(minimo, maximo)

    def _validar_curva_oc_alta(self, maximo):
        """Refuse >2000 MHz unless every preceding point has Level 3 voltage."""

        maximo = int(maximo)
        if maximo <= VOLTAGE_BOOST_START_MHZ:
            return
        try:
            points = GovernorTomlEditor(self._GOVERNOR_CONFIG).safe_point_state()
        except (OSError, RuntimeError, ValueError) as error:
            raise RuntimeError(
                'The governor TOML could not be validated before applying a '
                'range above 2000 MHz. The range was not changed.'
            ) from error
        active = {
            int(point['frequency']): int(point['voltage'])
            for point in points
            if bool(point['active'])
        }
        if maximo not in active:
            raise RuntimeError(
                f'{maximo} MHz is not an active safe-point in the governor TOML. '
                'The range was not changed.'
            )
        required = voltage_profile(3)
        gaps = [
            (frequency, required_voltage, active.get(frequency))
            for frequency, required_voltage in required.items()
            if (
                VOLTAGE_BOOST_START_MHZ <= frequency <= maximo
                and active.get(frequency, 0) < required_voltage
            )
        ]
        if gaps:
            details = ', '.join(
                f'{frequency} MHz={current if current is not None else "--"}/'
                f'{required_voltage} mV'
                for frequency, required_voltage, current in gaps
            )
            raise RuntimeError(
                'A range above 2000 MHz requires the complete Level 3 or '
                f'Level 6 voltage curve. Missing or low points: {details}. '
                'The range was not changed.'
            )

    def _leer_rango_governor(self, kind):
        if kind not in {'Current', 'Allowed'}:
            raise ValueError('Invalid governor range kind.')
        objeto = f'/com/cyanskillfish/Governor/Range/{kind}'
        minimo = self._dbus_uint_property(
            objeto,
            self._GOVERNOR_RANGE_INTERFACE,
            'Min',
        )
        maximo = self._dbus_uint_property(
            objeto,
            self._GOVERNOR_RANGE_INTERFACE,
            'Max',
        )
        if minimo is None or maximo is None or minimo > maximo:
            return None
        return int(minimo), int(maximo)

    def _esperar_rango_governor(self, expected, *, timeout=1.5):
        expected = int(expected[0]), int(expected[1])
        deadline = time.monotonic() + max(0.1, float(timeout))
        current = None
        while time.monotonic() < deadline:
            current = self._leer_rango_governor('Current')
            if current == expected:
                return current
            time.sleep(0.05)
        return current

    @staticmethod
    def _limitar_rango_governor(previous, allowed):
        minimo_anterior, maximo_anterior = (int(previous[0]), int(previous[1]))
        minimo_permitido, maximo_permitido = (int(allowed[0]), int(allowed[1]))
        minimo = max(minimo_permitido, min(minimo_anterior, maximo_permitido))
        maximo = max(minimo_permitido, min(maximo_anterior, maximo_permitido))
        minimo = min(minimo, maximo)
        return minimo, maximo

    def _restaurar_rango_governor(self, previous, *, timeout=6.0):
        deadline = time.monotonic() + max(0.5, float(timeout))
        last_error = 'D-Bus range objects did not become ready.'
        while time.monotonic() < deadline:
            allowed = self._leer_rango_governor('Allowed')
            if allowed is None:
                time.sleep(0.15)
                continue
            minimo, maximo = self._limitar_rango_governor(previous, allowed)
            rc, out, err = self._ejecutar([
                'busctl',
                'call',
                'com.cyanskillfish.Governor',
                '/com/cyanskillfish/Governor',
                'com.cyanskillfish.Governor.PerformanceMode',
                'SetRange',
                'uu',
                str(minimo),
                str(maximo),
            ], timeout=5)
            if rc != 0:
                last_error = err or out or 'busctl SetRange failed.'
                time.sleep(0.15)
                continue
            current = self._leer_rango_governor('Current')
            if current == (minimo, maximo):
                return current
            last_error = (
                f'The governor reported {current!r} after requesting '
                f'{minimo}-{maximo} MHz.'
            )
            time.sleep(0.15)
        raise RuntimeError(
            'The governor restarted, but its previous runtime range could not '
            f'be restored safely. {last_error} Do not start a GPU workload; '
            'apply a known-safe range first.'
        )

    def alternar_puntos_gpu_altos(self, enabled):
        action = 'enable-high-points' if bool(enabled) else 'disable-high-points'
        service = self._GOVERNOR_SERVICE
        active_rc, _out, _err = self._ejecutar(
            ['systemctl', 'is-active', '--quiet', service],
            timeout=5,
        )
        was_active = active_rc == 0
        previous_range = None
        if was_active:
            previous_range = self._leer_rango_governor('Current')
            if previous_range is None:
                raise RuntimeError(
                    'The active governor range could not be read through D-Bus. '
                    'The +2000 MHz points were not changed because restarting '
                    'now could expose the full unsafe range.'
                )
        result = self._editar_governor_toml(action)
        if not was_active:
            self.estado_bc250_cache = None
            suffix = (
                ' The governor is currently inactive, so it was not started automatically; '
                'the validated TOML will be used on the next manual service activation.'
            )
            return (result + suffix).strip()
        rc, out, err = self._ejecutar(
            ['pkexec', 'systemctl', 'restart', service],
            timeout=30,
        )
        if rc != 0:
            raise RuntimeError(
                (err or out or 'The governor service could not be restarted.')
                + ' The TOML edit was validated, but the service must be restarted before the new points are used.'
            )
        restored = self._restaurar_rango_governor(previous_range)
        self.estado_bc250_cache = None
        return (
            f'{result} Runtime range preserved at '
            f'{restored[0]}-{restored[1]} MHz after the governor restart.'
        )


    def status_governor(self):
        servicio = 'cyan-skillfish-governor-smu.service'
        if not self._command_path('cyan-skillfish-governor-smu'):
            raise RuntimeError('cyan-skillfish-governor-smu is not installed. Use Prepare dependencies first.')
        rc, out, err = self._ejecutar(['systemctl', 'status', servicio, '--no-pager'], timeout=8)
        texto = (out or err or '').strip()
        if not texto:
            texto = f'systemctl status {servicio} returned no output.'
        return texto


    def _ejecutar_voltage_lab_pkexec(self, comando, timeout=180):
        if not self._command_path('pkexec'):
            raise RuntimeError('polkit/pkexec was not found. Install polkit to authenticate voltage lab changes.')
        bash = self._command_path('bash') or '/bin/bash'
        rc, out, err = self._ejecutar(['pkexec', bash, '-lc', comando], timeout=timeout)
        if rc != 0:
            detalle = err or out or f'exit code {rc}'
            raise RuntimeError(detalle)
        self.estado_bc250_cache = None
        self.estado_herramientas_cache = None
        return (out or '').strip()


    def abrir_laboratorio_voltaje_gpu(self):
        script = Path(__file__).resolve().parents[1] / 'Resources' / 'scripts' / 'bc250-gpu-voltage-lab.sh'
        if not script.exists():
            raise RuntimeError(f'GPU voltage lab was not found at {script}')
        return self._abrir_terminal(shlex.quote(str(script)) + ' menu', 'BC250 GPU Voltage Lab')


    def aplicar_laboratorio_voltaje_gpu(self, nivel):
        nivel = int(nivel)
        if nivel not in SUPPORTED_VOLTAGE_LEVELS:
            raise ValueError('Invalid lab level. Use 0, 3 or 6.')
        if self._usar_steamos_game_helper():
            salida = self._ejecutar_steamos_game_helper('gpu-voltage', 'apply', nivel, timeout=240)
            self.estado_bc250_cache = None
            self.estado_herramientas_cache = None
            return salida
        script = Path(__file__).resolve().parents[1] / 'Resources' / 'scripts' / 'bc250-gpu-voltage-lab.sh'
        if not script.exists():
            raise RuntimeError(f'GPU voltage lab was not found at {script}')
        comando = f'{shlex.quote(str(script))} apply {nivel}'
        return self._ejecutar_voltage_lab_pkexec(comando)


    def aplicar_laboratorio_voltaje_gpu_personalizado(self, valores):
        if not valores:
            raise ValueError('No custom values to apply.')
        partes = []
        for frecuencia, voltaje in valores.items():
            frecuencia = int(frecuencia)
            voltaje = int(voltaje)
            if frecuencia <= 0:
                raise ValueError(f'Invalid safe-point frequency: {frecuencia}')
            if voltaje < CUSTOM_VOLTAGE_MIN_MV or voltaje > CUSTOM_VOLTAGE_MAX_MV:
                raise ValueError(
                    f'Voltage outside editor range for {frecuencia}: {voltaje} mV. '
                    f'Allowed: {CUSTOM_VOLTAGE_MIN_MV}..{CUSTOM_VOLTAGE_MAX_MV} mV'
                )
            partes.append(f'{frecuencia}={voltaje}')
        if self._usar_steamos_game_helper():
            salida = self._ejecutar_steamos_game_helper('gpu-voltage', 'apply-custom', *partes, timeout=240)
            self.estado_bc250_cache = None
            self.estado_herramientas_cache = None
            return salida
        script = Path(__file__).resolve().parents[1] / 'Resources' / 'scripts' / 'bc250-gpu-voltage-lab.sh'
        if not script.exists():
            raise RuntimeError(f'GPU voltage lab was not found at {script}')
        comando = f'{shlex.quote(str(script))} apply-custom ' + ' '.join(shlex.quote(x) for x in partes)
        return self._ejecutar_voltage_lab_pkexec(comando)


    def estado_bc250(self):
        ahora = time.monotonic()
        if self.estado_bc250_cache is not None and ahora - self.estado_bc250_cache_time < 1.5:
            return dict(self.estado_bc250_cache)
        gpu = self._gpu_device_path()
        sclk_texto = self._leer_texto(gpu / 'pp_dpm_sclk') if gpu else None
        mclk_texto = self._leer_texto(gpu / 'pp_dpm_mclk') if gpu else None
        od = self._parse_od(self._leer_texto(gpu / 'pp_od_clk_voltage') if gpu else None)
        busy = self._gpu_busy_percent(gpu) if gpu else self._gpu_busy_percent(None)
        vram_total = self._leer_entero(gpu / 'mem_info_vram_total') if gpu else None
        vram_usado = self._leer_entero(gpu / 'mem_info_vram_used') if gpu else None
        servicio = 'cyan-skillfish-governor-smu.service'
        current_obj = '/com/cyanskillfish/Governor/Range/Current'
        allowed_obj = '/com/cyanskillfish/Governor/Range/Allowed'
        range_iface = 'com.cyanskillfish.Governor.Range'
        safe_info = self._safe_points_config()
        try:
            high_points = GovernorTomlEditor(safe_info['config_path']).high_frequency_state()
        except Exception:
            high_points = {
                'available': False,
                'frequencies': (),
                'enabled_frequencies': (),
                'enabled': False,
            }
        tools = self.estado_herramientas_bc250()
        if tools.get('governor_cmd'):
            service_active = self._service_prop(servicio, 'ActiveState')
            service_sub = self._service_prop(servicio, 'SubState')
            service_enabled = self._service_prop(servicio, 'UnitFileState')
            service_main_pid = self._service_prop(servicio, 'MainPID')
            current_min = self._dbus_uint_property(current_obj, range_iface, 'Min')
            current_max = self._dbus_uint_property(current_obj, range_iface, 'Max')
            allowed_min = self._dbus_uint_property(allowed_obj, range_iface, 'Min')
            allowed_max = self._dbus_uint_property(allowed_obj, range_iface, 'Max')
            dbus_performance = self._dbus_bool_property('/com/cyanskillfish/Governor', 'com.cyanskillfish.Governor.PerformanceMode', 'Enabled')
        else:
            service_active = 'not-found'
            service_sub = ''
            service_enabled = 'not-found'
            service_main_pid = 0
            current_min = None
            current_max = None
            allowed_min = None
            allowed_max = None
            dbus_performance = None
        resultado = {
            'gpu_path': str(gpu) if gpu else '',
            'device': self._leer_texto(gpu / 'device') if gpu else None,
            'vendor': self._leer_texto(gpu / 'vendor') if gpu else None,
            'driver': 'amdgpu' if gpu else '',
            'service_active': service_active,
            'service_sub': service_sub,
            'service_enabled': service_enabled,
            'service_main_pid': service_main_pid,
            'dbus_ok': current_min is not None,
            'dbus_performance_enabled': dbus_performance,
            'current_min': current_min,
            'current_max': current_max,
            'allowed_min': allowed_min,
            'allowed_max': allowed_max,
            'sclk_actual': od.get('sclk') or self._parse_dpm_actual(sclk_texto),
            'mclk_actual': self._parse_dpm_actual(mclk_texto),
            'voltaje_actual': od.get('vddc'),
            'od_sclk_min': od.get('range_sclk_min'),
            'od_sclk_max': od.get('range_sclk_max'),
            'gpu_busy': busy,
            'vram_total': vram_total,
            'vram_usado': vram_usado,
            'power_level': self._leer_texto(gpu / 'power_dpm_force_performance_level') if gpu else None,
            'power_state': self._leer_texto(gpu / 'power_dpm_state') if gpu else None,
            'pp_dpm_sclk': sclk_texto or '',
            'safe_points': safe_info['points'],
            'safe_points_with_voltage': safe_info['points_with_voltage'],
            'config_max_frequency': safe_info['max_frequency'],
            'config_max_voltage': safe_info['max_voltage'],
            'safe_points_missing_voltage': safe_info['missing_voltage'],
            'safe_points_voltage_errors': safe_info['voltage_order_errors'],
            'safe_points_duplicate_frequencies': safe_info['duplicate_frequencies'],
            'config_path': safe_info['config_path'],
            'high_frequency_points': high_points,
            'tools': tools,
        }
        self.estado_bc250_cache = resultado
        self.estado_bc250_cache_time = ahora
        return dict(resultado)


    def aplicar_rango_bc250(self, minimo, maximo):
        self.estado_bc250_cache = None
        minimo = int(minimo)
        maximo = int(maximo)
        self._validar_curva_oc_alta(maximo)
        rc, out, err = self._ejecutar([
            'busctl', 'call', 'com.cyanskillfish.Governor', '/com/cyanskillfish/Governor',
            'com.cyanskillfish.Governor.PerformanceMode', 'SetRange', 'uu', str(minimo), str(maximo)
        ], timeout=5)
        if rc != 0:
            raise RuntimeError(err or out or 'busctl SetRange failed')
        current = self._esperar_rango_governor((minimo, maximo))
        if current != (minimo, maximo):
            raise RuntimeError(
                'The governor accepted SetRange but did not report the requested '
                f'{minimo}-{maximo} MHz range (reported {current!r}).'
            )
        return self.estado_bc250()


    def fijar_frecuencia_bc250(self, frecuencia):
        self.estado_bc250_cache = None
        frecuencia = int(frecuencia)
        self._validar_curva_oc_alta(frecuencia)
        rc, out, err = self._ejecutar([
            'busctl', 'call', 'com.cyanskillfish.Governor', '/com/cyanskillfish/Governor',
            'com.cyanskillfish.Governor.PerformanceMode', 'SetFixedFrequency', 'u', str(frecuencia)
        ], timeout=5)
        if rc != 0:
            raise RuntimeError(err or out or 'busctl SetFixedFrequency failed')
        current = self._esperar_rango_governor((frecuencia, frecuencia))
        if current != (frecuencia, frecuencia):
            raise RuntimeError(
                'The governor accepted SetFixedFrequency but did not report the '
                f'requested {frecuencia} MHz fixed range (reported {current!r}).'
            )
        return self.estado_bc250()
