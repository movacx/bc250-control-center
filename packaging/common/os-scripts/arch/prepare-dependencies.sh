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

# Only what is missing, and never the whole system on the way. This step used
# to run ``pacman -Syu`` even when every package was installed: on a CachyOS
# board it upgraded 22 packages including the kernel, removed the running
# kernel's modules and headers, and the fan PWM step right after it failed.
# Arch supports installing from the local database without refreshing it; a
# full update is the fallback only when that database cannot provide a
# missing package, because refreshing without upgrading is a partial upgrade.
install_runtime() {
  bold "${BC250_OS_LABEL:-Arch family}: installing BC250 runtime dependencies"
  local missing=() running_kernel
  mapfile -t missing < <(pacman -T "${runtime_packages[@]}" 2>/dev/null || true)
  if ((${#missing[@]} == 0)); then
    info "Every runtime package is already installed; the system was not updated."
  else
    info "Installing only what is missing (no system update): ${missing[*]}"
    if ! as_root pacman -S --needed --noconfirm "${missing[@]}"; then
      warn "The local package database could not provide: ${missing[*]}"
      warn "Arch installs only from an up-to-date database, so this needs a full system update."
      running_kernel="$(bc250_running_kernel_release)"
      as_root pacman -Syu --needed --noconfirm "${missing[@]}"
      if bc250_running_kernel_replaced "$running_kernel"; then
        warn "The update replaced the running kernel ($running_kernel)."
        warn "Reboot before preparing kernel modules such as the fan PWM driver."
      fi
    fi
  fi
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
  if ! as_root pacman -S --needed --noconfirm stress; then
    # Artix mirrors only its own repositories and ships stress-ng, whose
    # interface bc250_smu_oc cannot use; stress itself is in Arch's [extra].
    if ! pacman -Si stress >/dev/null 2>&1; then
      error "The stress package is not in any enabled pacman repository."
      error "On Artix, install artix-archlinux-support, enable Arch's [extra] in /etc/pacman.conf, then retry."
    fi
    return 1
  fi
  verify_command stress
}

install_sensors() {
  as_root pacman -S --needed --noconfirm lm_sensors
  verify_command sensors
}

# umr links against LLVM. When the distribution moves to a new LLVM, a umr that
# was built here (AUR) stays installed and stops starting, and "it is
# installed" is no longer a reason to leave it alone. The package that
# provides it, in the order the AUR names them, is what has to be built again.
rebuild_broken_umr() {
  local package
  if pacman -Qq umr-git >/dev/null 2>&1; then
    package=umr-git
  else
    package=umr
  fi
  warn "UMR is installed but does not start: a library it was built against was replaced (for example CachyOS moving to LLVM 23)."
  warn "Rebuilding $package against the libraries that are installed now."
  install_aur_package "$package" rebuild || true
  hash -r
  if ! binary_runs umr; then
    error "UMR still does not start after rebuilding it:"
    ldd "$(command -v umr)" 2>&1 | grep 'not found' | sed 's/^/  /' >&2 || true
    return 1
  fi
}

install_umr() {
  if [[ "${BC250_FORCE_UMR_FALLBACK:-0}" != "1" ]] && have umr; then
    if binary_runs umr; then
      info "UMR already installed: $(command -v umr)"
      return 0
    fi
    rebuild_broken_umr
    return
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
check_umr() {
  verify_command umr || return 1
  binary_runs umr || { error "umr is installed but does not start: a library it needs is missing. Prepare UMR again to rebuild it."; return 1; }
}
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
