#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../common/common.sh"
parse_component "$@"
REBOOT_REQUIRED=0

package_is_active() {
  rpm -q "$1" >/dev/null 2>&1
}

package_is_pending() {
  local package="$1"
  have rpm-ostree || return 1
  rpm-ostree status --json 2>/dev/null | python3 -c '
import json
import sys
package = sys.argv[1]
try:
    payload = json.load(sys.stdin)
except Exception:
    raise SystemExit(1)
for deployment in payload.get("deployments", []):
    if deployment.get("booted"):
        continue
    requested = set(deployment.get("requested-packages") or [])
    requested.update(deployment.get("packages") or [])
    if package in requested:
        raise SystemExit(0)
raise SystemExit(1)
' "$package"
}

enable_governor_repo() {
  if [[ -f /etc/yum.repos.d/_copr:copr.fedorainfracloud.org:filippor:bazzite.repo ]] || \
     grep -Rqs 'copr.fedorainfracloud.org.*filippor.*bazzite' /etc/yum.repos.d 2>/dev/null; then
    return 0
  fi
  if have dnf5; then
    as_root dnf5 -y copr enable filippor/bazzite
  elif have dnf; then
    as_root dnf -y copr enable filippor/bazzite
  else
    error "Neither dnf5 nor dnf is available to enable the governor COPR"
    return 1
  fi
}

layer_packages() {
  local missing=()
  local pending=()
  local package
  for package in "$@"; do
    if package_is_active "$package"; then
      continue
    elif package_is_pending "$package"; then
      pending+=("$package")
    else
      missing+=("$package")
    fi
  done

  if [[ ${#pending[@]} -gt 0 ]]; then
    info "Already queued for next boot: ${pending[*]}"
    REBOOT_REQUIRED=1
  fi
  if [[ ${#missing[@]} -eq 0 ]]; then
    return 0
  fi

  bold "Layering packages into one rpm-ostree deployment"
  as_root rpm-ostree install --idempotent "${missing[@]}"
  REBOOT_REQUIRED=1
}

runtime_packages=(
  python3 python3-pyqt6 python3-psutil lm_sensors stress git pciutils libdrm
  vulkan-tools polkit kmod make gcc elfutils-libelf-devel kernel-devel dkms umr
)

install_all() {
  bold "${BC250_OS_LABEL:-Bazzite}: preparing BC250 host dependencies"
  enable_governor_repo
  layer_packages "${runtime_packages[@]}" cyan-skillfish-governor-smu
}

install_runtime() {
  bold "${BC250_OS_LABEL:-Bazzite}: preparing runtime dependencies"
  layer_packages "${runtime_packages[@]}"
}

install_governor() {
  if have cyan-skillfish-governor-smu; then
    info "Governor already active in the current deployment"
    return 0
  fi
  enable_governor_repo
  layer_packages cyan-skillfish-governor-smu
}

install_stress() { have stress || layer_packages stress; }
install_sensors() { have sensors || layer_packages lm_sensors; }
install_umr() { have umr || layer_packages umr; }

print_credits
case "$BC250_COMPONENT" in
  all) install_all ;;
  runtime) install_runtime ;;
  governor) install_governor ;;
  stress) install_stress ;;
  sensors) install_sensors ;;
  umr) install_umr ;;
  *) error "Unsupported Bazzite component: $BC250_COMPONENT"; exit 2 ;;
esac

if [[ "$REBOOT_REQUIRED" == "1" ]]; then
  bold "Bazzite deployment prepared"
  warn "A new rpm-ostree deployment is ready. Reboot once; the downloaded BC250 tools are already prepared and you do not need to press Prepare dependencies again."
  echo "BC250_REBOOT_REQUIRED=1"
  exit 20
fi

bold "Bazzite dependencies are active in the current deployment"
