"""Additional settings carries the Dashboard's preparation tabs minus Components."""

from frontends.desktop.pages.additional_settings import AdditionalSettingsPage


def test_the_page_has_every_tab_but_components_and_opens_on_compatibility(qtbot):
    fed = []
    page = AdditionalSettingsPage(state_feed=fed.append)
    qtbot.addWidget(page)
    panel = page.panel

    assert panel.tab_buttons[0].isHidden()
    assert all(panel.tabs_grid.indexOf(b) >= 0 for b in panel.tab_buttons[1:])
    assert panel.tabs_grid.indexOf(panel.tab_buttons[0]) < 0
    assert panel.stack.currentIndex() == 1
    assert panel.tab_buttons[1].isChecked()
    assert not panel.prepare_footer.isVisibleTo(panel)

    page.set_updates_active(True)
    page.set_updates_active(False)
    assert fed == [True, False]


def test_the_page_forwards_dependency_and_driver_requests(qtbot):
    page = AdditionalSettingsPage()
    qtbot.addWidget(page)
    seen = []
    page.dependency_action_requested.connect(seen.append)
    page.driver_support_requested.connect(seen.append)
    page.panel.dependency_action_requested.emit({"action": "memory_swap"})
    page.panel.driver_support_requested.emit("printing")
    assert seen == [{"action": "memory_swap"}, "printing"]


def _compatibility(qtbot):
    page = AdditionalSettingsPage()
    qtbot.addWidget(page)
    page.resize(1200, 900)
    page.show()
    panel = page.panel
    panel._page = page  # the panel is a child of the page: keep both alive
    return panel


def test_compatibility_cards_start_as_a_title_row_and_open_on_demand(qtbot):
    panel = _compatibility(qtbot)
    for card in (panel.cyan_card, panel.oberon_card, panel.gfx_card, panel.fsr4_card):
        assert not card.is_expanded()
        assert card.detail.isHidden() or not card.detail.isVisible()
    card = panel.cyan_card
    card._toggle.click()
    assert card.is_expanded()
    assert card.detail.isVisible()
    card._toggle.click()
    assert not card.is_expanded()


def test_a_card_that_needs_attention_opens_itself_once(qtbot):
    panel = _compatibility(qtbot)
    card = panel.cachyos_stack_card
    card.set_status("Partially installed", "orange")
    assert card.is_expanded()
    card.set_expanded(False)
    card.set_status("Partially installed", "orange")
    assert not card.is_expanded()


def test_each_group_is_one_list_without_a_banner(qtbot):
    panel = _compatibility(qtbot)
    assert not hasattr(panel, "compatibility_attention")
    for heading, box, cards in panel._compatibility_headings:
        assert all(card.parentWidget() is box for card in cards)
    panel.gfx_card.hide()
    panel._refresh_compatibility_summary()
    assert panel.cachyos_stack_card.property("listFirst") is True
    assert panel.gfx_card.property("listFirst") is False


def test_the_dashboard_copy_keeps_full_cards(qtbot):
    from frontends.desktop.components.dashboard_widgets import PreparationSidebar

    panel = PreparationSidebar()
    qtbot.addWidget(panel)
    assert panel.cyan_card._body is None
