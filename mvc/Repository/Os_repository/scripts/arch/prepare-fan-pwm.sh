#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../common/common.sh"
source "$SCRIPT_DIR/../common/aur.sh"

SOURCE_DIR="${BC250_NCT6687_SOURCE_DIR:-$BC250_TOOLS_DIR/nct6687d}"
KERNEL_RELEASE="$(uname -r)"
MODULE_DIR="/usr/lib/modules/$KERNEL_RELEASE"
[[ -d "$MODULE_DIR" ]] || MODULE_DIR="/lib/modules/$KERNEL_RELEASE"

bold "${BC250_OS_LABEL:-Arch family}: preparing nct6687 PWM driver"
ensure_arch_build_toolchain
as_root pacman -S --needed --noconfirm lm_sensors dkms kmod

kernel_package="$(pacman -Qqo "$MODULE_DIR" 2>/dev/null | head -n 1 || true)"
headers_package=""
if [[ -n "$kernel_package" ]]; then
  headers_package="${kernel_package}-headers"
  info "Detected kernel package: $kernel_package; headers candidate: $headers_package"
  as_root pacman -S --needed --noconfirm "$headers_package" || headers_package=""
fi
if [[ ! -e "$MODULE_DIR/build/Makefile" ]]; then
  warn "Exact kernel headers were not resolved; trying linux-headers as a fallback"
  as_root pacman -S --needed --noconfirm linux-headers || true
fi
if [[ ! -e "$MODULE_DIR/build/Makefile" ]]; then
  error "Missing build tree for $KERNEL_RELEASE. Install headers matching the active kernel and retry."
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
if modinfo nct6687 >/dev/null 2>&1 || find "$MODULE_DIR" -type f -name 'nct6687.ko*' -print -quit | grep -q .; then
  info "nct6687 module is installed for $KERNEL_RELEASE"
else
  error "nct6687 was not installed for the active kernel"
  exit 22
fi
