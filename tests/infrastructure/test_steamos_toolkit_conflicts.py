"""Disabled native persistence is protected from overlapping installer actions."""
import pytest

from bc250cc.infrastructure.steamos_toolkit_conflicts import (
    native_conflicts,
    require_no_native_conflicts,
)


@pytest.mark.parametrize('component,unit', [
    ('cpu', 'bc250-smu-oc.service'), ('gpu', 'cyan-skillfish-governor-smu.service'),
    ('cu', 'bc250-cu-live-manager.service'), ('fans', 'bc250-fan-control.service'),
])
def test_native_unit_is_protected_without_starting_or_enabling_it(tmp_path, component, unit):
    path = tmp_path / 'etc/systemd/system' / unit
    path.parent.mkdir(parents=True)
    path.write_text('[Service]\nExecStart=/usr/libexec/bc250-control-center/native-helper apply\n')
    assert native_conflicts(component, tmp_path) == ('/etc/systemd/system/' + unit,)
    with pytest.raises(RuntimeError, match='Use its existing controls'):
        require_no_native_conflicts(component, tmp_path)
    with pytest.raises(RuntimeError):
        require_no_native_conflicts('all', tmp_path)
    assert path.read_text().endswith('native-helper apply\n')


def test_helpers_alone_do_not_mark_a_component_as_configured(tmp_path):
    helper = tmp_path / 'usr/libexec/bc250-control-center/bc250-cpu-smu-helper'
    helper.parent.mkdir(parents=True)
    helper.write_text('fixture')
    assert native_conflicts('all', tmp_path) == ()


def test_an_upstream_unit_is_not_misidentified_as_native(tmp_path):
    unit = tmp_path / 'etc/systemd/system/bc250-smu-oc.service'
    unit.parent.mkdir(parents=True)
    unit.write_text('ExecStart=/opt/toolkit/venv/bin/bc250-apply /etc/bc250-smu-oc.conf\n')
    assert native_conflicts('cpu', tmp_path) == ()


def test_cyan_config_with_native_preflight_is_protected(tmp_path):
    config = tmp_path / 'etc/cyan-skillfish-governor-smu/config.toml'
    config.parent.mkdir(parents=True)
    config.write_text('[dbus]\nenabled = true\n')
    dropin = tmp_path / 'etc/systemd/system/cyan-skillfish-governor-smu.service.d/91-bc250-control-center-overlay-preflight.conf'
    dropin.parent.mkdir(parents=True)
    dropin.write_text('[Service]\n')
    assert len(native_conflicts('gpu', tmp_path)) == 1


def test_native_core_unlock_persistence_is_not_removed_by_another_provider(tmp_path):
    unit = tmp_path / 'etc/systemd/system/bc250-core-unlock.service'
    unit.parent.mkdir(parents=True)
    unit.write_text('[Service]\nExecStart=/var/lib/bc250-core-unlock/bin/bc250-core-unlock apply --boot\n')
    with pytest.raises(RuntimeError, match='Control Center manages this component'):
        require_no_native_conflicts('cores', tmp_path)
    with pytest.raises(RuntimeError):
        require_no_native_conflicts('all', tmp_path)
    assert unit.is_file()


@pytest.mark.parametrize('component,path', [
    ('acpi', 'etc/default/grub.d/92-bc250-acpi.cfg'),
    ('audio', 'etc/udev/rules.d/91-bc250-control-center-hdmi-ac3.rules'),
    ('audio', 'home/.config/wireplumber/wireplumber.conf.d/90-bc250-control-center-hdmi-ac3.conf'),
    ('cec', 'home/.config/cecd/config.d/50-bc250-control-center.toml'),
    ('cec', 'etc/systemd/system/bc250-control-center-cec-poweroff.service'),
    ('video', 'etc/environment.d/90-bc250-control-center-vaapi.conf'),
    ('video', 'etc/profile.d/zz-bc250-control-center-vaapi.sh'),
    ('video', 'etc/X11/Xsession.d/95bc250-vaapi'),
])
def test_native_acpi_audio_and_cec_configuration_is_protected(tmp_path, component, path):
    owned = tmp_path / path
    owned.parent.mkdir(parents=True)
    owned.write_text('# Managed by BC250 Control Center\nfixture\n')
    with pytest.raises(RuntimeError, match='Control Center manages'):
        require_no_native_conflicts(component, tmp_path)
    assert owned.read_text().endswith('fixture\n')
    if component in {'acpi', 'audio', 'video'}:
        with pytest.raises(RuntimeError):
            require_no_native_conflicts('all', tmp_path)
    else:
        require_no_native_conflicts('all', tmp_path)  # Bulk actions do not change CEC.


def test_packaged_ac3_profile_alone_is_not_native_ownership(tmp_path):
    profile = tmp_path / 'usr/share/alsa-card-profile/mixer/profile-sets/hdmi-ac3.conf'
    profile.parent.mkdir(parents=True)
    profile.write_text('distribution package\n')
    assert native_conflicts('audio', tmp_path) == ()
