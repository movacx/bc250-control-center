"""Prepare the patched pahole required by MastaG's LTO kernel headers."""

from __future__ import annotations

import re
import shlex
import subprocess
import tarfile
from pathlib import Path

from .external_tools.catalog import EXTERNAL_TOOLS

PAHOLE_VERSION = "1:1.32-2"
PAHOLE_FILES = {
    "PKGBUILD": "fb30baf67d6cb88dd6839e5cd354daf3127a55b15b3f9c9d3e570b6f407d9468",
    "0001-CMakeLists.txt-Install-ostra.py-into-Python3_SITELIB.patch": "da917bf681672da406ca599ed3d19f891906de5afdbdca8180c71958e0c209a6",
    "0002-dwarf_loader-Take-the-merged-CU-language-from-a-CU-t.patch": "c9b1c220d839280719802e71086f11e8ebe346c212efcb7995eda2749c87581f",
    "0003-dwarf_loader-Load-types-that-kept-CUs-use-from-exclu.patch": "b58b36951c89fd1d4ccc40c799b1761fdcc213064fe7bb83d4531467cdd55391",
}
PAHOLE_SIGNING_KEY = "2DBF5BAA46FB4DED338A335BD65016F35352AA40"
DEPENDENCY_NOTE = (
    "These kernel headers need CachyOS's patched pahole. Prepare dependencies "
    "builds and installs it from the official CachyOS recipe. This updates system "
    "packages and can take a few minutes. Then retry the kernel installation."
)


def kernel_pahole_requirement(database: Path = Path("/var/lib/pacman/sync/bc250-cachyos.db")) -> str:
    """Read the actual stable-header dependency from the last synced database."""
    try:
        with tarfile.open(database) as archive:
            for entry in archive:
                if not (entry.isfile() and entry.name.startswith("linux-cachyos-bc250-headers-")
                        and entry.name.endswith("/desc") and entry.size < 65536):
                    continue
                source = archive.extractfile(entry)
                if source is None:
                    continue
                text = source.read().decode("utf-8")
                if "%DEPENDS%\n" not in text:
                    continue
                section = text.split("%DEPENDS%\n", 1)[1].split("\n\n", 1)[0]
                for line in section.splitlines():
                    if re.fullmatch(r"pahole>=[0-9][0-9A-Za-z.:+_-]*", line):
                        return line
    except (OSError, UnicodeError, tarfile.TarError):
        pass
    return ""


def pahole_dependency_state() -> dict:
    requirement = kernel_pahole_requirement()
    if not requirement:
        return {"requirement": "", "ready": True}
    try:
        result = subprocess.run(
            ["pacman", "-T", requirement], capture_output=True, text=True, timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return {"requirement": requirement, "ready": False}
    return {"requirement": requirement, "ready": result.returncode == 0}


def build_pahole_prepare_command() -> str:
    tool = EXTERNAL_TOOLS["cachyos_pahole"]
    base = f"https://raw.githubusercontent.com/CachyOS/CachyOS-PKGBUILDS/{tool.reviewed_revision}/pahole"
    downloads = []
    for name, digest in PAHOLE_FILES.items():
        downloads += [
            f"curl --fail --location --proto '=https' --retry 2 --output {shlex.quote(name)} {shlex.quote(base + '/' + name)}",
            f"printf '%s  %s\\n' {digest} {shlex.quote(name)} | sha256sum --check --status",
        ]
    download_script = "\n".join(downloads)
    requirement = shlex.quote(kernel_pahole_requirement() or f"pahole>={PAHOLE_VERSION}")
    return f'''set -Eeuo pipefail
export LANG=C LC_ALL=C
. /etc/os-release
case "${{ID:-}}" in arch|cachyos|cachy) ;; *) echo 'ERROR: This preparation is for Arch/CachyOS.'; exit 64 ;; esac
test "$(id -u)" != 0 || {{ echo 'ERROR: Run this preparation as your normal desktop user.'; exit 77; }}
test "$(uname -m)" = x86_64 || {{ echo 'ERROR: This package needs x86_64.'; exit 64; }}
bc250_requirement={requirement}
if pacman -T "$bc250_requirement" >/dev/null 2>&1; then
  echo 'OK: The kernel dependency is already ready. Retry the kernel installation.'
  exit 0
fi
echo '== Preparing the kernel dependency: patched pahole =='
echo 'Source: {tool.upstream} @ {tool.reviewed_revision}'
echo 'The system packages are updated first; BC-250 kernels and Mesa are held during this preparation.'
sudo pacman -Syu --needed --noconfirm --ignore 'linux-cachyos*-bc250*,mesa*,lib32-mesa*,vulkan-*,lib32-vulkan-*,opencl-mesa,lib32-opencl-mesa' base-devel curl git gnupg
if pacman -T "$bc250_requirement" >/dev/null 2>&1; then
  echo 'OK: The system update supplied the kernel dependency. Retry the kernel installation.'
  exit 0
fi
bc250_minimum="${{bc250_requirement#pahole>=}}"
if [ "$(vercmp {shlex.quote(PAHOLE_VERSION)} "$bc250_minimum")" -lt 0 ]; then
  echo 'ERROR: These headers need a newer pahole than this reviewed recipe. Update Control Center before preparing it.'
  exit 69
fi
umask 077
mkdir -p "${{XDG_CACHE_HOME:-$HOME/.cache}}/bc250-control-center"
bc250_work="$(mktemp -d "${{XDG_CACHE_HOME:-$HOME/.cache}}/bc250-control-center/pahole.XXXXXX")"
trap 'rm -rf -- "$bc250_work"' EXIT
cd "$bc250_work"
{download_script}
export GNUPGHOME="$bc250_work/gnupg"
mkdir -m 0700 "$GNUPGHOME"
gpg --batch --keyserver hkps://keyserver.ubuntu.com --recv-keys {PAHOLE_SIGNING_KEY}
echo '== Building the reviewed package as the desktop user =='
makepkg --syncdeps --noconfirm
bc250_package=''
while IFS= read -r candidate; do
  if [ "$(pacman -Qpq "$candidate")" = pahole ]; then
    bc250_package="$candidate"
    break
  fi
done < <(makepkg --packagelist)
test -n "$bc250_package" && test -f "$bc250_package" || {{ echo 'ERROR: The build did not produce the pahole package.'; exit 69; }}
test "$(pacman -Qp "$bc250_package" | awk '{{print $2}}')" = {shlex.quote(PAHOLE_VERSION)} || {{ echo 'ERROR: The built package has an unexpected version.'; exit 69; }}
sudo pacman -U --noconfirm -- "$bc250_package"
pacman -T "$bc250_requirement" || {{ echo 'ERROR: The kernel dependency is still unavailable.'; exit 69; }}
echo 'OK: The kernel dependency is ready. Press Update / repair kernel, or retry your chosen kernel installation.'
'''
