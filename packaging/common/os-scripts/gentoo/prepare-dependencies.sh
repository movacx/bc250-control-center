#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../common/common.sh"
parse_component "$@"

runtime_packages=(
  dev-lang/python dev-python/pyqt6 dev-python/psutil dev-qt/qtbase dev-qt/qtsvg
  dev-vcs/git sys-apps/pciutils media-libs/libdrm media-libs/mesa
  dev-util/vulkan-tools sys-auth/polkit sys-apps/kmod net-misc/curl
  app-misc/ca-certificates app-arch/tar app-arch/zstd app-misc/jq sys-apps/dbus sys-apps/systemd-utils
  sys-devel/gcc sys-kernel/linux-headers sys-kernel/dkms
)

emerge_install() { as_root emerge --ask=n --verbose --update --deep --newuse "$@"; }

install_runtime() {
  bold "${BC250_OS_LABEL:-Gentoo Linux}: installing BC250 runtime dependencies"
  emerge_install "${runtime_packages[@]}"
  verify_command python3
  verify_command git
  verify_command lspci
  verify_command pkexec
}

# The reviewed Cyan release is staged by the common integration after this
# dependency stage.  Portage merely provides its runtime prerequisites.
install_governor() {
  # Gentoo deliberately splits non-init systemd utilities for OpenRC hosts.
  # Cyan uses busctl for policy reload and verified range read-back; installing
  # only dbus would otherwise leave a late, ambiguous failure.
  emerge_install net-misc/curl app-misc/ca-certificates app-arch/tar sys-apps/dbus sys-apps/systemd-utils sys-auth/polkit
  verify_command busctl
}
install_stress() { emerge_install app-benchmarks/stress; verify_command stress; }
install_sensors() { emerge_install sys-apps/lm-sensors; verify_command sensors; }
install_umr() {
  if have umr; then info "UMR already installed"; return 0; fi
  warn "Gentoo does not provide a universally named UMR package; trying the reviewed CU-manager fallback."
  if [[ -n "${BC250_CU_MANAGER_SCRIPT:-}" && -x "${BC250_CU_MANAGER_SCRIPT}" ]]; then
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
plan_runtime() { plan_packages runtime emerge "${runtime_packages[@]}"; }
plan_governor() { plan_packages governor upstream-release net-misc/curl sys-apps/dbus sys-apps/systemd-utils sys-auth/polkit; }
plan_stress() { plan_packages stress emerge app-benchmarks/stress; }
plan_sensors() { plan_packages sensors emerge sys-apps/lm-sensors; }
plan_umr() { plan_packages umr reviewed-fallback bc250-cu-live-manager; }

print_credits
component_action runtime install_runtime check_runtime plan_runtime
component_action governor install_governor check_governor plan_governor
component_action stress install_stress check_stress plan_stress
component_action sensors install_sensors check_sensors plan_sensors
component_action umr install_umr check_umr plan_umr
finish_operation "Gentoo-family"
