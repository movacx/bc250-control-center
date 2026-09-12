from bc250cc.platform.immutable import is_immutable_root
from bc250cc.platform.init import InitSystem, detect_init_system
from bc250cc.platform.packages import PackageManagers

# ``bc250cc.platform.distro`` used to live here: a second distribution
# classifier that returned family "openrc" for alpine, artix, devuan, gentoo
# and funtoo — a value no repository factory, capability map or limitation
# table recognised, because it named an *init system* where every other part
# of the project names a *package family*. Nothing in production imported it;
# only this file did. The live classifier is
# ``bc250cc.platform.packages.strategies.detector``, and
# ``tests/platform/test_os_distribution_support.py`` covers it. Init detection
# is a separate question, answered by ``detect_init_system`` below.


def test_init_detection_prefers_openrc_runtime_marker(tmp_path):
    (tmp_path / "openrc").mkdir()
    (tmp_path / "openrc" / "softlevel").touch()
    (tmp_path / "systemd" / "system").mkdir(parents=True)
    assert detect_init_system(tmp_path) is InitSystem.OPENRC


def test_platform_probes_are_injectable(tmp_path, monkeypatch):
    (tmp_path / "ostree-booted").touch()
    monkeypatch.delenv("OSTREE_DEPLOYMENT", raising=False)
    assert is_immutable_root(tmp_path)
    managers = PackageManagers.detect(lambda name: name in {"apt", "busctl"})
    assert managers.apt and not managers.pacman and not managers.rpm_ostree
