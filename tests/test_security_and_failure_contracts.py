from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


class SecurityAndFailureContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]

    def read(self, relative):
        return (self.root / relative).read_text(encoding='utf-8')

    def test_pwm_helper_is_narrow_and_written_atomically(self):
        source = self.read('mvc/Repository/fan_repository.py')
        helper = source.split('helper_code = r"""', 1)[1].split('"""', 1)[0]
        self.assertIn("if pwm < 1 or pwm > 12", helper)
        self.assertIn("if value < 0 or value > 255", helper)
        self.assertNotIn('/etc/', helper)
        self.assertNotIn('modprobe', helper)
        self.assertNotIn('subprocess', helper)
        self.assertIn('os.O_EXCL', source)
        self.assertIn('os.O_NOFOLLOW', source)
        self.assertIn('ruta.chmod(0o700)', source)

    def test_packaged_pwm_helper_has_exact_polkit_path_and_is_packaged(self):
        helper = self.read('mvc/Resources/privileged/bc250-fan-pwm-helper')
        policy_path = self.root / 'packaging/common/polkit/io.github.fabianbeita.bc250-control-center.policy'
        policy = policy_path.read_text(encoding='utf-8')
        ET.parse(policy_path)
        fan_source = self.read('mvc/Repository/fan_repository.py')
        self.assertIn("metadata.st_uid != 0", fan_source)
        self.assertIn("metadata.st_mode & 0o022", fan_source)
        self.assertIn("installed_system_wide", fan_source)
        self.assertIn("/usr/libexec/bc250-control-center/bc250-fan-pwm-helper", policy)
        self.assertNotIn('/etc/', helper)
        self.assertNotIn('subprocess', helper)
        for recipe in (
            'packaging/arch/local/PKGBUILD',
            'packaging/arch/aur/PKGBUILD',
            'packaging/debian/build-deb.sh',
            'packaging/rpm/bc250-control-center.spec',
        ):
            with self.subTest(recipe=recipe):
                source = self.read(recipe)
                self.assertIn('bc250-fan-pwm-helper', source)
                self.assertIn('io.github.fabianbeita.bc250-control-center.policy', source)

    def test_local_installer_uses_the_exact_polkit_helper_path(self):
        installer = self.read('scripts/install-local.sh')
        uninstaller = self.read('scripts/uninstall-local.sh')
        exact_helper = '/usr/libexec/bc250-control-center/bc250-fan-pwm-helper'
        exact_policy = '/usr/share/polkit-1/actions/io.github.fabianbeita.bc250-control-center.policy'
        self.assertIn(f'SYSTEM_PRIV_HELPER="{exact_helper}"', installer)
        self.assertIn(f'SYSTEM_POLKIT_ACTION="{exact_policy}"', installer)
        self.assertIn('install_privileged_pwm_components', installer)
        self.assertNotIn('PRIV_HELPER_DIR="$PREFIX/libexec', installer)
        self.assertIn(f'SYSTEM_PRIV_HELPER="{exact_helper}"', uninstaller)
        self.assertIn(f'SYSTEM_POLKIT_ACTION="{exact_policy}"', uninstaller)

    def test_bazzite_returns_reboot_required_instead_of_false_success(self):
        source = self.read('mvc/Repository/Os_repository/scripts/bazzite/prepare-dependencies.sh')
        self.assertIn('package_is_active', source)
        self.assertIn('BC250_REBOOT_REQUIRED=1', source)
        self.assertIn('exit 20', source)
        dependency_repo = self.read('mvc/Repository/dependencias_repository.py')
        self.assertIn("prepare_dependencies_command('all'", dependency_repo)

    def test_debian_temporary_cleanup_does_not_leak_return_trap(self):
        source = self.read('mvc/Repository/Os_repository/scripts/debian/prepare-dependencies.sh')
        self.assertIn('install_governor() (', source)
        self.assertIn("trap 'rm -rf \"$workdir\"' EXIT", source)
        self.assertNotIn("trap 'rm -rf \"$workdir\"' RETURN", source)

    def test_direct_aur_fallback_requests_clean_build(self):
        source = self.read('mvc/Repository/Os_repository/scripts/common/aur.sh')
        self.assertIn('--cleanbuild', source)
        self.assertIn('--syncdeps', source)
        self.assertIn('--install', source)


if __name__ == '__main__':
    unittest.main()
