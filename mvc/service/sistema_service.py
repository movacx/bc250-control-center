import os
import logging
import signal
import subprocess
import psutil
try:
    from mvc.Model.proceso import Proceso
    from mvc.Model.rendimiento import Rendimiento
except ImportError:
    from Model.proceso import Proceso
    from Model.rendimiento import Rendimiento

logger = logging.getLogger(__name__)


CRITICOS = [
    'systemd', 'dbus', 'sddm', 'gdm', 'gdm-wayland-session', 'xorg', 'xwayland', 'wayland',
    'kwin', 'plasmashell', 'startplasma', 'ksmserver', 'kded', 'klauncher', 'kglobalaccel',
    'kactivity', 'kaccess', 'kwallet', 'ksecretd', 'powerdevil',
    'gnome-shell', 'gnome-session', 'gnome-session-binary', 'mutter', 'gnome-keyring',
    'gnome-settings-daemon', 'gsd-', 'dconf-service', 'ibus', 'at-spi', 'gvfs',
    'xdg-desktop', 'xdg-document-portal', 'xdg-permission-store', 'portal',
    'polkit', 'pipewire', 'wireplumber', 'pulseaudio', 'loginctl',
    'konsole', 'ptyxis', 'kgx', 'gnome-terminal', 'bash', 'zsh', 'fish', 'python',
    'codex', 'bc250-control-center'
]

OCULTOS = CRITICOS + [
    'baloo_file', 'baloorunner', 'kdeconnectd', 'agent', 'ssh-agent', 'gpg-agent',
    'tracker', 'tracker-miner', 'localsearch', 'gnome-software', 'evolution-source-registry',
    'evolution-calendar-factory', 'evolution-addressbook-factory', 'goa-daemon'
]

class SistemaService:
    def __init__(self, repo):
        self.repo = repo
        self.uid = os.getuid()
        self.pid_actual = os.getpid()

    @staticmethod
    def _config_int(value, default, minimum, maximum):
        try:
            parsed = int(float(value))
        except (TypeError, ValueError, OverflowError):
            parsed = int(default)
        return max(int(minimum), min(int(maximum), parsed))

    @staticmethod
    def _config_bool(value, default=False):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {'1', 'true', 'yes', 'on', 'enabled'}:
                return True
            if normalized in {'0', 'false', 'no', 'off', 'disabled', ''}:
                return False
        return bool(default)

    def _contiene(self, texto, lista):
        texto = texto.lower()
        for palabra in lista:
            if palabra in texto:
                return palabra
        return ''

    def _es_critico(self, nombre, comando):
        return self._contiene(f'{nombre} {comando}', CRITICOS)

    def _es_oculto(self, nombre, comando):
        return self._contiene(f'{nombre} {comando}', OCULTOS)

    def rendimiento(self):
        return Rendimiento(self.repo.obtener_rendimiento())

    def metricas_tiempo_real(self):
        return self.repo.obtener_metricas_tiempo_real()

    def procesos(self, ocultar_sistema=True):
        lista = []
        for p in self.repo.obtener_procesos():
            try:
                if p.pid == self.pid_actual:
                    continue

                uids = p.info.get('uids')
                if uids and uids.real != self.uid:
                    continue

                nombre = p.info.get('name') or '?'
                comando = ' '.join(p.info.get('cmdline') or []) or nombre
                memoria = p.info['memory_info'].rss if p.info.get('memory_info') else 0

                if memoria < 20 * 1024 * 1024:
                    continue

                if ocultar_sistema and self._es_oculto(nombre, comando):
                    continue

                razon = self._es_critico(nombre, comando)
                protegido = bool(razon)
                lista.append(Proceso(p.pid, nombre, memoria, comando, protegido, razon, p.create_time()))
            except (psutil.Error, OSError, ValueError):
                logger.debug("Skipping process %s because its metadata became unavailable", getattr(p, "pid", "?"), exc_info=True)

        lista.sort(key=lambda x: x.memoria, reverse=True)
        return lista

    def cerrar_procesos(self, procesos):
        pendientes = []
        for proceso in procesos:
            if proceso.protegido:
                continue
            try:
                process = psutil.Process(int(proceso.pid))
                expected_time = getattr(proceso, 'create_time', None)
                current_time = process.create_time()
                if expected_time is not None and float(expected_time) != float(current_time):
                    continue
                uids = process.uids()
                nombre = process.name() or ''
                comando = ' '.join(process.cmdline() or [])
                if uids.real != self.uid or process.pid == self.pid_actual or self._es_critico(nombre, comando):
                    continue
                process.send_signal(signal.SIGTERM)
                pendientes.append((process, current_time))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, ValueError, TypeError):
                continue

        if not pendientes:
            return []
        _gone, alive = psutil.wait_procs([process for process, _created in pendientes], timeout=1.5)
        alive_pids = {process.pid for process in alive}

        force_closed = []
        for process, create_time in pendientes:
            if process.pid not in alive_pids:
                continue
            try:
                # A PID may be reused after SIGTERM. Never kill a different
                # process that appeared under the same numeric PID.
                if process.is_running() and process.create_time() == create_time:
                    uids = process.uids()
                    nombre = process.name() or ''
                    comando = ' '.join(process.cmdline() or [])
                    if uids.real == self.uid and process.pid != self.pid_actual and not self._es_critico(nombre, comando):
                        process.kill()
                        force_closed.append(process.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return force_closed

    def limpiar_cache(self):
        """Run the fixed privileged cache workflow and report its real result."""
        try:
            result = subprocess.run(
                ['pkexec', 'sh', '-c', 'sync; echo 3 > /proc/sys/vm/drop_caches'],
                text=True,
                capture_output=True,
                timeout=120,
                check=False,
            )
        except FileNotFoundError as error:
            raise RuntimeError('pkexec is not available on this system.') from error
        except subprocess.TimeoutExpired as error:
            raise RuntimeError('The privileged cache operation timed out.') from error
        output = (result.stdout or result.stderr or '').strip()
        if result.returncode != 0:
            raise RuntimeError(output or f'pkexec exited with code {result.returncode}.')
        return {'returncode': result.returncode, 'output': output}


    def registrar_evento(self, tipo, nivel, titulo, detalle='', datos=None):
        return self.repo.registrar_evento(tipo, nivel, titulo, detalle, datos)

    def obtener_eventos(self, limite=300):
        return self.repo.obtener_eventos(limite)

    def limpiar_historial(self):
        return self.repo.limpiar_historial()



    def config_paths(self):
        return self.repo.config_paths()

    def leer_config_local(self):
        return self.repo.leer_config_local()

    def guardar_config_local(self, datos):
        return self.repo.guardar_config_local(datos)

    def leer_perfiles_locales(self):
        return self.repo.leer_perfiles_locales()

    def registrar_metrica_runtime(self, datos):
        return self.repo.registrar_metrica_runtime(datos)

    def detectar_juego_activo(self):
        patrones = [
            'steam_app_', 'proton', 'wine', 'gamescope', 'lutris', 'heroic', 'legendary',
            'furmark', 'vkmark', 'unigine', 'benchmark', 'mangohud'
        ]
        candidatos = []
        for p in psutil.process_iter(['pid', 'name', 'cmdline', 'memory_info', 'cpu_percent', 'uids']):
            try:
                uids = p.info.get('uids')
                if uids and uids.real != self.uid:
                    continue
                nombre = p.info.get('name') or ''
                comando = ' '.join(p.info.get('cmdline') or [])
                texto = f'{nombre} {comando}'.lower()
                if self._es_critico(nombre, comando):
                    continue
                if any(patron in texto for patron in patrones):
                    memoria = p.info['memory_info'].rss if p.info.get('memory_info') else 0
                    candidatos.append({
                        'pid': p.pid,
                        'nombre': nombre,
                        'memoria': memoria,
                        'memoria_mb': round(memoria / 1024 / 1024, 1),
                        'comando': comando[:240],
                    })
            except (psutil.Error, OSError, ValueError):
                logger.debug("Skipping memory candidate %s because its metadata became unavailable", getattr(p, "pid", "?"), exc_info=True)
        candidatos.sort(key=lambda x: x['memoria'], reverse=True)
        return candidatos[:8]

    def evaluar_presion_memoria(self):
        config = self.leer_config_local()
        memoria = psutil.virtual_memory()
        swap = psutil.swap_memory()
        warning = self._config_int(config.get('ram_warning_percent', 82), 82, 1, 99)
        critical = self._config_int(config.get('ram_critical_percent', 92), 92, warning + 1, 100)
        swap_warning = self._config_int(config.get('swap_warning_percent', 35), 35, 0, 100)
        nivel = 'normal'
        if memoria.percent >= critical or swap.percent >= max(swap_warning + 25, 70):
            nivel = 'critical'
        elif memoria.percent >= warning or swap.percent >= swap_warning:
            nivel = 'warning'
        juegos = self.detectar_juego_activo()
        return {
            'nivel': nivel,
            'ram_percent': memoria.percent,
            'ram_available': memoria.available,
            'swap_percent': swap.percent,
            'juegos_detectados': juegos,
            'config': {
                'warning': warning,
                'critical': critical,
                'swap_warning': swap_warning,
            }
        }

    def candidatos_cierre_memoria(self, limite=10):
        patrones_candidatos = [
            'firefox', 'chrome', 'chromium', 'brave', 'edge', 'vivaldi', 'opera',
            'discord', 'telegram', 'spotify', 'steamwebhelper', 'electron',
            'discover', 'packagekit', 'baloo', 'tracker', 'indexer'
        ]
        salida = []
        juegos = self.detectar_juego_activo()
        juegos_pid = {j['pid'] for j in juegos}
        for p in psutil.process_iter(['pid', 'name', 'cmdline', 'memory_info', 'uids']):
            try:
                if p.pid in juegos_pid or p.pid == self.pid_actual:
                    continue
                uids = p.info.get('uids')
                if uids and uids.real != self.uid:
                    continue
                nombre = p.info.get('name') or ''
                comando = ' '.join(p.info.get('cmdline') or [])
                memoria = p.info['memory_info'].rss if p.info.get('memory_info') else 0
                if memoria < 80 * 1024 * 1024:
                    continue
                if self._es_critico(nombre, comando):
                    continue
                texto = f'{nombre} {comando}'.lower()
                razon = self._contiene(texto, patrones_candidatos) or 'memoria alta'
                salida.append({
                    'pid': p.pid,
                    'create_time': p.create_time(),
                    'nombre': nombre,
                    'memoria': memoria,
                    'memoria_mb': round(memoria / 1024 / 1024, 1),
                    'razon': razon,
                    'comando': comando[:240],
                })
            except (psutil.Error, OSError, ValueError):
                logger.debug("Skipping process detail %s because its metadata became unavailable", getattr(p, "pid", "?"), exc_info=True)
        salida.sort(key=lambda x: x['memoria'], reverse=True)
        return salida[:limite]

    def proteccion_memoria(self, aplicar=False):
        config = self.leer_config_local()
        proteccion = config.get('proteccion_memoria', {}) or {}
        estado = self.evaluar_presion_memoria()
        candidatos = self.candidatos_cierre_memoria() if estado['nivel'] in ('warning', 'critical') else []
        accion = 'ninguna'
        cerrados = []
        puede_cerrar = bool(
            aplicar
            and self._config_bool(proteccion.get('enabled'))
            and self._config_bool(proteccion.get('cerrar_candidatos'))
            and not self._config_bool(proteccion.get('dry_run', True), True)
            and estado['nivel'] == 'critical'
        )
        if puede_cerrar:
            for item in candidatos[:3]:
                try:
                    process = psutil.Process(int(item['pid']))
                    expected_time = float(item.get('create_time') or 0)
                    uids = process.uids()
                    name = process.name() or ''
                    command = ' '.join(process.cmdline() or [])
                    if uids.real != self.uid or process.pid == self.pid_actual or self._es_critico(name, command):
                        continue
                    if expected_time and process.create_time() != expected_time:
                        continue
                    process.send_signal(signal.SIGTERM)
                    cerrados.append(item)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, ValueError, TypeError):
                    continue
            accion = 'sigterm_conservador' if cerrados else 'sin_cierres'
        elif candidatos:
            accion = 'sugerir_cierre'
        resultado = {'estado': estado, 'candidatos': candidatos, 'accion': accion, 'cerrados': cerrados}
        if estado['nivel'] != 'normal':
            self.registrar_evento('memoria', estado['nivel'], 'Presion de memoria detectada', accion, resultado)
        return resultado

    def estado_bc250(self):
        return self.repo.estado_bc250()

    def aplicar_rango_bc250(self, minimo, maximo):
        return self.repo.aplicar_rango_bc250(minimo, maximo)

    def fijar_frecuencia_bc250(self, frecuencia):
        return self.repo.fijar_frecuencia_bc250(frecuencia)

    def estado_herramientas_bc250(self):
        return self.repo.estado_herramientas_bc250()

    def instalar_dependencias_bc250(self):
        return self.repo.instalar_dependencias_bc250()

    def instalar_governor(self):
        return self.repo.instalar_governor()

    def controlar_governor(self, accion):
        return self.repo.controlar_governor(accion)

    def status_governor(self):
        return self.repo.status_governor()

    def abrir_laboratorio_voltaje_gpu(self):
        return self.repo.abrir_laboratorio_voltaje_gpu()

    def aplicar_laboratorio_voltaje_gpu(self, nivel):
        return self.repo.aplicar_laboratorio_voltaje_gpu(nivel)

    def aplicar_laboratorio_voltaje_gpu_personalizado(self, valores):
        return self.repo.aplicar_laboratorio_voltaje_gpu_personalizado(valores)

    def instalar_cpu_oc(self):
        return self.repo.instalar_cpu_oc()

    def instalar_umr(self):
        return self.repo.instalar_umr()

    def ejecutar_cpu_oc_temporal(self, frecuencia, vid, temp=90):
        return self.repo.ejecutar_cpu_oc_temporal(frecuencia, vid, temp)

    def comando_cpu_oc_temporal_embebido(self, frecuencia, vid, temp=90):
        return self.repo.comando_cpu_oc_temporal_embebido(frecuencia, vid, temp)

    def comando_cpu_oc_persistente_embebido(self):
        return self.repo.comando_cpu_oc_persistente_embebido()

    def estado_cpu_oc_persistente(self):
        return self.repo.estado_cpu_oc_persistente()

    def comando_cpu_oc_desactivar_persistente_embebido(self):
        return self.repo.comando_cpu_oc_desactivar_persistente_embebido()

    def obtener_mapa_cu(self):
        return self.repo.obtener_mapa_cu()

    def obtener_dashboard_cu(self):
        return self.repo.obtener_dashboard_cu()

    def ejecutar_cu_manager(self, accion):
        return self.repo.ejecutar_cu_manager(accion)

    def estado_fans_bc250(self):
        return self.repo.estado_fans_bc250()

    def cargar_nct6683_solo_lectura(self):
        return self.repo.cargar_nct6683_solo_lectura()

    def preparar_nct6687_control_pwm(self):
        return self.repo.preparar_nct6687_control_pwm()

    def desactivar_nct6687_control_pwm(self):
        return self.repo.desactivar_nct6687_control_pwm()

    def aplicar_pwm_fan(self, pwm, valor):
        return self.repo.aplicar_pwm_fan(pwm, valor)

    def obtener_estado_cu_cache(self):
        return self.repo.obtener_estado_cu_cache()

    def obtener_estado_cu(self):
        return self.repo.obtener_estado_cu()

    def aplicar_tabla_cu(self, masks):
        return self.repo.aplicar_tabla_cu(masks)

    def ejecutar_accion_cu_grafica(self, accion):
        return self.repo.ejecutar_accion_cu_grafica(accion)

