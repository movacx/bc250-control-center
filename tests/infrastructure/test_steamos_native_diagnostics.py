"""Native diagnostics observe kernel files without executing installer code."""
import subprocess

from bc250cc.infrastructure.steamos_native_diagnostics import (
    graphics_diagnostic_command,
)


def test_reads_loaded_kernel_evidence_without_promoting_it_to_attestation(tmp_path):
    root = tmp_path / "root with spaces"
    module = root / 'sys/module/amdgpu'
    (module / 'parameters').mkdir(parents=True)
    (root / 'proc').mkdir()
    (root / 'proc/cmdline').write_text('quiet amdgpu.sched_policy=2\n')
    (module / 'srcversion').write_text('FIXTURE123\n')
    (module / 'parameters/sched_policy').write_text('2\n')
    command = graphics_diagnostic_command(root)
    result = subprocess.run(['bash', '-euc', command], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert 'AMDGPU: loaded' in result.stdout
    assert 'AMDGPU srcversion: FIXTURE123' in result.stdout
    assert 'AMDGPU parameters/sched_policy: 2' in result.stdout
    assert 'Module attestation: not established' in result.stdout
    assert 'Vulkan runtime activation: not established' in result.stdout
    assert 'sudo' not in command and 'start.sh' not in command


def test_missing_kernel_evidence_is_reported_without_aborting_diagnostics(tmp_path):
    result = subprocess.run(['bash', '-euc', graphics_diagnostic_command(tmp_path)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert '[UNKNOWN] Kernel command line is unavailable.' in result.stdout
    assert 'AMDGPU: not observed loaded' in result.stdout
    assert list(tmp_path.iterdir()) == []
