"""A Cyan that would not start is a GPU fault, not a Compute Units one.

Cyan's start steps exit 62, a status the catalog gives to Compute Units, so a
governor stopped by a leftover sensor mount was reported as "UMR or the GPU
database do not match" (BC250-CU-001). The text the step prints decides now.
"""

from __future__ import annotations

import os
import subprocess

import pytest

from bc250cc.infrastructure.terminal_plan import exit_explanation_shell


def _diagnose(tail: str, status: int = 62) -> str:
    script = f'status={status}; evidence="$EVIDENCE"; {exit_explanation_shell()}\necho "CODE=$diagnostic"'
    result = subprocess.run(
        ["bash", "-c", script], env={**os.environ, "EVIDENCE": tail},
        capture_output=True, text=True, check=False,
    )
    return result.stdout.strip().splitlines()[-1].removeprefix("CODE=")


@pytest.mark.parametrize(
    ("tail", "code"),
    [
        ("ERROR: Cyan is running but its D-Bus name is unavailable after policy repair", "BC250-DBUS-001"),
        ("ERROR: Cyan D-Bus policy is missing; run Prepare dependencies", "BC250-DBUS-001"),
        (
            "Error: mount --bind /dev/shm/patched_gpu_metrics /sys/bus/pci/devices/0000:01:00.0/gpu_metrics "
            "failed: exit status: 32\nERROR: Cyan is running but its D-Bus name is unavailable after policy repair",
            "BC250-GPU-005",
        ),
        ("mount: /sys/.../gpu_metrics: move_mount() ha fallado: No existe el fichero", "BC250-GPU-005"),
    ],
)
def test_cyan_start_failures_get_a_gpu_code(tail, code):
    assert _diagnose(tail) == code


def test_a_compute_units_failure_keeps_its_code():
    assert _diagnose("QUICK_ACCESS_CU_VERIFY: live WGP map does not match") == "BC250-CU-001"


def test_the_kernel_usage_method_on_a_stock_kernel_is_named_before_start():
    """A stock kernel answers gpu_busy_percent with EOPNOTSUPP; Cyan then died
    with a bare "Io(Os { code: 95 })". The startup guard says it first."""
    from bc250cc.infrastructure.gpu_repository import GPURepository

    guard = GPURepository._cyan_metrics_overlay_preflight_command(object.__new__(GPURepository))
    assert 'method[[:space:]]*=[[:space:]]*\\"kernel\\"' in guard
    assert "gpu_busy_percent" in guard and "Nothing was changed" in guard
    message = guard.split('echo "ERROR: Cyan reads GPU usage', 1)[1].split('"', 1)[0]
    assert _diagnose("ERROR: Cyan reads GPU usage" + message) == "BC250-GPU-001"
