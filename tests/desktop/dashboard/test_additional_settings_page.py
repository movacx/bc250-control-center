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
