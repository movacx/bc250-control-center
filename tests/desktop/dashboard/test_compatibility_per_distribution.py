"""Additional settings › Compatibility says, per distribution, what applies to it.

Each row is shown or withdrawn for the distribution Control Center detected,
and the scope pill names where the tool is validated, so nobody is offered
something their system cannot take.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from frontends.desktop.components.dashboard_widgets import PreparationSidebar

_APP = None
_KEEP = []


def _sidebar(os_id, label, family, reason_key="", masta=False):
    global _APP
    _APP = QApplication.instance() or QApplication([])
    temporary = TemporaryDirectory()
    _KEEP.append(temporary)
    settings = QSettings(str(Path(temporary.name) / "c.ini"), QSettings.Format.IniFormat)
    sidebar = PreparationSidebar(settings=settings, standalone=True)
    tools = {"os_id": os_id, "os_label": label, "os_family": family, "prepare_components": {}}
    if reason_key:
        tools["gfx1013_compute"] = {"reason_key": reason_key, "masta_async_compute_ready": masta}
    state = SimpleNamespace(
        preparation_tools=tools, dependencies_ready=False, governor_tool_ready=False,
        cpu_tools_ready=False, core_unlock_ready=False, umr_ready=False,
        cu_manager_ready=False, nct_ready=False,
    )
    sidebar.set_state(state)
    sidebar.resize(1200, 900)
    sidebar.show()
    _APP.processEvents()
    return sidebar


#: os_id, label, family, ACPI row, GE-Proton (SteamOS) row, Arch/CachyOS stack row
DISTRIBUTIONS = [
    ("arch", "Arch Linux", "arch", True, False, True),
    ("cachyos", "CachyOS", "arch", True, False, True),
    ("bazzite", "Bazzite", "bazzite", True, False, False),
    ("steamos", "SteamOS", "steamos", True, True, False),
    ("ubuntu", "Ubuntu", "debian", False, False, False),
    ("fedora", "Fedora", "fedora", False, False, False),
]


@pytest.mark.parametrize("os_id,label,family,acpi,proton,stack", DISTRIBUTIONS)
def test_each_row_is_shown_only_where_the_distribution_can_use_it(os_id, label, family, acpi, proton, stack):
    sidebar = _sidebar(os_id, label, family)
    assert (not sidebar.acpi_card.isHidden()) is acpi
    assert (not sidebar.steamos_proton_card.isHidden()) is proton
    assert any((not card.isHidden()) is stack for card in sidebar.cachyos_cards)
    # The governors and VA-API are offered everywhere.
    for card in (sidebar.cyan_card, sidebar.oberon_card, sidebar.vaapi_card):
        assert not card.isHidden()


def test_the_acpi_scope_names_the_distribution_it_was_validated_on():
    assert "Arch" in _sidebar("arch", "Arch Linux", "arch").acpi_card.scope.text()
    assert "Bazzite" in _sidebar("bazzite", "Bazzite", "bazzite").acpi_card.scope.text()
    assert "SteamOS" in _sidebar("steamos", "SteamOS", "steamos").acpi_card.scope.text()


@pytest.mark.parametrize("reason,expected", [
    ("steamos-dedicated-backend", "SteamOS"),
    ("fedora-upstream-managed", "Fedora"),
    ("bazzite-release-managed", "Bazzite"),
    ("bazzite-release-version-unsupported", "not supported"),
    ("manual-patches-only", "Manual only"),
])
def test_the_async_compute_scope_follows_what_the_system_reported(reason, expected):
    family = "fedora" if "fedora" in reason else "bazzite" if "bazzite" in reason else "steamos" if "steamos" in reason else "debian"
    sidebar = _sidebar(family, family.title(), family, reason_key=reason)
    assert expected.lower() in sidebar.gfx_card.scope.text().lower()


def test_the_arch_stack_scope_says_it_comes_with_the_stack_when_it_is_supported():
    sidebar = _sidebar("arch", "Arch Linux", "arch", reason_key="arch-family-manual-untested")
    assert "arch" in sidebar.gfx_card.scope.text().lower()


def test_every_row_that_is_shown_has_a_scope_and_a_status_to_read():
    for os_id, label, family, *_ in DISTRIBUTIONS:
        sidebar = _sidebar(os_id, label, family)
        for _title, cards in sidebar.compatibility_groups:
            for card in cards:
                if card.isHidden():
                    continue
                assert card.title.text().strip(), (os_id, card)
                assert card.status.text().strip(), (os_id, card.title.text())
