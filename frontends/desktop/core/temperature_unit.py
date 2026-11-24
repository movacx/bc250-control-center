"""The temperature unit the interface shows: °C or °F, nothing else.

Everything the application measures, stores, compares and sends to the board
stays in degrees Celsius. Only what reaches the screen is converted, and only
through this module, so a threshold, a fan curve or a saved profile can never
drift because somebody once looked at it in Fahrenheit.

Three ways in, from most to least explicit:

* ``format_temperature(celsius)`` for a reading a widget shows directly;
* ``to_display`` / ``from_display`` for a control that edits a temperature
  (a spin box, a chart axis), converting back to Celsius before anything is
  saved;
* ``localize_temperature_text(text)`` for finished copy: it rewrites every
  ``N °C`` (or ``N °F``) in a sentence into the chosen unit. ``tr`` and
  ``tr_format`` run it on everything they return, which is how the translated
  messages, toasts and dialogs follow the setting without each one knowing.

``temperature_unit_notifier().changed`` fires when the user picks another
unit, so open pages can redraw at once.

The conversion itself lives in ``application.system.temperature_unit``; this module
adds the stored preference, and needs Qt only for that.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from bc250cc.application.system import temperature_unit as conversion
from bc250cc.application.system.temperature_unit import (
    CELSIUS as CELSIUS,
)
from bc250cc.application.system.temperature_unit import (
    DEFAULT_UNIT as DEFAULT_UNIT,
)
from bc250cc.application.system.temperature_unit import (
    FAHRENHEIT as FAHRENHEIT,
)
from bc250cc.application.system.temperature_unit import (
    UNITS as UNITS,
)
from bc250cc.application.system.temperature_unit import (
    celsius_to_fahrenheit as celsius_to_fahrenheit,
)
from bc250cc.application.system.temperature_unit import (
    fahrenheit_to_celsius as fahrenheit_to_celsius,
)
from bc250cc.application.system.temperature_unit import (
    normalize_unit as normalize_unit,
)

if TYPE_CHECKING:
    from PyQt6.QtCore import QSettings

SETTINGS_KEY = "settings/temperature_unit"
_current: str | None = None
_notifier = None


def temperature_unit_notifier():
    """The one object that announces a change of unit."""
    global _notifier
    if _notifier is None:
        from PyQt6.QtCore import QObject, pyqtSignal

        class Notifier(QObject):
            changed = pyqtSignal(str)

        _notifier = Notifier()
    return _notifier


def _settings(settings: QSettings | None) -> QSettings:
    if settings is not None:
        return settings
    from .preferences import application_settings

    return application_settings()


def load_temperature_unit(settings: QSettings | None = None) -> str:
    """Read the stored unit (Celsius when there is none) and make it current."""
    global _current
    _current = normalize_unit(_settings(settings).value(SETTINGS_KEY, DEFAULT_UNIT))
    return _current


def temperature_unit() -> str:
    if _current is None:
        # Shared presenters also run in frontends that never start Qt.
        if "PyQt6.QtCore" not in sys.modules:
            return DEFAULT_UNIT
        try:
            return load_temperature_unit()
        except Exception:  # noqa: BLE001 - a display preference must never break a read
            return DEFAULT_UNIT
    return _current


def set_temperature_unit(unit: object, settings: QSettings | None = None, *, persist: bool = True) -> str:
    """Store the unit and tell the open pages, unless it is already the one shown."""
    global _current
    normalized = normalize_unit(unit)
    if persist:
        store = _settings(settings)
        store.setValue(SETTINGS_KEY, normalized)
        store.sync()
    previous = _current
    _current = normalized
    if previous != normalized:
        temperature_unit_notifier().changed.emit(normalized)
    return normalized


def use_unit(unit: object) -> str:
    """Show this unit from now on without storing it (a frontend without Qt)."""
    global _current
    _current = normalize_unit(unit)
    return _current


def is_fahrenheit() -> bool:
    return temperature_unit() == FAHRENHEIT


def _unit(unit: str | None) -> str:
    return unit if unit is not None else temperature_unit()


def unit_symbol(unit: str | None = None) -> str:
    return conversion.unit_symbol(_unit(unit))


def to_display(celsius: float, unit: str | None = None) -> float:
    return conversion.to_display(celsius, _unit(unit))


def from_display(value: float, unit: str | None = None) -> float:
    return conversion.from_display(value, _unit(unit))


def to_display_int(celsius: float, unit: str | None = None) -> int:
    return conversion.to_display_int(celsius, _unit(unit))


def from_display_int(value: float, unit: str | None = None) -> int:
    return conversion.from_display_int(value, _unit(unit))


def to_display_delta(celsius_delta: float, unit: str | None = None) -> float:
    return conversion.to_display_delta(celsius_delta, _unit(unit))


def from_display_delta(value: float, unit: str | None = None) -> float:
    return conversion.from_display_delta(value, _unit(unit))


def format_temperature(
    celsius: float | None,
    decimals: int = 1,
    *,
    placeholder: str = "--",
    unit: str | None = None,
    spaced: bool = True,
) -> str:
    return conversion.format_temperature(celsius, decimals, placeholder=placeholder, unit=_unit(unit), spaced=spaced)


def format_temperature_delta(celsius_delta: float, decimals: int = 1, *, unit: str | None = None) -> str:
    return conversion.format_temperature_delta(celsius_delta, decimals, unit=_unit(unit))


def temperature_number(celsius: float | None, decimals: int = 1, *, unit: str | None = None) -> str:
    return conversion.temperature_number(celsius, decimals, unit=_unit(unit))


def localize_temperature_text(text: str, unit: str | None = None) -> str:
    return conversion.localize_temperature_text(text, _unit(unit)) if text else text


def reset_for_tests(unit: str | None = None) -> None:
    """Forget the cached unit (or force one) without touching settings."""
    global _current
    _current = normalize_unit(unit) if unit is not None else None
