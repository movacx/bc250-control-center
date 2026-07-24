from pathlib import Path
import shlex
import time

class GPURepository:
    def controlar_governor(self, accion):
        servicio = 'cyan-skillfish-governor-smu.service'
        if not self._command_path('cyan-skillfish-governor-smu'):
            raise RuntimeError('cyan-skillfish-governor-smu is not installed. Use Prepare dependencies first.')
        if accion == 'activar':
            comando = f'sudo systemctl enable --now {servicio}; systemctl status {servicio} --no-pager'
            titulo = 'Activar governor'
        elif accion == 'desactivar':
            comando = f'sudo systemctl disable --now {servicio}; systemctl status {servicio} --no-pager'
            titulo = 'Desactivar governor'
        elif accion == 'reiniciar':
            comando = f'sudo systemctl restart {servicio}; systemctl status {servicio} --no-pager'
            titulo = 'Reiniciar governor'
        else:
            raise ValueError('Invalid governor action.')
        self.estado_bc250_cache = None
        self.estado_herramientas_cache = None
        return self._abrir_terminal(comando, titulo)


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
        if nivel < 0 or nivel > 6:
            raise ValueError('Invalid lab level. Use 0..6.')
        script = Path(__file__).resolve().parents[1] / 'Resources' / 'scripts' / 'bc250-gpu-voltage-lab.sh'
        if not script.exists():
            raise RuntimeError(f'GPU voltage lab was not found at {script}')
        comando = f'{shlex.quote(str(script))} apply {nivel}'
        return self._ejecutar_voltage_lab_pkexec(comando)


    def aplicar_laboratorio_voltaje_gpu_personalizado(self, valores):
        if not valores:
            raise ValueError('No custom values to apply.')
        script = Path(__file__).resolve().parents[1] / 'Resources' / 'scripts' / 'bc250-gpu-voltage-lab.sh'
        if not script.exists():
            raise RuntimeError(f'GPU voltage lab was not found at {script}')
        partes = []
        permitidas = {1850, 2000, 2050, 2100, 2125, 2150, 2200, 2300, 2350, 2400}
        for frecuencia, voltaje in valores.items():
            frecuencia = int(frecuencia)
            voltaje = int(voltaje)
            if frecuencia not in permitidas:
                raise ValueError(f'Frequency not allowed for lab: {frecuencia}')
            if voltaje < 600 or voltaje > 1150:
                raise ValueError(f'Voltage outside safe limit for {frecuencia}: {voltaje} mV. Maximum allowed: 1150 mV')
            partes.append(f'{frecuencia}={voltaje}')
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
            'tools': tools,
        }
        self.estado_bc250_cache = resultado
        self.estado_bc250_cache_time = ahora
        return dict(resultado)


    def aplicar_rango_bc250(self, minimo, maximo):
        self.estado_bc250_cache = None
        minimo = int(minimo)
        maximo = int(maximo)
        rc, out, err = self._ejecutar([
            'busctl', 'call', 'com.cyanskillfish.Governor', '/com/cyanskillfish/Governor',
            'com.cyanskillfish.Governor.PerformanceMode', 'SetRange', 'uu', str(minimo), str(maximo)
        ], timeout=5)
        if rc != 0:
            raise RuntimeError(err or out or 'busctl SetRange failed')
        return self.estado_bc250()


    def fijar_frecuencia_bc250(self, frecuencia):
        self.estado_bc250_cache = None
        frecuencia = int(frecuencia)
        rc, out, err = self._ejecutar([
            'busctl', 'call', 'com.cyanskillfish.Governor', '/com/cyanskillfish/Governor',
            'com.cyanskillfish.Governor.PerformanceMode', 'SetFixedFrequency', 'u', str(frecuencia)
        ], timeout=5)
        if rc != 0:
            raise RuntimeError(err or out or 'busctl SetFixedFrequency failed')
        return self.estado_bc250()
