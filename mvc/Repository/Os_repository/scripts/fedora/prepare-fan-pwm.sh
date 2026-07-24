#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../common/common.sh"
SOURCE_DIR="${BC250_NCT6687_SOURCE_DIR:-$BC250_TOOLS_DIR/nct6687d}"
KERNEL_RELEASE="$(uname -r)"

kernel_build_tree_ready() {
  [[ -e "/lib/modules/$KERNEL_RELEASE/build/Makefile" || \
     -e "/usr/lib/modules/$KERNEL_RELEASE/build/Makefile" || \
     -e "/usr/src/kernels/$KERNEL_RELEASE/Makefile" ]]
}

install_build_dependencies() {
  # Fedora's kernel-headers package contains the userspace/glibc UAPI headers.
  # Its NEVRA does not have to match uname -r. Only kernel-devel must match the
  # running kernel when building an out-of-tree module.
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
    error "Fedora could not install kernel-devel-$KERNEL_RELEASE."
    error "The running kernel may be older/newer than the versions currently available in enabled repositories."
    error "Update Fedora, reboot into an installed kernel with matching kernel-devel, then retry Prepare fan PWM."
    return 21
  fi

  if ! kernel_build_tree_ready; then
    error "kernel-devel-$KERNEL_RELEASE was requested, but its build tree is still unavailable."
    error "Expected /lib/modules/$KERNEL_RELEASE/build or /usr/src/kernels/$KERNEL_RELEASE."
    return 21
  fi
}

bold "${BC250_OS_LABEL:-Fedora}: preparing nct6687 PWM driver"
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
  as_root install -Dm644 "$module_path" "/lib/modules/$KERNEL_RELEASE/kernel/drivers/hwmon/nct6687.ko"
fi
as_root depmod -a "$KERNEL_RELEASE"
modinfo nct6687 >/dev/null 2>&1 || { error "nct6687 is not available for $KERNEL_RELEASE"; exit 22; }
