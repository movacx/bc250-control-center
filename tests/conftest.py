"""Deterministic Qt setup for the automated desktop test suite."""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile

# UI tests must not compete with the developer's active Wayland/X11 window for
# keyboard focus. Callers can still choose another Qt backend explicitly.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Nor may they read or write the real ~/.config/bc250-control-center/ui.conf.
# Pages restore the user's saved profiles from it at construction, so a
# developer who had renamed a GPU profile saw two unrelated GPU tests fail on
# their machine and pass everywhere else — and a test that saves a profile was
# writing into their live configuration. One throwaway directory per run fixes
# both directions. Set before any Qt or application import so nothing has
# resolved the path yet.
_ISOLATED_CONFIG = tempfile.mkdtemp(prefix="bc250-tests-config-")
os.environ["XDG_CONFIG_HOME"] = _ISOLATED_CONFIG
atexit.register(shutil.rmtree, _ISOLATED_CONFIG, ignore_errors=True)
