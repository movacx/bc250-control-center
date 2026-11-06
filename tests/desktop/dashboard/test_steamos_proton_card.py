import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QPushButton

from frontends.desktop.components.dashboard_widgets import PreparationSidebar
from frontends.desktop.core.state import DashboardState


@pytest.mark.parametrize("family", ["steamos", "cachyos", "debian"])
def test_upstream_proton_card_is_only_actionable_on_steamos(qtbot, tmp_path, family):
    settings = QSettings(str(tmp_path / "test.ini"), QSettings.Format.IniFormat)
    sidebar = PreparationSidebar(settings=settings, standalone=True)
    qtbot.addWidget(sidebar)
    sidebar.set_state(DashboardState(preparation_tools={"os_family": family}))
    card = sidebar.steamos_proton_card
    assert card.isHidden() == (family != "steamos")
    assert card.isEnabled() == (family == "steamos")
    assert card in dict(sidebar.compatibility_groups)["Kernel and graphics"]
    if family == "steamos":
        button = next(b for b in card.findChildren(QPushButton) if b.text() == "Check Proton")
        with qtbot.waitSignal(sidebar.dependency_action_requested) as signal:
            button.click()
        assert signal.args[0]["action"] == "steamos_proton_status"


def test_preview_cannot_enable_steamos_proton_on_cachyos(qtbot, tmp_path):
    sidebar = PreparationSidebar(
        settings=QSettings(str(tmp_path / "test.ini"), QSettings.Format.IniFormat),
        standalone=True,
    )
    qtbot.addWidget(sidebar)
    sidebar.set_state(DashboardState(preparation_tools={"os_family": "cachyos"}))
    sidebar.compatibility_filter.setCurrentIndex(sidebar.compatibility_filter.findData("steamos"))
    assert not sidebar.steamos_proton_card.isHidden()
    assert not sidebar.steamos_proton_card.isEnabled()
