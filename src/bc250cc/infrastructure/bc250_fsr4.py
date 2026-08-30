"""Closed, per-game BC-250 FSR4 V3 runtime workflow.

The upstream project explicitly keeps this RADV build outside the system Mesa
installation.  Control Center follows that boundary: the reviewed installer
only writes beneath the current user's data directory and emits the Vulkan ICD
launch option.  It never changes a package, boot loader, kernel or global
Mesa configuration.
"""

from __future__ import annotations

from pathlib import Path

BC250_FSR4_REPOSITORY = "https://github.com/dmorazasanchez/bc250-fsr4"
BC250_FSR4_VERSION = "v3.0.0"
BC250_FSR4_ASSET = "bc250-fsr4-v3-cachyos-arch-llvm22-x86_64.tar.gz"
BC250_FSR4_SHA256 = "faab5222388c2059bde591aab88f65e4e7edba27db0abe309d1e1dac23983e9d"
BC250_FSR4_PREFIX = Path.home() / ".local/share/bc250-fsr4/v3"
BC250_FSR4_ICD = BC250_FSR4_PREFIX / "radv-bc250-fsr4-v3.json"
BC250_FSR4_SUPPORTED_FAMILIES = frozenset({"arch", "cachyos"})


def fsr4_runtime_state(family: str) -> dict:
    """Describe the local, reversible FSR4 V3 runtime without executing it."""

    library = BC250_FSR4_PREFIX / "libvulkan_radeon.so"
    installed = library.is_file() and BC250_FSR4_ICD.is_file()
    return {
        "repository": BC250_FSR4_REPOSITORY,
        "version": BC250_FSR4_VERSION,
        "sha256": BC250_FSR4_SHA256,
        "prefix": str(BC250_FSR4_PREFIX),
        "icd": str(BC250_FSR4_ICD),
        "installed": installed,
        "precompiled_supported": str(family or "").lower()
        in BC250_FSR4_SUPPORTED_FAMILIES,
        "source_build_required": str(family or "").lower()
        not in BC250_FSR4_SUPPORTED_FAMILIES,
    }


def build_fsr4_v3_install_command() -> str:
    """Build the fixed Arch/CachyOS per-user installation transaction.

    The release archive checksum is verified before extraction.  This is a
    static reproduction of the reviewed upstream V3 installer, rather than a
    pipe-to-shell fetch of a moving script.
    """

    return f'''set -euo pipefail
echo "== BC-250 FSR4 V3 per-game runtime =="
test -r /etc/os-release || {{ echo "ERROR: /etc/os-release is unavailable."; exit 64; }}
. /etc/os-release
case "${{ID:-}}" in arch|cachyos|cachy) ;; *)
  echo "ERROR: The reviewed precompiled FSR4 V3 runtime is limited to Arch/CachyOS userspace."; exit 64;; esac
test "$(uname -m)" = x86_64 || {{ echo "ERROR: FSR4 V3 is x86_64-only."; exit 64; }}
command -v curl >/dev/null 2>&1 || {{ echo "ERROR: curl is required."; exit 69; }}
command -v sha256sum >/dev/null 2>&1 || {{ echo "ERROR: sha256sum is required."; exit 69; }}
command -v tar >/dev/null 2>&1 || {{ echo "ERROR: tar is required."; exit 69; }}
if command -v lspci >/dev/null 2>&1 && ! lspci -Dn | grep -qiE '1002:13fe'; then
  echo "ERROR: AMD BC-250 PCI ID 1002:13FE was not detected."; exit 64
fi
bc250_tmp="$(mktemp -d)"
trap 'rm -rf -- "$bc250_tmp"' EXIT
bc250_prefix="$HOME/.local/share/bc250-fsr4/v3"
bc250_asset="{BC250_FSR4_ASSET}"
bc250_base="https://github.com/dmorazasanchez/bc250-fsr4/releases/download/{BC250_FSR4_VERSION}"
echo "[INFO] Downloading the reviewed {BC250_FSR4_VERSION} release."
curl --fail --location --retry 3 --connect-timeout 15 "$bc250_base/$bc250_asset" -o "$bc250_tmp/$bc250_asset"
(cd "$bc250_tmp" && printf '%s  %s\n' '{BC250_FSR4_SHA256}' "$bc250_asset" | sha256sum -c -)
case "$bc250_prefix" in "$HOME"/.local/share/bc250-fsr4/v3) ;; *) echo "ERROR: unexpected per-user target."; exit 70;; esac
rm -rf -- "$bc250_prefix"
mkdir -p "$bc250_prefix"
tar -xzf "$bc250_tmp/$bc250_asset" -C "$bc250_prefix"
test -f "$bc250_prefix/libvulkan_radeon.so" || {{ echo "ERROR: archive did not contain the FSR4 RADV library."; exit 71; }}
if command -v ldd >/dev/null 2>&1 && ldd "$bc250_prefix/libvulkan_radeon.so" | grep -q 'not found'; then
  echo "ERROR: This Arch/CachyOS binary is not ABI-compatible with the current system."
  ldd "$bc250_prefix/libvulkan_radeon.so" | grep 'not found' || true
  exit 72
fi
python3 - "$bc250_prefix/libvulkan_radeon.so" "$bc250_prefix/radv-bc250-fsr4-v3.json" <<'PY'
import json, sys
library, icd = sys.argv[1:]
with open(icd, 'w', encoding='utf-8') as handle:
    json.dump({{'file_format_version': '1.0.0', 'ICD': {{'library_path': library, 'api_version': '1.4.0'}}}}, handle, indent=2)
    handle.write('\\n')
PY
printf 'VK_DRIVER_FILES="%s" %%command%%\\n' "$bc250_prefix/radv-bc250-fsr4-v3.json" > "$bc250_prefix/STEAM-LAUNCH.txt"
if command -v vulkaninfo >/dev/null 2>&1; then
  VK_DRIVER_FILES="$bc250_prefix/radv-bc250-fsr4-v3.json" vulkaninfo --summary || {{ echo "ERROR: FSR4 V3 Vulkan validation failed."; exit 73; }}
fi
echo "OK: FSR4 V3 was installed per-user; no system Mesa file was modified."
echo "Steam launch option:"
cat "$bc250_prefix/STEAM-LAUNCH.txt"'''


def build_fsr4_v3_uninstall_command() -> str:
    """Return the fixed, per-user FSR4 V3 rollback command."""

    return '''set -euo pipefail
bc250_prefix="$HOME/.local/share/bc250-fsr4/v3"
case "$bc250_prefix" in "$HOME"/.local/share/bc250-fsr4/v3) ;; *) echo "ERROR: unexpected per-user target."; exit 70;; esac
rm -rf -- "$bc250_prefix"
echo "OK: Removed the BC-250 FSR4 V3 runtime. Remove VK_DRIVER_FILES from affected Steam launch options to return to system RADV."'''
