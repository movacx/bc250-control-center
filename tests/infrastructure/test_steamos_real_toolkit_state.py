"""Observe actual provider files; do not confuse installation with live use."""
import json

import pytest

from bc250cc.infrastructure.steamos_real_toolkit import REPOSITORY
from bc250cc.infrastructure.steamos_real_toolkit_state import probe_real_toolkit

REVISION = '0123456789abcdef0123456789abcdef01234567'


def _write(root, name, content):
    path = root / name.lstrip('/')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _graphics(root):
    prefix = 'opt/bc250-gfx1013/mesa-fixture'
    icd = prefix + '/share/vulkan/icd.d/radeon_icd.x86_64.json'
    lib = root / prefix / 'lib/libvulkan_radeon.so'
    lib.parent.mkdir(parents=True)
    lib.write_bytes(b'\x7fELF fixture, never loaded')
    _write(root, icd, json.dumps({'ICD': {'library_path': '/' + prefix + '/lib/libvulkan_radeon.so'}}))
    return icd, lib


def test_absent_provider_is_not_prepared_and_does_not_create_files(tmp_path):
    result = probe_real_toolkit(root=tmp_path, home=tmp_path / 'home', kernel='fixture')
    assert not result['prepared']
    assert result['graphics']['state'] == 'not-installed'
    assert result['graphics']['active'] is None
    assert list(tmp_path.iterdir()) == []


def test_provider_snapshot_is_separate_from_component_installation(tmp_path):
    workspace = 'home/.bc250-control-center/real-toolkit/workspace/'
    _write(tmp_path, workspace + '.bc250cc-provider.json', json.dumps({'repository': REPOSITORY, 'revision': REVISION}))
    _write(tmp_path, workspace + 'start.sh', '# never executed')
    state = probe_real_toolkit(root=tmp_path, home=tmp_path / 'home', kernel='fixture')
    assert state['prepared'] and state['graphics']['state'] == 'not-installed'
    assert state['reviewed_revision'] == REVISION
    assert not any(state['components'].values())


def test_a_workspace_without_a_commit_hash_is_not_prepared(tmp_path):
    workspace = 'home/.bc250-control-center/real-toolkit/workspace/'
    _write(tmp_path, workspace + '.bc250cc-provider.json', json.dumps({'repository': REPOSITORY, 'revision': 'main'}))
    _write(tmp_path, workspace + 'start.sh', '# never executed')
    state = probe_real_toolkit(root=tmp_path, home=tmp_path / 'home', kernel='fixture')
    assert not state['prepared'] and state['reviewed_revision'] == ''


def test_valid_library_and_environment_prove_configuration_not_live_activation(tmp_path):
    icd, _ = _graphics(tmp_path)
    _write(tmp_path, 'etc/environment', 'VK_DRIVER_FILES="/' + icd + '"\n')
    state = probe_real_toolkit(root=tmp_path, home=tmp_path / 'home', kernel='fixture')
    assert state['graphics']['state'] == 'configured'
    assert state['graphics']['activation_configured']
    assert state['graphics']['active'] is None


def test_missing_library_and_overridden_environment_are_not_ready(tmp_path):
    icd, library = _graphics(tmp_path)
    _write(tmp_path, 'etc/environment', 'VK_DRIVER_FILES=/' + icd + '\nVK_DRIVER_FILES=/stock.json\n')
    state = probe_real_toolkit(root=tmp_path, home=tmp_path / 'home', kernel='fixture')
    assert state['graphics']['state'] == 'incomplete'
    library.unlink()
    _write(tmp_path, 'etc/environment', 'VK_DRIVER_FILES=/' + icd + '\n')
    state = probe_real_toolkit(root=tmp_path, home=tmp_path / 'home', kernel='fixture')
    assert not state['graphics']['activation_configured']


def test_proton_marker_alone_is_not_a_working_compatibility_tool(tmp_path):
    home = tmp_path / 'home'
    marker = '.local/share/Steam/compatibilitytools.d/.bc250-fsr4-marker'
    _write(home, marker, 'package:tool\npackage:../../outside\n')
    assert probe_real_toolkit(root=tmp_path, home=home, kernel='fixture')['proton']['state'] == 'incomplete'
    _write(home, '.local/share/Steam/compatibilitytools.d/tool/compatibilitytool.vdf', 'fixture')
    assert probe_real_toolkit(root=tmp_path, home=home, kernel='fixture')['proton']['state'] == 'incomplete'
    launcher = _write(home, '.local/share/Steam/compatibilitytools.d/tool/proton', '#!/bin/sh\nexit 99\n')
    launcher.chmod(0o755)
    _write(home, marker, 'package:tool\n')
    state = probe_real_toolkit(root=tmp_path, home=home, kernel='fixture')
    assert state['proton'] == {'state': 'installed', 'tools': ['tool']}


def test_one_complete_proton_variant_does_not_hide_an_incomplete_second_variant(tmp_path):
    home = tmp_path / 'home'
    base = '.local/share/Steam/compatibilitytools.d/'
    _write(home, base + '.bc250-fsr4-marker', 'package-one:complete\npackage-two:incomplete\n')
    for name in ['complete', 'incomplete']:
        _write(home, base + name + '/compatibilitytool.vdf', 'fixture')
    _write(home, base + 'complete/proton', '#!/bin/sh\nexit 99\n').chmod(0o755)
    state = probe_real_toolkit(root=tmp_path, home=home, kernel='fixture')
    assert state['proton'] == {'state': 'incomplete', 'tools': ['complete']}


def test_non_executable_proton_launcher_is_not_an_installed_tool(tmp_path):
    home = tmp_path / 'home'
    base = '.local/share/Steam/compatibilitytools.d/'
    _write(home, base + '.bc250-fsr4-marker', 'package:tool\n')
    _write(home, base + 'tool/compatibilitytool.vdf', 'fixture')
    _write(home, base + 'tool/proton', '#!/bin/sh\nexit 99\n').chmod(0o644)
    assert probe_real_toolkit(root=tmp_path, home=home, kernel='fixture')['proton']['state'] == 'incomplete'


def test_old_kernel_modules_do_not_count_for_the_current_kernel(tmp_path):
    _write(tmp_path, '/usr/lib/modules/old/updates/amdgpu.ko', 'fixture')
    state = probe_real_toolkit(root=tmp_path, home=tmp_path / 'home', kernel='current')
    assert not state['graphics']['kernel_override_installed']


def test_shared_cpu_config_does_not_prove_toolkit_ownership(tmp_path):
    _write(tmp_path, 'etc/bc250-smu-oc.conf', 'fixture')
    _write(tmp_path, 'etc/systemd/system/bc250-smu-oc.service',
           'ExecStart=/usr/libexec/bc250-control-center/bc250-cpu-smu-helper apply-config /etc/bc250-smu-oc.conf\n')
    state = probe_real_toolkit(root=tmp_path, home=tmp_path / 'home', kernel='current')
    assert state['components']['cpu'], 'Only configuration presence is observed'
    assert state['native_ownership']['cpu'] == ['/etc/systemd/system/bc250-smu-oc.service']
    assert not state['prepared'], 'Native configuration does not prove the toolkit was prepared'


def test_dual_audio_observes_the_actual_user_configuration_paths(tmp_path):
    home = tmp_path / 'home/user'
    first = '.config/wireplumber/wireplumber.conf.d/50-bc250-audio.conf'
    second = '.config/pipewire/pipewire.conf.d/60-bc250-ac3-output.conf'
    _write(home, first, 'fixture')
    assert not probe_real_toolkit(root=tmp_path, home=home, kernel='current')['components']['dual-audio']
    _write(home, second, 'fixture')
    assert probe_real_toolkit(root=tmp_path, home=home, kernel='current')['components']['dual-audio']


@pytest.mark.parametrize('assignment', ['export VK_DRIVER_FILES="/{icd}"', ' VK_DRIVER_FILES = /{icd}'])
def test_probe_and_conflict_guard_recognize_the_same_assignment_forms(tmp_path, assignment):
    from bc250cc.infrastructure.steamos_graphics_ownership import graphics_conflicts

    icd, _ = _graphics(tmp_path)
    _write(tmp_path, 'etc/environment', assignment.format(icd=icd) + '\n')
    state = probe_real_toolkit(root=tmp_path, home=tmp_path / 'home', kernel='fixture')
    assert state['graphics']['state'] == 'configured'
    assert state['graphics']['active'] is None
    assert graphics_conflicts('real-toolkit', root=tmp_path, home=tmp_path / 'home') == ()


@pytest.mark.parametrize('last_value', ['"unterminated', '', '/one.json /two.json', '""'])
def test_invalid_later_selection_cannot_reuse_an_earlier_valid_selection(tmp_path, last_value):
    icd, _ = _graphics(tmp_path)
    _write(tmp_path, 'etc/environment', 'VK_DRIVER_FILES=/' + icd + '\nVK_DRIVER_FILES=' + last_value + '\n')
    state = probe_real_toolkit(root=tmp_path, home=tmp_path / 'home', kernel='fixture')
    assert state['graphics']['state'] == 'incomplete'
    assert not state['graphics']['activation_configured']


def test_partial_libraries_without_an_icd_are_an_incomplete_installation(tmp_path):
    _write(tmp_path, 'opt/bc250-gfx1013/v1/lib/libvulkan_radeon.so', 'partial')
    state = probe_real_toolkit(root=tmp_path, home=tmp_path / 'home', kernel='fixture')
    assert state['graphics']['state'] == 'incomplete'
    assert state['graphics']['icds'] == []


def test_another_vulkan_driver_does_not_establish_a_toolkit_installation(tmp_path):
    _write(tmp_path, 'etc/environment', 'VK_DRIVER_FILES=/custom/radeon.json\n')
    state = probe_real_toolkit(root=tmp_path, home=tmp_path / 'home', kernel='fixture')
    assert state['graphics']['state'] == 'not-installed'
    assert not state['graphics']['activation_configured']


def test_a_toolkit_environment_selection_can_outlive_its_installation(tmp_path):
    _write(tmp_path, 'etc/environment', 'export VK_DRIVER_FILES="/opt/bc250-gfx1013/v1/old.json"\n')
    state = probe_real_toolkit(root=tmp_path, home=tmp_path / 'home', kernel='fixture')
    assert state['graphics']['state'] == 'incomplete'
    assert not state['graphics']['activation_configured']


@pytest.mark.parametrize('state,activation,expected', [
    ('configured', True, True), ('configured', False, False),
    ('incomplete', True, False), ('not-installed', False, False), ('unknown', False, False),
])
def test_repository_legacy_ready_field_uses_validated_provider_evidence(
    tmp_path, monkeypatch, state, activation, expected,
):
    from types import SimpleNamespace

    from bc250cc.infrastructure import dependencias_repository as repository
    from bc250cc.infrastructure import (
        steamos_graphics_runtime,
        steamos_real_toolkit_state,
    )

    # These names and a comment satisfied the former heuristic even with an
    # invalid library/overridden selection. The authoritative probe must win.
    _write(tmp_path, 'opt/bc250-gfx1013/v1/share/vulkan/icd.d/radeon_icd.x86_64.json', 'invalid')
    _write(tmp_path, 'etc/environment', '# VK_DRIVER_FILES=/opt/bc250-gfx1013/v1/stale.json\n')
    monkeypatch.setattr(repository, 'Path', lambda name: tmp_path / str(name).lstrip('/'))
    monkeypatch.setattr(repository, 'read_os_release', lambda: {'VERSION_ID': 'fixture'})
    for name in ('masta_bc250_stack_state', 'gfx1013_source_state', 'debian_kernel_upgrade_state', 'radv_async_state'):
        monkeypatch.setattr(repository, name, lambda **kwargs: {})
    monkeypatch.setattr(steamos_graphics_runtime, 'probe_steamos_graphics_runtime', lambda: {})
    monkeypatch.setattr(steamos_real_toolkit_state, 'probe_real_toolkit',
                        lambda: {'graphics': {'state': state, 'activation_configured': activation}})
    host = SimpleNamespace(info=SimpleNamespace(family='steamos', distro_id='steamos', immutable=True))
    result = repository.DependenciasRepository()._gfx1013_compute_state(host)
    assert result['steamos_safe_radv_detected'] is expected
    assert result['steamos_real_toolkit']['graphics']['state'] == state
