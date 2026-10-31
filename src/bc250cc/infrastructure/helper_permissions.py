"""Bounded, authenticated recovery before an application terminal workflow."""

from __future__ import annotations

import shlex
from pathlib import Path


def recovery_preflight() -> str:
    """Use the installer's same policy, including when a system copy is older.

    The application already generates the privileged commands the user approves.
    Embed this finite repair rather than execute/import a helper through the
    very path whose permissions prevent trusting it. Healthy systems never ask
    for authorization here. Existing helper validation still runs afterwards.
    """
    maintenance = Path(__file__).resolve().parents[3] / "packaging/common/bc250-package-maintenance"
    prefix, separator, _ = maintenance.read_text(encoding="utf-8").partition('\ncase "${1:-}" in')
    if (not separator or "\nBC250_PERMISSION_REPAIR_PROTOCOL=1\n" not in prefix
            or "repair_permissions() {" not in prefix or "\ncase " in prefix):
        raise RuntimeError("The installation permission repair is unavailable. Update Control Center.")
    return (
        "(\n" + prefix + "\n"
        "if repair_permissions check; then\n"
        "  echo '== BC250: repairing installation permissions =='\n"
        '  if [ "${EUID:-$(id -u)}" -eq 0 ]; then\n'
        "    repair_permissions\n"
        "  else\n"
        "    sudo /bin/bash -c " + shlex.quote(prefix + "\nrepair_permissions\n") + "\n"
        "  fi\n"
        "fi\n) || exit $?\n"
    )
