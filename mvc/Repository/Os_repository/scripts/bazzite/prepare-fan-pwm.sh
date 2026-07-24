#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../common/common.sh"
SOURCE_DIR="${BC250_NCT6687_SOURCE_DIR:-$BC250_TOOLS_DIR/nct6687d}"
KERNEL_RELEASE="$(uname -r)"
STATE_DIR="/var/lib/bc250-control-center"
MODULE_DIR="$STATE_DIR/kernel-modules/$KERNEL_RELEASE"
MODULE_DEST="$MODULE_DIR/nct6687.ko"

package_is_active() {
  rpm -q "$1" >/dev/null 2>&1
}

ensure_build_dependencies() {
  local required=(lm_sensors git make gcc elfutils-libelf-devel kernel-devel kmod)
  local missing=()
  local package
  for package in "${required[@]}"; do
    package_is_active "$package" || missing+=("$package")
  done
  if [[ ${#missing[@]} -eq 0 ]]; then
    return 0
  fi
  bold "Layering missing Bazzite fan build dependencies"
  as_root rpm-ostree install --idempotent "${missing[@]}"
  warn "The required packages were added to a pending deployment. Reboot, then press Prepare fan PWM once."
  echo "BC250_REBOOT_REQUIRED=1"
  exit 20
}


bold "${BC250_OS_LABEL:-Bazzite}: preparing nct6687 PWM support"
if as_root modprobe nct6687 force=true 2>/dev/null; then
  info "A packaged nct6687 module is already available for $KERNEL_RELEASE"
  exit 0
fi

ensure_build_dependencies

BUILD_DIR=""
for candidate in "/usr/lib/modules/$KERNEL_RELEASE/build" "/lib/modules/$KERNEL_RELEASE/build"; do
  if [[ -f "$candidate/Makefile" ]]; then BUILD_DIR="$candidate"; break; fi
done
[[ -n "$BUILD_DIR" ]] || {
  error "Matching kernel-devel is not active for $KERNEL_RELEASE"
  exit 21
}

clone_or_update https://github.com/Fred78290/nct6687d "$SOURCE_DIR"
(
  cd "$SOURCE_DIR"
  run make kver="$KERNEL_RELEASE" build
)
MODULE_PATH="$(find "$SOURCE_DIR/$KERNEL_RELEASE" -maxdepth 1 -type f -name nct6687.ko -print -quit)"
[[ -n "$MODULE_PATH" ]] || { error "nct6687.ko was not produced for $KERNEL_RELEASE"; exit 22; }

as_root install -d -m 0755 "$MODULE_DIR"
as_root install -m 0644 "$MODULE_PATH" "$MODULE_DEST"
if have chcon; then
  as_root chcon -t modules_object_t "$MODULE_DEST" || warn "Could not apply SELinux modules_object_t label"
fi

# Do not run depmod here: /usr/lib/modules is immutable on rpm-ostree. The
# Bazzite persistence service loads this exact per-kernel file with insmod and
# owns live verification, so the service is installed even when the first load
# needs additional diagnostics (SELinux, Secure Boot or hardware probing).
info "Prepared kernel-specific nct6687 module at $MODULE_DEST"
info "Continuing with persistent service installation"
