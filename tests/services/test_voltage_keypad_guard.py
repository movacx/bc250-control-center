from PyQt6.QtWidgets import QFrame, QSpinBox

from frontends.desktop.core.voltage_keypad_guard import (
    clear_voltage_keypad_state,
    voltage_keypad_edit_active,
)
from frontends.desktop.pages.gpu_governor import GpuGovernorPage


class _Application:
    def __init__(self, tops=()):
        self.tops = tops

    def topLevelWidgets(self):
        return self.tops


def test_empty_or_untracked_spinboxes_do_not_block_refresh(qtbot):
    spin = QSpinBox()
    qtbot.addWidget(spin)
    assert voltage_keypad_edit_active([], application=_Application()) is False
    assert voltage_keypad_edit_active([spin], application=_Application()) is False


def test_visible_keypad_target_blocks_refresh_without_relying_on_focus(qtbot):
    top = QFrame()
    spin = QSpinBox(top)
    keypad = QFrame(top)
    keypad.setProperty("gamepadKeypad", True)
    keypad._target = spin
    qtbot.addWidget(top)
    top.show()
    keypad.show()

    assert voltage_keypad_edit_active(
        [spin], application=_Application([top])
    ) is True

    keypad.hide()
    assert voltage_keypad_edit_active(
        [spin], application=_Application([top])
    ) is False


def test_clear_keypad_state_restores_keyboard_tracking_and_dismissal(qtbot):
    spin = QSpinBox()
    qtbot.addWidget(spin)
    spin.setKeyboardTracking(False)
    spin.setProperty("gamepadKeypadKeyboardTracking", True)
    spin.setProperty("gamepadKeypadDismissed", True)

    clear_voltage_keypad_state([spin])

    assert spin.keyboardTracking() is True
    assert spin.property("gamepadKeypadKeyboardTracking") is None
    assert spin.property("gamepadKeypadDismissed") is False


def test_real_voltage_lab_passive_refresh_preserves_active_keypad_edit(qtbot):
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)
    page.show()
    page._sync_voltage_lab({
        "safe_points_with_voltage": [
            {"frequency": 1000, "voltage": 800},
            {"frequency": 1850, "voltage": 930},
        ]
    })
    page.voltage_level_combo.setCurrentIndex(
        page.voltage_level_combo.findData(-1)
    )
    spin = page._voltage_spinboxes[1000]
    spin.setValue(825)
    keypad = QFrame(page)
    keypad.setProperty("gamepadKeypad", True)
    keypad._target = spin
    keypad.show()

    page._sync_voltage_lab({
        "safe_points_with_voltage": [
            {"frequency": 1000, "voltage": 700},
            {"frequency": 2000, "voltage": 990},
        ]
    })

    assert page._voltage_points == [(1000, 800), (1850, 930)]
    assert page._voltage_spinboxes[1000] is spin
    assert spin.value() == 825
