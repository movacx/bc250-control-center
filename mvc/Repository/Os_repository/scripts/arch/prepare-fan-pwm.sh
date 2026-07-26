#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../common/common.sh"
source "$SCRIPT_DIR/../common/aur.sh"

SOURCE_DIR="${BC250_NCT6687_SOURCE_DIR:-$BC250_TOOLS_DIR/nct6687d}"
KERNEL_RELEASE="$(bc250_running_kernel_release)"
MODULE_DIR="/usr/lib/modules/$KERNEL_RELEASE"
[[ -d "$MODULE_DIR" ]] || MODULE_DIR="/lib/modules/$KERNEL_RELEASE"

bold "${BC250_OS_LABEL:-Arch family}: preparing nct6687 PWM driver"
bc250_kernel_headers_preflight "$KERNEL_RELEASE" || true
ensure_arch_build_toolchain
as_root pacman -S --needed --noconfirm lm_sensors dkms kmod

kernel_package=""
if [[ -r "$MODULE_DIR/pkgbase" ]]; then
  IFS= read -r kernel_package < "$MODULE_DIR/pkgbase" || true
fi
if [[ -z "$kernel_package" ]]; then
  kernel_package="$(pacman -Qqo "$MODULE_DIR" 2>/dev/null | head -n 1 || true)"
fi
headers_package=""
if [[ -n "$kernel_package" ]]; then
  headers_package="${kernel_package}-headers"
  info "Detected active kernel package: $kernel_package"
  info "Trying exact headers package: $headers_package"
  as_root pacman -S --needed --noconfirm "$headers_package" || true
fi
if ! bc250_find_matching_kernel_build_dir "$KERNEL_RELEASE"; then
  warn "The exact package could not provide matching headers; trying linux-headers only as a final fallback."
  as_root pacman -S --needed --noconfirm linux-headers || true
fi
if ! bc250_require_matching_kernel_headers "$KERNEL_RELEASE"; then
  error "Arch-family repair hint: install the headers package matching the active kernel package."
  if [[ -n "$kernel_package" ]]; then
    error "Suggested command: sudo pacman -S --needed $headers_package"
  fi
  error "For partial-upgrade cases, complete a full system update, reboot, and retry; do not compile against headers from another kernel."
  exit 21
fi

if ! install_aur_package nct6687d-dkms-git; then
  warn "AUR package installation failed; trying the upstream DKMS target directly"
  clone_or_update https://github.com/Fred78290/nct6687d "$SOURCE_DIR"
  (
    cd "$SOURCE_DIR"
    as_root make dkms/install
  )
fi

as_root depmod -a "$KERNEL_RELEASE"
module_path="$(modinfo -n nct6687 2>/dev/null || true)"
if [[ -z "$module_path" || ! -f "$module_path" ]]; then
  module_path="$(find "$MODULE_DIR" -type f -name 'nct6687.ko*' -print -quit 2>/dev/null || true)"
fi
if [[ -n "$module_path" && -f "$module_path" ]]; then
  bc250_verify_module_vermagic "$module_path" "$KERNEL_RELEASE"
  info "nct6687 module is installed for $KERNEL_RELEASE"
else
  error "nct6687 was not installed for the active kernel"
  exit 22
fi
