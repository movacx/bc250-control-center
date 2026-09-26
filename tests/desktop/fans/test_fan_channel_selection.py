import pytest
from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel

from frontends.desktop.i18n import current_language, localize_widget_tree, set_language
from frontends.desktop.pages import fans as fans_module
from frontends.desktop.pages.fans import FanCurvePlot, FansPage
from frontends.desktop.theme import COLORS


class _Controller:
    def __init__(self):
        self.saved = []

    def guardar_config_local(self, payload):
        self.saved.append(payload)

    def save_local_config(self, payload):
        self.saved.append(payload)


def _fan(index, label, *, root_writable=True, user_writable=False):
    return {
        "index": index,
        "label": label,
        "rpm": 1200 if index == 2 else 0,
        "pwm": 170,
        "pwm_path": f"/sys/class/hwmon/hwmon0/pwm{index}",
        "pwm_user_writable": user_writable,
        "pwm_root_writable": root_writable,
    }


class _ImmediateFanTask(QObject):
    """Execute the page worker synchronously so result handling is testable."""

    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self._operation = operation

    def start(self):
        try:
            self.succeeded.emit(self._operation())
        except Exception as error:  # pragma: no cover - defensive test seam
            self.failed.emit(str(error))
        finally:
            self.finished.emit()


def test_all_detected_pwm_channels_are_selectable_without_hardware_write(qtbot):
    controller = _Controller()
    page = FansPage(controller, settings_service=controller)
    qtbot.addWidget(page)
    page.current_state = {
        "driver_control": True,
        "sensores": {"fans": [_fan(1, "CPU Fan"), _fan(2, "Pump Fan"), _fan(3, "System Fan")]},
        "modulos": {"nct6687": True},
    }

    page._apply_state()

    assert page.channel_combo.isHidden() is False
    assert [page.channel_combo.itemData(i) for i in range(page.channel_combo.count())] == [2, 1, 3]
    page.channel_combo.setCurrentIndex(page.channel_combo.findData(3))
    qtbot.waitUntil(lambda: bool(controller.saved), timeout=2000)
    assert controller.saved[-1]["fan_curve"]["pwm"] == 3
    assert page.channel_combo.currentText().startswith("PWM 3")
    assert not hasattr(page, "selected_channel_title")


def test_channel_change_updates_enabled_static_preset_target(qtbot):
    controller = _Controller()
    page = FansPage(controller, settings_service=controller)
    qtbot.addWidget(page)
    page._fan_preset_config = {
        "enabled": True,
        "preset": "balanced",
        "percent": 60,
        "pwm": 2,
    }
    page.current_state = {
        "driver_control": True,
        "sensores": {"fans": [_fan(2, "Pump Fan"), _fan(4, "System Fan #2")]},
        "modulos": {"nct6687": True},
    }
    page._apply_state()

    page.channel_combo.setCurrentIndex(page.channel_combo.findData(4))
    qtbot.waitUntil(lambda: bool(controller.saved), timeout=2000)

    assert controller.saved[-1]["fan_preset"]["pwm"] == 4
    assert controller.saved[-1]["fan_preset"]["enabled"] is True


def test_single_detected_channel_uses_clean_readout_without_empty_selector(qtbot):
    controller = _Controller()
    page = FansPage(controller, settings_service=controller)
    qtbot.addWidget(page)
    page.current_state = {
        "driver_control": True,
        "sensores": {"fans": [_fan(2, "Pump Fan")]},
        "modulos": {"nct6687": True},
    }

    page._apply_state()

    assert page.channel_combo.count() == 1
    assert page.channel_selector_host.isHidden() is True
    assert page.selected_live_rpm.text() == "1,200 RPM"
    assert page.selected_access.text() == "Authenticated write required"
    assert not hasattr(page, "selected_channel_title")


def test_channel_combo_uses_an_explicit_readable_popup_palette(qtbot):
    page = FansPage(_Controller())
    qtbot.addWidget(page)
    view = page.channel_combo.view()
    palette = view.viewport().palette()

    assert palette.color(palette.ColorRole.Base).name().lower() == COLORS["panel"].lower()
    assert palette.color(palette.ColorRole.Text).name().lower() == COLORS["text"].lower()
    assert palette.color(palette.ColorRole.Base) != palette.color(palette.ColorRole.Text)
    assert "QAbstractItemView" in page.channel_combo.styleSheet()
    assert view.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff


def test_nonfinite_rpm_is_rendered_as_unavailable_without_breaking_page(qtbot):
    page = FansPage(_Controller())
    qtbot.addWidget(page)
    fan = _fan(2, "Pump Fan")
    fan["rpm"] = float("inf")
    page.current_state = {
        "driver_control": True,
        "sensores": {"fans": [fan]},
        "modulos": {"nct6687": True},
    }

    page._apply_state()

    assert page.selected_live_rpm.text() == "-- RPM"


def test_failed_refresh_keeps_last_verified_telemetry_but_blocks_pwm_writes(qtbot):
    page = FansPage(_Controller())
    qtbot.addWidget(page)
    page.current_state = {
        "driver_control": True,
        "sensores": {"fans": [_fan(2, "Pump Fan")]},
        "modulos": {"nct6687": True},
    }
    page._apply_state()

    page._refresh_failed("temporary hwmon read failure")

    assert page.channel_combo.count() == 1
    assert page.selected_live_rpm.text() == "1,200 RPM"
    assert page._fan_control_available() is False
    assert page.apply_pwm_button.isEnabled() is False
    assert page.telemetry_refresh.value.text() == "Last refresh failed"


def test_selected_read_only_pwm_blocks_manual_apply_and_automatic_restore(qtbot):
    page = FansPage(_Controller())
    qtbot.addWidget(page)
    page.current_state = {
        "driver_control": True,
        "sensores": {"fans": [_fan(2, "Read-only Pump", root_writable=False)]},
        "modulos": {"nct6687": True},
    }

    page._apply_state()

    assert page.selected_access.text() == "Read-only channel"
    assert page._selected_channel_writable() is False
    assert page.apply_pwm_button.isEnabled() is False
    assert page.restore_auto_button.isEnabled() is False


def test_directly_writable_pwm_is_not_mislabeled_read_only(qtbot):
    page = FansPage(_Controller())
    qtbot.addWidget(page)
    direct = _fan(2, "Direct PWM", root_writable=False, user_writable=True)
    direct["pwm_writable"] = True
    page.current_state = {
        "driver_control": True,
        "sensores": {"fans": [direct]},
        "modulos": {"nct6687": True},
    }

    page._apply_state()

    assert page.selected_access.text() == "User-writable channel"
    assert page.apply_pwm_button.isEnabled() is True


def test_busy_state_locks_all_mutating_fan_controls(qtbot):
    page = FansPage(_Controller())
    qtbot.addWidget(page)
    page.current_state = {
        "driver_control": True,
        "sensores": {"fans": [_fan(2, "Writable Pump")]},
        "modulos": {"nct6687": True},
    }
    page._apply_state()

    assert page.apply_pwm_button.isEnabled() is True
    page._set_busy(True, "Applying PWM…")

    assert page.channel_combo.isEnabled() is False
    assert page.speed_control.isEnabled() is False
    assert page.apply_pwm_button.isEnabled() is False
    assert page.restore_auto_button.isEnabled() is False
    assert page.manual_mode_button.isEnabled() is False
    assert page.curve_mode_button.isEnabled() is False
    assert page.curve_enabled.isEnabled() is False
    assert page.save_curve_button.isEnabled() is False
    assert page.apply_curve_button.isEnabled() is False
    assert all(not button.isEnabled() for button in page.manual_preset_buttons)
    assert page.curve_editor_toggle.isEnabled() is False
    assert page.add_curve_point_button.isEnabled() is False
    assert page.remove_curve_point_button.isEnabled() is False
    assert all(not button.isEnabled() for button in page.curve_preset_buttons)

    page._set_busy(False, "")

    assert page.channel_combo.isEnabled() is True
    assert page.apply_pwm_button.isEnabled() is True


@pytest.mark.parametrize(
    "result",
    (
        {"pwm": 2, "valor": 153, "verified": None},
        {"pwm": 2, "valor": 153, "verified": {"pwm": 2, "value": 127, "enable": 1}},
    ),
)
def test_pwm_missing_or_mismatched_readback_is_rejected(result):
    error = FansPage._pwm_result_verification_error(result, pwm=2, raw=153)

    assert error


def test_mismatched_pwm_readback_never_runs_the_success_path(qtbot, monkeypatch):
    class Controller(_Controller):
        def aplicar_pwm_fan(self, pwm, raw):
            assert (pwm, raw) == (2, 153)
            return {"pwm": 2, "valor": 153, "verified": {"pwm": 2, "value": 127, "enable": 1}}

    page = FansPage(Controller())
    qtbot.addWidget(page)
    page.current_state = {
        "driver_control": True,
        "sensores": {"fans": [_fan(2, "Writable Pump")]},
        "modulos": {"nct6687": True},
    }
    page._apply_state()
    errors = []
    successes = []
    page._show_error = lambda title, message, **_kwargs: errors.append((title, message))
    page._show_info = lambda *args, **kwargs: successes.append((args, kwargs))
    page._record_event = lambda *_args, **_kwargs: None
    page.refresh = lambda: successes.append((("refresh",), {}))
    monkeypatch.setattr(fans_module, "FanTask", _ImmediateFanTask)

    page._run_pwm_write(2, 60, source="manual")

    assert errors and errors[-1][0] == "Fan PWM operation failed"
    assert "read-back was 127" in errors[-1][1]
    assert successes == []
    assert page._last_pwm_text == "--"
    assert page._busy is False


def test_active_curve_keeps_its_target_when_manual_selector_changes(qtbot):
    controller = _Controller()
    page = FansPage(controller)
    qtbot.addWidget(page)
    page.current_state = {
        "driver_control": True,
        "sensores": {"fans": [_fan(2, "Pump"), _fan(3, "System Fan")]},
        "modulos": {"nct6687": True},
    }
    page._apply_state()
    page._curve_target_pwm = 2
    page.curve_enabled.blockSignals(True)
    page.curve_enabled.setChecked(True)
    page.curve_enabled.blockSignals(False)
    controller.saved.clear()

    page.channel_combo.setCurrentIndex(page.channel_combo.findData(3))
    qtbot.wait(10)

    assert page.channel_combo.currentData() == 3
    assert page._curve_target_pwm == 2
    assert page._curve_config()["pwm"] == 2
    assert controller.saved == []


def test_automatic_curve_presets_and_editor_stay_locked_until_enabled(qtbot):
    page = FansPage(_Controller())
    qtbot.addWidget(page)
    page.current_state = {
        "driver_control": True,
        "sensores": {"fans": [_fan(2, "Pump")]},
        "modulos": {"nct6687": True},
    }
    page._apply_state()

    assert page.curve_enabled.isChecked() is False
    assert all(not button.isEnabled() for button in page.curve_preset_buttons)
    assert page.curve_editor_toggle.isEnabled() is False
    assert page.add_curve_point_button.isEnabled() is False
    assert page.remove_curve_point_button.isEnabled() is False

    page.curve_enabled.setChecked(True)
    qtbot.waitUntil(lambda: all(button.isEnabled() for button in page.curve_preset_buttons))

    assert page.curve_editor_toggle.isEnabled() is True
    assert page.add_curve_point_button.isEnabled() is True
    # Three points is the protected minimum; the control is unlocked by the
    # automatic-curve state but still correctly unavailable at that limit.
    assert page.remove_curve_point_button.isEnabled() is False


def test_disabled_curve_rejects_programmatic_preset_without_mutating_or_persisting(qtbot):
    controller = _Controller()
    page = FansPage(controller)
    qtbot.addWidget(page)
    page.current_state = {
        "driver_control": True,
        "sensores": {"fans": [_fan(2, "Pump")]},
        "modulos": {"nct6687": True},
    }
    page._apply_state()
    before = page._curve_points_values()
    controller.saved.clear()

    page._apply_curve_preset("aggressive")
    qtbot.wait(20)

    assert page._curve_points_values() == before
    assert controller.saved == []


def test_curve_response_map_matches_the_controller_step_ranges(qtbot):
    response_map = FanCurvePlot()
    qtbot.addWidget(response_map)
    response_map.resize(720, 180)
    response_map.show()
    response_map.set_curve([(50, 60), (65, 85), (72, 100)])
    response_map.set_enabled(True)
    response_map.set_live(68.2, 85)
    qtbot.wait(5)

    assert response_map.scale.points == [(50, 60), (65, 85), (72, 100)]
    assert response_map.scale.live_temperature == 68.2
    assert response_map.scale.live_duty == 85
    assert response_map.scale.enabled is True
    # The chart carries its own reading; no caption rows around it.
    assert response_map.live_text() == "68.2 °C → 85%"
    assert response_map.findChildren(QLabel) == []
    assert response_map.scale.minimumHeight() >= 300


def test_curve_response_axis_follows_the_points_it_has_to_show(qtbot):
    response_map = FanCurvePlot()
    qtbot.addWidget(response_map)
    response_map.set_curve([(30, 30), (40, 40), (50, 55), (60, 70), (70, 85), (80, 95), (90, 100), (100, 100)])
    low, high = response_map.scale.temperature_range()
    assert (low, high) == (25.0, 105.0)
    response_map.set_curve([(50, 60), (65, 85), (72, 100)])
    assert response_map.scale.temperature_range() == (30.0, 95.0)
    response_map.set_live(61.4, 85, "cpu")
    assert response_map.live_text() == "CPU 61.4 °C → 85%"


def test_manual_workspace_uses_no_redundant_heading_or_rpm_caption(qtbot):
    page = FansPage(_Controller())
    qtbot.addWidget(page)
    page.current_state = {
        "driver_control": True,
        "sensores": {"fans": [_fan(2, "Pump"), _fan(3, "System")]},
        "modulos": {"nct6687": True},
    }
    page._apply_state()
    page.show()
    qtbot.wait(5)

    visible_copy = [
        label.text()
        for label in page.manual_card.findChildren(fans_module.QLabel)
        if label.isVisible()
    ]
    assert "Fan control" not in visible_copy
    assert "Stage one change, then confirm it." not in visible_copy
    assert "RPM observed" not in visible_copy
    # The speed is a row of the fan list, number and unit in their columns.
    assert page.speed_reading.isVisible()
    assert (page.speed_reading.value.text(), page.speed_reading.unit.text()) == ("1,200", "RPM")
    assert page.selected_live_rpm.text() == "1,200 RPM"


def test_staged_duty_readout_and_card_reflow_never_touch_hardware(qtbot):
    controller = _Controller()
    page = FansPage(controller)
    qtbot.addWidget(page)
    page.current_state = {
        "driver_control": True,
        "sensores": {"fans": [_fan(2, "Pump"), _fan(3, "System")]},
        "modulos": {"nct6687": True},
    }
    page._apply_state()

    page._set_staged_pwm_percent(60)
    assert round(page.duty_gauge.displayValue) == 60
    assert page.duty_channel_label.text() == "PWM 2"
    assert page.duty_raw_label.text() == "Raw PWM 153 / 255"
    assert controller.saved == []

    # The redesign drew the staged value once, beside the slider, and gave
    # the controls the full width: the dial is a data seam now, not a panel.
    page.show()
    for width in (1400, 1200, 520):
        page._reflow(width)
        assert page.duty_panel.isHidden()
        controls = page.manual_workspace.getItemPosition(
            page.manual_workspace.indexOf(page.manual_controls_panel)
        )
        assert controls[:2] == (0, 0)

    # Side by side above the shared GPU/CPU breakpoint, stacked below it.
    page._reflow(1400)
    assert page.workspace_grid.getItemPosition(
        page.workspace_grid.indexOf(page.cooling_card)
    )[:2] == (0, 1)
    page._reflow(900)
    assert page.workspace_grid.getItemPosition(
        page.workspace_grid.indexOf(page.cooling_card)
    )[:2] == (1, 0)
    assert controller.saved == []


def test_automatic_curve_does_not_write_when_hardware_already_matches(qtbot):
    """GitHub issue: fan PWM asked to authenticate on every boot/page visit.

    A fresh app launch has no memory of what it last applied, so before this
    fix the very first refresh always compared its target against ``None``
    and wrote unconditionally -- even right after a boot-time service had
    already restored the exact same duty, opening an unnecessary polkit
    prompt just from entering the Fans page. The observed (privilege-free)
    hwmon readback must be used to seed that baseline instead.
    """
    controller = _Controller()
    page = FansPage(controller, settings_service=controller)
    qtbot.addWidget(page)

    page.current_state = {
        "driver_control": True,
        # 178/255 rounds to 70%, matching what the default curve computes
        # for a 52 C reading -- exactly as a boot-time restore would leave it.
        "sensores": {"fans": [_fan(2, "Pump Fan", root_writable=True)]},
        "modulos": {"nct6687": True},
    }
    page.current_state["sensores"]["fans"][0]["pwm"] = 178
    page.performance_state = {"gpu_temp": 52.0}
    page._curve_target_pwm = 2
    page.curve_enabled.setChecked(True)

    writes = []
    page._run_pwm_write = lambda pwm, percent, **kwargs: writes.append((pwm, percent, kwargs))

    assert page._last_curve_percent is None
    page._maybe_apply_curve()

    assert writes == [], f"unnecessary privileged write on page entry: {writes}"
    assert page._last_curve_percent == 70


def test_automatic_curve_still_applies_a_genuinely_different_target(qtbot):
    controller = _Controller()
    page = FansPage(controller, settings_service=controller)
    qtbot.addWidget(page)

    page.current_state = {
        "driver_control": True,
        "sensores": {"fans": [_fan(2, "Pump Fan", root_writable=True)]},
        "modulos": {"nct6687": True},
    }
    page.current_state["sensores"]["fans"][0]["pwm"] = 102  # stale 40%
    page.performance_state = {"gpu_temp": 75.0}  # curve now calls for 100%
    page._curve_target_pwm = 2
    page.curve_enabled.setChecked(True)

    writes = []
    page._run_pwm_write = lambda pwm, percent, **kwargs: writes.append((pwm, percent, kwargs))

    page._maybe_apply_curve()

    assert len(writes) == 1
    assert writes[0][0] == 2
    assert writes[0][1] == 100


def test_dynamic_cooling_copy_retranslates_after_a_live_language_change(qtbot):
    previous_language = current_language()
    try:
        set_language("en")
        page = FansPage(_Controller())
        qtbot.addWidget(page)
        page.current_state = {
            "driver_control": True,
            "sensores": {"fans": [_fan(2, "Pump Fan")]},
            "modulos": {"nct6687": True},
        }
        page._apply_state()

        set_language("es")
        localize_widget_tree(page, "es")
        page.retranslate_dynamic_copy()

        assert page.manual_preset_buttons[0]._name_label.text() == "Silencioso"
        assert page.manual_preset_buttons[1]._name_label.text() == "Equilibrado"
        assert page.manual_preset_buttons[1]._detail_label.text().startswith("PWM bruto ")
        assert page.restore_auto_button.text() == "Volver al control de la BIOS"
        assert page.duty_eyebrow.text() == "Salida preparada"
        assert page.duty_raw_label.text().startswith("PWM bruto ")
        assert page.duty_metric.label.text() == "Ciclo actual"
        assert page.manual_note.text().startswith("Ciclo preparado:")
        assert page.system_control_button.text() in {"Activar", "Desactivar"}
    finally:
        set_language(previous_language)
