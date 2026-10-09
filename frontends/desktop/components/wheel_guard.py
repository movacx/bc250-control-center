"""The mouse wheel never changes a drop-down list by accident.

Scrolling a page with the pointer passing over a closed QComboBox changed
its value (a profile, a governor, a HelixSR setting) without a click. The
guard sends that wheel to the scroll area around the list instead, so the
page keeps scrolling. Choosing stays explicit: a click opens the list, where
the wheel moves through it as usual, and the keyboard is untouched.
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtWidgets import QAbstractScrollArea, QApplication, QComboBox, QWidget


class ComboWheelGuard(QObject):
    """Application-wide event filter: see the module docstring."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API name
        if event.type() != QEvent.Type.Wheel or not isinstance(watched, QComboBox):
            return False
        # Inside the open list the wheel belongs to the list.
        if watched.view().isVisible():
            return False
        # As Qt would pass an ignored wheel on: the nearest scroll area, and
        # the one around it when the inner one is already at its end.
        for area in _scroll_areas_around(watched):
            event.setAccepted(False)
            QApplication.sendEvent(area.viewport(), event)
            if event.isAccepted():
                break
        return True


def _scroll_areas_around(widget: QWidget) -> list[QAbstractScrollArea]:
    areas = []
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QAbstractScrollArea):
            areas.append(parent)
        parent = parent.parentWidget()
    return areas


def install_combo_wheel_guard(app: QApplication) -> ComboWheelGuard:
    """Install the guard once for every window of ``app``."""
    guard = getattr(app, "_bc250_combo_wheel_guard", None)
    if guard is None:
        guard = ComboWheelGuard(app)
        app.installEventFilter(guard)
        app._bc250_combo_wheel_guard = guard
    return guard
