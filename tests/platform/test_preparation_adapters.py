from bc250cc.application.preparation import plan_runtime_dependencies
from bc250cc.platform.packages import PackageManagers


def test_immutable_fedora_uses_rpm_ostree_and_reboot_boundary():
    plan = plan_runtime_dependencies(PackageManagers(rpm_ostree=True), immutable=True)
    assert plan.manager == "rpm-ostree"
    assert plan.requires_reboot


def test_openrc_package_family_is_not_inferred_from_init_system():
    plan = plan_runtime_dependencies(PackageManagers(apt=True), immutable=False)
    assert plan.manager == "apt"
    assert {"python3-pyqt6", "python3-psutil", "polkit", "kmod", "jq"}.issubset(plan.packages)


def test_arch_plan_uses_arch_package_names_and_declares_quick_access_dependencies():
    plan = plan_runtime_dependencies(PackageManagers(pacman=True), immutable=False)
    assert plan.manager == "pacman"
    assert "python-pyqt6" in plan.packages
    assert "python3-pyqt6" not in plan.packages
    assert "jq" in plan.packages


def test_openrc_package_managers_have_native_dependency_plans():
    alpine = plan_runtime_dependencies(PackageManagers(apk=True), immutable=False)
    gentoo = plan_runtime_dependencies(PackageManagers(emerge=True), immutable=False)
    assert alpine.manager == "apk"
    assert {"py3-qt6", "py3-psutil", "busctl", "jq"}.issubset(alpine.packages)
    assert gentoo.manager == "emerge"
    assert {"dev-python/pyqt6", "sys-apps/systemd-utils", "app-misc/jq"}.issubset(gentoo.packages)
