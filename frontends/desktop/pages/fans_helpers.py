"""Small pure helpers shared by the Fans page and its widgets."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from bc250cc.application.fan import board_view

# The numeric helpers are shared with the web and the terminal interface.
_dict = board_view.as_dict
_integer = board_view.integer
_finite_number = board_view.finite_number
_pwm_to_percent = board_view.pwm_to_percent
_percent_to_pwm = board_view.percent_to_pwm


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
