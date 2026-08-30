#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../common/common.sh"
SOURCE_DIR="${BC250_NCT6687_SOURCE_DIR:-$BC250_TOOLS_DIR/nct6687d}"
: "${BC250_NCT6687_REVIEWED_COMMIT:=163ffdcc3928a2bb04acdf9607e45f98eeb46b8a}"
KERNEL_RELEASE="$(bc250_running_kernel_release)"
NCT_SOURCE_STAGE=""

cleanup_nct_source_stage() {
  local status=$?
  trap - EXIT
  # The upstream DKMS target creates part of its staging tree as root.
  [[ -z "$NCT_SOURCE_STAGE" ]] || as_root rm -rf -- "$NCT_SOURCE_STAGE"
  exit "$status"
}
trap cleanup_nct_source_stage EXIT

bold "${BC250_OS_LABEL:-Debian family}: preparing nct6687 PWM driver"
bc250_kernel_headers_preflight "$KERNEL_RELEASE" || true
as_root apt-get update
as_root apt-get install -y lm-sensors git build-essential dkms dh-dkms kmod
if ! bc250_find_matching_kernel_build_dir "$KERNEL_RELEASE"; then
  bold "Installing headers for the running Debian/Ubuntu kernel"
  if ! as_root apt-get install -y "linux-headers-$KERNEL_RELEASE"; then
    warn "The repositories do not currently provide linux-headers-$KERNEL_RELEASE."
  fi
fi
if ! bc250_require_matching_kernel_headers "$KERNEL_RELEASE"; then
  error "Debian/Ubuntu repair hint: sudo apt install linux-headers-$(uname -r)"
  error "If that package does not exist, update the system, reboot into the newly installed kernel, and retry."
  exit 21
fi

bc250_stage_reviewed_git_tree https://github.com/Fred78290/nct6687d "$SOURCE_DIR" "$BC250_NCT6687_REVIEWED_COMMIT" NCT_SOURCE_STAGE
[[ -f "$NCT_SOURCE_STAGE/Makefile" ]] || { error "Reviewed nct6687 source is incomplete"; exit 22; }
(
  cd "$NCT_SOURCE_STAGE"
  as_root make dkms/install
)
as_root depmod -a "$KERNEL_RELEASE"
module_path="$(modinfo -n nct6687 2>/dev/null || true)"
if [[ -z "$module_path" || ! -f "$module_path" ]]; then
  module_path="$(find "/lib/modules/$KERNEL_RELEASE" "/usr/lib/modules/$KERNEL_RELEASE" -type f -name 'nct6687.ko*' -print -quit 2>/dev/null || true)"
fi
[[ -n "$module_path" && -f "$module_path" ]] || { error "nct6687 DKMS installation did not produce a module for $KERNEL_RELEASE"; exit 22; }
bc250_verify_module_vermagic "$module_path" "$KERNEL_RELEASE"
info "nct6687 DKMS module installed for $KERNEL_RELEASE"
