import logging
import os
import signal
import stat
import subprocess
from pathlib import Path

import psutil

from bc250cc.application.system.process_termination_policy import (
    ProcessIdentity,
    authorize_process_termination,
)
from bc250cc.domain.common.proceso import Proceso
from bc250cc.domain.common.rendimiento import Rendimiento
from bc250cc.infrastructure.polkit_session import normalize_polkit_error, pkexec_argv
from bc250cc.shared.failure_text import describe_failure

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
    'bc250-control-center'
]

OCULTOS = CRITICOS + [
    'baloo_file', 'baloorunner', 'kdeconnectd', 'agent', 'ssh-agent', 'gpg-agent',
    'tracker', 'tracker-miner', 'localsearch', 'gnome-software', 'evolution-source-registry',
    'evolution-calendar-factory', 'evolution-addressbook-factory', 'goa-daemon'
]

class SistemaService:
    def __init__(self, repo, *, activity_service=None, settings_service=None):
        self.repo = repo
        self.activity_service = activity_service
        self.settings_service = settings_service
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

    def estado_bc250_daemon(self):
        return self.repo.estado_bc250_daemon()

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
                identity = self._process_identity(process)
                decision = authorize_process_termination(
                    identity,
                    expected_create_time=expected_time,
                    owner_uid=self.uid,
                    controller_pid=self.pid_actual,
                    critical=bool(self._es_critico(identity.name, identity.command)),
                )
                if not decision.allowed:
                    continue
                process.send_signal(signal.SIGTERM)
                pendientes.append((process, identity.create_time))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError, ValueError, TypeError, OverflowError):
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
                if not process.is_running():
                    continue
                identity = self._process_identity(process)
                decision = authorize_process_termination(
                    identity,
                    expected_create_time=create_time,
                    owner_uid=self.uid,
                    controller_pid=self.pid_actual,
                    critical=bool(self._es_critico(identity.name, identity.command)),
                )
                if decision.allowed:
                    process.kill()
                    force_closed.append(process.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError, ValueError, TypeError, OverflowError):
                continue
        return force_closed

    @staticmethod
    def _process_identity(process) -> ProcessIdentity:
        uids = process.uids()
        return ProcessIdentity(
            pid=int(process.pid),
            create_time=float(process.create_time()),
            uid=int(uids.real),
            name=process.name() or '',
            command=' '.join(process.cmdline() or []),
        )

    def limpiar_cache(self):
        """Run the fixed privileged cache workflow and report its real result."""
        helper = Path("/usr/libexec/bc250-control-center/bc250-maintenance-helper")
        try:
            metadata = helper.stat(follow_symlinks=False)
        except OSError as error:
            raise RuntimeError(
                "The protected maintenance helper is missing. Reinstall Control Center."
            ) from error
        if (
            helper.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_mode & 0o022
            or not metadata.st_mode & stat.S_IXUSR
        ):
            raise RuntimeError("The protected maintenance helper has unsafe permissions.")
        command = pkexec_argv("pkexec", str(helper), "drop-caches")
        try:
            result = subprocess.run(
                command,
                text=True,
                capture_output=True,
                timeout=120,
                check=False,
            )
        except FileNotFoundError as error:
            raise RuntimeError('pkexec is not available on this system.') from error
        except subprocess.TimeoutExpired as error:
            raise RuntimeError('The privileged cache operation timed out.') from error
        output = (result.stdout or normalize_polkit_error(command, result.stderr) or '').strip()
        if result.returncode != 0:
            raise RuntimeError(describe_failure(result.returncode, output, ''))
        return {'returncode': result.returncode, 'output': output}

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
        if self.settings_service is None:
            raise RuntimeError("SistemaService requires a settings service for memory policy")
        config = self.settings_service.read_local_config()
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
        if self.settings_service is None:
            raise RuntimeError("SistemaService requires a settings service for memory protection")
        config = self.settings_service.read_local_config()
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
        if estado['nivel'] != 'normal' and self.activity_service is not None:
            self.activity_service.record(
                'memoria', estado['nivel'], 'Presion de memoria detectada', accion, resultado
            )
        return resultado

    def estado_bc250(self):
        return self.repo.estado_bc250()

    def aplicar_rango_bc250(self, minimo, maximo):
        return self.repo.aplicar_rango_bc250(minimo, maximo)

    def guardar_rango_gpu_arranque(self):
        return self.repo.guardar_rango_gpu_arranque()

    def fijar_frecuencia_bc250(self, frecuencia):
        return self.repo.fijar_frecuencia_bc250(frecuencia)

    def estado_herramientas_bc250(self):
        return self.repo.estado_herramientas_bc250()

    def instalar_dependencias_bc250(
        self,
        confirmar_conflictos=False,
        desactivar_conflictos=False,
        governor_preference=None,
        include_pwm=False,
        components=None,
    ):
        return self.repo.instalar_dependencias_bc250(
            confirmar_conflictos, desactivar_conflictos, governor_preference, include_pwm, components
        )

    def preparar_memoria_bazzite(self, policy: str, ttm_gib: int):
        return self.repo.preparar_memoria_bazzite(policy, ttm_gib)

    def preparar_memoria(self, policy: str, ttm_gib: int):
        return self.repo.preparar_memoria(policy, ttm_gib)

    def preparar_vram(self, uma_size_mb: int):
        return self.repo.preparar_vram(uma_size_mb)

    def gestionar_mitigaciones_bazzite(self, action: str):
        return self.repo.gestionar_mitigaciones_bazzite(action)

    def gestionar_acpi(self, action: str):
        return self.repo.gestionar_acpi(action)

    def reparar_telemetria_8core(self, action: str = "telemetry-fix"):
        return self.repo.reparar_telemetria_8core(action)

    def preparar_compatibilidad_steamos(self):
        return self.repo.preparar_compatibilidad_steamos()

    def gestionar_graficos_steamos(self, action):
        return self.repo.gestionar_graficos_steamos(action)

    def diagnostico_steamos(self):
        return self.repo.diagnostico_steamos()

    def preparar_quick_access_steamos(self, *, install_decky: bool):
        return self.repo.preparar_quick_access_steamos(install_decky=install_decky)

    def driver_inventory(self):
        return self.repo.driver_inventory()

    def install_driver_support(self, component):
        return self.repo.install_driver_support(component)

    def preparar_kernel_cachyos_bc250(self):
        return self.repo.preparar_kernel_cachyos_bc250()

    def preparar_cachyos_bc250(self, action):
        return self.repo.preparar_cachyos_bc250(action)

    def gestionar_fsr4_bc250(self, action):
        return self.repo.gestionar_fsr4_bc250(action)

    def gestionar_gfx1013_fedora(self, action):
        return self.repo.gestionar_gfx1013_fedora(action)

    def gestionar_gfx1013_bazzite(self, action):
        return self.repo.gestionar_gfx1013_bazzite(action)

    def actualizar_aplicacion_local(self):
        return self.repo.actualizar_aplicacion_local()

    def health_check(self):
        return self.repo.health_check()

    def repair_installation(self):
        return self.repo.repair_installation()

    def generate_diagnostic_report(self):
        return self.repo.generate_diagnostic_report()

    def recovery_inventory(self, limit=50):
        return self.repo.recovery_inventory(limit)

    def create_recovery_snapshot(self, label="manual-before-change"):
        return self.repo.create_recovery_snapshot(label)

    def recovery_plan(self, snapshot_id):
        return self.repo.recovery_plan(snapshot_id)

    def export_recovery_snapshot(self, snapshot_id, destination):
        return self.repo.export_recovery_snapshot(snapshot_id, destination)

    def detectar_gobernadores_gpu_incompatibles(self):
        return self.repo.detectar_gobernadores_gpu_incompatibles()

    def instalar_governor(
        self,
        confirmar_conflictos=False,
        desactivar_conflictos=False,
        governor_preference=None,
    ):
        return self.repo.instalar_governor(
            confirmar_conflictos, desactivar_conflictos, governor_preference
        )

    def cambiar_governor(self, governor):
        return self.repo.cambiar_governor(governor)

    def desinstalar_governor(self, governor):
        return self.repo.desinstalar_governor(governor)

    def controlar_governor(self, accion, confirmar_conflictos=False, desactivar_conflictos=False):
        return self.repo.controlar_governor(accion, confirmar_conflictos, desactivar_conflictos)

    def status_governor(self):
        return self.repo.status_governor()

    def abrir_laboratorio_voltaje_gpu(self):
        return self.repo.abrir_laboratorio_voltaje_gpu()

    def aplicar_laboratorio_voltaje_gpu(self, nivel):
        return self.repo.aplicar_laboratorio_voltaje_gpu(nivel)

    def aplicar_laboratorio_voltaje_gpu_personalizado(self, valores):
        return self.repo.aplicar_laboratorio_voltaje_gpu_personalizado(valores)

    def aplicar_perfil_gpu(self, minimo, maximo):
        return self.repo.aplicar_perfil_gpu(minimo, maximo)

    def fijar_piso_gpu_persistente(self, minimo):
        return self.repo.fijar_piso_gpu_persistente(minimo)

    def alternar_puntos_gpu_altos(self, enabled):
        return self.repo.alternar_puntos_gpu_altos(enabled)

    def configurar_compatibilidad_gpu_cyan(
        self, set_method, usage_method, fix_metrics, fix_frequency
    ):
        return self.repo.configurar_compatibilidad_gpu_cyan(
            set_method, usage_method, fix_metrics, fix_frequency
        )

    def instalar_cpu_oc(self):
        return self.repo.instalar_cpu_oc()

    def instalar_core_unlock(self):
        return self.repo.instalar_core_unlock()

    def instalar_umr(self):
        return self.repo.instalar_umr()

    def ejecutar_cpu_oc_temporal(self, frecuencia, vid, temp=90):
        return self.repo.ejecutar_cpu_oc_temporal(frecuencia, vid, temp)

    def comando_cpu_oc_temporal_embebido(self, frecuencia, vid, temp=90):
        return self.repo.comando_cpu_oc_temporal_embebido(frecuencia, vid, temp)

    def registrar_resultado_deteccion_cpu(self, target=None):
        return self.repo.registrar_resultado_deteccion_cpu(target)

    def estado_resultado_deteccion_cpu(self):
        return self.repo.estado_resultado_deteccion_cpu()

    def evaluar_override_escala_cpu(self, scale_override, frequency_override=None):
        return self.repo.evaluar_override_escala_cpu(scale_override, frequency_override)

    def evaluar_aplicacion_manual_cpu(self, frequency, scale, temperature=90):
        return self.repo.evaluar_aplicacion_manual_cpu(frequency, scale, temperature)

    def comando_cpu_scale_live_embebido(self, scale_override, confirm_scale_jump=False, frequency_override=None, temperature_override=None):
        return self.repo.comando_cpu_scale_live_embebido(scale_override, confirm_scale_jump, frequency_override, temperature_override)

    def registrar_prueba_escala_cpu(self, scale_override, frequency_override=None, temperature_override=None):
        return self.repo.registrar_prueba_escala_cpu(scale_override, frequency_override, temperature_override)

    def comando_cpu_oc_manual_embebido(self, frequency, scale, temperature=90, confirm_manual=False):
        return self.repo.comando_cpu_oc_manual_embebido(
            frequency, scale, temperature, confirm_manual
        )

    def registrar_aplicacion_manual_cpu(self, frequency, scale, temperature=90):
        return self.repo.registrar_aplicacion_manual_cpu(frequency, scale, temperature)

    def estado_prueba_escala_cpu(self, scale_override=None, frequency_override=None, temperature_override=None):
        return self.repo.estado_prueba_escala_cpu(scale_override, frequency_override, temperature_override)

    def preparar_evidencia_persistencia_escala_cpu(self, scale_override, frequency_override, temperature_override):
        return self.repo.preparar_evidencia_persistencia_escala_cpu(
            scale_override, frequency_override, temperature_override
        )

    def estado_cpu_qam_runtime(self):
        return self.repo.estado_cpu_qam_runtime()

    def comando_cpu_oc_persistente_embebido(self, scale_override=None, confirm_scale_jump=False, frequency_override=None, temperature_override=None):
        return self.repo.comando_cpu_oc_persistente_embebido(scale_override, confirm_scale_jump, frequency_override, temperature_override)

    def estado_cpu_oc_persistente(self):
        return self.repo.estado_cpu_oc_persistente()

    def comando_cpu_oc_desactivar_persistente_embebido(self):
        return self.repo.comando_cpu_oc_desactivar_persistente_embebido()

    def estado_desbloqueo_nucleos_cpu(self):
        return self.repo.estado_desbloqueo_nucleos_cpu()

    def comando_desbloquear_nucleos_cpu(self):
        return self.repo.comando_desbloquear_nucleos_cpu()

    def estado_gddr6_memory_temp(self):
        return self.repo.estado_gddr6_memory_temp()

    def comando_preparar_gddr6_memory_temp(self):
        return self.repo.comando_preparar_gddr6_memory_temp()

    def comando_estado_smu_vram(self):
        return self.repo.comando_estado_smu_vram()

    def comando_leer_temperatura_vram(self):
        return self.repo.comando_leer_temperatura_vram()

    def leer_temperatura_vram(self, *, chips=True):
        return self.repo.leer_temperatura_vram(chips=chips)

    def ultima_temperatura_vram(self):
        return self.repo.ultima_temperatura_vram()

    def comando_monitorizar_vram(self, seconds=None):
        if seconds is None:
            return self.repo.comando_monitorizar_vram()
        return self.repo.comando_monitorizar_vram(seconds)

    def comando_aplicar_parche_vram(self):
        return self.repo.comando_aplicar_parche_vram()

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

    def restaurar_pwm_automatico(self, pwm):
        return self.repo.restaurar_pwm_automatico(pwm)

    def leer_pwm_fan(self, pwm):
        return self.repo.leer_pwm_fan(pwm)

    def obtener_estado_cu_cache(self):
        return self.repo.obtener_estado_cu_cache()

    def obtener_estado_cu(self):
        return self.repo.obtener_estado_cu()

    def aplicar_tabla_cu(self, masks):
        return self.repo.aplicar_tabla_cu(masks)

    def guardar_tabla_cu(self, masks):
        return self.repo.guardar_tabla_cu(masks)

    def ejecutar_accion_cu_grafica(self, accion):
        return self.repo.ejecutar_accion_cu_grafica(accion)
