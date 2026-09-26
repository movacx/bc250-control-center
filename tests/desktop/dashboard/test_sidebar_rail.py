"""The navigation rail: brand row, grouped modules, and nothing cut short.

The rail keeps one width in every language, so each label either fits,
wraps (the brand) or is elided with the full name in its tooltip (a row).
"""

from __future__ import annotations

import pytest
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import QHBoxLayout, QWidget

from frontends.desktop.components.sidebar import Sidebar
from frontends.desktop.i18n import (
    SUPPORTED_LANGUAGES,
    localize_widget_tree,
    set_language,
    tr,
)
from frontends.desktop.theme import COLORS, application_stylesheet


def _shell(qtbot, sidebar: Sidebar) -> QWidget:
    shell = QWidget()
    qtbot.addWidget(shell)
    shell.setStyleSheet(application_stylesheet("dark", scale=100))
    QHBoxLayout(shell).addWidget(sidebar)
    shell.resize(320, 760)
    shell.show()
    qtbot.wait(5)
    return shell


def test_the_modules_keep_their_order_under_two_captions(qtbot):
    sidebar = Sidebar()
    shell = _shell(qtbot, sidebar)  # noqa: F841 - keeps the window alive
    # LB/RB cycle through this order; the captions only label it.
    assert list(sidebar.buttons) == [
        "dashboard", "cpu", "gpu", "cu", "performance", "fans", "processes",
        "firmware", "settings",
    ]
    hardware, monitoring = sidebar.sections
    assert hardware.label.text() == tr("Hardware").upper()
    assert monitoring.label.text() == tr("Monitoring").upper()
    buttons = sidebar.buttons
    assert buttons["dashboard"].y() < hardware.y() < buttons["cpu"].y()
    assert buttons["cu"].y() < monitoring.y() < buttons["performance"].y()
    assert sidebar.footer_rule.y() < buttons["settings"].y()
    # Firmware waits at the bottom, just above the rule: it is used once in a
    # board's life, not every day.
    assert buttons["processes"].y() + buttons["processes"].height() < buttons["firmware"].y()
    assert buttons["firmware"].y() < sidebar.footer_rule.y()


def test_collapsed_the_rail_is_icons_and_rules(qtbot):
    sidebar = Sidebar()
    shell = _shell(qtbot, sidebar)  # noqa: F841 - keeps the window alive
    sidebar.set_collapsed(True)
    qtbot.wait(5)
    assert sidebar.width() == Sidebar.COLLAPSED_WIDTH
    assert not sidebar.brand_title.isVisible() and not sidebar.logo.isVisible()
    assert sidebar.toggle.isVisible() and sidebar.toggle.toolTip() == tr("Expand sidebar")
    for section in sidebar.sections:
        assert not section.label.isVisible() and section.rule.isVisible()
    for button in sidebar.buttons.values():
        assert button.text() == ""
        assert button.width() == button.height() and button.geometry().right() < sidebar.width() - 1
    sidebar.set_collapsed(False)
    qtbot.wait(5)
    assert sidebar.brand_title.isVisible() and sidebar.sections[0].label.isVisible()
    assert sidebar.buttons["dashboard"].text() == tr("Dashboard")
    # Expanding again used to leave every row at its bare text height.
    assert {button.height() for button in sidebar.buttons.values()} == {40}


def test_the_selected_row_lights_its_icon_in_the_chosen_accent(qtbot):
    """Every module wears the accent from Appearance, the GPU's included.

    Each module used to keep a colour of its own (purple for the GPU, orange
    for the compute units), so choosing an accent changed three rows of eight.
    """
    sidebar = Sidebar()
    shell = _shell(qtbot, sidebar)  # noqa: F841 - keeps the window alive
    button = sidebar.buttons["gpu"]
    selected = button.icon().pixmap(button.iconSize(), QIcon.Mode.Normal, QIcon.State.On).toImage()
    resting = button.icon().pixmap(button.iconSize(), QIcon.Mode.Normal, QIcon.State.Off).toImage()

    def ink(image) -> set[tuple[int, int, int]]:
        # The glyph is one flat colour; only its edges fade out.
        return {
            (colour.red() // 8, colour.green() // 8, colour.blue() // 8)
            for x in range(image.width())
            for y in range(image.height())
            if (colour := image.pixelColor(x, y)).alpha() > 160
        }

    def expected(key: str) -> set[tuple[int, int, int]]:
        colour = QColor(COLORS[key])
        return {(colour.red() // 8, colour.green() // 8, colour.blue() // 8)}

    def near(found: set, wanted: set) -> bool:
        # Blending the glyph's edge can land one step either side of a bucket.
        (target,) = wanted
        return bool(found) and all(
            all(abs(a - b) <= 1 for a, b in zip(colour, target)) for colour in found
        )

    assert near(ink(selected), expected("blue"))
    assert near(ink(resting), expected("muted"))


@pytest.mark.parametrize("language", sorted(SUPPORTED_LANGUAGES))
def test_no_label_is_cut_short_in_any_language(qtbot, language):
    try:
        set_language(language)
        sidebar = Sidebar()
        shell = _shell(qtbot, sidebar)
        # The shared pass that runs on every language change must not put a
        # full label back over an elided one.
        localize_widget_tree(shell, language)
        qtbot.wait(5)
        subtitle = sidebar.brand_subtitle
        width = subtitle.fontMetrics().horizontalAdvance(subtitle.text())
        assert width <= subtitle.width() or subtitle.height() >= 2 * subtitle.fontMetrics().height()
        for button in sidebar.buttons.values():
            shown = button.text()
            assert shown == button.full_text or shown.endswith("…"), (language, shown)
            assert button.toolTip() == button.full_text
            room = button.width() - 16 - button.iconSize().width() - 4
            assert button.fontMetrics().horizontalAdvance(shown) <= room, (language, shown)
        for section in sidebar.sections:
            label = section.label
            assert label.fontMetrics().horizontalAdvance(label.text()) <= label.width(), (language, label.text())
    finally:
        set_language("en")
