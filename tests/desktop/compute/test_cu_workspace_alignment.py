"""Layout contract for the Compute Units workspace.

The page used to be a stack of separate cards. It is now the shape the GPU
Governor page uses: a wide topology card on the left, and a side column whose
merged "Live CU telemetry" card carries the summary tiles and the action panels
that used to live in cards of their own.

``persistence_card`` still exists, hidden, purely so the ``persistence_status``
calls scattered through the page keep working. It is not part of the visible
layout, so nothing here measures it — these tests assert against what actually
renders. The matching "Recent CU actions" card has been removed outright: it was
hidden at construction and never shown, yet every action rebuilt five row
widgets inside it.
"""

import pytest
from PyQt6.QtCore import QPoint

from frontends.desktop.i18n import localize_widget_tree, set_language, tr
from frontends.desktop.pages.compute_units import ComputeUnitsPage
from frontends.desktop.theme import application_stylesheet


def _bottom(widget, parent):
    return widget.mapTo(parent, widget.rect().bottomLeft()).y()


def _host_card(widget):
    """The SectionCard a widget is rendered inside, or None."""
    host = widget.parent()
    while host is not None and not hasattr(host, "body"):
        host = host.parent()
    return host


@pytest.mark.parametrize("width", (1200, 1440, 1920))
@pytest.mark.parametrize("language", ("en", "es", "de"))
def test_cu_workspace_columns_end_together_at_desktop_widths(qtbot, width, language):
    """Both workspace columns must finish on the same line, in every language.

    The grid stretches each column to the row height and each card's trailing
    stretch absorbs the slack, so a card that forgets that stretch shows up
    here as one column floating short.
    """
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
            assert abs(_bottom(page.topology_card, page.content)
                       - _bottom(page.side_column, page.content)) <= 1
            assert page.side_column.mapTo(page.content, QPoint()).y() == page.topology_card.y()
            for button in page.persistence_action_buttons:
                assert button.isVisible()
                card = _host_card(button)
                assert card is not None, button.text()
                assert card.rect().contains(
                    button.mapTo(card, button.rect().bottomRight())
                ), button.text()
    finally:
        set_language("en")


def test_cu_keeps_the_full_telemetry_strip_and_drops_redundant_badges(qtbot):
    page = ComputeUnitsPage(object())
    qtbot.addWidget(page)
    for card in (page.topology_card, page.profiles_card, page.persistence_card):
        assert card.status is None

    # Nine tiles: CU service and boot persistence, plus the GPU and CPU
    # readings the merged card absorbed. Asserted so a tile cannot silently
    # disappear across a state refresh.
    assert len(page.summary_strip.items) == 9
    assert page.register_toggle is not None
    assert page.register_toggle.isEnabled()

    # "Raw status" moved out of the activity card header into the side column.
    assert any(
        button.text() == tr("Raw status") for button in page.persistence_action_buttons
    )

    page._apply_state({})
    page._set_busy(True, "Working")
    assert not page.topology_table.isEnabled()
    page._set_busy(False, "")
    assert page.topology_table.isEnabled()
    assert len(page.summary_strip.items) == 9


def test_the_merged_cards_stay_out_of_the_visible_layout(qtbot):
    """They are kept alive for their state hooks, not to be shown again."""
    page = ComputeUnitsPage(object())
    qtbot.addWidget(page)
    page.resize(1440, 900)
    page.show()
    qtbot.wait(50)
    assert not page.persistence_card.isVisible()
    # The activity card is gone entirely, not merely hidden.
    assert not hasattr(page, "activity_card")
    assert not hasattr(page, "activity_body")


@pytest.mark.parametrize("width", (360, 720, 1440, 720))
def test_cu_workspace_reflows_without_overflowing_sideways(qtbot, width):
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
    else:
        # Two columns: they sit beside each other and never overlap.
        assert page.side_column.x() >= page.topology_card.geometry().right()
