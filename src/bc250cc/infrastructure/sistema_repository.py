import fnmatch
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import asdict
from pathlib import Path

import psutil

from bc250cc.application.recovery.service import RecoveryRepository
from bc250cc.domain.telemetry import clock_mhz, voltage_mv
from bc250cc.infrastructure.cpu_repository import CPURepository
from bc250cc.infrastructure.cu_repository import CURepository
from bc250cc.infrastructure.dependencias_repository import DependenciasRepository
from bc250cc.infrastructure.drivers_repository import DriversRepository
from bc250cc.infrastructure.fan_repository import FanRepository
from bc250cc.infrastructure.firmware.board import read_installed_bios
from bc250cc.infrastructure.gddr6_memory_temp_repository import (
    Gddr6MemoryTempRepository,
)
from bc250cc.infrastructure.gpu_fdinfo import (
    DrmFdinfoSampler,
    busiest_client,
    busy_percent,
)
from bc250cc.infrastructure.gpu_repository import GPURepository
from bc250cc.infrastructure.health_repository import HealthRepository
from bc250cc.infrastructure.memory_runtime import read_memory_runtime_state
from bc250cc.infrastructure.persistence.activity_journal import activity_journal_path
from bc250cc.infrastructure.persistence.configuracion_local import ConfiguracionLocal
from bc250cc.infrastructure.persistence.profile_bundle import ProfileBundleRepository
from bc250cc.infrastructure.polkit_session import normalize_polkit_error
from bc250cc.infrastructure.privilege_repository import PrivilegeRepository
from bc250cc.infrastructure.realtime_metrics_policy import (
    bounded_percent,
    disk_rates,
    network_rates,
)
from bc250cc.infrastructure.terminal_repository import TerminalRepository
from bc250cc.infrastructure.vrm_telemetry_reader import (
    leer_telemetria_vrm,
    sondear_telemetria_vrm,
)
from bc250cc.platform.init.services import (
    detect_init_manager,
    parse_openrc_runlevel,
    parse_openrc_status,
    service_key,
)

logger = logging.getLogger(__name__)

# One GPU load sample at a time per process, whichever thread asks.
_GPU_BUSY_CACHE_LOCK = threading.Lock()
_GPU_BUSY_LOCK = threading.Lock()


class SistemaRepository(PrivilegeRepository, TerminalRepository, DependenciasRepository, DriversRepository, GPURepository, CPURepository, CURepository, FanRepository, HealthRepository, RecoveryRepository, Gddr6MemoryTempRepository):
    def __init__(self):
        self.configuracion = ConfiguracionLocal()
        self.hwmons = []
        self._buscar_sensores()
        self.disco_anterior = psutil.disk_io_counters()
        self.tiempo_anterior = time.time()
        self.lectura_disco = 0
        self.escritura_disco = 0
        self.gpu_fdinfo_anterior = None
        self.tiempo_gpu_fdinfo = None
        # The compute (ACE) queues on their own: whether async compute is
        # really used, and by which process.
        self.gpu_compute_anterior = None
        self.gpu_compute_busy = None
        self.gpu_compute_process = ''
        self.gpu_busy_cache = None
        self.gpu_busy_cache_time = 0
        self.estado_herramientas_cache = None
        self.estado_herramientas_cache_time = 0
        self.estado_bc250_cache = None
        self.estado_bc250_cache_time = 0
        self._metricas_rt_lock = threading.Lock()
        self._metricas_rt_time = None
        self._metricas_rt_disk = None
        self._metricas_rt_network = {}
        self._aux_temperature_cache = {}
        self._aux_temperature_cache_time = 0.0

    def _leer_texto(self, ruta):
        try:
            return Path(ruta).read_text().strip()
        except Exception:
            return None

    def _leer_entero(self, ruta):
        valor = self._leer_texto(ruta)
        if valor is None:
            return None
        try:
            return int(valor)
        except Exception:
            return None

    def _buscar_sensores(self):
        if not hasattr(self, 'hwmons'):
            self.hwmons = []
        self.hwmons.clear()
        hwmon_root = Path(getattr(self, '_hwmon_root', '/sys/class/hwmon'))
        for carpeta in sorted(hwmon_root.glob('hwmon*')):
            nombre = self._leer_texto(carpeta / 'name') or carpeta.name
            self.hwmons.append((nombre, carpeta))

    @staticmethod
    def _temperatura_valida(valor):
        """Reject disconnected hwmon inputs without hiding realistic BC-250 heat."""
        return valor is not None and 0 < valor <= 130

    def _temperatura_etiqueta_exacta(self, chip, etiqueta):
        for nombre, carpeta in self.hwmons:
            if chip.lower() not in nombre.lower():
                continue
            for label in carpeta.glob('temp*_label'):
                texto = (self._leer_texto(label) or '').strip()
                if texto.casefold() != etiqueta.casefold():
                    continue
                entrada = carpeta / label.name.replace('_label', '_input')
                valor = self._leer_entero(entrada)
                return None if valor is None else valor / 1000
        return None

    def temperatura_cpu(self):
        """Read the best available CPU temperature, including BC-250 NCT fallback.

        The optional nct6687 module is commonly loaded after the application has
        already started.  Refreshing the tiny hwmon directory here prevents the
        initial sensor inventory from becoming stale for the rest of the session.
        """
        self._buscar_sensores()
        candidates = (
            self._temperatura_etiqueta_exacta('k10temp', 'Tctl'),
            self._temperatura_etiqueta_exacta('k10temp', 'Tdie'),
            self._temperatura_etiqueta_exacta('zenpower', 'Tctl'),
            self._temperatura_etiqueta_exacta('zenpower', 'Tdie'),
            # On the BC-250, nct6686/nct6687 exposes the useful package reading
            # as exactly "CPU".  Exact matching deliberately excludes the
            # disconnected "CPU Socket" channel often reported as 0 °C.
            self._temperatura_etiqueta_exacta('nct', 'CPU'),
        )
        return next((value for value in candidates if self._temperatura_valida(value)), None)

    def temperatura_chip(self, chip, etiqueta=None, indice=1):
        for nombre, carpeta in self.hwmons:
            if chip.lower() not in nombre.lower():
                continue

            if etiqueta:
                for label in carpeta.glob('temp*_label'):
                    texto = self._leer_texto(label) or ''
                    if etiqueta.lower() in texto.lower():
                        entrada = carpeta / label.name.replace('_label', '_input')
                        valor = self._leer_entero(entrada)
                        return None if valor is None else valor / 1000

            valor = self._leer_entero(carpeta / f'temp{indice}_input')
            return None if valor is None else valor / 1000
        return None

    @staticmethod
    def _normalizar_potencia_microwatts(valor):
        if valor is None:
            return None
        try:
            watts = float(valor) / 1_000_000.0
        except (TypeError, ValueError):
            return None
        return watts if watts >= 0 else None

    def _canales_potencia(self):
        """Enumerate passive hwmon power channels without guessing their scope.

        Linux hwmon normally exposes instantaneous/average power as
        ``powerN_average``; a few drivers use ``powerN_input``.  Both are read,
        but one logical channel is returned only once and ``average`` wins when
        both files exist.
        """
        channels = []
        for nombre, carpeta in self.hwmons:
            files = {}
            for archivo in carpeta.glob('power*_average'):
                files[archivo.name.removesuffix('_average')] = archivo
            for archivo in carpeta.glob('power*_input'):
                files.setdefault(archivo.name.removesuffix('_input'), archivo)
            for prefix, archivo in sorted(files.items()):
                valor = self._normalizar_potencia_microwatts(self._leer_entero(archivo))
                if valor is None:
                    continue
                etiqueta = self._leer_texto(carpeta / f'{prefix}_label') or ''
                channels.append({
                    'value_w': valor,
                    'hwmon_name': nombre,
                    'sensor_label': etiqueta,
                    'source': str(archivo),
                })
        return channels

    @staticmethod
    def _es_potencia_total(canal):
        """Accept only sensors that explicitly identify whole-system power.

        AMDGPU hwmon is deliberately excluded even when a firmware label uses
        wording such as "board power".  That interface belongs to the GPU
        driver and cannot prove that RAM, storage, fans, VRM losses and input
        conversion are included in the measurement.
        """
        nombre = str(canal.get('hwmon_name') or '').lower()
        etiqueta = str(canal.get('sensor_label') or '').lower()
        if 'amdgpu' in nombre:
            return False
        texto = f'{nombre} {etiqueta}'
        nombres_totales = ('acpi_power_meter', 'power_meter', 'powermeter', 'psu')
        etiquetas_totales = (
            'total power', 'board power', 'system power', 'platform power',
            'input power', 'whole system', 'potencia total', 'consumo total',
        )
        return any(token in nombre for token in nombres_totales) or any(token in texto for token in etiquetas_totales)

    def lectura_potencia(self):
        """Return an honest power reading and its measurement scope.

        A dedicated total-board/system sensor is preferred.  When the platform
        exposes only AMDGPU hwmon power, the value is returned as GPU/SoC power
        and is never presented as whole-board consumption.
        """
        channels = self._canales_potencia()
        total = next((item for item in channels if self._es_potencia_total(item)), None)
        gpu = next(
            (item for item in channels if 'amdgpu' in str(item.get('hwmon_name') or '').lower()),
            None,
        )
        selected = total or gpu
        if selected is None:
            return {
                'value_w': None,
                'gpu_w': None,
                'is_total': False,
                'scope': 'unavailable',
                'label': 'Power sensor unavailable',
                'source': '',
                'sensor_name': '',
                'sensor_label': '',
            }
        is_total = selected is total
        return {
            'value_w': selected.get('value_w'),
            'gpu_w': gpu.get('value_w') if gpu is not None else None,
            'is_total': is_total,
            'scope': 'board_total' if is_total else 'gpu_soc',
            'label': 'Total board power' if is_total else 'SoC package power',
            'source': str(selected.get('source') or ''),
            'sensor_name': str(selected.get('hwmon_name') or ''),
            'sensor_label': str(selected.get('sensor_label') or ''),
        }

    def potencia_gpu(self):
        """Compatibility accessor for the AMDGPU/SoC channel only."""
        return self.lectura_potencia().get('gpu_w')

    def voltaje_chip(self, chip, etiqueta):
        for nombre, carpeta in self.hwmons:
            if chip.lower() not in nombre.lower():
                continue
            for label in carpeta.glob('in*_label'):
                texto = self._leer_texto(label) or ''
                if etiqueta.lower() in texto.lower():
                    entrada = carpeta / label.name.replace('_label', '_input')
                    valor = self._leer_entero(entrada)
                    return voltage_mv(valor)
        return None

    def ventilador_principal(self):
        mejor = None
        for _nombre, carpeta in self.hwmons:
            for archivo in carpeta.glob('fan*_input'):
                valor = self._leer_entero(archivo)
                if valor and valor > 0:
                    mejor = max(mejor or 0, valor)
        return mejor

    def temperaturas_board(self):
        lista = []
        for nombre, carpeta in self.hwmons:
            if 'nct' not in nombre.lower():
                continue
            for label in carpeta.glob('temp*_label'):
                etiqueta = self._leer_texto(label) or label.name
                valor = self._leer_entero(carpeta / label.name.replace('_label', '_input'))
                if valor:
                    lista.append((etiqueta, valor / 1000))
        return lista

    def temperaturas_auxiliares(self, *, max_age=10.0):
        """Return independent NVMe, board and VRM temperatures from hwmon.

        NVMe Composite remains the primary drive temperature.  The hottest
        additional NVMe sensor is exposed separately for the compact hotspot
        readout. Explicitly labelled NCT board/VRM channels are accepted; raw
        Nuvoton channel numbers and disconnected 0 °C inputs are not guessed.
        """
        now = time.monotonic()
        cached = dict(getattr(self, '_aux_temperature_cache', {}) or {})
        cached_at = float(getattr(self, '_aux_temperature_cache_time', 0.0) or 0.0)
        if cached_at > 0 and now - cached_at < max(0.0, float(max_age)):
            return cached

        self._buscar_sensores()
        nvme = []
        nvme_hotspot = []
        board = []
        vrm = []
        for name, directory in self.hwmons:
            lowered_name = str(name).casefold()
            if lowered_name == 'nvme' or lowered_name.startswith('nvme'):
                raw = self._leer_entero(directory / 'temp1_input')
                value = None if raw is None else raw / 1000.0
                if self._temperatura_valida(value):
                    nvme.append(value)
                for sensor_path in sorted(directory.glob('temp*_input')):
                    if sensor_path.name == 'temp1_input':
                        continue
                    raw_sensor = self._leer_entero(sensor_path)
                    sensor_value = (
                        None if raw_sensor is None else raw_sensor / 1000.0
                    )
                    if self._temperatura_valida(sensor_value):
                        nvme_hotspot.append(sensor_value)
                continue
            if 'nct' not in lowered_name:
                continue
            for label_path in sorted(directory.glob('temp*_label')):
                label = (self._leer_texto(label_path) or '').strip()
                raw = self._leer_entero(
                    directory / label_path.name.replace('_label', '_input')
                )
                value = None if raw is None else raw / 1000.0
                if not self._temperatura_valida(value):
                    continue
                normalized = label.casefold()
                if normalized in {'system', 'board', 'motherboard'}:
                    board.append(value)
                elif 'vrm' in normalized:
                    vrm.append(value)

        # Two physical VRMs, kept apart. Collapsing them into one maximum
        # hid which rail was heating up, and when the PMBus daemon is absent
        # the fallback is not a VRM reading at all: it is whatever channel the
        # Nuvoton labels "VRM MOS", which on a BC-250 tracks the board sensor.
        # The source travels with the value so nothing downstream has to guess
        # what it is looking at.
        vrm_externo = leer_telemetria_vrm()
        vrm_cpu = vrm_externo.get('vrm_cpu_temperature_c')
        vrm_gpu = vrm_externo.get('vrm_gpu_temperature_c')
        vrm_externo_valores = [
            valor for valor in (vrm_cpu, vrm_gpu) if valor is not None
        ]
        if vrm_externo_valores:
            vrm_temperature = max(vrm_externo_valores)
            vrm_source = 'pmbus'
        elif vrm:
            vrm_temperature = max(vrm)
            vrm_source = 'nct'
        else:
            vrm_temperature = None
            vrm_source = ''

        result = {
            'nvme_temperature_c': max(nvme) if nvme else None,
            'nvme_hotspot_temperature_c': (
                max(nvme_hotspot) if nvme_hotspot else None
            ),
            'board_temperature_c': max(board) if board else None,
            'vrm_temperature_c': vrm_temperature,
            # The Nuvoton "VRM MOS" channel on its own: present on every
            # board, shown beside the PMBus rails instead of replaced by them.
            'vrm_mos_temperature_c': max(vrm) if vrm else None,
            'vrm_cpu_temperature_c': vrm_cpu,
            'vrm_gpu_temperature_c': vrm_gpu,
            'vrm_source': vrm_source,
            'vrm_input_voltage_v': vrm_externo.get('vrm_input_voltage_v'),
            'vrm_total_power_w': vrm_externo.get('vrm_total_power_w'),
            'vrm_cpu_voltage_v': vrm_externo.get('vrm_cpu_voltage_v'),
            'vrm_gpu_voltage_v': vrm_externo.get('vrm_gpu_voltage_v'),
            'vrm_cpu_current_a': vrm_externo.get('vrm_cpu_current_a'),
            'vrm_gpu_current_a': vrm_externo.get('vrm_gpu_current_a'),
            'vrm_cpu_power_w': vrm_externo.get('vrm_cpu_power_w'),
            'vrm_gpu_power_w': vrm_externo.get('vrm_gpu_power_w'),
            'vrm_alerts': tuple(vrm_externo.get('vrm_alerts') or ()),
            # Unchecked, for the manual Power delivery mode (Settings ›
            # Telemetry): what the daemon reports even when it says invalid.
            'vrm_probe': sondear_telemetria_vrm(),
        }
        self._aux_temperature_cache = dict(result)
        self._aux_temperature_cache_time = now
        return result

    def velocidad_disco(self):
        ahora = time.time()
        actual = psutil.disk_io_counters()
        if actual and self.disco_anterior:
            diferencia = max(0.1, ahora - self.tiempo_anterior)
            self.lectura_disco = max(0, (actual.read_bytes - self.disco_anterior.read_bytes) / diferencia)
            self.escritura_disco = max(0, (actual.write_bytes - self.disco_anterior.write_bytes) / diferencia)
        self.disco_anterior = actual
        self.tiempo_anterior = ahora
        return self.lectura_disco, self.escritura_disco


    def _ejecutar(self, comando, timeout=2):
        try:
            r = subprocess.run(comando, text=True, capture_output=True, timeout=timeout, check=False)
            stdout = (r.stdout or '').strip()
            stderr = normalize_polkit_error(comando, (r.stderr or '').strip())
            return r.returncode, stdout, stderr
        except Exception as error:
            return 1, '', str(error)

    def _leer_gpu_archivo(self, nombre):
        for ruta in sorted(Path('/sys/class/drm').glob('card*/device')):
            archivo = ruta / nombre
            if archivo.exists():
                return self._leer_texto(archivo)
        return None

    def _gpu_device_path(self):
        for ruta in sorted(Path('/sys/class/drm').glob('card*/device')):
            vendor = self._leer_texto(ruta / 'vendor') or ''
            if vendor.lower() == '0x1002' or (ruta / 'pp_dpm_sclk').exists():
                return ruta
        return None


    def firmware_instalado(self):
        """The BIOS image the board runs, identified once per process.

        DMI, the EFI variable names and the VRAM carve-out only change across
        a reboot, and this is asked on every performance sample.
        """
        cached = getattr(self, '_installed_bios_cache', None)
        if cached is not None:
            return cached
        gpu = self._gpu_device_path()
        try:
            cores = int(psutil.cpu_count(logical=False) or 0)
        except (TypeError, ValueError, OSError):
            cores = 0
        installed = read_installed_bios(
            vram_total_bytes=int((self._leer_entero(gpu / 'mem_info_vram_total') if gpu else 0) or 0),
            physical_cores=cores,
        )
        self._installed_bios_cache = {
            'bios_version': installed.version,
            'bios_variant': installed.variant,
            'bios_family': installed.family,
            'bios_evidence': installed.evidence,
        }
        return self._installed_bios_cache

    def _gpu_fdinfo_sampler(self):
        sampler = getattr(self, "_drm_fdinfo_sampler", None)
        if sampler is None:
            sampler = self._drm_fdinfo_sampler = DrmFdinfoSampler()
        return sampler

    def _gpu_fdinfo_total_ns(self):
        return sum(self._gpu_fdinfo_sampler().sample().values())

    def _gpu_busy_fdinfo(self):
        with _GPU_BUSY_LOCK:
            sampler = self._gpu_fdinfo_sampler()
            current = sampler.sample()
            compute = sampler.compute_sample()
            ahora = time.monotonic_ns()
            previous = self.gpu_fdinfo_anterior
            previous_compute = self.gpu_compute_anterior
            since = self.tiempo_gpu_fdinfo
            self.gpu_fdinfo_anterior = current
            self.gpu_compute_anterior = compute
            self.tiempo_gpu_fdinfo = ahora
            if not isinstance(previous, dict) or since is None:
                return None
            if isinstance(previous_compute, dict):
                self.gpu_compute_busy = busy_percent(previous_compute, compute, ahora - since)
                client = busiest_client(previous_compute, compute)
                self.gpu_compute_process = sampler.process_name(client) if client else ''
            return busy_percent(previous, current, ahora - since)

    def _gpu_busy_percent(self, gpu=None):
        sysfs_invalid = False
        if gpu:
            busy = self._leer_entero(gpu / 'gpu_busy_percent')
            if busy is not None:
                if 0 <= busy <= 100:
                    self.gpu_busy_cache = busy
                    self.gpu_busy_cache_time = time.monotonic()
                    return self.gpu_busy_cache
                # Broken BC-250 metrics can expose impossible percentages
                # (for example ~655%).  Clamping those to 100% fabricates a
                # full-load signal and can make frequency verification report
                # a false governor failure.  Treat the source as invalid and
                # fall back to fdinfo instead.
                logger.warning(
                    "Ignoring out-of-range amdgpu gpu_busy_percent: %s", busy
                )
                sysfs_invalid = True
        if not sysfs_invalid and time.monotonic() - self.gpu_busy_cache_time < 2:
            return self.gpu_busy_cache
        # The dashboard, the performance graphs and the alerts ask at nearly
        # the same moment from different threads. One samples; the others get
        # its answer instead of taking a second reading a few ms later. The
        # time is taken after the sample: taken before, a slow sample left
        # the cache already expired and every caller sampled again.
        with _GPU_BUSY_CACHE_LOCK:
            if not sysfs_invalid and time.monotonic() - self.gpu_busy_cache_time < 2:
                return self.gpu_busy_cache
            self.gpu_busy_cache = self._gpu_busy_fdinfo()
            self.gpu_busy_cache_time = time.monotonic()
            return self.gpu_busy_cache

    def _parse_dpm_actual(self, texto):
        if not texto:
            return None
        matches = re.findall(r'(?im)^\s*\d+:\s*(\d+)\s*MHz\s*\*\s*$', texto)
        return clock_mhz(matches[0]) if len(matches) == 1 else None

    def _parse_od(self, texto):
        datos = {'sclk': None, 'vddc': None, 'range_sclk_min': None, 'range_sclk_max': None}
        if not texto:
            return datos
        for linea in texto.splitlines():
            if 'Mhz' in linea and '*' in linea:
                m = re.search(r'(\d+)\s*Mhz', linea, re.IGNORECASE)
                if m:
                    datos['sclk'] = int(m.group(1))
            if 'mV' in linea and '*' in linea:
                m = re.search(r'(\d+)\s*mV', linea, re.IGNORECASE)
                if m:
                    datos['vddc'] = int(m.group(1))
            if linea.strip().startswith('SCLK:'):
                nums = [int(x) for x in re.findall(r'(\d+)\s*Mhz', linea, re.IGNORECASE)]
                if len(nums) >= 2:
                    datos['range_sclk_min'], datos['range_sclk_max'] = nums[0], nums[1]
        return datos

    def _dbus_property_text(self, objeto, interfaz, propiedad):
        rc, out, err = self._ejecutar([
            'busctl', 'get-property', 'com.cyanskillfish.Governor', objeto, interfaz, propiedad
        ])
        if rc != 0:
            # busctl's own timeout is 25 s, so a timeout here is always ours:
            # Cyan is on the bus but its D-Bus thread is not getting a turn.
            if 'timed out' in (err or '').lower():
                self._cyan_dbus_last_timeout = time.monotonic()
            return None
        return out

    def _dbus_uint_property(self, objeto, interfaz, propiedad):
        out = self._dbus_property_text(objeto, interfaz, propiedad)
        if out is None:
            return None
        match = re.fullmatch(r'\s*(?:u|t|q)\s+(\d+)\s*', out or '')
        if not match:
            logger.warning("Unexpected busctl integer property format for %s: %r", propiedad, out)
            return None
        value = int(match.group(1))
        if not 0 <= value <= 10_000:
            logger.warning("Out-of-range busctl integer property for %s: %s", propiedad, value)
            return None
        return value

    def _dbus_bool_property(self, objeto, interfaz, propiedad):
        out = self._dbus_property_text(objeto, interfaz, propiedad)
        if out is None:
            return None
        match = re.fullmatch(r'\s*b\s+(true|false)\s*', out or '', re.IGNORECASE)
        if not match:
            logger.warning("Unexpected busctl boolean property format for %s: %r", propiedad, out)
            return None
        return match.group(1).lower() == 'true'

    def _service_prop(self, servicio, prop):
        init_manager = detect_init_manager()
        if init_manager.kind == 'openrc':
            try:
                key = service_key(servicio)
            except ValueError:
                return ''
            if prop in {'ActiveState', 'SubState'}:
                rc, out, err = self._ejecutar(['rc-service', key, 'status'], timeout=5)
                return parse_openrc_status(rc, out or err)
            if prop == 'UnitFileState':
                _rc, out, _err = self._ejecutar(['rc-update', 'show', 'default'], timeout=5)
                return 'enabled' if parse_openrc_runlevel(out, key) else 'disabled'
            # OpenRC's shell service scripts do not expose a portable main PID
            # field.  Returning an empty value is more honest than borrowing
            # a PID from an implementation-specific status format.
            return ''
        if init_manager.kind != 'systemd':
            return ''
        rc, out, _err = self._ejecutar(['systemctl', 'show', servicio, f'--property={prop}', '--value'])
        return out if rc == 0 else ''

    def _command_path(self, nombre):
        return shutil.which(nombre) or ''

    def _git_path(self):
        if Path('/usr/bin/git').exists():
            return '/usr/bin/git'
        return self._command_path('git')

    def _os_release(self):
        datos = {}
        for ruta in [Path('/etc/os-release'), Path('/usr/lib/os-release')]:
            if not ruta.exists():
                continue
            try:
                for linea in ruta.read_text(encoding='utf-8').splitlines():
                    if '=' not in linea or linea.startswith('#'):
                        continue
                    clave, valor = linea.split('=', 1)
                    datos[clave] = valor.strip().strip('"')
                break
            except Exception:
                continue
        return datos

    def _es_ostree(self):
        datos = self._os_release()
        texto = ' '.join([datos.get('ID', ''), datos.get('ID_LIKE', ''), datos.get('VARIANT_ID', ''), datos.get('NAME', '')]).lower()
        return bool(self._command_path('rpm-ostree') and any(x in texto for x in ['bazzite', 'silverblue', 'kinoite', 'ublue', 'atomic']))

    def _data_dir(self):
        return self.configuracion.data_dir()

    def config_paths(self):
        return {
            'config': str(self.configuracion.config_path()),
            'perfiles': str(self.configuracion.perfiles_path()),
            'historial': str(activity_journal_path(self.configuracion)),
            'estabilidad': str(self.configuracion.estabilidad_path()),
            'metricas_runtime': str(self.configuracion.metricas_runtime_path()),
            'tools': str(self._tool_dir()),
            'data': str(self.configuracion.carpeta_data()),
            'resource_tools': str(self.configuracion.carpeta_resource_tools()),
            'recovery': str(self._recovery_snapshot_root()),
        }

    def leer_config_local(self):
        return self.configuracion.leer_config()

    def guardar_config_local(self, datos):
        return self.configuracion.guardar_config(datos)

    def leer_perfiles_locales(self):
        return self.configuracion.leer_perfiles()

    def registrar_metrica_runtime(self, datos):
        return self.configuracion.registrar_metrica_runtime(datos)

    def exportar_bundle_perfil(self, destino):
        return str(ProfileBundleRepository(self.configuracion).export(destino))

    def previsualizar_bundle_perfil(self, origen):
        return asdict(ProfileBundleRepository(self.configuracion).preview(origen))

    def importar_bundle_perfil(self, origen):
        return str(ProfileBundleRepository(self.configuracion).import_bundle(origen))

    def exportar_metricas_runtime(self, destino, formato='csv'):
        # The optional daemon is the normal producer.  A first-time desktop
        # user may legitimately have no JSONL history yet; exporting an empty
        # header looked successful but produced no useful report.  Capture one
        # passive sample in that case so CSV export remains useful without
        # requiring the daemon to be enabled.
        if not self.configuracion.leer_metricas_runtime(limite=1):
            sample = self.obtener_rendimiento()
            if not isinstance(sample, dict) or not sample:
                raise RuntimeError(
                    'No recorded metrics are available and a current sample could not be captured.'
                )
            sample = dict(sample)
            sample['sample_source'] = 'desktop_export'
            if not self.configuracion.registrar_metrica_runtime(sample):
                raise RuntimeError('The current metrics sample could not be recorded.')
        return str(
            self.configuracion.exportar_metricas_runtime(destino, formato=formato)
        )

    def _tool_dir(self):
        nuevo = self.configuracion.carpeta_resource_tools()
        viejo = self._data_dir() / 'tools'
        if viejo.exists():
            try:
                if not any(nuevo.iterdir()):
                    for item in viejo.iterdir():
                        destino = nuevo / item.name
                        if item.is_dir() and not destino.exists():
                            shutil.copytree(item, destino)
                        elif item.is_file() and not destino.exists():
                            shutil.copy2(item, destino)
            except OSError:
                logger.warning("Could not migrate legacy data from %s to %s", viejo, nuevo, exc_info=True)
        return nuevo

    def _candidatos_busqueda(self):
        candidatos = [
            self._tool_dir(),
            self._data_dir() / 'tools',
            Path.cwd(),
            Path.cwd().parent,
            Path.home() / 'BC250',
            Path.home() / 'Documents',
            Path.home() / 'Downloads',
            Path('/opt'),
            Path('/usr/local/src'),
        ]
        extra = os.environ.get('BC250_TOOLS_DIR')
        if extra:
            candidatos.insert(0, Path(extra))
        vistos = set()
        salida = []
        for ruta in candidatos:
            try:
                r = ruta.expanduser().resolve()
            except Exception:
                r = ruta.expanduser()
            if str(r) not in vistos and r.exists():
                vistos.add(str(r))
                salida.append(r)
        return salida

    #: Directories a toolkit checkout never lives in. The installed app runs
    #: from ~/.local/share/bc250-control-center, so the parent it searches is
    #: ~/.local/share -- Steam's libraries and Proton prefixes included.
    _BUSQUEDA_OMITIR = frozenset({
        'Steam', 'steamapps', 'compatdata', 'shadercache', 'Trash', 'flatpak',
        'node_modules', '__pycache__', 'site-packages',
    })
    _BUSQUEDA_TTL = 300.0

    def _buscar_archivo(self, patron, max_depth=5):
        # The answer changes when a toolkit is cloned or removed, not between
        # two refreshes; the walk behind it held the GIL for seconds.
        cache = self.__dict__.setdefault('_busqueda_cache', {})
        ahora = time.monotonic()
        previo = cache.get((patron, max_depth))
        if previo is not None and ahora - previo[0] < self._BUSQUEDA_TTL:
            if not previo[1] or Path(previo[1]).exists():
                return previo[1]
        encontrado = self._buscar_archivo_en_disco(patron, max_depth)
        cache[(patron, max_depth)] = (ahora, encontrado)
        return encontrado

    def _buscar_archivo_en_disco(self, patron, max_depth):
        for base in self._candidatos_busqueda():
            try:
                directos = sorted(base.glob(patron))
                if directos:
                    return str(directos[0])
                # rglob walked the whole tree and only filtered the results by
                # depth; this stops descending at the depth a match may have.
                for raiz, carpetas, archivos in os.walk(base):
                    profundidad = len(Path(raiz).relative_to(base).parts)
                    for nombre in sorted(archivos):
                        if fnmatch.fnmatch(nombre, patron):
                            return str(Path(raiz) / nombre)
                    if profundidad + 1 >= max_depth:
                        carpetas[:] = []
                        continue
                    carpetas[:] = sorted(
                        nombre for nombre in carpetas
                        if not nombre.startswith('.') and nombre not in self._BUSQUEDA_OMITIR
                    )
            except Exception:
                continue
        return ''

    def _buscar_directorio_con(self, archivo, nombre_preferido=''):
        if nombre_preferido:
            for base in self._candidatos_busqueda():
                ruta = base / nombre_preferido
                if (ruta / archivo).exists():
                    return str(ruta)
        encontrado = self._buscar_archivo(archivo)
        return str(Path(encontrado).parent) if encontrado else ''

    def obtener_rendimiento(self):
        memoria = psutil.virtual_memory()
        swap = psutil.swap_memory()
        raiz = psutil.disk_usage('/')
        lectura, escritura = self.velocidad_disco()

        cpu_freq = psutil.cpu_freq()
        gpu = self._gpu_device_path()
        gpu_busy = self._gpu_busy_percent(gpu) if gpu else self._gpu_busy_percent(None)
        potencia = self.lectura_potencia()
        gpu_technical = self._gpu_technical_metrics(gpu)
        auxiliary_temperatures = self.temperaturas_auxiliares(max_age=0.0)
        sample_time = time.monotonic()
        cpu_temperature = self.temperatura_cpu()
        gpu_temperature = self.temperatura_chip('amdgpu', 'edge')
        vrm_temperature = auxiliary_temperatures.get('vrm_temperature_c')
        board_temperature = auxiliary_temperatures.get('board_temperature_c')
        return {
            'cpu': psutil.cpu_percent(interval=None),
            'hilos': psutil.cpu_percent(interval=None, percpu=True),
            'cpu_freq': cpu_freq.current if cpu_freq else None,
            'cpu_voltage': self.voltaje_chip('amdgpu', 'vddnb'),
            'gpu_voltage': self.voltaje_chip('amdgpu', 'vddgfx'),
            'gpu_busy': gpu_busy,
            'memoria_porcentaje': memoria.percent,
            'memoria_disponible': memoria.available,
            'memoria_total': memoria.total,
            'swap_porcentaje': swap.percent,
            'swap_usado': swap.used,
            'swap_total': swap.total,
            'disco_porcentaje': raiz.percent,
            'disco_usado': raiz.used,
            'disco_total': raiz.total,
            'disco_lectura': lectura,
            'disco_escritura': escritura,
            'cpu_temp': cpu_temperature,
            'gpu_temp': gpu_temperature,
            'vrm_temp': vrm_temperature,
            'vrm_mos_temp': auxiliary_temperatures.get('vrm_mos_temperature_c'),
            'vrm_temp_cpu': auxiliary_temperatures.get('vrm_cpu_temperature_c'),
            'vrm_temp_gpu': auxiliary_temperatures.get('vrm_gpu_temperature_c'),
            'vrm_source': auxiliary_temperatures.get('vrm_source', ''),
            'vrm_input_voltage_v': auxiliary_temperatures.get('vrm_input_voltage_v'),
            'vrm_total_power_w': auxiliary_temperatures.get('vrm_total_power_w'),
            'vrm_cpu_voltage_v': auxiliary_temperatures.get('vrm_cpu_voltage_v'),
            'vrm_gpu_voltage_v': auxiliary_temperatures.get('vrm_gpu_voltage_v'),
            'vrm_cpu_current_a': auxiliary_temperatures.get('vrm_cpu_current_a'),
            'vrm_gpu_current_a': auxiliary_temperatures.get('vrm_gpu_current_a'),
            'vrm_cpu_power_w': auxiliary_temperatures.get('vrm_cpu_power_w'),
            'vrm_gpu_power_w': auxiliary_temperatures.get('vrm_gpu_power_w'),
            'vrm_alerts': tuple(auxiliary_temperatures.get('vrm_alerts') or ()),
            'vrm_probe': auxiliary_temperatures.get('vrm_probe') or {},
            'board_temp': board_temperature,
            'temperature_sensor_times': {
                sensor: sample_time
                for sensor, value in (
                    ('cpu', cpu_temperature),
                    ('gpu', gpu_temperature),
                    ('vrm', vrm_temperature),
                    ('board', board_temperature),
                )
                if value is not None
            },
            'gpu_power': potencia.get('gpu_w'),
            'power_w': potencia.get('value_w'),
            'power_scope': potencia.get('scope'),
            'power_label': potencia.get('label'),
            'power_source': potencia.get('source'),
            'power_is_total': bool(potencia.get('is_total')),
            'fan_rpm': self.ventilador_principal(),
            'board_temps': self.temperaturas_board(),
            **self.firmware_instalado(),
            **gpu_technical,
        }

    def _interfaz_red_predeterminada(self):
        try:
            lineas = Path('/proc/net/route').read_text(encoding='utf-8', errors='ignore').splitlines()[1:]
            for linea in lineas:
                partes = linea.split()
                if len(partes) >= 4 and partes[1] == '00000000' and int(partes[3], 16) & 0x2:
                    return partes[0]
        except (OSError, ValueError):
            logger.debug("Could not determine the default network route from /proc/net/route", exc_info=True)
        try:
            estados = psutil.net_if_stats()
            contadores = psutil.net_io_counters(pernic=True)
            candidatas = [
                nombre for nombre, estado in estados.items()
                if nombre != 'lo' and estado.isup and nombre in contadores
            ]
            if candidatas:
                return max(candidatas, key=lambda nombre: contadores[nombre].bytes_recv + contadores[nombre].bytes_sent)
        except (OSError, RuntimeError):
            logger.debug("Could not determine the busiest active network interface", exc_info=True)
        return ''

    def _contador_disco_raiz(self):
        dispositivo = ''
        try:
            particiones = psutil.disk_partitions(all=False)
            raiz = next((item for item in particiones if item.mountpoint == '/'), None)
            dispositivo = raiz.device if raiz else ''
        except Exception:
            dispositivo = ''
        try:
            por_disco = psutil.disk_io_counters(perdisk=True, nowrap=True) or {}
        except TypeError:
            por_disco = psutil.disk_io_counters(perdisk=True) or {}
        claves = []
        if dispositivo:
            claves.extend((Path(dispositivo).name, dispositivo.rsplit('/', 1)[-1]))
            try:
                resuelto = Path(dispositivo).resolve()
                claves.append(resuelto.name)
            except OSError:
                logger.debug("Could not resolve disk device path %s", dispositivo, exc_info=True)
        contador = next((por_disco.get(clave) for clave in claves if por_disco.get(clave) is not None), None)
        etiqueta = next((clave for clave in claves if por_disco.get(clave) is not None), '')
        if contador is None:
            try:
                contador = psutil.disk_io_counters(nowrap=True)
            except TypeError:
                contador = psutil.disk_io_counters()
            etiqueta = Path(dispositivo).name if dispositivo else 'all disks'
        return etiqueta or 'root disk', contador

    #: How long the core counts are trusted. Topology only changes with CPU
    #: hotplug, and re-reading it every second was a fifth of a sample's cost.
    _TOPOLOGIA_CPU_TTL = 30.0

    def _topologia_cpu(self):
        """(physical, logical) core counts, re-read at most every 30 seconds."""
        ahora = time.monotonic()
        cache = getattr(self, '_topologia_cpu_cache', None)
        if cache is None or ahora - cache[0] > self._TOPOLOGIA_CPU_TTL:
            cache = (ahora, psutil.cpu_count(logical=False), psutil.cpu_count(logical=True))
            self._topologia_cpu_cache = cache
        return cache[1], cache[2]

    @staticmethod
    def _tiempo_cpu_ocupado(tiempos):
        """(busy, total) seconds of one CPU, counted the way psutil counts them.

        Guest time is already inside user and nice on Linux, so it is taken
        out of the total rather than counted twice.
        """
        total = sum(tiempos)
        total -= getattr(tiempos, 'guest', 0.0) + getattr(tiempos, 'guest_nice', 0.0)
        return total - tiempos.idle - getattr(tiempos, 'iowait', 0.0), total

    def _uso_cpu_propio(self):
        """(total %, per-thread %) over this sampler's own interval, or None.

        psutil.cpu_percent(interval=None) measures since the last call made by
        anyone in the process, and the CPU page and the dashboard call it too.
        One of them calling a few milliseconds earlier left this sample an
        interval of almost nothing, and the monitor's graph plunged to 0 %.
        """
        actuales = psutil.cpu_times(percpu=True)
        anteriores = getattr(self, '_metricas_rt_cpu_times', None)
        self._metricas_rt_cpu_times = actuales
        if not anteriores or len(anteriores) != len(actuales):
            return None
        ocupado_total = transcurrido_total = 0.0
        hilos = []
        for antes, ahora in zip(anteriores, actuales):
            ocupado_antes, total_antes = self._tiempo_cpu_ocupado(antes)
            ocupado_ahora, total_ahora = self._tiempo_cpu_ocupado(ahora)
            ocupado = max(0.0, ocupado_ahora - ocupado_antes)
            transcurrido = max(0.0, total_ahora - total_antes)
            ocupado_total += ocupado
            transcurrido_total += transcurrido
            hilos.append(100.0 * ocupado / transcurrido if transcurrido > 0 else 0.0)
        if transcurrido_total <= 0:
            return None
        return 100.0 * ocupado_total / transcurrido_total, hilos

    def _muestra_cpu_tiempo_real(self):
        propio = self._uso_cpu_propio()
        if propio is None:
            # The first sample has no interval of its own yet.
            cpu_total = psutil.cpu_percent(interval=None)
            cpu_hilos = psutil.cpu_percent(interval=None, percpu=True)
        else:
            cpu_total, cpu_hilos = propio
        try:
            cpu_frecuencias = psutil.cpu_freq(percpu=True) or []
        except TypeError:
            # Some psutil backends only expose the aggregate frequency.  The
            # per-core dashboard still reports load, without inventing clocks.
            cpu_frecuencias = []
        actuales = [
            float(frequency.current)
            for frequency in cpu_frecuencias
            if frequency and frequency.current is not None
        ]
        # psutil's aggregate is this same mean over the per-CPU readings;
        # asking it separately read every scaling_cur_freq file twice.
        cpu_freq_mhz = (
            sum(actuales) / len(actuales)
            if actuales
            else getattr(psutil.cpu_freq(), 'current', None)
        )
        physical_cores, logical_cores = self._topologia_cpu()
        # Present physical-core usage in the UI.  On SMT systems psutil's
        # per-cpu values are logical threads; average each thread group so
        # the BC-250 summary reports its eight actual cores, not 1–8 threads.
        per_core = list(cpu_hilos)
        if physical_cores and len(cpu_hilos) > physical_cores:
            threads_per_core = max(1, len(cpu_hilos) // physical_cores)
            per_core = [
                sum(cpu_hilos[offset : offset + threads_per_core]) / threads_per_core
                for offset in range(0, len(cpu_hilos), threads_per_core)
            ][:physical_cores]
            per_core_frequency = [
                sum(
                    float(frequency.current)
                    for frequency in cpu_frecuencias[offset : offset + threads_per_core]
                    if frequency and frequency.current is not None
                )
                / max(
                    1,
                    sum(
                        1
                        for frequency in cpu_frecuencias[
                            offset : offset + threads_per_core
                        ]
                        if frequency and frequency.current is not None
                    ),
                )
                for offset in range(0, len(cpu_frecuencias), threads_per_core)
            ][:physical_cores]
        else:
            per_core_frequency = [
                float(frequency.current)
                for frequency in cpu_frecuencias
                if frequency and frequency.current is not None
            ]
        return {
            'usage_percent': bounded_percent(cpu_total),
            'per_core_percent': [bounded_percent(value) for value in per_core],
            'per_core_frequency_mhz': per_core_frequency,
            'frequency_mhz': float(cpu_freq_mhz) if cpu_freq_mhz is not None else None,
            'temperature_c': self.temperatura_cpu(),
            'logical_cores': logical_cores or len(cpu_hilos),
            'physical_cores': physical_cores,
            'load_average': list(os.getloadavg()) if hasattr(os, 'getloadavg') else [],
        }

    @staticmethod
    def _muestra_memoria_tiempo_real():
        memoria = psutil.virtual_memory()
        swap = psutil.swap_memory()
        return {
            'usage_percent': float(memoria.percent),
            'used': max(0, int(memoria.total - memoria.available)),
            'available': int(memoria.available),
            'total': int(memoria.total),
            'swap_percent': float(swap.percent),
            'swap_used': int(swap.used),
            'swap_total': int(swap.total),
            **read_memory_runtime_state(),
        }

    def _muestra_disco_tiempo_real(self, intervalo):
        raiz = psutil.disk_usage('/')
        nombre, contador = self._contador_disco_raiz()
        lectura, escritura, actividad = disk_rates(
            nombre, contador, self._metricas_rt_disk, intervalo
        )
        self._metricas_rt_disk = (nombre, contador)
        return {
            'device': nombre,
            'usage_percent': float(raiz.percent),
            'used': int(raiz.used),
            'total': int(raiz.total),
            'active_percent': actividad,
            'read_bps': lectura,
            'write_bps': escritura,
            'read_total': int(getattr(contador, 'read_bytes', 0) or 0),
            'write_total': int(getattr(contador, 'write_bytes', 0) or 0),
        }

    def _muestra_red_tiempo_real(self, intervalo):
        interfaz = self._interfaz_red_predeterminada()
        try:
            redes = psutil.net_io_counters(pernic=True, nowrap=True) or {}
        except TypeError:
            redes = psutil.net_io_counters(pernic=True) or {}
        contador = redes.get(interfaz)
        bajada, subida = network_rates(
            contador, self._metricas_rt_network.get(interfaz), intervalo
        )
        if contador is not None:
            self._metricas_rt_network = {interfaz: contador}
        return {
            'interface': interfaz or 'not detected',
            'download_bps': bajada,
            'upload_bps': subida,
            'bytes_received': int(getattr(contador, 'bytes_recv', 0) or 0),
            'bytes_sent': int(getattr(contador, 'bytes_sent', 0) or 0),
        }

    def _muestra_gpu_potencia_tiempo_real(self):
        gpu = self._gpu_device_path()
        gpu_busy = self._gpu_busy_percent(gpu) if gpu else self._gpu_busy_percent(None)
        from bc250cc.infrastructure.gpu_live_clock import read_hwmon_clock_mhz

        gpu_sclk = read_hwmon_clock_mhz(gpu)
        if gpu_sclk is None and gpu:
            gpu_sclk = self._parse_dpm_actual(self._leer_texto(gpu / 'pp_dpm_sclk'))
        vram_total = self._leer_entero(gpu / 'mem_info_vram_total') if gpu else None
        vram_used = self._leer_entero(gpu / 'mem_info_vram_used') if gpu else None
        potencia = self.lectura_potencia()
        technical = self._gpu_technical_metrics(gpu)
        return (
            {
                'usage_percent': None if gpu_busy is None else bounded_percent(gpu_busy),
                'frequency_mhz': gpu_sclk,
                'temperature_c': self.temperatura_chip('amdgpu', 'edge'),
                'voltage_mv': self.voltaje_chip('amdgpu', 'vddgfx'),
                'power_w': potencia.get('gpu_w'),
                'vram_used': vram_used,
                'vram_total': vram_total,
                'compute_busy_percent': getattr(self, 'gpu_compute_busy', None),
                'compute_process': getattr(self, 'gpu_compute_process', ''),
                **technical,
            },
            {
                'value_w': potencia.get('value_w'),
                'gpu_w': potencia.get('gpu_w'),
                'scope': potencia.get('scope'),
                'label': potencia.get('label'),
                'source': potencia.get('source'),
                'is_total': bool(potencia.get('is_total')),
            },
        )

    def _gpu_technical_metrics(self, gpu):
        """Read compact, passive GPU diagnostics from the selected DRM device."""
        if not gpu:
            return {
                'memory_frequency_mhz': None,
                'soc_frequency_mhz': None,
                'fabric_frequency_mhz': None,
                'pcie_link': '',
                'vbios_version': '',
                'gtt_used': None,
                'gtt_total': None,
                'dpm_force_level': '',
                'dpm_state': '',
            }
        return {
            'memory_frequency_mhz': self._parse_dpm_actual(
                self._leer_texto(gpu / 'pp_dpm_mclk')
            ),
            # The two clocks that decide how fast the GPU can reach memory on
            # this APU. Both are already exposed by amdgpu and neither was
            # read: a 450 MHz fabric clock explains a stall that core and
            # memory clocks alone do not.
            'soc_frequency_mhz': self._parse_dpm_actual(
                self._leer_texto(gpu / 'pp_dpm_socclk')
            ),
            'fabric_frequency_mhz': self._parse_dpm_actual(
                self._leer_texto(gpu / 'pp_dpm_fclk')
            ),
            # A BC-250 on a riser can negotiate a narrower or slower link than
            # the slot allows, and nothing else on screen would show it.
            'pcie_link': self._enlace_pcie(gpu),
            # The first thing any support thread asks for.
            'vbios_version': (self._leer_texto(gpu / 'vbios_version') or '').strip(),
            'gtt_used': self._leer_entero(gpu / 'mem_info_gtt_used'),
            'gtt_total': self._leer_entero(gpu / 'mem_info_gtt_total'),
            'dpm_force_level': self._leer_texto(
                gpu / 'power_dpm_force_performance_level'
            ) or '',
            'dpm_state': self._leer_texto(gpu / 'power_dpm_state') or '',
        }

    def _enlace_pcie(self, gpu):
        """The negotiated link, as "16.0 GT/s x16", or empty when unknown."""
        speed = (self._leer_texto(gpu / 'current_link_speed') or '').strip()
        width = (self._leer_texto(gpu / 'current_link_width') or '').strip()
        if not speed or not width:
            return ''
        # The driver writes "16.0 GT/s PCIe"; the bus name is already implied.
        speed = speed.replace('PCIe', '').strip()
        return f'{speed} x{width}'

    def obtener_metricas_tiempo_real(self):
        """Return one passive Linux performance sample for the live monitor.

        Disk and network counters remain local to this sampler so their rates
        represent the interval between real-time samples. The View shares each
        completed sample briefly to avoid duplicate sensor enumeration.
        """
        with self._metricas_rt_lock:
            ahora = time.monotonic()
            anterior = self._metricas_rt_time
            intervalo = max(0.001, ahora - anterior) if anterior is not None else 0.0

            cpu = self._muestra_cpu_tiempo_real()
            memoria = self._muestra_memoria_tiempo_real()
            disco = self._muestra_disco_tiempo_real(intervalo)
            red = self._muestra_red_tiempo_real(intervalo)
            gpu, potencia = self._muestra_gpu_potencia_tiempo_real()
            sensors = self.temperaturas_auxiliares()

            self._metricas_rt_time = ahora
            return {
                'sample_interval': intervalo,
                'cpu': cpu,
                'gpu': gpu,
                'power': potencia,
                'sensors': sensors,
                'memory': memoria,
                'disk': disco,
                'network': red,
            }

    def obtener_procesos(self):
        return psutil.process_iter(['pid', 'name', 'cmdline', 'memory_info', 'uids'])
