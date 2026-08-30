"""Canonical construction of the durable local activity journal."""

from __future__ import annotations

import logging
import shutil

from bc250cc.infrastructure.historial_repository import HistorialRepository

logger = logging.getLogger(__name__)


def activity_journal_path(configuration):
    """Return the existing journal path, migrating the pre-XDG filename once."""
    current = configuration.historial_path()
    previous = configuration.data_dir() / "historial_eventos.jsonl"
    if previous.exists() and not current.exists():
        try:
            current.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(previous, current)
        except OSError:
            logger.warning("Could not migrate legacy activity data from %s", previous, exc_info=True)
    return current


def activity_journal(configuration) -> HistorialRepository:
    """Build the stable JSONL journal with its existing 1000/800 policy."""
    return HistorialRepository(activity_journal_path(configuration), 1000, 800)
