"""Do visual work only when it shows: a look that changed, a page on screen.

``setStyleSheet`` and an unpolish/polish pair make Qt work out the style of
the widget again, and of every widget below it, even when the sheet or the
property is the same as before. The pages refresh their readings every
second, and most rows read the same tone, border and colours they read a
second earlier: restyling them anyway was most of what made switching
between pages stutter on a BC-250.
"""

from __future__ import annotations

from collections.abc import Mapping

from PyQt6.QtWidgets import QWidget


def set_style_sheet(widget: QWidget, sheet: str) -> bool:
    """Give ``widget`` this style sheet; True when it was a different one."""
    if widget.styleSheet() == sheet:
        return False
    widget.setStyleSheet(sheet)
    return True


def repolish(*widgets: QWidget) -> None:
    """Make the style sheet read the widgets' dynamic properties again."""
    for widget in widgets:
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)


def set_style_properties(
    widget: QWidget,
    values: Mapping[str, object],
    *also: QWidget,
) -> bool:
    """Set the properties the style sheet selects on, repolishing on a change.

    ``also`` are other widgets whose selectors read these properties (a
    child coloured through its parent's property): Qt re-evaluates a
    selector only for the widget that is polished.
    """
    changed = False
    for name, value in values.items():
        if widget.property(name) != value:
            widget.setProperty(name, value)
            changed = True
    if changed:
        repolish(widget, *also)
    return changed


def set_style_property(widget: QWidget, name: str, value: object, *also: QWidget) -> bool:
    """One property; see :func:`set_style_properties`."""
    return set_style_properties(widget, {name: value}, *also)


def offscreen_in_shown_window(widget: QWidget) -> bool:
    """A page of the open window that is not the one on screen.

    Such a page can leave drawing a new state until it is shown. A widget
    whose window was never shown (a page on its own, as the tests build
    them) draws at once, as before.
    """
    return widget.window().isVisible() and not widget.isVisible()
