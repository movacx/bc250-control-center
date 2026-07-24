#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../common/common.sh"
parse_component "$@"

install_runtime() {
  bold "${BC250_OS_LABEL:-Debian family}: installing BC250 runtime dependencies"
  as_root apt-get update
  local core_packages=(
    python3 python3-pyqt6 python3-psutil lm-sensors stress git pciutils
    libdrm2 libdrm-amdgpu1 curl ca-certificates dbus dbus-user-session kmod
  )
  as_root apt-get install -y "${core_packages[@]}"
  as_root apt-get install -y python-is-python3 || warn "python-is-python3 is optional; the application uses python3 directly"
  as_root apt-get install -y mesa-utils vulkan-tools || warn "Optional Mesa/Vulkan diagnostics are unavailable"
  as_root apt-get install -y policykit-1 || as_root apt-get install -y polkitd pkexec
  as_root apt-get install -y build-essential dkms dh-dkms || warn "DKMS build tools are unavailable; PWM support will remain disabled"
  if ! as_root apt-get install -y "linux-headers-$(uname -r)"; then
    warn "Matching kernel headers are unavailable. Monitoring will work, but DKMS/PWM features remain disabled until headers are installed."
  fi
}

install_governor() (
  if have cyan-skillfish-governor-smu; then
    info "cyan-skillfish-governor-smu already installed"
    return 0
  fi
  local version="${BC250_GOVERNOR_SMU_VERSION:-0.4.11}"
  local workdir
  workdir="$(mktemp -d)"
  trap 'rm -rf "$workdir"' EXIT
  local deb="cyan-skillfish-governor-smu_${version}-1_amd64.deb"
  local archive="cyan-skillfish-governor-smu-v${version}-x86_64-linux.tar.gz"
  local base_url="https://github.com/filippor/cyan-skillfish-governor/releases/download/v${version}"

  as_root apt-get update
  as_root apt-get install -y curl ca-certificates dbus
  if run curl --fail --location --retry 3 --output "$workdir/$deb" "$base_url/$deb"; then
    as_root apt-get install -y "$workdir/$deb"
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

print_credits
component_is runtime && install_runtime
component_is governor && install_governor
component_is stress && install_stress
component_is sensors && install_sensors
component_is umr && install_umr
bold "Debian-family dependency preparation completed"
