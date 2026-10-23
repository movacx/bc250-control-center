"""Small pure helpers shared by the Fans page and its widgets."""

from __future__ import annotations

import math

from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


def _dict(value) -> dict:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    try:
        return dict(value or {})
    except Exception:
        return {}


def _integer(value, default=0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return int(default)


def _finite_number(value: object) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _pwm_to_percent(value) -> int | None:
    if value is None:
        return None
    return max(0, min(100, round(_integer(value) * 100 / 255)))


def _percent_to_pwm(value) -> int:
    return max(0, min(255, round(_integer(value) * 255 / 100)))


def _rpm_text(value: object) -> str:
    number = _finite_number(value)
    return f"{int(number):,} RPM" if number is not None else "-- RPM"


def _percent_text(value: object) -> str:
    return f"{_integer(value)} %" if value is not None else "-- %"


def _temperature_text(value: float | None) -> str:
    return f"{value:.1f} °C" if value is not None else "-- °C"


def _action_bar(grid: QGridLayout) -> QWidget:
    """A form's action bar: a hairline, then the buttons in ``grid``."""
    bar = QWidget()
    bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    layout = QVBoxLayout(bar)
    layout.setContentsMargins(0, 4, 0, 0)
    layout.setSpacing(12)
    rule = QFrame()
    rule.setProperty("fanFooterRule", True)
    rule.setFixedHeight(1)
    layout.addWidget(rule)
    layout.addLayout(grid)
    return bar


def _hairline() -> QFrame:
    line = QFrame()
    line.setProperty("instrumentHairline", True)
    line.setFixedHeight(1)
    return line
