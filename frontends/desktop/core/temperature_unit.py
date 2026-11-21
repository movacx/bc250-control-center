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
"""

from __future__ import annotations

import math
import re

from PyQt6.QtCore import QObject, QSettings, pyqtSignal

CELSIUS = "celsius"
FAHRENHEIT = "fahrenheit"
UNITS = (CELSIUS, FAHRENHEIT)
DEFAULT_UNIT = CELSIUS
SETTINGS_KEY = "settings/temperature_unit"

_SYMBOLS = {CELSIUS: "°C", FAHRENHEIT: "°F"}

_current: str | None = None


class _Notifier(QObject):
    #: The new unit code, ``"celsius"`` or ``"fahrenheit"``.
    changed = pyqtSignal(str)


_notifier: _Notifier | None = None


def temperature_unit_notifier() -> _Notifier:
    """The one object that announces a change of unit."""
    global _notifier
    if _notifier is None:
        _notifier = _Notifier()
    return _notifier


def normalize_unit(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in {"f", "°f", "fahrenheit", "imperial"}:
        return FAHRENHEIT
    return CELSIUS


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


def is_fahrenheit() -> bool:
    return temperature_unit() == FAHRENHEIT


def unit_symbol(unit: str | None = None) -> str:
    return _SYMBOLS[normalize_unit(unit) if unit is not None else temperature_unit()]


def celsius_to_fahrenheit(celsius: float) -> float:
    return celsius * 9.0 / 5.0 + 32.0


def fahrenheit_to_celsius(fahrenheit: float) -> float:
    return (fahrenheit - 32.0) * 5.0 / 9.0


def to_display(celsius: float, unit: str | None = None) -> float:
    """A Celsius value in the unit on screen."""
    target = normalize_unit(unit) if unit is not None else temperature_unit()
    return celsius_to_fahrenheit(celsius) if target == FAHRENHEIT else float(celsius)


def from_display(value: float, unit: str | None = None) -> float:
    """A value typed or dragged on screen, back in Celsius."""
    source = normalize_unit(unit) if unit is not None else temperature_unit()
    return fahrenheit_to_celsius(value) if source == FAHRENHEIT else float(value)


def to_display_int(celsius: float, unit: str | None = None) -> int:
    """A whole-degree Celsius setting as the whole number shown for it.

    Whole Celsius degrees survive the trip there and back:
    ``from_display_int(to_display_int(c)) == c`` for every integer ``c``,
    because one Fahrenheit degree is narrower than one Celsius degree.
    """
    return int(round(to_display(celsius, unit)))


def from_display_int(value: float, unit: str | None = None) -> int:
    return int(round(from_display(value, unit)))


def to_display_delta(celsius_delta: float, unit: str | None = None) -> float:
    """A difference of temperatures: scaled, never offset by 32."""
    target = normalize_unit(unit) if unit is not None else temperature_unit()
    return celsius_delta * 9.0 / 5.0 if target == FAHRENHEIT else float(celsius_delta)


def from_display_delta(value: float, unit: str | None = None) -> float:
    source = normalize_unit(unit) if unit is not None else temperature_unit()
    return value * 5.0 / 9.0 if source == FAHRENHEIT else float(value)


def format_temperature(
    celsius: float | None,
    decimals: int = 1,
    *,
    placeholder: str = "--",
    unit: str | None = None,
    spaced: bool = True,
) -> str:
    """``"47.5 °C"`` or ``"117.5 °F"``; ``"-- °C"`` when there is no reading."""
    symbol = unit_symbol(unit)
    gap = " " if spaced else ""
    if celsius is None:
        return f"{placeholder}{gap}{symbol}" if placeholder else ""
    try:
        value = float(celsius)
    except (TypeError, ValueError):
        return f"{placeholder}{gap}{symbol}" if placeholder else ""
    if not math.isfinite(value):
        return f"{placeholder}{gap}{symbol}" if placeholder else ""
    return f"{to_display(value, unit):.{max(0, int(decimals))}f}{gap}{symbol}"


def format_temperature_delta(celsius_delta: float, decimals: int = 1, *, unit: str | None = None) -> str:
    return f"{to_display_delta(float(celsius_delta), unit):.{max(0, int(decimals))}f} {unit_symbol(unit)}"


def temperature_number(celsius: float | None, decimals: int = 1, *, unit: str | None = None) -> str:
    """The number alone, for a column or axis whose header names the unit."""
    if celsius is None:
        return "--"
    try:
        value = float(celsius)
    except (TypeError, ValueError):
        return "--"
    if not math.isfinite(value):
        return "--"
    return f"{to_display(value, unit):.{max(0, int(decimals))}f}"


# "45 °C", "45.5°C", "-3 ℃", "30–95 °C" (a range keeps both ends) and the
# same in °F. A number glued to letters ("x86 °C") is left alone.
_NUMBER = r"-?\d+(?:\.\d+)?"
_TEMPERATURE = re.compile(
    rf"(?<![\w.])(?P<low>{_NUMBER})(?P<dash>\s*[–—-]\s*|\s*…\s*)?(?P<high>{_NUMBER})?"
    r"(?P<space>\s?)(?P<unit>°\s?[CF]|℃|℉)(?![A-Za-z])"
)


def _convert_number(text: str, source: str, target: str) -> str:
    decimals = len(text.split(".", 1)[1]) if "." in text else 0
    value = float(text)
    celsius = fahrenheit_to_celsius(value) if source == FAHRENHEIT else value
    shown = celsius_to_fahrenheit(celsius) if target == FAHRENHEIT else celsius
    rendered = f"{shown:.{decimals}f}"
    return "0" if rendered in {"-0", "-0.0"} and decimals == 0 else rendered


def localize_temperature_text(text: str, unit: str | None = None) -> str:
    """Every temperature written in ``text``, in the chosen unit.

    Values keep the precision they were written with. Text already in the
    chosen unit comes back unchanged, so running it twice is harmless, and a
    sentence rendered in one unit converts cleanly into the other.
    """
    if not text:
        return text
    target = normalize_unit(unit) if unit is not None else temperature_unit()
    if "°" not in text and "℃" not in text and "℉" not in text:
        if target != FAHRENHEIT or " C" not in text:
            return text

    def replace(match: re.Match[str]) -> str:
        written = match.group("unit").replace(" ", "")
        source = FAHRENHEIT if written in {"°F", "℉"} else CELSIUS
        if source == target:
            return match.group(0)
        if match.group("dash") is not None and match.group("high") is None:
            # "45 - °C": not a range after all; convert nothing.
            return match.group(0)
        low = _convert_number(match.group("low"), source, target)
        high = match.group("high")
        if match.group("dash") is not None and high is not None:
            converted = f"{low}{match.group('dash')}{_convert_number(high, source, target)}"
        elif high is not None:
            # Two numbers with nothing between them cannot happen with this
            # pattern; keep the text exactly as written if it ever does.
            return match.group(0)
        else:
            converted = low
        return f"{converted}{match.group('space')}{_SYMBOLS[target]}"

    converted = _TEMPERATURE.sub(replace, text)
    if target == FAHRENHEIT and " C" in converted:
        # Messages from the daemon and the fan engine write "45.0 C -> 60 %".
        converted = _PLAIN_C.sub(
            lambda match: f"{_convert_number(match.group(1), CELSIUS, FAHRENHEIT)} °F", converted
        )
    # What is left is a unit with no number in front of it: a column header
    # ("GPU °C"), an empty reading ("-- °C"). Only the symbol changes.
    return _BARE_UNIT[target].sub(_SYMBOLS[target], converted)


#: "45.0 C" without the degree sign, only where nothing else can be meant:
#: before an arrow, before "is", or closing the sentence.
_PLAIN_C = re.compile(
    rf"(?<![\w.])({_NUMBER}) C(?=\s*(?:->|→)|\s+is\b|[.,;)]?\s*$)"
)

#: A unit symbol other than the target's, wherever it is still written.
_BARE_UNIT = {
    FAHRENHEIT: re.compile(r"°\s?C(?![A-Za-z])|℃"),
    CELSIUS: re.compile(r"°\s?F(?![A-Za-z])|℉"),
}


def reset_for_tests(unit: str | None = None) -> None:
    """Forget the cached unit (or force one) without touching settings."""
    global _current
    _current = normalize_unit(unit) if unit is not None else None
