"""Graphics provider selection must preserve the other provider's artifacts."""
import pytest

from bc250cc.infrastructure.steamos_graphics_ownership import (
    graphics_conflicts,
    require_graphics_provider,
)
from bc250cc.shared.errors import ActionNeeded


def _write(path, data='fixture'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data)
    return path


@pytest.mark.parametrize('artifact', [
    'usr/lib/libvulkan_radeon_driconf.so',
    'usr/lib/systemd/user-environment-generators/60-bc250-gfx1013',
    'home/user/.local/share/bc250-mesh-shader/install.conf',
])
def test_real_toolkit_does_not_take_over_existing_alternative_graphics(tmp_path, artifact):
    existing = _write(tmp_path / artifact)
    with pytest.raises(ActionNeeded, match='keyboardspecialist'):
        require_graphics_provider('real-toolkit', root=tmp_path, home=tmp_path / 'home/user')
    assert existing.read_text() == 'fixture'


def test_alternative_does_not_take_over_an_incomplete_real_toolkit_prefix(tmp_path):
    icd = _write(tmp_path / 'opt/bc250-gfx1013/v1/share/vulkan/icd.d/radeon_icd.x86_64.json', 'incomplete')
    with pytest.raises(ActionNeeded, match='Real Toolkit / GFX1013'):
        require_graphics_provider('keyboardspecialist', root=tmp_path, home=tmp_path / 'home')
    assert icd.read_text() == 'incomplete'


def test_a_downloaded_source_tree_does_not_count_as_a_graphics_installation(tmp_path):
    _write(tmp_path / 'home/.bc250-control-center/real-toolkit/workspace/start.sh')
    _write(tmp_path / 'home/user/ResourceTools/bc250-steamos/bc250-mesh-shader.sh')
    for provider in ['real-toolkit', 'keyboardspecialist']:
        assert graphics_conflicts(provider, root=tmp_path, home=tmp_path / 'home/user') == ()


def test_real_toolkit_cannot_erase_a_custom_vulkan_selection(tmp_path):
    environment = _write(tmp_path / 'etc/environment', 'VK_DRIVER_FILES=/custom/radeon.json\nOTHER=value\n')
    with pytest.raises(ActionNeeded):
        require_graphics_provider('real-toolkit', root=tmp_path, home=tmp_path / 'home')
    assert environment.read_text().endswith('OTHER=value\n')


def test_own_toolkit_vulkan_paths_keep_the_existing_stock_32bit_fallback(tmp_path):
    _write(tmp_path / 'etc/environment', 'VK_DRIVER_FILES=/opt/bc250-gfx1013/v1/share/vulkan/icd.d/radeon_icd.x86_64.json:/usr/share/vulkan/icd.d/radeon_icd.i686.json\n')
    assert graphics_conflicts('real-toolkit', root=tmp_path, home=tmp_path / 'home') == ()


@pytest.mark.parametrize('artifact', [
    'opt/bc250-gfx1013/v1/lib/libvulkan_radeon.so',
    'opt/bc250-gfx1013/v1/share/partial-install',
])
def test_alternative_preserves_a_partial_prefix_without_an_icd(tmp_path, artifact):
    existing = _write(tmp_path / artifact)
    with pytest.raises(ActionNeeded, match='Real Toolkit / GFX1013'):
        require_graphics_provider('keyboardspecialist', root=tmp_path, home=tmp_path / 'home')
    assert existing.read_text() == 'fixture'


def test_alternative_preserves_a_dangling_prefix_symlink(tmp_path):
    prefix = tmp_path / 'opt/bc250-gfx1013'
    prefix.parent.mkdir()
    prefix.symlink_to(tmp_path / 'missing')
    assert str(prefix) in graphics_conflicts('keyboardspecialist', root=tmp_path, home=tmp_path / 'home')
    assert prefix.is_symlink()


def test_empty_prefix_does_not_establish_an_existing_installation(tmp_path):
    (tmp_path / 'opt/bc250-gfx1013').mkdir(parents=True)
    assert graphics_conflicts('keyboardspecialist', root=tmp_path, home=tmp_path / 'home') == ()


@pytest.mark.parametrize('assignment', [
    'VK_DRIVER_FILES=/opt/bc250-gfx1013/v1/share/vulkan/icd.d/radeon_icd.x86_64.json',
    'export VK_DRIVER_FILES="/opt/bc250-gfx1013/v1/share/vulkan/icd.d/radeon_icd.x86_64.json"',
    '  VK_DRIVER_FILES = /opt/bc250-gfx1013/v1/share/vulkan/icd.d/radeon_icd.x86_64.json',
])
def test_alternative_does_not_ignore_an_environment_selection_after_prefix_loss(tmp_path, assignment):
    environment = _write(tmp_path / 'etc/environment', assignment + '\n')
    assert graphics_conflicts('keyboardspecialist', root=tmp_path, home=tmp_path / 'home') == (str(environment),)
    assert environment.read_text() == assignment + '\n'


@pytest.mark.parametrize('assignment', [
    'export VK_DRIVER_FILES=/custom/radeon.json',
    '  VK_DRIVER_FILES = "/custom/radeon.json"',
    'VK_DRIVER_FILES=/usr/share/vulkan/icd.d/radeon_icd.i686.json',
    'VK_DRIVER_FILES=/opt/bc250-gfx1013/../../custom/radeon.json',
    'VK_DRIVER_FILES="unterminated',
])
def test_real_toolkit_revert_cannot_remove_foreign_or_unparseable_selections(tmp_path, assignment):
    environment = _write(tmp_path / 'etc/environment', assignment + '\n')
    with pytest.raises(ActionNeeded):
        require_graphics_provider('real-toolkit', root=tmp_path, home=tmp_path / 'home')
    assert environment.read_text() == assignment + '\n'


def test_comments_do_not_establish_a_live_graphics_selection(tmp_path):
    _write(tmp_path / 'etc/environment', '# VK_DRIVER_FILES=/custom/radeon.json\n')
    for provider in ['real-toolkit', 'keyboardspecialist']:
        assert graphics_conflicts(provider, root=tmp_path, home=tmp_path / 'home') == ()


@pytest.mark.parametrize('marker', ['.bc250-gfx1013-fix', '.bc250-audio-fix', '.bc250-metrics-fix'])
def test_kernel_only_alternative_installation_is_protected_without_mesa(tmp_path, marker):
    path = _write(tmp_path / 'usr/lib/modules/current/updates' / marker, 'a' * 64 + ' smu-8core-metrics-r1\n')
    with pytest.raises(ActionNeeded, match='keyboardspecialist'):
        require_graphics_provider('real-toolkit', root=tmp_path, home=tmp_path / 'home', kernel='current')
    assert path.read_text().endswith('smu-8core-metrics-r1\n')


def test_current_alternative_marker_is_retained_as_a_conflict_during_interrupted_rollback(tmp_path):
    marker = _write(tmp_path / 'usr/lib/modules/current/updates/.bc250-gfx1013-fix', 'pending initramfs rebuild')
    assert not (marker.parent / 'amdgpu.ko.zst').exists()
    assert str(marker) in graphics_conflicts('real-toolkit', root=tmp_path, home=tmp_path / 'home', kernel='current')


def test_real_toolkit_can_repair_its_own_hash_only_module_installation(tmp_path):
    _write(tmp_path / 'usr/lib/modules/current/updates/.bc250-audio-fix', 'a' * 64 + '\n')
    assert graphics_conflicts('real-toolkit', root=tmp_path, home=tmp_path / 'home', kernel='current') == ()
    with pytest.raises(ActionNeeded, match='legacy kernel'):
        require_graphics_provider('keyboardspecialist', root=tmp_path, home=tmp_path / 'home', kernel='current')


@pytest.mark.parametrize('with_gfx_marker', [False, True])
def test_current_alternative_keeps_its_own_kernel_repair_available(tmp_path, with_gfx_marker):
    updates = tmp_path / 'usr/lib/modules/current/updates'
    for name in ['.bc250-audio-fix', '.bc250-metrics-fix'] + (['.bc250-gfx1013-fix'] if with_gfx_marker else []):
        _write(updates / name, 'a' * 64 + ' smu-8core-metrics-r1\n')
    assert graphics_conflicts('keyboardspecialist', root=tmp_path, home=tmp_path / 'home', kernel='current') == ()


def test_native_oc_telemetry_override_cannot_be_replaced_but_a_stale_marker_does_not_block(tmp_path):
    updates = tmp_path / 'usr/lib/modules/current/updates'
    _write(updates / '.bc250-control-center-telemetry-oc-2400', 'a' * 64)
    module = _write(updates / 'amdgpu.ko.zst', 'native override')
    with pytest.raises(ActionNeeded, match='Control Center'):
        require_graphics_provider('real-toolkit', root=tmp_path, home=tmp_path / 'home', kernel='current')
    module.unlink()
    _write(updates / 'amdgpu.ko.zst.old', 'unused backup')
    assert graphics_conflicts('real-toolkit', root=tmp_path, home=tmp_path / 'home', kernel='current') == ()


def test_bulk_recovery_checks_other_kernels_while_individual_actions_stay_scoped(tmp_path):
    marker = _write(tmp_path / 'usr/lib/modules/other/updates/.bc250-gfx1013-fix', 'pending')
    assert graphics_conflicts('real-toolkit', root=tmp_path, home=tmp_path / 'home', kernel='current') == ()
    assert str(marker) in graphics_conflicts('real-toolkit', root=tmp_path, home=tmp_path / 'home',
                                            kernel='current', all_kernels=True)


@pytest.mark.parametrize('provider', ['real-toolkit', 'keyboardspecialist'])
@pytest.mark.parametrize('name', ['.bc250-audio-fix', '.bc250-gfx1013-fix'])
def test_unsafe_kernel_marker_links_are_not_adopted(tmp_path, provider, name):
    marker = tmp_path / 'usr/lib/modules/current/updates' / name
    marker.parent.mkdir(parents=True)
    marker.symlink_to(tmp_path / 'missing')
    assert str(marker) in graphics_conflicts(provider, root=tmp_path, home=tmp_path / 'home', kernel='current')


@pytest.mark.parametrize('kernel', ['../other', '.', '..', ''])
def test_kernel_argument_cannot_escape_the_modules_tree(tmp_path, kernel):
    with pytest.raises(ValueError, match='Unsafe kernel'):
        graphics_conflicts('real-toolkit', root=tmp_path, home=tmp_path / 'home', kernel=kernel)
