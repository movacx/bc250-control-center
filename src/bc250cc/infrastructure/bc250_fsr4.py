"""Official-upstream BC-250 FSR4 V3 lifecycle.

Control Center does not reproduce the FSR4 patches or installer. It updates the
official ``v3`` branch and invokes its installer/uninstaller unchanged. The
local wrapper only enforces platform/hardware scope and restores the previous
per-user runtime if upstream installation fails.
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path

from .source_checkout import clone_or_update_branch

BC250_FSR4_REPOSITORY = "https://github.com/dmorazasanchez/bc250-fsr4"
BC250_FSR4_BRANCH = "v3"
BC250_FSR4_PREFIX = Path.home() / ".local/share/bc250-fsr4/v3"
BC250_FSR4_ICD = BC250_FSR4_PREFIX / "radv-bc250-fsr4-v3.json"
BC250_FSR4_SUPPORTED_FAMILIES = frozenset({"arch", "cachyos"})
BC250_FSR4_EXPERIMENTAL_IDS = frozenset({"manjaro"})


def _fsr4_platform_mode(*, family: str, distro_id: str) -> tuple[bool, bool]:
    normalized_family = str(family or "").strip().lower()
    normalized_id = str(distro_id or "").strip().lower()
    documented = normalized_family in BC250_FSR4_SUPPORTED_FAMILIES and normalized_id in {
        "",
        "arch",
        "cachyos",
        "cachy",
    }
    experimental = normalized_id in BC250_FSR4_EXPERIMENTAL_IDS
    return documented, experimental


def fsr4_runtime_state(family: str, distro_id: str = "") -> dict:
    """Validate the shape of the upstream-managed per-user runtime."""

    library = BC250_FSR4_PREFIX / "libvulkan_radeon.so"
    revision_file = BC250_FSR4_PREFIX / ".bc250-upstream-revision"
    artifacts_present = library.exists() or BC250_FSR4_ICD.exists()
    valid_icd = False
    if (
        library.is_file()
        and not library.is_symlink()
        and BC250_FSR4_ICD.is_file()
        and not BC250_FSR4_ICD.is_symlink()
    ):
        try:
            manifest = json.loads(BC250_FSR4_ICD.read_text(encoding="utf-8"))
            icd = manifest.get("ICD", {})
            valid_icd = (
                manifest.get("file_format_version") == "1.0.0"
                and icd.get("library_path") == str(library)
                and icd.get("api_version") == "1.4.0"
            )
        except (OSError, ValueError, TypeError):
            pass
    revision = ""
    try:
        revision = revision_file.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    current = bool(valid_icd)
    documented, experimental = _fsr4_platform_mode(
        family=family,
        distro_id=distro_id,
    )
    return {
        "repository": BC250_FSR4_REPOSITORY,
        "branch": BC250_FSR4_BRANCH,
        "version": "upstream-v3",
        "upstream_revision": revision,
        "upstream_managed": True,
        "prefix": str(BC250_FSR4_PREFIX),
        "icd": str(BC250_FSR4_ICD),
        "installed": artifacts_present,
        "current": current,
        "state": "ready" if current else "invalid" if artifacts_present else "not-installed",
        "precompiled_supported": documented,
        "experimental_precompiled": experimental,
        "installer_available": documented or experimental,
        "source_build_required": not (documented or experimental),
    }


def build_fsr4_v3_install_command(destination: str | Path) -> str:
    """Update the official V3 branch and run its installer unchanged."""

    destination = Path(destination)
    checkout = clone_or_update_branch(
        BC250_FSR4_REPOSITORY,
        destination,
        BC250_FSR4_BRANCH,
    )
    qdest = shlex.quote(str(destination))
    return f'''set -euo pipefail
echo "== BC-250 FSR4 official upstream V3 workflow =="
test -r /etc/os-release || {{ echo "ERROR: /etc/os-release is unavailable."; exit 64; }}
. /etc/os-release
case "${{ID:-}}" in
  arch|cachyos|cachy) ;;
  manjaro) echo "[WARN] Upstream describes an Arch-style userspace but does not name Manjaro. Its own ABI and Vulkan checks must pass." ;;
  *) echo "ERROR: The upstream precompiled V3 runtime targets CachyOS/Arch-style userspace; other systems must use its source-build path."; exit 64 ;;
esac
command -v git >/dev/null 2>&1 || {{ echo "ERROR: git is required to update the official FSR4 source."; exit 69; }}
command -v lspci >/dev/null 2>&1 || {{ echo "ERROR: lspci (pciutils) is required to verify BC-250 hardware."; exit 69; }}
lspci -Dn | grep -qiE '1002:13fe' || {{ echo "ERROR: AMD BC-250 PCI ID 1002:13FE was not detected."; exit 64; }}
{checkout}
test -f {qdest}/install-v3.sh || {{ echo "ERROR: official upstream install-v3.sh is missing."; exit 29; }}
test -f {qdest}/uninstall-v3.sh || {{ echo "ERROR: official upstream uninstall-v3.sh is missing."; exit 29; }}
test -f {qdest}/bc250-fsr4-v3.patch || {{ echo "ERROR: official upstream V3 patch is missing."; exit 29; }}
bc250_prefix="$HOME/.local/share/bc250-fsr4/v3"
bc250_parent="$HOME/.local/share/bc250-fsr4"
bc250_backup=''
mkdir -p "$bc250_parent"
if test -e "$bc250_prefix"; then
  bc250_backup="$(mktemp -d "$bc250_parent/.v3.backup.XXXXXX")"
  rmdir "$bc250_backup"
  mv -- "$bc250_prefix" "$bc250_backup"
fi
if BC250_FSR4_PREFIX="$bc250_prefix" bash {qdest}/install-v3.sh; then
  test -z "$bc250_backup" || rm -rf -- "$bc250_backup"
else
  bc250_result=$?
  rm -rf -- "$bc250_prefix"
  if test -n "$bc250_backup" && test -e "$bc250_backup"; then
    mv -- "$bc250_backup" "$bc250_prefix"
  fi
  echo "ERROR: The official upstream installer failed; the previous per-user runtime was restored."
  exit "$bc250_result"
fi
git -C {qdest} rev-parse HEAD > "$bc250_prefix/.bc250-upstream-revision"
echo "OK: official upstream FSR4 V3 installed per-user at revision $(cat "$bc250_prefix/.bc250-upstream-revision")."'''


def build_fsr4_v3_uninstall_command(destination: str | Path) -> str:
    """Update upstream and invoke its official uninstall script."""

    destination = Path(destination)
    checkout = clone_or_update_branch(
        BC250_FSR4_REPOSITORY,
        destination,
        BC250_FSR4_BRANCH,
    )
    qdest = shlex.quote(str(destination))
    return f'''set -euo pipefail
command -v git >/dev/null 2>&1 || {{ echo "ERROR: git is required to update the official FSR4 source."; exit 69; }}
{checkout}
test -f {qdest}/uninstall-v3.sh || {{ echo "ERROR: official upstream uninstall-v3.sh is missing."; exit 29; }}
BC250_FSR4_PREFIX="$HOME/.local/share/bc250-fsr4/v3" bash {qdest}/uninstall-v3.sh'''
