"""Compact density for layouts built in code.

The style sheet can tighten what it draws — paddings, minimum heights — but
most of this interface's air lives in layout margins and spacings set in
Python, which a style sheet never reaches. "Compact" used to change three of
those, so it looked the same as "Comfortable". This pass tightens every
layout of a window by one factor and puts each value back exactly when
Comfortable returns.

Pages reflow: a resize may set a layout's margins again from code. Each
layout therefore remembers both its comfortable value and the compact value
this pass wrote. A value that no longer matches what was written was set by
the page since, so it becomes the new comfortable value instead of being
"restored" over the page's own decision.

Comfortable is the default, and in Comfortable this pass only undoes what it
did before — a window that never went compact is never touched.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QFormLayout, QGridLayout, QLayout, QStackedLayout, QWidget

MARGIN_FACTOR = 0.62
SPACING_FACTOR = 0.62

_BASE = "bc250DensityBase"
_APPLIED = "bc250DensityApplied"
#: A widget whose own layout and every layout below it keep their geometry —
#: for surfaces that are already measured to the pixel (the first-run panel,
#: tour bubbles, the gamepad's on-screen keypad).
LOCK_PROPERTY = "densityLocked"
#: A layout whose owner already sets compact values itself (the window's root
#: margins, for one), so this pass must not tighten it a second time.
MANAGED_PROPERTY = "densityManaged"


def is_compact() -> bool:
    from ..theme import ACTIVE_DENSITY

    return ACTIVE_DENSITY == "compact"


def _read(layout: QLayout) -> tuple[int, int, int, int, int, int]:
    margins = layout.contentsMargins()
    if isinstance(layout, (QGridLayout, QFormLayout)):
        horizontal, vertical = layout.horizontalSpacing(), layout.verticalSpacing()
    elif isinstance(layout, QStackedLayout):
        horizontal = vertical = -1
    else:
        horizontal = vertical = layout.spacing()
    return (margins.left(), margins.top(), margins.right(), margins.bottom(), horizontal, vertical)


def _write(layout: QLayout, values: tuple[int, int, int, int, int, int]) -> None:
    left, top, right, bottom, horizontal, vertical = values
    layout.setContentsMargins(left, top, right, bottom)
    if isinstance(layout, (QGridLayout, QFormLayout)):
        if horizontal >= 0:
            layout.setHorizontalSpacing(horizontal)
        if vertical >= 0:
            layout.setVerticalSpacing(vertical)
    elif not isinstance(layout, QStackedLayout) and horizontal >= 0:
        layout.setSpacing(horizontal)


def _shrink(value: int, factor: float) -> int:
    # Negative spacing means "use the style's default": leave it to the style.
    if value <= 0:
        return value
    return max(1, round(value * factor))


def compact_values(values: tuple[int, int, int, int, int, int]) -> tuple[int, int, int, int, int, int]:
    left, top, right, bottom, horizontal, vertical = values
    return (
        _shrink(left, MARGIN_FACTOR),
        _shrink(top, MARGIN_FACTOR),
        _shrink(right, MARGIN_FACTOR),
        _shrink(bottom, MARGIN_FACTOR),
        _shrink(horizontal, SPACING_FACTOR),
        _shrink(vertical, SPACING_FACTOR),
    )


def _locked(layout: QLayout, locks: list[QWidget]) -> bool:
    owner = layout.parentWidget()
    if owner is None:
        return False
    return any(lock is owner or lock.isAncestorOf(owner) for lock in locks)


def apply_layout_density(root: QWidget | None, compact: bool | None = None) -> int:
    """Tighten (or restore) every layout under ``root``. Returns how many changed."""
    if root is None:
        return 0
    compact = is_compact() if compact is None else bool(compact)
    locks = [widget for widget in root.findChildren(QWidget) if widget.property(LOCK_PROPERTY)]
    if root.property(LOCK_PROPERTY):
        return 0
    layouts = root.findChildren(QLayout)
    # QWidget.layout, not root.layout: several pages keep a layout in an
    # attribute named ``layout`` and so shadow the method on the instance.
    own = QWidget.layout(root)
    if own is not None and own not in layouts:
        layouts.append(own)
    changed = 0
    for layout in layouts:
        if layout.property(MANAGED_PROPERTY):
            continue
        if locks and _locked(layout, locks):
            continue
        current = _read(layout)
        applied = layout.property(_APPLIED)
        applied = tuple(applied) if applied is not None else None
        if compact:
            if applied is not None and current == applied:
                continue  # Already compact, and nothing moved it since.
            # First pass, or the page set this value itself since: either way
            # it is the comfortable value from here on.
            target = compact_values(current)
            layout.setProperty(_BASE, current)
            layout.setProperty(_APPLIED, target)
            if target != current:
                _write(layout, target)
                changed += 1
        else:
            if applied is None:
                continue
            base = layout.property(_BASE)
            layout.setProperty(_BASE, None)
            layout.setProperty(_APPLIED, None)
            if current == applied and base is not None:
                _write(layout, tuple(base))
                changed += 1
    return changed
