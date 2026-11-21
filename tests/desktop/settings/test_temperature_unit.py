"""°C or °F: one display preference, everything else stays in Celsius."""

import pytest
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import QComboBox, QWidget

from frontends.desktop.components.dashboard_instruments import Reading
from frontends.desktop.components.temperature_spin import TemperatureSpinBox
from frontends.desktop.core import temperature_unit as unit
from frontends.desktop.core.sensor_log import format_sensor_value
from frontends.desktop.i18n import set_language, tr, tr_format
from frontends.desktop.onboarding.welcome import WelcomeOverlay
from frontends.desktop.pages.blackbox import COLUMNS as BLACKBOX_COLUMNS
from frontends.desktop.pages.blackbox import SampleModel
from frontends.desktop.pages.fans import PointsEditor
from frontends.desktop.pages.fans_widgets import FanCurveScale
from frontends.desktop.pages.settings import SettingsPage


class SettingsService:
    pass


class ActivityService:
    def clear(self):
        return True


@pytest.fixture(autouse=True)
def _celsius_after_each_test():
    unit.reset_for_tests(unit.CELSIUS)
    yield
    unit.reset_for_tests(unit.CELSIUS)
    set_language("en")


def _settings(tmp_path):
    return QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)


# ------------------------------------------------------------------ helper


def test_conversion_and_formatting():
    assert unit.format_temperature(45.5) == "45.5 °C"
    assert unit.format_temperature(None) == "-- °C"
    unit.reset_for_tests(unit.FAHRENHEIT)
    assert unit.format_temperature(45.5) == "113.9 °F"
    assert unit.format_temperature(100, 0) == "212 °F"
    assert unit.format_temperature(None) == "-- °F"
    assert unit.format_temperature_delta(5, 0) == "9 °F"


def test_every_whole_celsius_degree_survives_the_trip_through_fahrenheit():
    for celsius in range(-40, 151):
        shown = unit.to_display_int(celsius, unit.FAHRENHEIT)
        assert unit.from_display_int(shown, unit.FAHRENHEIT) == celsius


def test_sentences_follow_the_unit_and_convert_back_cleanly():
    text = "GPU 45.5 °C · range 30–95 °C · -- °C · Temperature °C"
    shown = unit.localize_temperature_text(text, unit.FAHRENHEIT)
    assert shown == "GPU 113.9 °F · range 86–203 °F · -- °F · Temperature °F"
    assert unit.localize_temperature_text(shown, unit.CELSIUS) == text
    # Already in the chosen unit: untouched, so the pass can run twice.
    assert unit.localize_temperature_text(shown, unit.FAHRENHEIT) == shown
    # Daemon messages write "C" without the degree sign.
    assert unit.localize_temperature_text("GPU 50.0 C -> fan 60%", unit.FAHRENHEIT) == "GPU 122.0 °F -> fan 60%"
    assert unit.localize_temperature_text("Celsius", unit.FAHRENHEIT) == "Celsius"


def test_translations_render_in_the_chosen_unit():
    set_language("es")
    unit.reset_for_tests(unit.FAHRENHEIT)
    assert tr_format("Reading {value} °C", value="60") == "Leyendo 140 °F"
    assert tr("Temperature unit") == "Unidad de temperatura"
    unit.reset_for_tests(unit.CELSIUS)
    assert tr_format("Reading {value} °C", value="60") == "Leyendo 60 °C"


# -------------------------------------------------------------- persistence


def test_celsius_by_default_and_the_choice_is_stored(tmp_path, qtbot):
    settings = _settings(tmp_path)
    assert unit.load_temperature_unit(settings) == unit.CELSIUS
    with qtbot.waitSignal(unit.temperature_unit_notifier().changed) as signal:
        unit.set_temperature_unit("fahrenheit", settings)
    assert signal.args == ["fahrenheit"]
    assert _settings(tmp_path).value(unit.SETTINGS_KEY) == "fahrenheit"
    unit.reset_for_tests()
    assert unit.load_temperature_unit(_settings(tmp_path)) == unit.FAHRENHEIT
    assert unit.normalize_unit("anything else") == unit.CELSIUS


# ---------------------------------------------------------------- controls


def test_settings_general_offers_the_unit_and_applies_it(tmp_path, qtbot):
    settings = _settings(tmp_path)
    page = SettingsPage(
        object(), settings_service=SettingsService(), activity_service=ActivityService(), app_settings=settings,
    )
    qtbot.addWidget(page)
    page._ensure_section("general")
    combo = page.controls[unit.SETTINGS_KEY]
    assert isinstance(combo, QComboBox)
    assert [combo.itemData(index) for index in range(combo.count())] == [unit.CELSIUS, unit.FAHRENHEIT]
    assert combo.currentData() == unit.CELSIUS

    combo.setCurrentIndex(combo.findData(unit.FAHRENHEIT))

    assert unit.temperature_unit() == unit.FAHRENHEIT
    assert settings.value(unit.SETTINGS_KEY) == unit.FAHRENHEIT


def test_the_welcome_language_step_offers_celsius_and_fahrenheit(qtbot):
    window = QWidget()
    window.resize(1300, 860)
    qtbot.addWidget(window)
    panel = WelcomeOverlay(window, temperature_unit="celsius")
    qtbot.addWidget(panel)
    assert panel.temperature_buttons["celsius"].isChecked()
    assert panel.temperature_buttons["fahrenheit"].text() == "°F"

    with qtbot.waitSignal(panel.temperature_unit_chosen) as signal:
        panel.temperature_buttons["fahrenheit"].click()

    assert signal.args == ["fahrenheit"]
    assert panel.temperature_buttons["fahrenheit"].isChecked()
    assert not panel.temperature_buttons["celsius"].isChecked()


# ------------------------------------------------------------- fan curves


def test_a_curve_opened_and_saved_in_fahrenheit_keeps_its_celsius_points(qtbot):
    unit.reset_for_tests(unit.FAHRENHEIT)
    curve = [[40, 30], [61, 50], [73, 75], [82, 100]]
    editor = PointsEditor()
    qtbot.addWidget(editor)
    editor.set_points(curve)

    first = editor._rows[0][0]
    assert first.value() == 104 and first.suffix() == " °F"
    assert editor.points() == curve

    # Edited in °F, saved in °C.
    first.setValue(113)
    assert editor.points()[0] == [45, 30]

    # Switching back shows the same points in °C, without re-rounding them.
    unit.reset_for_tests(unit.CELSIUS)
    editor.refresh_temperature_unit()
    assert first.value() == 45 and first.suffix() == " °C"
    assert editor.points() == [[45, 30], [61, 50], [73, 75], [82, 100]]


def test_spin_box_reads_back_exactly_what_was_set():
    unit.reset_for_tests(unit.FAHRENHEIT)
    spin = TemperatureSpinBox(60, 90, 87)
    assert spin.value() == 189
    assert spin.celsius() == 87
    assert (spin.minimum(), spin.maximum()) == (140, 194)
    hysteresis = TemperatureSpinBox(0, 10, 5, delta=True)
    assert hysteresis.value() == 9 and hysteresis.celsius() == 5


def test_the_curve_chart_tags_the_live_reading_in_fahrenheit(qtbot):
    unit.reset_for_tests(unit.FAHRENHEIT)
    scale = FanCurveScale()
    qtbot.addWidget(scale)
    scale.set_state([(40, 30), (80, 100)], 50.0, 55, True, sensor="gpu")
    assert scale.live_tag() == "GPU 122.0 °F → 55%"


# ------------------------------------------------------------------ pages


def test_readings_and_tables_render_fahrenheit(qtbot):
    unit.reset_for_tests(unit.FAHRENHEIT)
    reading = Reading("GPU")
    qtbot.addWidget(reading)
    reading.set_value("50.0 °C")
    assert (reading.value.text(), reading.unit.text()) == ("122.0", "°F")

    assert format_sensor_value(50.0, "°C") == "122.0 °F"

    model = SampleModel()
    model.set_rows([{"t_gpu": "50", "t_cpu": "61.5", "busy": "40"}])
    columns = [key for _heading, key, _right in BLACKBOX_COLUMNS]
    assert model.data(model.index(0, columns.index("t_gpu"))) == "122"
    assert model.data(model.index(0, columns.index("t_cpu"))) == "142.7"
    assert model.headerData(columns.index("t_gpu"), Qt.Orientation.Horizontal) == "GPU °F"
