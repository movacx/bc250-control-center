from pathlib import Path
import json
import os
import time
import shutil


class ConfiguracionLocal:
    app_id = 'bc250-control-center'
    legacy_app_id = 'modo-juego-ram'

    def config_dir(self):
        base = os.environ.get('XDG_CONFIG_HOME')
        if base:
            return Path(base) / self.app_id
        return Path.home() / '.config' / self.app_id

    def data_dir(self):
        base = os.environ.get('XDG_DATA_HOME')
        if base:
            return Path(base) / self.app_id
        return Path.home() / '.local' / 'share' / self.app_id

    def cache_dir(self):
        base = os.environ.get('XDG_CACHE_HOME')
        if base:
            return Path(base) / self.app_id
        return Path.home() / '.cache' / self.app_id

    def legacy_config_dir(self):
        base = os.environ.get('XDG_CONFIG_HOME')
        if base:
            return Path(base) / self.legacy_app_id
        return Path.home() / '.config' / self.legacy_app_id

    def legacy_data_dir(self):
        base = os.environ.get('XDG_DATA_HOME')
        if base:
            return Path(base) / self.legacy_app_id
        return Path.home() / '.local' / 'share' / self.legacy_app_id

    def legacy_cache_dir(self):
        base = os.environ.get('XDG_CACHE_HOME')
        if base:
            return Path(base) / self.legacy_app_id
        return Path.home() / '.cache' / self.legacy_app_id

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
                except Exception:
                    pass

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
            return defecto if defecto is not None else {}
        try:
            return json.loads(ruta.read_text(encoding='utf-8'))
        except Exception:
            respaldo = ruta.with_suffix(ruta.suffix + f'.corrupt-{int(time.time())}')
            try:
                ruta.rename(respaldo)
            except Exception:
                pass
            return defecto if defecto is not None else {}

    def escribir_json(self, ruta, datos):
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = ruta.with_suffix(ruta.suffix + '.tmp')
        temporal.write_text(json.dumps(datos, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
        temporal.replace(ruta)
        return True

    def leer_config(self):
        defecto = {
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
                'cerrar_candidatos': False
            }
        }
        self.migrar_legacy_si_existe()
        actual = self.leer_json(self.config_path(), defecto.copy())
        combinado = defecto.copy()
        combinado.update(actual or {})
        if not self.config_path().exists():
            self.escribir_json(self.config_path(), combinado)
        return combinado

    def guardar_config(self, datos):
        actual = self.leer_config()
        actual.update(datos or {})
        actual['version'] = 1
        return self.escribir_json(self.config_path(), actual)

    def leer_perfiles(self):
        defecto = {
            'version': 1,
            'gpu': {
                'seguro': {'min': 500, 'max': 1500, 'descripcion': 'Uso diario seguro'},
                'gaming': {'min': 1000, 'max': 1850, 'descripcion': 'Gaming moderado'},
                'benchmark_controlado': {'min': 1000, 'max': 2000, 'descripcion': 'Solo pruebas controladas'},
                'recuperacion': {'min': 500, 'max': 1000, 'descripcion': 'Bajar consumo y temperatura'}
            },
            'cpu': {
                'stock': {'frequency': 3500, 'vid': 1100, 'temp': 90},
                'medio': {'frequency': 3850, 'vid': 1150, 'temp': 90},
                'maximo_temporal': {'frequency': 4000, 'vid': 1275, 'temp': 90}
            }
        }
        self.migrar_legacy_si_existe()
        actual = self.leer_json(self.perfiles_path(), defecto.copy())
        if not self.perfiles_path().exists():
            self.escribir_json(self.perfiles_path(), defecto)
            return defecto
        return actual or defecto

    def registrar_metrica_runtime(self, datos, max_lineas=5000):
        ruta = self.metricas_runtime_path()
        evento = {'ts': time.time(), 'datos': datos or {}}
        with ruta.open('a', encoding='utf-8') as archivo:
            archivo.write(json.dumps(evento, ensure_ascii=False, default=str) + '\n')
        try:
            lineas = ruta.read_text(encoding='utf-8').splitlines()
            if len(lineas) > max_lineas:
                ruta.write_text('\n'.join(lineas[-max_lineas:]) + '\n', encoding='utf-8')
        except Exception:
            pass
        return True
