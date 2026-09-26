"""The chips row wraps instead of running off a narrow window."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton, QWidget

from frontends.desktop.components.flow_layout import FlowLayout


def test_items_that_do_not_fit_move_to_the_next_row(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    layout = FlowLayout(host, spacing=6)
    buttons = [QPushButton(f"Chip {index}") for index in range(6)]
    for button in buttons:
        button.setFixedSize(100, 24)
        layout.addWidget(button)
    buttons[5].hide()

    one_row = layout.heightForWidth(1000)
    assert one_row == 24
    # 320 px holds three 100 px chips with 6 px between them.
    assert layout.heightForWidth(320) == 24 + 6 + 24
    host.resize(320, 60)
    host.show()
    qtbot.waitExposed(host)
    assert buttons[3].y() > buttons[0].y() and buttons[3].x() == buttons[0].x()
    assert layout.count() == 6 and layout.itemAt(0).widget() is buttons[0]
    assert layout.expandingDirections() == Qt.Orientation(0)
    assert layout.takeAt(5).widget() is buttons[5] and layout.count() == 5
