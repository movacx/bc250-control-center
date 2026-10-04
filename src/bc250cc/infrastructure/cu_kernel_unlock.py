"""Whether the BC-250 kernel driver owns the compute-unit routing.

linux-cachyos-bc250's amdgpu has ``bc250_cc_write_mode``; at ``3``
(clear-all-SAs) the driver clears every shader array's disable bits when it
loads, so all 40 CUs are driver-known from boot. umr and the live CU manager
then have nothing left to unlock, and a live write would change the routing
underneath a driver that already counts those CUs. Every CU write surface
(desktop page, Decky tab, boot service) treats this as read-only.
"""

from __future__ import annotations

from pathlib import Path

CU_WRITE_MODE_PARAMETER = Path("/sys/module/amdgpu/parameters/bc250_cc_write_mode")
#: clear-all-SAs. 1 and 4 only probe; 2 clears SE0.SH0 alone.
KERNEL_UNLOCK_MODE = "3"


def kernel_cu_unlock_active(parameter: Path | None = None) -> bool:
    try:
        return (parameter or CU_WRITE_MODE_PARAMETER).read_text(encoding="ascii", errors="strict").strip() == KERNEL_UNLOCK_MODE
    except (OSError, UnicodeError):
        return False
