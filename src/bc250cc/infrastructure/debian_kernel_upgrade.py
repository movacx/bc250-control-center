"""A newer kernel and Mesa for Debian, from the release's own backports.

Debian 13 ships linux 6.12 and Mesa 25.0, and neither knows the BC-250 GPU
(GFX1013): Mesa reports ``unknown (family_id, chip_external_rev)`` and the whole
desktop falls back to llvmpipe, software rendering on the CPU. Checked on a
real BC-250 under a 7.1 kernel: Mesa 25.0.7 from stable still renders on
llvmpipe, and Mesa 26.1.6 from ``trixie-backports`` drives the GPU (radeonsi
and RADV GFX1013). So Mesa is what ends the software rendering; a newer kernel
is what the GFX1013 source build needs (linux 6.14 or newer, which Debian only
offers through ``<release>-backports``).

This module reads where the system stands and builds the one reviewable shell
workflow, run in the embedded terminal, that adds that suite and installs what
is missing from it. The stock kernel stays installed and stays in the boot
menu, so a kernel that does not suit the machine is one menu entry away from
being left behind.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path

from .gfx1013_source import MIN_KERNEL, kernel_version

#: Debian releases whose backports carry a kernel new enough (6.14 or later).
#: Debian 12 backports stop below that, so it is not offered a route that
#: cannot work.
SUPPORTED_CODENAMES = frozenset({"trixie"})
SOURCE_FILE = Path("/etc/apt/sources.list.d/bc250-control-center-backports.sources")
BOOT_DIR = Path("/boot")
OS_RELEASE = Path("/etc/os-release")
ACTIONS = frozenset({"install"})
#: Meta packages: the kernel, its headers (the GFX1013 build compiles a module
#: for the running kernel) and the GPU firmware, which has to follow a newer
#: kernel.
PACKAGES = ("linux-image-amd64", "linux-headers-amd64", "firmware-amd-graphics")
#: The Mesa that draws the desktop (OpenGL, EGL) and runs games (Vulkan). Their
#: shared pieces (mesa-libgallium and the like) follow through dependencies.
MESA_PACKAGES = ("mesa-vulkan-drivers", "libgl1-mesa-dri", "libglx-mesa0", "libegl-mesa0", "libgbm1")
#: The package whose version tells which Mesa the desktop runs on.
MESA_PROBE = "libgl1-mesa-dri"
#: The first Mesa series whose OpenGL (radeonsi, what the desktop draws with)
#: recognizes the BC-250. Checked on a real board: 25.0, 25.2, 25.3 and 26.0.8
#: leave the desktop on llvmpipe (Vulkan/RADV works from 25.2), 26.1.6 and
#: 26.2.4 drive it.
MESA_MIN = (26, 1)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def os_release_codename(text: str | None = None) -> str:
    """``VERSION_CODENAME`` of /etc/os-release, empty when absent."""
    content = _read(OS_RELEASE) if text is None else text
    match = re.search(r'^VERSION_CODENAME="?([A-Za-z0-9._-]+)"?\s*$', content, re.MULTILINE)
    return match.group(1).lower() if match else ""


def installed_kernel_versions(boot_dir: Path | None = None) -> list[tuple[int, int]]:
    """``(major, minor)`` of every kernel image in /boot."""
    versions = []
    try:
        images = sorted((boot_dir or BOOT_DIR).glob("vmlinuz-*"))
    except OSError:
        return []
    for image in images:
        parsed = kernel_version(image.name.removeprefix("vmlinuz-"))
        if parsed is not None:
            versions.append(parsed)
    return versions


def installed_mesa_version() -> str:
    """The installed Mesa's package version, empty when dpkg cannot tell."""
    try:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Version}", MESA_PROBE],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def debian_kernel_upgrade_state(
    *,
    family: str,
    distro_id: str = "",
    kernel: str = "",
    codename: str | None = None,
    boot_dir: Path | None = None,
    immutable: bool = False,
    mesa_version: str | None = None,
) -> dict:
    """Read-only: whether backports is the way out, and what it still has to install.

    ``state`` is ``available`` (a kernel or a Mesa is still to install),
    ``reboot-required`` (a new enough kernel is installed but not running, and
    nothing else is missing) or ``not-offered``. ``install_kernel`` and
    ``install_mesa`` say which part the workflow has to bring.
    """
    family = str(family or "").strip().lower()
    distro_id = str(distro_id or "").strip().lower()
    codename = os_release_codename() if codename is None else str(codename).strip().lower()
    mesa_version = installed_mesa_version() if mesa_version is None else str(mesa_version).strip()
    running = kernel_version(kernel)
    mesa_series = kernel_version(mesa_version)
    kernel_old = running is not None and running < MIN_KERNEL
    mesa_old = codename in SUPPORTED_CODENAMES and mesa_series is not None and mesa_series < MESA_MIN
    reason = ""
    # Only Debian itself has this suite: Ubuntu, Mint and Pop!_OS name their
    # newer kernels differently, and each of them needs its own route.
    if distro_id != "debian" and not (family == "debian" and not distro_id):
        reason = "Only Debian offers this route."
    elif immutable:
        reason = "Image-based systems cannot take another kernel this way."
    elif "bc250" in str(kernel or "").lower():
        reason = "This BC-250 kernel is already in use."
    elif running is None:
        reason = "The running kernel version could not be read."
    elif codename not in SUPPORTED_CODENAMES:
        reason = (
            "This Debian release has no backports kernel new enough."
            if kernel_old else "The running kernel is already new enough."
        )
    elif not kernel_old and not mesa_old:
        reason = "The running kernel is already new enough."
    offered = not reason
    state = "not-offered"
    install_kernel = False
    if offered:
        newer = any(version >= MIN_KERNEL for version in installed_kernel_versions(boot_dir))
        install_kernel = kernel_old and not newer
        state = "available" if install_kernel or mesa_old else "reboot-required"
    return {
        "offered": offered,
        "state": state,
        "reason": reason,
        "kernel": str(kernel or ""),
        "codename": codename,
        "minimum": f"{MIN_KERNEL[0]}.{MIN_KERNEL[1]}",
        "install_kernel": install_kernel,
        "install_mesa": offered and mesa_old,
        "mesa": mesa_version,
    }


def build_debian_kernel_command(
    action: str,
    codename: str,
    *,
    source: Path = SOURCE_FILE,
    kernel: bool = True,
    mesa: bool = True,
) -> str:
    """The closed shell workflow for the embedded terminal.

    Nothing is removed. The backports suite is added in a file of its own (delete
    it to undo), what is installed comes from it explicitly, and a backports
    kernel or Mesa that is not new enough is left out. A kernel that cannot be
    had stops the run before anything is installed; a Mesa that cannot be had
    only stops it when it was the one thing asked for.
    """
    action = str(action or "").strip().lower()
    if action not in ACTIONS:
        raise ValueError(f"Unsupported Debian kernel action: {action or '--'}")
    codename = str(codename or "").strip().lower()
    if codename not in SUPPORTED_CODENAMES:
        raise ValueError("This Debian release has no backports kernel new enough.")
    if not kernel and not mesa:
        raise ValueError("Unsupported Debian kernel action: nothing to install")
    suite = f"{codename}-backports"
    minimum = ".".join(str(part) for part in MIN_KERNEL)
    mesa_minimum = ".".join(str(part) for part in MESA_MIN)
    quoted_source = shlex.quote(str(source))
    what = "newer kernel and Mesa" if kernel and mesa else "newer kernel" if kernel else "newer Mesa"
    lines = [
        "set -Eeuo pipefail",
        'echo; echo "=========================================================================="',
        f'echo "  BC-250 · {what} from Debian backports"',
        'echo "=========================================================================="; echo',
    ]
    if kernel:
        lines.append('echo "[INFO] Debian keeps its current kernel installed and in the boot menu."')
    lines += [
        "sudo -v",
        # Add the suite in a file of its own, unless some source already has it.
        f'if ! grep -rqsE "^(Suites:.*|deb .*) {suite}( |$)" /etc/apt/sources.list /etc/apt/sources.list.d; then',
        '  test -r /usr/share/keyrings/debian-archive-keyring.gpg || { echo "ERROR: debian-archive-keyring is missing."; exit 29; }',
        "  printf 'Types: deb\\nURIs: http://deb.debian.org/debian\\n"
        f"Suites: {suite}\\nComponents: main non-free-firmware\\n"
        f"Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg\\n' | sudo tee {quoted_source} >/dev/null",
        f'  echo "[INFO] Added {source}. Delete it to undo."',
        "fi",
        "sudo apt-get update",
    ]
    if kernel:
        lines += [
            f'candidate="$(apt-cache madison linux-image-amd64 | awk \'/{suite}/ {{print $3; exit}}\')"',
            f'test -n "$candidate" || {{ echo "ERROR: {suite} offers no linux-image-amd64."; exit 29; }}',
            f'dpkg --compare-versions "$candidate" ge {minimum} || '
            f'{{ echo "ERROR: the backports kernel $candidate is older than {minimum}."; exit 29; }}',
            f'packages="{" ".join(PACKAGES)}"',
            # The meta package follows future backports kernels, but the mirror
            # sometimes publishes it before the packages it depends on. Simulate
            # first, and fall back to the newest complete kernel when it cannot be
            # installed yet.
            f'if apt-get install -s -t {suite} $packages >/dev/null 2>&1; then',
            '  echo "[INFO] Installing kernel $candidate from backports."',
            "else",
            '  echo "[INFO] Kernel $candidate is not complete on the mirror yet. Looking for the newest one that is."',
            '  packages=""',
            "  for image in $(apt-cache pkgnames linux-image- | grep -E '^linux-image-[0-9]+\\.[0-9]+\\.[0-9]+\\+deb[0-9]+-amd64$' | sort -rV); do",
            '    version="${image#linux-image-}"; version="${version%%+*}"',
            f'    dpkg --compare-versions "$version" ge {minimum} || continue',
            '    headers="${image/linux-image-/linux-headers-}"',
            f'    if apt-get install -s -t {suite} "$image" "$headers" >/dev/null 2>&1; then',
            '      packages="$image $headers"; break',
            "    fi",
            "  done",
            f'  test -n "$packages" || {{ echo "ERROR: {suite} has no complete kernel of {minimum} or newer right now. Try again later."; exit 29; }}',
            '  packages="$packages firmware-amd-graphics"',
            '  echo "[INFO] Installing $packages from backports."',
            "fi",
        ]
    else:
        lines.append('packages=""')
    if mesa:
        none_left = (
            '  echo "[WARN] Mesa from ' + suite + ' cannot be installed right now. The kernel is installed anyway: run this again later for Mesa."'
            if kernel else
            f'  echo "ERROR: {suite} has no complete Mesa of {mesa_minimum} or newer right now. Try again later."; exit 29'
        )
        lines += [
            f'mesa="{" ".join(MESA_PACKAGES)}"',
            f"mesa_candidate=\"$(apt-cache madison {MESA_PROBE} | awk '/{suite}/ {{print $3; exit}}')\"",
            'if [ -n "$mesa_candidate" ] && '
            f'dpkg --compare-versions "$mesa_candidate" ge {mesa_minimum} && '
            f'apt-get install -s -t {suite} $mesa >/dev/null 2>&1; then',
            '  echo "[INFO] Installing Mesa $mesa_candidate from backports."',
            '  packages="${packages:+$packages }$mesa"',
            "else",
            none_left,
            "fi",
        ]
    lines.append(f"sudo apt-get install -y -t {suite} $packages")
    lines.append('echo; echo "[OK] Done. Restart to use it."')
    if kernel:
        lines.append('echo "[INFO] Check the kernel with: uname -r. The previous kernel stays in the boot menu (Advanced options)."')
    if mesa:
        lines.append('echo "[INFO] Check the graphics with: vulkaninfo --summary (package vulkan-tools)."')
    return "\n".join(lines)
