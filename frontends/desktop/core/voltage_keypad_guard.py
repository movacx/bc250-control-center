"""Qt-safe guard that prevents passive refresh from destroying keypad edits."""

from __future__ import annotations

from collections.abc import Iterable

from PyQt6.QtWidgets import QWidget


def _direct_edit_active(spin: object) -> bool:
    try:
        tracking = spin.property("gamepadKeypadKeyboardTracking")
        if tracking is None:
            return False
        return bool(spin.hasFocus() or spin.lineEdit().hasFocus())
    except (AttributeError, RuntimeError, TypeError):
        return False


def _top_level_widgets(application: object) -> tuple[object, ...]:
    if application is None:
        return ()
    try:
        return tuple(application.topLevelWidgets())
    except (AttributeError, RuntimeError, TypeError):
        return ()


def _widget_tree(top: object) -> tuple[object, ...]:
    try:
        return (top, *top.findChildren(QWidget))
    except (AttributeError, RuntimeError, TypeError):
        return ()


def _visible_keypad_targets(top_levels: Iterable[object]) -> tuple[object, ...]:
    targets = []
    for top in top_levels:
        for widget in _widget_tree(top):
            try:
                if widget.property("gamepadKeypad") and widget.isVisible():
                    targets.append(getattr(widget, "_target", None))
            except (AttributeError, RuntimeError, TypeError):
                continue
    return tuple(targets)


def voltage_keypad_edit_active(
    spinboxes: Iterable[object], *, application: object,
) -> bool:
    tracked = tuple(spinboxes)
    if not tracked:
        return False
    if any(_direct_edit_active(spin) for spin in tracked):
        return True
    targets = _visible_keypad_targets(_top_level_widgets(application))
    return any(target is spin for target in targets for spin in tracked)


def clear_voltage_keypad_state(spinboxes: Iterable[object]) -> None:
    for spin in tuple(spinboxes):
        try:
            stored = spin.property("gamepadKeypadKeyboardTracking")
            if stored is not None:
                spin.setKeyboardTracking(bool(stored))
                spin.setProperty("gamepadKeypadKeyboardTracking", None)
            spin.setProperty("gamepadKeypadDismissed", False)
        except (AttributeError, RuntimeError, TypeError):
            continue
