"""First run: ask the four questions, then offer to show the way round.

The application had been answering all of this on the user's behalf — a
language guessed from the locale, a theme guessed from the desktop, a rail
width guessed from the window — and introducing none of it. This package is
the one time it asks instead, plus the guided tour that introduces the modules
afterwards.

Both are optional and both are re-runnable from Settings, so nothing here is a
gate: the flag below records that the offer was made, not that it was taken.
"""

from __future__ import annotations

from .glass import frosted, frosted_snapshot
from .script import tour_stops
from .tour import Spotlight, TourCallout, TourGuide, TourStop
from .welcome import WelcomeOverlay

#: Bumping this shows the first run again to people who have already seen an
#: older one. It is a deliberate act — the screen is welcome once and an
#: interruption every other time — so it moves only when the questions change.
ONBOARDING_VERSION = 1
SETTINGS_KEY = "onboarding/completed_version"


def completed_version(settings) -> int:
    try:
        return int(settings.value(SETTINGS_KEY, 0))
    except (TypeError, ValueError):
        return 0


def first_run_pending(settings) -> bool:
    """Whether the welcome screen still owes this user its questions."""
    return completed_version(settings) < ONBOARDING_VERSION


def mark_first_run_done(settings) -> None:
    settings.setValue(SETTINGS_KEY, ONBOARDING_VERSION)
    settings.sync()


__all__ = [
    "ONBOARDING_VERSION",
    "SETTINGS_KEY",
    "Spotlight",
    "TourCallout",
    "TourGuide",
    "TourStop",
    "WelcomeOverlay",
    "completed_version",
    "first_run_pending",
    "frosted",
    "frosted_snapshot",
    "mark_first_run_done",
    "tour_stops",
]
