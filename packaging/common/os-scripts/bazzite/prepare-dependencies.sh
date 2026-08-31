#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../common/common.sh"
parse_component "$@"
REBOOT_REQUIRED=0

print_reboot_notice() {
  echo
  echo "=========================================================================="
  echo "= REBOOT REQUIRED / REINICIO REQUERIDO / ТРЕБУЕТСЯ ПЕРЕЗАГРУЗКА"
  echo "="
  echo "= EN: Restart the computer once to activate the new Bazzite deployment."
  echo "=     After reboot, run ONLY 'NCT sensors and PWM' to finish setup."
  echo "="
  echo "= ES: Reinicia la computadora una vez para activar el nuevo deployment de Bazzite."
  echo "=     Después del reinicio, ejecuta ÚNICAMENTE 'NCT sensors and PWM' para finalizar."
  echo "="
  echo "= RU: Перезагрузите компьютер один раз, чтобы активировать новое развёртывание Bazzite."
  echo "=     После перезагрузки запустите ТОЛЬКО 'NCT sensors and PWM', чтобы завершить настройку."
  echo "=========================================================================="
  echo
}

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
  python3 python3-pyqt6 qt6-qtsvg python3-psutil git pciutils libdrm
  vulkan-tools polkit kmod make gcc elfutils-libelf-devel kernel-devel dkms
  jq
)

install_all() {
  bold "${BC250_OS_LABEL:-Bazzite}: preparing BC250 host dependencies"
  enable_governor_repo
  layer_packages "${runtime_packages[@]}" lm_sensors stress umr cyan-skillfish-governor-smu
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

check_runtime() { verify_command python3; verify_command git; verify_command lspci; verify_command pkexec; verify_command jq; python3 -c 'import PyQt6, psutil'; }
check_governor() { verify_command cyan-skillfish-governor-smu; }
check_stress() { verify_command stress; }
check_sensors() { verify_command sensors; }
check_umr() { verify_command umr; }
plan_runtime() { plan_packages runtime rpm-ostree "${runtime_packages[@]}"; }
plan_governor() { plan_packages governor rpm-ostree/copr cyan-skillfish-governor-smu; }
plan_stress() { plan_packages stress rpm-ostree stress; }
plan_sensors() { plan_packages sensors rpm-ostree lm_sensors; }
plan_umr() { plan_packages umr rpm-ostree umr; }

print_credits
if [[ "$BC250_MODE" == "apply" && "$BC250_COMPONENT" == "all" ]]; then
  install_all
  result_event "ok" "all" 0 "apply completed"
else
  component_action runtime install_runtime check_runtime plan_runtime
  component_action governor install_governor check_governor plan_governor
  component_action stress install_stress check_stress plan_stress
  component_action sensors install_sensors check_sensors plan_sensors
  component_action umr install_umr check_umr plan_umr
fi

if [[ "$BC250_MODE" == "apply" && "$REBOOT_REQUIRED" == "1" ]]; then
  bold "Bazzite deployment prepared"
  print_reboot_notice
  echo "BC250_REBOOT_REQUIRED=1"
  exit 20
fi

finish_operation "Bazzite"
