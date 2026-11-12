"""Additional settings › Memory and swap: the swap table and the TTM / VRAM rails.

The workspace presents the panel's hidden combos; the render code keeps feeding
those combos, so what the user picks has to land in them.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from PyQt6.QtCore import QPointF, QSettings, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QComboBox

from frontends.desktop.components.dashboard_widgets import PreparationSidebar
from frontends.desktop.components.memory_workspace import (
    ComboRail,
    SwapList,
    _gib_label,
    _mib_label,
    read_vram_total_mb,
)

_KEEP = []

pytestmark = pytest.mark.usefixtures("qapp")


def _sidebar():
    app = QApplication.instance() or QApplication([])
    temporary = TemporaryDirectory()
    _KEEP.append(temporary)
    settings = QSettings(str(Path(temporary.name) / "m.ini"), QSettings.Format.IniFormat)
    sidebar = PreparationSidebar(settings=settings, standalone=True)
    sidebar.resize(1200, 900)
    sidebar.show()
    app.processEvents()
    return sidebar


def _combo(sizes, current=0):
    combo = QComboBox()
    for size in sizes:
        combo.addItem(str(size), size)
    combo.setCurrentIndex(current)
    return combo


def _click(widget, x):
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress, QPointF(x, 10), QPointF(x, 10),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    widget.mousePressEvent(event)
    widget.mouseReleaseEvent(event)


def test_the_workspace_replaces_the_old_controls_and_keeps_the_combos_as_data():
    sidebar = _sidebar()
    workspace = sidebar.memory_workspace
    assert workspace.swap_cards.combo is sidebar.memory_policy_combo
    assert workspace.ttm_rail.combo is sidebar.ttm_limit_combo
    assert workspace.vram_rail.combo is sidebar.vram_size_combo
    for combo in (sidebar.memory_policy_combo, sidebar.ttm_limit_combo, sidebar.vram_size_combo):
        assert combo.isHidden()
    assert sidebar.memory_detail.isHidden()
    assert sidebar.memory_scope.isHidden()


def test_the_zram_warning_is_never_a_window_of_its_own():
    sidebar = _sidebar()
    frame = sidebar.memory_zram_warning_frame
    sidebar.memory_zram_warning.setText("ZRAM is active")
    frame.show()
    QApplication.processEvents()
    assert not frame.isWindow()
    assert frame.parentWidget() is not None
    assert not frame.isVisible(), "it lives in the hidden holder, so it never draws"


def test_each_swap_policy_of_the_panel_is_a_row_of_the_table():
    sidebar = _sidebar()
    swap = sidebar.memory_workspace.swap_cards
    combo = sidebar.memory_policy_combo
    assert len(swap.rows) == combo.count() >= 2
    assert [row.isEnabled() for row in swap.rows] == [combo.isEnabled()] * combo.count()


def test_picking_a_row_sets_the_combo_it_is_bound_to():
    combo = _combo([0, 1, 2])
    swap = SwapList(combo, {})
    swap.rows[2].clicked.emit()
    assert combo.currentIndex() == 2
    swap.rows[0].clicked.emit()
    assert combo.currentIndex() == 0


def test_a_policy_the_distribution_cannot_use_is_not_pickable():
    combo = _combo([0, 1, 2])
    swap = SwapList(combo, {})
    combo.model().item(1).setEnabled(False)
    swap.refresh()
    assert swap.rows[0].isEnabled() and not swap.rows[1].isEnabled()
    combo.setEnabled(False)
    swap.refresh()
    assert not any(row.isEnabled() for row in swap.rows)


def test_the_swap_location_row_only_shows_with_a_policy_that_creates_a_file():
    sidebar = _sidebar()
    sidebar.memory_swap_target_combo.setVisible(True)
    sidebar.memory_workspace.swap_cards.refresh()
    footer = sidebar.memory_workspace.swap_cards._footer
    assert not footer.isHidden()
    sidebar.memory_swap_target_combo.setVisible(False)
    QApplication.processEvents()
    assert footer.isHidden()


def test_the_rail_has_one_stop_per_size_and_clicking_picks_the_nearest():
    combo = _combo([4096, 8192, 12288, 14336])
    rail = ComboRail(combo, _gib_label, 1024)
    rail.resize(700, rail.height())
    stops = rail.stops()
    assert [size for _i, size, _on in stops] == [4096, 8192, 12288, 14336]
    _click(rail, rail.width() - 30)
    assert combo.currentIndex() == 3
    _click(rail, 30)
    assert combo.currentIndex() == 0


def test_the_rail_ignores_items_that_are_not_sizes_and_skips_disabled_stops():
    combo = QComboBox()
    combo.addItem("Not set", None)
    combo.addItem("8", 8192)
    combo.addItem("12", 12288)
    combo.addItem("14", 14336)
    combo.model().item(2).setEnabled(False)
    rail = ComboRail(combo, _gib_label, 1024)
    assert [size for _i, size, _on in rail.stops()] == [8192, 12288, 14336]
    assert [on for _i, _size, on in rail.stops()] == [True, False, True]
    combo.setCurrentIndex(1)
    rail.step(1)
    assert combo.currentIndex() == 3, "stepping jumps over the stop the system cannot take"
    rail.step(-1)
    assert combo.currentIndex() == 1


def test_a_disabled_combo_leaves_every_stop_dimmed():
    combo = _combo([4096, 8192])
    combo.setEnabled(False)
    rail = ComboRail(combo, _gib_label, 1024)
    assert not any(on for _i, _size, on in rail.stops())
    _click(rail, rail.width() - 30)
    assert combo.currentIndex() == 0


def test_the_ttm_rail_marks_what_the_kernel_uses_now():
    sidebar = _sidebar()
    workspace = sidebar.memory_workspace
    workspace.set_runtime({"ttm_limit_bytes": 14 * 1024 ** 3})
    assert workspace.ttm_rail.current_mb == 14 * 1024
    workspace.set_runtime({})
    assert workspace.ttm_rail.current_mb is None


def test_the_labels_read_in_gib_and_mib():
    assert _gib_label(14) == "14 GiB"
    assert _mib_label(512) == "512 MiB"
    assert _mib_label(2048) == "2 GiB"


def test_the_vram_total_is_read_from_the_first_card_that_reports_it(tmp_path):
    assert read_vram_total_mb(tmp_path) is None
    bad = tmp_path / "card0" / "device"
    bad.mkdir(parents=True)
    good = tmp_path / "card1" / "device"
    good.mkdir(parents=True)
    (good / "mem_info_vram_total").write_text(str(512 * 1024 ** 2))
    assert read_vram_total_mb(tmp_path) == 512
