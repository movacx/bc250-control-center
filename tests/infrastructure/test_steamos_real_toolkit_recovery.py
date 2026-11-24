"""Generated recovery must stop before root writes or reboot when rejected."""
import shlex
import subprocess

import pytest

from bc250cc.infrastructure.steamos_real_toolkit_recovery import (
    CTL_HANDOFF,
    CTL_PRELUDE,
    REVERT_ALL_STEPS,
    adapt_recovery_ctl,
    adapt_revert_all,
)


def _helper(tmp_path, checker_status, child_status, root_state='disabled'):
    checker = tmp_path / 'checker.sh'
    checker.write_text('exit ' + str(checker_status) + '\n')
    child = tmp_path / 'toolkit.sh'
    child.write_text('exit ' + str(child_status) + '\n')
    helper = tmp_path / 'recovery.sh'
    # All side effects are marker functions; no root, systemctl, reboot or
    # real toolkit component can be invoked by this fixture.
    source = ('#!/bin/bash\nset -u\n'
              'unlock() { echo UNLOCK; }; stat() { echo 0; };\n'
              'steamos-readonly() { echo ' + shlex.quote(root_state) + '; return '
              + ('1' if root_state == 'disabled' else '0') + '; };\n'
              'cmd_revert() {\n' + CTL_PRELUDE
              + '    toolkit=' + shlex.quote(str(child)) + '\n'
              + CTL_HANDOFF + '    echo CLEANUP_AND_REBOOT\n}\ncmd_revert\n')
    helper.write_text(adapt_recovery_ctl(source, ('/usr/bin/bash', str(checker))))
    return subprocess.run(['bash', str(helper)], capture_output=True, text=True)


def test_native_conflict_stops_before_unlock(tmp_path):
    result = _helper(tmp_path, 79, 0)
    assert result.returncode == 79
    assert 'UNLOCK' not in result.stdout
    assert 'CLEANUP_AND_REBOOT' not in result.stdout


def test_failed_toolkit_revert_stops_before_success_cleanup_and_reboot(tmp_path):
    result = _helper(tmp_path, 0, 23)
    assert result.returncode == 23
    assert 'UNLOCK' in result.stdout
    assert 'CLEANUP_AND_REBOOT' not in result.stdout
    assert 'cleanup and reboot were stopped' in result.stderr


def test_successful_revert_keeps_the_remaining_upstream_recovery_flow(tmp_path):
    result = _helper(tmp_path, 0, 0)
    assert result.returncode == 0
    assert 'CLEANUP_AND_REBOOT' in result.stdout


def test_changed_recovery_template_cannot_be_silently_used():
    with pytest.raises(ValueError, match='contract changed'):
        adapt_recovery_ctl('different helper', ('/usr/bin/true',))


def test_failed_root_unlock_cannot_continue_into_recovery_cleanup(tmp_path):
    result = _helper(tmp_path, 0, 0, root_state='enabled')
    assert result.returncode == 1
    assert 'CLEANUP_AND_REBOOT' not in result.stdout
    assert 'Root is not confirmed writable' in result.stderr


@pytest.mark.parametrize('failed_step', REVERT_ALL_STEPS)
def test_bulk_revert_stops_at_each_component_failure_even_in_a_conditional(failed_step):
    names = [step.split()[0] for step in REVERT_ALL_STEPS]
    shell = 'set -euo pipefail\n'
    for step, name in zip(REVERT_ALL_STEPS, names):
        shell += name + '() { echo ' + name + '; return ' + ('23' if step == failed_step else '0') + '; }\n'
    shell += ('run_revert_all() {\n'
              + ''.join('    ' + step + '\n' for step in REVERT_ALL_STEPS)
              + '    echo PURGE_RECOVERY_STATE\n}\n'
              + 'result=0; run_revert_all || result=$?; exit "$result"\n')
    result = subprocess.run(['bash', '-c', adapt_revert_all(shell)], capture_output=True, text=True)
    assert result.returncode == 23, result.stderr
    assert result.stdout.splitlines() == names[:REVERT_ALL_STEPS.index(failed_step) + 1]


def test_successful_bulk_revert_preserves_order_and_final_cleanup():
    names = [step.split()[0] for step in REVERT_ALL_STEPS]
    shell = ''.join(name + '() { echo ' + name + '; };\n' for name in names)
    shell += ('run_revert_all() {\n'
              + ''.join('    ' + step + '\n' for step in REVERT_ALL_STEPS)
              + '    echo PURGE_RECOVERY_STATE\n}\nrun_revert_all\n')
    result = subprocess.run(['bash', '-c', adapt_revert_all(shell)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == names + ['PURGE_RECOVERY_STATE']


def test_changed_bulk_revert_contract_cannot_skip_error_propagation():
    with pytest.raises(ValueError, match='bulk revert'):
        adapt_revert_all('run_revert_all() {\n    unknown_new_component\n}\n')


def test_recovery_checks_target_file_and_all_parents(tmp_path):
    import os

    from bc250cc.infrastructure.steamos_real_toolkit_recovery import (
        RECOVERY_UNIT,
        unsafe_recovery,
    )

    target = tmp_path / 'home/deck/.bc250-toolkit/bc250-recovery-ctl.sh'
    target.parent.mkdir(parents=True)
    target.write_text('fixture')
    unit = tmp_path / 'etc/systemd/system' / RECOVERY_UNIT
    unit.parent.mkdir(parents=True)
    unit.write_text('[Service]\nExecStart=/home/deck/.bc250-toolkit/bc250-recovery-ctl.sh revert\n')
    assert unsafe_recovery(tmp_path, trusted_uid=os.getuid()) == ()
    target.parent.chmod(0o775)
    assert unsafe_recovery(tmp_path, trusted_uid=os.getuid()) == (str(target),)
    target.parent.chmod(0o755)
    target.chmod(0o666)
    assert unsafe_recovery(tmp_path, trusted_uid=os.getuid()) == (str(target),)


def test_recovery_refuses_before_the_upstream_install_body():
    from bc250cc.infrastructure.steamos_real_toolkit_recovery import (
        RECOVERY_REFUSAL,
        refuse_unsafe_install,
    )

    source = 'install_recovery_entries() { echo WROTE_BOOT_ENTRY; }\ninstall_recovery_entries\n'
    result = subprocess.run(['bash', '-s'], input=refuse_unsafe_install(source),
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 1
    assert not result.stdout
    assert RECOVERY_REFUSAL in result.stderr


def test_recovery_catches_writable_intermediate_symlink_directory(tmp_path):
    import os

    from bc250cc.infrastructure import steamos_real_toolkit_recovery as recovery

    real = tmp_path / 'protected'
    real.mkdir()
    (real / 'helper').write_text('fixture')
    unsafe = tmp_path / 'writable'
    unsafe.mkdir(mode=0o777)
    unsafe.chmod(0o777)
    (unsafe / 'proxy').symlink_to(real / 'helper')
    grub = tmp_path / recovery.RECOVERY_GRUB
    grub.parent.mkdir(parents=True)
    grub.symlink_to(unsafe / 'proxy')
    assert recovery.unsafe_recovery(tmp_path, trusted_uid=os.getuid()) == (str(grub),)


def test_boot_path_can_be_created_only_under_trusted_directories(tmp_path):
    import os

    from bc250cc.infrastructure import steamos_real_toolkit_recovery as recovery

    var = tmp_path / 'var'
    data = tmp_path / 'data'
    data.mkdir()
    var.symlink_to(data)
    paths = ('var/helper',)
    assert not recovery.unsafe_boot_paths(tmp_path, paths, trusted_uid=os.getuid())
    data.chmod(0o777)
    assert recovery.unsafe_boot_paths(tmp_path, paths, trusted_uid=os.getuid())


def test_existing_boot_service_cannot_switch_to_an_untrusted_target(tmp_path):
    import os

    from bc250cc.infrastructure import steamos_real_toolkit_recovery as recovery

    unit = tmp_path / 'etc/systemd/system/fixture.service'
    unit.parent.mkdir(parents=True)
    unit.write_text('[Service]\nExecStart=/usr/bin/true\nExecStop=/home/player/handoff\n')
    paths = ('etc/systemd/system/fixture.service', 'usr/bin/true')
    assert recovery.unsafe_boot_paths(tmp_path, paths, trusted_uid=os.getuid())
    unit.write_text('[Service]\nExecStart=/usr/bin/true\n')
    assert not recovery.unsafe_boot_paths(tmp_path, paths, trusted_uid=os.getuid())
