"""Official-upstream BC-250 FSR4 V3 lifecycle.

Arch-family hosts use the upstream installer unchanged. Bazzite and
Debian/Ubuntu build the same official ``v3`` branch in its Fedora container
with rootless Podman, then install only the verified per-user Vulkan ICD. Every
path restores the previous per-user runtime if installation or Vulkan
validation fails.
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
BC250_FSR4_SOURCE_BUILD_IDS = frozenset({"bazzite"})
BC250_FSR4_DEBIAN_SOURCE_FAMILIES = frozenset({"debian", "ubuntu"})


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
    experimental = normalized_id in BC250_FSR4_EXPERIMENTAL_IDS
    return documented, experimental


def _fsr4_source_build_mode(*, family: str, distro_id: str) -> str:
    normalized_family = str(family or "").strip().lower()
    normalized_id = str(distro_id or "").strip().lower()
    if (
        normalized_family in BC250_FSR4_SOURCE_BUILD_IDS
        or normalized_id in BC250_FSR4_SOURCE_BUILD_IDS
    ):
        return "bazzite-podman-source"
    if normalized_family in BC250_FSR4_DEBIAN_SOURCE_FAMILIES:
        return "debian-podman-source"
    return ""


def fsr4_runtime_state(family: str, distro_id: str = "") -> dict:
    """Validate the shape of the upstream-managed per-user runtime."""

    library = BC250_FSR4_PREFIX / "libvulkan_radeon.so"
    revision_file = BC250_FSR4_PREFIX / ".bc250-upstream-revision"
    build_kind_file = BC250_FSR4_PREFIX / ".bc250-build-kind"
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
    build_kind = ""
    try:
        build_kind = build_kind_file.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    if build_kind.endswith("-podman-source"):
        matching_libdrm = BC250_FSR4_PREFIX / "lib/libdrm.so.2"
        matching_amdgpu = BC250_FSR4_PREFIX / "lib/libdrm_amdgpu.so.1"
        valid_icd = bool(
            valid_icd
            and matching_libdrm.is_file()
            and not matching_libdrm.is_symlink()
            and matching_amdgpu.is_file()
            and not matching_amdgpu.is_symlink()
        )
    current = bool(valid_icd)
    documented, experimental = _fsr4_platform_mode(
        family=family,
        distro_id=distro_id,
    )
    source_build_mode = _fsr4_source_build_mode(
        family=family,
        distro_id=distro_id,
    )
    source_build_supported = bool(source_build_mode)
    return {
        "repository": BC250_FSR4_REPOSITORY,
        "branch": BC250_FSR4_BRANCH,
        "version": "upstream-v3",
        "upstream_revision": revision,
        "build_kind": build_kind,
        "steam_launch_option": fsr4_steam_launch_option(build_kind),
        "upstream_managed": True,
        "prefix": str(BC250_FSR4_PREFIX),
        "icd": str(BC250_FSR4_ICD),
        "installed": artifacts_present,
        "current": current,
        "state": "ready" if current else "invalid" if artifacts_present else "not-installed",
        "precompiled_supported": documented,
        "experimental_precompiled": experimental,
        "source_build_supported": source_build_supported,
        "build_mode": source_build_mode or "precompiled",
        "installer_available": documented or experimental or source_build_supported,
        "source_build_required": source_build_supported or not (documented or experimental),
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
echo "OK: official upstream FSR4 V3 installed per-user at revision $(cat "$bc250_prefix/.bc250-upstream-revision")."
echo "Portable Steam launch option:"
printf '%s\n' 'VK_DRIVER_FILES="$HOME/.local/share/bc250-fsr4/v3/radv-bc250-fsr4-v3.json" %command%'
'''


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
    else:
        raise ValueError(f"Unsupported FSR4 Podman source-build platform: {platform_mode}")

    destination = Path(destination)
    checkout = clone_or_update_branch(
        BC250_FSR4_REPOSITORY,
        destination,
        BC250_FSR4_BRANCH,
    )
    qdest = shlex.quote(str(destination))
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
  podman build --tag "$bc250_image" --build-arg "MESA_COMMIT=$bc250_mesa_commit" {qdest}
  echo "Compiling the official FSR4 V3 RADV runtime..."
  podman run --rm \
    --env VARIANT=patch \
    --volume {qdest}:/workspace:ro,Z \
    --volume "$bc250_build":/build:Z \
    "$bc250_image"
  test -s "$bc250_build/libvulkan_radeon.so" || {{ echo "ERROR: the official source build did not produce libvulkan_radeon.so."; exit 29; }}
  printf '%s\n' "$bc250_revision" > "$bc250_build_revision"
fi
if ! podman image exists "$bc250_image"; then
  echo "Restoring the official Fedora 44 image required for the private FSR4 runtime libraries."
  podman build --tag "$bc250_image" --build-arg "MESA_COMMIT=$bc250_mesa_commit" {qdest}
fi
bc250_runtime_libs="$bc250_build/runtime-libs"
rm -rf -- "$bc250_runtime_libs"
mkdir -p "$bc250_runtime_libs"
podman run --rm \
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


def build_fsr4_v3_bazzite_install_command(destination: str | Path) -> str:
    """Build official V3 with rootless Podman and install it per-user on Bazzite."""

    return _build_fsr4_v3_podman_install_command(
        destination, platform_mode="bazzite"
    )


def build_fsr4_v3_debian_install_command(destination: str | Path) -> str:
    """Build official V3 in a rootless container on Debian/Ubuntu derivatives."""

    return _build_fsr4_v3_podman_install_command(
        destination, platform_mode="debian"
    )


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
