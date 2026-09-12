from __future__ import annotations

import csv
import fcntl
import json
import logging
import math
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

from bc250cc.domain.fan.persistence import normalize_fan_curve, normalize_fan_preset

from .config_paths import (
    APP_ID,
    app_cache_dir,
    app_config_dir,
    app_data_dir,
    xdg_cache_home,
    xdg_config_home,
    xdg_data_home,
)

logger = logging.getLogger(__name__)


class ConfiguracionLocal:
    app_id = APP_ID
    legacy_app_id = 'modo-juego-ram'
    _metric_record_max_bytes = 64 * 1024
    _metric_scan_max_bytes = 32 * 1024 * 1024

    def config_dir(self):
        return app_config_dir()

    def data_dir(self):
        return app_data_dir()

    def cache_dir(self):
        return app_cache_dir()

    def legacy_config_dir(self):
        return xdg_config_home() / self.legacy_app_id

    def legacy_data_dir(self):
        return xdg_data_home() / self.legacy_app_id

    def legacy_cache_dir(self):
        return xdg_cache_home() / self.legacy_app_id

    @contextmanager
    def _file_lock(self, target, *, exclusive=True):
        """Serialize GUI/daemon access without changing the public file format."""
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        lock_path = target.with_name(target.name + '.lock')
        with lock_path.open('a+', encoding='utf-8') as lock_file:
            mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            fcntl.flock(lock_file.fileno(), mode)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def migrar_legacy_si_existe(self):
        pares = [
            (self.legacy_config_dir(), self.config_dir()),
            (self.legacy_data_dir(), self.data_dir()),
            (self.legacy_cache_dir(), self.cache_dir()),
        ]
        for origen, destino in pares:
            if not origen.exists():
                continue
            destino.mkdir(parents=True, exist_ok=True)
            for item in origen.iterdir():
                objetivo = destino / item.name
                if objetivo.exists():
                    continue
                try:
                    if item.is_dir():
                        shutil.copytree(item, objetivo)
                    else:
                        shutil.copy2(item, objetivo)
                except (OSError, shutil.Error):
                    # Migration is best-effort and never blocks application start.
                    continue

    def config_path(self):
        self.config_dir().mkdir(parents=True, exist_ok=True)
        return self.config_dir() / 'config.json'

    def perfiles_path(self):
        self.config_dir().mkdir(parents=True, exist_ok=True)
        return self.config_dir() / 'perfiles.json'

    def carpeta_data(self):
        ruta = self.data_dir() / 'Data'
        ruta.mkdir(parents=True, exist_ok=True)
        return ruta

    def carpeta_resource_tools(self):
        ruta = self.data_dir() / 'ResourceTools'
        ruta.mkdir(parents=True, exist_ok=True)
        return ruta

    def estabilidad_path(self):
        return self.carpeta_data() / 'estabilidad.json'

    def historial_path(self):
        return self.carpeta_data() / 'historial_eventos.jsonl'

    def metricas_runtime_path(self):
        return self.carpeta_data() / 'metricas_runtime.jsonl'

    def leer_json(self, ruta, defecto=None):
        ruta = Path(ruta)
        if not ruta.exists():
            return deepcopy(defecto) if defecto is not None else {}
        try:
            return json.loads(ruta.read_text(encoding='utf-8'))
        except (OSError, UnicodeError, json.JSONDecodeError):
            respaldo = ruta.with_suffix(ruta.suffix + f'.corrupt-{int(time.time())}')
            try:
                ruta.replace(respaldo)
            except OSError:
                logger.warning("Could not preserve the invalid configuration file %s", ruta, exc_info=True)
            return deepcopy(defecto) if defecto is not None else {}

    def escribir_json(self, ruta, datos):
        """Write JSON atomically and durably in the destination directory."""
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporal_name = tempfile.mkstemp(
            prefix=f'.{ruta.name}.', suffix='.tmp', dir=str(ruta.parent)
        )
        temporal = Path(temporal_name)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as file:
                json.dump(datos, file, indent=2, ensure_ascii=False, sort_keys=True)
                file.write('\n')
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporal, ruta)
            try:
                directory_fd = os.open(ruta.parent, os.O_DIRECTORY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError:
                logger.debug("Directory metadata could not be synchronized for %s", ruta.parent, exc_info=True)
            return True
        finally:
            try:
                temporal.unlink(missing_ok=True)
            except OSError:
                logger.debug("Temporary configuration file was already unavailable: %s", temporal, exc_info=True)

    @staticmethod
    def _config_defaults():
        return {
            'version': 2,
            'idioma': 'en',
            'tema': 'light',
            'alertas_activas': False,
            'modo_discreto': False,
            'ram_warning_percent': 82,
            'ram_critical_percent': 92,
            'swap_warning_percent': 35,
            'gpu_temp_warning': 82,
            'cpu_temp_warning': 88,
            # ``auto`` follows a uniquely active/installed supported governor.
            # Existing installations therefore migrate without being forced
            # away from the service that is already running.
            'gpu_governor': 'auto',
            'daemon_interval_seconds': 2,
            'fan_daemon_verify_seconds': 30,
            'fan_daemon_sensor_timeout_seconds': 15,
            'fan_daemon_sensor_max_age_seconds': 6,
            'fan_daemon_failsafe_percent': 100,
            'fan_daemon_sensor_offsets_c': {
                'gpu': 0,
                'cpu': 0,
                'vrm': 0,
                'board': 0,
            },
            'fan_daemon_critical_temperatures_c': {
                'gpu': 95,
                'cpu': 95,
                'vrm': 105,
                'board': 90,
            },
            'fan_daemon_hysteresis_c': 1.0,
            'fan_daemon_duty_deadband_percent': 2,
            'fan_daemon_max_down_step_percent': 10,
            'daemon_metrics_interval_seconds': 5,
            'daemon_governor_interval_seconds': 10,
            'daemon_memory_interval_seconds': 30,
            'proteccion_memoria': {
                'enabled': False,
                'dry_run': True,
                'priorizar_juego': True,
                'cerrar_candidatos': False,
            },
            'fan_curve': {
                'enabled': False,
                'edit_enabled': False,
                'pwm': 2,
                't1': 50,
                's1': 70,
                't2': 65,
                's2': 100,
                't3': 70,
                's3': 100,
                'point_count': 3,
                'points': [
                    {'temperature': 50, 'speed': 70},
                    {'temperature': 65, 'speed': 100},
                    {'temperature': 70, 'speed': 100},
                ],
                'preset': 'custom',
                'last_pwm_text': '--',
            },
            'fan_preset': {
                'enabled': False,
                'preset': '',
                'percent': 0,
                'pwm': 2,
            },
        }

    def _leer_config_unlocked(self):
        defecto = self._config_defaults()
        ruta = self.config_path()
        actual = self.leer_json(ruta, defecto)
        combinado = deepcopy(defecto)
        if isinstance(actual, dict):
            combinado.update(actual)
        combinado['fan_curve'] = normalize_fan_curve(combinado.get('fan_curve'))
        combinado['fan_preset'] = normalize_fan_preset(combinado.get('fan_preset'))
        combinado['version'] = 2
        if not ruta.exists() or actual != combinado:
            self.escribir_json(ruta, combinado)
        return combinado

    def leer_config(self):
        self.migrar_legacy_si_existe()
        ruta = self.config_path()
        with self._file_lock(ruta, exclusive=True):
            return self._leer_config_unlocked()

    def guardar_config(self, datos):
        ruta = self.config_path()
        with self._file_lock(ruta, exclusive=True):
            actual = self._leer_config_unlocked()
            if isinstance(datos, dict):
                actual.update(datos)
            actual['version'] = 2
            return self.escribir_json(ruta, actual)

    def guardar_config_completa(self, datos):
        """Replace portable user configuration after bundle validation."""
        if not isinstance(datos, dict):
            raise TypeError('Configuration must be an object.')
        ruta = self.config_path()
        with self._file_lock(ruta, exclusive=True):
            combinado = self._config_defaults()
            combinado.update(deepcopy(datos))
            combinado['fan_curve'] = normalize_fan_curve(combinado.get('fan_curve'))
            combinado['fan_preset'] = normalize_fan_preset(combinado.get('fan_preset'))
            combinado['version'] = 2
            return self.escribir_json(ruta, combinado)

    @staticmethod
    def _profile_defaults():
        return {
            'version': 1,
            'gpu': {
                'seguro': {'min': 500, 'max': 1500, 'descripcion': 'Uso diario seguro'},
                'gaming': {'min': 1000, 'max': 1850, 'descripcion': 'Gaming moderado'},
                'benchmark_controlado': {'min': 1000, 'max': 2000, 'descripcion': 'Solo pruebas controladas'},
                'recuperacion': {'min': 500, 'max': 1000, 'descripcion': 'Bajar consumo y temperatura'},
            },
            'cpu': {
                'stock': {'frequency': 3500, 'vid': 1100, 'temp': 90},
                'medio': {'frequency': 3850, 'vid': 1150, 'temp': 90},
                'maximo_temporal': {'frequency': 4000, 'vid': 1275, 'temp': 90},
            },
        }

    def leer_perfiles(self):
        self.migrar_legacy_si_existe()
        ruta = self.perfiles_path()
        defecto = self._profile_defaults()
        with self._file_lock(ruta, exclusive=True):
            actual = self.leer_json(ruta, defecto)
            if not ruta.exists():
                self.escribir_json(ruta, defecto)
                return deepcopy(defecto)
            return actual if isinstance(actual, dict) else deepcopy(defecto)

    def guardar_perfiles(self, datos):
        if not isinstance(datos, dict):
            raise TypeError('Profiles must be an object.')
        ruta = self.perfiles_path()
        with self._file_lock(ruta, exclusive=True):
            perfiles = deepcopy(datos)
            perfiles['version'] = 1
            return self.escribir_json(ruta, perfiles)

    @classmethod
    def _metric_tail_lines(cls, ruta, limite):
        """Read only a bounded tail; an oversized/corrupt prefix is disposable."""
        if limite <= 0:
            return []
        with ruta.open('rb') as archivo:
            archivo.seek(0, os.SEEK_END)
            final = archivo.tell()
            inicio = max(0, final - cls._metric_scan_max_bytes)
            archivo.seek(inicio)
            contenido = archivo.read(cls._metric_scan_max_bytes)
        if inicio and b'\n' in contenido:
            contenido = contenido.split(b'\n', 1)[1]
        elif inicio:
            return []
        lineas = contenido.splitlines()
        return [
            linea
            for linea in lineas[-limite:]
            if len(linea) <= cls._metric_record_max_bytes
        ]

    @staticmethod
    def _metric_json_value(valor):
        if valor is None or isinstance(valor, (bool, str, int)):
            return valor
        if isinstance(valor, float):
            return valor if math.isfinite(valor) else None
        if isinstance(valor, dict):
            return {
                str(clave): ConfiguracionLocal._metric_json_value(contenido)
                for clave, contenido in valor.items()
            }
        if isinstance(valor, (list, tuple)):
            return [ConfiguracionLocal._metric_json_value(item) for item in valor]
        return str(valor)

    @staticmethod
    def _metric_csv_value(valor):
        if isinstance(valor, (dict, list)):
            return json.dumps(
                valor, ensure_ascii=False, sort_keys=True, separators=(',', ':')
            )
        if isinstance(valor, str) and valor.startswith(
            ('=', '+', '-', '@', '\t', '\r')
        ):
            return "'" + valor
        return valor

    def registrar_metrica_runtime(self, datos, max_lineas=5000):
        ruta = self.metricas_runtime_path()
        try:
            limite = max(100, int(max_lineas))
        except (TypeError, ValueError):
            limite = 5000
        if datos is not None and not isinstance(datos, dict):
            logger.warning("Ignoring runtime metric with non-object payload")
            return False
        evento = {'ts': time.time(), 'datos': self._metric_json_value(datos or {})}
        serializado = json.dumps(
            evento, ensure_ascii=False, allow_nan=False, separators=(',', ':')
        ).encode('utf-8')
        if len(serializado) > self._metric_record_max_bytes:
            logger.warning(
                "Ignoring oversized runtime metric (%d bytes)", len(serializado)
            )
            return False
        with self._file_lock(ruta, exclusive=True):
            ruta.parent.mkdir(parents=True, exist_ok=True)
            with ruta.open('ab') as archivo:
                archivo.write(serializado + b'\n')
                archivo.flush()
                os.fsync(archivo.fileno())
            try:
                lineas = self._metric_tail_lines(ruta, limite + 1)
                if (
                    len(lineas) > limite
                    or ruta.stat().st_size > self._metric_scan_max_bytes
                ):
                    contenido = b'\n'.join(lineas[-limite:]) + b'\n'
                    descriptor, temporal_name = tempfile.mkstemp(
                        prefix=f'.{ruta.name}.', suffix='.tmp', dir=str(ruta.parent)
                    )
                    temporal = Path(temporal_name)
                    try:
                        with os.fdopen(descriptor, 'wb') as archivo:
                            archivo.write(contenido)
                            archivo.flush()
                            os.fsync(archivo.fileno())
                        os.replace(temporal, ruta)
                    finally:
                        temporal.unlink(missing_ok=True)
            except (OSError, UnicodeError):
                # A failed compaction must not discard the metric that was appended.
                logger.warning(
                    "Metric history compaction failed for %s", ruta, exc_info=True
                )
        return True

    def leer_metricas_runtime(self, limite=1000, desde=None):
        ruta = self.metricas_runtime_path()
        try:
            limite = max(0, min(int(limite), 100_000))
        except (TypeError, ValueError):
            limite = 1000
        try:
            desde = float(desde) if desde is not None else None
        except (TypeError, ValueError):
            desde = None
        eventos = []
        with self._file_lock(ruta, exclusive=False):
            try:
                candidatos = min(max(limite * 4, 100), 100_000)
                lineas = self._metric_tail_lines(ruta, candidatos)
            except OSError:
                return []
        for linea in lineas:
            try:
                evento = json.loads(linea)
                ts = float(evento.get('ts'))
                datos = evento.get('datos')
            except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if (
                not math.isfinite(ts)
                or not isinstance(datos, dict)
                or (desde is not None and ts < desde)
            ):
                continue
            eventos.append({'ts': ts, 'datos': datos})
        return eventos[-limite:] if limite else []

    def exportar_metricas_runtime(
        self, destino, *, formato='jsonl', limite=100_000, desde=None
    ):
        destino = Path(destino)
        formato = str(formato).lower()
        if formato not in {'jsonl', 'csv'}:
            raise ValueError('Metrics format must be jsonl or csv.')
        eventos = self.leer_metricas_runtime(limite=limite, desde=desde)
        destino.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporal_name = tempfile.mkstemp(
            prefix=f'.{destino.name}.', suffix='.tmp', dir=str(destino.parent)
        )
        temporal = Path(temporal_name)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8', newline='') as archivo:
                if formato == 'jsonl':
                    for evento in eventos:
                        archivo.write(
                            json.dumps(evento, ensure_ascii=False, default=str) + '\n'
                        )
                else:
                    campos = sorted(
                        {clave for evento in eventos for clave in evento['datos']}
                    )
                    writer = csv.DictWriter(
                        archivo,
                        fieldnames=['ts', *campos],
                        extrasaction='ignore',
                    )
                    writer.writeheader()
                    for evento in eventos:
                        writer.writerow({
                            'ts': evento['ts'],
                            **{
                                clave: self._metric_csv_value(valor)
                                for clave, valor in evento['datos'].items()
                            },
                        })
                archivo.flush()
                os.fsync(archivo.fileno())
            temporal.chmod(0o600)
            os.replace(temporal, destino)
        finally:
            temporal.unlink(missing_ok=True)
        return destino
