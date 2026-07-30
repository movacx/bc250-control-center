from pathlib import Path
import logging
import os
import re
import shutil
import subprocess
import time
import threading
import psutil
from mvc.Repository.configuracion_local import ConfiguracionLocal
from mvc.Repository.historial_repository import HistorialRepository
from mvc.Repository.terminal_repository import TerminalRepository
from mvc.Repository.dependencias_repository import DependenciasRepository
from mvc.Repository.gpu_repository import GPURepository
from mvc.Repository.cpu_repository import CPURepository
from mvc.Repository.cu_repository import CURepository
from mvc.Repository.fan_repository import FanRepository
from mvc.Repository.privilege_repository import PrivilegeRepository

logger = logging.getLogger(__name__)


class SistemaRepository(PrivilegeRepository, TerminalRepository, DependenciasRepository, GPURepository, CPURepository, CURepository, FanRepository):
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
        self.hwmons.clear()
        for carpeta in sorted(Path('/sys/class/hwmon').glob('hwmon*')):
            nombre = self._leer_texto(carpeta / 'name') or carpeta.name
            self.hwmons.append((nombre, carpeta))

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
        for nombre, carpeta in self.hwmons:
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
            r = subprocess.run(comando, text=True, capture_output=True, timeout=timeout)
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
        if gpu:
            busy = self._leer_entero(gpu / 'gpu_busy_percent')
            if busy is not None:
                self.gpu_busy_cache = max(0, min(100, busy))
                self.gpu_busy_cache_time = time.monotonic()
                return self.gpu_busy_cache
        ahora = time.monotonic()
        if ahora - self.gpu_busy_cache_time < 2:
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
        rc, out, _err = self._ejecutar(['systemctl', 'show', servicio, f'--property={prop}', '--value'])
        return out if rc == 0 else ''

    def _safe_points_config(self):
        ruta = Path('/etc/cyan-skillfish-governor-smu/config.toml')
        texto = self._leer_texto(ruta) or ''
        puntos = []
        frecuencias = []
        bloque = {}
        activo = False
        for linea in texto.splitlines():
            limpia = linea.strip()
            if not limpia:
                continue
            comentada = limpia.startswith('#')
            if limpia.lstrip('#').strip() == '[[safe-points]]':
                if 'frequency' in bloque:
                    puntos.append(bloque)
                bloque = {}
                activo = not comentada
                continue
            if activo and '=' in limpia and not comentada:
                clave, valor = limpia.split('=', 1)
                clave = clave.strip()
                m = re.search(r'\d+', valor)
                if clave in ('frequency', 'voltage') and m:
                    bloque[clave] = int(m.group(0))
                    if clave == 'frequency':
                        frecuencias.append(int(m.group(0)))
        if 'frequency' in bloque:
            puntos.append(bloque)
        con_voltaje = [p for p in puntos if 'frequency' in p and 'voltage' in p]
        sin_voltaje = [p for p in puntos if 'frequency' in p and 'voltage' not in p]
        ordenados = sorted(con_voltaje, key=lambda p: p['frequency'])
        errores_voltaje = []
        for anterior, actual in zip(ordenados, ordenados[1:]):
            if actual['voltage'] < anterior['voltage']:
                errores_voltaje.append({
                    'previous_frequency': anterior['frequency'],
                    'previous_voltage': anterior['voltage'],
                    'frequency': actual['frequency'],
                    'voltage': actual['voltage'],
                })
        duplicadas = sorted({f for f in frecuencias if frecuencias.count(f) > 1})
        max_freq = max([p['frequency'] for p in con_voltaje], default=max(frecuencias, default=None))
        max_volt = max([p['voltage'] for p in con_voltaje], default=None)
        return {
            'points': puntos,
            'points_with_voltage': con_voltaje,
            'max_frequency': max_freq,
            'max_voltage': max_volt,
            'missing_voltage': sin_voltaje,
            'voltage_order_errors': errores_voltaje,
            'duplicate_frequencies': duplicadas,
            'config_path': str(ruta),
        }


    def _historial_path(self):
        nuevo = self.configuracion.historial_path()
        viejo = self._data_dir() / 'historial_eventos.jsonl'
        if viejo.exists() and not nuevo.exists():
            try:
                nuevo.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(viejo, nuevo)
            except OSError:
                logger.warning("Could not migrate legacy data from %s to %s", viejo, nuevo, exc_info=True)
        return nuevo

    def _historial_repo(self):
        # Keep a useful audit trail; the former 26/6 policy discarded twenty
        # records at once as soon as the 27th event arrived.
        return HistorialRepository(self._historial_path(), 1000, 800)

    def registrar_evento(self, tipo, nivel, titulo, detalle='', datos=None):
        repo = self._historial_repo()
        evento = repo.nuevo_evento(tipo, nivel, titulo, detalle, datos or {})
        return repo.agregar(evento)

    def obtener_eventos(self, limite=300):
        return self._historial_repo().listar(limite)

    def limpiar_historial(self):
        return self._historial_repo().limpiar()

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
            'historial': str(self._historial_path()),
            'estabilidad': str(self.configuracion.estabilidad_path()),
            'metricas_runtime': str(self.configuracion.metricas_runtime_path()),
            'tools': str(self._tool_dir()),
            'data': str(self.configuracion.carpeta_data()),
            'resource_tools': str(self.configuracion.carpeta_resource_tools()),
        }

    def leer_config_local(self):
        return self.configuracion.leer_config()

    def guardar_config_local(self, datos):
        return self.configuracion.guardar_config(datos)

    def leer_perfiles_locales(self):
        return self.configuracion.leer_perfiles()

    def registrar_metrica_runtime(self, datos):
        return self.configuracion.registrar_metrica_runtime(datos)

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
        return {
            'cpu': psutil.cpu_percent(interval=None),
            'hilos': psutil.cpu_percent(interval=None, percpu=True),
            'cpu_freq': cpu_freq.current if cpu_freq else None,
            'cpu_voltage': self.voltaje_chip('amdgpu', 'vddnb'),
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
            'cpu_temp': self.temperatura_chip('k10temp', 'Tctl'),
            'gpu_temp': self.temperatura_chip('amdgpu', 'edge'),
            'gpu_power': potencia.get('gpu_w'),
            'power_w': potencia.get('value_w'),
            'power_scope': potencia.get('scope'),
            'power_label': potencia.get('label'),
            'power_source': potencia.get('source'),
            'power_is_total': bool(potencia.get('is_total')),
            'fan_rpm': self.ventilador_principal(),
            'board_temps': self.temperaturas_board()
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

            cpu_total = psutil.cpu_percent(interval=None)
            cpu_hilos = psutil.cpu_percent(interval=None, percpu=True)
            cpu_freq = psutil.cpu_freq()
            memoria = psutil.virtual_memory()
            swap = psutil.swap_memory()
            raiz = psutil.disk_usage('/')

            disco_nombre, disco = self._contador_disco_raiz()
            lectura_bps = escritura_bps = actividad_disco = 0.0
            if intervalo and disco is not None and self._metricas_rt_disk is not None:
                previo_nombre, previo = self._metricas_rt_disk
                if previo_nombre == disco_nombre:
                    lectura_bps = max(0.0, (disco.read_bytes - previo.read_bytes) / intervalo)
                    escritura_bps = max(0.0, (disco.write_bytes - previo.write_bytes) / intervalo)
                    busy_actual = getattr(disco, 'busy_time', None)
                    busy_previo = getattr(previo, 'busy_time', None)
                    if busy_actual is not None and busy_previo is not None:
                        actividad_disco = max(0.0, min(100.0, (busy_actual - busy_previo) / (intervalo * 10.0)))
                    else:
                        delta_ms = max(0, (disco.read_time - previo.read_time) + (disco.write_time - previo.write_time))
                        actividad_disco = max(0.0, min(100.0, delta_ms / (intervalo * 10.0)))
            self._metricas_rt_disk = (disco_nombre, disco)

            interfaz = self._interfaz_red_predeterminada()
            try:
                redes = psutil.net_io_counters(pernic=True, nowrap=True) or {}
            except TypeError:
                redes = psutil.net_io_counters(pernic=True) or {}
            red = redes.get(interfaz)
            bajada_bps = subida_bps = 0.0
            if intervalo and red is not None:
                previo = self._metricas_rt_network.get(interfaz)
                if previo is not None:
                    bajada_bps = max(0.0, (red.bytes_recv - previo.bytes_recv) / intervalo)
                    subida_bps = max(0.0, (red.bytes_sent - previo.bytes_sent) / intervalo)
            if red is not None:
                self._metricas_rt_network[interfaz] = red

            gpu = self._gpu_device_path()
            gpu_busy = self._gpu_busy_percent(gpu) if gpu else self._gpu_busy_percent(None)
            gpu_sclk = self._parse_dpm_actual(self._leer_texto(gpu / 'pp_dpm_sclk')) if gpu else None
            vram_total = self._leer_entero(gpu / 'mem_info_vram_total') if gpu else None
            vram_used = self._leer_entero(gpu / 'mem_info_vram_used') if gpu else None
            potencia = self.lectura_potencia()

            self._metricas_rt_time = ahora
            return {
                'sample_interval': intervalo,
                'cpu': {
                    'usage_percent': max(0.0, min(100.0, float(cpu_total or 0.0))),
                    'per_core_percent': [max(0.0, min(100.0, float(value or 0.0))) for value in cpu_hilos],
                    'frequency_mhz': float(cpu_freq.current) if cpu_freq else None,
                    'temperature_c': self.temperatura_chip('k10temp', 'Tctl'),
                    'logical_cores': psutil.cpu_count(logical=True) or len(cpu_hilos),
                    'physical_cores': psutil.cpu_count(logical=False),
                    'load_average': list(os.getloadavg()) if hasattr(os, 'getloadavg') else [],
                },
                'gpu': {
                    'usage_percent': None if gpu_busy is None else max(0.0, min(100.0, float(gpu_busy))),
                    'frequency_mhz': gpu_sclk,
                    'temperature_c': self.temperatura_chip('amdgpu', 'edge'),
                    'power_w': potencia.get('gpu_w'),
                    'vram_used': vram_used,
                    'vram_total': vram_total,
                },
                'power': {
                    'value_w': potencia.get('value_w'),
                    'gpu_w': potencia.get('gpu_w'),
                    'scope': potencia.get('scope'),
                    'label': potencia.get('label'),
                    'source': potencia.get('source'),
                    'is_total': bool(potencia.get('is_total')),
                },
                'memory': {
                    'usage_percent': float(memoria.percent),
                    'used': max(0, int(memoria.total - memoria.available)),
                    'available': int(memoria.available),
                    'total': int(memoria.total),
                    'swap_percent': float(swap.percent),
                    'swap_used': int(swap.used),
                    'swap_total': int(swap.total),
                },
                'disk': {
                    'device': disco_nombre,
                    'usage_percent': float(raiz.percent),
                    'used': int(raiz.used),
                    'total': int(raiz.total),
                    'active_percent': actividad_disco,
                    'read_bps': lectura_bps,
                    'write_bps': escritura_bps,
                    'read_total': int(getattr(disco, 'read_bytes', 0) or 0),
                    'write_total': int(getattr(disco, 'write_bytes', 0) or 0),
                },
                'network': {
                    'interface': interfaz or 'not detected',
                    'download_bps': bajada_bps,
                    'upload_bps': subida_bps,
                    'bytes_received': int(getattr(red, 'bytes_recv', 0) or 0),
                    'bytes_sent': int(getattr(red, 'bytes_sent', 0) or 0),
                },
            }

    def obtener_procesos(self):
        return psutil.process_iter(['pid', 'name', 'cmdline', 'memory_info', 'uids'])
