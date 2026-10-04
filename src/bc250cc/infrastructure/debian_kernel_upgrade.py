"""A newer kernel for Debian, from the release's own backports.

Debian 13 ships linux 6.12 and Mesa 25.0, and neither knows the BC-250 GPU
(GFX1013): Mesa reports ``unknown (family_id, chip_external_rev)`` and the whole
desktop falls back to llvmpipe, software rendering on the CPU. The GFX1013
source build needs linux 6.14 or newer, which Debian only offers through
``<release>-backports``. This module reads where the system stands and builds
the one reviewable shell workflow, run in the embedded terminal, that adds that
suite and installs the backports kernel beside the stock one.

The stock kernel stays installed and stays in the boot menu, so a kernel that
does not suit the machine is one menu entry away from being left behind.
"""

from __future__ import annotations

import re
import shlex
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


def debian_kernel_upgrade_state(
    *,
    family: str,
    distro_id: str = "",
    kernel: str = "",
    codename: str | None = None,
    boot_dir: Path | None = None,
    immutable: bool = False,
) -> dict:
    """Read-only: whether the backports kernel is the way out, and where it stands.

    ``state`` is ``available`` (nothing newer installed), ``reboot-required``
    (a new enough kernel is installed but not running) or ``not-offered``.
    """
    family = str(family or "").strip().lower()
    distro_id = str(distro_id or "").strip().lower()
    codename = os_release_codename() if codename is None else str(codename).strip().lower()
    running = kernel_version(kernel)
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
    elif running >= MIN_KERNEL:
        reason = "The running kernel is already new enough."
    elif codename not in SUPPORTED_CODENAMES:
        reason = "This Debian release has no backports kernel new enough."
    offered = not reason
    state = "not-offered"
    if offered:
        newer = any(version >= MIN_KERNEL for version in installed_kernel_versions(boot_dir))
        state = "reboot-required" if newer else "available"
    return {
        "offered": offered,
        "state": state,
        "reason": reason,
        "kernel": str(kernel or ""),
        "codename": codename,
        "minimum": f"{MIN_KERNEL[0]}.{MIN_KERNEL[1]}",
    }


def build_debian_kernel_command(action: str, codename: str, *, source: Path = SOURCE_FILE) -> str:
    """The closed shell workflow for the embedded terminal.

    Nothing is removed. The backports suite is added in a file of its own (delete
    it to undo), the kernel comes from it explicitly, and a backports kernel
    that is not new enough stops the run before anything is installed.
    """
    action = str(action or "").strip().lower()
    if action not in ACTIONS:
        raise ValueError(f"Unsupported Debian kernel action: {action or '--'}")
    codename = str(codename or "").strip().lower()
    if codename not in SUPPORTED_CODENAMES:
        raise ValueError("This Debian release has no backports kernel new enough.")
    suite = f"{codename}-backports"
    minimum = ".".join(str(part) for part in MIN_KERNEL)
    quoted_source = shlex.quote(str(source))
    packages = " ".join(PACKAGES)
    return "\n".join((
        "set -Eeuo pipefail",
        'echo; echo "=========================================================================="',
        'echo "  BC-250 · newer kernel from Debian backports"',
        'echo "=========================================================================="; echo',
        'echo "[INFO] Debian keeps its current kernel installed and in the boot menu."',
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
        f'candidate="$(apt-cache madison linux-image-amd64 | awk \'/{suite}/ {{print $3; exit}}\')"',
        f'test -n "$candidate" || {{ echo "ERROR: {suite} offers no linux-image-amd64."; exit 29; }}',
        f'dpkg --compare-versions "$candidate" ge {minimum} || '
        f'{{ echo "ERROR: the backports kernel $candidate is older than {minimum}."; exit 29; }}',
        f'packages="{packages}"',
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
        f"sudo apt-get install -y -t {suite} $packages",
        'echo; echo "[OK] Done. Restart, then check the kernel with: uname -r"',
        'echo "[INFO] The previous kernel stays in the boot menu (Advanced options)."',
    ))
