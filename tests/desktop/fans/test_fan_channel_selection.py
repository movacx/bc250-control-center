import pytest
from PyQt6.QtCore import QObject, Qt, pyqtSignal

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
    assert page.use_live_button.isEnabled() is False
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
    assert response_map.ranges_title.text() == "Thermal response scale"
    assert "exact step response" in response_map.scale_caption.text()
    assert response_map.live_temperature_label.text() == "GPU 68.2 °C"
    assert response_map.live_duty_label.text() == "PWM 85 %"


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
    assert page.selected_live_rpm.isVisible()
    assert page.selected_live_rpm.text() == "1,200 RPM"


def test_manual_dial_tracks_staged_pwm_and_reflows_without_changing_hardware(qtbot):
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

    page._reflow(1200)
    wide_dial = page.manual_workspace.getItemPosition(page.manual_workspace.indexOf(page.duty_panel))
    wide_controls = page.manual_workspace.getItemPosition(page.manual_workspace.indexOf(page.manual_controls_panel))
    assert wide_dial[:2] == (0, 0)
    assert wide_controls[:2] == (0, 1)

    page._reflow(520)
    narrow_dial = page.manual_workspace.getItemPosition(page.manual_workspace.indexOf(page.duty_panel))
    narrow_controls = page.manual_workspace.getItemPosition(page.manual_workspace.indexOf(page.manual_controls_panel))
    assert narrow_dial[:2] == (0, 0)
    assert narrow_controls[:2] == (1, 0)


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

        assert page.manual_preset_buttons[0].text() == "Silencioso · 45%"
        assert page.manual_preset_buttons[1].text() == "Equilibrado · 60%"
        assert page.duty_eyebrow.text() == "Salida preparada"
        assert page.duty_raw_label.text().startswith("PWM bruto ")
        assert page.duty_metric.label.text() == "Ciclo actual"
        assert page.manual_note.text().startswith("Ciclo preparado:")
        assert page.curve_plot.live_title.text() == "Vista previa de respuesta"
        assert page.curve_plot.ranges_title.text() == "Escala de respuesta térmica"
        assert "respuesta exacta por escalones" in page.curve_plot.scale_caption.text()
    finally:
        set_language(previous_language)
