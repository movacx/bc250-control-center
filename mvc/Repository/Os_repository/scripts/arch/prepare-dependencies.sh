#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../common/common.sh
source "$SCRIPT_DIR/../common/common.sh"
# shellcheck source=../common/aur.sh
source "$SCRIPT_DIR/../common/aur.sh"
parse_component "$@"

install_runtime() {
  bold "${BC250_OS_LABEL:-Arch family}: installing BC250 runtime dependencies"
  local packages=(
    python python-pyqt6 python-psutil lm_sensors stress git pciutils libdrm
    vulkan-tools mesa-utils polkit kmod curl ca-certificates tar zstd
    base-devel fakeroot debugedit
  )
  as_root pacman -Syu --needed --noconfirm "${packages[@]}"
  verify_command python3
  verify_command git
  verify_command sensors
  verify_command stress
  verify_command makepkg
  verify_command fakeroot
}

install_governor() {
  if have cyan-skillfish-governor-smu; then
    info "cyan-skillfish-governor-smu already installed"
    return 0
  fi
  install_aur_package cyan-skillfish-governor-smu
  hash -r
  verify_command cyan-skillfish-governor-smu
}

install_stress() {
  as_root pacman -S --needed --noconfirm stress
  verify_command stress
}

install_sensors() {
  as_root pacman -S --needed --noconfirm lm_sensors
  verify_command sensors
}

install_umr() {
  if have umr; then
    info "UMR already installed: $(command -v umr)"
    return 0
  fi
  if ! as_root pacman -S --needed --noconfirm umr; then
    warn "umr is not available from pacman; trying AUR"
    install_aur_package umr
  fi
  if ! have umr && [[ -n "${BC250_CU_MANAGER_SCRIPT:-}" && -x "${BC250_CU_MANAGER_SCRIPT}" ]]; then
    warn "Package installation did not provide UMR; trying bc250-cu-live-manager fallback"
    as_root "${BC250_CU_MANAGER_SCRIPT}" install-umr
  fi
  hash -r
  verify_command umr
}

print_credits
component_is runtime && install_runtime
component_is governor && install_governor
component_is stress && install_stress
component_is sensors && install_sensors
component_is umr && install_umr

bold "Arch-family dependency preparation completed"
