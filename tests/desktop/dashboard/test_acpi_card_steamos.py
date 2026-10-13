"""The ACPI card on SteamOS: shown, labelled beta, and its repair explained."""

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


def _show(sidebar, family, acpi):
    sidebar.set_state(DashboardState(preparation_tools={
        "os_family": family,
        "system_setup": {"helper_available": True, "acpi": acpi},
    }))


@pytest.mark.parametrize(("family", "scope"), [
    ("steamos", "Beta · SteamOS"),
    ("bazzite", "Beta · Bazzite"),
    ("manjaro", "Validated · Arch / CachyOS / Manjaro"),
])
def test_the_card_is_offered_where_the_helper_has_a_route(sidebar, family, scope):
    _show(sidebar, family, {"status": "not-installed", "available": True})
    assert not sidebar.acpi_card.isHidden()
    assert sidebar.acpi_card.scope.text() == scope


def test_a_steamos_update_offers_the_repair(sidebar):
    _show(sidebar, "steamos", {"status": "needs-repair", "installed": True})
    assert sidebar.acpi_card.status.text() == "Repair required"
    button = sidebar.acpi_update_button
    assert not button.isHidden() and button.isEnabled()
    assert button.text() == "Repair correction"


class _Dialog:
    seen = []
    DialogCode = QDialog.DialogCode

    def __init__(self, title, body, **kwargs):
        _Dialog.seen.append((body, kwargs.get("confirm_text")))

    def exec(self):
        return QDialog.DialogCode.Rejected


@pytest.mark.parametrize(("family", "status", "action", "words", "confirm"), [
    ("steamos", "needs-repair", "acpi-update", "A SteamOS update replaced /boot", "Repair correction"),
    ("steamos", "not-installed", "acpi-install", "delete /boot/bc250-acpi.cpio", "Install correction"),
    ("steamos", "outdated", "acpi-update", "drops the C3 idle state", "Update correction"),
    ("bazzite", "not-installed", "acpi-install", "Bazzite without the BC250 ACPI tables", "Install correction"),
])
def test_the_confirmation_says_what_this_system_does(monkeypatch, family, status, action, words, confirm):
    from frontends.desktop.pages import gpu_governor

    monkeypatch.setattr(gpu_governor, "ConfirmDialog", _Dialog)
    _Dialog.seen = []
    page = type("Page", (), {
        "current_state": {"tools": {"os_family": family, "system_setup": {"acpi": {"status": status}}}},
    })()
    gpu_governor.GpuGovernorPage._manage_acpi(page, action)
    body, confirm_text = _Dialog.seen[0]
    assert words in body and confirm_text == confirm
