"""The mouse wheel never changes a drop-down list by accident.

Scrolling a page with the pointer passing over a closed QComboBox changed
its value (a profile, a governor, a HelixSR setting) without a click.
``GuardedComboBox`` hands that wheel to the scroll area around the list
instead, so the page keeps scrolling. Choosing stays explicit: a click opens
the list, where the wheel moves through it as usual, and the keyboard is
untouched.

Every drop-down list of the application is one of these; a test reads the
sources and refuses a bare ``QComboBox()``.

It used to be an application-wide event filter written in Python. That crashed
the interpreter: Qt sends events to widgets while they are being destroyed, the
filter receives each of them as a Python object, and PyQt then hands out a
wrapper that is already being freed. Any Python filter on the application did
it (an empty one too), as soon as a page with enough widgets was torn down
while the filter was installed; a test ended in a segmentation fault. A virtual
method on the list itself only ever runs on a live widget.
"""

from __future__ import annotations

from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QAbstractScrollArea, QApplication, QComboBox, QWidget


class GuardedComboBox(QComboBox):
    """A ``QComboBox`` whose closed list leaves the wheel to the page around it."""

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt API name
        # Inside the open list the wheel belongs to the list.
        if self.view().isVisible():
            super().wheelEvent(event)
            return
        # As Qt would pass an ignored wheel on: to the nearest scroll area, and
        # to the one around it when the inner one is already at its end. It is
        # passed on here, not left to Qt, so that it happens once and in the
        # same way for a real wheel and for one sent by a test.
        for area in _scroll_areas_around(self):
            event.setAccepted(False)
            QApplication.sendEvent(area.viewport(), event)
            if event.isAccepted():
                break
        # Consumed: Qt must not offer it to the parents a second time.
        event.accept()


def _scroll_areas_around(widget: QWidget) -> list[QAbstractScrollArea]:
    areas = []
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QAbstractScrollArea):
            areas.append(parent)
        parent = parent.parentWidget()
    return areas
