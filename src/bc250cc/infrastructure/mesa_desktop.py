"""Where the BC-250 desktop is still drawn by the CPU, and the way out.

Measured on a real BC-250 with the distributions' own images: Vulkan (RADV)
recognizes the GPU from Mesa 25.2, but the OpenGL the desktop draws with
(radeonsi, used by KWin and Mutter) only does from Mesa 26.1. Ubuntu 24.04 to
26.04 (Mesa 25.2 to 26.0) and Fedora 43 (Mesa 25.3) therefore run games on the
GPU and the desktop on llvmpipe. Debian has its own route in
``debian_kernel_upgrade``.

* Ubuntu and its derivatives: the ``kisak/kisak-mesa`` PPA carries Mesa 26.2 for
  every supported release. It is a third-party source, so the workflow does not
  trust it blindly: the signing key it fetches has to match the fingerprint
  pinned here, or nothing is written.
* Fedora: the release itself moves to Mesa 26.1 with Fedora 44. There is nothing
  to install, so this only tells the person.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path

from .debian_kernel_upgrade import MESA_MIN, MESA_PACKAGES
from .gfx1013_source import kernel_version

OS_RELEASE = Path("/etc/os-release")
PPA = "ppa:kisak/kisak-mesa"
PPA_URI = "https://ppa.launchpadcontent.net/kisak/kisak-mesa/ubuntu/"
#: The PPA's signing key, as Launchpad publishes it for ~kisak/kisak-mesa. Pinned
#: the way the other reviewed sources are: a different key is refused.
PPA_FINGERPRINT = "EB8B81E14DA65431D7504EA8F63F0F2B90935439"
PPA_KEY_URL = f"https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x{PPA_FINGERPRINT}"
SOURCE_FILE = Path("/etc/apt/sources.list.d/bc250-control-center-kisak-mesa.sources")
KEY_FILE = Path("/etc/apt/keyrings/bc250-control-center-kisak-mesa.asc")
#: Ubuntu itself and the derivatives that take Ubuntu's archive (the PPA needs its codename).
UBUNTU_IDS = frozenset({"ubuntu", "linuxmint", "pop", "zorin", "elementary", "neon"})
ACTIONS = frozenset({"install"})
#: Fedora 44 is the first release whose Mesa is new enough.
FEDORA_RELEASE = 44
#: 32-bit Mesa, only when it is installed (Steam): apt keeps both architectures at one version.
MESA_PACKAGES_32 = tuple(f"{name}:i386" for name in MESA_PACKAGES)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def os_release_fields(text: str | None = None) -> dict[str, str]:
    """The ``KEY=value`` lines of /etc/os-release, unquoted."""
    content = _read(OS_RELEASE) if text is None else text
    fields = {}
    for line in content.splitlines():
        match = re.fullmatch(r'([A-Z_]+)=(?:"([^"]*)"|\'([^\']*)\'|(.*))', line.strip())
        if match:
            fields[match.group(1)] = next((group for group in match.groups()[1:] if group is not None), "")
    return fields


def ubuntu_codename(fields: dict[str, str] | None = None) -> str:
    """The Ubuntu release a derivative is built on (``UBUNTU_CODENAME``), else its own codename."""
    fields = os_release_fields() if fields is None else fields
    return (fields.get("UBUNTU_CODENAME") or fields.get("VERSION_CODENAME") or "").strip().lower()


def installed_mesa_version(family: str) -> str:
    """The installed Mesa's package version, empty when the package manager cannot tell."""
    command = (
        ["rpm", "-q", "--qf", "%{VERSION}", "mesa-dri-drivers"]
        if family == "fedora" else
        ["dpkg-query", "-W", "-f=${Version}", "libgl1-mesa-dri"]
    )
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def mesa_desktop_state(
    *,
    family: str,
    distro_id: str = "",
    id_like: str | None = None,
    mesa_version: str | None = None,
    immutable: bool = False,
    debian_upgrade: dict | None = None,
    fields: dict[str, str] | None = None,
) -> dict:
    """Read-only: whether this system draws its desktop on the CPU for want of Mesa 26.1.

    ``route`` is ``ppa`` (Ubuntu and derivatives), ``backports`` (Debian, when the
    kernel is already fine) or ``release`` (Fedora: upgrade the release). Only
    ``ppa`` and ``backports`` have something to run.
    """
    family = str(family or "").strip().lower()
    distro_id = str(distro_id or "").strip().lower()
    fields = os_release_fields() if fields is None else fields
    id_like = fields.get("ID_LIKE", "") if id_like is None else str(id_like)
    if mesa_version is None:
        mesa_version = installed_mesa_version(family) if family in {"debian", "fedora"} else ""
    mesa_version = str(mesa_version).strip()
    series = kernel_version(mesa_version)
    old = series is not None and series < MESA_MIN
    route, action, reason = "", "", ""
    if immutable:
        reason = "Image-based systems update Mesa with the image."
    elif family not in {"debian", "fedora"}:
        reason = "No route is offered for this distribution."
    elif series is None:
        reason = "The installed Mesa version could not be read."
    elif not old:
        reason = "Mesa is already new enough."
    elif distro_id in UBUNTU_IDS or "ubuntu" in id_like.split():
        route, action = "ppa", "mesa_ppa_install"
    elif distro_id == "fedora":
        route = "release"
    elif distro_id == "debian" or (family == "debian" and not distro_id):
        upgrade = debian_upgrade or {}
        # Debian: the card of the kernel and Mesa already covers a kernel to install.
        if upgrade.get("install_mesa") and not upgrade.get("install_kernel"):
            route, action = "backports", "debian_kernel_install"
        else:
            reason = "Debian's own card handles this."
    else:
        reason = "No route is offered for this distribution."
    return {
        "offered": bool(route),
        "route": route,
        "action": action,
        "reason": reason,
        "mesa": mesa_version,
        "minimum": f"{MESA_MIN[0]}.{MESA_MIN[1]}",
        "codename": ubuntu_codename(fields) if route == "ppa" else "",
    }


def build_mesa_ppa_command(action: str, codename: str, *, source: Path = SOURCE_FILE, key: Path = KEY_FILE) -> str:
    """The closed shell workflow for the embedded terminal.

    The PPA is added in a file of its own with its key beside it (delete both to
    undo), and only after the key's fingerprint matches the pinned one and the
    PPA publishes for this release. Mesa and, when present, its 32-bit libraries
    are simulated first, so a combination apt cannot resolve changes nothing.
    """
    action = str(action or "").strip().lower()
    if action not in ACTIONS:
        raise ValueError(f"Unsupported Mesa action: {action or '--'}")
    codename = str(codename or "").strip().lower()
    if not re.fullmatch(r"[a-z]+", codename):
        raise ValueError("Unsupported Mesa action: the Ubuntu release is unknown")
    quoted_source, quoted_key = shlex.quote(str(source)), shlex.quote(str(key))
    packages = " ".join(MESA_PACKAGES)
    packages32 = " ".join(MESA_PACKAGES_32)
    release_url = f"{PPA_URI}dists/{codename}/InRelease"
    return "\n".join((
        "set -Eeuo pipefail",
        'echo; echo "=========================================================================="',
        'echo "  BC-250 · newer Mesa from the kisak-mesa PPA"',
        'echo "=========================================================================="; echo',
        'echo "[INFO] ppa:kisak/kisak-mesa is a third-party source. It is added in its own file, with its key checked first."',
        "sudo -v",
        "sudo apt-get install -y curl gnupg ca-certificates",
        f'curl -fsI {shlex.quote(release_url)} >/dev/null || '
        f'{{ echo "ERROR: the kisak-mesa PPA has no packages for {codename}."; exit 29; }}',
        # Skip the key and the source when the PPA is already set up (add-apt-repository or by hand).
        'if ! grep -rqsE "ppa\\.launchpadcontent\\.net/kisak/kisak-mesa" /etc/apt/sources.list /etc/apt/sources.list.d; then',
        '  bc250_key="$(mktemp)"; trap \'rm -f -- "$bc250_key"\' EXIT',
        f"  curl -fsSL {shlex.quote(PPA_KEY_URL)} -o \"$bc250_key\"",
        '  bc250_fpr="$(gpg --show-keys --with-colons "$bc250_key" 2>/dev/null | awk -F: \'/^fpr/ {print $10; exit}\')"',
        f'  [ "$bc250_fpr" = {PPA_FINGERPRINT} ] || '
        '{ echo "ERROR: the signing key is $bc250_fpr, not the pinned one. Nothing was added."; exit 30; }',
        f'  sudo install -D -m 0644 "$bc250_key" {quoted_key}',
        f"  printf 'Types: deb\\nURIs: {PPA_URI}\\nSuites: {codename}\\nComponents: main\\n"
        f"Signed-By: {key}\\n' | sudo tee {quoted_source} >/dev/null",
        f'  echo "[INFO] Added {source} and its key. Delete both to undo."',
        "fi",
        "sudo apt-get update",
        f'packages="{packages}"',
        # Steam's 32-bit Mesa has to move with the 64-bit one.
        "if dpkg-query -W libgl1-mesa-dri:i386 >/dev/null 2>&1; then",
        f'  packages="$packages {packages32}"',
        "fi",
        'if ! apt-get install -s $packages >/dev/null 2>&1; then',
        '  echo "ERROR: apt cannot install the newer Mesa together with what is installed. Nothing was changed."',
        '  echo "       Details: apt-get install -s $packages"',
        "  exit 29",
        "fi",
        f'mesa_candidate="$(apt-cache policy {MESA_PACKAGES[1]} | awk \'/Candidate:/ {{print $2; exit}}\')"',
        f'dpkg --compare-versions "$mesa_candidate" ge {".".join(str(part) for part in MESA_MIN)} || '
        f'{{ echo "ERROR: the newest Mesa on offer is $mesa_candidate, older than {".".join(str(part) for part in MESA_MIN)}."; exit 29; }}',
        'echo "[INFO] Installing Mesa $mesa_candidate."',
        "sudo apt-get install -y $packages",
        'echo; echo "[OK] Done. Restart to use it."',
        'echo "[INFO] Check the desktop graphics with: eglinfo -B | grep renderer (package mesa-utils-extra)."',
        # Once the source is gone, -t does not lower an installed version: name the archive per package.
        'bc250_back=""; for bc250_name in $packages; do bc250_back="$bc250_back $bc250_name/' + codename + '-updates"; done',
        f'echo "[INFO] To go back: delete {source} and {key}, run sudo apt-get update, then:"',
        'echo "       sudo apt-get install --allow-downgrades$bc250_back"',
    ))
