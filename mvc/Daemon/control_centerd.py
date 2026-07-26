#!/usr/bin/python3
from pathlib import Path
import math
import shutil
import signal
import subprocess
import sys
import time

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from mvc.Repository.sistema_repository import SistemaRepository
from mvc.service.sistema_service import SistemaService


class BC250ControlCenterDaemon:
    def __init__(self):
        self.repo = SistemaRepository()
        self.servicio = SistemaService(self.repo)
        self.activo = True
        self.ultimo_fan_curve_apply = 0
        self.ultimo_fan_curve_percent = None
        self.ultimo_fan_curve_error = 0
        self.alerta_temp_estado = {}
        signal.signal(signal.SIGTERM, self.detener)
        signal.signal(signal.SIGINT, self.detener)

    def detener(self, *_args):
        self.activo = False

    @staticmethod
    def _safe_number(value, default, minimum, maximum, *, integer=False):
        try:
            parsed = int(value) if integer else float(value)
            if not integer and not math.isfinite(parsed):
                raise ValueError('non-finite number')
        except (TypeError, ValueError, OverflowError):
            parsed = int(default) if integer else float(default)
        parsed = max(minimum, min(maximum, parsed))
        return int(parsed) if integer else float(parsed)

    @staticmethod
    def _safe_bool(value, default=False):
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

    def notificar(self, titulo, mensaje, urgencia='normal'):
        if not shutil.which('notify-send'):
            return False
        try:
            subprocess.Popen(['notify-send', '-u', urgencia, titulo, mensaje])
            return True
        except Exception:
            return False

    def porcentaje_a_pwm(self, porcentaje):
        percent = self._safe_number(porcentaje, 0, 0, 100, integer=True)
        return max(0, min(255, round(percent * 255 / 100)))

    def fan_curve_percent_for_temp(self, temp, fan_config):
        puntos = [
            (self._safe_number(fan_config.get('t1'), 50, 0, 120, integer=True), self._safe_number(fan_config.get('s1'), 70, 0, 100, integer=True)),
            (self._safe_number(fan_config.get('t2'), 65, 0, 120, integer=True), self._safe_number(fan_config.get('s2'), 100, 0, 100, integer=True)),
            (self._safe_number(fan_config.get('t3'), 70, 0, 120, integer=True), self._safe_number(fan_config.get('s3'), 100, 0, 100, integer=True)),
        ]
        puntos.sort(key=lambda item: item[0])
        objetivo = puntos[0][1]
        for limite, velocidad in puntos:
            if temp >= limite:
                objetivo = velocidad
        return max(0, min(100, int(objetivo)))

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

    def aplicar_curva_fan_si_corresponde(self, metrica, config):
        fan_config = (config or {}).get('fan_curve') or {}
        if not self._safe_bool(fan_config.get('enabled', False)):
            return
        temp = metrica.get('gpu_temp')
        if temp is None:
            return
        try:
            temp = float(temp)
            if not math.isfinite(temp):
                return
        except (TypeError, ValueError, OverflowError):
            return
        ahora = time.monotonic()
        if ahora - self.ultimo_fan_curve_apply < 5:
            return
        porcentaje = self.fan_curve_percent_for_temp(temp, fan_config)
        if self.ultimo_fan_curve_percent == porcentaje:
            self.ultimo_fan_curve_apply = ahora
            return
        pwm = self._safe_number(fan_config.get('pwm'), 2, 1, 7, integer=True)
        valor = self.porcentaje_a_pwm(porcentaje)
        try:
            self.servicio.aplicar_pwm_fan(pwm, valor)
            self.ultimo_fan_curve_apply = ahora
            self.ultimo_fan_curve_percent = porcentaje
            self.servicio.registrar_evento(
                'fan', 'info', 'Fan curve daemon applied',
                f'GPU {temp:.1f} C -> PWM {pwm} {porcentaje}%',
                {'pwm': pwm, 'percent': porcentaje, 'raw': valor, 'gpu_temp': temp}
            )
        except Exception as error:
            if ahora - self.ultimo_fan_curve_error > 60:
                self.ultimo_fan_curve_error = ahora
                self.servicio.registrar_evento('fan', 'error', 'Fan curve daemon error', str(error), {'pwm': pwm})

    def ciclo(self):
        rendimiento = self.servicio.rendimiento()
        estado_bc250 = {}
        try:
            estado_bc250 = self.servicio.estado_bc250()
        except Exception as error:
            estado_bc250 = {'error': str(error)}

        metrica = {
            'cpu': rendimiento.get('cpu'),
            'cpu_temp': rendimiento.get('cpu_temp'),
            'gpu_temp': rendimiento.get('gpu_temp'),
            'gpu_busy': rendimiento.get('gpu_busy'),
            'gpu_power': rendimiento.get('gpu_power'),
            'memoria_porcentaje': rendimiento.get('memoria_porcentaje'),
            'swap_porcentaje': rendimiento.get('swap_porcentaje'),
            'bc250': {
                'service_active': estado_bc250.get('service_active'),
                'dbus_ok': estado_bc250.get('dbus_ok'),
                'current_min': estado_bc250.get('current_min'),
                'current_max': estado_bc250.get('current_max'),
                'sclk_actual': estado_bc250.get('sclk_actual'),
            }
        }
        self.servicio.registrar_metrica_runtime(metrica)

        config = self.servicio.leer_config_local()
        self.aplicar_curva_fan_si_corresponde(metrica, config)
        alertas = self._safe_bool(config.get('alertas_activas', False))
        gpu_temp_warning = self._safe_number(config.get('gpu_temp_warning'), 82, 30, 120)
        cpu_temp_warning = self._safe_number(config.get('cpu_temp_warning'), 88, 30, 120)

        if alertas and rendimiento.get('gpu_temp') and self.debe_notificar_temperatura('gpu', rendimiento.get('gpu_temp'), gpu_temp_warning):
            self.servicio.registrar_evento('temperatura', 'warning', 'GPU caliente', f"{rendimiento.get('gpu_temp'):.1f} C", metrica)
            self.notificar('BC250 Control Center: GPU caliente', f"GPU {rendimiento.get('gpu_temp'):.1f} C", 'critical')

        if alertas and rendimiento.get('cpu_temp') and self.debe_notificar_temperatura('cpu', rendimiento.get('cpu_temp'), cpu_temp_warning):
            self.servicio.registrar_evento('temperatura', 'warning', 'CPU caliente', f"{rendimiento.get('cpu_temp'):.1f} C", metrica)
            self.notificar('BC250 Control Center: CPU caliente', f"CPU {rendimiento.get('cpu_temp'):.1f} C", 'critical')

        presion = self.servicio.proteccion_memoria(aplicar=True)
        if alertas and presion['estado']['nivel'] == 'critical':
            self.notificar('BC250 Control Center: RAM critica', 'Presion alta de memoria detectada. Revisa Historial/Procesos.', 'critical')

        if alertas and estado_bc250 and estado_bc250.get('service_active') not in ('active', '', None):
            self.servicio.registrar_evento('governor', 'warning', 'Governor no activo', str(estado_bc250.get('service_active')), estado_bc250)

    def run(self):
        self.servicio.registrar_evento('daemon', 'info', 'bc250-control-centerd iniciado', 'Monitor conservador activo')
        while self.activo:
            inicio = time.monotonic()
            try:
                self.ciclo()
            except Exception as error:
                self.servicio.registrar_evento('daemon', 'error', 'Error en daemon', str(error))
            config = self.servicio.leer_config_local()
            intervalo = self._safe_number(config.get('daemon_interval_seconds'), 2, 1, 3600, integer=True)
            restante = intervalo - (time.monotonic() - inicio)
            time.sleep(max(0.5, restante))
        self.servicio.registrar_evento('daemon', 'info', 'bc250-control-centerd detenido', 'Monitor apagado')


if __name__ == '__main__':
    BC250ControlCenterDaemon().run()
