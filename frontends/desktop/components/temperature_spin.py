"""A spin box that edits a whole-degree Celsius setting in the unit on screen.

The number in the box is °C or °F, whichever the user chose; ``celsius()``
and ``set_celsius()`` always speak Celsius, so whatever is saved, compared or
sent to the board never sees Fahrenheit. Whole Celsius degrees survive the
trip through Fahrenheit and back exactly, so opening a fan curve in °F and
saving it untouched writes the same points it read.

``delta=True`` is for a difference of temperatures (a hysteresis): it scales
by 9/5 without the 32-degree offset.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QSpinBox, QWidget

from ..core.temperature_unit import (
    from_display,
    from_display_delta,
    temperature_unit,
    to_display,
    to_display_delta,
    unit_symbol,
)


class TemperatureSpinBox(QSpinBox):
    def __init__(
        self,
        minimum_c: int = 0,
        maximum_c: int = 120,
        value_c: int | None = None,
        parent: QWidget | None = None,
        *,
        delta: bool = False,
    ) -> None:
        super().__init__(parent)
        self._delta = bool(delta)
        self._range_c = (int(minimum_c), int(maximum_c))
        self._unit = temperature_unit()
        self._celsius = int(minimum_c if value_c is None else value_c)
        self._apply_unit()
        self.set_celsius(self._celsius)

    # ------------------------------------------------------------ conversion

    def _shown(self, celsius: float, unit: str | None = None) -> int:
        convert = to_display_delta if self._delta else to_display
        return int(round(convert(celsius, unit or self._unit)))

    def _read(self, shown: float, unit: str | None = None) -> int:
        convert = from_display_delta if self._delta else from_display
        return int(round(convert(shown, unit or self._unit)))

    def _apply_unit(self) -> None:
        low, high = self._range_c
        self.blockSignals(True)
        try:
            self.setRange(self._shown(low), self._shown(high))
            self.setSuffix(f" {unit_symbol(self._unit)}")
        finally:
            self.blockSignals(False)

    # --------------------------------------------------------------- the API

    def celsius(self) -> int:
        """The setting, in °C. Untouched, it is exactly what was set."""
        shown = self.value()
        if shown == self._shown(self._celsius):
            return self._celsius
        low, high = self._range_c
        return max(low, min(high, self._read(shown)))

    def set_celsius(self, celsius: float) -> None:
        low, high = self._range_c
        self._celsius = max(low, min(high, int(round(float(celsius)))))
        self.setValue(self._shown(self._celsius))

    def set_celsius_range(self, minimum_c: int, maximum_c: int) -> None:
        current = self.celsius()
        self._range_c = (int(minimum_c), max(int(minimum_c), int(maximum_c)))
        self._apply_unit()
        self.set_celsius(current)

    def refresh_unit(self) -> None:
        """Show the same Celsius setting in the unit chosen since."""
        if self._unit == temperature_unit():
            return
        current = self.celsius()
        self._unit = temperature_unit()
        self.blockSignals(True)
        try:
            self._apply_unit()
            self.set_celsius(current)
        finally:
            self.blockSignals(False)
