#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../common/common.sh"
source "$SCRIPT_DIR/../common/aur.sh"
parse_component "$@"

prepare_steamos_pacman() {
  bold "Preparing SteamOS writable package layer"
  warn "SteamOS updates can replace packages installed into the unlocked root filesystem."
  if have steamos-readonly; then
    as_root steamos-readonly disable
  fi
  as_root timedatectl set-ntp true || true
  as_root pacman-key --init || true
  as_root pacman-key --populate holo || true
  as_root pacman-key --populate archlinux || true
  as_root pacman -Syy --noconfirm
}

install_runtime() {
  prepare_steamos_pacman
  local packages=(
    python python-pyqt6 python-psutil lm_sensors stress git pciutils libdrm
    vulkan-tools mesa-utils polkit kmod curl ca-certificates tar zstd
    base-devel fakeroot debugedit gcc make pkgconf pahole dkms
  )
  as_root pacman -S --needed --noconfirm "${packages[@]}"
  verify_command makepkg
  verify_command fakeroot
  ensure_aur_helper
}

install_governor() {
  if have cyan-skillfish-governor-smu; then info "Governor already installed"; return 0; fi
  prepare_steamos_pacman
  install_aur_package cyan-skillfish-governor-smu
  hash -r
  verify_command cyan-skillfish-governor-smu
}
install_stress() { prepare_steamos_pacman; as_root pacman -S --needed --noconfirm stress; verify_command stress; }
install_sensors() { prepare_steamos_pacman; as_root pacman -S --needed --noconfirm lm_sensors; verify_command sensors; }
install_umr() {
  if have umr; then info "UMR already installed"; return 0; fi
  prepare_steamos_pacman
  if ! as_root pacman -S --needed --noconfirm umr; then
    install_aur_package umr
  fi
  if ! have umr && [[ -n "${BC250_CU_MANAGER_SCRIPT:-}" && -x "${BC250_CU_MANAGER_SCRIPT}" ]]; then
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
bold "SteamOS dependency preparation completed"
warn "Re-run Prepare dependencies after major SteamOS updates if the writable root packages were replaced."
