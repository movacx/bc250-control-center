"""Deterministic Qt setup for the automated desktop test suite."""

from __future__ import annotations

import os

# UI tests must not compete with the developer's active Wayland/X11 window for
# keyboard focus. Callers can still choose another Qt backend explicitly.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
