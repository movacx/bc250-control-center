"""Control Center's passive kernel evidence, independent of installer ownership."""
from __future__ import annotations

import shlex
from pathlib import Path


def graphics_diagnostic_command(root: Path = Path('/')) -> str:
    """Read live evidence without running an external toolkit or requesting root.

    An installed module and a loaded module are different observations. Neither
    proves that a patched module was reviewed or that a Vulkan process uses it.
    The root argument allows an isolated filesystem fixture in tests.
    """
    cmdline = shlex.quote(str(root / 'proc/cmdline'))
    module = shlex.quote(str(root / 'sys/module/amdgpu'))
    return '; '.join([
        'echo "== Native AMDGPU evidence =="',
        f'if [ -r {cmdline} ]; then '
        f'printf "Kernel command line: "; cat {cmdline}; '
        'else echo "[UNKNOWN] Kernel command line is unavailable."; fi',
        f'if [ -d {module} ]; then echo "AMDGPU: loaded"; '
        'else echo "AMDGPU: not observed loaded"; fi',
        f'for field in version srcversion taint parameters/sched_policy; do '
        f'if [ -r {module}/"$field" ]; then '
        f'printf "AMDGPU %s: " "$field"; cat {module}/"$field"; fi; done',
        'echo "Module attestation: not established by these observations."',
        'echo "Vulkan runtime activation: not established by kernel evidence."',
    ])
