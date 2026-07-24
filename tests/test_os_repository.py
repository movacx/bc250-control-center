from pathlib import Path
import shutil
import unittest

from mvc.Repository.Os_repository.arch_repository import ArchRepository, CachyOSRepository, ManjaroRepository
from mvc.Repository.Os_repository.bazzite_repository import BazziteRepository
from mvc.Repository.Os_repository.debian_repository import DebianRepository, UbuntuRepository
from mvc.Repository.Os_repository.detector import detect_os_info
from mvc.Repository.Os_repository.factory import create_os_repository
from mvc.Repository.Os_repository.fedora_repository import FedoraRepository
from mvc.Repository.Os_repository.steamos_repository import SteamOSRepository


class FakeHost:
    def __init__(self, os_release, commands=()):
        self.os_release = os_release
        self.commands = set(commands)

    def _os_release(self):
        return dict(self.os_release)

    def _command_path(self, name):
        return f'/usr/bin/{name}' if name in self.commands else ''

    def _tool_dir(self):
        return Path('/home/test/.local/share/bc250-control-center/ResourceTools')


class OSDetectionTests(unittest.TestCase):
    def test_distribution_families(self):
        cases = [
            ({'ID': 'arch'}, (), ArchRepository),
            ({'ID': 'manjaro', 'ID_LIKE': 'arch'}, (), ManjaroRepository),
            ({'ID': 'cachyos', 'ID_LIKE': 'arch'}, (), CachyOSRepository),
            ({'ID': 'ubuntu', 'ID_LIKE': 'debian'}, (), UbuntuRepository),
            ({'ID': 'debian'}, (), DebianRepository),
            ({'ID': 'fedora'}, (), FedoraRepository),
            ({'ID': 'bazzite', 'ID_LIKE': 'fedora'}, ('rpm-ostree',), BazziteRepository),
            ({'ID': 'steamos', 'ID_LIKE': 'arch'}, ('pacman',), SteamOSRepository),
            ({'ID': 'holo', 'NAME': 'SteamOS'}, ('pacman',), SteamOSRepository),
        ]
        for raw, commands, expected_type in cases:
            with self.subTest(raw=raw):
                self.assertIsInstance(create_os_repository(FakeHost(raw, commands)), expected_type)

    def test_bazzite_is_immutable(self):
        info = detect_os_info({'ID': 'bazzite', 'ID_LIKE': 'fedora'}, has_rpm_ostree=True)
        self.assertEqual(info.family, 'bazzite')
        self.assertTrue(info.immutable)

    def test_manjaro_has_dedicated_strategy_identity(self):
        repo = create_os_repository(FakeHost({'ID': 'manjaro', 'ID_LIKE': 'arch'}, ('pacman',)))
        self.assertEqual(repo.info.family, 'manjaro')
        self.assertEqual(repo.family, 'manjaro')
        self.assertIn('arch/prepare-dependencies.sh', repo.prepare_dependencies_command())


class ScriptContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]

    def read(self, relative):
        return (self.root / relative).read_text(encoding='utf-8')

    def test_arch_bootstraps_complete_aur_toolchain_and_yay(self):
        common_aur = self.read('mvc/Repository/Os_repository/scripts/common/aur.sh')
        arch = self.read('mvc/Repository/Os_repository/scripts/arch/prepare-dependencies.sh')
        self.assertIn('base-devel git fakeroot debugedit', common_aur)
        self.assertIn('pacman -Si yay', common_aur)
        self.assertIn('https://aur.archlinux.org/yay.git', common_aur)
        self.assertIn('cyan-skillfish-governor-smu', arch)
        self.assertIn('verify_command cyan-skillfish-governor-smu', arch)

    def test_fan_and_dependency_repositories_no_longer_embed_package_manager_branches(self):
        dependency_source = self.read('mvc/Repository/dependencias_repository.py')
        fan_source = self.read('mvc/Repository/fan_repository.py')
        for token in ('sudo pacman', 'sudo apt', 'sudo dnf', 'rpm-ostree install'):
            self.assertNotIn(token, dependency_source)
            self.assertNotIn(token, fan_source)

    def test_all_os_scripts_exist_and_are_executable(self):
        paths = [
            'arch/prepare-dependencies.sh', 'arch/prepare-fan-pwm.sh',
            'debian/prepare-dependencies.sh', 'debian/prepare-fan-pwm.sh',
            'fedora/prepare-dependencies.sh', 'fedora/prepare-fan-pwm.sh',
            'bazzite/prepare-dependencies.sh', 'bazzite/prepare-fan-pwm.sh',
            'steamos/prepare-dependencies.sh', 'steamos/prepare-fan-pwm.sh',
            'common/install-fan-persistence.sh',
            'bazzite/install-fan-persistence.sh',
        ]
        scripts_root = self.root / 'mvc/Repository/Os_repository/scripts'
        for relative in paths:
            with self.subTest(relative=relative):
                path = scripts_root / relative
                self.assertTrue(path.is_file())
                self.assertTrue(path.stat().st_mode & 0o111)

    def test_bazzite_prepares_sources_before_single_transactional_reboot(self):
        dependency_repo = self.read('mvc/Repository/dependencias_repository.py')
        method = dependency_repo.split('def instalar_dependencias_bc250', 1)[1].split('def _clone_or_update_command', 1)[0]
        self.assertLess(method.index('_clone_or_update_with_archive_command'), method.index("prepare_dependencies_command('all'"))

        script = self.read('mvc/Repository/Os_repository/scripts/bazzite/prepare-dependencies.sh')
        self.assertEqual(script.count('rpm-ostree install --idempotent'), 1)
        self.assertIn('Layering packages into one rpm-ostree deployment', script)
        self.assertIn('you do not need to press Prepare dependencies again', script)
        self.assertIn('package_is_pending', script)

    def test_fedora_fan_uses_generic_kernel_headers_and_matching_kernel_devel(self):
        script = self.read('mvc/Repository/Os_repository/scripts/fedora/prepare-fan-pwm.sh')
        self.assertIn('kernel-headers', script)
        self.assertNotIn('"kernel-headers-$KERNEL_RELEASE"', script)
        self.assertIn('"kernel-devel-$KERNEL_RELEASE"', script)
        self.assertIn('kernel_build_tree_ready', script)
        self.assertIn('return 21', script)

    def test_bazzite_fan_module_uses_persistent_var_storage_without_depmod(self):
        prepare = self.read('mvc/Repository/Os_repository/scripts/bazzite/prepare-fan-pwm.sh')
        persistence = self.read('mvc/Repository/Os_repository/scripts/bazzite/install-fan-persistence.sh')
        self.assertIn('/var/lib/bc250-control-center', prepare)
        self.assertIn('kernel-modules/$KERNEL_RELEASE', prepare)
        self.assertNotIn('akmod-nct6687d', prepare)
        self.assertNotIn('as_root depmod', prepare)
        self.assertNotIn('restorecon', prepare)
        self.assertIn('build_for_current_kernel', persistence)
        self.assertIn('MODULE_ROOT="$STATE_DIR/kernel-modules"', persistence)
        self.assertIn('chcon -t modules_object_t', persistence)
        self.assertNotIn('restorecon', persistence)
        self.assertIn('/etc/systemd/system/nct6687-load.service', persistence)



if __name__ == '__main__':
    unittest.main()
