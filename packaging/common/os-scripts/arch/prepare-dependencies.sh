#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../common/common.sh
source "$SCRIPT_DIR/../common/common.sh"
# shellcheck source=../common/aur.sh
source "$SCRIPT_DIR/../common/aur.sh"
parse_component "$@"

runtime_packages=(
  python python-pyqt6 qt6-svg python-psutil git pciutils libdrm
  vulkan-tools mesa-utils polkit kmod curl ca-certificates tar zstd
  jq base-devel fakeroot debugedit
)

install_runtime() {
  bold "${BC250_OS_LABEL:-Arch family}: installing BC250 runtime dependencies"
  as_root pacman -Syu --needed --noconfirm "${runtime_packages[@]}"
  verify_command python3
  verify_command git
  verify_command makepkg
  verify_command fakeroot
  verify_command jq
}

install_governor() {
  # AUR helpers compare the installed package with the current PKGBUILD and
  # update it when needed. --needed keeps an already-current build idempotent.
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
  if [[ "${BC250_FORCE_UMR_FALLBACK:-0}" != "1" ]] && have umr; then
    info "UMR already installed: $(command -v umr)"
    return 0
  fi
  if ! as_root pacman -S --needed --noconfirm umr; then
    warn "umr is not available from pacman; trying AUR"
    if ! install_aur_package umr; then
      warn "AUR installation did not provide UMR; trying the BC250 live-manager fallback"
    fi
  fi
  if { [[ "${BC250_FORCE_UMR_FALLBACK:-0}" == "1" ]] || ! have umr; } && [[ -n "${BC250_CU_MANAGER_SCRIPT:-}" && -x "${BC250_CU_MANAGER_SCRIPT}" ]]; then
    warn "Package installation did not provide UMR; trying bc250-cu-live-manager fallback"
    run "${BC250_CU_MANAGER_SCRIPT}" install-umr
  fi
  hash -r
  verify_command umr
}

check_runtime() { verify_command python3; verify_command git; verify_command lspci; verify_command pkexec; verify_command jq; python3 -c 'import PyQt6, psutil'; }
check_governor() { verify_command cyan-skillfish-governor-smu; }
check_stress() { verify_command stress; }
check_sensors() { verify_command sensors; }
check_umr() { verify_command umr; }
plan_runtime() { plan_packages runtime pacman "${runtime_packages[@]}"; }
plan_governor() { plan_packages governor aur cyan-skillfish-governor-smu; }
plan_stress() { plan_packages stress pacman stress; }
plan_sensors() { plan_packages sensors pacman lm_sensors; }
plan_umr() { plan_packages umr pacman/aur umr; }

print_credits
component_action runtime install_runtime check_runtime plan_runtime
component_action governor install_governor check_governor plan_governor
component_action stress install_stress check_stress plan_stress
component_action sensors install_sensors check_sensors plan_sensors
component_action umr install_umr check_umr plan_umr

finish_operation "Arch-family"
