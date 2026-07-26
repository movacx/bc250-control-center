from __future__ import annotations

"""Shared responsive-layout helpers for the definitive Qt interface.

The helpers deliberately stay small: pages keep ownership of their visual
hierarchy while sharing the rules that make a QScrollArea and its content
actually shrink to the viewport instead of preserving an accidental desktop
minimum width.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QAbstractScrollArea, QFrame, QGridLayout, QScrollArea, QSizePolicy, QWidget


PAGE_SMALL = 640
PAGE_MEDIUM = 900
PAGE_LARGE = 1180
QT_MAX_SIZE = 16_777_215


def configure_responsive_scroll_area(scroll: QScrollArea, content: QWidget) -> None:
    """Configure a page scroll area for vertical-only, width-driven reflow."""

    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
    scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    scroll.setMinimumSize(0, 0)

    content.setMinimumSize(0, 0)
    content.setMaximumWidth(QT_MAX_SIZE)
    content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)


def effective_viewport_width(owner: QWidget, scroll: QScrollArea | None = None) -> int:
    """Return the current page width without trusting a stale viewport size.

    During the first desktop render Qt resizes the page before the internal
    ``QScrollArea.viewport()`` has completed its own layout pass.  Reading the
    viewport at that instant can therefore return the tiny construction width
    (often close to 100 px) even though the main window is already maximized.
    That stale value used to select the one-column/mobile layout until the user
    manually resized the window.

    The owner is the direct child of the central ``QStackedWidget`` and has
    zero outer margins on all responsive pages, so its contents rect is the
    authoritative width while a resize event is in flight.  The viewport is
    retained as a fallback for isolated widgets and tests where the owner has
    not received a useful geometry yet.
    """

    owner_width = owner.contentsRect().width()
    if owner_width > 1:
        return owner_width
    if scroll is not None:
        viewport_width = scroll.viewport().contentsRect().width()
        if viewport_width > 0:
            return viewport_width
    return max(1, owner.width())


def clear_grid(layout: QGridLayout, *, reset_columns: int = 12, reset_rows: int = 24) -> None:
    """Detach every managed widget and remove stale stretch/minimum metadata."""

    while layout.count():
        # Keep widgets parented to the page while they are moved between grid
        # cells. Reparenting through ``None`` hides them and can create a visible
        # flash during a live resize.
        layout.takeAt(0)
    for column in range(reset_columns):
        layout.setColumnStretch(column, 0)
        layout.setColumnMinimumWidth(column, 0)
    for row in range(reset_rows):
        layout.setRowStretch(row, 0)
        layout.setRowMinimumHeight(row, 0)


def responsive_columns(width: int, *breakpoints: tuple[int, int], fallback: int = 1) -> int:
    """Choose a column count from descending ``(minimum_width, columns)`` pairs."""

    for minimum_width, columns in breakpoints:
        if width >= minimum_width:
            return max(1, int(columns))
    return max(1, int(fallback))
