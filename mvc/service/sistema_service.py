import os
import signal
import subprocess
import time
import psutil
try:
    from mvc.Model.proceso import Proceso
    from mvc.Model.rendimiento import Rendimiento
except Exception:
    from Model.proceso import Proceso
    from Model.rendimiento import Rendimiento

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
                lista.append(Proceso(p.pid, nombre, memoria, comando, protegido, razon))
            except Exception:
                pass

        lista.sort(key=lambda x: x.memoria, reverse=True)
        return lista

    def cerrar_procesos(self, procesos):
        for proceso in procesos:
            if proceso.protegido:
                continue
            try:
                os.kill(proceso.pid, signal.SIGTERM)
            except Exception:
                pass

        time.sleep(1.5)

        for proceso in procesos:
            if proceso.protegido:
                continue
            try:
                p = psutil.Process(proceso.pid)
                if p.is_running():
                    p.kill()
            except Exception:
                pass

    def limpiar_cache(self):
        subprocess.Popen(['pkexec', 'sh', '-c', 'sync; echo 3 > /proc/sys/vm/drop_caches'])


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
            except Exception:
                pass
        candidatos.sort(key=lambda x: x['memoria'], reverse=True)
        return candidatos[:8]

    def evaluar_presion_memoria(self):
        config = self.leer_config_local()
        memoria = psutil.virtual_memory()
        swap = psutil.swap_memory()
        warning = int(config.get('ram_warning_percent', 82))
        critical = int(config.get('ram_critical_percent', 92))
        swap_warning = int(config.get('swap_warning_percent', 35))
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
                    'nombre': nombre,
                    'memoria': memoria,
                    'memoria_mb': round(memoria / 1024 / 1024, 1),
                    'razon': razon,
                    'comando': comando[:240],
                })
            except Exception:
                pass
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
            and proteccion.get('enabled')
            and proteccion.get('cerrar_candidatos')
            and not proteccion.get('dry_run', True)
            and estado['nivel'] == 'critical'
        )
        if puede_cerrar:
            for item in candidatos[:3]:
                try:
                    os.kill(item['pid'], signal.SIGTERM)
                    cerrados.append(item)
                except Exception:
                    pass
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
