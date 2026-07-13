#!/usr/bin/python3
from pathlib import Path
import os
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
        signal.signal(signal.SIGTERM, self.detener)
        signal.signal(signal.SIGINT, self.detener)

    def detener(self, *_args):
        self.activo = False

    def notificar(self, titulo, mensaje, urgencia='normal'):
        if not shutil.which('notify-send'):
            return False
        try:
            subprocess.Popen(['notify-send', '-u', urgencia, titulo, mensaje])
            return True
        except Exception:
            return False

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
        alertas = bool(config.get('alertas_activas', False))
        gpu_temp_warning = float(config.get('gpu_temp_warning', 82))
        cpu_temp_warning = float(config.get('cpu_temp_warning', 88))

        if alertas and rendimiento.get('gpu_temp') and rendimiento.get('gpu_temp') >= gpu_temp_warning:
            self.servicio.registrar_evento('temperatura', 'warning', 'GPU caliente', f"{rendimiento.get('gpu_temp'):.1f} C", metrica)
            self.notificar('BC250 Control Center: GPU caliente', f"GPU {rendimiento.get('gpu_temp'):.1f} C", 'critical')

        if alertas and rendimiento.get('cpu_temp') and rendimiento.get('cpu_temp') >= cpu_temp_warning:
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
            intervalo = max(1, int(config.get('daemon_interval_seconds', 2)))
            restante = intervalo - (time.monotonic() - inicio)
            time.sleep(max(0.5, restante))
        self.servicio.registrar_evento('daemon', 'info', 'bc250-control-centerd detenido', 'Monitor apagado')


if __name__ == '__main__':
    BC250ControlCenterDaemon().run()
