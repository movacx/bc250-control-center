"""Settings and portable-profile use cases outside the desktop frontend."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Protocol


class SettingsStore(Protocol):
    def leer_config(self) -> dict: ...
    def guardar_config(self, values: dict) -> dict: ...
    def leer_perfiles(self) -> dict: ...
    def config_path(self) -> Path: ...
    def perfiles_path(self) -> Path: ...
    def estabilidad_path(self) -> Path: ...
    def metricas_runtime_path(self) -> Path: ...
    def carpeta_data(self) -> Path: ...
    def carpeta_resource_tools(self) -> Path: ...
    def registrar_metrica_runtime(self, data: dict) -> bool: ...
    def exportar_metricas_runtime(self, destination: str | Path, formato: str = "csv") -> Path: ...


class SettingsService:
    """Coordinates stable user settings and portable profile bundles."""

    def __init__(self, store: SettingsStore, bundle_repository, *, history_path, recovery_root):
        self._store = store
        self._bundle_repository = bundle_repository
        self._history_path = history_path
        self._recovery_root = recovery_root

    def config_paths(self) -> dict[str, str]:
        return {
            "config": str(self._store.config_path()),
            "perfiles": str(self._store.perfiles_path()),
            "historial": str(self._history_path()),
            "estabilidad": str(self._store.estabilidad_path()),
            "metricas_runtime": str(self._store.metricas_runtime_path()),
            "data": str(self._store.carpeta_data()),
            "resource_tools": str(self._store.carpeta_resource_tools()),
            "recovery": str(self._recovery_root()),
        }

    def read_local_config(self) -> dict:
        return self._store.leer_config()

    def save_local_config(self, values: dict) -> dict:
        return self._store.guardar_config(values)

    def read_local_profiles(self) -> dict:
        return self._store.leer_perfiles()

    def export_profile_bundle(self, destination: str | Path) -> str:
        return str(self._bundle_repository.export(destination))

    def preview_profile_bundle(self, source: str | Path) -> dict:
        return asdict(self._bundle_repository.preview(source))

    def import_profile_bundle(self, source: str | Path) -> str:
        return str(self._bundle_repository.import_bundle(source))

    def record_runtime_metric(self, data: dict) -> bool:
        return bool(self._store.registrar_metrica_runtime(data))

    def export_runtime_metrics(self, destination: str | Path, format_name: str = "csv") -> str:
        return str(self._store.exportar_metricas_runtime(destination, formato=format_name))
