#!/usr/bin/python3
import fcntl
import json
import os
import signal
import tempfile
import threading
import time
from contextlib import suppress
from pathlib import Path

from bc250cc.application.system.activity_service import ActivityService
from bc250cc.application.system.daemon_policy import (
    build_runtime_metric,
    governor_warning_needed,
    plan_daemon_cycle,
    safe_bool,
    safe_number,
)
from bc250cc.application.system.settings_service import SettingsService
from bc250cc.domain.fan.persistence import (
    FanControlMemory,
    fan_curve_percent_for_temp,
    plan_persistent_fan,
)
from bc250cc.infrastructure.persistence.activity_journal import activity_journal
from bc250cc.infrastructure.persistence.profile_bundle import ProfileBundleRepository
from bc250cc.infrastructure.sistema_repository import SistemaRepository
from bc250cc.infrastructure.system_service import SistemaService


class BC250ControlCenterDaemon:
    def __init__(self):
        self.repo = SistemaRepository()
        self.activity_service = ActivityService(lambda: activity_journal(self.repo.configuracion))
        self.settings_service = SettingsService(
            self.repo.configuracion,
            ProfileBundleRepository(self.repo.configuracion),
            history_path=lambda: activity_journal(self.repo.configuracion).archivo,
            recovery_root=self.repo._recovery_snapshot_root,
        )
        self.servicio = SistemaService(
            self.repo,
            activity_service=self.activity_service,
            settings_service=self.settings_service,
        )
        self.activo = True
        self.ultimo_fan_curve_apply = 0
        self.ultimo_fan_curve_percent = None
        self.ultimo_fan_target = None
        self.ultimo_fan_verify = 0
        self.ultimo_fan_sensor_path = ''
        self.ultimo_fan_curve_error = 0
        self.fan_temp_missing_since = None
        self.ultima_fan_temperature = None
        self.ultimo_metrics_write = 0
        self.ultimo_governor_read = 0
        self.ultimo_memory_check = 0
        self.estado_bc250_cache = {}
        self._stop_event = threading.Event()
        self._lock_file = None
        self._health_enabled = True
        self._last_health_write = 0
        self.alerta_temp_estado = {}
        signal.signal(signal.SIGTERM, self.detener)
        signal.signal(signal.SIGINT, self.detener)

    def detener(self, *_args):
        self.activo = False
        stop_event = getattr(self, '_stop_event', None)
        if stop_event is not None:
            stop_event.set()

    @staticmethod
    def _state_dir():
        configured = os.environ.get('XDG_STATE_HOME', '').strip()
        return Path(configured) if configured else Path.home() / '.local' / 'state'

    def _health_path(self):
        return self._state_dir() / 'bc250-control-center' / 'daemon-health.json'

    def _write_health(self, **updates):
        """Publish a small atomic status file for diagnostics without privileges."""
        if not getattr(self, '_health_enabled', False):
            return False
        path = self._health_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            current = getattr(self, '_health', {})
            current.update(updates)
            current['updated_at'] = int(time.time())
            self._health = current
            fd, temporary = tempfile.mkstemp(prefix='.daemon-health-', dir=path.parent)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                    json.dump(current, stream, ensure_ascii=False, indent=2, sort_keys=True)
                    stream.write('\n')
                    stream.flush()
                    os.fsync(stream.fileno())
                os.chmod(temporary, 0o600)
                os.replace(temporary, path)
                self._last_health_write = time.monotonic()
            finally:
                with suppress(FileNotFoundError):
                    os.unlink(temporary)
        except OSError:
            # Health reporting must never stop thermal control.
            return False
        return True

    def _acquire_singleton_lock(self):
        runtime = os.environ.get('XDG_RUNTIME_DIR', '').strip()
        base = Path(runtime) if runtime else self._state_dir() / 'bc250-control-center'
        base.mkdir(parents=True, exist_ok=True)
        path = base / 'bc250-control-centerd.lock'
        lock_file = path.open('a+', encoding='utf-8')
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock_file.close()
            raise RuntimeError(
                'Another BC250 Control Center daemon instance is already running.'
            ) from None
        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(f'{os.getpid()}\n')
        lock_file.flush()
        self._lock_file = lock_file

    @staticmethod
    def _safe_number(value, default, minimum, maximum, *, integer=False):
        return safe_number(
            value, default, minimum, maximum, integer=integer
        )

    @staticmethod
    def _safe_bool(value, default=False):
        return safe_bool(value, default)

    def notificar(self, titulo, mensaje, urgencia='normal'):
        # Retained as a compatibility entry point, but desktop notifications
        # are currently disabled globally.  Do not invoke notify-send even if
        # stale user configuration requests alerts.
        del titulo, mensaje, urgencia
        return False

    def porcentaje_a_pwm(self, porcentaje):
        percent = self._safe_number(porcentaje, 0, 0, 100, integer=True)
        return max(0, min(255, round(percent * 255 / 100)))

    def fan_curve_percent_for_temp(self, temp, fan_config):
        result = fan_curve_percent_for_temp(temp, fan_config)
        return 0 if result is None else result

    def debe_notificar_temperatura(self, clave, temp, limite):
        if temp is None:
            return False
        try:
            temp = float(temp)
        except Exception:
            return False
        estado = self.alerta_temp_estado.setdefault(clave, {
            'activo': False,
            'temp': None,
            'cambios': 0,
        })
        if temp < limite:
            estado['activo'] = False
            estado['temp'] = None
            estado['cambios'] = 0
            return False
        temp_redondeada = round(temp, 1)
        if not estado['activo']:
            estado['activo'] = True
            estado['temp'] = temp_redondeada
            estado['cambios'] = 0
            return True
        if estado['temp'] != temp_redondeada:
            estado['temp'] = temp_redondeada
            estado['cambios'] += 1
        if estado['cambios'] >= 30:
            estado['cambios'] = 0
            return True
        return False

    def _fan_control_memory(self):
        return FanControlMemory(
            last_apply=getattr(self, 'ultimo_fan_curve_apply', 0),
            last_percent=getattr(self, 'ultimo_fan_curve_percent', None),
            last_target=getattr(self, 'ultimo_fan_target', None),
            last_verify=getattr(self, 'ultimo_fan_verify', 0),
            missing_since=getattr(self, 'fan_temp_missing_since', None),
            last_temperature=getattr(self, 'ultima_fan_temperature', None),
        )

    def _fan_readback_matches(self, decision, target, ahora):
        if decision.action != 'verify':
            return False, None
        reader = getattr(self.servicio, 'leer_pwm_fan', None)
        if not callable(reader):
            return False, None
        confirmed = reader(target.pwm)
        self.ultimo_fan_verify = ahora
        previous_path = getattr(self, 'ultimo_fan_sensor_path', '')
        same_value = int(confirmed.get('value', -1)) == target.raw
        same_path = not previous_path or confirmed.get('sensor_path') == previous_path
        if not (same_value and same_path):
            return False, confirmed
        self.ultimo_fan_curve_apply = ahora
        self._write_health(
            status='healthy', fan_pwm=target.pwm, fan_percent=target.percent,
            fan_raw=target.raw, fan_sensor_path=confirmed.get('sensor_path', ''),
            fan_source=target.source, fan_error='',
        )
        return True, confirmed

    def _fan_confirm_after_write(self, target, result, prior_confirmed):
        confirmed = prior_confirmed
        verification_error = ''
        if isinstance(result, dict):
            confirmed = result.get('verified')
            verification_error = str(result.get('verification_error') or '')
        if not isinstance(confirmed, dict):
            reader = getattr(self.servicio, 'leer_pwm_fan', None)
            if callable(reader):
                try:
                    confirmed = reader(target.pwm)
                except RuntimeError as error:
                    verification_error = verification_error or str(error)
        if isinstance(confirmed, dict) and int(confirmed.get('value', -1)) != target.raw:
            raise RuntimeError('PWM verification did not match the requested value.')
        return confirmed, verification_error

    def _record_fan_apply(self, target, confirmed, verification_error, ahora):
        self.ultimo_fan_curve_apply = ahora
        self.ultimo_fan_curve_percent = target.percent
        self.ultimo_fan_target = target.identity
        self.ultimo_fan_verify = ahora
        self.ultima_fan_temperature = target.temperature
        self.ultimo_fan_sensor_path = (
            confirmed.get('sensor_path', '') if isinstance(confirmed, dict) else ''
        )
        self._write_health(
            status='warning' if verification_error else 'healthy',
            fan_pwm=target.pwm, fan_percent=target.percent, fan_raw=target.raw,
            fan_sensor_path=self.ultimo_fan_sensor_path,
            fan_temperature=target.temperature, fan_source=target.source,
            fan_error=verification_error,
        )
        detail = (
            f'GPU {float(target.temperature):.1f} C -> PWM {target.pwm} {target.percent}%'
            if target.curve_enabled and target.temperature is not None
            else f'PWM {target.pwm} {target.percent}% ({target.source})'
        )
        self.activity_service.record(
            'fan', 'info', 'Persistent fan setting applied', detail,
            {
                'pwm': target.pwm, 'percent': target.percent, 'raw': target.raw,
                'gpu_temp': target.temperature, 'source': target.source,
            },
        )

    def _record_fan_error(self, target, error, ahora):
        self._write_health(
            status='error', fan_pwm=target.pwm, fan_percent=target.percent,
            fan_error=str(error),
        )
        if ahora - getattr(self, 'ultimo_fan_curve_error', 0) > 60:
            self.ultimo_fan_curve_error = ahora
            self.activity_service.record(
                'fan', 'error', 'Fan curve daemon error', str(error),
                {'pwm': target.pwm},
            )

    def _execute_fan_decision(self, decision, ahora):
        target = decision.target
        if target is None:
            return
        try:
            matched, confirmed = self._fan_readback_matches(decision, target, ahora)
            if matched:
                return
            result = self.servicio.aplicar_pwm_fan(target.pwm, target.raw)
            confirmed, error = self._fan_confirm_after_write(target, result, confirmed)
            self._record_fan_apply(target, confirmed, error, ahora)
        except Exception as error:
            self._record_fan_error(target, error, ahora)

    def aplicar_ventilador_persistente_si_corresponde(self, metrica, config):
        ahora = time.monotonic()
        decision = plan_persistent_fan(
            metrica, config, self._fan_control_memory(), now=ahora
        )
        self.fan_temp_missing_since = decision.missing_since
        if decision.action == 'sensor-missing':
            self._write_health(status='warning', fan_error=decision.reason)
        elif decision.action == 'skip':
            self.ultimo_fan_curve_apply = ahora
        elif decision.action in {'verify', 'apply'}:
            self._execute_fan_decision(decision, ahora)
    def aplicar_curva_fan_si_corresponde(self, metrica, config):
        """Backward-compatible entry point for older callers/tests."""
        return self.aplicar_ventilador_persistente_si_corresponde(metrica, config)

    def _governor_state_for_cycle(self, plan, ahora):
        state = getattr(self, 'estado_bc250_cache', {})
        if not plan.governor_due:
            return state
        try:
            reader = getattr(self.servicio, 'estado_bc250_daemon', None)
            state = reader() if callable(reader) else self.servicio.estado_bc250()
        except Exception as error:
            state = {'error': str(error)}
        self.estado_bc250_cache = state
        self.ultimo_governor_read = ahora
        return state

    def _process_temperature_alerts(self, performance, metric, plan):
        alerts = (
            (
                'gpu', performance.get('gpu_temp'), plan.gpu_temp_warning,
                'GPU caliente', 'BC250 Control Center: GPU caliente',
            ),
            (
                'cpu', performance.get('cpu_temp'), plan.cpu_temp_warning,
                'CPU caliente', 'BC250 Control Center: CPU caliente',
            ),
        )
        if not plan.alerts_enabled:
            return
        for key, temperature, limit, event_title, notification_title in alerts:
            if not temperature or not self.debe_notificar_temperatura(
                key, temperature, limit
            ):
                continue
            detail = f'{float(temperature):.1f} C'
            self.activity_service.record(
                'temperatura', 'warning', event_title, detail, metric
            )
            self.notificar(
                notification_title,
                f'{key.upper()} {detail}',
                'critical',
            )

    def _process_memory_guard(self, plan, ahora):
        if not plan.memory_due:
            return
        pressure = self.servicio.proteccion_memoria(aplicar=True)
        self.ultimo_memory_check = ahora
        if plan.alerts_enabled and pressure['estado']['nivel'] == 'critical':
            self.notificar(
                'BC250 Control Center: RAM critica',
                'Presion alta de memoria detectada. Revisa Historial/Procesos.',
                'critical',
            )

    def ciclo(self):
        rendimiento = self.servicio.rendimiento()
        ahora = time.monotonic()
        config = self.settings_service.read_local_config()
        plan = plan_daemon_cycle(
            config,
            now=ahora,
            last_governor=getattr(self, 'ultimo_governor_read', 0),
            last_metrics=getattr(self, 'ultimo_metrics_write', 0),
            last_memory=getattr(self, 'ultimo_memory_check', 0),
            last_health=getattr(self, '_last_health_write', 0),
        )
        estado_bc250 = self._governor_state_for_cycle(plan, ahora)
        metrica = build_runtime_metric(rendimiento, estado_bc250)
        if plan.metrics_due:
            self.settings_service.record_runtime_metric(metrica)
            self.ultimo_metrics_write = ahora

        self.aplicar_ventilador_persistente_si_corresponde(metrica, config)
        self._process_temperature_alerts(rendimiento, metrica, plan)
        self._process_memory_guard(plan, ahora)
        if governor_warning_needed(plan.alerts_enabled, estado_bc250):
            self.activity_service.record('governor', 'warning', 'Governor no activo', str(estado_bc250.get('service_active')), estado_bc250)
        if plan.health_due:
            self._write_health(status='healthy', last_cycle=int(time.time()), last_error='')

    def run(self):
        self._acquire_singleton_lock()
        self.activity_service.record('daemon', 'info', 'bc250-control-centerd iniciado', 'Monitor conservador activo')
        while self.activo:
            inicio = time.monotonic()
            try:
                self.ciclo()
            except Exception as error:
                self.activity_service.record('daemon', 'error', 'Error en daemon', str(error))
            config = self.settings_service.read_local_config()
            intervalo = self._safe_number(config.get('daemon_interval_seconds'), 2, 1, 3600, integer=True)
            restante = intervalo - (time.monotonic() - inicio)
            stop_event = getattr(self, '_stop_event', None)
            if stop_event is not None:
                stop_event.wait(max(0.5, restante))
            else:  # compatibility with tests constructing the daemon without __init__
                time.sleep(max(0.5, restante))
        self.activity_service.record('daemon', 'info', 'bc250-control-centerd detenido', 'Monitor apagado')


if __name__ == '__main__':
    BC250ControlCenterDaemon().run()
