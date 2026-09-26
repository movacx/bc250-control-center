"""The GPU workspace reads like the CPU one: no title rows and no badges.

The cards carried an icon, a title that repeated the page's and a subtitle
that repeated the panel headings; the telemetry tiles each wore a coloured
badge. None of it told the user anything the labels did not, and all of it
competed with the readings. What the headers did carry that mattered, the
range state and the ring shown while hardware work runs, now sits in the
heading of the Cyan kernel compatibility panel.
"""

from frontends.desktop.components.busy_spinner import BusyBadge
from frontends.desktop.components.page_widgets import MetricTile
from frontends.desktop.components.widgets import IconBadge
from frontends.desktop.pages.gpu_governor_view import GpuGovernorView


def test_no_card_has_a_title_row_icon_or_badge(qtbot):
    view = GpuGovernorView()
    qtbot.addWidget(view)
    assert view._configuration._headerless and view._telemetry._headerless
    assert view.findChildren(IconBadge) == []
    tiles = view.findChildren(MetricTile)
    assert len(tiles) == 6


def test_the_range_state_and_the_busy_ring_sit_in_the_cyan_compatibility_heading(qtbot):
    view = GpuGovernorView()
    qtbot.addWidget(view)
    view.resize(1500, 900)
    view.show()
    qtbot.waitExposed(view)
    pill, ring = view._safe_pill, view._busy_badge
    assert isinstance(ring, BusyBadge)
    assert view._compat_panel.isAncestorOf(pill) and view._compat_panel.isAncestorOf(ring)
    assert not view.profiles_panel.isAncestorOf(pill)
    assert pill.isVisible() and not ring.isVisible()

    view.set_operation_busy(True, "GPU operation in progress")
    assert ring.isVisible() and not pill.isVisible()
    assert ring.label.text() == "GPU operation in progress"

    view.set_operation_busy(False, "")
    assert pill.isVisible() and not ring.isVisible()


def test_on_oberon_the_status_moves_up_beside_the_profiles(qtbot):
    """Oberon has no Cyan compatibility panel; the range state must stay visible."""
    view = GpuGovernorView()
    qtbot.addWidget(view)
    view.resize(1500, 900)
    view.show()
    qtbot.waitExposed(view)
    view.set_oberon_mode(True)
    assert view.profiles_panel.isAncestorOf(view._safe_pill)
    assert view.profiles_panel.isAncestorOf(view._busy_badge)
    assert view._safe_pill.isVisible()
    view.set_oberon_mode(False)
    assert view._compat_panel.isAncestorOf(view._safe_pill)
    assert view._compat_panel.isAncestorOf(view._busy_badge)
