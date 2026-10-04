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

_ACTIONS = frozenset({"install", "status", "uninstall", "boot-patched", "activate"})
#: Upstream's marker of an installed release; ``install.sh`` refuses a second.
STATE_ROOT = "/var/lib/bc250-gfx1013"
#: Seconds between the progress lines printed while upstream builds.
PROGRESS_INTERVAL = 30


def build_progress_functions(qbuild: str) -> str:
    """Shell functions that tell what upstream's build is doing from its logs.

    ``bc250_build_detail`` prints one line for the phase in progress, or
    nothing while a download or an extraction runs (curl draws its own
    progress). ``bc250_build_progress`` prints that line every
    ``PROGRESS_INTERVAL`` seconds. Only files written since
    ``bc250_build_started`` count: a cancelled attempt leaves its logs behind.
    """
    return f'''bc250_build_root={qbuild}
bc250_build_started="$(date +%s)"
bc250_fresh() {{ [ -e "$1" ] && [ "$(stat -c %Y -- "$1" 2>/dev/null || echo 0)" -ge "$bc250_build_started" ]; }}
bc250_build_detail() {{
  local step
  if bc250_fresh "$bc250_build_root/mesa-build.log"; then
    if grep -q 'Installing files' "$bc250_build_root/mesa-build.log" 2>/dev/null; then
      echo "Mesa/RADV: staging the finished build"
    else
      step="$(grep -o '^\\[[0-9]*/[0-9]*\\]' "$bc250_build_root/mesa-build.log" 2>/dev/null | tail -n 1 | tr -d '[]' || true)"
      echo "Mesa/RADV: step ${{step:-0/?}} compiled"
    fi
  elif bc250_fresh "$bc250_build_root/mesa-setup.log"; then
    echo "Mesa/RADV: configuring the build"
  elif bc250_fresh "$bc250_build_root/artifacts/cu-mode"; then
    # The kernel half is done; Mesa is being fetched and unpacked.
    return 0
  elif bc250_fresh "$bc250_build_root/artifacts/amdgpu.ko.xz"; then
    # The module keeps its debug information (about 800 MB), so xz -9
    # alone takes minutes.
    echo "kernel module: compressing amdgpu.ko, $(( $(stat -c %s -- "$bc250_build_root/artifacts/amdgpu.ko.xz" 2>/dev/null || echo 0) / 1048576 )) MB written"
  elif bc250_fresh "$bc250_build_root/kernel-build.log"; then
    echo "kernel module: $(grep -c 'CC \\[M\\]' "$bc250_build_root/kernel-build.log" 2>/dev/null || true) files compiled"
  fi
}}
bc250_build_progress() {{
  local detail elapsed
  # The sleep must not hold the output pipe: killed with its loop, an
  # orphaned sleep kept the workflow open until it woke up.
  while sleep {PROGRESS_INTERVAL} </dev/null >/dev/null 2>&1; do
    detail="$(bc250_build_detail)"
    [ -n "$detail" ] || continue
    elapsed=$(( $(date +%s) - bc250_build_started ))
    printf '    ... %s (%dm%02ds)\\n' "$detail" $(( elapsed / 60 )) $(( elapsed % 60 ))
  done
}}'''


def _build_with_progress(qdest: str, qbuild: str) -> str:
    """``install.sh build``, with a progress line every half minute.

    Upstream sends the compiler output to log files, so the terminal said
    "kernel module: building" and then nothing for minutes while about a
    thousand files compiled and the module was compressed, and the same again
    for Mesa. Users took that for a hang and cancelled builds that were
    working. A background loop reads those same logs; the installer itself is
    not edited for it.
    """
    return f'''echo "[INFO] Building the kernel module and Mesa/RADV takes about 10-20 minutes on a BC-250."
echo "[INFO] The compilers write to log files, so a progress line is printed every {PROGRESS_INTERVAL} seconds. Do not cancel the build."
{build_progress_functions(qbuild)}
bc250_build_progress &
bc250_build_watch=$!
bc250_build_status=0
{qdest}/install.sh build || bc250_build_status=$?
kill "$bc250_build_watch" 2>/dev/null || true
if [ "$bc250_build_status" -ne 0 ]; then
  for bc250_log in mesa-build.log mesa-setup.log kernel-build.log; do
    if bc250_fresh "$bc250_build_root/$bc250_log"; then
      echo "---- last lines of $bc250_build_root/$bc250_log ----"
      tail -n 30 "$bc250_build_root/$bc250_log"
      break
    fi
  done
  exit "$bc250_build_status"
fi'''


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
            # The build outlasts sudo's password cache (five minutes by
            # default), so the install at the end would ask again, long after
            # the user stepped away, and the prompt times out. Ask once and
            # keep it fresh until the end, as the source-build workflow does.
            'echo "[INFO] Your password is asked once now; the install at the end reuses it."',
            "sudo -v",
            "( while sleep 50 </dev/null >/dev/null 2>&1; do sudo -n -v >/dev/null 2>&1 || exit 0; done ) &",
            "bc250_sudo_keepalive=$!",
            "trap 'kill \"$bc250_sudo_keepalive\" \"${bc250_build_watch:-}\" 2>/dev/null || true' EXIT",
            f"sudo {qdest}/install.sh deps",
            _build_with_progress(qdest, shlex.quote(str(destination / "build"))),
            # Upstream refuses to install over a release ("a release is
            # already installed; uninstall it first"), so Install / update
            # failed after a full build. The old release is removed only once
            # the new build exists: a failed build leaves it untouched.
            f'''if [ -e {STATE_ROOT}/active.env ]; then
  echo "[INFO] A previous GFX1013 release is installed; replacing it with this build."
  sudo {qdest}/install.sh uninstall
fi''',
            f"sudo {qdest}/install.sh install",
            'echo "BC250_REBOOT_REQUIRED=1"',
            'echo "OK: the patched entry is selected for the next boot only; the stock Fedora entry remains the default."',
        ))
    elif action == "uninstall":
        commands.extend((
            f"sudo {qdest}/install.sh uninstall",
            'echo "OK: upstream GFX1013 files and patched boot entry were removed."',
        ))
    elif action == "boot-patched":
        commands.extend((
            f"sudo {qdest}/install.sh boot-patched",
            'echo "BC250_REBOOT_REQUIRED=1"',
            'echo "OK: the next boot uses the patched entry once; the stock Fedora entry remains the default."',
        ))
    elif action == "activate":
        commands.extend((
            f"sudo {qdest}/install.sh activate",
            'echo "OK: the patched entry is now the default boot entry. The stock entry stays in the boot menu for recovery."',
        ))
    else:
        commands.append(f"{qdest}/install.sh status")
    return "\n".join(commands)
