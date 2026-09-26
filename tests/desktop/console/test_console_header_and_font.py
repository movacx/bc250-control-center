"""The console's header says what its buttons do, and its grid is monospace.

The interface stylesheet gives every widget the interface face. The grid was
measured in a monospace font and painted in that proportional one, so text
ran short of its own columns and the caret after "[sudo] password for …:"
sat a dozen cells past the colon.
"""

from __future__ import annotations

import pytest
from PyQt6.QtGui import QFontInfo, QFontMetricsF
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

from frontends.desktop.console.console_panel import (
    HEADER_LABELS_WIDTH,
    MAXIMUM_TABS,
    ConsolePanel,
)
from frontends.desktop.i18n import tr
from frontends.desktop.theme import application_stylesheet


@pytest.fixture
def panel(qtbot):
    host = QWidget()
    host.resize(1300, 900)
    host.setStyleSheet(application_stylesheet("dark", scale=100))
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(QWidget(host), 1)
    widget = ConsolePanel(host)
    layout.addWidget(widget)
    qtbot.addWidget(host)
    host.show()
    yield widget
    widget.shutdown()


def test_the_grid_paints_in_the_font_it_is_measured_in(qtbot, panel):
    view = panel.view
    assert QFontInfo(view._grid_font).fixedPitch()
    text = "[sudo] password for fabianbeita:"
    advance = QFontMetricsF(view._grid_font).horizontalAdvance(text)
    assert abs(advance - len(text) * view._cell_width) <= 1.0


def test_plus_opens_a_clean_shell_beside_the_running_workflow(qtbot, panel):
    assert panel.run(["/bin/sh", "-c", "sleep 5"], title="Install", launch_path="/tmp/install.sh")
    workflow = panel.active_tab
    assert panel.new_button.isEnabled()
    assert panel.new_button.toolTip() == tr("New terminal")

    assert panel.open_new_shell()
    shell = panel.active_tab
    assert shell is not workflow and shell.interactive and shell.running
    assert panel.tab_count() == 2
    # A shell has no workflow script to hand to a desktop terminal.
    assert not panel.external_button.isEnabled()
    panel._activate(workflow)
    assert panel.external_button.isEnabled()


def test_plus_is_unavailable_once_every_tab_is_taken(qtbot, panel):
    for _ in range(MAXIMUM_TABS):
        assert panel.open_new_shell()
    assert panel.tab_count() == MAXIMUM_TABS
    assert not panel.new_button.isEnabled()
    assert panel.open_new_shell() is False


def test_the_actions_carry_their_word_when_there_is_room(qtbot, panel):
    panel.slide_in()
    qtbot.waitUntil(lambda: panel.is_open)
    assert panel.width() >= HEADER_LABELS_WIDTH
    assert panel.copy_button.text() == tr("Copy")
    assert panel.hide_button.text() == tr("Hide")
    assert "F4" in panel.hide_button.toolTip()

    panel.window().resize(700, 900)
    panel.resize(700, panel.height())
    QApplication.processEvents()
    assert panel.copy_button.text() == ""
    assert panel.copy_button.toolTip() == tr("Copy")
    assert panel.copy_button.accessibleName() == tr("Copy")
