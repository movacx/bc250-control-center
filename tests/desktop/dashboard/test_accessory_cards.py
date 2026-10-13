"""The Drivers tab's case accessory cards, and what their buttons start."""

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
    sidebar.set_state(DashboardState(preparation_tools={"os_family": "cachyos", "accessories": accessories}))


def _visible(sidebar, key):
    return {name for name, button in sidebar.accessory_buttons[key].items() if not button.isHidden()}


def test_before_the_inventory_the_cards_only_link_upstream(sidebar):
    _show(sidebar)
    assert _visible(sidebar, "thermalright") == {"upstream"}
    assert sidebar.thermalright_card.status.text() == "Checking"


def test_a_detected_device_without_software_offers_the_install(sidebar):
    _show(sidebar, thermalright={"state": "not-installed", "device": True}, corsair={"state": "not-installed"})
    assert sidebar.thermalright_card.status.text() == "Device detected"
    assert sidebar.corsair_card.status.text() == "Not installed"
    assert _visible(sidebar, "thermalright") == {"install", "upstream"}


def test_a_working_accessory_offers_its_configuration_first(sidebar):
    _show(sidebar, thermalright={"state": "active", "device": True})
    assert sidebar.thermalright_card.status.text() == "Active"
    assert _visible(sidebar, "thermalright") == {"configure", "remove", "upstream"}
    configure = sidebar.accessory_buttons["thermalright"]["configure"]
    assert configure.text() == "Open configuration" and configure.property("accented")


def test_what_a_state_asks_of_the_owner_is_said_on_the_card(sidebar):
    _show(sidebar, corsair={"state": "relogin-required", "device": True})
    note = sidebar._accessory_notes["corsair"]
    assert not note.isHidden() and "Log out" in note.text()
    assert not sidebar.accessory_buttons["corsair"]["configure"].isEnabled()
    _show(sidebar, thermalright={"state": "active", "device": False})
    assert "Nothing is plugged in" in sidebar._accessory_notes["thermalright"].text()


def test_an_install_made_elsewhere_is_only_opened(sidebar):
    _show(sidebar, corsair={"state": "managed-elsewhere"})
    assert _visible(sidebar, "corsair") == {"configure", "upstream"}


def test_the_buttons_name_the_accessory_and_the_operation(sidebar, qtbot):
    _show(sidebar, thermalright={"state": "not-installed"})
    with qtbot.waitSignal(sidebar.driver_support_requested) as signal:
        sidebar.accessory_buttons["thermalright"]["install"].click()
    assert signal.args == ["thermalright:install"]


# ------------------------------------------------------------------ window


class _Controller:
    def __init__(self):
        self.calls = []

    def manage_accessory(self, component, action):
        self.calls.append((component, action))

    def accessory_configure_argv(self, component):
        return ["/bin/true"]


def _window(controller):
    from frontends.desktop.app import ControlCenterWindow

    return type("W", (), {
        "controller": controller,
        "_ACCESSORY_LINKS": ControlCenterWindow._ACCESSORY_LINKS,
    })()


def _run(window, accessory, operation):
    from frontends.desktop.app import ControlCenterWindow

    ControlCenterWindow._dashboard_accessory(window, accessory, operation)


def test_install_goes_straight_to_the_terminal():
    controller = _Controller()
    _run(_window(controller), "corsair", "install")
    assert controller.calls == [("corsair", "install")]


@pytest.mark.parametrize(("answer", "calls"), [
    (QDialog.DialogCode.Accepted, [("thermalright", "remove")]),
    (QDialog.DialogCode.Rejected, []),
])
def test_removing_asks_first(monkeypatch, answer, calls):
    from frontends.desktop.components import page_widgets

    class Dialog:
        DialogCode = QDialog.DialogCode

        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return answer

    monkeypatch.setattr(page_widgets, "ConfirmDialog", Dialog)
    controller = _Controller()
    _run(_window(controller), "thermalright", "remove")
    assert controller.calls == calls


def test_configure_starts_trcc_detached_and_corsair_opens_its_panel(monkeypatch):
    from PyQt6 import QtCore

    from frontends.desktop.core import external_links

    started, opened = [], []
    monkeypatch.setattr(QtCore.QProcess, "startDetached", staticmethod(lambda program, args: started.append((program, args)) or True))
    monkeypatch.setattr(external_links, "open_external_url", lambda url: opened.append(url) or (True, ""))
    window = _window(_Controller())
    _run(window, "thermalright", "configure")
    _run(window, "corsair", "configure")
    assert started == [("/bin/true", [])]
    assert opened == ["http://127.0.0.1:27003"]


# ------------------------------------------------------- receiver and TV


def test_ac3_set_up_but_not_selected_offers_to_switch_back(sidebar):
    _show(sidebar, hdmi_ac3={"state": "installed", "device": True})
    assert _visible(sidebar, "hdmi_ac3") == {"install", "remove", "upstream"}
    assert sidebar.accessory_buttons["hdmi_ac3"]["install"].text() == "Use 5.1 output"
    _show(sidebar, hdmi_ac3={"state": "active", "device": False})
    assert _visible(sidebar, "hdmi_ac3") == {"remove", "upstream"}
    assert "Dolby Digital" in sidebar._accessory_notes["hdmi_ac3"].text()


def test_tv_control_offers_its_test_once_cecd_runs(sidebar):
    _show(sidebar, hdmi_cec={"state": "not-installed", "device": False})
    assert "adapter" in sidebar._accessory_notes["hdmi_cec"].text()
    assert _visible(sidebar, "hdmi_cec") == {"install", "upstream"}
    _show(sidebar, hdmi_cec={"state": "active", "device": True})
    configure = sidebar.accessory_buttons["hdmi_cec"]["configure"]
    assert not configure.isHidden() and configure.text() == "Test TV control"


def test_the_tv_test_goes_to_the_terminal():
    calls = []
    controller = _Controller()
    controller.test_tv_control = lambda: calls.append("test")
    _run(_window(controller), "hdmi_cec", "configure")
    assert calls == ["test"]
