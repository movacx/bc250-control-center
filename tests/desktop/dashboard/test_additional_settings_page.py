"""Additional settings carries the Dashboard's preparation tabs minus Components."""

from frontends.desktop.pages.additional_settings import AdditionalSettingsPage


def test_the_page_has_only_compatibility_memory_and_drivers_and_opens_on_compatibility(qtbot):
    fed = []
    page = AdditionalSettingsPage(state_feed=fed.append)
    qtbot.addWidget(page)
    panel = page.panel

    # Components and Decky stay on the Dashboard.
    visible = [panel.tab_buttons[i] for i in (1, 5, 2, 4)]
    assert all(panel.tab_buttons[i].isHidden() for i in (0, 3))
    assert all(panel.tabs_grid.indexOf(b) >= 0 for b in visible)
    assert all(panel.tabs_grid.indexOf(panel.tab_buttons[i]) < 0 for i in (0, 3))
    # Upscaling sits right after Compatibility, in that order on screen.
    places = [panel.tabs_grid.getItemPosition(panel.tabs_grid.indexOf(b))[:2] for b in visible]
    assert places == sorted(places) and len(set(places)) == 4
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


def test_buttons_of_a_collapsed_row_keep_their_width_and_accent_in_sync(qtbot):
    """A collapsed body hides its buttons from isVisibleTo(card); the styling
    must still follow the state, or they open stale (no stretch, no accent)."""
    panel = _compatibility(qtbot)
    card = panel.gfx_card
    assert not card.is_expanded()
    card.update_action(card.gfx_primary_button if hasattr(card, "gfx_primary_button") else panel.gfx_primary_button, text="Build and install", enabled=True)
    primary = panel.gfx_primary_button
    link = panel.gfx_secondary_button
    card.update_action(link, text="Open upstream project", visible=True)
    assert card.actions.stretch(card.actions.indexOf(primary)) == 1
    assert card.actions.stretch(card.actions.indexOf(link)) == 0
    # Swapping the link back into an action restores its width and alignment.
    card.update_action(link, text="Install Mesa", visible=True)
    assert card.actions.stretch(card.actions.indexOf(link)) == 1
    assert int(card.actions.itemAt(card.actions.indexOf(link)).alignment().value) == 0


def test_boot_options_show_on_additional_settings_and_not_on_the_dashboard(qtbot):
    from frontends.desktop.components.dashboard_widgets import PreparationSidebar

    dashboard = PreparationSidebar()
    qtbot.addWidget(dashboard)
    dashboard.show()
    assert dashboard._boot_holder.isHidden()

    page = AdditionalSettingsPage()
    qtbot.addWidget(page)
    page.resize(1200, 900)
    page.show()
    panel = page.panel
    assert panel._boot_holder.parentWidget() is not None
    assert panel._boot_holder.isAncestorOf(panel.kernel_options_panel)
    # Nothing to show until the helper reports a manageable boot setup.
    assert panel._boot_holder.isHidden()
    panel.kernel_options_panel.setVisible(True)
    panel._refresh_compatibility_summary()
    assert not panel._boot_holder.isHidden()


def test_kernel_options_hide_the_plain_enabled_disabled_pill(qtbot):
    page = AdditionalSettingsPage()
    qtbot.addWidget(page)
    page.show()
    panel = page.panel
    tools = {"system_setup": {"helper_available": True, "kernel_options": {"available": True, "arguments": {
        "mitigations=off": {"managed": True, "configured": True, "active": True},
        "nosmt": {"managed": False, "configured": False, "active": False},
    }}}}
    panel._update_kernel_options_control(tools)
    _, mitigations_pill, mitigations_button = panel.kernel_option_controls["mitigations=off"]
    _, smt_pill, smt_button = panel.kernel_option_controls["nosmt"]
    assert mitigations_pill.isHidden() and smt_pill.isHidden()
    assert mitigations_button.text() == "Restore mitigations"
    assert smt_button.text() == "Disable SMT"
    # A pending reboot is not something the button can say, so it stays.
    tools["system_setup"]["kernel_options"]["arguments"]["nosmt"] = {
        "managed": True, "configured": True, "active": False,
    }
    panel._update_kernel_options_control(tools)
    assert not smt_pill.isHidden()
    assert smt_pill.text() == "Reboot required"


def test_the_dashboard_timer_keeps_reading_for_a_page_it_feeds():
    """Additional settings is fed by the Dashboard's five-second read: its
    ticks must not stop because the Dashboard itself is hidden."""
    from types import SimpleNamespace

    from frontends.desktop.pages.dashboard import DashboardPage

    requests = []
    page = SimpleNamespace(_updates_active=False, _feeding=True,
                           _refresher=SimpleNamespace(request=lambda: requests.append(1)))
    DashboardPage.refresh(page)
    assert requests == [1]
    page._feeding = False
    DashboardPage.refresh(page)
    assert requests == [1], "nothing shown, nothing read"
