"""WrappedLabel and ActionGrid(fit_content): the pieces that keep Settings compact."""

from __future__ import annotations

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from frontends.desktop.pages.settings import ActionGrid, WrappedLabel

#: A paragraph that wraps right at the edge of its width, which is where
#: QLabel.heightForWidth answered one line too many.
PARAGRAPH = (
    "El botón En vivo arranca igualmente. Los bloqueos entre programas siguen activos, "
    "una placa cuyo firmware no es P3 se sigue rechazando, y también una placa en la que "
    "BC250-Telemetry se interrumpió a mitad de un cambio."
)


def _lines(label: WrappedLabel, width: int) -> int:
    metrics = label.fontMetrics()
    rect = metrics.boundingRect(QRect(0, 0, width, 100000), int(Qt.TextFlag.TextWordWrap), label.text())
    return rect.height()


def test_the_height_is_the_height_of_the_painted_text_at_every_width(qtbot):
    label = WrappedLabel(PARAGRAPH)
    qtbot.addWidget(label)
    for width in range(300, 900, 7):
        assert label.heightForWidth(width) == _lines(label, width)


def test_a_label_in_a_layout_takes_exactly_its_text_and_anchors_it_to_the_top(qtbot):
    host = QWidget()
    layout = QVBoxLayout(host)
    label = WrappedLabel(PARAGRAPH)
    layout.addWidget(label)
    layout.addStretch(1)
    qtbot.addWidget(host)
    host.resize(640, 400)
    host.show()
    qtbot.waitExposed(host)

    assert label.height() == _lines(label, label.width())
    assert label.alignment() & Qt.AlignmentFlag.AlignTop


def test_changing_the_text_refits_the_height(qtbot):
    host = QWidget()
    layout = QVBoxLayout(host)
    label = WrappedLabel("short")
    layout.addWidget(label)
    layout.addStretch(1)
    qtbot.addWidget(host)
    host.resize(500, 300)
    host.show()
    qtbot.waitExposed(host)
    short = label.height()

    label.setText(PARAGRAPH * 2)

    assert label.height() > short
    assert label.height() == _lines(label, label.width())


def _grid(qtbot, width, labels=("Refresh", "Enable", "Disable", "Details")):
    host = QWidget()
    layout = QVBoxLayout(host)
    grid = ActionGrid(columns=2, fit_content=True)
    for text in labels:
        grid.addWidget(QPushButton(text))
    layout.addWidget(grid)
    qtbot.addWidget(host)
    host.resize(width, 200)
    host.show()
    qtbot.waitExposed(host)
    grid._host = host  # the host owns the buttons: keep it alive with the grid
    return grid


def _rows(grid):
    return len({button.y() for button in grid._buttons})


def test_buttons_that_fit_share_one_row(qtbot):
    assert _rows(_grid(qtbot, 760)) == 1


def test_buttons_that_do_not_fit_wrap_into_two_columns(qtbot):
    long_labels = ("Actualizar el estado ahora mismo", "Activar el daemon de usuario",
                   "Desactivar el daemon de usuario", "Ver todos los detalles del daemon")
    grid = _grid(qtbot, 700, long_labels)
    assert _rows(grid) == 2
    assert len({button.x() for button in grid._buttons}) == 2


def test_a_grid_without_fit_content_keeps_its_old_behaviour(qtbot):
    host = QWidget()
    layout = QVBoxLayout(host)
    grid = ActionGrid(columns=3)
    for text in ("a", "b", "c"):
        grid.addWidget(QPushButton(text))
    layout.addWidget(grid)
    qtbot.addWidget(host)
    host.resize(800, 200)
    host.show()
    qtbot.waitExposed(host)
    assert _rows(grid) == 1
    host.resize(400, 200)
    qtbot.wait(50)
    assert _rows(grid) == 3  # one column under 520 px, exactly as before
