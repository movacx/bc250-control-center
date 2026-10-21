"""The problem report, as the interface sees it.

The form itself (questions, the live check, the POST to Google Forms) is in
``bc250cc.infrastructure.feedback_form``; the desktop goes through here, like
every other use case, so it never imports infrastructure directly.
"""

from __future__ import annotations

from bc250cc.infrastructure import feedback_form as form
from bc250cc.infrastructure.system_snapshot import _os_release as os_release
from bc250cc.infrastructure.system_snapshot import system_snapshot

__all__ = ["form", "os_release", "system_snapshot"]
