#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../common/common.sh"
SOURCE_DIR="${BC250_NCT6687_SOURCE_DIR:-$BC250_TOOLS_DIR/nct6687d}"
KERNEL_RELEASE="$(bc250_running_kernel_release)"

kernel_build_tree_ready() {
  bc250_find_matching_kernel_build_dir "$KERNEL_RELEASE"
}

install_build_dependencies() {
  # Fedora's kernel-headers package contains userspace UAPI headers. Only
  # kernel-devel must match uname -r for an out-of-tree kernel module.
  local common_packages=(
    lm_sensors git make gcc gcc-c++ elfutils-libelf-devel dkms kmod kernel-headers
  )
  as_root dnf install -y "${common_packages[@]}"

  if kernel_build_tree_ready; then
    info "Matching kernel-devel is already available for $KERNEL_RELEASE"
    return 0
  fi

  bold "Installing kernel-devel for the running Fedora kernel"
  if ! as_root dnf install -y "kernel-devel-$KERNEL_RELEASE"; then
    warn "Fedora could not install kernel-devel-$KERNEL_RELEASE from the enabled repositories."
  fi

  if ! bc250_require_matching_kernel_headers "$KERNEL_RELEASE"; then
    error "Fedora repair hint: sudo dnf install kernel-devel-$(uname -r) kernel-headers"
    error "If the exact kernel-devel build is unavailable, update Fedora, reboot into the installed kernel, and retry."
    return 21
  fi
}

bold "${BC250_OS_LABEL:-Fedora}: preparing nct6687 PWM driver"
bc250_kernel_headers_preflight "$KERNEL_RELEASE" || true
install_build_dependencies
clone_or_update https://github.com/Fred78290/nct6687d "$SOURCE_DIR"
if (
  cd "$SOURCE_DIR"
  as_root make dkms/install
); then
  info "Installed nct6687 through upstream DKMS target"
else
  warn "DKMS target failed; trying direct module build"
  (
    cd "$SOURCE_DIR"
    run make build
  )
  module_path="$(find "$SOURCE_DIR" -type f -name nct6687.ko -print -quit)"
  [[ -n "$module_path" ]] || { error "nct6687.ko was not produced"; exit 22; }
  bc250_verify_module_vermagic "$module_path" "$KERNEL_RELEASE"
  as_root install -Dm644 "$module_path" "/lib/modules/$KERNEL_RELEASE/kernel/drivers/hwmon/nct6687.ko"
fi
as_root depmod -a "$KERNEL_RELEASE"
installed_module="$(modinfo -n nct6687 2>/dev/null || true)"
if [[ -z "$installed_module" || ! -f "$installed_module" ]]; then
  installed_module="$(find "/lib/modules/$KERNEL_RELEASE" "/usr/lib/modules/$KERNEL_RELEASE" -type f -name 'nct6687.ko*' -print -quit 2>/dev/null || true)"
fi
[[ -n "$installed_module" && -f "$installed_module" ]] || { error "nct6687 is not available for $KERNEL_RELEASE"; exit 22; }
bc250_verify_module_vermagic "$installed_module" "$KERNEL_RELEASE"
info "nct6687 module verified for $KERNEL_RELEASE"
