"""One GPU screen for both backends, dressed differently.

Oberon used to keep its own original screen, so the same job had two layouts
and the buttons moved depending on which governor a board ran. It now wears
this view with the Cyan-only panels hidden. Nothing here may change what Cyan
shows: that half is the regression guard.
"""

from frontends.desktop.pages.gpu_governor import GpuGovernorPage
from frontends.desktop.pages.gpu_governor_integration import OBERON_PROFILES

CYAN = "cyan-skillfish-governor-smu"
OBERON = "oberon-governor"


def _page(qtbot, backend):
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)
    page._apply_state({"governor_backend": backend}, {})
    return page, page._redesigned_gpu_view


# ``isHidden`` rather than ``not isVisible``: a child of a window that was
# never shown is not visible even when it is set to be. See docs/CONTEXTO.md.


def test_both_backends_use_the_one_shared_screen(qtbot):
    for backend in (CYAN, OBERON):
        page, view = _page(qtbot, backend)
        assert not view.isHidden()
        # The original screen is never the one on show any more.
        assert page.overview_scroll.isHidden()


def test_cyan_keeps_every_panel_it_had(qtbot):
    """The regression guard: adapting Oberon must not trim Cyan."""
    _page_, view = _page(qtbot, CYAN)

    assert not view._range_panel.isHidden()
    assert not view._compat_panel.isHidden()
    assert not view._risk_panel.isHidden()
    assert not view.startup_button.isHidden()
    assert view.apply_button.text() == "Review and apply range"
    assert view._open_config_button.text() == "Open config.toml"
    assert not any(card._edit_button.isHidden() for card in view._profile_cards)


def test_oberon_hides_the_panels_that_only_describe_cyan(qtbot):
    """Oberon has two YAML endpoints, not a multi-point TOML curve."""
    _page_, view = _page(qtbot, OBERON)

    assert view._range_panel.isHidden()
    assert view._compat_panel.isHidden()
    # Nothing to uncomment: the +2000 MHz points are a config.toml concept.
    assert view._risk_panel.isHidden()


def test_oberon_does_not_offer_an_action_the_backend_refuses(qtbot):
    """``guardar_rango_gpu_arranque`` raises for Oberon, so hide the button."""
    _page_, view = _page(qtbot, OBERON)

    assert view.startup_button.isHidden()


def test_oberon_names_its_own_configuration_and_action(qtbot):
    _page_, view = _page(qtbot, OBERON)

    assert view.apply_button.text() == "Review and apply Oberon profile"
    assert view._open_config_button.text() == "Open oberon-config.yaml"


def test_oberon_profiles_come_from_the_contract_and_are_not_editable(qtbot):
    _page_, view = _page(qtbot, OBERON)

    shapes = [(profile.minimum, profile.maximum) for profile in view.profiles()]
    assert shapes == [(p.minimum, p.maximum) for p in OBERON_PROFILES]
    assert shapes == [(1000, 1500), (1000, 1850), (1000, 2000)]
    assert all(card._edit_button.isHidden() for card in view._profile_cards)


def test_switching_backends_restores_the_other_layout(qtbot):
    """A preference change flips the backend without rebuilding the page."""
    page, view = _page(qtbot, CYAN)

    page._apply_state({"governor_backend": OBERON}, {})
    assert view._range_panel.isHidden()

    page._apply_state({"governor_backend": CYAN}, {})
    assert not view._range_panel.isHidden()
    assert not view.startup_button.isHidden()
    assert view.apply_button.text() == "Review and apply range"


def test_oberon_never_borrows_a_voltage_from_cyans_curve(qtbot):
    """Oberon's two YAML endpoints are flat; Cyan's TOML curve is not its.

    ``domain/gpu/oberon.py`` exists precisely to stop Oberon voltages being
    derived from Cyan's unrelated multipoint table, and that must hold in the
    interface too.
    """
    from bc250cc.domain.gpu.oberon import OBERON_REFERENCE_VOLTAGE_MV

    _page_, view = _page(qtbot, OBERON)

    shown = [card._voltage_label.text() for card in view._profile_cards]
    assert shown == [f"{OBERON_REFERENCE_VOLTAGE_MV} mV"] * 3
    assert f"{OBERON_REFERENCE_VOLTAGE_MV} mV" in view._lab_point.text()


def test_cyan_still_shows_its_own_per_frequency_voltages(qtbot):
    _page_, view = _page(qtbot, CYAN)

    shown = [card._voltage_label.text() for card in view._profile_cards]
    assert shown == ["900 mV", "930 mV", "960 mV"]


def test_the_old_screen_is_never_painted_not_even_for_one_frame(qtbot):
    """It used to show for the second before the first refresh arrived.

    The swap waited for telemetry to confirm the backend. Since this view now
    serves both backends there is nothing to wait for, so it happens at mount.
    """
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)

    # No _apply_state call at all: this is the state the window opens in.
    assert page.overview_scroll.isHidden()
    assert not page._redesigned_gpu_view.isHidden()
