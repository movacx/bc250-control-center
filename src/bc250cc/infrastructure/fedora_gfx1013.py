"""Pinned Fedora 43 workflow for DryhoppedIPA's complete GFX1013 stack.

The reviewed upstream installer intentionally treats its kernel and Mesa/RADV
patches as one compatibility unit.  This adapter does not fork that lifecycle:
it verifies the exact upstream-tested host, checks out the reviewed revision,
and runs the upstream dependency/build/install stages in order.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from .gfx1013_compute_policy import (
    GFX1013_REVIEWED_COMMIT,
    GFX1013_TESTED_KERNEL,
    GFX1013_UPSTREAM,
)
from .source_checkout import clone_or_update_commit

_ACTIONS = frozenset({"install", "status", "uninstall"})


def build_fedora_gfx1013_command(action: str, destination: str | Path) -> str:
    """Build a closed command for the reviewed non-Atomic Fedora workflow."""

    action = str(action or "").strip().lower()
    if action not in _ACTIONS:
        raise ValueError(f"Unsupported Fedora GFX1013 action: {action or '--'}")
    destination = Path(destination)
    checkout = clone_or_update_commit(
        GFX1013_UPSTREAM, destination, GFX1013_REVIEWED_COMMIT
    )
    qdest = shlex.quote(str(destination))
    fedora_gate = '''test -r /etc/os-release || { echo "ERROR: /etc/os-release is unavailable."; exit 64; }
. /etc/os-release
test "${ID:-}" = fedora || { echo "ERROR: This reviewed direct workflow supports Fedora only."; exit 64; }
command -v rpm-ostree >/dev/null 2>&1 && { echo "ERROR: Fedora Atomic/Bazzite is not supported by this direct installer."; exit 64; }'''
    install_gate = f'''test "${{VERSION_ID:-}}" = 43 || {{ echo "ERROR: This reviewed direct workflow supports Fedora 43 only."; exit 64; }}
test "$(uname -r)" = {shlex.quote(GFX1013_TESTED_KERNEL)} || {{ echo "ERROR: The running kernel is outside the exact upstream-validated host ({GFX1013_TESTED_KERNEL})."; exit 64; }}
bc250_found=0
for device in /sys/bus/pci/devices/*; do
  test -r "$device/vendor" && test -r "$device/device" || continue
  test "$(cat "$device/vendor")" = 0x1002 && test "$(cat "$device/device")" = 0x13fe && bc250_found=1 && break
done
test "$bc250_found" = 1 || {{ echo "ERROR: AMD BC-250 PCI device 1002:13fe was not found."; exit 64; }}'''
    source_gate = f'''{checkout}
test -x {qdest}/install.sh || {{ echo "ERROR: reviewed install.sh is missing."; exit 29; }}
test -f {qdest}/LICENSE -a -f {qdest}/LICENSES.md || {{ echo "ERROR: upstream component licenses are missing."; exit 29; }}
test "$(sed -n '/^[^#[:space:]]/p' {qdest}/patches/mesa/series)" = 0001-gfx1013-compute-queue-fix.patch || {{ echo "ERROR: reviewed safe Mesa patch series changed; mesh/task remains blocked."; exit 29; }}'''

    commands = [
        "set -Eeuo pipefail",
        "export LC_ALL=C LANG=C",
        fedora_gate,
    ]
    if action == "install":
        commands.append(install_gate)
    commands.append(source_gate)
    if action == "install":
        commands.extend((
            'echo "== GFX1013 complete kernel + Mesa/RADV stack =="',
            'echo "[INFO] Kernel-only and Mesa-only installation are intentionally not offered: upstream requires both halves together."',
            'echo "[INFO] Mesh/task patches 0002 and 0003 remain disabled because upstream reports unrecoverable GPU hangs."',
            f"sudo {qdest}/install.sh deps",
            f"{qdest}/install.sh build",
            f"sudo {qdest}/install.sh install",
            'echo "BC250_REBOOT_REQUIRED=1"',
            'echo "OK: the patched entry is selected for the next boot only; the stock Fedora entry remains the default."',
        ))
    elif action == "uninstall":
        commands.extend((
            f"sudo {qdest}/install.sh uninstall",
            'echo "OK: upstream GFX1013 files and patched boot entry were removed."',
        ))
    else:
        commands.append(f"{qdest}/install.sh status")
    return "\n".join(commands)
