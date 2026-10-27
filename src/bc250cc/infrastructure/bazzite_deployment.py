"""Whether Prepare dependencies left Bazzite waiting for a reboot.

On Bazzite the host packages are layered with ``rpm-ostree install``: they
land in a new deployment that only becomes the running system after a
reboot, and the parts that build on them (fan PWM, verification) are left
for a second preparation after that reboot.

Read-only. The answer is yes only when the deployment waiting for the next
boot requests one of the packages Prepare dependencies layers and the running
deployment does not: an automatic Bazzite update staged in the background
carries the same layered packages over, so it never reads as pending setup.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Callable

# The packages packaging/common/os-scripts/bazzite/prepare-dependencies.sh
# layers. Kept in step with that script.
PREPARED_PACKAGES = frozenset({
    "python3", "python3-pyqt6", "qt6-qtsvg", "python3-psutil", "git",
    "pciutils", "libdrm", "vulkan-tools", "polkit", "kmod", "make", "gcc",
    "elfutils-libelf-devel", "kernel-devel", "dkms", "jq", "lm_sensors",
    "stress", "umr", "cyan-skillfish-governor-smu",
})


def _requested(deployment: dict) -> set[str]:
    names = set(deployment.get("requested-packages") or [])
    names.update(deployment.get("packages") or [])
    return {str(name) for name in names}


def pending_prepared_packages(status: object) -> tuple[str, ...]:
    """The prepared packages ``rpm-ostree status --json`` has queued for next boot."""
    if not isinstance(status, dict):
        return ()
    deployments = [item for item in status.get("deployments") or [] if isinstance(item, dict)]
    booted_index = next(
        (index for index, item in enumerate(deployments) if item.get("booted")), None
    )
    if booted_index is None:
        return ()
    booted = _requested(deployments[booted_index])
    # rpm-ostree lists the deployment for the next boot first; the ones after
    # the booted deployment are rollbacks.
    for deployment in deployments[:booted_index]:
        queued = (_requested(deployment) - booted) & PREPARED_PACKAGES
        if queued:
            return tuple(sorted(queued))
    return ()


def probe_bazzite_reboot_pending(
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, object]:
    """Ask rpm-ostree, without changing anything, what waits for the next boot."""
    try:
        result = runner(
            ("rpm-ostree", "status", "--json"),
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
            env={**os.environ, "LANG": "C", "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError):
        return {"available": False, "pending": False, "packages": []}
    if result.returncode != 0:
        return {"available": False, "pending": False, "packages": []}
    try:
        status = json.loads(result.stdout or "")
    except ValueError:
        return {"available": False, "pending": False, "packages": []}
    packages = pending_prepared_packages(status)
    return {"available": True, "pending": bool(packages), "packages": list(packages)}


#: Runs before a workflow on an rpm-ostree system. Bazzite's automatic update
#: (or another workflow's ``rpm-ostree kargs``) holds rpm-ostree for minutes,
#: and every install or kargs call then failed at once with "Transaction in
#: progress": three reports in one week. Waiting is what the user would do.
RPM_OSTREE_IDLE_WAIT = (
    "if command -v rpm-ostree >/dev/null 2>&1; then "
    "bc250_ostree_waited=0; "
    "while rpm-ostree status --json 2>/dev/null | python3 -c "
    "'import json,sys; sys.exit(0 if json.load(sys.stdin).get(\"transaction\") else 1)' 2>/dev/null; do "
    'if [ "$bc250_ostree_waited" -eq 0 ]; then '
    'echo "Another rpm-ostree transaction (usually an automatic system update) is running; waiting for it to finish..."; fi; '
    "bc250_ostree_waited=$((bc250_ostree_waited + 1)); "
    'if [ "$bc250_ostree_waited" -ge 180 ]; then '
    'echo "[ERROR] rpm-ostree stayed busy for 15 minutes. Try again once the system update has finished."; exit 75; fi; '
    "sleep 5; done; fi"
)
