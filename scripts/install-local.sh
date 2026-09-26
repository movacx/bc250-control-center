#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
STEAMOS_ROOT_HELPER="$ROOT_DIR/scripts/system/steamos-root.sh"
USER_PATHS_HELPER="$ROOT_DIR/scripts/lib/user-paths.sh"
if [[ ! -f "$USER_PATHS_HELPER" ]]; then
  echo "Error: missing user path helper: $USER_PATHS_HELPER" >&2
  exit 1
fi
# shellcheck source=lib/user-paths.sh
source "$USER_PATHS_HELPER"
bc250_resolve_user_paths
if [[ -f "$STEAMOS_ROOT_HELPER" ]]; then
  # shellcheck source=steamos-root.sh
  source "$STEAMOS_ROOT_HELPER"
fi

restore_steamos_install_root() {
  local status="${1:-0}"
  if declare -F bc250_steamos_restore_root >/dev/null 2>&1; then
    bc250_steamos_restore_root "$status"
    return $?
  fi
  return "$status"
}

early_install_cleanup() {
  local status=$?
  trap - EXIT
  if restore_steamos_install_root "$status"; then exit 0; else exit $?; fi
}
trap early_install_cleanup EXIT

if [[ -z "${PREFIX:-}" ]]; then
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    PREFIX="/usr/local"
  else
    PREFIX="$HOME/.local"
  fi
fi

APP_DIR="$PREFIX/share/bc250-control-center"
BIN_DIR="$PREFIX/bin"
DESKTOP_DIR="$PREFIX/share/applications"
ICON_DIR="$PREFIX/share/icons/hicolor"
METAINFO_DIR="$PREFIX/share/metainfo"
SYSTEMD_USER_DIR="$PREFIX/lib/systemd/user"
DOC_DIR="$PREFIX/share/doc/bc250-control-center"
SYSTEM_PRIV_HELPER="/usr/libexec/bc250-control-center/bc250-fan-pwm-helper"
SYSTEM_STEAMOS_GAME_HELPER="/usr/libexec/bc250-control-center/bc250-steamos-game-helper"
SYSTEM_GOVERNOR_CONFIG_HELPER="/usr/libexec/bc250-control-center/bc250-governor-config-helper"
SYSTEM_CORE_UNLOCK_HELPER="/usr/libexec/bc250-control-center/bc250-core-unlock-helper"
SYSTEM_CPU_SMU_HELPER="/usr/libexec/bc250-control-center/bc250-cpu-smu-helper"
SYSTEM_GDDR6_TEMP_HELPER="/usr/libexec/bc250-control-center/bc250-gddr6-temp-helper"
SYSTEM_GDDR6_TEMP_READER="/usr/libexec/bc250-control-center/bc250-gddr6-temp-reader"
SYSTEM_OPENRC_SERVICE_HELPER="/usr/libexec/bc250-control-center/bc250-openrc-service-helper"
SYSTEM_SERVICE_HELPER="/usr/libexec/bc250-control-center/bc250-service-helper"
SYSTEM_MAINTENANCE_HELPER="/usr/libexec/bc250-control-center/bc250-maintenance-helper"
# Installed here, not only by the Decky installer: uninstall-local.sh has
# always removed it, so a local install followed by a local uninstall used
# to delete a root helper this script never placed. The package
# (stage-package-root.sh) already ships it, so this makes the two
# installation paths agree.
SYSTEM_QUICK_ACCESS_HELPER="/usr/libexec/bc250-control-center/bc250-quick-access-helper"
SYSTEM_GPU_LAB_SCRIPT="/usr/libexec/bc250-control-center/bc250-gpu-voltage-lab.sh"
SYSTEM_STEAMOS_AMDGPU_OVERLAY="/usr/libexec/bc250-control-center/bc250-steamos-amdgpu-overlay"
SYSTEM_CYAN_OVERLAY_PREFLIGHT="/usr/libexec/bc250-control-center/bc250-cyan-overlay-preflight"
SYSTEM_CYAN_OVERLAY_DROPIN="/etc/systemd/system/cyan-skillfish-governor-smu.service.d/91-bc250-control-center-overlay-preflight.conf"
SYSTEM_CPU_SMU_VENDOR="/usr/libexec/bc250-control-center/lib/bc250_smu_oc_vendor.zip"
SYSTEM_CPU_SMU_CONFIG="/etc/bc250-smu-oc.conf"
SYSTEM_GOVERNOR_TOML_IMPLEMENTATION="/usr/libexec/bc250-control-center/lib/governor_toml.py"
LEGACY_CORE_UNLOCK_IMPLEMENTATION="/usr/libexec/bc250-control-center/lib/core_unlock.py"
SYSTEM_POLKIT_ACTION="/usr/share/polkit-1/actions/io.github.movacx.bc250-control-center.policy"

BC250_STEAMOS_INSTALL_PACMAN_PREPARED=0

is_steamos_install_local() {
  local text=""
  if [[ -r /etc/os-release ]]; then
    text="$(cat /etc/os-release)"
  elif [[ -r /usr/lib/os-release ]]; then
    text="$(cat /usr/lib/os-release)"
  fi
  printf '%s' "$text" | tr '[:upper:]' '[:lower:]' | grep -Eq 'steamos|steamdeck|holo'
}

prepare_steamos_pacman_install_local() {
  if ! is_steamos_install_local || ! command -v pacman >/dev/null 2>&1; then
    return 0
  fi
  echo "SteamOS detected: preparing writable pacman/keyring layer for GUI dependencies..."
  if declare -F bc250_steamos_unlock_root >/dev/null 2>&1; then
    bc250_steamos_unlock_root
  else
    echo "Error: SteamOS root-state guard is unavailable; refusing host package changes." >&2
    return 70
  fi
  [[ "$BC250_STEAMOS_INSTALL_PACMAN_PREPARED" == "1" ]] && return 0
  sudo timedatectl set-ntp true || true
  sudo pacman-key --init
  sudo pacman-key --populate holo 2>/dev/null || sudo pacman-key --populate
  sudo pacman-key --populate archlinux 2>/dev/null || true
  sudo rm -f /var/cache/pacman/pkg/python-pyqt6-*.pkg.tar.zst /var/cache/pacman/pkg/python-pyqt6-sip-*.pkg.tar.zst 2>/dev/null || true
  sudo pacman -Syy --noconfirm
  BC250_STEAMOS_INSTALL_PACMAN_PREPARED=1
}

if [[ "${EUID:-$(id -u)}" -ne 0 && "$PREFIX" == "$HOME/.local" ]]; then
  SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
fi

if [[ ! -d "$ROOT_DIR/scripts" || ! -d "$ROOT_DIR/packaging/common" ]]; then
  echo "Error: no se encontro la raiz del proyecto BC250 Control Center." >&2
  echo "Script: $SCRIPT_PATH" >&2
  echo "Raiz detectada: $ROOT_DIR" >&2
  echo "Ejecuta el instalador desde el repo/tarball o revisa que existan scripts/ y packaging/common/." >&2
  exit 1
fi

# Fail before package-manager or root-filesystem changes when the source tree
# is incomplete. The full Python/vendor check runs after dependency recovery.
bash "$ROOT_DIR/scripts/qa/validate-install-source.sh" "$ROOT_DIR" --structure-only

missing_python_deps=0
missing_python_deps_command=()
missing_python_deps_command_text=""
missing_python_deps_reboot_notice=0
python_gui_deps_missing=0
# Installed privileged files are verified byte for byte with cmp. It belongs
# to diffutils, which a minimal Arch, CachyOS or openSUSE install need not
# carry, and its absence read as "does not match this build".
if [[ "${BC250_SKIP_PRIVILEGED_HELPER:-0}" != "1" ]] && ! command -v cmp >/dev/null 2>&1; then
  echo "Error: the cmp command (package diffutils) is required to verify the installed files." >&2
  echo "Install diffutils with your package manager, then run this installer again." >&2
  exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "Warning: python3 is not installed or is not in PATH." >&2
  python_gui_deps_missing=1
elif ! python3 - <<'PY' >/dev/null 2>&1
from PyQt6.QtGui import QImageReader
from PyQt6.QtWidgets import QApplication
import psutil
formats = {bytes(fmt).decode("ascii", "ignore").lower() for fmt in QImageReader.supportedImageFormats()}
assert "svg" in formats, "Qt SVG image plugin is missing"
PY
then
  echo "Warning: Python GUI dependencies are missing or Qt SVG support is unavailable. The app will install, but icons or the GUI may fail until they are installed." >&2
  python_gui_deps_missing=1
fi

# A source install on Debian/Ubuntu must cover the same runtime boundary as
# the .deb.  Check the non-Python tools independently: a host may already have
# PyQt6 while still lacking jq or the pkexec authentication frontend.
if command -v apt-get >/dev/null 2>&1 && {
  [[ "$python_gui_deps_missing" -eq 1 ]] ||
  ! command -v jq >/dev/null 2>&1 ||
  ! command -v pkexec >/dev/null 2>&1
}; then
  debian_polkit_package="pkexec"
  if command -v apt-cache >/dev/null 2>&1 && ! apt-cache show pkexec >/dev/null 2>&1; then
    debian_polkit_package="policykit-1"
  fi
  missing_python_deps_command=(
    apt-get install -y python3 python3-pyqt6 libqt6svg6 python3-psutil
    "$debian_polkit_package" jq
  )
  missing_python_deps=1
elif [[ "$python_gui_deps_missing" -eq 1 ]]; then
  if [[ -e /run/ostree-booted ]] && command -v rpm-ostree >/dev/null 2>&1; then
    missing_python_deps_command=(rpm-ostree install --idempotent python3-pyqt6 qt6-qtsvg python3-psutil)
    missing_python_deps_reboot_notice=1
  elif command -v dnf >/dev/null 2>&1; then
    missing_python_deps_command=(dnf install -y python3-pyqt6 qt6-qtsvg python3-psutil)
  elif command -v pacman >/dev/null 2>&1; then
    missing_python_deps_command=(pacman -S --needed python-pyqt6 qt6-svg python-psutil)
  elif command -v apk >/dev/null 2>&1; then
    # The same packages the Alpine dependency preparation installs
    # (packaging/common/os-scripts/alpine/prepare-dependencies.sh).
    missing_python_deps_command=(apk add --no-progress bash python3 py3-qt6 py3-psutil qt6-qtbase qt6-qtsvg jq polkit)
  fi
  missing_python_deps=1
fi
if [[ "$missing_python_deps" -eq 1 ]]; then
  if [[ ${#missing_python_deps_command[@]} -gt 0 ]]; then
    printf -v missing_python_deps_command_text '%q ' "${missing_python_deps_command[@]}"
    echo "Install command: sudo ${missing_python_deps_command_text% }" >&2
  fi
fi

if [[ ${#missing_python_deps_command[@]} -gt 0 && "${BC250_SKIP_DEPENDENCY_INSTALL:-0}" != "1" ]]; then
  prepare_steamos_pacman_install_local
  echo "Installing missing Python GUI dependencies..."
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    "${missing_python_deps_command[@]}"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "${missing_python_deps_command[@]}"
  else
    echo "Warning: sudo is not available. Install manually: ${missing_python_deps_command_text% }" >&2
  fi
  if is_steamos_install_local; then
    restore_steamos_install_root 0
  fi
elif [[ ${#missing_python_deps_command[@]} -gt 0 ]]; then
  echo "Skipping host dependency installation because BC250_SKIP_DEPENDENCY_INSTALL=1."
fi

bash "$ROOT_DIR/scripts/qa/validate-install-source.sh" "$ROOT_DIR"

install -dm755 "$APP_DIR" "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR" "$METAINFO_DIR" "$SYSTEMD_USER_DIR" "$DOC_DIR"

# Validate a complete staging copy before replacing the installed Python tree.
# Configuration, profiles and ResourceTools are never component names in this
# swap. They remain untouched even when the default XDG data directory and the
# local application directory share the same parent.
APP_STAGE="$(mktemp -d "${APP_DIR}.update.XXXXXX")"
APP_BACKUP="${APP_DIR}.tree.previous.$$"
VERSION_BACKUP="${APP_DIR}.VERSION.previous.$$"
APP_SWAP_COMPLETE=0
APP_HAD_VERSION=0
APP_COMPONENTS=(src frontends privileged packaging assets scripts integrations)
LEGACY_COMPONENTS=(mvc)
cleanup_application_swap() {
  local status=$?
  trap - EXIT
  if [[ "$status" -ne 0 && "$APP_SWAP_COMPLETE" -eq 1 ]]; then
    echo "Installation failed; rolling back the application code." >&2
    for component in "${APP_COMPONENTS[@]}" "${LEGACY_COMPONENTS[@]}"; do
      rm -rf -- "$APP_DIR/$component"
      if [[ -d "$APP_BACKUP/$component" ]]; then
        mv -- "$APP_BACKUP/$component" "$APP_DIR/$component"
      fi
    done
    rm -f -- "$APP_DIR/VERSION"
    if [[ "$APP_HAD_VERSION" -eq 1 && -f "$VERSION_BACKUP" ]]; then
      mv -- "$VERSION_BACKUP" "$APP_DIR/VERSION"
    fi
  fi
  rm -rf -- "$APP_STAGE"
  if [[ "$status" -eq 0 ]]; then
    rm -rf -- "$APP_BACKUP"
    rm -f -- "$VERSION_BACKUP"
  fi
  if restore_steamos_install_root "$status"; then
    exit 0
  else
    exit $?
  fi
}
trap cleanup_application_swap EXIT
for component in src frontends privileged packaging assets; do
  cp -a "$ROOT_DIR/$component" "$APP_STAGE/"
done
# Version 1.18 installed its complete Python application in mvc/. Keep it in
# the same rollback transaction, then discard it only after 1.19 is fully
# installed. This prevents a failed privileged-helper update from leaving a
# half-upgraded local installation.
LEGACY_MVC_DETECTED=0
for component in "${LEGACY_COMPONENTS[@]}"; do
  if [[ -e "$APP_DIR/$component" ]]; then
    LEGACY_MVC_DETECTED=1
  fi
done
if [[ "$LEGACY_MVC_DETECTED" -eq 1 ]]; then
  migration_dir="$BC250_USER_STATE_DIR/migration-backups/1.18-to-1.19-$(date -u +%Y%m%dT%H%M%SZ)"
  install -d -m700 "$migration_dir"
  for migration_file in \
    "$BC250_USER_CONFIG_DIR/config.json" \
    "$BC250_USER_CONFIG_DIR/perfiles.json" \
    "$BC250_USER_CONFIG_DIR/ui.conf"; do
    if [[ -f "$migration_file" ]]; then
      install -m600 "$migration_file" "$migration_dir/$(basename "$migration_file")"
    fi
  done
  printf '%s\n' 'BC250 Control Center 1.18 to 1.19 configuration snapshot' > "$migration_dir/README.txt"
fi
# Stage the small opt-in Decky runtime and installed maintenance scripts as
# part of the same application transaction. Development dependencies are
# deliberately excluded.
install -Dm755 "$ROOT_DIR/scripts/install-decky-quick-access.sh" \
  "$APP_STAGE/scripts/install-decky-quick-access.sh"
install -Dm755 "$ROOT_DIR/scripts/uninstall-local.sh" "$APP_STAGE/scripts/uninstall-local.sh"
install -Dm755 "$ROOT_DIR/scripts/maintenance/update-local.sh" \
  "$APP_STAGE/scripts/maintenance/update-local.sh"
install -Dm644 "$ROOT_DIR/scripts/lib/user-paths.sh" "$APP_STAGE/scripts/lib/user-paths.sh"
cp -a -- "$ROOT_DIR/scripts/system" "$APP_STAGE/scripts/system"
find "$APP_STAGE/scripts/system" -type d -name __pycache__ -prune -exec rm -rf -- {} +
find "$APP_STAGE/scripts/system" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
for decky_runtime in plugin.json package.json main.py dist/index.js \
  bc250cc/__init__.py bc250cc/domain/__init__.py \
  bc250cc/domain/gpu/__init__.py bc250cc/domain/gpu/profiles.py; do
  install -Dm644 \
    "$ROOT_DIR/integrations/decky/bc250-quick-access/$decky_runtime" \
    "$APP_STAGE/integrations/decky/bc250-quick-access/$decky_runtime"
done
install -m644 "$ROOT_DIR/VERSION" "$APP_STAGE/VERSION"
PYTHONPYCACHEPREFIX="$APP_STAGE/pycache" python3 -m compileall -q \
  "$APP_STAGE/src" "$APP_STAGE/frontends" "$APP_STAGE/privileged"
rm -rf -- "$APP_STAGE/pycache"
# Same normalisation as stage-package-root.sh: one file left 0600 in the
# source tree (editors create them) made a root install under /usr/local
# unreadable to the desktop user, and the window failed to start.
chmod -R a+rX "$APP_STAGE"
for component in "${APP_COMPONENTS[@]}"; do
  if [[ -e "$APP_DIR/$component" ]]; then
    install -d -m700 "$APP_BACKUP"
    cp -a -- "$APP_DIR/$component" "$APP_BACKUP/$component"
  fi
done
for component in "${LEGACY_COMPONENTS[@]}"; do
  if [[ -e "$APP_DIR/$component" ]]; then
    install -d -m700 "$APP_BACKUP"
    cp -a -- "$APP_DIR/$component" "$APP_BACKUP/$component"
  fi
done
if [[ -f "$APP_DIR/VERSION" ]]; then
  APP_HAD_VERSION=1
  cp -a -- "$APP_DIR/VERSION" "$VERSION_BACKUP"
fi
APP_SWAP_COMPLETE=1
for component in "${APP_COMPONENTS[@]}" "${LEGACY_COMPONENTS[@]}"; do
  rm -rf -- "$APP_DIR/$component"
done
rm -f -- "$APP_DIR/VERSION"
for component in "${APP_COMPONENTS[@]}"; do
  mv -- "$APP_STAGE/$component" "$APP_DIR/$component"
done
mv -- "$APP_STAGE/VERSION" "$APP_DIR/VERSION"
install -Dm644 "$ROOT_DIR/README.md" "$DOC_DIR/README.md"
install -Dm644 "$ROOT_DIR/LICENSE" "$DOC_DIR/LICENSE"
install -Dm644 "$ROOT_DIR/docs/THIRD_PARTY_NOTICES.md" "$DOC_DIR/THIRD_PARTY_NOTICES.md"
install_privileged_pwm_components() {
  local helper_source="$ROOT_DIR/privileged/helpers/bc250-fan-pwm-helper"
  local system_setup_helper_source="$ROOT_DIR/privileged/helpers/bc250-system-setup-helper"
  local steamos_helper_source="$ROOT_DIR/privileged/helpers/bc250-steamos-game-helper"
  local governor_helper_source="$ROOT_DIR/privileged/helpers/bc250-governor-config-helper"
  local core_unlock_helper_source="$ROOT_DIR/privileged/helpers/bc250-core-unlock-helper"
  local cpu_smu_helper_source="$ROOT_DIR/privileged/helpers/bc250-cpu-smu-helper"
  local gddr6_temp_helper_source="$ROOT_DIR/privileged/helpers/bc250-gddr6-temp-helper"
  local gddr6_temp_reader_source="$ROOT_DIR/privileged/helpers/bc250-gddr6-temp-reader"
  local openrc_service_helper_source="$ROOT_DIR/privileged/helpers/bc250-openrc-service-helper"
  local service_helper_source="$ROOT_DIR/privileged/helpers/bc250-service-helper"
  local maintenance_helper_source="$ROOT_DIR/privileged/helpers/bc250-maintenance-helper"
  local quick_access_helper_source="$ROOT_DIR/privileged/helpers/bc250-quick-access-helper"
  local cu_helper_source="$ROOT_DIR/privileged/helpers/bc250-cu-helper"
  local cu_helper_target="/usr/libexec/bc250-control-center/bc250-cu-helper"
  local gpu_lab_source="$ROOT_DIR/scripts/system/bc250-gpu-voltage-lab.sh"
  local steamos_amdgpu_overlay_source="$ROOT_DIR/scripts/system/prepare-steamos-telemetry-oc-overlay.py"
  local cyan_overlay_preflight_source="$ROOT_DIR/privileged/helpers/bc250-cyan-overlay-preflight"
  local cpu_smu_vendor_source="$ROOT_DIR/privileged/lib/bc250_smu_oc_vendor.zip"
  local governor_toml_source="$ROOT_DIR/privileged/lib/governor_toml.py"
  local policy_source="$ROOT_DIR/privileged/policies/io.github.movacx.bc250-control-center.policy"
  local -a elevate=()

  if [[ "${BC250_SKIP_PRIVILEGED_HELPER:-0}" == "1" ]]; then
    echo "Skipping privileged PWM helper because BC250_SKIP_PRIVILEGED_HELPER=1."
    return 0
  fi

  if [[ -e /run/ostree-booted ]]; then
    echo "Warning: immutable rpm-ostree system detected; install the RPM with rpm-ostree for the hardened PWM helper." >&2
    return 0
  fi

  if is_steamos_install_local; then
    echo "SteamOS detected: temporarily opening the root filesystem for Control Center's privileged helpers..."
    if declare -F bc250_steamos_unlock_root >/dev/null 2>&1; then
      bc250_steamos_unlock_root
    else
      echo "Error: SteamOS root-state guard is unavailable; refusing privileged helper installation." >&2
      return 70
    fi
  fi

  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    if ! command -v sudo >/dev/null 2>&1; then
      echo "Warning: sudo is unavailable; the hardened PWM helper and Polkit action were not installed." >&2
      return 0
    fi
    elevate=(sudo)
  fi

  echo "Installing root-owned privileged helpers and Polkit action..."
  local privileged_backup_dir privileged_status rollback_failed target index
  local -a managed_targets=(
    "/usr/libexec/bc250-control-center/bc250-system-setup-helper"
    "/usr/libexec/bc250-control-center/lib/system_setup_common.py"
    "/usr/libexec/bc250-control-center/lib/system_setup_memory.py"
    "/usr/libexec/bc250-control-center/lib/system_setup_acpi.py"
    "/usr/libexec/bc250-control-center/lib/system_setup_telemetry.py"
    "/usr/libexec/bc250-control-center/lib/system_setup_vram.py"
    "/usr/libexec/bc250-control-center/lib/acpi_payload.py"
    "/usr/libexec/bc250-control-center/lib/bc250_contract.py"
    "$cu_helper_target"
    "$SYSTEM_PRIV_HELPER"
    "$SYSTEM_STEAMOS_GAME_HELPER"
    "$SYSTEM_QUICK_ACCESS_HELPER"
    "$SYSTEM_GOVERNOR_CONFIG_HELPER"
    "$SYSTEM_CORE_UNLOCK_HELPER"
    "$SYSTEM_CPU_SMU_HELPER"
    "$SYSTEM_GDDR6_TEMP_HELPER"
    "$SYSTEM_GDDR6_TEMP_READER"
    "$SYSTEM_OPENRC_SERVICE_HELPER"
    "$SYSTEM_SERVICE_HELPER"
    "$SYSTEM_MAINTENANCE_HELPER"
    "$SYSTEM_GPU_LAB_SCRIPT"
    "$SYSTEM_STEAMOS_AMDGPU_OVERLAY"
    "$SYSTEM_CYAN_OVERLAY_PREFLIGHT"
    "$SYSTEM_CYAN_OVERLAY_DROPIN"
    "$SYSTEM_CPU_SMU_VENDOR"
    "$SYSTEM_CPU_SMU_CONFIG"
    "$SYSTEM_GOVERNOR_TOML_IMPLEMENTATION"
    "$LEGACY_CORE_UNLOCK_IMPLEMENTATION"
    "$SYSTEM_POLKIT_ACTION"
    "/etc/cyan-skillfish-governor-smu/config.toml"
  )
  local -a target_existed=()
  # Keep rollback material outside the caller's writable namespace. Otherwise
  # a user could tamper with a saved helper and have sudo restore it as root.
  privileged_backup_dir="$("${elevate[@]}" mktemp -d /var/tmp/bc250-privileged-backup.XXXXXX)"
  "${elevate[@]}" chmod 0700 "$privileged_backup_dir"

  # Snapshot every privileged file that this function can mutate.  The
  # application tree has its own transaction above; this gives /usr/libexec,
  # Polkit and the optional Cyan config the same fail-closed behavior.
  for index in "${!managed_targets[@]}"; do
    target="${managed_targets[$index]}"
    if "${elevate[@]}" test -e "$target"; then
      target_existed[$index]=1
      "${elevate[@]}" cp -a -- "$target" "$privileged_backup_dir/$index"
    else
      target_existed[$index]=0
    fi
  done

  set +e
  (
    set -e
    # Normalize parent directories as well as helper files.  An older package
    # built under a permissive umask could leave this trust boundary writable
    # by the group, causing every hardened helper to reject its own imports.
    "${elevate[@]}" install -d -m0755 /usr/libexec/bc250-control-center /usr/libexec/bc250-control-center/lib
    "${elevate[@]}" install -Dm755 "$system_setup_helper_source" /usr/libexec/bc250-control-center/bc250-system-setup-helper
    for setup_module in system_setup_common.py system_setup_memory.py system_setup_acpi.py system_setup_telemetry.py system_setup_vram.py acpi_payload.py bc250_contract.py; do
      "${elevate[@]}" install -Dm644 "$ROOT_DIR/privileged/lib/$setup_module" "/usr/libexec/bc250-control-center/lib/$setup_module"
    done
    "${elevate[@]}" install -Dm755 "$helper_source" "$SYSTEM_PRIV_HELPER"
    "${elevate[@]}" install -Dm755 "$cu_helper_source" "$cu_helper_target"
    "${elevate[@]}" install -Dm755 "$steamos_helper_source" "$SYSTEM_STEAMOS_GAME_HELPER"
    "${elevate[@]}" install -Dm755 "$quick_access_helper_source" "$SYSTEM_QUICK_ACCESS_HELPER"
    "${elevate[@]}" install -Dm755 "$governor_helper_source" "$SYSTEM_GOVERNOR_CONFIG_HELPER"
    "${elevate[@]}" install -Dm755 "$core_unlock_helper_source" "$SYSTEM_CORE_UNLOCK_HELPER"
    "${elevate[@]}" install -Dm755 "$cpu_smu_helper_source" "$SYSTEM_CPU_SMU_HELPER"
    "${elevate[@]}" install -Dm755 "$gddr6_temp_helper_source" "$SYSTEM_GDDR6_TEMP_HELPER"
    "${elevate[@]}" install -Dm755 "$gddr6_temp_reader_source" "$SYSTEM_GDDR6_TEMP_READER"
    "${elevate[@]}" install -Dm755 "$openrc_service_helper_source" "$SYSTEM_OPENRC_SERVICE_HELPER"
    "${elevate[@]}" install -Dm755 "$service_helper_source" "$SYSTEM_SERVICE_HELPER"
    "${elevate[@]}" install -Dm755 "$maintenance_helper_source" "$SYSTEM_MAINTENANCE_HELPER"
    "${elevate[@]}" install -Dm755 "$gpu_lab_source" "$SYSTEM_GPU_LAB_SCRIPT"
    "${elevate[@]}" install -Dm755 "$steamos_amdgpu_overlay_source" "$SYSTEM_STEAMOS_AMDGPU_OVERLAY"
    "${elevate[@]}" install -Dm755 "$cyan_overlay_preflight_source" "$SYSTEM_CYAN_OVERLAY_PREFLIGHT"
    # Same file the packages ship, so the two installation paths cannot drift.
    "${elevate[@]}" install -Dm644 \
      "$ROOT_DIR/packaging/common/91-bc250-control-center-overlay-preflight.conf" \
      "$SYSTEM_CYAN_OVERLAY_DROPIN"
    "${elevate[@]}" install -Dm644 "$cpu_smu_vendor_source" "$SYSTEM_CPU_SMU_VENDOR"
    # The boot OC config contains only frequency, scale and temperature.  Keep
    # it root-owned but world-readable so the unprivileged GUI can validate
    # exactly what will be applied at boot.  Older hardened builds used 0600,
    # which made a valid config look corrupt to the desktop telemetry reader.
    if "${elevate[@]}" test -e "$SYSTEM_CPU_SMU_CONFIG"; then
      config_owner="$("${elevate[@]}" stat -c '%u' "$SYSTEM_CPU_SMU_CONFIG" 2>/dev/null || true)"
      config_type="$("${elevate[@]}" stat -c '%F' "$SYSTEM_CPU_SMU_CONFIG" 2>/dev/null || true)"
      if [[ "$config_owner" == "0" && "$config_type" == "regular file" ]]; then
        "${elevate[@]}" chmod 0644 "$SYSTEM_CPU_SMU_CONFIG"
      else
        echo "Warning: existing $SYSTEM_CPU_SMU_CONFIG was not normalized because it is not a root-owned regular file." >&2
      fi
    fi
    "${elevate[@]}" install -Dm644 "$governor_toml_source" "$SYSTEM_GOVERNOR_TOML_IMPLEMENTATION"
    "${elevate[@]}" rm -f -- "$LEGACY_CORE_UNLOCK_IMPLEMENTATION"
    "${elevate[@]}" install -Dm644 "$policy_source" "$SYSTEM_POLKIT_ACTION"
    for helper_pair in \
      "$system_setup_helper_source:/usr/libexec/bc250-control-center/bc250-system-setup-helper" \
      "$cu_helper_source:$cu_helper_target" \
      "$helper_source:$SYSTEM_PRIV_HELPER" \
      "$steamos_helper_source:$SYSTEM_STEAMOS_GAME_HELPER" \
      "$governor_helper_source:$SYSTEM_GOVERNOR_CONFIG_HELPER" \
      "$core_unlock_helper_source:$SYSTEM_CORE_UNLOCK_HELPER" \
      "$cpu_smu_helper_source:$SYSTEM_CPU_SMU_HELPER" \
      "$gddr6_temp_helper_source:$SYSTEM_GDDR6_TEMP_HELPER" \
      "$gddr6_temp_reader_source:$SYSTEM_GDDR6_TEMP_READER" \
      "$openrc_service_helper_source:$SYSTEM_OPENRC_SERVICE_HELPER" \
      "$service_helper_source:$SYSTEM_SERVICE_HELPER" \
      "$maintenance_helper_source:$SYSTEM_MAINTENANCE_HELPER" \
      "$gpu_lab_source:$SYSTEM_GPU_LAB_SCRIPT" \
      "$steamos_amdgpu_overlay_source:$SYSTEM_STEAMOS_AMDGPU_OVERLAY" \
      "$cyan_overlay_preflight_source:$SYSTEM_CYAN_OVERLAY_PREFLIGHT"; do
      helper_source_path="${helper_pair%%:*}"
      helper_installed_path="${helper_pair#*:}"
      if ! cmp -s "$helper_source_path" "$helper_installed_path"; then
        echo "ERROR: installed privileged helper does not match this build: $helper_installed_path" >&2
        exit 1
      fi
      helper_metadata="$("${elevate[@]}" stat -c '%u:%a' "$helper_installed_path")"
      if [[ "$helper_metadata" != "0:755" ]]; then
        echo "ERROR: privileged helper must be root-owned mode 0755: $helper_installed_path" >&2
        exit 1
      fi
    done
    for implementation_pair in \
      "$governor_toml_source:$SYSTEM_GOVERNOR_TOML_IMPLEMENTATION" \
      "$cpu_smu_vendor_source:$SYSTEM_CPU_SMU_VENDOR"; do
      implementation_source_path="${implementation_pair%%:*}"
      implementation_installed_path="${implementation_pair#*:}"
      if ! cmp -s "$implementation_source_path" "$implementation_installed_path"; then
        echo "ERROR: installed privileged implementation does not match this build: $implementation_installed_path" >&2
        exit 1
      fi
      implementation_metadata="$("${elevate[@]}" stat -c '%u:%a' "$implementation_installed_path")"
      if [[ "$implementation_metadata" != "0:644" ]]; then
        echo "ERROR: privileged implementation must be root-owned mode 0644: $implementation_installed_path" >&2
        exit 1
      fi
    done
    for trusted_directory in /usr/libexec/bc250-control-center /usr/libexec/bc250-control-center/lib; do
      trusted_directory_metadata="$("${elevate[@]}" stat -c '%u:%a' "$trusted_directory")"
      if [[ "$trusted_directory_metadata" != "0:755" ]]; then
        echo "ERROR: privileged directory must be root-owned mode 0755: $trusted_directory" >&2
        exit 1
      fi
    done
    expected_game_helper_protocol="$(sed -n 's/^BC250_HELPER_PROTOCOL=//p' "$steamos_helper_source" | head -n1)"
    if [[ ! "$expected_game_helper_protocol" =~ ^[0-9]+$ ]] || \
       ! grep -q "^BC250_HELPER_PROTOCOL=${expected_game_helper_protocol}$" "$SYSTEM_STEAMOS_GAME_HELPER"; then
      echo "ERROR: the installed SteamOS Game Mode helper protocol marker is missing or stale." >&2
      exit 1
    fi

    # Normalize only unambiguous legacy frequency-range layouts. This edit is
    # idempotent, preserves user values and every unrelated TOML byte, and is
    # deliberately performed while install/update already has root authority.
    #
    # The file belongs to the governor, and other toolkits edit it too. One of
    # them leaving it unreadable (a key written twice, GitHub issue #1) used to
    # fail this step and roll back the whole installation. Identical repeats
    # are now repaired by the helper; anything else is reported and left alone.
    if [[ -f /etc/cyan-skillfish-governor-smu/config.toml ]]; then
      if ! "${elevate[@]}" "$SYSTEM_GOVERNOR_CONFIG_HELPER" migrate-legacy-frequency-range; then
        echo "WARNING: /etc/cyan-skillfish-governor-smu/config.toml could not be normalized and was left unchanged." >&2
        echo "         Fix the line reported above, then apply the GPU range again from BC250 Control Center." >&2
      fi
    fi
    if [[ -d /run/systemd/system ]] && command -v systemctl >/dev/null 2>&1; then
      "${elevate[@]}" systemctl daemon-reload
    fi
  )
  privileged_status=$?
  set -e

  if [[ "$privileged_status" -ne 0 ]]; then
    echo "Privileged component installation failed; restoring the previous privileged state." >&2
    rollback_failed=0
    for index in "${!managed_targets[@]}"; do
      target="${managed_targets[$index]}"
      if ! "${elevate[@]}" rm -f -- "$target"; then
        rollback_failed=1
        continue
      fi
      if [[ "${target_existed[$index]}" -eq 1 ]]; then
        if ! "${elevate[@]}" mkdir -p -- "$(dirname "$target")" || \
           ! "${elevate[@]}" cp -a -- "$privileged_backup_dir/$index" "$target"; then
          rollback_failed=1
        fi
      fi
    done
    "${elevate[@]}" rm -rf -- "$privileged_backup_dir"
    if [[ "$rollback_failed" -ne 0 ]]; then
      echo "ERROR: privileged rollback was incomplete; run Health Check before using hardware controls." >&2
      return 1
    fi
    if [[ -d /run/systemd/system ]] && command -v systemctl >/dev/null 2>&1; then
      "${elevate[@]}" systemctl daemon-reload || true
    fi
    return "$privileged_status"
  fi

  "${elevate[@]}" rm -rf -- "$privileged_backup_dir"
}

install_privileged_pwm_components
if is_steamos_install_local; then
  restore_steamos_install_root 0
fi
# Replace launchers only after both the application-tree and privileged-file
# transactions succeeded. Old 1.18 launchers remain usable during rollback.
install -Dm755 "$ROOT_DIR/scripts/entrypoints/bc250-control-center" "$BIN_DIR/bc250-control-center"
install -Dm755 "$ROOT_DIR/scripts/entrypoints/bc250-control-center-cli" "$BIN_DIR/bc250-control-center-cli"
install -Dm755 "$ROOT_DIR/scripts/entrypoints/bc250-control-centerd" "$BIN_DIR/bc250-control-centerd"
rm -f "$ICON_DIR/scalable/apps/bc250-control-center.svg"
# 16 and 24 matter: the window manager and the task switcher ask for them,
# and without an exact match they downscale 32 and lose the outline.
for size in 16 24 32 48 64 128 256 512 1024; do
  install -Dm644 "$ROOT_DIR/assets/icons/bc250-control-center-${size}.png" "$ICON_DIR/${size}x${size}/apps/bc250-control-center.png"
done
desktop_file="$DESKTOP_DIR/io.github.movacx.bc250-control-center.desktop"
install -Dm644 "$ROOT_DIR/packaging/common/io.github.movacx.bc250-control-center.desktop" "$desktop_file"
sed -i "s|^Exec=.*|Exec=$BIN_DIR/bc250-control-center|" "$desktop_file"
install -Dm644 "$ROOT_DIR/packaging/common/io.github.movacx.bc250-control-center.metainfo.xml" "$METAINFO_DIR/io.github.movacx.bc250-control-center.metainfo.xml"

# Tell the desktop that the icon changed.
#
# The uninstaller has always refreshed these caches and the installer never
# did, which made a reinstall the one case that went wrong: uninstalling
# rebuilt the icon cache *after* deleting the icons, then installing wrote new
# ones without telling anyone. Launchers kept reading a cache that described
# the previous icon, so the files on disk were right and the desktop still
# showed the old artwork.
#
# ``-t`` because a per-user hicolor directory has no index.theme of its own;
# without it gtk-update-icon-cache refuses and the stale cache survives. Every
# one of these is optional and advisory, so none of them may fail the install.
#
# Only for a prefix a desktop actually reads, matching the uninstaller. Writing
# an icon cache into a staging root would leave a file behind that nothing
# created on purpose and nothing removes.
install_runtime_prefix=0
case "$PREFIX" in
  /usr|/usr/local|"$HOME/.local") install_runtime_prefix=1 ;;
esac
if [[ "$install_runtime_prefix" -eq 1 ]]; then
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi
for icon_cache_tool in gtk-update-icon-cache gtk4-update-icon-cache; do
  if command -v "$icon_cache_tool" >/dev/null 2>&1; then
    "$icon_cache_tool" -q -f -t "$ICON_DIR" >/dev/null 2>&1 || true
  fi
done
# Plasma keeps its own icon and service caches and only notices through these.
rm -f "${XDG_CACHE_HOME:-$HOME/.cache}/icon-cache.kcache" 2>/dev/null || true
for sycoca_tool in kbuildsycoca6 kbuildsycoca5; do
  if command -v "$sycoca_tool" >/dev/null 2>&1; then
    "$sycoca_tool" --noincremental >/dev/null 2>&1 || true
    break
  fi
done
if command -v xdg-desktop-menu >/dev/null 2>&1; then
  xdg-desktop-menu forceupdate >/dev/null 2>&1 || true
fi
fi
expected_user_systemd_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
daemon_reload_attempted=0
if [[ -d /run/systemd/system ]]; then
  install -Dm644 "$ROOT_DIR/packaging/common/bc250-control-centerd.service" "$SYSTEMD_USER_DIR/bc250-control-centerd.service"
  sed -i "s|^ExecStart=.*|ExecStart=$BIN_DIR/bc250-control-centerd|" "$SYSTEMD_USER_DIR/bc250-control-centerd.service"
  if [[ "$SYSTEMD_USER_DIR" != "$PREFIX/lib/systemd/user" ]]; then
    rm -f "$PREFIX/lib/systemd/user/bc250-control-centerd.service"
  fi
  if [[ "${EUID:-$(id -u)}" -ne 0 && "$SYSTEMD_USER_DIR" == "$expected_user_systemd_dir" ]] \
    && command -v systemctl >/dev/null 2>&1; then
    systemctl --user daemon-reload >/dev/null 2>&1 || true
    daemon_reload_attempted=1
  fi
fi

echo "Installed in $PREFIX"
echo "GUI: $BIN_DIR/bc250-control-center"
echo "CLI: $BIN_DIR/bc250-control-center-cli"
if [[ ! -d /run/systemd/system ]]; then
  echo "Background daemon: not installed without an active systemd user manager; Desktop Mode refresh remains available."
else
  echo "Optional daemon: systemctl --user enable --now bc250-control-centerd.service"
fi
if [[ "${BC250_SKIP_PRIVILEGED_HELPER:-0}" == "1" ]]; then
  echo "Privileged helpers: intentionally skipped for this installation."
elif [[ -x "$SYSTEM_PRIV_HELPER" ]]; then
  echo "PWM helper: $SYSTEM_PRIV_HELPER"
  if [[ -x "$SYSTEM_STEAMOS_GAME_HELPER" ]]; then
    echo "SteamOS Game Mode helper: $SYSTEM_STEAMOS_GAME_HELPER"
  fi
  if [[ -x "$SYSTEM_CORE_UNLOCK_HELPER" ]]; then
    echo "CPU core unlock helper: $SYSTEM_CORE_UNLOCK_HELPER (official clone launcher ready)"
  else
    echo "CPU core unlock helper: not ready; rerun this installer with sudo access."
  fi
  if [[ -x "$SYSTEM_GDDR6_TEMP_HELPER" ]]; then
    echo "GDDR6 memory-temperature helper: $SYSTEM_GDDR6_TEMP_HELPER (official clone launcher ready)"
  else
    echo "GDDR6 memory-temperature helper: not ready; rerun this installer with sudo access."
  fi
else
  echo "PWM helper: not installed; use a native package or rerun with sudo access for hardened PWM control."
fi
if [[ ! -d /run/systemd/system ]]; then
  echo "Daemon reload: skipped because systemd is not the active init"
elif [[ "$daemon_reload_attempted" -eq 1 ]]; then
  echo "Daemon reload: attempted for the active user service directory"
else
  echo "Daemon reload: not needed for this installation prefix"
fi
if [[ -d /run/systemd/system ]]; then
  echo "If systemd still does not find the daemon, run: systemctl --user daemon-reload"
fi
echo "Uninstall: PREFIX=\"$PREFIX\" $APP_DIR/scripts/uninstall-local.sh"
if [[ "$missing_python_deps" -eq 1 ]]; then
  echo "Important: install the Python GUI dependencies above before opening the app."
  if [[ "$missing_python_deps_reboot_notice" -eq 1 ]]; then
    echo "Bazzite/Fedora Atomic note: reboot after rpm-ostree installs new packages, then open the app again."
  fi
fi
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "Note: $BIN_DIR is not in PATH. Use the full GUI command above or add it to your shell PATH." ;;
esac
