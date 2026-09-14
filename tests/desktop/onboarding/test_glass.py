"""The frosted portrait behind the first-run panel.

The point of the glass is that the shell stays recognisable and stops being
legible. These hold the two properties the panel depends on: the portrait is
the size of what it photographed, and asking for one of something that has no
size is an ordinary answer rather than a crash — which is exactly what happens
during the first layout pass, before the window has been placed.
"""

from PyQt6.QtGui import QColor, QPixmap

from frontends.desktop.onboarding.glass import frosted, frosted_snapshot


def _filled(width: int, height: int) -> QPixmap:
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor("#203040"))
    return pixmap


def test_the_portrait_is_the_size_of_what_it_photographed(qapp):
    source = _filled(400, 250)

    assert frosted(source).size() == source.size()


def test_a_pixmap_too_small_to_halve_comes_back_untouched(qapp):
    """The working copy is half-size; one pixel of that is not a blur."""
    tiny = _filled(2, 2)

    assert frosted(tiny) is tiny


def test_an_empty_pixmap_is_not_a_failure(qapp):
    assert frosted(QPixmap()).isNull()


def test_a_widget_with_no_size_yet_yields_no_portrait(qtbot):
    """Before the window is placed there is nothing to photograph."""
    from PyQt6.QtWidgets import QWidget

    widget = QWidget()
    qtbot.addWidget(widget)
    widget.resize(0, 0)

    assert frosted_snapshot(widget).isNull()


def test_the_portrait_keeps_the_colour_and_loses_the_detail(qtbot):
    """Glass, not a scrim: the shell's colours survive, its words do not."""
    from PyQt6.QtGui import QPainter
    from PyQt6.QtWidgets import QWidget

    widget = QWidget()
    qtbot.addWidget(widget)
    widget.resize(300, 200)
    source = QPixmap(300, 200)
    source.fill(QColor("#101820"))
    painter = QPainter(source)
    # A single hard white line: after the blur no pixel may still be white.
    painter.fillRect(10, 90, 280, 4, QColor("#FFFFFF"))
    painter.end()

    image = frosted(source).toImage()
    brightest = max(
        QColor(image.pixel(x, y)).lightness()
        for y in range(0, image.height(), 3)
        for x in range(0, image.width(), 3)
    )
    assert brightest < 240, "the line survived the blur intact"
    assert brightest > 25, "everything was flattened; this is a scrim, not glass"
