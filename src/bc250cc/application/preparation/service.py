"""Dependency planning; execution remains an explicit platform operation."""

from __future__ import annotations

from dataclasses import dataclass

from bc250cc.platform.packages import PackageManagers


@dataclass(frozen=True)
class PreparationPlan:
    manager: str
    packages: tuple[str, ...]
    requires_reboot: bool = False


_PACKAGES_BY_MANAGER: dict[str, tuple[str, ...]] = {
    "pacman": (
        "python", "python-pyqt6", "qt6-svg", "python-psutil", "git",
        "pciutils", "polkit", "kmod", "jq",
    ),
    "dnf": (
        "python3", "python3-pyqt6", "qt6-qtsvg", "python3-psutil", "git",
        "pciutils", "polkit", "kmod", "jq",
    ),
    "apt": (
        "python3", "python3-pyqt6", "libqt6svg6", "python3-psutil", "git",
        "pciutils", "polkit", "kmod", "jq",
    ),
    "apk": (
        "python3", "py3-qt6", "py3-psutil", "qt6-qtsvg", "git", "pciutils",
        "polkit", "kmod", "dbus", "busctl", "jq",
    ),
    "emerge": (
        "dev-lang/python", "dev-python/pyqt6", "dev-python/psutil", "dev-qt/qtbase",
        "dev-qt/qtsvg", "dev-vcs/git", "sys-apps/pciutils", "sys-auth/polkit",
        "sys-apps/kmod", "sys-apps/dbus", "sys-apps/systemd-utils", "app-misc/jq",
    ),
}


def plan_runtime_dependencies(managers: PackageManagers, *, immutable: bool) -> PreparationPlan:
    if immutable and managers.rpm_ostree:
        return PreparationPlan(
            "rpm-ostree", _PACKAGES_BY_MANAGER["dnf"], requires_reboot=True
        )
    if managers.pacman:
        return PreparationPlan("pacman", _PACKAGES_BY_MANAGER["pacman"])
    if managers.dnf:
        return PreparationPlan("dnf", _PACKAGES_BY_MANAGER["dnf"])
    if managers.apt:
        return PreparationPlan("apt", _PACKAGES_BY_MANAGER["apt"])
    if managers.apk:
        return PreparationPlan("apk", _PACKAGES_BY_MANAGER["apk"])
    if managers.emerge:
        return PreparationPlan("emerge", _PACKAGES_BY_MANAGER["emerge"])
    return PreparationPlan("unsupported", ())
