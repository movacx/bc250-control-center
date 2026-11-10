"""A Kbuild exit 2 must not be called a protected-helper version mismatch.

A bare GLIBC mismatch is RUNTIME-001 on every distribution; BUILD-001 keeps
its SteamOS meaning only through the runtime preflight's own marker.
"""
import shlex
import subprocess

from bc250cc.infrastructure.terminal_plan import workflow_wrapper
from bc250cc.shared.error_catalog import for_marker


def test_reported_glibc_error_is_explained_even_with_make_exit_two(tmp_path):
    detail = ('ImportError: /usr/lib/libm.so.6: version `GLIBC_2.44\' not found '
              '(required by deps/usr/lib/python3.14/lib-dynload/math.cpython-314-x86_64-linux-gnu.so)\n'
              'make: *** [Makefile:248: __sub-make] Error 2\n')
    command = 'printf %s ' + shlex.quote(detail) + '; exit 2'
    result = subprocess.run(['bash', '-c', workflow_wrapper(command, tmp_path / 'status', tmp_path / 'log', hold=False)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 2
    assert 'BC250-RUNTIME-001' in result.stdout
    assert 'BC250-PROTOCOL-001' not in result.stdout
    assert 'BC250-BUILD-001' not in result.stdout
    assert for_marker(detail.splitlines()[0]).code == 'BC250-RUNTIME-001'


def test_the_steamos_preflight_marker_keeps_build_001_over_the_bare_glibc_line(tmp_path):
    detail = ("[ERROR] STEAMOS_BUILD_RUNTIME_INCOMPATIBLE: the downloaded toolchain needs GLIBC_2.44, "
              "this SteamOS has 2.41 (version `GLIBC_2.44' not found)")
    command = 'printf %s ' + shlex.quote(detail) + '; exit 2'
    result = subprocess.run(['bash', '-c', workflow_wrapper(command, tmp_path / 'status', tmp_path / 'log', hold=False)],
                            capture_output=True, text=True, timeout=30)
    assert 'BC250-BUILD-001' in result.stdout
    assert 'BC250-RUNTIME-001' not in result.stdout


def test_unrelated_compiler_error_is_not_a_runtime_or_protocol_mismatch(tmp_path):
    command = "echo '[ERROR] STEAMOS_AMDGPU_BUILD_FAILED: compiler error; module was not installed.'; exit 2"
    result = subprocess.run(['bash', '-c', workflow_wrapper(command, tmp_path / 'status', tmp_path / 'log', hold=False)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 2
    assert 'BC250-BUILD-002' in result.stdout
    assert 'BC250-PROTOCOL-001' not in result.stdout
