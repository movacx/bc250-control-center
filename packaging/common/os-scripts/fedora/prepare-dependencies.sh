#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../common/common.sh"
parse_component "$@"

runtime_packages=(
  python3 python3-pyqt6 qt6-qtsvg python3-psutil git pciutils libdrm
  vulkan-tools polkit kmod curl ca-certificates make gcc elfutils-libelf-devel
  kernel-devel kernel-headers dkms dnf-plugins-core jq
)

install_runtime() {
  bold "${BC250_OS_LABEL:-Fedora family}: installing BC250 runtime dependencies"
  as_root dnf install -y "${runtime_packages[@]}"
  as_root dnf install -y glx-utils || warn "Optional OpenGL diagnostics package glx-utils is unavailable"
}

install_governor() {
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

check_runtime() { verify_command python3; verify_command git; verify_command lspci; verify_command pkexec; verify_command jq; python3 -c 'import PyQt6, psutil'; }
check_governor() { verify_command cyan-skillfish-governor-smu; }
check_stress() { verify_command stress; }
check_sensors() { verify_command sensors; }
check_umr() { verify_command umr; }
plan_runtime() { plan_packages runtime dnf "${runtime_packages[@]}"; echo "PLAN optional=glx-utils"; }
plan_governor() { plan_packages governor copr cyan-skillfish-governor-smu; }
plan_stress() { plan_packages stress dnf stress; }
plan_sensors() { plan_packages sensors dnf lm_sensors; }
plan_umr() { plan_packages umr dnf/fallback umr; }

print_credits
component_action runtime install_runtime check_runtime plan_runtime
component_action governor install_governor check_governor plan_governor
component_action stress install_stress check_stress plan_stress
component_action sensors install_sensors check_sensors plan_sensors
component_action umr install_umr check_umr plan_umr
finish_operation "Fedora"
