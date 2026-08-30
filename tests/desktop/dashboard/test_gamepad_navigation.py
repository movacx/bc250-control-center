from types import SimpleNamespace

from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from frontends.desktop.core.gamepad import (
    ACTION_ACCEPT,
    ACTION_CONTEXT_X,
    ACTION_CONTEXT_Y,
    ACTION_DOWN,
    ACTION_RIGHT,
    EvdevGamepadBackend,
    GamepadNavigationController,
    LinuxJoystickBackend,
)


def _navigation_host(qtbot):
    host = QMainWindow()
    content = QWidget()
    layout = QVBoxLayout(content)
    combo = QComboBox()
    combo.addItems(("1850 MHz", "2000 MHz", "2400 MHz"))
    button = QPushButton("Apply")
    layout.addWidget(combo)
    layout.addWidget(button)
    host.setCentralWidget(content)
    host.resize(640, 360)
    qtbot.addWidget(host)
    host.show()
    navigation = GamepadNavigationController(host, start_worker=False)
    navigation.set_connected_for_testing(True)
    QApplication.processEvents()
    return host, combo, button, navigation


def test_gamepad_can_open_and_choose_a_combo_entry(qtbot):
    _host, combo, _button, navigation = _navigation_host(qtbot)
    combo.setFocus()

    navigation.dispatch_action(ACTION_ACCEPT)
    QApplication.processEvents()
    assert navigation._combo_popup_visible(combo)

    navigation.dispatch_action(ACTION_DOWN)
    navigation.dispatch_action(ACTION_DOWN)
    navigation.dispatch_action(ACTION_ACCEPT)
    QApplication.processEvents()

    assert combo.currentIndex() == 2
    assert not navigation._combo_popup_visible(combo)
    navigation.stop()


def test_explicit_horizontal_group_keeps_controller_inside_tab_row(qtbot):
    host = QMainWindow()
    content = QWidget()
    layout = QVBoxLayout(content)
    tabs = []
    for index, label in enumerate(("Components", "Compatibility", "Decky", "Drivers")):
        button = QPushButton(label)
        button.setProperty("gamepadHorizontalGroup", "preparation-tabs")
        button.setProperty("gamepadHorizontalIndex", index)
        layout.addWidget(button)
        tabs.append(button)
    combo = QComboBox()
    combo.addItems(("Detected", "All"))
    layout.addWidget(combo)
    host.setCentralWidget(content)
    host.resize(640, 420)
    qtbot.addWidget(host)
    host.show()
    navigation = GamepadNavigationController(host, start_worker=False)
    navigation.set_connected_for_testing(True)
    QApplication.processEvents()
    tabs[1].setFocus()
    QApplication.processEvents()

    navigation.dispatch_action(ACTION_RIGHT)
    QApplication.processEvents()
    assert QApplication.focusWidget() is tabs[2]
    navigation.dispatch_action(ACTION_RIGHT)
    QApplication.processEvents()
    assert QApplication.focusWidget() is tabs[3]
    navigation.dispatch_action(ACTION_RIGHT)
    QApplication.processEvents()
    assert QApplication.focusWidget() is tabs[0]
    navigation.stop()


def test_live_layout_requests_do_not_rebuild_gamepad_focus_cache(qtbot):
    host, _combo, button, navigation = _navigation_host(qtbot)
    navigation._focusable_widgets(host, host)
    revision = navigation._focus_cache_revision

    navigation.eventFilter(button, QEvent(QEvent.Type.LayoutRequest))

    assert navigation._focus_cache_revision == revision
    navigation.stop()


def test_enabled_changes_still_invalidate_gamepad_focus_cache(qtbot):
    host, _combo, button, navigation = _navigation_host(qtbot)
    navigation._focusable_widgets(host, host)
    revision = navigation._focus_cache_revision

    navigation.eventFilter(button, QEvent(QEvent.Type.EnabledChange))

    assert navigation._focus_cache_revision == revision + 1
    navigation.stop()


def test_focusable_widgets_are_filtered_and_sorted_by_screen_position(qtbot):
    host = QMainWindow()
    content = QWidget()
    host.setCentralWidget(content)
    lower = QPushButton("Lower", content)
    lower.setGeometry(20, 180, 100, 30)
    upper_right = QPushButton("Upper right", content)
    upper_right.setGeometry(180, 30, 100, 30)
    upper_left = QPushButton("Upper left", content)
    upper_left.setGeometry(20, 30, 100, 30)
    skipped = QPushButton("Skipped", content)
    skipped.setGeometry(20, 100, 100, 30)
    skipped.setProperty("gamepadSkip", True)
    disabled = QPushButton("Disabled", content)
    disabled.setGeometry(180, 100, 100, 30)
    disabled.setEnabled(False)
    host.resize(360, 260)
    qtbot.addWidget(host)
    host.show()
    navigation = GamepadNavigationController(host, start_worker=False)
    navigation.set_connected_for_testing(True)
    QApplication.processEvents()

    candidates = navigation._focusable_widgets(content, host)

    assert candidates == [upper_left, upper_right, lower]
    navigation.stop()


def test_focusable_widget_cache_avoids_rescanning_unchanged_tree(qtbot, monkeypatch):
    host, _combo, _button, navigation = _navigation_host(qtbot)
    expected = navigation._focusable_widgets(host, host)
    monkeypatch.setattr(
        navigation,
        "_normalize_focusables",
        lambda _root: (_ for _ in ()).throw(AssertionError("unexpected rescan")),
    )

    assert navigation._focusable_widgets(host, host) == expected
    navigation.stop()


def test_evdev_xbox_face_buttons_keep_x_and_y_semantics():
    ecodes = SimpleNamespace(
        EV_KEY=1,
        EV_ABS=3,
        BTN_SOUTH=304,
        BTN_EAST=305,
        BTN_NORTH=307,
        BTN_WEST=308,
        BTN_TL=310,
        BTN_TR=311,
        ABS_X=0,
        ABS_Y=1,
        ABS_RY=4,
        ABS_HAT0X=16,
        ABS_HAT0Y=17,
    )
    backend = EvdevGamepadBackend(SimpleNamespace(ecodes=ecodes))

    xbox_x = backend._map_event(SimpleNamespace(type=1, code=307, value=1))
    xbox_y = backend._map_event(SimpleNamespace(type=1, code=308, value=1))

    assert [item.action for item in xbox_x] == [ACTION_CONTEXT_X]
    assert [item.action for item in xbox_y] == [ACTION_CONTEXT_Y]


def test_evdev_poll_failure_disconnects_and_releases_held_axis(monkeypatch):
    class BrokenDevice:
        fd = 9

        def read(self):
            raise RuntimeError("malformed device event")

        def close(self):
            self.closed = True

    backend = EvdevGamepadBackend(SimpleNamespace(ecodes=SimpleNamespace()))
    device = BrokenDevice()
    backend._device = device
    backend._axis_actions = {"left_x": ACTION_RIGHT}
    monkeypatch.setattr(
        "frontends.desktop.core.gamepad.select.select",
        lambda *_args: ([device.fd], [], []),
    )

    events = backend.poll(0)

    assert [(item.action, item.pressed) for item in events] == [(ACTION_RIGHT, False)]
    assert backend._device is None
    assert device.closed is True


def test_joystick_eof_disconnects_and_releases_held_axis(monkeypatch):
    backend = LinuxJoystickBackend()
    backend._fd = 11
    backend._axis_actions = {"left_x": ACTION_RIGHT}
    closed = []
    monkeypatch.setattr(
        "frontends.desktop.core.gamepad.select.select",
        lambda *_args: ([11], [], []),
    )
    monkeypatch.setattr("frontends.desktop.core.gamepad.os.read", lambda *_args: b"")
    monkeypatch.setattr("frontends.desktop.core.gamepad.os.close", closed.append)

    events = backend.poll(0)

    assert [(item.action, item.pressed) for item in events] == [(ACTION_RIGHT, False)]
    assert backend._fd is None
    assert closed == [11]


def test_xbox_x_opens_numeric_keypad_for_focused_input(qtbot):
    host = QMainWindow()
    numeric = QLineEdit("3550")
    numeric.setValidator(QIntValidator(3000, 4200, numeric))
    host.setCentralWidget(numeric)
    host.resize(640, 360)
    qtbot.addWidget(host)
    host.show()
    navigation = GamepadNavigationController(host, start_worker=False)
    navigation.set_connected_for_testing(True, name="Xbox Wireless Controller")
    numeric.setFocus()
    QApplication.processEvents()

    navigation.dispatch_action(ACTION_CONTEXT_X)
    QApplication.processEvents()

    keypad = navigation._keypads.get(id(host))
    assert keypad is not None
    assert keypad.isVisible()
    assert keypad._target is numeric
    navigation.stop()


def test_unified_keypad_setting_opens_automatically_on_gamepad_focus(qtbot):
    host = QMainWindow()
    content = QWidget()
    layout = QVBoxLayout(content)
    button = QPushButton("Before")
    numeric = QLineEdit("3550")
    numeric.setValidator(QIntValidator(3000, 4200, numeric))
    layout.addWidget(button)
    layout.addWidget(numeric)
    host.setCentralWidget(content)
    host.resize(640, 360)
    qtbot.addWidget(host)
    host.show()
    navigation = GamepadNavigationController(host, start_worker=False)
    navigation.set_onscreen_keypad_enabled(True)
    navigation.set_onscreen_keypad_auto_show(True)
    navigation.set_connected_for_testing(True, name="Xbox Wireless Controller")
    button.setFocus()
    QApplication.processEvents()

    numeric.setFocus()
    QApplication.processEvents()

    keypad = navigation._keypads.get(id(host))
    assert keypad is not None
    assert keypad.isVisible()
    assert keypad._target is numeric
    navigation.stop()
