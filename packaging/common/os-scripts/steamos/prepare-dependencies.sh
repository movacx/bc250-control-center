#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../common/common.sh"
source "$SCRIPT_DIR/../common/aur.sh"
source "$SCRIPT_DIR/../common/steamos-root.sh"
parse_component "$@"

runtime_packages=(
  python python-pyqt6 qt6-svg python-psutil git pciutils libdrm
  vulkan-tools mesa-utils polkit kmod curl ca-certificates tar zstd
  base-devel fakeroot debugedit gcc make pkgconf pahole dkms jq
)

BC250_STEAMOS_PACMAN_PREPARED=0
cleanup_steamos_dependencies() {
  local status=$?
  trap - EXIT
  if bc250_steamos_restore_root "$status"; then exit 0; else exit $?; fi
}
trap cleanup_steamos_dependencies EXIT

prepare_steamos_pacman() {
  [[ "$BC250_STEAMOS_PACMAN_PREPARED" == "1" ]] && return 0
  bold "Preparing SteamOS writable package layer"
  warn "SteamOS updates can replace packages installed into the unlocked root filesystem."
  bc250_steamos_unlock_root
  as_root timedatectl set-ntp true || true
  as_root pacman-key --init
  as_root pacman-key --populate holo 2>/dev/null || as_root pacman-key --populate
  as_root pacman-key --populate archlinux 2>/dev/null || true
  as_root pacman -Syy --noconfirm
  BC250_STEAMOS_PACMAN_PREPARED=1
}

install_runtime() {
  prepare_steamos_pacman
  as_root pacman -S --needed --noconfirm "${runtime_packages[@]}"
  verify_command makepkg
  verify_command fakeroot
}

install_governor() {
  # Control Center stages Cyan from the official checksummed upstream release
  # immediately after this distro step. Avoid an unnecessary AUR/package-layer
  # installation on SteamOS: the common installer supplies the binary, service,
  # D-Bus policy and default TOML when they are missing.
  if have cyan-skillfish-governor-smu; then
    info "Existing Cyan installation detected; the verified upstream runtime will be reconciled next"
  else
    info "SteamOS: Cyan will be installed from the verified official upstream release"
  fi
}
install_stress() { prepare_steamos_pacman; as_root pacman -S --needed --noconfirm stress; verify_command stress; }
install_sensors() { prepare_steamos_pacman; as_root pacman -S --needed --noconfirm lm_sensors; verify_command sensors; }
install_umr() {
  if [[ "${BC250_FORCE_UMR_FALLBACK:-0}" != "1" ]] && have umr; then info "UMR already installed"; return 0; fi
  prepare_steamos_pacman
  if ! as_root pacman -S --needed --noconfirm umr; then
    if ! install_aur_package umr; then
      warn "AUR installation did not provide UMR; trying the SteamOS BC250 live-manager fallback"
    fi
  fi
  if { [[ "${BC250_FORCE_UMR_FALLBACK:-0}" == "1" ]] || ! have umr; } && [[ -n "${BC250_CU_MANAGER_SCRIPT:-}" && -x "${BC250_CU_MANAGER_SCRIPT}" ]]; then
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
plan_runtime() { plan_packages runtime pacman "${runtime_packages[@]}"; warn "SteamOS root is modified only in apply mode and may be replaced by an OS update."; }
plan_governor() { plan_packages governor verified-upstream cyan-skillfish-governor-smu; }
plan_stress() { plan_packages stress pacman stress; }
plan_sensors() { plan_packages sensors pacman lm_sensors; }
plan_umr() { plan_packages umr pacman/aur/fallback umr; }

print_credits
component_action runtime install_runtime check_runtime plan_runtime
component_action governor install_governor check_governor plan_governor
component_action stress install_stress check_stress plan_stress
component_action sensors install_sensors check_sensors plan_sensors
component_action umr install_umr check_umr plan_umr
finish_operation "SteamOS"
if [[ "$BC250_MODE" == "apply" ]]; then
  warn "Re-run Prepare dependencies after major SteamOS updates if the writable root packages were replaced."
fi
