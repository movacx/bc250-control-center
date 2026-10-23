"""Immutable trust anchors for the reverse-engineered GDDR6 SMU tool.

Mirrors core_unlock_trust.py: the reviewed revision comes from the shared
external-tool manifest. ``patch_smu.py`` is the one script this project
executes verbatim (from a private root-owned copy, exactly like core-unlock),
so it additionally carries an independently reviewed SHA-256 as defense in
depth against local tampering after checkout; the helpers pin every other
file they copy the same way. Reading temperatures does not exec read_temp.py
at all -- it is an endless terminal monitor, not something a root-owned
helper should run -- so the helper instead imports the reviewed
``bc250_smu.Bc250Smu`` class directly and calls the same
``send_message(3, 0x6, [parity])`` primitive read_temp.py does.
"""
from __future__ import annotations

from .external_tools.catalog import EXTERNAL_TOOLS

REVIEWED_REVISION = EXTERNAL_TOOLS["gddr6_memory_temp"].reviewed_revision
REVIEWED_PATCH_SCRIPT_SHA256 = "04e69ef1e4c1ec3051d97ed8c3cb68eb31b43c2be3cdb921f1d3957f99aa32ed"
