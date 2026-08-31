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
from bc250cc.infrastructure.cpu_repository import CPURepository
from bc250cc.infrastructure.cu_repository import CURepository
from bc250cc.infrastructure.dependencias_repository import DependenciasRepository
from bc250cc.infrastructure.drivers_repository import DriversRepository
from bc250cc.infrastructure.fan_repository import FanRepository
from bc250cc.infrastructure.gpu_repository import GPURepository
from bc250cc.infrastructure.health_repository import HealthRepository
from bc250cc.infrastructure.memory_runtime import read_memory_runtime_state
from bc250cc.infrastructure.persistence.activity_journal import activity_journal_path
from bc250cc.infrastructure.persistence.configuracion_local import ConfiguracionLocal
from bc250cc.infrastructure.persistence.profile_bundle import ProfileBundleRepository
from bc250cc.infrastructure.privilege_repository import PrivilegeRepository
from bc250cc.infrastructure.realtime_metrics_policy import (
    bounded_percent,
    disk_rates,
    network_rates,
)
from bc250cc.infrastructure.terminal_repository import TerminalRepository
from bc250cc.platform.init.services import (
    detect_init_manager,
    parse_openrc_runlevel,
    parse_openrc_status,
    service_key,
)

logger = logging.getLogger(__name__)


class SistemaRepository(PrivilegeRepository, TerminalRepository, DependenciasRepository, DriversRepository, GPURepository, CPURepository, CURepository, FanRepository, HealthRepository, RecoveryRepository):
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
                    return None if valor is None else valor
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

        result = {
            'nvme_temperature_c': max(nvme) if nvme else None,
            'nvme_hotspot_temperature_c': (
                max(nvme_hotspot) if nvme_hotspot else None
            ),
            'board_temperature_c': max(board) if board else None,
            'vrm_temperature_c': max(vrm) if vrm else None,
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
            return r.returncode, (r.stdout or '').strip(), (r.stderr or '').strip()
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


    def _gpu_fdinfo_total_ns(self):
        totales = {}
        for archivo in Path('/proc').glob('[0-9]*/fdinfo/*'):
            try:
                texto = archivo.read_text(errors='ignore')
            except Exception:
                continue
            if 'drm-driver:' not in texto or 'amdgpu' not in texto:
                continue
            pid = archivo.parent.parent.name
            total = 0
            for linea in texto.splitlines():
                if not linea.startswith('drm-engine-'):
                    continue
                m = re.search(r':\s*(\d+)\s*ns', linea)
                if m:
                    total += int(m.group(1))
            if total:
                totales[pid] = max(totales.get(pid, 0), total)
        return sum(totales.values())

    def _gpu_busy_fdinfo(self):
        ahora = time.monotonic_ns()
        total = self._gpu_fdinfo_total_ns()
        if self.gpu_fdinfo_anterior is None or self.tiempo_gpu_fdinfo is None:
            self.gpu_fdinfo_anterior = total
            self.tiempo_gpu_fdinfo = ahora
            return None
        delta = total - self.gpu_fdinfo_anterior
        transcurrido = ahora - self.tiempo_gpu_fdinfo
        self.gpu_fdinfo_anterior = total
        self.tiempo_gpu_fdinfo = ahora
        if delta <= 0 or transcurrido <= 0:
            return 0
        return int(max(0, min(100, round((delta / transcurrido) * 100))))

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
        ahora = time.monotonic()
        if not sysfs_invalid and ahora - self.gpu_busy_cache_time < 2:
            return self.gpu_busy_cache
        self.gpu_busy_cache = self._gpu_busy_fdinfo()
        self.gpu_busy_cache_time = ahora
        return self.gpu_busy_cache

    def _parse_dpm_actual(self, texto):
        if not texto:
            return None
        for linea in texto.splitlines():
            if '*' not in linea:
                continue
            m = re.search(r'(\d+)\s*Mhz', linea, re.IGNORECASE)
            if m:
                return int(m.group(1))
        return None

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

    def _dbus_uint_property(self, objeto, interfaz, propiedad):
        rc, out, _err = self._ejecutar([
            'busctl', 'get-property', 'com.cyanskillfish.Governor', objeto, interfaz, propiedad
        ])
        if rc != 0:
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
        rc, out, _err = self._ejecutar([
            'busctl', 'get-property', 'com.cyanskillfish.Governor', objeto, interfaz, propiedad
        ])
        if rc != 0:
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

    def _buscar_archivo(self, patron, max_depth=5):
        for base in self._candidatos_busqueda():
            try:
                directos = list(base.glob(patron))
                if directos:
                    return str(directos[0])
                for ruta in base.rglob(patron):
                    try:
                        rel = ruta.relative_to(base)
                        if len(rel.parts) <= max_depth:
                            return str(ruta)
                    except Exception:
                        return str(ruta)
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
            'cpu_temp': self.temperatura_cpu(),
            'gpu_temp': self.temperatura_chip('amdgpu', 'edge'),
            'gpu_power': potencia.get('gpu_w'),
            'power_w': potencia.get('value_w'),
            'power_scope': potencia.get('scope'),
            'power_label': potencia.get('label'),
            'power_source': potencia.get('source'),
            'power_is_total': bool(potencia.get('is_total')),
            'fan_rpm': self.ventilador_principal(),
            'board_temps': self.temperaturas_board(),
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

    def _muestra_cpu_tiempo_real(self):
        cpu_total = psutil.cpu_percent(interval=None)
        cpu_hilos = psutil.cpu_percent(interval=None, percpu=True)
        cpu_freq = psutil.cpu_freq()
        try:
            cpu_frecuencias = psutil.cpu_freq(percpu=True) or []
        except TypeError:
            # Some psutil backends only expose the aggregate frequency.  The
            # per-core dashboard still reports load, without inventing clocks.
            cpu_frecuencias = []
        physical_cores = psutil.cpu_count(logical=False)
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
            'frequency_mhz': float(cpu_freq.current) if cpu_freq else None,
            'temperature_c': self.temperatura_cpu(),
            'logical_cores': psutil.cpu_count(logical=True) or len(cpu_hilos),
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
                'gtt_used': None,
                'gtt_total': None,
                'dpm_force_level': '',
                'dpm_state': '',
            }
        return {
            'memory_frequency_mhz': self._parse_dpm_actual(
                self._leer_texto(gpu / 'pp_dpm_mclk')
            ),
            'gtt_used': self._leer_entero(gpu / 'mem_info_gtt_used'),
            'gtt_total': self._leer_entero(gpu / 'mem_info_gtt_total'),
            'dpm_force_level': self._leer_texto(
                gpu / 'power_dpm_force_performance_level'
            ) or '',
            'dpm_state': self._leer_texto(gpu / 'power_dpm_state') or '',
        }

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
