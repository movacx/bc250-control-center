from bc250cc.platform.distro import DistroIdentity, read_os_release
from bc250cc.platform.immutable import is_immutable_root
from bc250cc.platform.init import InitSystem, detect_init_system
from bc250cc.platform.packages import PackageManagers


def test_distro_family_is_metadata_only(tmp_path):
    release = tmp_path / "os-release"
    release.write_text('ID=cachyos\nID_LIKE="arch"\nPRETTY_NAME="CachyOS"\n')
    identity = read_os_release(release)
    assert identity.family == "arch"
    assert identity.pretty_name == "CachyOS"


def test_artix_id_like_arch_still_selects_openrc_installation_family():
    identity = DistroIdentity("artix", ("arch",), "Artix Linux")
    assert identity.family == "openrc"


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
