from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QHBoxLayout, QWidget

from frontends.desktop.app import ControlCenterWindow
from frontends.desktop.components.sidebar import Sidebar
from frontends.desktop.i18n import (
    SUPPORTED_LANGUAGES,
    localize_widget_tree,
    set_language,
    tr,
)
from frontends.desktop.pages.cpu_smu import CpuSmuPage
from frontends.desktop.pages.dashboard import DashboardPage
from frontends.desktop.pages.fans import FansPage
from frontends.desktop.theme import application_stylesheet


def test_dashboard_buttons_emit_navigation_not_hardware_operations(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    actions = []
    modules = []
    page.action_requested.connect(actions.append)
    page.module_requested.connect(modules.append)
    for card in (page.cpu_card, page.fan_card):
        for button in card.action_buttons:
            button.click()
    page.footer.repositories_button.click()
    page.cu_card.primary_button.click()
    assert actions == ["cpu_configuration", "cpu_overview", "fans_manual", "fans_curve", "repositories"]
    assert modules == ["cu"]
    assert page.cu_card.status.isHidden()
    assert page.readiness.status.isHidden()
    assert page.gpu_card.governor_metric.parent() is page.gpu_card.evidence
    assert page.gpu_card.load_metric.parent() is page.gpu_card.evidence


def test_shortcuts_select_the_requested_tab_even_after_visiting_the_other(qtbot):
    cpu, fans = CpuSmuPage(object()), FansPage(object())
    qtbot.addWidget(cpu)
    qtbot.addWidget(fans)
    visited = []
    window = SimpleNamespace(cpu_page=cpu, fans_page=fans, navigate=visited.append)
    for action in ("cpu_overview", "cpu_configuration", "fans_curve", "fans_manual"):
        ControlCenterWindow._dashboard_action(window, action)
    assert visited == ["cpu", "cpu", "fans", "fans"]
    assert cpu.workspace_tab_buttons["configuration"].isChecked()
    assert fans.manual_mode_button.isChecked()


@pytest.mark.parametrize("language", sorted(SUPPORTED_LANGUAGES))
def test_new_shortcuts_translate_when_language_changes(qtbot, language):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    try:
        set_language(language)
        localize_widget_tree(page, language)
        for button, key in zip(page.cpu_card.action_buttons, ("Configure CPU", "Unlock cores"), strict=True):
            assert button.text() == tr(key)
            if language != "en":
                assert button.text() != key
    finally:
        set_language("en")


@pytest.mark.parametrize("width,height", ((1024, 720), (1920, 1080)))
def test_icons_fit_existing_sidebar_without_reserving_dashboard_space(qtbot, width, height):
    shell = QWidget()
    qtbot.addWidget(shell)
    shell.setStyleSheet(application_stylesheet("dark", scale=100))
    layout = QHBoxLayout(shell)
    sidebar, page = Sidebar(), DashboardPage(object())
    sidebar.set_collapsed(True)
    layout.addWidget(sidebar)
    layout.addWidget(page, 1)
    shell.resize(width, height)
    shell.show()
    qtbot.wait(100)
    assert shell.width() == width and shell.height() == height
    assert page.scroll.viewportMargins().right() == 0
    assert page.readiness.system_bar.isAncestorOf(page.footer)
    assert page.footer.isVisible()
    assert page.footer.geometry().right() < page.readiness.system_bar.width()
    assert page.footer.x() > page.readiness.system_label.geometry().right()
    assert page.content.width() == page.scroll.viewport().width()
