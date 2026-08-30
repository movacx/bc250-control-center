#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../common/common.sh"
SOURCE_DIR="${BC250_NCT6687_SOURCE_DIR:-$BC250_TOOLS_DIR/nct6687d}"
: "${BC250_NCT6687_REVIEWED_COMMIT:=163ffdcc3928a2bb04acdf9607e45f98eeb46b8a}"
KERNEL_RELEASE="$(bc250_running_kernel_release)"
STATE_DIR="/var/lib/bc250-control-center"
MODULE_DIR="$STATE_DIR/kernel-modules/$KERNEL_RELEASE"
MODULE_DEST="$MODULE_DIR/nct6687.ko"
NCT_SOURCE_STAGE=""

cleanup_nct_source_stage() {
  local status=$?
  trap - EXIT
  [[ -z "$NCT_SOURCE_STAGE" ]] || rm -rf -- "$NCT_SOURCE_STAGE"
  exit "$status"
}
trap cleanup_nct_source_stage EXIT

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

bc250_kernel_headers_preflight "$KERNEL_RELEASE" || true
ensure_build_dependencies
if ! bc250_require_matching_kernel_headers "$KERNEL_RELEASE"; then
  error "Bazzite has kernel-devel installed, but it does not match the active immutable kernel."
  error "Apply the pending system update/deployment, reboot, and run Prepare PWM driver again."
  error "Do not copy a kernel-devel tree from another deployment."
  exit 21
fi
BUILD_DIR="$BC250_KERNEL_BUILD_DIR"

bc250_stage_reviewed_git_tree https://github.com/Fred78290/nct6687d "$SOURCE_DIR" "$BC250_NCT6687_REVIEWED_COMMIT" NCT_SOURCE_STAGE
[[ -f "$NCT_SOURCE_STAGE/Makefile" ]] || { error "Reviewed nct6687 source is incomplete"; exit 22; }
(
  cd "$NCT_SOURCE_STAGE"
  run make kver="$KERNEL_RELEASE" build
)
MODULE_PATH="$(find "$NCT_SOURCE_STAGE/$KERNEL_RELEASE" -maxdepth 1 -type f -name nct6687.ko -print -quit)"
[[ -n "$MODULE_PATH" ]] || { error "nct6687.ko was not produced for $KERNEL_RELEASE"; exit 22; }
bc250_verify_module_vermagic "$MODULE_PATH" "$KERNEL_RELEASE"

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
