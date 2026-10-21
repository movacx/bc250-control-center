"""The I2C modification guide: where the two wires go, with photos.

Owners asked for pictures before touching the board. The photos and research
are BC250-Telemetry's (MIT); they ship with the app without camera metadata,
and the guide credits and links the original.
"""

from __future__ import annotations

from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QLabel, QPushButton

from frontends.desktop.components import i2c_guide
from frontends.desktop.components.i2c_guide import IMAGES, I2cGuideDialog

PHOTOS = ("i2c-header1-pins.jpg", "tpms1-pins.jpg", "tpms1-connected.jpg", "i2c-header1-connected.jpg")


def test_every_photo_ships_and_loads_without_camera_metadata(qtbot):
    for name in PHOTOS:
        path = IMAGES / name
        assert not QPixmap(str(path)).isNull(), name
        assert b"Exif" not in path.read_bytes()[:4096], f"{name} still carries EXIF"
    notice = (IMAGES / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in notice and "onlinermm, fansteori" in notice


def test_the_guide_names_the_exact_pins_and_credits_its_source(qtbot):
    dialog = I2cGuideDialog()
    qtbot.addWidget(dialog)
    text = " ".join(label.text() for label in dialog.findChildren(QLabel))
    cells = [label.text() for label in dialog.findChildren(QLabel) if label.objectName() == "DialogIdentityValue"]
    assert cells == ["SCL (red)", "Pin 4", "SMB_CLK_MAIN", "SDA (blue)", "Pin 6", "SMB_DATA_MAIN"]
    assert "BC250-Telemetry" in text and "MIT" in text
    photos = [label for label in dialog.findChildren(QLabel) if label.objectName() == "GuidePhoto"]
    assert len(photos) == len(PHOTOS) and all(not photo.pixmap().isNull() for photo in photos)


def test_the_credit_button_opens_the_original_guide(qtbot, monkeypatch):
    opened = []
    monkeypatch.setattr(i2c_guide, "open_external_url", lambda url: (opened.append(url), (True, ""))[1])
    dialog = I2cGuideDialog()
    qtbot.addWidget(dialog)
    dialog.source_button.click()
    assert opened == [i2c_guide.GUIDE_URL]


def test_the_guide_can_go_straight_to_the_telemetry_settings(qtbot):
    dialog = I2cGuideDialog()
    qtbot.addWidget(dialog)
    button = next(b for b in dialog.findChildren(QPushButton) if b.objectName() == "DialogPrimary")
    button.click()
    assert dialog.result() == I2cGuideDialog.TELEMETRY


def test_the_status_of_this_board_heads_the_left_panel(qtbot):
    dialog = I2cGuideDialog(message="Your kernel reads the voltage regulator itself.")
    qtbot.addWidget(dialog)
    texts = [label.text() for label in dialog.findChildren(QLabel)]
    assert "Your kernel reads the voltage regulator itself." in texts


def test_the_install_button_shows_only_when_it_can_install(qtbot):
    offered = I2cGuideDialog(can_install=True)
    hidden = I2cGuideDialog()
    qtbot.addWidget(offered)
    qtbot.addWidget(hidden)
    assert offered.install_button.isVisibleTo(offered) and not hidden.install_button.isVisibleTo(hidden)
    offered.install_button.click()
    assert offered.result() == I2cGuideDialog.INSTALL


def test_the_dashboard_routes_the_install_to_settings(qtbot, monkeypatch):
    import frontends.desktop.pages.dashboard as dashboard_module

    class Dialog:
        TELEMETRY = I2cGuideDialog.TELEMETRY
        INSTALL = I2cGuideDialog.INSTALL

        def __init__(self, parent, *, message, can_install):
            pass

        def exec(self):
            return self.INSTALL

    monkeypatch.setattr(dashboard_module, "I2cGuideDialog", Dialog)
    monkeypatch.setattr(dashboard_module, "kernel_vrm_driver_present", lambda: False)
    monkeypatch.setattr(dashboard_module, "sondear_telemetria_vrm", lambda: {"daemon": "missing"})
    routed = []

    class Signal:
        def emit(self, value):
            routed.append(value)

    fake = type("Fake", (), {"action_requested": Signal()})()
    dashboard_module.DashboardPage._show_vrm_help(fake)
    assert routed == ["telemetry_install"]
