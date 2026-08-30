#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../common/common.sh"
parse_component "$@"

runtime_core_packages=(
  python3 python3-pyqt6 libqt6svg6 python3-psutil git pciutils
  libdrm2 libdrm-amdgpu1 curl ca-certificates dbus dbus-user-session kmod jq
)
runtime_optional_diagnostics=(mesa-utils vulkan-tools)
runtime_optional_build=(build-essential dkms dh-dkms)

install_runtime() {
  bold "${BC250_OS_LABEL:-Debian family}: installing BC250 runtime dependencies"
  as_root apt-get update
  as_root apt-get install -y "${runtime_core_packages[@]}"
  as_root apt-get install -y python-is-python3 || warn "python-is-python3 is optional; the application uses python3 directly"
  as_root apt-get install -y "${runtime_optional_diagnostics[@]}" || warn "Optional Mesa/Vulkan diagnostics are unavailable"
  as_root apt-get install -y policykit-1 || as_root apt-get install -y polkitd pkexec
  as_root apt-get install -y "${runtime_optional_build[@]}" || warn "DKMS build tools are unavailable; PWM support will remain disabled"
  if ! as_root apt-get install -y "linux-headers-$(uname -r)"; then
    warn "Matching kernel headers are unavailable. Monitoring will work, but DKMS/PWM features remain disabled until headers are installed."
  fi
}

install_governor() (
  local version="${BC250_GOVERNOR_SMU_VERSION:-0.4.12}"
  local workdir
  workdir="$(mktemp -d)"
  trap 'rm -rf "$workdir"' EXIT
  local deb="cyan-skillfish-governor-smu_${version}-1_amd64.deb"
  local archive="cyan-skillfish-governor-smu-v${version}-x86_64-linux.tar.gz"
  local base_url="https://github.com/filippor/cyan-skillfish-governor/releases/download/v${version}"

  as_root apt-get update
  as_root apt-get install -y curl ca-certificates dbus
  if ! have busctl; then
    if bc250_openrc_active; then
      # Devuan/OpenRC must not be converted to systemd just to obtain the
      # inspection client. elogind supplies busctl on Debian-family OpenRC
      # systems without replacing the init system.
      as_root apt-get install -y elogind
    else
      as_root apt-get install -y systemd
    fi
  fi
  verify_command busctl
  local package_current=0 installation_complete=0
  if dpkg-query -W -f='${Status} ${Version}\n' cyan-skillfish-governor-smu 2>/dev/null | \
     grep -q "^install ok installed ${version}-"; then
    package_current=1
  fi
  if have cyan-skillfish-governor-smu; then
    if bc250_openrc_active; then
      [[ -f /etc/init.d/cyan-skillfish-governor-smu ]] && installation_complete=1
    elif systemctl cat cyan-skillfish-governor-smu.service >/dev/null 2>&1; then
      installation_complete=1
    fi
  fi

  if (( package_current == 1 && installation_complete == 1 )); then
    info "cyan-skillfish-governor-smu $version is already current"
  elif run curl --fail --location --retry 3 --output "$workdir/$deb" "$base_url/$deb"; then
    if (( package_current == 1 )); then
      warn "The Cyan package database is current, but its binary or systemd unit is missing; repairing the package"
      as_root apt-get install --reinstall -y "$workdir/$deb"
    else
      as_root apt-get install -y "$workdir/$deb"
    fi
  elif run curl --fail --location --retry 3 --output "$workdir/$archive" "$base_url/$archive"; then
    run tar -xf "$workdir/$archive" -C "$workdir"
    local installer
    installer="$(find "$workdir" -path '*/scripts/install.sh' -type f | head -n 1)"
    [[ -n "$installer" ]] || { error "Governor archive did not contain scripts/install.sh"; return 1; }
    as_root bash "$installer"
  else
    error "Unable to download the pinned cyan-skillfish-governor-smu release v$version"
    return 1
  fi
  hash -r
  verify_command cyan-skillfish-governor-smu
)

install_stress() { as_root apt-get update; as_root apt-get install -y stress; verify_command stress; }
install_sensors() { as_root apt-get update; as_root apt-get install -y lm-sensors; verify_command sensors; }
install_umr() {
  if have umr; then info "UMR already installed"; return 0; fi
  as_root apt-get update
  as_root apt-get install -y umr || true
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
plan_runtime() { plan_packages runtime apt "${runtime_core_packages[@]}" policykit-1 python-is-python3 "${runtime_optional_diagnostics[@]}" "${runtime_optional_build[@]}" "linux-headers-$(uname -r)"; }
plan_governor() { plan_packages governor upstream-release cyan-skillfish-governor-smu; }
plan_stress() { plan_packages stress apt stress; }
plan_sensors() { plan_packages sensors apt lm-sensors; }
plan_umr() { plan_packages umr apt/fallback umr; }

print_credits
component_action runtime install_runtime check_runtime plan_runtime
component_action governor install_governor check_governor plan_governor
component_action stress install_stress check_stress plan_stress
component_action sensors install_sensors check_sensors plan_sensors
component_action umr install_umr check_umr plan_umr
finish_operation "Debian-family"
