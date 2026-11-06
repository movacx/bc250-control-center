"""Thin SteamOS adapter for keyboardspecialist's unmodified GE-Proton installer.

Only the userspace Proton checkout follows upstream master. The kernel/RADV
backend keeps its independently reviewed revision and privileged boundaries.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from .external_tools.catalog import EXTERNAL_TOOLS
from .source_checkout import clone_or_update_branch
from .steamos_amdgpu_backend import STEAMOS_GRAPHICS_BACKEND

STEAMOS_PROTON_DIRECTORY = "bc250-steamos-proton"
STEAMOS_PROTON_ACTIONS = frozenset({"install", "update", "status", "uninstall"})


def build_steamos_proton_command(
    action: str,
    destination: Path,
    *,
    backend_guard: str,
    mesh_script: Path = STEAMOS_GRAPHICS_BACKEND,
) -> str:
    if action not in STEAMOS_PROTON_ACTIONS:
        raise ValueError(f"Unsupported SteamOS Proton action: {action}")
    if not backend_guard.strip():
        raise ValueError("The Proton installer requires a protected RADV backend guard.")
    spec = EXTERNAL_TOOLS["steamos_proton"]
    script = destination / "bc250-proton.sh"
    qscript = shlex.quote(str(script))
    steps = [
        "set -Eeuo pipefail",
        "export LC_ALL=C LANG=C",
        'test "$(id -u)" -ne 0 || { echo "ERROR: Run Proton management as the desktop user, not root."; exit 64; }',
        '. /etc/os-release; case "${ID:-}" in steamos|holo) ;; *) echo "ERROR: This Proton workflow is available only on SteamOS."; exit 64;; esac',
        'echo "== SteamOS BC-250 GE-Proton · keyboardspecialist upstream =="',
    ]
    if action == "status":
        steps.append(
            f'if [ ! -f {qscript} ]; then '
            'echo "[INFO] Proton management is not prepared yet. Use Install / update to prepare the upstream installer and verify any existing tool."; exit 0; fi'
        )
    else:
        steps.append(clone_or_update_branch(spec.upstream, destination, "master"))
    steps.append(f'test -f {qscript} && test ! -L {qscript}')
    if action in {"install", "update"}:
        steps.append(
            f'{backend_guard} || {{ echo "ERROR: STEAMOS_PROTON_FAILED: Prepare the SteamOS kernel and Mesa/RADV backend first."; exit 38; }}'
        )
    # Upstream explicitly supports BC250_MESH_TOOL. Point it at the existing
    # protected runtime manager; never update or install Mesa as a side effect.
    steps.append(f"export BC250_MESH_TOOL={shlex.quote(str(mesh_script))}")
    invocation = f"/usr/bin/bash {qscript} {action}"
    if action == "status":
        # Upstream status uses 1 for absent and 2 for an incomplete tool.
        # Those are inspection results, not helper protocol errors.
        steps.append(
            f'if {invocation}; then :; else bc250_proton_rc=$?; '
            'case "$bc250_proton_rc" in 1|2) echo "[INFO] Use Install / update to install or repair the compatibility tool.";; '
            '*) echo "ERROR: STEAMOS_PROTON_FAILED: Upstream Proton inspection failed."; exit "$bc250_proton_rc";; esac; fi'
        )
    else:
        steps.append(
            f'if {invocation}; then :; else bc250_proton_rc=$?; '
            'echo "ERROR: STEAMOS_PROTON_FAILED: The upstream Proton action did not complete. Read its explanation above."; '
            'exit "$bc250_proton_rc"; fi'
        )
    return "; ".join(steps)
