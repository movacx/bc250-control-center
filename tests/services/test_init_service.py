from pathlib import Path

import pytest

from bc250cc.platform.init.services import (
    InitManagerState,
    detect_init_manager,
    inspect_service,
    openrc_enable_argv,
    openrc_start_argv,
    openrc_status_argv,
    parse_openrc_runlevel,
    parse_openrc_status,
)


def test_openrc_detection_requires_active_runlevel_and_all_tools(tmp_path):
    softlevel = tmp_path / 'softlevel'
    softlevel.write_text('default\n', encoding='utf-8')
    tools = {'openrc-run': '/sbin/openrc-run', 'rc-service': '/sbin/rc-service', 'rc-update': '/sbin/rc-update'}
    state = detect_init_manager(
        openrc_softlevel=softlevel,
        systemd_runtime=tmp_path / 'absent-systemd',
        which=tools.get,
    )
    assert state.kind == 'openrc'
    assert state.available is True


def test_openrc_tools_without_active_runlevel_are_not_treated_as_openrc(tmp_path):
    tools = {'openrc-run': '/sbin/openrc-run', 'rc-service': '/sbin/rc-service', 'rc-update': '/sbin/rc-update'}
    state = detect_init_manager(
        openrc_softlevel=tmp_path / 'absent', systemd_runtime=tmp_path / 'absent-systemd', which=tools.get,
    )
    assert state.kind == 'unknown'
    assert state.available is False


def test_systemd_detection_requires_its_runtime_not_only_systemctl(tmp_path):
    tools = {'systemctl': '/usr/bin/systemctl'}
    inactive = detect_init_manager(
        openrc_softlevel=tmp_path / 'openrc',
        systemd_runtime=tmp_path / 'systemd-absent',
        pid1_comm=tmp_path / 'pid1-absent',
        which=tools.get,
    )
    assert inactive.kind == 'unknown'
    assert inactive.persistence_supported is False

    runtime = tmp_path / 'systemd'
    runtime.mkdir()
    active = detect_init_manager(
        openrc_softlevel=tmp_path / 'openrc',
        systemd_runtime=runtime,
        pid1_comm=tmp_path / 'pid1-absent',
        which=tools.get,
    )
    assert active.kind == 'systemd'
    assert active.persistence_supported is True


@pytest.mark.parametrize(
    ('comm', 'tools', 'expected'),
    (
        ('runit', {'sv': '/usr/bin/sv'}, 'runit'),
        ('s6-svscan', {'s6-svstat': '/usr/bin/s6-svstat'}, 's6'),
        ('dinit', {'dinitctl': '/usr/bin/dinitctl'}, 'dinit'),
        ('init', {'service': '/usr/sbin/service'}, 'sysvinit'),
    ),
)
def test_detected_only_init_managers_are_named_without_claiming_persistence(
    tmp_path, comm, tools, expected,
):
    pid1 = tmp_path / 'comm'
    pid1.write_text(comm + '\n', encoding='ascii')
    state = detect_init_manager(
        openrc_softlevel=tmp_path / 'openrc',
        systemd_runtime=tmp_path / 'systemd',
        pid1_comm=pid1,
        which=tools.get,
    )
    assert state.kind == expected
    assert state.available is True
    assert state.persistence_supported is False
    assert 'live hardware readings remain available' in state.persistence_detail


def test_unknown_init_has_an_explicit_non_persistent_state(tmp_path):
    pid1 = tmp_path / 'comm'
    pid1.write_text('custom-init\n', encoding='ascii')
    state = detect_init_manager(
        openrc_softlevel=tmp_path / 'openrc',
        systemd_runtime=tmp_path / 'systemd',
        pid1_comm=pid1,
        which=lambda _name: None,
    )
    assert state.kind == 'unknown'
    assert state.persistence_supported is False


def test_openrc_argv_and_parsers_are_strict():
    assert openrc_status_argv('bc250-smu-oc.service') == ('rc-service', 'bc250-smu-oc', 'status')
    assert openrc_start_argv('nct6687-load', 'restart') == ('rc-service', 'nct6687-load', 'restart')
    assert openrc_enable_argv('bc250-cu-live-manager', True) == ('rc-update', 'add', 'bc250-cu-live-manager', 'default')
    assert parse_openrc_status(0, ' * status: started') == 'active'
    assert parse_openrc_status(3, ' * status: stopped') == 'inactive'
    assert parse_openrc_status(1, ' * status: crashed') == 'failed'
    assert parse_openrc_runlevel(' bc250-smu-oc | default\n', 'bc250-smu-oc') is True
    assert parse_openrc_runlevel('nct6687-load | default\n', 'bc250-smu-oc') is False


def test_shared_service_inspection_normalizes_systemd_state(tmp_path):
    calls = []

    def runner(command, timeout):
        calls.append((command, timeout))
        if 'is-active' in command:
            return 0, 'active\n', ''
        return 0, 'enabled-runtime\n', ''

    state = inspect_service(
        runner,
        'bc250-smu-oc.service',
        manager=InitManagerState('systemd', True, 'ready'),
        init_script_root=tmp_path,
    )
    assert state.active == 'active'
    assert state.enabled == 'enabled-runtime'
    assert state.exists is True
    assert calls == [
        (['systemctl', 'is-active', 'bc250-smu-oc.service'], 4),
        (['systemctl', 'is-enabled', 'bc250-smu-oc.service'], 4),
    ]


def test_shared_service_inspection_uses_openrc_runlevel(tmp_path):
    script = tmp_path / 'bc250-smu-oc'
    script.write_text('#!/sbin/openrc-run\n', encoding='utf-8')

    def runner(command, timeout):
        del timeout
        if command[0] == 'rc-service':
            return 0, ' * status: started\n', ''
        return 0, ' bc250-smu-oc | default\n', ''

    state = inspect_service(
        runner,
        'bc250-smu-oc.service',
        manager=InitManagerState('openrc', True, 'ready'),
        init_script_root=tmp_path,
    )
    assert state.active == 'active'
    assert state.enabled == 'enabled'
    assert state.exists is True


@pytest.mark.parametrize('output', ['', ' \n', 'Failed to connect to bus'])
def test_service_query_errors_never_become_states(output):
    state = inspect_service(
        lambda *args, **kwargs: (1, output, 'Permission denied'),
        'bc250-smu-oc.service',
        manager=InitManagerState('systemd', True, 'ready'),
    )
    assert state.active == 'unknown'
    assert state.enabled == 'unknown'
    assert state.exists is False


def test_openrc_runlevel_query_failure_is_not_disabled(tmp_path):
    state = inspect_service(
        lambda *args, **kwargs: (1, '', 'Permission denied'),
        'bc250-smu-oc',
        manager=InitManagerState('openrc', True, 'ready'),
        init_script_root=tmp_path,
    )
    assert state.enabled == 'unknown'


def test_openrc_cu_script_waits_for_any_render_node_not_a_fixed_minor():
    helper = (
        Path(__file__).resolve().parents[2]
        / 'privileged/helpers/bc250-openrc-service-helper'
    ).read_text(encoding='utf-8')

    assert '/dev/dri/renderD128' not in helper
    assert 'for node in /dev/dri/renderD*' in helper


def test_openrc_fan_service_requires_a_real_nct_fan_pwm_hwmon_after_loading():
    helper = (
        Path(__file__).resolve().parents[2]
        / 'privileged/helpers/bc250-openrc-service-helper'
    ).read_text(encoding='utf-8')
    fan_script = helper.split('def _fan_script() -> str:', 1)[1].split('\n\ndef _governor_script', 1)[0]

    assert 'NCT6687 loaded but no fan/PWM hwmon node became ready' in fan_script
    assert 'for bc250_nct_name in /sys/class/hwmon/hwmon*/name' in fan_script
    assert '"$bc250_nct_dir"/fan*_input "$bc250_nct_dir"/pwm*_enable' in fan_script


def test_core_unlock_uses_openrc_stop_and_reboot_paths_when_openrc_is_active():
    helper = (
        Path(__file__).resolve().parents[2]
        / 'privileged/helpers/bc250-core-unlock-helper'
    ).read_text(encoding='utf-8')

    assert "['rc-update', 'del', key, 'default']" in helper
    assert "['rc-service', key, 'stop']" in helper
    assert 'def _reboot_after_core_unlock' in helper
    assert "'/sbin/reboot'" in helper


def test_openrc_helper_refuses_to_replace_an_unmanaged_root_service():
    helper = (
        Path(__file__).resolve().parents[2]
        / 'privileged/helpers/bc250-openrc-service-helper'
    ).read_text(encoding='utf-8')

    install_body = helper.split('def install(name: str) -> int:', 1)[1].split('\n\ndef remove', 1)[0]
    assert 'Refusing to replace an OpenRC script not managed by Control Center' in install_body
    assert 'if MARKER not in current:' in install_body


def test_cyan_preparation_does_not_enable_openrc_persistence_implicitly():
    installer = (
        Path(__file__).resolve().parents[2]
        / 'packaging/common/os-scripts/common/install-cyan-upstream-release.sh'
    ).read_text(encoding='utf-8')

    openrc_body = installer.split('if is_openrc; then', 1)[1].split('load_state=', 1)[0]
    assert 'rc-update add cyan-skillfish-governor-smu default' not in openrc_body


def test_openrc_service_property_mapping_does_not_need_systemctl():
    source = (
        Path(__file__).resolve().parents[2]
        / 'src/bc250cc/infrastructure/sistema_repository.py'
    ).read_text(encoding='utf-8')
    method = source.split('    def _service_prop(self, servicio, prop):', 1)[1].split('\n    def _command_path', 1)[0]

    assert "if init_manager.kind == 'openrc':" in method
    assert "['rc-service', key, 'status']" in method
    assert "['rc-update', 'show', 'default']" in method
    assert "if init_manager.kind != 'systemd':" in method


def test_openrc_does_not_offer_the_systemd_user_daemon_controls():
    source = (
        Path(__file__).resolve().parents[2]
        / 'frontends/desktop/pages/settings.py'
    ).read_text(encoding='utf-8')

    daemon_command = source.split('    def _daemon_command(', 1)[1].split('\n    def refresh_daemon_status', 1)[0]
    assert 'detect_init_manager().kind != "systemd"' in daemon_command
    assert 'requires an active systemd user manager' in daemon_command


def test_openrc_cyan_actions_require_the_existing_dbus_preflight():
    source = (
        Path(__file__).resolve().parents[2]
        / 'src/bc250cc/infrastructure/gpu_repository.py'
    ).read_text(encoding='utf-8')

    assert 'def _require_openrc_governor_preflight' in source
    assert "missing_for_cyan" in source
    assert 'self._require_openrc_governor_preflight(selected)' in source
    assert 'requires the system D-Bus to be running' in source


def test_openrc_cyan_restart_verifies_dbus_without_journalctl():
    source = (
        Path(__file__).resolve().parents[2]
        / 'src/bc250cc/infrastructure/gpu_repository.py'
    ).read_text(encoding='utf-8')
    restart = source.split('    def _governor_restart_command(', 1)[1].split('\n    def _governor_config_helper_path', 1)[0]

    assert 'self._cyan_openrc_dbus_wait_steps(' in restart
    assert 'Cyan restarted but its D-Bus name is unavailable after policy repair' in restart
    assert 'journalctl' not in restart
