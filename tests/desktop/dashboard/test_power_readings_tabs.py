"""The power readings window: one tab per way to get the readings.

The I2C tab keeps the modification guide and its service; the two kernel
tabs explain Hexxeh's drivers and offer to build them where they can be.
"""

from __future__ import annotations

from frontends.desktop.components.i2c_guide import I2cGuideDialog


def _dialog(qtbot, **drivers_state):
    drivers = {key: {"state": value, "reading": 47.0} for key, value in drivers_state.items()}
    dialog = I2cGuideDialog(message="", can_install=True, drivers=drivers)
    qtbot.addWidget(dialog)
    return dialog


def test_the_three_ways_are_tabs(qtbot):
    dialog = _dialog(qtbot)
    assert list(dialog.tab_buttons) == ["i2c", "vrm", "vram"]
    assert dialog.current_tab == "i2c" and dialog.tab_buttons["i2c"].isChecked()


def test_the_i2c_tab_keeps_the_service_install(qtbot):
    dialog = _dialog(qtbot, vrm_sensor="not-installed")
    assert not dialog.install_button.isHidden() and dialog.build_button.isHidden()


def test_a_buildable_driver_offers_to_compile_it(qtbot):
    dialog = _dialog(qtbot, vrm_sensor="not-installed", vram_sensor="unsupported")
    dialog.select_tab("vrm")
    assert not dialog.build_button.isHidden()
    assert dialog.install_button.isHidden() and dialog.settings_button.isHidden()
    dialog.select_tab("vram")
    assert dialog.build_button.isHidden()


def test_compiling_closes_with_the_driver_it_names(qtbot):
    dialog = _dialog(qtbot, vrm_sensor="not-installed", vram_sensor="not-installed")
    dialog.select_tab("vram")
    dialog.build_button.click()
    assert dialog.result() == I2cGuideDialog.BUILD_VRAM


def test_a_kernel_that_carries_it_says_so_with_its_reading(qtbot):
    dialog = _dialog(qtbot, vrm_sensor="managed-elsewhere")
    dialog.select_tab("vrm")
    assert dialog.build_button.isHidden()
    from PyQt6.QtWidgets import QLabel

    page = dialog.pages.widget(dialog.page_index["vrm"])
    texts = " ".join(label.text() for label in page.findChildren(QLabel))
    assert "47 °C" in texts


def test_the_footer_link_follows_the_tab(qtbot):
    dialog = _dialog(qtbot)
    dialog.select_tab("vrm")
    assert dialog._link.endswith("Hexxeh/bc250-vrm-dkms")
    assert "bc250-vrm" in dialog.source_button.text()


def test_an_earlier_build_is_offered_as_an_update(qtbot):
    dialog = _dialog(qtbot, vrm_sensor="update-available")
    dialog.select_tab("vrm")
    assert not dialog.build_button.isHidden()
    assert dialog.build_button.text() in {"Update", "Actualizar"}
    dialog.build_button.click()
    assert dialog.result() == I2cGuideDialog.BUILD_VRM
