"""Every real disk has a row on the Cooling panel, and a removed one loses it."""

from __future__ import annotations

import pytest

from frontends.desktop.core.state import DashboardState
from frontends.desktop.pages.dashboard import DashboardPage
from frontends.tui.pages.dashboard import extra_disk_meters

GIB = 1 << 30
SYSTEM = {"mountpoint": "/", "label": "System", "kind": "system", "used": 100 * GIB, "total": 400 * GIB, "percent": 25.0}
USB = {"mountpoint": "/run/media/u/Backup", "label": "Backup", "kind": "external", "used": 930 * GIB, "total": 1000 * GIB, "percent": 93.0}


def _disk(*volumes):
    return {"disk": {"used": 100 * GIB, "total": 400 * GIB, "usage_percent": 25.0, "volumes": list(volumes)}}


@pytest.fixture
def page(qtbot):
    page = DashboardPage(object())
    qtbot.addWidget(page)
    return page


def test_the_state_keeps_the_extra_disks_and_the_last_list_when_a_sample_omits_it():
    state = DashboardState().with_live_metrics(_disk(SYSTEM, USB))
    assert [row[0] for row in state.extra_disks] == ["/run/media/u/Backup"]

    partial = state.with_live_metrics({"cpu": {"usage_percent": 4}})
    assert partial.extra_disks == state.extra_disks
    assert state.with_live_metrics(_disk(SYSTEM)).extra_disks == ()


def test_a_plugged_drive_gets_a_storage_row_that_goes_away_when_unplugged(page):
    details = page.fan_card.details

    page.apply_state(page.state.with_live_metrics(_disk(SYSTEM, USB)))
    reading = details.readings["disk:/run/media/u/Backup"]
    assert details.group_of("disk:/run/media/u/Backup") == "Storage"
    assert reading.label.text() == "Backup"
    assert reading.property("tone") == "warning"
    # The M.2 drive's own row is still the first disk.
    assert details.group_of("storage") == "M.2 drive"
    # A second sample updates the row in place.
    page.apply_state(page.state.with_live_metrics(_disk(SYSTEM, USB)))
    assert details.readings["disk:/run/media/u/Backup"] is reading

    page.apply_state(page.state.with_live_metrics(_disk(SYSTEM)))
    assert not [key for key in details.readings if key.startswith("disk:")]
    assert "Storage" not in details.groups


def test_the_storage_group_sits_before_the_bios(page):
    page.apply_state(page.state.with_live_metrics(_disk(SYSTEM, USB)))
    titles = [group.title.source_text for group, _column in page.fan_card.details._placement]
    assert titles.index("Storage") == titles.index("BIOS") - 1


def test_the_terminal_dashboard_draws_one_meter_per_extra_disk():
    assert extra_disk_meters([SYSTEM]) == []
    blocks = extra_disk_meters([SYSTEM, USB])
    assert len(blocks) == 2
    assert blocks[1].label == "Backup"
