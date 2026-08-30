"""Application use cases for the local, non-hardware activity journal."""

from __future__ import annotations


class ActivityService:
    """Expose the existing JSONL audit journal through a narrow API."""

    def __init__(self, repository_factory):
        self._repository_factory = repository_factory

    def record(self, category, level, title, detail="", data=None):
        repository = self._repository_factory()
        event = repository.nuevo_evento(category, level, title, detail, data or {})
        return repository.agregar(event)

    def list(self, limit=300):
        return self._repository_factory().listar(limit)

    def clear(self):
        return self._repository_factory().limpiar()
