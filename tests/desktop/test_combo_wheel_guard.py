"""Scrolling over a closed drop-down list scrolls the page, not the list."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QApplication, QComboBox, QScrollArea, QVBoxLayout, QWidget

from frontends.desktop.components.wheel_guard import install_combo_wheel_guard


def _wheel(widget: QWidget) -> None:
    centre = QPointF(widget.rect().center())
    event = QWheelEvent(centre, widget.mapToGlobal(centre), QPoint(0, 0), QPoint(0, -120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                        Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, event)


def test_the_wheel_scrolls_the_page_and_leaves_the_choice_alone():
    app = QApplication.instance() or QApplication([])
    install_combo_wheel_guard(app)
    area = QScrollArea()
    page = QWidget()
    layout = QVBoxLayout(page)
    combo = QComboBox()
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
    assert install_combo_wheel_guard(app) is install_combo_wheel_guard(app), "installed once"
    area.close()


def test_an_inner_area_at_its_end_hands_the_wheel_to_the_page():
    app = QApplication.instance() or QApplication([])
    install_combo_wheel_guard(app)
    outer = QScrollArea()
    page = QWidget()
    page_layout = QVBoxLayout(page)
    inner = QScrollArea()
    inner.setFixedHeight(120)
    content = QWidget()
    QVBoxLayout(content).addWidget(combo := QComboBox())
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

    app = QApplication.instance() or QApplication([])
    install_combo_wheel_guard(app)
    page = AdditionalSettingsPage()
    defaults = {"Sharpening.Mode": "off"}
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
