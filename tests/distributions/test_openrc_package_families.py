from pathlib import Path

from bc250cc.application.preparation.component_engine import component_capabilities
from bc250cc.platform.packages.strategies.alpine_repository import AlpineRepository
from bc250cc.platform.packages.strategies.detector import OSInfo
from bc250cc.platform.packages.strategies.gentoo_repository import GentooRepository


class Host:
    def __init__(self, tmp_path):
        self.tmp_path = tmp_path

    def _command_path(self, _name):
        return ""

    def _tool_dir(self):
        return self.tmp_path / "ResourceTools"


def _info(family: str) -> OSInfo:
    return OSInfo(family, (), family.title(), family.title(), "", family)


def test_openrc_package_families_expose_real_preparation_and_pwm_scripts(tmp_path):
    for repository_type, family, manager in (
        (AlpineRepository, "alpine", "apk"),
        (GentooRepository, "gentoo", "emerge"),
    ):
        repository = repository_type(Host(tmp_path), _info(family))
        assert Path(repository.scripts_root / repository.dependency_script).is_file()
        assert Path(repository.scripts_root / repository.fan_script).is_file()
        source = (repository.scripts_root / repository.dependency_script).read_text(encoding="utf-8")
        assert manager in source
        assert component_capabilities(repository.info)["runtime"]["available"] is True


def test_openrc_package_scripts_preserve_cpu_detector_contract():
    root = Path(__file__).parents[2] / "packaging/common/os-scripts"
    alpine = (root / "alpine/prepare-dependencies.sh").read_text(encoding="utf-8")
    gentoo = (root / "gentoo/prepare-dependencies.sh").read_text(encoding="utf-8")
    for source in (alpine, gentoo):
        # CPURepository checks for this exact binary before dispatching
        # bc250-detect.  stress-ng cannot stand in for it.
        assert "verify_command stress" in source
        assert "verify_command stress-ng" not in source
        assert "check_governor()" in source
        assert "check_umr()" in source
    assert "py3-qt6" in alpine
    assert "py3-pyqt6" not in alpine
    assert "dev-python/pyqt6" in gentoo
    assert "dev-python/PyQt6" not in gentoo
    assert "dev-util/vulkan-tools" in gentoo
    assert "media-libs/vulkan-tools" not in gentoo
    assert "not stress-ng" in alpine


def test_openrc_cyan_preparation_installs_the_dbus_client_and_service_integration():
    root = Path(__file__).parents[2] / "packaging/common/os-scripts"
    alpine = (root / "alpine/prepare-dependencies.sh").read_text(encoding="utf-8")
    gentoo = (root / "gentoo/prepare-dependencies.sh").read_text(encoding="utf-8")

    # Cyan's reviewed installer intentionally fails closed without busctl.
    # Package preparation must therefore install the exact client before a
    # user gets as far as a root-owned D-Bus policy/service operation.
    assert "dbus-openrc" in alpine
    assert "busctl" in alpine
    assert "verify_command busctl" in alpine
    assert "sys-apps/systemd-utils" in gentoo
    assert "verify_command busctl" in gentoo
