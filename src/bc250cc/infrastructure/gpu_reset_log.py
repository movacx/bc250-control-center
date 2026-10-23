"""Read this boot's GPU hang summary from the kernel log, without privileges if it can.

``journalctl -k`` is tried first (a desktop user in the ``systemd-journal``,
``adm`` or ``wheel`` group can read it), then ``dmesg``. When neither is
readable the answer is ``None``: not "no resets", which is a different fact.
"""

from __future__ import annotations

import shutil
import subprocess

from bc250cc.domain.gpu.reset_log import GpuResetSummary, summarize

QUERY_TIMEOUT_S = 4.0
#: A boot's amdgpu lines are a few hundred bytes; this only bounds a flooded log.
MAX_BYTES = 8 * 1024 * 1024
_COMMANDS = (
    ("journalctl", "-k", "-b", "0", "-o", "short-iso", "--no-pager", "-q"),
    ("dmesg", "--time-format", "iso"),
)


def _run(argv: tuple[str, ...]) -> str | None:
    if not shutil.which(argv[0]):
        return None
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, errors="replace",
            timeout=QUERY_TIMEOUT_S, check=False,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout[:MAX_BYTES] if result.returncode == 0 and result.stdout else None


def read_gpu_resets() -> GpuResetSummary | None:
    """This boot's GPU hangs, or ``None`` when the kernel log cannot be read."""
    for argv in _COMMANDS:
        text = _run(argv)
        if text is not None:
            return summarize(text.splitlines())
    return None
