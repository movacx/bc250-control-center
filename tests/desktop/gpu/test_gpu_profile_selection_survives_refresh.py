"""Regression for GitHub issue: clicking an operating profile card, then a
telemetry refresh landing before the user hits Apply, must not un-select it.

``sync_active_range`` re-syncs the rail with whatever the hardware still
reports as long as ``_follow_hardware`` is True. Clicking a profile card
stages a change the same way dragging the rail does, so it must also flip
that flag off — otherwise the very next refresh snaps the selection back.
"""
from frontends.desktop.pages.gpu_governor_view import GpuGovernorView


def test_profile_card_selection_is_not_reverted_by_telemetry_refresh(qtbot):
    view = GpuGovernorView()
    qtbot.addWidget(view)

    hardware_min, hardware_max = view._state.active_minimum, view._state.active_maximum
    other_card = next(
        card for card in view._profile_cards
        if (card.profile.minimum, card.profile.maximum) != (hardware_min, hardware_max)
    )

    view._on_profile_selected(other_card.profile)
    assert view._selected_profile == other_card.profile.key

    # A telemetry refresh lands before the user presses Apply.
    view.sync_active_range(hardware_min, hardware_max)

    assert view._selected_profile == other_card.profile.key
    assert view._selected_minimum == other_card.profile.minimum
    assert view._selected_maximum == other_card.profile.maximum
