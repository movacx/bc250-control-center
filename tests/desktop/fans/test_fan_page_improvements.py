"""Pointer/keyboard integration and calibration proposals on the Fans page."""

from copy import deepcopy

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QDialog, QLineEdit

from frontends.desktop.pages import fans as fans_module
from tests.desktop.fans.test_fan_page import ImmediateTask, make_page, select


@pytest.mark.parametrize("editable", [True, False])
@pytest.mark.parametrize("edge", ["left", "right"])
def test_drag_second_point_updates_draft_between_neighbours(qtbot, monkeypatch, editable, edge):
    page, controller, _ = make_page(qtbot, monkeypatch, config={"fan_channels": {
        "3": {"mode": "curve", "points": [[40, 30], [60, 60], [80, 100]]},
    }})
    select(page, 3)
    editor = page.editor
    # Show the actual editor independently so scrolling the page cannot hide the chart.
    editor.setParent(None)
    qtbot.addWidget(editor)
    editor.resize(850, 1500)
    editor.show()
    editor.plot.set_editable(editable)
    scale = editor.plot.scale
    qtbot.waitUntil(lambda: not scale._plot.isEmpty())
    before = editor.points.points()
    moved = QSignalSpy(editor.plot.point_moved)
    start = scale._point_positions()[1].toPoint()
    destination = QPoint(round(getattr(scale._plot, edge)()), round(scale._plot.center().y()))
    QTest.mousePress(scale, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(scale, destination, delay=10)
    QTest.mouseRelease(scale, Qt.MouseButton.LeftButton, pos=destination)
    after = editor.points.points()
    if editable:
        assert len(moved) >= 1
        assert after[1] == [41 if edge == "left" else 79, 50]
        assert after[0][0] < after[1][0] < after[2][0]
        assert after[0] == before[0] and after[2] == before[2]
        assert editor.dirty and editor.apply_button.isEnabled()
    else:
        assert after == before
        assert not moved and not editor.dirty
    assert scale.dragging is None
    assert controller.saved == controller.writes == []


@pytest.mark.parametrize("duty", [None, 0, 50, 100])
def test_duty_delegate_renders_table_and_exposes_raw_role(qtbot, monkeypatch, duty):
    page, _, _ = make_page(qtbot, monkeypatch)
    table = page.table
    assert isinstance(table.itemDelegateForColumn(fans_module.DUTY), fans_module.DutyDelegate)
    rows = deepcopy(page.model.rows)
    rows[0]["duty"] = duty
    rows[0]["cells"] = list(rows[0]["cells"])
    rows[0]["cells"][fans_module.DUTY] = "—" if duty is None else str(duty)
    page.model.set_rows(rows)
    index = page.model.index(0, fans_module.DUTY)
    assert index.data(page.model.DUTY_ROLE) == duty
    assert page.model.index(0, fans_module.CHANNEL).data(page.model.DUTY_ROLE) is None
    page.resize(1100, 900)
    page.show()
    qtbot.waitUntil(lambda: table.viewport().width() > 100)
    pixmap = QPixmap(table.size())
    pixmap.fill(Qt.GlobalColor.transparent)
    table.render(pixmap)
    assert not pixmap.isNull()


@pytest.mark.parametrize("trigger", ["double_click", "f2"])
def test_inline_rename_calls_service_from_keyboard_editor(qtbot, monkeypatch, trigger):
    page, controller, _ = make_page(qtbot, monkeypatch)
    calls = []
    original = page._channels_service.set_label

    def set_label(pwm, label):
        calls.append((pwm, label))
        return original(pwm, label)

    monkeypatch.setattr(page._channels_service, "set_label", set_label)
    page.resize(1100, 900)
    page.show()
    table = page.table
    index = page.model.index(page.model.row_for(3), fans_module.CHANNEL)
    table.setCurrentIndex(index)
    table.scrollTo(index)
    table.setFocus()
    qtbot.waitUntil(lambda: table.visualRect(index).isValid())
    if trigger == "double_click":
        position = table.visualRect(index).center()
        QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=position)
        QTest.mouseDClick(table.viewport(), Qt.MouseButton.LeftButton, pos=position)
    else:
        QTest.keyClick(table, Qt.Key.Key_F2)
    qtbot.waitUntil(lambda: any(child.isVisible() for child in table.findChildren(QLineEdit)))
    field = next(child for child in table.findChildren(QLineEdit) if child.isVisible())
    QTest.keyClick(field, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(field, "  Case   intake  ")
    QTest.keyClick(field, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: bool(calls))
    assert calls == [(3, "Case intake")]
    assert controller.config["fan_channel_labels"]["3"] == "Case intake"
    assert page.model.data(index, Qt.ItemDataRole.EditRole) == "Case intake"
    for column in range(page.model.columnCount()):
        cell = page.model.index(index.row(), column)
        assert bool(page.model.flags(cell) & Qt.ItemFlag.ItemIsEditable) == (column == fans_module.CHANNEL)
        if column != fans_module.CHANNEL:
            assert not page.model.setData(cell, "unexpected")
    assert calls == [(3, "Case intake")]


@pytest.mark.parametrize("mode,role,visible", [
    ("firmware", "fan", False), ("fixed", "fan", False),
    ("curve", "pump", False), ("curve", "fan", True), ("mix", "fan", True),
])
def test_calibrate_visibility_tracks_mode_and_role(qtbot, monkeypatch, mode, role, visible):
    page, _, _ = make_page(qtbot, monkeypatch)
    select(page, 3, mode)
    page.editor.role.setCurrentIndex(page.editor.role.findData(role))
    assert (not page.editor.calibrate_button.isHidden()) == visible


@pytest.fixture
def calibration_page(qtbot, monkeypatch, tmp_path):
    page, controller, notices = make_page(qtbot, monkeypatch, config={"fan_channels": {
        "3": {"mode": "curve", "points": [[40, 30], [60, 60], [80, 100]]},
    }})
    page.current_state["sensores"]["path"] = str(tmp_path)
    tach = tmp_path / "fan3_input"
    tach.write_text("1200")
    spinning = True
    original = controller.aplicar_pwm_fan

    def write(pwm, raw):
        nonlocal spinning
        assert pwm == 3
        percent = round(raw * 100 / 255)
        if percent < 20:
            spinning = False
        elif percent >= 30:
            spinning = True
        tach.write_text("1200" if spinning else "0")
        return original(pwm, raw)

    monkeypatch.setattr(controller, "aplicar_pwm_fan", write)
    monkeypatch.setattr(fans_module, "_hottest_temperature", lambda: 45.0)
    monkeypatch.setattr(fans_module, "_wait", lambda seconds, cancel: None)
    select(page, 3)
    return page, controller, notices


def test_calibration_confirmation_cancel_does_nothing(calibration_page):
    page, controller, notices = calibration_page
    notices["answer"] = QDialog.DialogCode.Rejected
    before = controller.read_local_config()
    page.editor.calibrate_button.click()
    assert notices["confirms"][-1][0] == "Calibrate this fan"
    assert controller.config == before
    assert controller.writes == controller.saved == []
    assert not page._busy and not page.editor.dirty


def test_calibration_proposes_limits_and_saves_only_on_apply(calibration_page):
    page, controller, notices = calibration_page
    before = controller.read_local_config()
    page.editor.calibrate_button.click()
    assert controller.writes[0] == controller.writes[-1] == (3, 255)
    assert page.editor.min_percent.value() == 25
    assert page.editor.start_percent.value() == 35
    assert page.editor.entry()["min_percent"] == 25
    assert page.editor.entry()["start_percent"] == 35
    assert page.editor.dirty and page.editor.advanced_toggle.isChecked()
    assert controller.config == before and controller.saved == []
    assert notices["dialogs"][-1][0] == "Calibration finished"
    assert "20 %" in notices["dialogs"][-1][1] and "30 %" in notices["dialogs"][-1][1]
    assert not page._busy and page.editor.calibrate_button.text() == "Calibrate"
    page.editor.apply_button.click()
    assert controller.config["fan_channels"]["3"]["min_percent"] == 25
    assert controller.config["fan_channels"]["3"]["start_percent"] == 35
    assert controller.saved and not page.editor.dirty


def test_overheating_aborts_without_proposal(calibration_page, monkeypatch):
    page, controller, notices = calibration_page
    monkeypatch.setattr(fans_module, "_hottest_temperature", lambda: 80.0)
    before = page.editor.entry()
    page.editor.calibrate_button.click()
    assert controller.writes == [(3, 255)]  # final safety write, no measurement
    assert notices["dialogs"][-1] == ("Calibration stopped", "overheating: temperature at or above 80 C")
    assert page.editor.entry() == before and not page.editor.dirty
    assert controller.saved == [] and not page._busy


def test_second_click_cancels_busy_calibration(calibration_page, monkeypatch):
    page, controller, notices = calibration_page

    class DeferredTask(ImmediateTask):
        def start(self):
            pass

    monkeypatch.setattr(fans_module, "FanTask", DeferredTask)
    page.editor.calibrate_button.click()
    worker = page._worker
    assert page._busy and page.editor.calibrate_button.text() == "Cancel"
    assert not page._calibration_cancel.is_set()
    page.editor.calibrate_button.click()
    assert page._calibration_cancel.is_set()
    assert len(notices["confirms"]) == 1
    # Finish through the same synchronous harness, exercising cancellation and cleanup.
    ImmediateTask.start(worker)
    assert controller.writes == [(3, 255)]
    assert notices["dialogs"][-1] == ("Calibration stopped", "cancelled")
    assert not page._busy and controller.saved == []


def test_calibration_and_drag_copy_is_reviewed_in_every_locale():
    """Include indirect dialog summaries and abort reasons missed by the literal scan."""
    import json

    from frontends.desktop.i18n import SUPPORTED_LANGUAGES, tr
    from frontends.desktop.i18n.interface_catalog import INTERFACE_TRANSLATIONS
    from frontends.desktop.i18n.locale_catalog import LOCALE_DIRECTORY

    messages = {
        "Calibrate", "Calibrate this fan", "Cancel", "Cancel calibration",
        "Hottest allowed", "Drag a point to move it.", "Calibration finished",
        "Calibration stopped", "The calibration returned no result.",
        "Keeps turning down to {stop}, starts at {start}. Review the proposal and press Apply.",
        "The fan goes to full speed, then down step by step until it stops, then up until it starts "
        "again. It takes one to two minutes and stops at once if the board reaches 80 °C. "
        "It ends at full speed; nothing is saved until you press Apply.",
        "Measures the lowest PWM at which this fan keeps turning and the one at which it starts, "
        "and proposes them as its minimum and spin-up kick.",
        "cancelled", "pumps are not calibrated: stopping a pump is unsafe",
        "overheating: temperature at or above 80 C", "no tachometer reading",
        "fan did not remain stopped at 0 percent", "fan did not restart at 100 percent",
        "calibration failed: {error}", "final write of 100 percent failed: {error}",
        "step must be an integer in 1..100", "margin must be an integer in 0..100",
        "settle_seconds must be finite and nonnegative", "abort_c must be finite",
        "overheating: temperature at or above {temperature} C",
    }
    for language in SUPPORTED_LANGUAGES:
        catalog = json.loads((LOCALE_DIRECTORY / f"{language}.json").read_text())
        assert messages <= catalog.keys(), (language, messages - catalog.keys())
        for message in messages:
            assert catalog[message].strip(), (language, message)
            assert tr(message, language) == catalog[message], (language, message)
            if message != "Cancel":  # pre-existing shared action
                assert INTERFACE_TRANSLATIONS[message][language] == catalog[message]
            if language != "en":
                assert catalog[message] != message, (language, message)
