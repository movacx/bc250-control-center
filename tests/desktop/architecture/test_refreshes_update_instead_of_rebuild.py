"""A refresh updates what is on screen; it does not build it again.

Every one of these panels re-reads the hardware on a timer — two, three or
five seconds — and every one of them used to answer by destroying its contents
and constructing them from scratch. The process table did it on every keystroke
in its search box, which is around a thousand widget constructions per letter.

Nothing failed, because rebuilding produces the correct picture. It just costs
a frame each time, and throws away the text selection, the scroll position and
the widget the controller was pointing at.

What is pinned here is object identity across a refresh: the same widget has to
still be there afterwards.
"""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QVBoxLayout, QWidget

# ------------------------------------------------------------------- drivers


@pytest.fixture
def driver_rows(qtbot):
    from frontends.desktop.pages.drivers import DriversPage

    class _Controller:
        def driver_inventory(self):
            return {}

    page = DriversPage(_Controller())
    qtbot.addWidget(page)
    return page


def _snapshot(network=(), bluetooth=()) -> dict:
    return {
        "family": "arch",
        "init_manager": "systemd",
        "supported_components": (),
        "network": list(network),
        "bluetooth_controllers": list(bluetooth),
        "printing": {},
        "usb_printers": [],
        "aic8800": {},
    }


def _rows(layout: QVBoxLayout) -> list[QWidget]:
    return [
        layout.itemAt(index).widget()
        for index in range(layout.count())
        if layout.itemAt(index).widget() is not None
    ]


def test_the_same_device_rows_survive_a_refresh(driver_rows):
    payload = _snapshot(network=[{"name": "enp1s0", "kind": "ethernet", "state": "up"}])
    driver_rows._apply_snapshot(payload)
    before = _rows(driver_rows.network_rows)
    driver_rows._apply_snapshot(payload)
    after = _rows(driver_rows.network_rows)
    assert before and [id(row) for row in before] == [id(row) for row in after]


def test_a_row_that_changes_is_updated_not_replaced(driver_rows):
    driver_rows._apply_snapshot(
        _snapshot(network=[{"name": "enp1s0", "kind": "ethernet", "state": "up"}])
    )
    row = _rows(driver_rows.network_rows)[0]
    driver_rows._apply_snapshot(
        _snapshot(network=[{"name": "enp1s0", "kind": "ethernet", "state": "down"}])
    )
    assert _rows(driver_rows.network_rows)[0] is row
    assert "down" in row.status.text().lower()


def test_rows_are_dropped_when_the_hardware_goes_away(driver_rows):
    driver_rows._apply_snapshot(
        _snapshot(
            network=[
                {"name": "enp1s0", "kind": "ethernet", "state": "up"},
                {"name": "wlan0", "kind": "wifi", "state": "up"},
            ]
        )
    )
    many = len(_rows(driver_rows.network_rows))
    driver_rows._apply_snapshot(_snapshot())
    assert len(_rows(driver_rows.network_rows)) < many


def test_the_drivers_page_reuses_a_recent_read_when_you_come_back(driver_rows):
    """It was the one page that refused its own cache, on a two-second timer."""
    from pathlib import Path

    source = Path("frontends/desktop/pages/drivers.py").read_text(encoding="utf-8")
    assert "fresh_for=0.0" not in source
    assert "refresh_delay_ms=0" not in source


# ----------------------------------------------------------- GPU safe points


@pytest.fixture
def safe_points(qtbot):
    from frontends.desktop.pages.gpu_governor_view import SafePointTable

    table = SafePointTable()
    qtbot.addWidget(table)
    return table


def test_the_safe_point_rows_survive_a_refresh(safe_points):
    before = _rows(safe_points._rows)
    safe_points.refresh(1000, 1850, unlocked=False)
    after = _rows(safe_points._rows)
    assert before and [id(row) for row in before] == [id(row) for row in after]


def test_moving_the_range_repaints_the_rows_that_changed(safe_points):
    safe_points.refresh(1000, 1500, unlocked=False)
    rows = _rows(safe_points._rows)
    looks = [row._look for row in rows]
    safe_points.refresh(1000, 1850, unlocked=False)
    assert [row._look for row in rows] != looks, "nothing was repainted"
    assert [id(row) for row in _rows(safe_points._rows)] == [id(row) for row in rows]


def test_a_row_whose_look_did_not_move_is_not_restyled(safe_points, monkeypatch):
    safe_points.refresh(1000, 1850, unlocked=False)
    repaints: list[int] = []
    for row in _rows(safe_points._rows):
        monkeypatch.setattr(
            row, "_refresh_palette", lambda: repaints.append(1), raising=False
        )
    safe_points.refresh(1000, 1850, unlocked=False)
    assert repaints == []


def test_a_shorter_backend_table_drops_the_extra_rows(safe_points):
    safe_points.refresh(1000, 1850, unlocked=False, points=[(1000, 900), (1500, 1000)])
    assert len(_rows(safe_points._rows)) == 2


# --------------------------------------------------------- the contract panel


def test_the_contract_lines_survive_a_refresh(qtbot):
    from frontends.desktop.pages.gpu_governor_view import ContractPanel

    panel = ContractPanel()
    qtbot.addWidget(panel)
    rows = [("Governor", "Cyan"), ("Method", "SMU"), ("Range", "1000-1850")]
    panel.set_rows(rows)
    before = list(panel._lines)
    panel.set_rows([("Governor", "Oberon"), ("Method", "SMU"), ("Range", "1000-2000")])
    assert before and [id(line) for line in before] == [id(line) for line in panel._lines]
    assert "Oberon" in panel._lines[0].reading.text()


def test_fewer_contract_rows_drop_the_extra_lines(qtbot):
    from frontends.desktop.pages.gpu_governor_view import ContractPanel

    panel = ContractPanel()
    qtbot.addWidget(panel)
    panel.set_rows([("a", "1"), ("b", "2"), ("c", "3")])
    panel.set_rows([("a", "1")])
    assert len(panel._lines) == 1


# ------------------------------------------------ the controller amplifier


def test_a_new_widget_does_not_schedule_a_whole_application_sweep():
    """With a controller connected this multiplied every rebuild above.

    Each ``ChildAdded`` asked for ``findChildren(QWidget)`` over every
    top-level window. The parent that received the child already contains
    everything that is new.
    """
    from pathlib import Path

    source = Path("frontends/desktop/core/gamepad.py").read_text(encoding="utf-8")
    assert "root=watched if event_type == QEvent.Type.ChildAdded else None" in source
    assert "_pending_normalize_roots" in source


def test_a_shown_window_still_sweeps_everything():
    """A window appearing really can add candidates anywhere."""
    from pathlib import Path

    source = Path("frontends/desktop/core/gamepad.py").read_text(encoding="utf-8")
    assert "self._pending_normalize_all = True" in source
    assert "self._normalize_all_top_levels()" in source


# ------------------------------------------------------------- the click path


def test_navigating_does_not_write_settings_inside_the_click():
    from pathlib import Path

    source = Path("frontends/desktop/app.py").read_text(encoding="utf-8")
    assert 'self.settings.setValue("settings/last_module", key)' not in source
    assert "QTimer.singleShot(0, self._remember_current_module)" in source
