"""GPU screen: the Modern | Classic buttons at its foot, and the classic
layout's draggable monitoring column (as on the CPU screen)."""

from __future__ import annotations

import pytest

from frontends.desktop.core.preferences import application_settings
from frontends.desktop.pages import gpu_governor_integration as integration
from frontends.desktop.pages import gpu_governor_view_classic as classic
from frontends.desktop.pages.gpu_governor import GpuGovernorPage
from frontends.desktop.pages.gpu_governor_view import GpuGovernorView


@pytest.fixture(autouse=True)
def clean():
    settings = application_settings()
    for key in (integration.GPU_INTERFACE_KEY, classic.SIDE_WIDTH_KEY):
        settings.remove(key)
    yield
    for key in (integration.GPU_INTERFACE_KEY, classic.SIDE_WIDTH_KEY):
        settings.remove(key)


def test_each_layout_shows_which_one_it_is(qtbot):
    modern, old = GpuGovernorView(), classic.GpuGovernorView()
    qtbot.addWidget(modern)
    qtbot.addWidget(old)
    assert modern.interface_switch.current() == "modern"
    assert old.interface_switch.current() == "original"


def test_the_foot_buttons_switch_and_remember(qtbot):
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)
    page._redesigned_gpu_view.interface_switch.buttons["original"].click()
    qtbot.waitUntil(lambda: type(page._redesigned_gpu_view) is classic.GpuGovernorView, timeout=2000)
    assert application_settings().value(integration.GPU_INTERFACE_KEY) == "original"
    page._redesigned_gpu_view.interface_switch.buttons["modern"].click()
    qtbot.waitUntil(lambda: type(page._redesigned_gpu_view) is GpuGovernorView, timeout=2000)


def test_the_classic_monitoring_column_drags_and_is_remembered(qtbot):
    view = classic.GpuGovernorView()
    qtbot.addWidget(view)
    view.resize(1700, 1000)
    view.show()
    qtbot.waitExposed(view)
    before = view._telemetry.width()
    view._side_grip.pressed.emit()
    view._side_grip.dragged.emit(-100)
    view._side_grip.released.emit()
    assert view.side_width() == before + 100
    assert int(application_settings().value(classic.SIDE_WIDTH_KEY)) == before + 100
    view._side_grip.double_clicked.emit()
    assert view.side_width() == 0
    view._reflow(classic.STACK_WIDTH - 100)
    assert view._side_grip.isHidden()
