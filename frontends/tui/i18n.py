"""Translations for the terminal interface: the desktop application's catalogs.

``tr`` is the desktop's own ``tr`` (the same 30 locale files), so a string
translated once reads the same in both frontends. Importing it pulls in no Qt.
"""

from __future__ import annotations

from frontends.desktop.i18n import (
    current_language,
    resolve_language,
    set_language,
    tr,
    tr_format,
)

__all__ = ["current_language", "resolve_language", "set_language", "tr", "tr_format"]
