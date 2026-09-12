"""Official-upstream Fedora workflow for DryhoppedIPA's GFX1013 stack.

The reviewed upstream installer intentionally treats its kernel and Mesa/RADV
patches as one compatibility unit. This adapter keeps that lifecycle intact:
it verifies the supported host, checks out the reviewed revision, applies only
narrowly-scoped host compatibility repairs, and runs the upstream stages in
order.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from .gfx1013_compute_policy import (
    GFX1013_REVIEWED_COMMIT,
    GFX1013_UPSTREAM,
)
from .source_checkout import clone_or_update_commit

_ACTIONS = frozenset({"install", "status", "uninstall"})


def build_fedora_gfx1013_command(action: str, destination: str | Path) -> str:
    """Build a closed command for the reviewed non-Atomic Fedora workflow."""

    action = str(action or "").strip().lower()
    if action not in _ACTIONS:
        raise ValueError(f"Unsupported Fedora GFX1013 action: {action or '--'}")
    destination = Path(destination)
    checkout = clone_or_update_commit(
        GFX1013_UPSTREAM, destination, GFX1013_REVIEWED_COMMIT
    )
    qdest = shlex.quote(str(destination))
    fedora_gate = '''test -r /etc/os-release || { echo "ERROR: /etc/os-release is unavailable."; exit 64; }
. /etc/os-release
test "${ID:-}" = fedora || { echo "ERROR: This reviewed direct workflow supports Fedora only."; exit 64; }
command -v rpm-ostree >/dev/null 2>&1 && { echo "ERROR: Fedora Atomic/Bazzite is not supported by this direct installer."; exit 64; }'''
    install_gate = '''bc250_found=0
for device in /sys/bus/pci/devices/*; do
  test -r "$device/vendor" && test -r "$device/device" || continue
  test "$(cat "$device/vendor")" = 0x1002 && test "$(cat "$device/device")" = 0x13fe && bc250_found=1 && break
done
test "$bc250_found" = 1 || { echo "ERROR: AMD BC-250 PCI device 1002:13fe was not found."; exit 64; }'''
    source_gate = f'''{checkout}
test "$(git -C {qdest} rev-parse HEAD)" = {GFX1013_REVIEWED_COMMIT} || {{ echo "ERROR: reviewed upstream revision was not checked out."; exit 29; }}
test -x {qdest}/install.sh || {{ echo "ERROR: official upstream install.sh is missing."; exit 29; }}
test -f {qdest}/LICENSE -a -f {qdest}/LICENSES.md || {{ echo "ERROR: upstream component licenses are missing."; exit 29; }}
test -f {qdest}/patches/mesa/series || {{ echo "ERROR: official upstream Mesa patch series is missing."; exit 29; }}'''

    commands = [
        "set -Eeuo pipefail",
        "export LC_ALL=C LANG=C",
        fedora_gate,
    ]
    if action == "install":
        commands.append(install_gate)
    commands.append(source_gate)
    if action == "install":
        commands.extend((
            'echo "== Fedora 44 source-RPM compatibility =="',
            f'''bc250_upstream_installer={qdest}/install.sh
bc250_cpio_old="cpio -id --quiet 'linux-*.tar.xz'"
bc250_cpio_fixed="cpio -id --quiet './linux-*.tar.xz' 'linux-*.tar.xz'"
if grep -Fq "$bc250_cpio_fixed" "$bc250_upstream_installer"; then
  echo "[INFO] Upstream already supports RPM 6 source paths."
elif grep -Fq "$bc250_cpio_old" "$bc250_upstream_installer"; then
  sed -i "s|cpio -id --quiet 'linux-\\*\\.tar\\.xz'|cpio -id --quiet './linux-*.tar.xz' 'linux-*.tar.xz'|" "$bc250_upstream_installer"
  grep -Fq "$bc250_cpio_fixed" "$bc250_upstream_installer" || {{ echo "ERROR: Fedora 44 source-RPM compatibility repair did not apply."; exit 29; }}
  echo "[INFO] Added the optional ./ prefix accepted by Fedora 44 rpm2cpio output."
else
  echo "ERROR: upstream kernel source extraction changed; refusing an unreviewed automatic edit."
  exit 29
fi''',
            r'''echo "== Fedora external-module trace compatibility =="
bc250_trace_marker='local bc250_trace_header='
if grep -Fq "$bc250_trace_marker" "$bc250_upstream_installer"; then
  echo "[INFO] Upstream installer already repairs the external trace include path."
elif grep -Eq "^[[:space:]]+printf .*kernel module: building" "$bc250_upstream_installer"; then
  bc250_installer_new="${bc250_upstream_installer}.bc250cc-new"
  awk '
/^    printf .*kernel module: building/ && !bc250_inserted {
    print "    local bc250_trace_header=\"${linux_root}/drivers/gpu/drm/amd/amdgpu/amdgpu_trace.h\""
    print "    if grep -Fqx \"#define TRACE_INCLUDE_PATH ../../drivers/gpu/drm/amd/amdgpu\" \"${bc250_trace_header}\"; then"
    print "        sed -i \"s|^#define TRACE_INCLUDE_PATH ../../drivers/gpu/drm/amd/amdgpu$|#define TRACE_INCLUDE_PATH .|\" \"${bc250_trace_header}\""
    print "    elif ! grep -Fqx \"#define TRACE_INCLUDE_PATH .\" \"${bc250_trace_header}\"; then"
    print "        die \"unsupported amdgpu trace include layout: ${bc250_trace_header}\""
    print "    fi"
    print ""
    bc250_inserted = 1
}
{ print }
END { if (!bc250_inserted) exit 29 }
' "$bc250_upstream_installer" >"$bc250_installer_new" || {
    rm -f "$bc250_installer_new"
    echo "ERROR: upstream kernel build layout changed; refusing an unreviewed automatic edit."
    exit 29
  }
  chmod --reference="$bc250_upstream_installer" "$bc250_installer_new"
  mv -f "$bc250_installer_new" "$bc250_upstream_installer"
  grep -Fq "$bc250_trace_marker" "$bc250_upstream_installer" || {
    echo "ERROR: Fedora external trace compatibility repair did not apply."
    exit 29
  }
  echo "[INFO] External amdgpu trace headers will resolve from the extracted source tree."
else
  echo "ERROR: upstream kernel build layout changed; refusing an unreviewed automatic edit."
  exit 29
fi''',
            'echo; echo "=========================================================================="; echo "  BC-250 GFX1013 - kernel and Mesa/RADV stack"; echo "  complete upstream lifecycle"; echo "=========================================================================="; echo',
            'echo "[INFO] Kernel-only and Mesa-only installation are intentionally not offered: upstream requires both halves together."',
            'echo "[INFO] Mesh/task patches 0002 and 0003 remain disabled because upstream reports unrecoverable GPU hangs."',
            f"sudo {qdest}/install.sh deps",
            f"{qdest}/install.sh build",
            f"sudo {qdest}/install.sh install",
            'echo "BC250_REBOOT_REQUIRED=1"',
            'echo "OK: the patched entry is selected for the next boot only; the stock Fedora entry remains the default."',
        ))
    elif action == "uninstall":
        commands.extend((
            f"sudo {qdest}/install.sh uninstall",
            'echo "OK: upstream GFX1013 files and patched boot entry were removed."',
        ))
    else:
        commands.append(f"{qdest}/install.sh status")
    return "\n".join(commands)
