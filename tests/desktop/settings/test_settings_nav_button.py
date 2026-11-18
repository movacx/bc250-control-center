"""A long label in the settings sidebar keeps its icon and its left alignment."""
from PyQt6.QtWidgets import QGridLayout, QWidget

from frontends.desktop.pages import settings as page


def _column(qtbot, width=190):
    host = QWidget()
    host.setProperty("settingsPage", True)
    host.setStyleSheet(page.settings_stylesheet())
    host.setFixedWidth(width)
    layout = QGridLayout(host)
    buttons = {}
    for row, (key, text, icon) in enumerate([("general", "General", "settings_blue"),
                                             ("console", "Terminal and controls", "terminal_window_gray")]):
        buttons[key] = page.SettingsNavButton(key, text, icon)
        layout.addWidget(buttons[key], row, 0)
    qtbot.addWidget(host)
    host.resize(width, 200)
    host.show()
    qtbot.wait(30)
    return host, buttons


def _has_ink(image, x0, x1, y0, y1):
    background = image.pixelColor(x0, y0)
    return any(image.pixelColor(x, y) != background for x in range(x0, x1) for y in range(y0, y1))


def test_a_label_that_does_not_fit_wraps_and_the_row_grows(qtbot):
    _host, buttons = _column(qtbot)
    short, long = buttons["general"], buttons["console"]
    assert long.height() > short.height(), "the two-line label needs a taller row"
    assert long.heightForWidth(long.width()) <= long.height()
    assert short.heightForWidth(short.width()) == short.minimumHeight() == 34


def test_the_icon_is_drawn_at_the_left_of_a_wrapped_row(qtbot):
    _host, buttons = _column(qtbot)
    button = buttons["console"]
    image = button.grab().toImage()
    size = button.iconSize()
    left = page.SettingsNavButton.SIDE
    middle = (button.height() - size.height()) // 2
    assert _has_ink(image, left, left + size.width(), middle, middle + size.height())
    # Nothing is centred over the icon's column: the text starts after it.
    text_start = left + size.width() + page.SettingsNavButton.GAP
    assert _has_ink(image, text_start, text_start + 60, 4, button.height() - 4)


def test_the_label_is_never_replaced_or_shortened(qtbot):
    _host, buttons = _column(qtbot)
    assert buttons["console"].text() == "Terminal and controls"
    buttons["console"].setText("Terminal und Steuerung")
    assert buttons["console"].text() == "Terminal und Steuerung"
