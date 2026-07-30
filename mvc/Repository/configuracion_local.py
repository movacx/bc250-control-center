from __future__ import annotations

from contextlib import contextmanager
import logging
from copy import deepcopy
from pathlib import Path
import fcntl
import json
import os

from mvc.config_paths import (
    APP_ID,
    app_cache_dir,
    app_config_dir,
    app_data_dir,
    xdg_cache_home,
    xdg_config_home,
    xdg_data_home,
)
import shutil
import tempfile
import time


logger = logging.getLogger(__name__)


class ConfiguracionLocal:
    app_id = APP_ID
    legacy_app_id = 'modo-juego-ram'

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
            'version': 1,
            'idioma': 'en',
            'tema': 'light',
            'alertas_activas': False,
            'modo_discreto': False,
            'ram_warning_percent': 82,
            'ram_critical_percent': 92,
            'swap_warning_percent': 35,
            'gpu_temp_warning': 82,
            'cpu_temp_warning': 88,
            'daemon_interval_seconds': 2,
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
        if not ruta.exists():
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
            actual['version'] = 1
            return self.escribir_json(ruta, actual)

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

    def registrar_metrica_runtime(self, datos, max_lineas=5000):
        ruta = self.metricas_runtime_path()
        try:
            limite = max(100, int(max_lineas))
        except (TypeError, ValueError):
            limite = 5000
        evento = {'ts': time.time(), 'datos': datos or {}}
        with self._file_lock(ruta, exclusive=True):
            ruta.parent.mkdir(parents=True, exist_ok=True)
            with ruta.open('a', encoding='utf-8') as archivo:
                archivo.write(json.dumps(evento, ensure_ascii=False, default=str) + '\n')
                archivo.flush()
                os.fsync(archivo.fileno())
            try:
                lineas = ruta.read_text(encoding='utf-8').splitlines()
                if len(lineas) > limite:
                    contenido = '\n'.join(lineas[-limite:]) + '\n'
                    descriptor, temporal_name = tempfile.mkstemp(
                        prefix=f'.{ruta.name}.', suffix='.tmp', dir=str(ruta.parent)
                    )
                    temporal = Path(temporal_name)
                    try:
                        with os.fdopen(descriptor, 'w', encoding='utf-8') as archivo:
                            archivo.write(contenido)
                            archivo.flush()
                            os.fsync(archivo.fileno())
                        os.replace(temporal, ruta)
                    finally:
                        temporal.unlink(missing_ok=True)
            except (OSError, UnicodeError):
                # A failed compaction must not discard the metric that was appended.
                logger.warning("Metric history compaction failed for %s", ruta, exc_info=True)
        return True
