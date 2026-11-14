"""The Disk tab lists every real disk in its menu, as a task manager does.

The system disk is the tab itself; each other disk, an external drive
included, is one more entry with its own space, read/write chart and active
time. Unplugging the drive removes its entry on the next sample.
"""

from __future__ import annotations

import pytest

from frontends.desktop.core.performance_model import PerformanceRecorder
from frontends.desktop.core.performance_sample_presenter import present_disk_volumes
from frontends.desktop.core.performance_views import (
    VIEW_BY_KEY,
    disk_views,
    sync_disk_views,
    views_for,
)
from frontends.desktop.pages.performance import PerformancePage
from frontends.tui.pages.performance import view_options

GIB = 1024 ** 3
SYSTEM = {"mountpoint": "/", "label": "System", "kind": "system", "device": "/dev/nvme0n1p2",
          "used": 300 * GIB, "total": 400 * GIB, "percent": 75.0,
          "read_bps": 1024.0, "write_bps": 0.0, "active_percent": 1.0}
USB = {"mountpoint": "/run/media/u/Ventoy", "label": "Ventoy", "kind": "external", "device": "/dev/sdb1",
       "used": 20 * GIB, "total": 116 * GIB, "percent": 17.2,
       "read_bps": 40 * 1024 ** 2, "write_bps": 2 * 1024 ** 2, "active_percent": 63.0}
BASE = {
    "cpu": {"usage_percent": 9.0, "frequency_mhz": 1070},
    "gpu": {"usage_percent": 40.0, "frequency_mhz": 1500},
    "memory": {"usage_percent": 38.0, "used": 6 * GIB, "total": 16 * GIB},
    "network": {"download_bps": 0, "upload_bps": 0, "interface": "enp3s0"},
}


def _sample(*volumes):
    return {**BASE, "disk": {"usage_percent": 75.0, "used": 300 * GIB, "total": 400 * GIB,
                             "read_bps": 1024.0, "write_bps": 0.0, "volumes": list(volumes)}}


@pytest.fixture(autouse=True)
def _no_disk_views_left_behind():
    yield
    sync_disk_views(())


def test_one_disk_needs_no_menu_and_two_disks_list_both():
    assert disk_views([SYSTEM]) == ()
    views = disk_views([SYSTEM, USB])
    assert [view.key for view in views] == ["disk", "disk:/run/media/u/Ventoy"]
    assert views[0].is_summary and not views[0].literal
    assert views[1].volume == "/run/media/u/Ventoy" and not views[1].is_summary
    # A volume label is shown as written; "System" goes through the catalogue.
    assert views[1].shown_title(lambda text: f"<{text}>") == "Ventoy"
    assert views[0].shown_title(lambda text: f"<{text}>") == "<System>"


def test_plugging_and_unplugging_a_drive_adds_and_removes_its_menu_entry():
    assert sync_disk_views([SYSTEM, USB]) is True
    assert "disk:/run/media/u/Ventoy" in VIEW_BY_KEY
    assert sync_disk_views([SYSTEM, USB]) is False
    assert sync_disk_views([SYSTEM]) is True
    assert views_for("disk") == ()
    assert not [key for key in VIEW_BY_KEY if key.startswith("disk")]


def test_each_extra_disk_has_its_own_space_and_throughput_plan():
    (plan,) = present_disk_volumes(_sample(SYSTEM, USB), previous_peaks={})
    assert plan.key == "disk:/run/media/u/Ventoy"
    assert plan.primary == "17%"
    assert plan.context.startswith("20.0 GiB / 116.0 GiB")
    assert dict(plan.graph_values) == {"Read": 40 * 1024 ** 2, "Write": 2 * 1024 ** 2}
    assert plan.stats[2] == "63%"


def test_the_recorder_charts_the_drive_and_forgets_it_when_unplugged():
    recorder = PerformanceRecorder(inventory=type("Empty", (), {"read": lambda self, sample: []})())
    recorder.record(_sample(SYSTEM, USB))
    recorder.record(_sample(SYSTEM, USB))
    view = VIEW_BY_KEY["disk:/run/media/u/Ventoy"]
    history, definition, (primary, _context, stats), summary = recorder.reading("disk", view)
    assert summary is True and definition.key == "disk"
    assert len(history.times) == 2 and primary == "17%"
    assert stats[2] == "63%"
    # The terminal's menu names it too.
    assert any("Ventoy" in text for _key, text in view_options(views_for("disk"), "disk", recorder.available))

    recorder.record(_sample(SYSTEM))
    assert recorder.volume_histories == {}
    assert "disk:/run/media/u/Ventoy" not in recorder.plans


@pytest.fixture
def page(qtbot):
    page = PerformancePage(object())
    qtbot.addWidget(page)
    page.resize(1400, 900)
    page.show()
    qtbot.wait(5)
    return page


def test_the_disk_tab_shows_the_chosen_drive_and_falls_back_when_it_is_unplugged(page):
    page._sample_ready(_sample(SYSTEM, USB))
    assert page.tiles["disk"].has_views()
    page._choose_view("disk", "disk:/run/media/u/Ventoy")
    page._sample_ready(_sample(SYSTEM, USB))

    assert page.detail.primary.text() == "17%"
    assert "Ventoy" in page.detail.title.text()
    assert page.detail.subtitle.text() == "/run/media/u/Ventoy"
    assert len(page.volume_histories["disk:/run/media/u/Ventoy"].times) == 2

    page._sample_ready(_sample(SYSTEM))
    assert not page.tiles["disk"].has_views()
    assert page._current_view("disk") == "disk"
    assert page.detail.primary.text() == "75%"
    assert page.volume_histories == {}


def test_the_open_menu_gains_the_drive_when_it_is_plugged_in(page):
    page._sample_ready(_sample(SYSTEM, USB))
    page.pin_views_menu("disk")
    assert [row.view.key for row in page.flyout.rows] == ["disk", "disk:/run/media/u/Ventoy"]
    assert [row.title.text() for row in page.flyout.rows][1] == "Ventoy"
    page.unpin_views_menu()
