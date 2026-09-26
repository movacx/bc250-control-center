import os
import subprocess
from pathlib import Path

from bc250cc.infrastructure.dependencias_repository import DependenciasRepository
from bc250cc.infrastructure.gpu_repository import GPURepository
from bc250cc.infrastructure.terminal_plan import workflow_wrapper
from bc250cc.infrastructure.terminal_repository import TerminalRepository


def test_cyan_installer_reloads_system_dbus_policy():
    source = Path(
        'packaging/common/os-scripts/common/install-cyan-upstream-release.sh'
    ).read_text(encoding='utf-8')

    marker = '<allow own="com.cyanskillfish.Governor"/>'
    assert marker in source
    assert 'org.freedesktop.DBus ReloadConfig' in source
    assert source.index(marker) < source.index('org.freedesktop.DBus ReloadConfig')


def test_cyan_activation_repairs_dbus_before_start_and_requires_bus_name(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "bc250cc.infrastructure.gpu_repository.detect_init_manager",
        lambda: type("Init", (), {"kind": "systemd", "persistence_supported": True, "display_name": "systemd"})(),
    )

    class Repository(GPURepository):
        def _selected_gpu_governor(self):
            return 'cyan-skillfish-governor-smu'

        def _command_path(self, _name):
            return '/usr/local/bin/cyan-skillfish-governor-smu'

        def _tool_dir(self):
            return tmp_path

        def _abrir_terminal(self, command, title):
            captured['command'] = command
            captured['title'] = title
            return command

    monkeypatch.setattr(
        'bc250cc.infrastructure.gpu_repository.ensure_no_incompatible_governors',
        lambda *_args, **_kwargs: [],
    )

    command = Repository().controlar_governor('activar')
    assert 'org.freedesktop.DBus ReloadConfig' in command
    assert '/usr/share/dbus-1/system.d/com.cyanskillfish.Governor.conf' in command
    assert 'sudo systemctl restart cyan-skillfish-governor-smu.service' in command
    assert 'busctl --system status com.cyanskillfish.Governor' in command
    assert 'Cyan service and D-Bus interface are active' in command
    assert command.index('org.freedesktop.DBus ReloadConfig') < command.index('systemctl enable --now')
    assert command.index('systemctl enable --now') < command.index('busctl --system status com.cyanskillfish.Governor')
    parsed = subprocess.run(
        ['bash', '-n', '-c', command], capture_output=True, text=True, check=False
    )
    assert parsed.returncode == 0, parsed.stderr


def test_cyan_restart_also_repairs_dbus_policy(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "bc250cc.infrastructure.gpu_repository.detect_init_manager",
        lambda: type("Init", (), {"kind": "systemd", "persistence_supported": True, "display_name": "systemd"})(),
    )

    class Repository(GPURepository):
        def _selected_gpu_governor(self):
            return 'cyan-skillfish-governor-smu'

        def _command_path(self, _name):
            return '/usr/local/bin/cyan-skillfish-governor-smu'

        def _tool_dir(self):
            return tmp_path

        def _abrir_terminal(self, command, _title):
            return command

    monkeypatch.setattr(
        'bc250cc.infrastructure.gpu_repository.ensure_no_incompatible_governors',
        lambda *_args, **_kwargs: [],
    )
    command = Repository().controlar_governor('reiniciar')
    assert command.index('org.freedesktop.DBus ReloadConfig') < command.index('systemctl restart')
    assert 'busctl --system status com.cyanskillfish.Governor' in command
    parsed = subprocess.run(
        ['bash', '-n', '-c', command], capture_output=True, text=True, check=False
    )
    assert parsed.returncode == 0, parsed.stderr


def test_steamos_compatibility_repairs_good_module_without_rebuild(tmp_path):
    repository = DependenciasRepository()
    repository._tool_dir = lambda: tmp_path
    command = repository._steamos_compatibility_stage_command(install=True)

    assert 'boot-config.sh' in command
    assert 'repairing only the SteamOS scheduler boot policy' in command
    assert 'SteamOS scheduler boot policy repaired' in command
    assert 'sudo /usr/bin/bash' in command
    assert 'patch-driver.sh status' in command
    # When a verified module is already present, the branch repairs boot policy
    # directly; the full patch-driver call lives only in the final else branch.
    repair_branch = command.index('repairing only the SteamOS scheduler boot policy')
    full_build = command.index('Building and installing the validated SteamOS fixes')
    assert repair_branch < full_build
    assert command[repair_branch:full_build].count('boot-config.sh install') == 1
    parsed = subprocess.run(
        ['bash', '-n', '-c', command], capture_output=True, text=True, check=False
    )
    assert parsed.returncode == 0, parsed.stderr


def test_full_steamos_install_reapplies_boot_policy_after_protected_install(tmp_path):
    repository = DependenciasRepository()
    repository._tool_dir = lambda: tmp_path
    command = repository._steamos_compatibility_stage_command(install=True)

    build_call = command.rindex('/build.sh;')
    install_call = command.rindex('/install.sh;')
    boot_repair = command.rindex('boot-config.sh install')
    final_status = command.rindex('patch-driver.sh status')
    assert build_call < install_call < boot_repair < final_status
    assert f'sudo /usr/bin/bash {tmp_path}' not in command


def test_terminal_workflows_are_automatically_tee_logged():
    repository = Path('src/bc250cc/infrastructure/terminal_repository.py').read_text(encoding='utf-8')
    planner = Path('src/bc250cc/infrastructure/terminal_plan.py').read_text(encoding='utf-8')
    assert 'workflow-{run_id}.log' in repository
    assert 'workflow_wrapper(comando, status_path, log_path, hold=hold)' in repository
    assert '2>&1 | tee {log}' in planner
    assert 'status=$?' in planner
    assert 'PIPESTATUS' not in planner
    # The log line is now composed through the translator, so assert the
    # generated script rather than a literal in the source.
    assert 'Full log saved to' in workflow_wrapper('true', Path('/tmp/s'), Path('/tmp/l'))
    assert 'log_file=str(log_path)' in repository
    assert 'tee -a {log}' in planner


def test_both_terminal_paths_are_logged_through_the_same_wrapper():
    """A workflow shown in the console must leave the same evidence as before.

    There are now two ways to run a workflow — a terminal emulator, or the
    console docked in the window — and support depends on the .log file either
    way. One writer keeps them from drifting: if a second call to
    ``workflow_wrapper`` ever appears, one of the two paths is logging on its
    own terms and this fails.
    """
    repository = Path('src/bc250cc/infrastructure/terminal_repository.py').read_text(encoding='utf-8')
    assert repository.count('workflow_wrapper(') == 1
    assert repository.count('_write_launch_script(') == 3  # one writer, two callers
    embedded = repository.index('embedded = self._try_embedded_terminal')
    external = repository.index('candidates = terminal_candidates(')
    assert embedded < external, 'the console must be offered before a terminal window'


def test_the_console_declining_still_opens_a_terminal_window():
    """The console is an addition, never a single point of failure."""
    repository = Path('src/bc250cc/infrastructure/terminal_repository.py').read_text(encoding='utf-8')
    # Only a console that took the workflow returns early (and tells the
    # window's workflow watcher); a declined one falls through to the
    # terminal emulators below.
    assert 'if embedded is not None:\n            return _announce_workflow(embedded)' in repository
    # An exception inside the host is swallowed on purpose, so a broken panel
    # costs the user a nicer window and not the workflow itself.
    assert 'except Exception:' in repository
    assert 'The embedded terminal could not run the workflow' in repository


def test_a_workflow_shown_in_the_console_does_not_wait_for_a_key_press():
    """The prompt exists so a terminal window does not vanish; a panel stays."""
    from bc250cc.infrastructure.terminal_plan import workflow_wrapper

    held = workflow_wrapper('echo hi', Path('/tmp/s'), Path('/tmp/l'), hold=True)
    docked = workflow_wrapper('echo hi', Path('/tmp/s'), Path('/tmp/l'), hold=False)
    assert 'Enter to close' in held
    assert 'Enter to close' not in docked
    for wrapper in (held, docked):
        assert 'tee' in wrapper
        assert '> /tmp/s' in wrapper
        assert wrapper.rstrip().endswith('exit "$status"')


def test_manual_terminal_log_is_complete_and_preserves_failure(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path))
    script = TerminalRepository()._manual_terminal_script(
        "printf 'stdout-line\\n'; printf 'stderr-line\\n' >&2; exit 17",
        'Logging test',
    )

    completed = subprocess.run(
        ['bash', str(script)], capture_output=True, text=True, check=False,
        env={**os.environ, 'XDG_STATE_HOME': str(tmp_path)},
    )
    assert completed.returncode == 17
    logs = list((tmp_path / 'bc250-control-center' / 'terminal').glob('workflow-*.log'))
    assert len(logs) == 1
    log = logs[0].read_text(encoding='utf-8')
    assert 'stdout-line' in log
    assert 'stderr-line' in log
    assert 'Process finished with exit code 17' in log
    assert f'Full log saved to: {logs[0]}' in log


def test_steamos_nct6687_install_waits_before_reporting_load_error():
    source = Path(
        'packaging/common/os-scripts/steamos/prepare-fan-pwm.sh'
    ).read_text(encoding='utf-8')

    assert 'bc250_wait_for_nct6687_ready()' in source
    assert 'for attempt in {1..5}' in source
    assert 'insmod /var/lib/nct6687/nct6687.ko force=1' in source
    assert source.count('udevadm trigger --subsystem-match=hwmon') == 2
    assert source.index('bc250_wait_for_nct6687_ready()') < source.index(
        'nct6687 load verification failed'
    )
