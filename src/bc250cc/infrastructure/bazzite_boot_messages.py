"""Explicit, reversible Bazzite lifecycle for ``loglevel=0``.

The BC-250's CPU makes the kernel print a warning about its random-number
instructions (RDSEED) at every boot. It is a level 0 message, so ``loglevel=0``
is the only level that hides it, and it hides every other kernel message on
screen too. Nothing is fixed: the messages stay in ``dmesg``.

The transaction itself is shared with the other Bazzite kernel arguments, see
``bazzite_kargs``: the ``loglevel=`` arguments the image had are saved first
and put back exactly on restore.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from bc250cc.infrastructure.bazzite_kargs import KargSpec, build_karg_command, probe_karg

BOOT_MESSAGES_ARGUMENT = "loglevel=0"
BOOT_MESSAGES_STATE_FILE = Path(
    "/etc/bc250-control-center/loglevel-kargs.original"
)
SPEC = KargSpec(
    argument=BOOT_MESSAGES_ARGUMENT,
    family="^loglevel=",
    valid="^loglevel=[0-9]+$",
    state_file=BOOT_MESSAGES_STATE_FILE,
    title="BC250 Bazzite boot messages",
    noun="boot-messages",
    previous="previous boot-messages level",
    enable_action="hide",
    enabled_label="hidden",
    disabled_label="shown",
    done_message="the kernel boot messages will be hidden after reboot.",
    restored_message="the previous kernel boot-messages level will return after reboot.",
)


def probe_bazzite_boot_messages(
    *,
    proc_cmdline: Path = Path("/proc/cmdline"),
    state_file: Path = BOOT_MESSAGES_STATE_FILE,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, object]:
    return probe_karg(SPEC, proc_cmdline=proc_cmdline, state_file=state_file, runner=runner)


def build_bazzite_boot_messages_command(action: str) -> str:
    return build_karg_command(SPEC, action)
