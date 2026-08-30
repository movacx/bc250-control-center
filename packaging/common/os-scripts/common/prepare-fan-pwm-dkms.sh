#!/usr/bin/env bash
# Shared build/verification half of the mutable-distribution PWM workflow.
# A family wrapper must define ``bc250_install_fan_build_prerequisites`` before
# sourcing this file.  Keeping package-manager syntax outside this file makes
# the hardware checks identical on OpenRC and systemd hosts.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

: "${BC250_NCT6687_SOURCE_DIR:=$BC250_TOOLS_DIR/nct6687d}"
: "${BC250_NCT6687_REVIEWED_COMMIT:=163ffdcc3928a2bb04acdf9607e45f98eeb46b8a}"
KERNEL_RELEASE="$(bc250_running_kernel_release)"
NCT_SOURCE_STAGE=""

declare -F bc250_install_fan_build_prerequisites >/dev/null || {
  error "The distribution wrapper did not provide PWM build prerequisites."
  exit 64
}

cleanup_nct_source_stage() {
  local status=$?
  trap - EXIT
  # DKMS copies the staged tree as root.  A desktop user must not receive a
  # misleading failure merely because cleanup needs the same privilege.
  [[ -z "$NCT_SOURCE_STAGE" ]] || as_root rm -rf -- "$NCT_SOURCE_STAGE"
  exit "$status"
}
trap cleanup_nct_source_stage EXIT

bold "${BC250_OS_LABEL:-Linux}: preparing nct6687 PWM driver"
bc250_kernel_headers_preflight "$KERNEL_RELEASE" || true
bc250_install_fan_build_prerequisites
if ! bc250_require_matching_kernel_headers "$KERNEL_RELEASE"; then
  error "Install headers matching $(uname -r), reboot into that kernel, and retry PWM preparation."
  exit 21
fi

bc250_stage_reviewed_git_tree https://github.com/Fred78290/nct6687d \
  "$BC250_NCT6687_SOURCE_DIR" "$BC250_NCT6687_REVIEWED_COMMIT" NCT_SOURCE_STAGE
[[ -f "$NCT_SOURCE_STAGE/Makefile" ]] || { error "Reviewed nct6687 source is incomplete"; exit 22; }
(
  cd "$NCT_SOURCE_STAGE"
  as_root make dkms/install
)
as_root depmod -a "$KERNEL_RELEASE"
module_path="$(modinfo -n nct6687 2>/dev/null || true)"
if [[ -z "$module_path" || ! -f "$module_path" ]]; then
  module_path="$(find "/lib/modules/$KERNEL_RELEASE" "/usr/lib/modules/$KERNEL_RELEASE" \
    -type f -name 'nct6687.ko*' -print -quit 2>/dev/null || true)"
fi
[[ -n "$module_path" && -f "$module_path" ]] || {
  error "nct6687 DKMS installation did not produce a module for $KERNEL_RELEASE"
  exit 22
}
bc250_verify_module_vermagic "$module_path" "$KERNEL_RELEASE"
info "nct6687 DKMS module installed for $KERNEL_RELEASE"
