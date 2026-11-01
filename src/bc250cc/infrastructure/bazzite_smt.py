"""Explicit, reversible Bazzite lifecycle for ``nosmt``.

``nosmt`` leaves one thread per core (6 or 8 threads instead of 12 or 16). On
Bazzite it is a kernel argument like ``mitigations=off``, so it goes through
``rpm-ostree kargs`` and applies at the next boot; the other distributions
manage it from the protected helper's kernel-options block. The transaction is
shared with the other Bazzite kernel arguments, see ``bazzite_kargs``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from bc250cc.infrastructure.bazzite_kargs import KargSpec, build_karg_command, probe_karg

SMT_ARGUMENT = "nosmt"
SMT_STATE_FILE = Path("/etc/bc250-control-center/nosmt-kargs.original")
SPEC = KargSpec(
    argument=SMT_ARGUMENT,
    # nosmt=force and nosmt=off are other forms of the same switch.
    family="^nosmt(=[A-Za-z]+)?$",
    valid="^nosmt(=[A-Za-z]+)?$",
    state_file=SMT_STATE_FILE,
    title="BC250 Bazzite simultaneous multithreading",
    noun="smt",
    previous="previous SMT setting",
    enable_action="disable",
    enabled_label="disabled",
    disabled_label="enabled",
    done_message="simultaneous multithreading will be disabled after reboot.",
    restored_message="the previous SMT setting will return after reboot.",
)


def probe_bazzite_smt(
    *,
    proc_cmdline: Path = Path("/proc/cmdline"),
    state_file: Path = SMT_STATE_FILE,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, object]:
    return probe_karg(SPEC, proc_cmdline=proc_cmdline, state_file=state_file, runner=runner)


def build_bazzite_smt_command(action: str) -> str:
    return build_karg_command(SPEC, action)
