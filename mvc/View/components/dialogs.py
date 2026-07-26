from __future__ import annotations

from types import MethodType
from typing import Any
import weakref

from PyQt6.QtCore import QTimer

try:
    from PyQt6 import sip
except ImportError:  # pragma: no cover - PyQt6 provides sip at runtime.
    sip = None
from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QSizePolicy, QWidget


_DEFAULT_SCREEN_MARGIN = 48


def enable_adaptive_dialog(
    dialog: QDialog,
    *,
    preferred_width: int,
    preferred_height: int = 0,
    minimum_width: int = 360,
    minimum_height: int = 0,
    screen_margin: int = _DEFAULT_SCREEN_MARGIN,
) -> None:
    """Install content-aware sizing on a dialog without fixing its dimensions.

    The target size is recalculated against the active screen every time the
    dialog is shown or retranslates. Wrapped labels may grow vertically, while
    scroll-based dialogs retain a useful preferred size without exceeding the
    available desktop geometry.
    """

    dialog.setProperty("adaptiveDialog", True)
    dialog.setProperty("adaptivePreferredWidth", max(1, int(preferred_width)))
    dialog.setProperty("adaptivePreferredHeight", max(0, int(preferred_height)))
    dialog.setProperty("adaptiveMinimumWidth", max(1, int(minimum_width)))
    dialog.setProperty("adaptiveMinimumHeight", max(0, int(minimum_height)))
    dialog.setProperty("adaptiveScreenMargin", max(16, int(screen_margin)))
    dialog.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

    def fit_to_content(instance: QDialog) -> None:
        fit_dialog_to_content(instance)
        # Hidden stacked pages and translated wrapping labels may receive their
        # final width only after the first event-loop pass. A weak deferred pass
        # cannot outlive a dialog that is closed/deleted in the meantime.
        _defer_dialog_fit(instance)

    # A callable hook lets the shared i18n localizer request a new geometry pass
    # after longer translated strings replace the original copy.
    dialog.fit_to_content = MethodType(fit_to_content, dialog)  # type: ignore[attr-defined]
    _defer_dialog_fit(dialog)



def _dialog_alive(dialog: QDialog | None) -> bool:
    if dialog is None:
        return False
    try:
        if sip is not None and sip.isdeleted(dialog):
            return False
        dialog.objectName()
        return True
    except (RuntimeError, TypeError, AttributeError):
        return False


def _defer_dialog_fit(dialog: QDialog) -> None:
    """Queue geometry work without retaining a deleted Qt wrapper."""

    try:
        reference = weakref.ref(dialog)
    except TypeError:
        return

    def run_if_alive() -> None:
        target = reference()
        if not _dialog_alive(target):
            return
        try:
            fit_dialog_to_content(target)
        except (RuntimeError, TypeError):
            return

    QTimer.singleShot(0, run_if_alive)


def reflow_wrapped_labels(root: QWidget) -> None:
    """Recalculate the minimum height of every wrapped label below *root*.

    Qt normally provides ``heightForWidth`` for ``QLabel``, but labels created
    inside a hidden ``QStackedWidget`` page can be measured before their real
    viewport width is known.  Once that page becomes visible the layout may
    keep the stale one-line height.  Explicitly recomputing it is inexpensive
    and makes translated, multi-line copy deterministic.
    """

    labels = []
    if isinstance(root, QLabel):
        labels.append(root)
    try:
        labels.extend(root.findChildren(QLabel))
    except (RuntimeError, TypeError):
        return

    for label in labels:
        if not label.wordWrap():
            continue
        try:
            label.setMinimumHeight(0)
            label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            label.updateGeometry()
            width = label.contentsRect().width()
            if width <= 1 and label.parentWidget() is not None:
                width = label.parentWidget().contentsRect().width()
            if width <= 1:
                continue
            height = label.heightForWidth(width)
            if height > 0:
                label.setMinimumHeight(height)
            label.updateGeometry()
        except (RuntimeError, TypeError):
            continue

    layout = root.layout()
    if layout is not None:
        layout.invalidate()
        layout.activate()
    root.updateGeometry()

def fit_dialog_to_content(dialog: QDialog) -> None:
    preferred_width = _int_property(dialog, "adaptivePreferredWidth", 520)
    preferred_height = _int_property(dialog, "adaptivePreferredHeight", 0)
    minimum_width = _int_property(dialog, "adaptiveMinimumWidth", 360)
    minimum_height = _int_property(dialog, "adaptiveMinimumHeight", 0)
    screen_margin = _int_property(dialog, "adaptiveScreenMargin", _DEFAULT_SCREEN_MARGIN)

    screen = dialog.screen() or QApplication.primaryScreen()
    if screen is not None:
        available = screen.availableGeometry()
        maximum_width = max(280, available.width() - screen_margin)
        maximum_height = max(220, available.height() - screen_margin)
    else:
        maximum_width = 1_200
        maximum_height = 900

    minimum_width = min(minimum_width, maximum_width)
    minimum_height = min(minimum_height, maximum_height)
    dialog.setMinimumSize(minimum_width, minimum_height)
    dialog.setMaximumSize(maximum_width, maximum_height)

    for label in dialog.findChildren(QLabel):
        if label.wordWrap():
            label.setMinimumWidth(0)
            label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            label.updateGeometry()

    reflow_wrapped_labels(dialog)

    layout = dialog.layout()
    if layout is not None:
        layout.invalidate()
        layout.activate()

    # Establish the wrapping width first, then ask Qt for the resulting height.
    width = min(maximum_width, max(minimum_width, preferred_width))
    initial_height = max(minimum_height, min(maximum_height, preferred_height or dialog.height()))
    dialog.resize(width, initial_height)
    if layout is not None:
        layout.invalidate()
        layout.activate()
    dialog.adjustSize()

    hint = dialog.sizeHint()
    target_width = min(maximum_width, max(minimum_width, preferred_width, hint.width()))
    target_height = min(maximum_height, max(minimum_height, preferred_height, hint.height()))
    dialog.resize(target_width, target_height)
    dialog.updateGeometry()


def center_dialog(dialog: QDialog) -> None:
    parent = dialog.parentWidget()
    if parent is not None:
        target = parent.window().frameGeometry()
    else:
        screen = dialog.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        target = screen.availableGeometry()
    geometry = dialog.frameGeometry()
    geometry.moveCenter(target.center())
    dialog.move(geometry.topLeft())


def _int_property(dialog: QDialog, name: str, default: int) -> int:
    value: Any = dialog.property(name)
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default
