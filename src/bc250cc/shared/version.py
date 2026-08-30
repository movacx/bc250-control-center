"""Single read-only application version sourced from the release VERSION file."""

from __future__ import annotations

from pathlib import Path


def application_version() -> str:
    for parent in Path(__file__).resolve().parents:
        version_file = parent / "VERSION"
        try:
            value = version_file.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        return value or "development"
    return "development"


__version__ = application_version()
