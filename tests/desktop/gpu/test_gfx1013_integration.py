from pathlib import Path

import pytest

from bc250cc.infrastructure.gfx1013_compute_policy import (
    GFX1013_REVIEWED_COMMIT,
    GFX1013_REVIEWED_VERSION,
    GFX1013_TESTED_KERNEL,
    classify_gfx1013_support,
)


def classify(family, distro_id, version_id, kernel, immutable=False):
    return classify_gfx1013_support(
        family=family,
        distro_id=distro_id,
        version_id=version_id,
        kernel=kernel,
        immutable=immutable,
    )


def test_exact_upstream_fedora_host_is_recognized_but_not_auto_installed():
    state = classify('fedora', 'fedora', '43', GFX1013_TESTED_KERNEL)
    assert state['exact_upstream_validated_host'] is True
    assert state['direct_installer_allowed'] is True
    assert state['automatic_install_allowed'] is False
    assert state['reason_key'] == 'fedora-upstream-managed'
    assert state['upstream_branch'] == 'main'
    assert state['upstream_managed'] is True


def test_other_mutable_fedora_versions_delegate_compatibility_to_upstream():
    state = classify('fedora', 'fedora', '44', '7.1.5-200.fc44.x86_64')
    assert state['exact_upstream_validated_host'] is False
    assert state['direct_installer_allowed'] is True
    assert state['automatic_install_allowed'] is False
    assert state['reason_key'] == 'fedora-upstream-managed'


@pytest.mark.parametrize('family,distro', (
    ('arch', 'arch'),
    ('manjaro', 'manjaro'),
    ('cachyos', 'cachyos'),
))
def test_arch_family_is_manual_and_unverified(family, distro):
    state = classify(family, distro, '', '7.1.5-arch1-1')
    assert state['status'] == 'manual-untested'
    assert state['automatic_install_allowed'] is False
    assert state['reason_key'] == 'arch-family-manual-untested'


def test_bazzite_and_atomic_are_blocked():
    state = classify('bazzite', 'bazzite', '43', '6.17.9', immutable=True)
    assert state['status'] == 'blocked'
    assert state['direct_installer_allowed'] is False
    assert state['reason_key'] == 'bazzite-not-supported-upstream'


def test_steamos_uses_dedicated_backend_not_fedora_installer():
    state = classify('steamos', 'steamos', '3.9', '6.18.40-neptune-616')
    assert state['mode'] == 'steamos-backend'
    assert state['direct_installer_allowed'] is False
    assert state['automatic_install_allowed'] is False
    assert state['reason_key'] == 'steamos-dedicated-backend'
    assert 'keyboardspecialist/bc250-steamos' in state['steamos_backend']


def test_other_distros_are_manual_only():
    state = classify('debian', 'debian', '13', '6.12.0')
    assert state['mode'] == 'manual-only'
    assert state['automatic_install_allowed'] is False


def test_reviewed_revision_and_version_are_pinned_in_policy():
    assert GFX1013_REVIEWED_VERSION == '0.2.0-alpha'
    assert GFX1013_REVIEWED_COMMIT == '5bb0dac39d094fe9cbd10d2b34868837125d9c39'


def test_prepare_dependencies_never_invokes_unsafe_legacy_radv_installer():
    source = Path('src/bc250cc/infrastructure/dependencias_repository.py').read_text(encoding='utf-8')
    assert 'bc250-mesh-shader.sh' not in source
    assert './install.sh build' not in source
    assert './install.sh install' not in source


def test_third_party_credit_identifies_the_official_gfx1013_workflow():
    common = Path('packaging/common/os-scripts/common/common.sh').read_text(encoding='utf-8')
    expected = '- GFX1013 kernel/Mesa stack (official upstream workflow): https://github.com/DryhoppedIPA/bc250-gfx1013-fix'
    assert expected in common
    assert 'GFX1013 kernel/Mesa async-compute research' not in common


def test_third_party_notices_record_gfx1013_as_official_external_install():
    notices = Path('docs/THIRD_PARTY_NOTICES.md').read_text(encoding='utf-8')
    assert 'bc250-gfx1013-fix' in notices
    assert 'External install; Control Center updates official `main`' in notices


def test_gfx1013_visible_copy_is_translated_for_every_supported_language():
    from frontends.desktop.i18n.interface_catalog import INTERFACE_TRANSLATIONS

    keys = (
        'GFX1013 async compute',
        'Review required',
        'Kernel ready',
        'SteamOS backend',
        'Official upstream workflow',
        'Blocked',
        'Manual only',
        'Patched boot active',
        'External install',
        'An external DryhoppedIPA installation is active on this boot. Control Center will not modify its boot entry, initramfs, amdgpu module or Mesa files.',
        'An external DryhoppedIPA installation was detected, but this boot is not using its patched entry. Boot selection and rollback remain managed by the upstream installer.',
        'SteamOS uses its dedicated BC-250 kernel compatibility backend. Control Center will not run DryhoppedIPA\'s Fedora installer or the legacy mesh/task RADV path.',
        'The SteamOS kernel compute repair is active. The optional alternate RADV path is not installed by Control Center.',
        "Control Center updates DryhoppedIPA's official main branch and invokes its combined kernel + Mesa/RADV workflow unchanged. Upstream performs the Fedora/kernel compatibility checks and keeps the stock boot entry as the recovery path.",
        'Upstream documents this Arch-family path as manual and untested. Control Center does not automate kernel/Mesa changes here.',
        'Upstream currently says Bazzite is not supported. Control Center blocks the direct installer on immutable systems.',
        'Reviewed upstream: {version} · {commit}',
        'Open upstream project',
        'Could not open upstream project',
        'The upstream project link could not be opened by this desktop session.',
    )
    from frontends.desktop.i18n import SUPPORTED_LANGUAGES, tr
    from frontends.desktop.i18n.locale_catalog import load_locale_catalog
    for key in keys:
        assert key in INTERFACE_TRANSLATIONS
        for language in SUPPORTED_LANGUAGES:
            assert tr(key, language).strip()
            assert key in load_locale_catalog(language)
