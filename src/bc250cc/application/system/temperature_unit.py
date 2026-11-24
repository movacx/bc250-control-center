"""Convert Celsius readings, inputs and display text without UI state."""

from __future__ import annotations

import math
import re

CELSIUS = "celsius"
FAHRENHEIT = "fahrenheit"
UNITS = (CELSIUS, FAHRENHEIT)
DEFAULT_UNIT = CELSIUS

_SYMBOLS = {CELSIUS: "°C", FAHRENHEIT: "°F"}

def normalize_unit(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in {"f", "°f", "fahrenheit", "imperial"}:
        return FAHRENHEIT
    return CELSIUS


def unit_symbol(unit: str | None = None) -> str:
    return _SYMBOLS[normalize_unit(unit)]


def celsius_to_fahrenheit(celsius: float) -> float:
    return celsius * 9.0 / 5.0 + 32.0


def fahrenheit_to_celsius(fahrenheit: float) -> float:
    return (fahrenheit - 32.0) * 5.0 / 9.0


def to_display(celsius: float, unit: str | None = None) -> float:
    """A Celsius value in the unit on screen."""
    target = normalize_unit(unit)
    return celsius_to_fahrenheit(celsius) if target == FAHRENHEIT else float(celsius)


def from_display(value: float, unit: str | None = None) -> float:
    """A value typed or dragged on screen, back in Celsius."""
    source = normalize_unit(unit)
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
    target = normalize_unit(unit)
    return celsius_delta * 9.0 / 5.0 if target == FAHRENHEIT else float(celsius_delta)


def from_display_delta(value: float, unit: str | None = None) -> float:
    source = normalize_unit(unit)
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
    target = normalize_unit(unit)
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
