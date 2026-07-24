#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../common/common.sh"
parse_component "$@"

install_runtime() {
  bold "${BC250_OS_LABEL:-Fedora family}: installing BC250 runtime dependencies"
  local packages=(
    python3 python3-pyqt6 python3-psutil lm_sensors stress git pciutils libdrm
    vulkan-tools polkit kmod curl ca-certificates make gcc elfutils-libelf-devel
    kernel-devel kernel-headers dkms dnf-plugins-core
  )
  as_root dnf install -y "${packages[@]}"
  as_root dnf install -y glx-utils || warn "Optional OpenGL diagnostics package glx-utils is unavailable"
}

install_governor() {
  if have cyan-skillfish-governor-smu; then info "Governor already installed"; return 0; fi
  as_root dnf -y copr enable filippor/bazzite
  as_root dnf install -y cyan-skillfish-governor-smu
  hash -r
  verify_command cyan-skillfish-governor-smu
}
install_stress() { as_root dnf install -y stress; verify_command stress; }
install_sensors() { as_root dnf install -y lm_sensors; verify_command sensors; }
install_umr() {
  if have umr; then info "UMR already installed"; return 0; fi
  as_root dnf install -y umr || true
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
bold "Fedora dependency preparation completed"
