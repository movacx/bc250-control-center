"""The black box page: start, stop, and the last rows it recorded, in the Processes look."""

from __future__ import annotations

import pytest

from frontends.desktop.pages.blackbox import COLUMNS, BlackBoxPage


def _row(second: int, **extra):
    row = {"time": f"12:00:{second:02d}.250", "clock": "2000Mhz", "busy": "99%", "t_gpu": "71", "t_cpu": "60",
           "volts": "1050", "watts": "140", "rpm": "fan1:2400", "cpu": "3500", "mem": "9000"}
    return {**row, **extra}


def _state(**changes):
    state = {
        "supported": True, "running": False, "pid": None,
        "autostart": {"supported": True, "enabled": False, "foreign": False},
        "directory": "/home/u/.local/state/bc250-control-center/black-box",
        "state": "none", "state_text": "", "header": "", "rows": [],
    }
    state.update(changes)
    return state


class FakeController:
    def __init__(self, state=None):
        self.state = state or _state()
        self.calls = []

    def blackbox_estado(self, filas=200):
        self.calls.append(("estado", filas))
        return self.state

    def blackbox_iniciar(self):
        self.calls.append(("iniciar",))
        return {"started": True}

    def blackbox_detener(self):
        self.calls.append(("detener",))
        return {"stopped": True}

    def blackbox_con_la_sesion(self, activar):
        self.calls.append(("sesion", activar))
        return {"enabled": activar}


@pytest.fixture()
def page(qtbot):
    controller = FakeController()
    widget = BlackBoxPage(controller)
    qtbot.addWidget(widget)
    widget.resize(1200, 800)
    widget.show()
    return widget


def test_the_table_has_the_columns_of_a_recorded_line(page):
    headings = [page.model.headerData(i, __import__("PyQt6.QtCore", fromlist=["Qt"]).Qt.Orientation.Horizontal)
                for i in range(page.model.columnCount())]
    assert headings == [heading.upper() for heading, _key, _right in COLUMNS]
    assert {"GPU CLOCK", "GPU LOAD", "GPU °C", "CPU °C", "FANS RPM"} <= set(headings)


def test_a_recording_shows_its_rows_newest_first_and_says_it_is_recording(page):
    rows = [_row(3), _row(2), _row(1)]
    page._apply_state(_state(running=True, pid=4242, state="recording", rows=rows))
    assert page.card.status.text() == "Recording"
    assert page.record_button.text() == "Stop recording"
    assert page.model.rowCount() == 3
    assert page.model.index(0, 0).data() == "12:00:03.250"
    assert page.model.index(2, 0).data() == "12:00:01.250"
    assert "Recording now" in page.state_label.text()
    assert "3 rows shown" in page.footer.text()


def test_a_recording_cut_off_by_a_freeze_is_called_out(page):
    page._apply_state(_state(state="cut-off", rows=[_row(9)]))
    assert page.card.status.text() == "Stopped"
    assert "Cut off by a restart or a freeze" in page.state_label.text()
    assert "color" in page.state_label.styleSheet()


def test_nothing_recorded_says_how_to_get_a_recording(page):
    page._apply_state(_state())
    assert page.model.rowCount() == 0
    assert "Start the black box before playing" in page.state_label.text()
    assert page.record_button.text() == "Start recording"


def test_a_missing_sensor_is_a_dash_not_an_empty_cell(page):
    page._apply_state(_state(rows=[_row(1, t_cpu="-", rpm="-")]))
    assert page.model.index(0, 4).data() == "–"
    assert page.model.index(0, 7).data() == "–"


def test_a_board_without_the_gpu_cannot_record(page):
    page._apply_state(_state(supported=False))
    assert page.card.status.text() == "No BC-250 GPU"
    assert not page.record_button.isEnabled()


def test_the_button_starts_and_then_stops_the_recorder(page, qtbot):
    controller = page.controller
    page._apply_state(_state())
    qtbot.mouseClick(page.record_button, __import__("PyQt6.QtCore", fromlist=["Qt"]).Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: ("iniciar",) in controller.calls, timeout=3000)
    # The button stays off until the action is over, so a second click cannot overlap it.
    qtbot.waitUntil(lambda: not page._background.is_running("action"), timeout=3000)
    page._apply_state(_state(running=True, state="recording"))
    assert page.record_button.isEnabled()
    qtbot.mouseClick(page.record_button, __import__("PyQt6.QtCore", fromlist=["Qt"]).Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: ("detener",) in controller.calls, timeout=3000)


def test_the_session_switch_is_offered_only_with_systemd(page):
    page._apply_state(_state())
    assert not page.autostart_switch.isHidden()
    page._apply_state(_state(autostart={"supported": False, "enabled": False, "foreign": False}))
    assert page.autostart_switch.isHidden() and page.autostart_label.isHidden()


def test_a_service_somebody_else_wrote_cannot_be_switched_here(page):
    page._apply_state(_state(autostart={"supported": True, "enabled": False, "foreign": True}))
    assert not page.autostart_switch.isEnabled()


def test_showing_the_state_does_not_toggle_the_service(page):
    page._apply_state(_state(autostart={"supported": True, "enabled": True, "foreign": False}))
    assert page.autostart_switch.isChecked()
    assert [call for call in page.controller.calls if call[0] == "sesion"] == []


def test_the_user_turning_the_switch_on_asks_for_the_service(page, qtbot):
    page._apply_state(_state())
    page.autostart_switch.setChecked(True)
    qtbot.waitUntil(lambda: ("sesion", True) in page.controller.calls, timeout=3000)


def test_updates_run_only_while_the_page_is_on_screen(page):
    page.set_updates_active(True)
    assert page.refresh_timer.isActive()
    page.set_updates_active(False)
    assert not page.refresh_timer.isActive()


def test_a_failed_read_does_not_open_a_window_every_second(page):
    page._status_failed("boom")
    assert page.card.status.text() == "Unavailable"


def test_the_card_has_no_icon_the_title_stands_alone(page):
    """A cleaner page: the sidebar already says where you are."""
    assert page.card._header_icon is None


def test_a_recording_in_progress_always_offers_the_way_to_stop_it(page):
    """The reported case: "Stopped" in the corner, "Recording now" below it, and no Stop button."""
    page._apply_state(_state(running=True, state="recording", rows=[_row(1)]))
    assert page.card.status.text() == "Recording"
    assert page.record_button.text() == "Stop recording"
    assert page.record_button.isEnabled()


def test_the_whole_recording_is_shown_not_only_its_end(page):
    rows = [_row(i % 60, time=f"12:{i // 60:02d}:{i % 60:02d}.000") for i in range(9000, 0, -1)]
    page._apply_state(_state(running=True, state="recording", rows=rows))
    assert page.model.rowCount() == 9000
    assert "9000 rows shown" in page.footer.text()


def test_reading_older_rows_pauses_the_view_until_the_top_is_back(page, qtbot):
    page.resize(1200, 600)
    page._apply_state(_state(running=True, state="recording", rows=[_row(i) for i in range(59, 0, -1)]))
    bar = page.table.verticalScrollBar()
    qtbot.wait(50)  # the view works out its scroll range when its layout settles
    bar.setValue(bar.maximum())
    assert bar.value() > 0
    page._apply_state(_state(running=True, state="recording", rows=[_row(i) for i in range(60, 0, -1)]))
    assert page.model.rowCount() == 59 and not page.paused_label.isHidden()
    bar.setValue(0)
    assert page.model.rowCount() == 60 and page.paused_label.isHidden()


def test_a_stopped_recording_is_not_redrawn_every_second(page):
    rows = [_row(2), _row(1)]
    page._apply_state(_state(state="stopped", rows=rows))
    resets = []
    page.model.modelReset.connect(lambda: resets.append(1))
    page._apply_state(_state(state="stopped", rows=[dict(row) for row in rows]))
    assert resets == []


def test_the_diagnosis_takes_the_tables_place_and_the_button_brings_it_back(qtbot):
    controller = FakeController()
    controller.diagnostico_completo = lambda: [("Kernel", "6.18.7"), ("Previous boot", "clean"), ("Black box", "x")]
    page = BlackBoxPage(controller)
    qtbot.addWidget(page)
    page.resize(1200, 800)
    page.show()
    page._apply_state(_state(rows=[_row(1)]))
    assert page.stack.currentWidget() is page.recording_page
    assert page.diagnosis_view is None  # nothing is collected until it is asked for

    page.diagnosis_button.click()
    assert page.stack.currentWidget() is page.diagnosis_page
    assert page.diagnosis_button.text() == "← Back to the recording"
    qtbot.waitUntil(lambda: len(page.diagnosis_view._sections) == 3, timeout=3000)
    assert page.table.isHidden() or not page.table.isVisibleTo(page)
    assert page.diagnosis_view._sections[0].toggle.text().startswith("▶ Kernel (")

    page.diagnosis_button.click()
    assert page.stack.currentWidget() is page.recording_page
    assert page.diagnosis_button.text() == "View full diagnosis"
    # Asking again does not collect it again.
    page.diagnosis_button.click()
    assert len(page.diagnosis_view._sections) == 3


def test_the_recording_state_line_is_not_shown_over_the_diagnosis(qtbot):
    controller = FakeController()
    controller.diagnostico_completo = lambda: [("Kernel", "x")]
    page = BlackBoxPage(controller)
    qtbot.addWidget(page)
    page.resize(1200, 800)
    page.show()
    page._apply_state(_state(running=True, state="recording", rows=[_row(1)]))
    assert not page.state_label.isHidden()
    page.diagnosis_button.click()
    assert page.state_label.isHidden()
    page.diagnosis_button.click()
    assert not page.state_label.isHidden()


def test_the_button_that_leads_back_is_pale_blue_with_an_arrow(qtbot):
    """The way back must not look like the way in: it was easy to get lost."""
    controller = FakeController()
    controller.diagnostico_completo = lambda: [("Kernel", "x")]
    page = BlackBoxPage(controller)
    qtbot.addWidget(page)
    page.resize(1200, 800)
    page.show()
    assert page.diagnosis_button.property("processButton") == "secondary"
    page.diagnosis_button.click()
    assert page.diagnosis_button.property("processButton") == "back"
    assert page.diagnosis_button.text().startswith("← ")
    assert "QPushButton[processButton='back']" in page.styleSheet()
    page.diagnosis_button.click()
    assert page.diagnosis_button.property("processButton") == "secondary"
    assert not page.diagnosis_button.text().startswith("←")
