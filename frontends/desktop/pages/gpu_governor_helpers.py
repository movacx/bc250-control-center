"""Small pure helpers shared by the GPU page and its widgets."""

from __future__ import annotations

from bc250cc.application.gpu.telemetry import (
    format_bytes,
)


def _dict(value):
    if hasattr(value, "to_dict"):
        return value.to_dict()
    try:
        return dict(value or {})
    except (TypeError, ValueError):
        return {}


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _integer(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _format_bytes(value) -> str:
    return format_bytes(value)
