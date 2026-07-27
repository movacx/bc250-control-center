from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import fcntl
import json
import os
import tempfile
import time


class HistorialRepository:
    def __init__(self, ruta, max_registros=26, conservar=6):
        self.archivo = os.path.abspath(str(ruta))
        self.max_registros = max(1, int(max_registros))
        self.conservar = max(1, min(int(conservar), self.max_registros))
        self.lista = []
        self._load()

    @property
    def _path(self):
        return Path(self.archivo)

    @contextmanager
    def _lock(self, *, exclusive=True):
        path = self._path
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = path.with_name(path.name + '.lock')
        with lock_path.open('a+', encoding='utf-8') as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _read_unlocked(self):
        items = []
        path = self._path
        if not path.exists():
            return items
        with path.open('r', encoding='utf-8', errors='replace') as file:
            for linea in file:
                texto = linea.strip()
                if not texto:
                    continue
                try:
                    item = json.loads(texto)
                    items.append(item if isinstance(item, dict) else {'detalle': str(item)})
                except json.JSONDecodeError:
                    items.append({
                        'id': 0,
                        'ts': 0,
                        'fecha': '--',
                        'tipo': 'error',
                        'nivel': 'warning',
                        'titulo': 'Linea de historial invalida',
                        'detalle': texto[:240],
                        'datos': {},
                    })
        return items

    def _write_unlocked(self, items):
        path = self._path
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f'.{path.name}.', suffix='.tmp', dir=str(path.parent)
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as file:
                for item in items:
                    file.write(json.dumps(item, ensure_ascii=False, default=str) + '\n')
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
            return True
        finally:
            temporary.unlink(missing_ok=True)

    def _load(self):
        with self._lock(exclusive=True):
            items = self._read_unlocked()
            if len(items) > self.max_registros:
                items = items[-self.conservar:]
                self._write_unlocked(items)
            self.lista = items
        return True

    def _save(self):
        with self._lock(exclusive=True):
            self._write_unlocked(self.lista)
        return True

    def _compactar_si_ocupa(self):
        if len(self.lista) <= self.max_registros:
            return False
        self.lista = self.lista[-self.conservar:]
        return True

    def agregar(self, evento):
        with self._lock(exclusive=True):
            # Reload while holding the lock so GUI and daemon writers cannot
            # overwrite each other's most recent entries.
            self.lista = self._read_unlocked()
            self.lista.append(evento)
            self._compactar_si_ocupa()
            self._write_unlocked(self.lista)
        return True

    def listar(self, limite=300):
        try:
            limite = max(0, int(limite))
        except (TypeError, ValueError):
            limite = 300
        with self._lock(exclusive=True):
            self.lista = self._read_unlocked()
            if len(self.lista) > self.max_registros:
                self.lista = self.lista[-self.conservar:]
                self._write_unlocked(self.lista)
            return list(reversed(self.lista[-limite:])) if limite else []

    def limpiar(self):
        with self._lock(exclusive=True):
            self.lista = []
            self._write_unlocked(self.lista)
        return True

    def nuevo_evento(self, tipo, nivel, titulo, detalle='', datos=None):
        ahora = time.time()
        return {
            'id': int(ahora * 1000),
            'ts': ahora,
            'fecha': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ahora)),
            'tipo': str(tipo),
            'nivel': str(nivel),
            'titulo': str(titulo),
            'detalle': str(detalle),
            'datos': datos or {},
        }
