import pytest
from PyQt6.QtCore import QPoint

from frontends.desktop.i18n import localize_widget_tree, set_language, tr
from frontends.desktop.pages.compute_units import ComputeUnitsPage
from frontends.desktop.theme import application_stylesheet


def _bottom(widget, parent):
    return widget.mapTo(parent, widget.rect().bottomLeft()).y()


@pytest.mark.parametrize("width", (1200, 1440, 1920))
@pytest.mark.parametrize("language", ("en", "es", "de"))
def test_cu_persistence_footer_matches_topology_at_desktop_widths(qtbot, width, language):
    page = ComputeUnitsPage(object())
    qtbot.addWidget(page)
    try:
        set_language(language)
        localize_widget_tree(page, language)
        page.setStyleSheet(application_stylesheet("dark", scale=100))
        page.resize(width, 1000)
        page.show()
        qtbot.wait(100)
        assert page._workspace_columns == 2
        for expanded in (False, True, False):
            page.register_panel.set_expanded(expanded)
            # Register details animate; check the final layout, not an interim frame.
            qtbot.wait(350)
            assert abs(_bottom(page.persistence_card, page.content)
                       - _bottom(page.topology_card, page.content)) <= 1
            assert page.profiles_card.mapTo(page.content, QPoint()).y() == page.topology_card.y()
            assert page.persistence_card.y() > page.profiles_card.geometry().bottom()
            for button in page.persistence_action_buttons:
                assert button.isVisible()
                assert page.persistence_card.rect().contains(
                    button.mapTo(page.persistence_card, button.rect().bottomRight())
                )
    finally:
        set_language("en")


def test_cu_removes_only_redundant_header_badges_and_keeps_summary(qtbot):
    page = ComputeUnitsPage(object())
    qtbot.addWidget(page)
    for card in (page.topology_card, page.profiles_card, page.persistence_card, page.activity_card):
        assert card.status is None
    assert len(page.summary_strip.items) == 5
    assert page.register_toggle is not None
    assert any(button.text() == tr("Raw status") for button in page.activity_card._header_buttons)
    # State refresh and busy handling must tolerate the removed status badges.
    page._apply_state({})
    page._set_busy(True, "Working")
    assert not page.topology_table.isEnabled()
    page._set_busy(False, "")
    assert page.topology_table.isEnabled()
    assert len(page.summary_strip.items) == 5


@pytest.mark.parametrize("width", (360, 720, 1440, 720))
def test_cu_workspace_reflows_without_overlapping_cards(qtbot, width):
    page = ComputeUnitsPage(object())
    qtbot.addWidget(page)
    page.resize(1440, 900)
    page.show()
    qtbot.wait(50)
    page.resize(width, 900)
    qtbot.wait(100)
    assert page.scroll.horizontalScrollBar().maximum() == 0
    assert page.content.width() == page.scroll.viewport().width()
    if page._workspace_columns == 1:
        assert page.side_column.y() > page.topology_card.geometry().bottom()
    assert page.activity_card.y() > _bottom(page.persistence_card, page.content)
