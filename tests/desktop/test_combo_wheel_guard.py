"""Scrolling over a closed drop-down list scrolls the page, not the list."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QApplication, QComboBox, QScrollArea, QVBoxLayout, QWidget

from frontends.desktop.components.wheel_guard import GuardedComboBox


def _wheel(widget: QWidget) -> None:
    centre = QPointF(widget.rect().center())
    event = QWheelEvent(centre, widget.mapToGlobal(centre), QPoint(0, 0), QPoint(0, -120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                        Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, event)


def test_the_wheel_scrolls_the_page_and_leaves_the_choice_alone():
    _app = QApplication.instance() or QApplication([])
    area = QScrollArea()
    page = QWidget()
    layout = QVBoxLayout(page)
    combo = GuardedComboBox()
    combo.addItems(["Auto", "32", "64"])
    layout.addWidget(combo)
    page.setMinimumHeight(3000)
    area.setWidget(page)
    area.resize(300, 200)
    area.show()
    QApplication.processEvents()

    _wheel(combo)

    assert combo.currentIndex() == 0, "the value did not move"
    assert area.verticalScrollBar().value() > 0, "the page scrolled instead"
    area.close()


def test_an_inner_area_at_its_end_hands_the_wheel_to_the_page():
    _app = QApplication.instance() or QApplication([])
    outer = QScrollArea()
    page = QWidget()
    page_layout = QVBoxLayout(page)
    inner = QScrollArea()
    inner.setFixedHeight(120)
    content = QWidget()
    QVBoxLayout(content).addWidget(combo := GuardedComboBox())
    combo.addItems(["A", "B"])
    inner.setWidget(content)  # fits: nothing to scroll inside
    page_layout.addWidget(inner)
    page.setMinimumHeight(3000)
    outer.setWidget(page)
    outer.resize(300, 200)
    outer.show()
    QApplication.processEvents()

    _wheel(combo)

    assert combo.currentIndex() == 0
    assert outer.verticalScrollBar().value() > 0
    outer.close()


def test_no_drop_down_on_the_real_pages_moves_under_the_wheel():
    """Every QComboBox of Additional settings (Compatibility's filter,
    HelixSR's settings, ...) keeps its value."""
    from types import SimpleNamespace

    from frontends.desktop.pages.additional_settings import AdditionalSettingsPage

    _app = QApplication.instance() or QApplication([])
    page = AdditionalSettingsPage()
    defaults = {"Sharpening.Sharpener": "off"}
    page.apply_state(SimpleNamespace(
        preparation_tools={"os_id": "bazzite", "os_label": "Bazzite", "os_family": "bazzite",
                           "prepare_components": {},
                           "helixsr": {"installer_available": True, "installed": True, "current": True,
                                       "network_ready": True, "state": "ready", "games": [],
                                       "settings": defaults, "settings_defaults": defaults},
                           "fsr4": {}},
        dependencies_ready=False, governor_tool_ready=False, cpu_tools_ready=False,
        core_unlock_ready=False, umr_ready=False, cu_manager_ready=False, nct_ready=False,
    ))
    page.resize(1200, 700)
    page.show()
    form = page.panel.helixsr_settings
    for title in form.groups:
        form.set_group_expanded(title, True)
    checked = 0
    for tab in ("compatibility", "upscaling", "memory"):
        page.panel.select_tab(page.panel.tab_index(tab))
        QApplication.processEvents()
        for combo in page.findChildren(QComboBox):
            if not combo.isVisible() or combo.count() < 2:
                continue
            before = combo.currentIndex()
            _wheel(combo)
            assert combo.currentIndex() == before, (tab, combo.accessibleName() or combo.currentText())
            checked += 1
    assert checked >= 8, checked
    page.close()


def test_an_open_list_keeps_the_wheel_for_itself():
    _app = QApplication.instance() or QApplication([])
    area = QScrollArea()
    page = QWidget()
    layout = QVBoxLayout(page)
    combo = GuardedComboBox()
    combo.addItems(["A", "B", "C"])
    layout.addWidget(combo)
    page.setMinimumHeight(3000)
    area.setWidget(page)
    area.resize(300, 200)
    area.show()
    QApplication.processEvents()
    combo.showPopup()
    QApplication.processEvents()
    assert combo.view().isVisible()

    _wheel(combo)

    assert area.verticalScrollBar().value() == 0, "the page stayed where it was: the list took the wheel"
    combo.hidePopup()
    area.close()
