from pathlib import Path
import os
import re
import shlex
import shutil
import subprocess
import time
import json
import psutil
from mvc.Repository.configuracion_local import ConfiguracionLocal
from mvc.Repository.historial_repository import HistorialRepository
from mvc.Repository.terminal_repository import TerminalRepository
from mvc.Repository.dependencias_repository import DependenciasRepository
from mvc.Repository.gpu_repository import GPURepository
from mvc.Repository.cpu_repository import CPURepository
from mvc.Repository.cu_repository import CURepository

class SistemaRepository(TerminalRepository, DependenciasRepository, GPURepository, CPURepository, CURepository):
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

    def potencia_gpu(self):
        for nombre, carpeta in self.hwmons:
            if 'amdgpu' in nombre.lower():
                valor = self._leer_entero(carpeta / 'power1_input')
                return None if valor is None else valor / 1000000
        return None

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
        m = re.search(r'\b(\d+)\b', out)
        return int(m.group(1)) if m else None

    def _dbus_bool_property(self, objeto, interfaz, propiedad):
        rc, out, _err = self._ejecutar([
            'busctl', 'get-property', 'com.cyanskillfish.Governor', objeto, interfaz, propiedad
        ])
        if rc != 0:
            return None
        return 'true' in out.lower()

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
            except Exception:
                pass
        return nuevo

    def _historial_repo(self):
        return HistorialRepository(self._historial_path(), 26, 6)

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
            except Exception:
                pass
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
            'gpu_power': self.potencia_gpu(),
            'fan_rpm': self.ventilador_principal(),
            'board_temps': self.temperaturas_board()
        }

    def obtener_procesos(self):
        return psutil.process_iter(['pid', 'name', 'cmdline', 'memory_info', 'uids'])
