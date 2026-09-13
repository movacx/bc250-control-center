"""Immutable trust anchors for the reverse-engineered GDDR6 SMU tool.

Mirrors core_unlock_trust.py: the reviewed revision comes from the shared
external-tool manifest. ``patch_smu.py`` is the one script this project
executes verbatim (via fd, exactly like core-unlock), so it additionally
carries an independently reviewed SHA-256 as defense in depth against local
tampering after checkout. Reading temperatures does not exec read_temp.py at
all -- read_temp.py's own dependency on the third-party ``tabulate`` package
is not something a root-owned helper should require system-wide, so the
helper instead imports the reviewed ``bc250_smu.Bc250Smu`` class directly and
calls the same ``send_message(3, 0x5, [chip])`` primitive read_temp.py does.
"""
from __future__ import annotations

from .external_tools.catalog import EXTERNAL_TOOLS

REVIEWED_REVISION = EXTERNAL_TOOLS["gddr6_memory_temp"].reviewed_revision
REVIEWED_PATCH_SCRIPT_SHA256 = "c6c0b17f3f2dad415f7814035a1918331068ab1827269a97254df0ddb554ca6e"
