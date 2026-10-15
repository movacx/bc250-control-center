"""Official-upstream BC-250 FSR4 V3 lifecycle.

Arch and CachyOS use the upstream installer unchanged. Fedora 44 and Bazzite
build the same official ``v3`` branch in its Fedora container
with rootless Podman, then install only the verified per-user Vulkan ICD. Every
path restores the previous per-user runtime if installation or Vulkan
validation fails.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from . import container_network
from .source_checkout import clone_or_update_commit

BC250_FSR4_REPOSITORY = "https://github.com/dmorazasanchez/bc250-fsr4"
BC250_FSR4_BRANCH = "v3"
BC250_FSR4_REVIEWED_COMMIT = "6173651fa3a5a557cba2c2ff802e2d6f49881bc1"
BC250_FSR4_PREFIX = Path.home() / ".local/share/bc250-fsr4/v3"
BC250_FSR4_ICD = BC250_FSR4_PREFIX / "radv-bc250-fsr4-v3.json"
BC250_FSR4_SUPPORTED_FAMILIES = frozenset({"arch", "cachyos"})
BC250_FSR4_SOURCE_BUILD_IDS = frozenset({"bazzite"})
BC250_FSR4_FEDORA_SOURCE_IDS = frozenset({"fedora"})


def fsr4_steam_launch_option(build_kind: str = "") -> str:
    """Return a username-independent Steam option for the installed runtime."""

    prefix = "$HOME/.local/share/bc250-fsr4/v3"
    icd_option = f'VK_DRIVER_FILES="{prefix}/radv-bc250-fsr4-v3.json"'
    if str(build_kind or "").endswith("-podman-source"):
        return (
            f'LD_LIBRARY_PATH="{prefix}/lib'
            '${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" '
            f"{icd_option} %command%"
        )
    return f"{icd_option} %command%"


def _fsr4_platform_mode(*, family: str, distro_id: str) -> tuple[bool, bool]:
    normalized_family = str(family or "").strip().lower()
    normalized_id = str(distro_id or "").strip().lower()
    documented = normalized_family in BC250_FSR4_SUPPORTED_FAMILIES and normalized_id in {
        "",
        "arch",
        "cachyos",
        "cachy",
    }
    return documented, False


def _fsr4_source_build_mode(
    *, family: str, distro_id: str, version_id: str = ""
) -> str:
    normalized_family = str(family or "").strip().lower()
    normalized_id = str(distro_id or "").strip().lower()
    normalized_version = str(version_id or "").strip()
    if (
        normalized_family in BC250_FSR4_SOURCE_BUILD_IDS
        or normalized_id in BC250_FSR4_SOURCE_BUILD_IDS
    ):
        return "bazzite-podman-source"
    if (
        normalized_family in BC250_FSR4_FEDORA_SOURCE_IDS
        and normalized_id in BC250_FSR4_FEDORA_SOURCE_IDS
        and normalized_version == "44"
    ):
        return "fedora44-podman-source"
    return ""


def _build_fsr4_v3_podman_install_command(
    destination: str | Path, *, platform_mode: str
) -> str:
    """Build official V3 with rootless Podman and install a per-user ICD."""

    if platform_mode == "bazzite":
        platform_label = "Bazzite"
        platform_gate = (
            'test "${ID:-}" = "bazzite" || '
            '{ echo "ERROR: This source-build workflow is available only on Bazzite."; exit 64; }'
        )
        dependency_prepare = ""
        build_kind = "bazzite-podman-source"
    elif platform_mode == "debian":
        platform_label = "Debian/Ubuntu"
        platform_gate = '''bc250_os_family=" ${ID:-} ${ID_LIKE:-} "
case "$bc250_os_family" in
  *" debian "*|*" ubuntu "*) ;;
  *) echo "ERROR: This source-build workflow is available only on Debian/Ubuntu and derivatives."; exit 64 ;;
esac
command -v apt-get >/dev/null 2>&1 || { echo "ERROR: apt-get is required for the Debian/Ubuntu FSR4 source build."; exit 69; }'''
        dependency_prepare = '''bc250_apt_packages=()
for bc250_command in git lspci podman python3 ldd vulkaninfo; do
  command -v "$bc250_command" >/dev/null 2>&1 || bc250_apt_packages=(git pciutils podman python3 libc-bin vulkan-tools)
done
if ! ldconfig -p 2>/dev/null | grep -q 'libLLVM\\.so\\.22\\.1'; then
  if apt-cache show libllvm22 >/dev/null 2>&1; then
    bc250_apt_packages+=(libllvm22)
  else
    echo "ERROR: this Debian/Ubuntu repository does not provide libllvm22, required by the official Fedora 44 V3 build."
    exit 69
  fi
fi
if [ "${#bc250_apt_packages[@]}" -gt 0 ]; then
  echo "Installing the Debian/Ubuntu build and LLVM 22 runtime tools required by the isolated FSR4 source build..."
  sudo apt-get update
  sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y "${bc250_apt_packages[@]}"
fi'''
        build_kind = "debian-podman-source"
    elif platform_mode == "fedora44":
        platform_label = "Fedora 44"
        platform_gate = '''test "${ID:-}" = "fedora" || { echo "ERROR: This source-build workflow is available only on Fedora."; exit 64; }
test "${VERSION_ID:-}" = "44" || { echo "ERROR: The reviewed FSR4 source build supports Fedora 44 only."; exit 64; }
command -v rpm-ostree >/dev/null 2>&1 && { echo "ERROR: Fedora Atomic must use its immutable-system workflow, not this Fedora Workstation route."; exit 64; }
command -v dnf >/dev/null 2>&1 || { echo "ERROR: dnf is required for Fedora 44 preparation."; exit 69; }
command -v sudo >/dev/null 2>&1 || { echo "ERROR: sudo is required to prepare missing Fedora build tools."; exit 69; }
grep -qw 'bc250.gfx1013_v33=1' /proc/cmdline || { echo "ERROR: Boot the repaired GFX1013 kernel entry before building or using its FSR4 RADV runtime."; exit 64; }
test -f /var/lib/bc250-gfx1013/active.env || { echo "ERROR: The reviewed GFX1013 kernel/Mesa installation is not complete."; exit 64; }'''
        dependency_prepare = '''bc250_dnf_packages=()
command -v git >/dev/null 2>&1 || bc250_dnf_packages+=(git)
command -v lspci >/dev/null 2>&1 || bc250_dnf_packages+=(pciutils)
command -v podman >/dev/null 2>&1 || bc250_dnf_packages+=(podman)
command -v python3 >/dev/null 2>&1 || bc250_dnf_packages+=(python3)
command -v ldd >/dev/null 2>&1 || bc250_dnf_packages+=(glibc)
command -v vulkaninfo >/dev/null 2>&1 || bc250_dnf_packages+=(vulkan-tools)
if [ "${#bc250_dnf_packages[@]}" -gt 0 ]; then
  echo "Installing the Fedora 44 tools required by the isolated FSR4 source build..."
  sudo dnf install -y "${bc250_dnf_packages[@]}"
fi'''
        build_kind = "fedora44-podman-source"
    else:
        raise ValueError(f"Unsupported FSR4 Podman source-build platform: {platform_mode}")

    destination = Path(destination)
    checkout = clone_or_update_commit(
        BC250_FSR4_REPOSITORY,
        destination,
        BC250_FSR4_REVIEWED_COMMIT,
    )
    qdest = shlex.quote(str(destination))
    network_setup = "\n".join(container_network.setup_lines("podman"))
    return f'''set -euo pipefail
echo "== BC-250 FSR4 official V3 source build for {platform_label} =="
test -r /etc/os-release || {{ echo "ERROR: /etc/os-release is unavailable."; exit 64; }}
. /etc/os-release
{platform_gate}
test "$(uname -m)" = "x86_64" || {{ echo "ERROR: The official Fedora 44 build container targets x86_64."; exit 64; }}
{dependency_prepare}
for bc250_command in git lspci podman python3 ldd vulkaninfo; do
  command -v "$bc250_command" >/dev/null 2>&1 || {{ echo "ERROR: $bc250_command is required for the {platform_label} FSR4 source build."; exit 69; }}
done
lspci -Dn | grep -qiE '1002:13fe' || {{ echo "ERROR: AMD BC-250 PCI ID 1002:13FE was not detected."; exit 64; }}
podman info >/dev/null || {{ echo "ERROR: rootless Podman is not ready for the current user."; exit 69; }}
{network_setup}
{checkout}
for bc250_file in Dockerfile build-bc250.sh bc250-fsr4-v3.patch mesa-commit.txt; do
  test -f {qdest}/"$bc250_file" || {{ echo "ERROR: official upstream $bc250_file is missing."; exit 29; }}
done
bc250_revision="$(git -C {qdest} rev-parse HEAD)"
case "$bc250_revision" in
  *[!0-9a-f]*|'') echo "ERROR: invalid upstream Git revision."; exit 29 ;;
esac
bc250_mesa_commit="$(head -n 1 {qdest}/mesa-commit.txt | tr -d '[:space:]')"
case "$bc250_mesa_commit" in
  *[!A-Za-z0-9._/-]*|'') echo "ERROR: invalid Mesa revision in official mesa-commit.txt."; exit 29 ;;
esac
bc250_cache_root="$HOME/.cache/bc250-fsr4"
bc250_build="$bc250_cache_root/v3-build"
bc250_build_revision="$bc250_cache_root/v3-build.revision"
bc250_image="localhost/bc250-fsr4:official-v3"
mkdir -p "$bc250_cache_root"
if test -s "$bc250_build/libvulkan_radeon.so" && test -f "$bc250_build_revision" && test "$(cat "$bc250_build_revision" 2>/dev/null || true)" = "$bc250_revision"; then
  echo "Reusing the verified FSR4 build cached for upstream revision $bc250_revision."
else
  rm -rf -- "$bc250_build"
  rm -f -- "$bc250_build_revision"
  mkdir -p "$bc250_build"
  echo "Building the official Fedora 44 image with Podman. The first build can take several minutes."
  podman build $bc250_net --tag "$bc250_image" --build-arg "MESA_COMMIT=$bc250_mesa_commit" {qdest}
  echo "Compiling the official FSR4 V3 RADV runtime..."
  podman run --rm $bc250_net \
    --env VARIANT=patch \
    --volume {qdest}:/workspace:ro,Z \
    --volume "$bc250_build":/build:Z \
    "$bc250_image"
  test -s "$bc250_build/libvulkan_radeon.so" || {{ echo "ERROR: the official source build did not produce libvulkan_radeon.so."; exit 29; }}
  printf '%s\n' "$bc250_revision" > "$bc250_build_revision"
fi
if ! podman image exists "$bc250_image"; then
  echo "Restoring the official Fedora 44 image required for the private FSR4 runtime libraries."
  podman build $bc250_net --tag "$bc250_image" --build-arg "MESA_COMMIT=$bc250_mesa_commit" {qdest}
fi
bc250_runtime_libs="$bc250_build/runtime-libs"
rm -rf -- "$bc250_runtime_libs"
mkdir -p "$bc250_runtime_libs"
podman run --rm $bc250_net \
  --entrypoint /bin/sh \
  --volume "$bc250_runtime_libs":/out:Z \
  "$bc250_image" \
  -c 'cp -L /usr/lib64/libdrm.so.2 /out/libdrm.so.2 && cp -L /usr/lib64/libdrm_amdgpu.so.1 /out/libdrm_amdgpu.so.1'
test -s "$bc250_runtime_libs/libdrm.so.2" || {{ echo "ERROR: the official build image did not provide its matching libdrm runtime."; exit 29; }}
test -s "$bc250_runtime_libs/libdrm_amdgpu.so.1" || {{ echo "ERROR: the official build image did not provide its matching AMDGPU libdrm runtime."; exit 29; }}
if LD_LIBRARY_PATH="$bc250_runtime_libs" ldd "$bc250_build/libvulkan_radeon.so" | grep -q 'not found'; then
  echo "ERROR: the source-built driver has unresolved {platform_label} runtime dependencies."
  LD_LIBRARY_PATH="$bc250_runtime_libs" ldd "$bc250_build/libvulkan_radeon.so" | grep 'not found' || true
  exit 29
fi
bc250_parent="$HOME/.local/share/bc250-fsr4"
bc250_prefix="$bc250_parent/v3"
bc250_library="$bc250_prefix/libvulkan_radeon.so"
bc250_icd="$bc250_prefix/radv-bc250-fsr4-v3.json"
bc250_backup=''
mkdir -p "$bc250_parent"
bc250_stage="$(mktemp -d "$bc250_parent/.v3.stage.XXXXXX")"
cp -- "$bc250_build/libvulkan_radeon.so" "$bc250_stage/libvulkan_radeon.so"
mkdir -p "$bc250_stage/lib"
cp -- "$bc250_runtime_libs/libdrm.so.2" "$bc250_stage/lib/libdrm.so.2"
cp -- "$bc250_runtime_libs/libdrm_amdgpu.so.1" "$bc250_stage/lib/libdrm_amdgpu.so.1"
if LD_LIBRARY_PATH="$bc250_stage/lib" ldd "$bc250_stage/libvulkan_radeon.so" | grep -q 'not found'; then
  echo "ERROR: the staged source-built driver still has unresolved runtime dependencies."
  LD_LIBRARY_PATH="$bc250_stage/lib" ldd "$bc250_stage/libvulkan_radeon.so" | grep 'not found' || true
  rm -rf -- "$bc250_stage"
  exit 29
fi
printf '%s\n' "$bc250_revision" > "$bc250_stage/.bc250-upstream-revision"
printf '%s\n' '{build_kind}' > "$bc250_stage/.bc250-build-kind"
BC250_FSR4_LIBRARY="$bc250_library" BC250_FSR4_ICD="$bc250_stage/radv-bc250-fsr4-v3.json" python3 - <<'PY'
import json
import os
from pathlib import Path

manifest = {{
    "file_format_version": "1.0.0",
    "ICD": {{
        "library_path": os.environ["BC250_FSR4_LIBRARY"],
        "api_version": "1.4.0",
    }},
}}
Path(os.environ["BC250_FSR4_ICD"]).write_text(
    json.dumps(manifest, indent=2) + "\\n",
    encoding="utf-8",
)
PY
python3 -m json.tool "$bc250_stage/radv-bc250-fsr4-v3.json" >/dev/null
if test -L "$bc250_prefix"; then
  rm -rf -- "$bc250_stage"
  echo "ERROR: refusing to replace a symlink at $bc250_prefix."
  exit 29
fi
if test -e "$bc250_prefix"; then
  bc250_backup="$(mktemp -d "$bc250_parent/.v3.backup.XXXXXX")"
  rmdir "$bc250_backup"
  mv -- "$bc250_prefix" "$bc250_backup"
fi
mv -- "$bc250_stage" "$bc250_prefix"
if LD_LIBRARY_PATH="$bc250_prefix/lib${{LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}}" VK_DRIVER_FILES="$bc250_icd" vulkaninfo --summary; then
  test -z "$bc250_backup" || rm -rf -- "$bc250_backup"
else
  bc250_result=$?
  rm -rf -- "$bc250_prefix"
  if test -n "$bc250_backup" && test -e "$bc250_backup"; then
    mv -- "$bc250_backup" "$bc250_prefix"
  fi
  echo "ERROR: Vulkan rejected the source-built driver; the previous per-user runtime was restored."
  exit "$bc250_result"
fi
echo "OK: official upstream FSR4 V3 was source-built and installed per-user at revision $bc250_revision."
echo "Steam launch option:"
printf '%s\n' 'LD_LIBRARY_PATH="$HOME/.local/share/bc250-fsr4/v3/lib${{LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}}" VK_DRIVER_FILES="$HOME/.local/share/bc250-fsr4/v3/radv-bc250-fsr4-v3.json" %command%'
'''


def build_fsr4_v3_uninstall_command(destination: str | Path) -> str:
    """Update upstream and invoke its official uninstall script."""

    destination = Path(destination)
    checkout = clone_or_update_commit(
        BC250_FSR4_REPOSITORY,
        destination,
        BC250_FSR4_REVIEWED_COMMIT,
    )
    qdest = shlex.quote(str(destination))
    return f'''set -euo pipefail
command -v git >/dev/null 2>&1 || {{ echo "ERROR: git is required to update the official FSR4 source."; exit 69; }}
{checkout}
test -f {qdest}/uninstall-v3.sh || {{ echo "ERROR: official upstream uninstall-v3.sh is missing."; exit 29; }}
BC250_FSR4_PREFIX="$HOME/.local/share/bc250-fsr4/v3" bash {qdest}/uninstall-v3.sh'''
