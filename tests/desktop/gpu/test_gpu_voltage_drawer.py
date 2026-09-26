from PyQt6.QtCore import QAbstractAnimation
from PyQt6.QtWidgets import QDialog, QSpinBox, QWidget

import frontends.desktop.pages.gpu_governor as gpu_governor_module
from frontends.desktop.components.voltage_lab_drawer import VoltageLabDrawer
from frontends.desktop.pages.gpu_governor import GpuGovernorPage


def _gpu_state():
    return {
        "governor_backend": "cyan-skillfish-governor-smu",
        "service_active": "active",
        "service_enabled": "enabled",
        "dbus_ok": True,
        "range_control_ok": True,
        "sclk_actual": 1850,
        "voltaje_actual": 930,
        "gpu_busy": 32,
        "current_min": 1000,
        "current_max": 1850,
        "safe_points_with_voltage": [
            {"frequency": 1000, "voltage": 800},
            {"frequency": 1850, "voltage": 930},
            {"frequency": 2000, "voltage": 960},
        ],
    }


def _settle(qtbot, drawer):
    """Wait for the slide animation to actually stop.

    ``qWait(duration + margin)`` is a race: under full-suite load the final
    frame can land after the budget, leaving the drawer parked at its start
    offset and the assertions reading animation state instead of layout.
    """
    qtbot.waitUntil(
        lambda: drawer._animation.state() != QAbstractAnimation.State.Running,
        timeout=5000,
    )
    qtbot.wait(20)

def test_gpu_voltage_button_opens_the_drawer_and_leaves_the_overview_in_place(qtbot):
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)
    page.resize(1280, 800)
    page.show()
    page.current_state = _gpu_state()
    page.current_perf = {"gpu_temp": 61.5, "gpu_busy": 32}

    page.open_voltage_lab()

    # The drawer floats over the overview. There used to be a second, full-page
    # voltage laboratory in the stack as well; nothing could reach it, because
    # this very method returns the stack to the overview before opening the
    # drawer. It has been removed rather than left as a screen with no door.
    assert not hasattr(page, "voltage_lab_page")
    assert page.page_stack.count() == 1
    assert page.page_stack.currentWidget() is page.overview_page
    assert page.voltage_lab_drawer.is_open()
    assert set(page.voltage_lab_drawer.profile_buttons) == {1, 2, 3, -1}
    assert not hasattr(page.voltage_lab_drawer, "metrics")
    assert not hasattr(page.voltage_lab_drawer, "refresh_button")
    # A narrow side panel: the GPU page stays readable beside it.
    assert page.voltage_lab_drawer.drawer.width() == min(
        500, max(420, round(page.width() * 0.36))
    )
    # The redesign sizes the preset row from the QSS instead of a fixed height,
    # so assert the row is uniform and reasonable rather than one exact pixel
    # value that any spacing change would invalidate.
    preset_heights = {
        button.height() for button in page.voltage_lab_drawer.profile_buttons.values()
    }
    assert len(preset_heights) == 1
    assert 40 <= preset_heights.pop() <= 64
    assert page.gamepad_focus_scope() is page.voltage_lab_drawer.drawer
    assert page.voltage_lab_button.text() == "Open voltage laboratory"


def test_voltage_drawer_profiles_preview_exact_10_to_30_mv_ladder(qtbot):
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)
    page.current_state = _gpu_state()
    page.current_perf = {"gpu_temp": 61.5}
    page._sync_voltage_lab(page.current_state)

    for level in range(1, 4):
        page._select_drawer_voltage_profile(level)
        assert page.voltage_lab_drawer.selected_level() == level
        assert f"+{level * 10} mV" in page.voltage_lab_drawer.profile_detail.text()


def test_unchanged_voltage_refresh_reuses_curve_widgets(qtbot):
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)
    page.current_state = _gpu_state()
    page.current_perf = {}
    page._sync_voltage_lab(page.current_state)

    drawer = page.voltage_lab_drawer
    first = tuple(
        drawer.curve_rows.itemAt(index).widget()
        for index in range(drawer.curve_rows.count())
    )
    page._sync_voltage_drawer()
    second = tuple(
        drawer.curve_rows.itemAt(index).widget()
        for index in range(drawer.curve_rows.count())
    )

    assert second == first


def test_voltage_drawer_stacks_controls_in_a_narrow_window(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(360, 700)
    host.show()
    drawer = VoltageLabDrawer(host)

    drawer.show_animated()
    _settle(qtbot, drawer)

    # The drawer fills a narrow host: at 360 px the boost levels fall to two
    # columns and the footer buttons stack instead of squeezing side by side.
    assert drawer._profile_columns < 4
    assert drawer._footer_horizontal is False
    assert drawer.drawer.geometry().left() == 5
    assert drawer.drawer.geometry().right() == host.width() - 2
    assert drawer.drawer.geometry().bottom() == host.height() - 1


def test_voltage_drawer_custom_mode_reuses_active_point_values(qtbot):
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)
    page.current_state = _gpu_state()
    page.current_perf = {"gpu_temp": 61.5}
    page._sync_voltage_lab(page.current_state)

    page._select_drawer_voltage_profile(-1)

    assert set(page.voltage_lab_drawer.custom_values()) == {1000, 1850, 2000}
    assert all(
        isinstance(editor, QSpinBox)
        for editor in page.voltage_lab_drawer.editors()
    )
    assert "safe points currently active" in page.voltage_lab_drawer.profile_detail.text()


def test_voltage_drawer_controller_back_and_reopen_do_not_close_it_again(qtbot):
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)
    page.resize(1280, 800)
    page.show()
    page.current_state = _gpu_state()
    page.current_perf = {"gpu_temp": 61.5, "gpu_busy": 32}
    page.open_voltage_lab()

    _settle(qtbot, page.voltage_lab_drawer)
    assert page.gamepad_back() is True
    _settle(qtbot, page.voltage_lab_drawer)
    assert not page.voltage_lab_drawer.is_open()

    page.open_voltage_lab()
    _settle(qtbot, page.voltage_lab_drawer)
    assert page.voltage_lab_drawer.is_open()


def test_voltage_drawer_oberon_is_read_only_and_shows_only_real_endpoints(qtbot):
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)
    page.resize(1280, 800)
    page.show()
    page.current_state = {
        "governor_backend": "oberon-governor",
        "service_active": "active",
        "current_min": 1000,
        "current_max": 1850,
        "safe_points_with_voltage": [
            {"frequency": 1000, "voltage": 800},
            {"frequency": 1850, "voltage": 930},
        ],
    }
    page.current_perf = {}

    page._sync_voltage_lab(page.current_state)
    page.open_voltage_lab()

    drawer = page.voltage_lab_drawer
    assert drawer.compatibility_note.isVisible()
    assert drawer.profiles_card.isHidden()
    assert drawer.footer.isHidden()
    assert drawer.editors() == ()
    labels = [label.text() for label in drawer.findChildren(type(drawer.profile_detail))]
    assert "800 mV" in labels
    assert "930 mV" in labels


def test_steamos_use_active_range_action_persists_the_live_range(qtbot):
    calls = []

    class Controller:
        def guardar_rango_gpu_arranque(self):
            calls.append("save")
            return "Saved active range 1000-1850 MHz for Cyan startup."

    class AcceptedDialog:
        def __init__(self, *_args, **_kwargs):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

    page = GpuGovernorPage(Controller())
    qtbot.addWidget(page)
    page.current_state = {
        **_gpu_state(),
        "tools": {"os_family": "steamos"},
    }
    page._run_backend_action = (
        lambda operation, success, _title, **_kwargs: success(operation()) or True
    )
    original_dialog = gpu_governor_module.ConfirmDialog
    gpu_governor_module.ConfirmDialog = AcceptedDialog
    try:
        page._use_active_range()
    finally:
        gpu_governor_module.ConfirmDialog = original_dialog

    assert calls == ["save"]
    assert "1000-1850 MHz" in page._last_operation_summary


def test_non_steamos_uses_the_same_startup_range_persistence_action(qtbot):
    calls = []

    class Controller:
        def guardar_rango_gpu_arranque(self):
            calls.append("save")
            return "Saved active range 1000-1850 MHz for Cyan startup."

    class AcceptedDialog:
        def __init__(self, *_args, **_kwargs):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

    page = GpuGovernorPage(Controller())
    qtbot.addWidget(page)
    page.current_state = {
        **_gpu_state(),
        "tools": {"os_family": "arch"},
    }
    page._run_backend_action = (
        lambda operation, success, _title, **_kwargs: success(operation()) or True
    )
    original_dialog = gpu_governor_module.ConfirmDialog
    gpu_governor_module.ConfirmDialog = AcceptedDialog
    try:
        page._use_active_range()
    finally:
        gpu_governor_module.ConfirmDialog = original_dialog

    assert calls == ["save"]


# ------------------------------------------------ what the laboratory keeps
# Reported on a real board: a +30 mV curve that had been applied and saved
# looked as if it had not been, edits vanished while being typed, scrolling the
# table changed voltages, and Custom offered a curve older than the one on disk.

from PyQt6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QWheelEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from bc250cc.domain.gpu.voltage_profiles import voltage_profile  # noqa: E402

#: The curve the board carries with the +2000 MHz points switched off.
_UP_TO_2000 = (500, 1000, 1175, 1500, 1600, 1700, 1850, 2000)


def _cyan(curve):
    return {
        "governor_backend": "cyan-skillfish-governor-smu",
        "service_active": "active",
        "current_min": 1000,
        "current_max": 1850,
        "safe_points_with_voltage": [
            {"frequency": frequency, "voltage": voltage} for frequency, voltage in curve.items()
        ],
    }


def _level(level):
    profile = voltage_profile(level)
    return {frequency: profile[frequency] for frequency in _UP_TO_2000}


def _open(qtbot, curve):
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)
    page.resize(1280, 800)
    page.show()
    page.current_state = _cyan(curve)
    page.current_perf = {}
    page.open_voltage_lab()
    return page


def test_the_laboratory_opens_on_the_level_the_board_runs(qtbot):
    for level in (1, 2, 3):
        assert _open(qtbot, _level(level)).voltage_lab_drawer.selected_level() == level
    # The packaged curve has no boost to show: the first level is offered.
    assert _open(qtbot, _level(0)).voltage_lab_drawer.selected_level() == 1
    # A curve of its own, or a level without a button, is shown point by point.
    own = {**_level(0), 1850: 945}
    assert _open(qtbot, own).voltage_lab_drawer.selected_level() == -1
    assert _open(qtbot, _level(5)).voltage_lab_drawer.selected_level() == -1


def test_a_choice_made_in_the_open_laboratory_survives_a_refresh(qtbot):
    page = _open(qtbot, _level(3))
    page._select_drawer_voltage_profile(1)
    page._sync_voltage_lab(_cyan(_level(3)))
    assert page.voltage_lab_drawer.selected_level() == 1


def test_a_refresh_leaves_the_field_being_edited_alone(qtbot):
    page = _open(qtbot, _level(3))
    page._select_drawer_voltage_profile(-1)
    drawer = page.voltage_lab_drawer
    field = drawer._editors[1850]
    field.setFocus()
    field.setValue(940)

    page._sync_voltage_lab(_cyan(_level(3)))  # the page's three-second refresh

    assert drawer._editors[1850] is field
    assert field.value() == 940
    assert drawer.custom_values()[1850] == 940


def test_values_on_disk_reach_the_rows_without_replacing_them(qtbot):
    page = _open(qtbot, _level(3))
    page._select_drawer_voltage_profile(-1)
    drawer = page.voltage_lab_drawer
    rows = [drawer.curve_rows.itemAt(index).widget() for index in range(drawer.curve_rows.count())]

    page._sync_voltage_lab(_cyan(_level(1)))

    assert [drawer.curve_rows.itemAt(index).widget() for index in range(drawer.curve_rows.count())] == rows
    assert drawer._editors[2000].value() == _level(1)[2000]
    assert drawer._editors[2000].parentWidget().current_label.text() == f"{_level(1)[2000]} mV"


def _wheel(widget):
    event = QWheelEvent(
        QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False,
    )
    QApplication.sendEvent(widget, event)


def test_the_wheel_scrolls_the_table_instead_of_changing_a_voltage(qtbot):
    page = _open(qtbot, _level(0))
    page._select_drawer_voltage_profile(-1)
    field = page.voltage_lab_drawer._editors[1000]
    page.voltage_lab_drawer.close_button.setFocus()

    _wheel(field)
    assert field.value() == 800

    field.setFocus()
    qtbot.waitUntil(field.hasFocus)
    _wheel(field)
    assert field.value() != 800, "a field that was chosen still takes the wheel"


def test_custom_follows_the_curve_on_disk_except_what_was_typed(qtbot, monkeypatch):
    page = _open(qtbot, _level(3))
    page._select_drawer_voltage_profile(-1)
    page.voltage_lab_drawer._editors[1850].setValue(940)

    # +10 applied from somewhere else: the untouched points follow the file,
    # the typed one keeps what was typed.
    page._sync_voltage_lab(_cyan(_level(1)))
    values = page.voltage_lab_drawer.custom_values()
    assert values[2000] == _level(1)[2000]
    assert values[1850] == 940

    # Closing and opening again shows the draft, not a preset.
    page.open_voltage_lab()
    assert page.voltage_lab_drawer.selected_level() == -1

    # Once applied, the draft is on disk and the editor follows the file again.
    successes = []
    page._run_backend_action = lambda operation, success, *_a, **_k: successes.append(success)
    page._show_info = lambda *_args, **_kwargs: None
    page._append_console = lambda *_args, **_kwargs: None
    monkeypatch.setattr(gpu_governor_module, "ConfirmDialog", _Accepted)
    page._request_apply_voltage_curve_from_drawer()
    successes[0]("ok")
    page.current_state = _cyan(_level(2))
    page._sync_voltage_lab(page.current_state)
    assert page.voltage_lab_drawer.custom_values()[1850] == _level(2)[1850]
    page.open_voltage_lab()
    assert page.voltage_lab_drawer.selected_level() == 2


class _Accepted:
    def __init__(self, *_args, **_kwargs):
        pass

    def exec(self):
        return QDialog.DialogCode.Accepted
