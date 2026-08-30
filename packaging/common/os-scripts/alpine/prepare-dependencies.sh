#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../common/common.sh"
parse_component "$@"

runtime_packages=(
  bash python3 py3-qt6 py3-psutil qt6-qtbase qt6-qtsvg git pciutils
  libdrm mesa-dri-gallium vulkan-tools polkit kmod curl ca-certificates tar
  zstd dbus dbus-openrc busctl jq build-base linux-headers dkms
)

apk_install() { as_root apk add --no-progress "$@"; }

install_runtime() {
  bold "${BC250_OS_LABEL:-Alpine Linux}: installing BC250 runtime dependencies"
  apk_install "${runtime_packages[@]}"
  verify_command python3
  verify_command git
  verify_command lspci
  verify_command pkexec
}

# Cyan's reviewed, checksummed release is installed by the common Control
# Center integration after this dependency stage.  Do not substitute an
# unreviewed community package here.
install_governor() {
  # ``dbus`` provides the daemon but Alpine keeps its OpenRC integration and
  # the D-Bus inspection client in separate packages.  Cyan needs both: the
  # service depends on the system bus and the reviewed setup reloads policy
  # and verifies the governor through ``busctl``.
  apk_install curl ca-certificates tar dbus dbus-openrc busctl polkit
  verify_command busctl
}
# Alpine packages stress-ng, whose command-line contract is not interchangeable
# with the upstream CPU detector's required ``stress`` binary.  Failing here is
# intentional: silently installing another tool would make CPU OC look ready
# and then fail later under load.
install_stress() {
  error "Alpine does not ship the exact 'stress' binary required by bc250_smu_oc. CPU OC remains unavailable until a compatible stress binary is supplied."
  return 69
}
install_sensors() { apk_install lm_sensors; verify_command sensors; }
install_umr() {
  if have umr; then info "UMR already installed"; return 0; fi
  apk_install umr || true
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
plan_runtime() { plan_packages runtime apk "${runtime_packages[@]}"; }
plan_governor() { plan_packages governor upstream-release curl ca-certificates tar dbus dbus-openrc busctl polkit; }
plan_stress() { plan_packages stress unavailable "exact stress binary (not stress-ng)"; }
plan_sensors() { plan_packages sensors apk lm_sensors; }
plan_umr() { plan_packages umr apk/fallback umr; }

print_credits
component_action runtime install_runtime check_runtime plan_runtime
component_action governor install_governor check_governor plan_governor
component_action stress install_stress check_stress plan_stress
component_action sensors install_sensors check_sensors plan_sensors
component_action umr install_umr check_umr plan_umr
finish_operation "Alpine"
