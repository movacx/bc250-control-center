"""Whether the running kernel can build modules, and the repair when it cannot.

DKMS drivers (fans, power and memory sensors, VirtualBox...) are built against
the headers of the running kernel. When the headers are missing, or are for
another version, every DKMS driver disappears at the next boot. The common
cause is a partial update: on Arch, installing the headers alone pulls the
repository's newer version while the kernel stays on the old one, and the
DKMS hook then removes the modules built for the running kernel (seen on
2026-11-21 with linux 7.3.4 and linux-headers 7.3.5).

The check only reads: /usr/lib/modules, /var/lib/dkms and the package
database. The repair is one terminal workflow that decides on the spot, per
package manager, between installing the exact headers of the running kernel
and updating kernel and headers together (then asking for a restart), and
finally rebuilds the DKMS modules for the running kernel.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

MODULES_ROOT = Path("/usr/lib/modules")
DKMS_ROOT = Path("/var/lib/dkms")
OS_RELEASE = Path("/etc/os-release")
OSTREE_BOOTED = Path("/run/ostree-booted")

OK = "ok"                          # headers match, every DKMS module is built
MISSING = "missing"                # no headers for the running kernel
MISMATCH = "mismatch"              # headers installed, for another version
MODULES_MISSING = "modules-missing"  # headers fine, some DKMS module not built
REBOOT_PENDING = "reboot-pending"  # the running kernel was replaced on disk
NOT_APPLICABLE = "not-applicable"  # immutable system or unknown package manager

ARCH, FEDORA, DEBIAN = "pacman", "dnf", "apt"


def _os_release(path: Path = OS_RELEASE) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key:
                values[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return values


def package_manager(os_release: Path = OS_RELEASE, ostree_booted: Path = OSTREE_BOOTED) -> str:
    """pacman, dnf or apt for a system where the repair applies; "" otherwise.

    Immutable systems (SteamOS, Bazzite and Fedora Atomic) are left out: their
    kernel and headers come with the image, not from a package install.
    """
    release = _os_release(os_release)
    distro = release.get("ID", "").lower()
    family = {distro, *release.get("ID_LIKE", "").lower().split()}
    if distro == "steamos" or ostree_booted.exists():
        return ""
    if family & {"arch", "archlinux"}:
        return ARCH
    if family & {"fedora", "rhel", "centos"}:
        return FEDORA
    if family & {"debian", "ubuntu"}:
        return DEBIAN
    return ""


def _ubuntu_like(os_release: Path = OS_RELEASE) -> bool:
    release = _os_release(os_release)
    return "ubuntu" in {release.get("ID", "").lower(), *release.get("ID_LIKE", "").lower().split()}


def _run(*command: str) -> str:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=10, check=False,
            env={**os.environ, "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _arch_versions(kernel: str, modules_root: Path) -> tuple[str, str, str]:
    """(kernel package, its version, installed headers version) on pacman."""
    owner = _run("pacman", "-Qqo", str(modules_root / kernel / "vmlinuz"))
    if not owner:
        return "", "", ""
    kernel_version = _run("pacman", "-Q", owner).split(" ")[-1]
    headers_version = _run("pacman", "-Q", f"{owner}-headers").split(" ")[-1]
    return owner, kernel_version, headers_version


def unbuilt_dkms_modules(kernel: str, dkms_root: Path = DKMS_ROOT) -> tuple[str, ...]:
    """DKMS modules registered on this system with no build for ``kernel``."""
    missing: list[str] = []
    try:
        modules = sorted(entry for entry in dkms_root.iterdir() if entry.is_dir())
    except OSError:
        return ()
    for module in modules:
        try:
            versions = [
                entry for entry in module.iterdir()
                if entry.is_dir() and not entry.is_symlink() and not entry.name.startswith(("kernel-", "source"))
            ]
        except OSError:
            continue
        if versions and not any((version / kernel).is_dir() for version in versions):
            missing.append(module.name)
    return tuple(missing)


def headers_state(
    kernel: str | None = None,
    *,
    modules_root: Path = MODULES_ROOT,
    dkms_root: Path = DKMS_ROOT,
    os_release: Path = OS_RELEASE,
    ostree_booted: Path = OSTREE_BOOTED,
) -> dict:
    """``{"state", "manager", "kernel", "kernel_package", "headers", "modules"}``. Read-only."""
    kernel = kernel or os.uname().release
    manager = package_manager(os_release, ostree_booted)
    result = {"state": NOT_APPLICABLE, "manager": manager, "kernel": kernel,
              "kernel_package": "", "headers": "", "modules": ()}
    if not manager:
        return result
    if not (modules_root / kernel).is_dir():
        # An update replaced the running kernel; its modules are gone from disk.
        result["state"] = REBOOT_PENDING
        return result
    if manager == ARCH:
        owner, kernel_version, headers_version = _arch_versions(kernel, modules_root)
        result["kernel_package"] = f"{owner} {kernel_version}".strip()
        result["headers"] = f"{owner}-headers {headers_version}" if headers_version else ""
    if not (modules_root / kernel / "build").exists():
        result["state"] = MISMATCH if result["headers"] else MISSING
        return result
    unbuilt = unbuilt_dkms_modules(kernel, dkms_root)
    result["modules"] = unbuilt
    result["state"] = MODULES_MISSING if unbuilt else OK
    return result


def _arch_steps() -> list[str]:
    return [
        'bc250_owner="$(pacman -Qqo "/usr/lib/modules/$bc250_kernel/vmlinuz" 2>/dev/null || true)"',
        'if [ -z "$bc250_owner" ]; then echo "The running kernel $bc250_kernel is no longer installed: an update '
        'replaced it. Restart the computer to use the installed kernel, then check again."; exit 3; fi',
        'bc250_kver="$(pacman -Q "$bc250_owner" | awk \'{print $2}\')"',
        'bc250_hver="$(pacman -Q "$bc250_owner-headers" 2>/dev/null | awk \'{print $2}\' || true)"',
        'bc250_repo="$(LC_ALL=C pacman -Si "$bc250_owner-headers" 2>/dev/null | awk -F\': \' \'/^Version/{print $2; exit}\' || true)"',
        'echo "Kernel package: $bc250_owner $bc250_kver · headers installed: ${bc250_hver:-none} · in the repository: ${bc250_repo:-none}"',
        'if bc250_build_ok && [ "$bc250_hver" = "$bc250_kver" ]; then',
        '  echo "The headers already match the running kernel."',
        'elif [ -n "$bc250_repo" ] && [ "$bc250_repo" = "$bc250_kver" ]; then',
        '  echo "Installing the headers of the running kernel ($bc250_kver)..."',
        '  sudo pacman -S --noconfirm "$bc250_owner-headers" || exit 1',
        'else',
        '  echo "The repository has a newer $bc250_owner. Updating the whole system so the kernel and its headers '
        'match (a partial update is what breaks them)..."',
        '  sudo pacman -Syu --noconfirm || exit 1',
        '  [ "$(pacman -Q "$bc250_owner" | awk \'{print $2}\')" = "$bc250_kver" ] || bc250_newer=1',
        '  pacman -Q "$bc250_owner-headers" >/dev/null 2>&1 || sudo pacman -S --needed --noconfirm "$bc250_owner-headers" || exit 1',
        'fi',
    ]


def _fedora_steps() -> list[str]:
    return [
        'if rpm -q "kernel-devel-$bc250_kernel" >/dev/null 2>&1 && bc250_build_ok; then',
        '  echo "kernel-devel-$bc250_kernel is installed."',
        'elif sudo dnf install -y "kernel-devel-$bc250_kernel"; then',
        '  echo "Installed the headers of the running kernel."',
        'else',
        '  echo "kernel-devel-$bc250_kernel is no longer in the repositories. Updating the kernel and its headers together..."',
        '  sudo dnf upgrade -y --refresh kernel kernel-core kernel-modules kernel-devel || exit 1',
        '  bc250_newer=1',
        'fi',
    ]


def _debian_steps(ubuntu: bool) -> list[str]:
    meta = "linux-generic" if ubuntu else "linux-image-amd64 linux-headers-amd64"
    return [
        'if dpkg-query -W -f=\'${Status}\' "linux-headers-$bc250_kernel" 2>/dev/null | grep -q "install ok installed" '
        '&& bc250_build_ok; then',
        '  echo "linux-headers-$bc250_kernel is installed."',
        'else',
        '  sudo apt-get update || exit 1',
        '  if apt-cache show "linux-headers-$bc250_kernel" >/dev/null 2>&1; then',
        '    sudo apt-get install -y "linux-headers-$bc250_kernel" || exit 1',
        '  else',
        '    echo "linux-headers-$bc250_kernel is no longer in the repositories. Installing the current kernel with its headers..."',
        f'    sudo apt-get install -y {meta} || exit 1',
        '    bc250_newer=1',
        '  fi',
        'fi',
    ]


def repair_command(manager: str | None = None, *, os_release: Path = OS_RELEASE) -> str:
    """The terminal workflow: matching headers, then DKMS rebuilt for the running kernel."""
    manager = manager if manager is not None else package_manager(os_release)
    steps = {ARCH: _arch_steps, FEDORA: _fedora_steps}.get(manager)
    if manager == DEBIAN:
        body = _debian_steps(_ubuntu_like(os_release))
    elif steps is not None:
        body = steps()
    else:
        raise ValueError("Kernel headers are not managed on this system")
    return "\n".join((
        "set -u",
        'bc250_kernel="$(uname -r)"',
        "bc250_newer=0",
        'bc250_build_ok() { [ -e "/usr/lib/modules/$bc250_kernel/build/Makefile" ]; }',
        'echo "== Kernel headers and DKMS modules for $bc250_kernel =="',
        *body,
        'if bc250_build_ok; then',
        '  if command -v dkms >/dev/null 2>&1; then',
        '    echo "Building the DKMS modules for $bc250_kernel..."',
        '    sudo dkms autoinstall -k "$bc250_kernel" || echo "WARNING: some DKMS modules did not build for '
        '$bc250_kernel; dkms status lists them."',
        '  fi',
        '  echo "OK: the running kernel has its headers and its DKMS modules."',
        '  exit 0',
        'fi',
        'if [ "$bc250_newer" = 1 ]; then',
        '  echo "OK: the kernel and its headers were updated together, and the DKMS modules were built for the '
        'new kernel. Restart the computer to finish."',
        '  exit 0',
        'fi',
        'echo "ERROR: the headers of $bc250_kernel are still missing. Update the system, restart and check again."',
        "exit 2",
    ))
