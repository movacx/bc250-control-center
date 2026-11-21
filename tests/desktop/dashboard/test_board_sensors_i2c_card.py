"""Compatibility › Board sensors lists BC250-Telemetry with the two kernel drivers.

The wired route installs on every distribution its installer covers, so
owners who look for sensors there find it too, not only in Settings.
"""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QDialog

from frontends.desktop.components.dashboard_widgets import PreparationSidebar
from frontends.desktop.core.state import DashboardState


@pytest.fixture
def sidebar(qtbot):
    widget = PreparationSidebar()
    qtbot.addWidget(widget)
    return widget


def _show(sidebar, **accessories):
    sidebar.set_state(DashboardState(preparation_tools={"os_family": "ubuntu", "accessories": accessories}))


def _visible(sidebar, key):
    return {name for name, button in sidebar.accessory_buttons[key].items() if not button.isHidden()}


def test_it_is_one_of_the_board_sensor_cards(sidebar):
    assert sidebar._accessory_cards["apu_telemetry"] is sidebar.apu_telemetry_card
    assert "Author: onlinermm" in sidebar.apu_telemetry_card.detail.text()


def test_not_installed_offers_the_install(sidebar):
    _show(sidebar, apu_telemetry={"state": "not-installed", "device": True})
    install = sidebar.accessory_buttons["apu_telemetry"]["install"]
    assert "install" in _visible(sidebar, "apu_telemetry") and install.isEnabled()
    assert install.text() in {"Install service", "Instalar servicio"}


def test_running_offers_remove_as_the_row_action(sidebar):
    _show(sidebar, apu_telemetry={"state": "active", "device": True, "managed": True})
    assert "remove" in _visible(sidebar, "apu_telemetry")
    remove = sidebar.accessory_buttons["apu_telemetry"]["remove"]
    assert remove.property("rowAction") and remove.text() in {"Remove service", "Quitar servicio"}
    assert "install" not in _visible(sidebar, "apu_telemetry")


def test_where_it_cannot_install_the_card_says_why(sidebar):
    _show(sidebar, apu_telemetry={
        "state": "unsupported", "device": True,
        "blocked_reason": "This kernel already reads the VRM itself (bc250_vrm).",
    })
    # The row keeps its button, greyed, with the reason on hover and in the note.
    install = sidebar.accessory_buttons["apu_telemetry"]["install"]
    assert "install" in _visible(sidebar, "apu_telemetry") and not install.isEnabled()
    assert "bc250_vrm" in install.toolTip()
    assert "bc250_vrm" in sidebar._accessory_notes["apu_telemetry"].text()


def test_installed_by_upstream_is_left_alone(sidebar):
    _show(sidebar, apu_telemetry={"state": "managed-elsewhere", "device": True})
    assert _visible(sidebar, "apu_telemetry") == {"install", "upstream"}
    assert not sidebar.accessory_buttons["apu_telemetry"]["install"].isEnabled()


@pytest.mark.parametrize(("operation", "answer", "calls"), [
    ("install", QDialog.DialogCode.Accepted, ["install"]),
    ("install", QDialog.DialogCode.Rejected, []),
    ("remove", QDialog.DialogCode.Accepted, ["uninstall"]),
])
def test_the_card_runs_the_same_workflow_as_settings(monkeypatch, operation, answer, calls):
    from frontends.desktop.app import ControlCenterWindow
    from frontends.desktop.pages import settings

    class Dialog:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return answer

    monkeypatch.setattr(settings, "ConfirmDialog", Dialog)

    class Controller:
        def __init__(self):
            self.calls = []

        def gestionar_apu_telemetry(self, action):
            self.calls.append(action)

    class Window:
        _ACCESSORY_LINKS = ControlCenterWindow._ACCESSORY_LINKS

        def _accessory_error(self, error):
            raise error

    window = Window()
    window.controller = Controller()
    ControlCenterWindow._dashboard_accessory(window, "apu_telemetry", operation)
    assert window.controller.calls == calls


def test_a_probe_that_failed_says_so_instead_of_checking_forever(sidebar):
    _show(sidebar, vram_sensor={"state": "error", "error": "KeyError: 'x'"})
    assert sidebar.vram_sensor_card.status.text() in {"Could not check", "No se pudo comprobar"}
    assert "KeyError" in sidebar._accessory_notes["vram_sensor"].text()
