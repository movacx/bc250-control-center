#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
if [[ -z "${PREFIX:-}" ]]; then
  if [[ "$SCRIPT_PATH" == */share/bc250-control-center/scripts/uninstall-local.sh ]]; then
    PREFIX="${SCRIPT_PATH%/share/bc250-control-center/scripts/uninstall-local.sh}"
  elif [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    PREFIX="$HOME/.local"
  else
    PREFIX="/usr/local"
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
SYSTEM_CU_HELPER="/usr/libexec/bc250-control-center/bc250-cu-helper"
SYSTEM_GOVERNOR_CONFIG_HELPER="/usr/libexec/bc250-control-center/bc250-governor-config-helper"
SYSTEM_CORE_UNLOCK_HELPER="/usr/libexec/bc250-control-center/bc250-core-unlock-helper"
SYSTEM_CPU_SMU_HELPER="/usr/libexec/bc250-control-center/bc250-cpu-smu-helper"
SYSTEM_OPENRC_SERVICE_HELPER="/usr/libexec/bc250-control-center/bc250-openrc-service-helper"
SYSTEM_GPU_LAB_SCRIPT="/usr/libexec/bc250-control-center/bc250-gpu-voltage-lab.sh"
SYSTEM_STEAMOS_AMDGPU_OVERLAY="/usr/libexec/bc250-control-center/bc250-steamos-amdgpu-overlay"
SYSTEM_CYAN_OVERLAY_PREFLIGHT="/usr/libexec/bc250-control-center/bc250-cyan-overlay-preflight"
SYSTEM_CYAN_OVERLAY_DROPIN="/etc/systemd/system/cyan-skillfish-governor-smu.service.d/91-bc250-control-center-overlay-preflight.conf"
SYSTEM_STEAMOS_AMDGPU_BACKEND_DIR="/usr/libexec/bc250-control-center/steamos-amdgpu-backend"
SYSTEM_CPU_SMU_VENDOR="/usr/libexec/bc250-control-center/lib/bc250_smu_oc_vendor.zip"
SYSTEM_GOVERNOR_TOML_IMPLEMENTATION="/usr/libexec/bc250-control-center/lib/governor_toml.py"
LEGACY_CORE_UNLOCK_IMPLEMENTATION="/usr/libexec/bc250-control-center/lib/core_unlock.py"
SYSTEM_POLKIT_ACTION="/usr/share/polkit-1/actions/io.github.movacx.bc250-control-center.policy"

if [[ "${EUID:-$(id -u)}" -ne 0 && "$PREFIX" == "$HOME/.local" ]]; then
  SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
fi

YES=0
DRY_RUN=0
PURGE_USER_DATA=0
KEEP_PRIVILEGED=0

usage() {
  cat <<USAGE
BC250 Control Center local uninstaller

Usage:
  PREFIX="\$HOME/.local" ./scripts/uninstall-local.sh [options]
  sudo ./scripts/uninstall-local.sh [options]

Options:
  -y, --yes             Do not ask for confirmation.
  --dry-run             Show what would be removed, but do not delete anything.
  --purge-user-data     Also remove ~/.config and ~/.local/share data created by the app.
  --keep-privileged     Keep global helpers, Polkit policy and managed CPU boot service.
  -h, --help            Show this help.

This removes only files installed by scripts/install-local.sh.
It does not uninstall system dependencies, AUR/RPM packages, cyan-skillfish-governor,
UMR, or unrelated persistent CPU OC services. A service created by this build is disabled before its helper is removed.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -y|--yes) YES=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --purge-user-data) PURGE_USER_DATA=1 ;;
    --keep-privileged) KEEP_PRIVILEGED=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done


disable_managed_cpu_service() {
  local unit="/etc/systemd/system/bc250-smu-oc.service"
  local openrc_unit="/etc/init.d/bc250-smu-oc"
  local openrc=0
  [[ -f /run/openrc/softlevel ]] && command -v rc-service >/dev/null 2>&1 && openrc=1
  if [[ "$openrc" -eq 1 ]]; then
    [[ -f "$openrc_unit" ]] || return 0
  elif [[ ! -f "$unit" ]] || ! grep -Fq "$SYSTEM_CPU_SMU_HELPER apply-config" "$unit" 2>/dev/null; then
    return 0
  fi
  echo "Disabling BC250 CPU boot service because it depends on the helper being uninstalled."
  if [[ "$DRY_RUN" -eq 1 ]]; then
    return 0
  fi
  if [[ "$openrc" -eq 1 ]]; then
    # Delegate OpenRC ownership/content verification to the privileged helper.
    # It refuses to remove a user-modified script rather than deleting a
    # potentially unrelated boot action during an uninstall.
    if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
      "$SYSTEM_CPU_SMU_HELPER" disable-boot
    elif command -v sudo >/dev/null 2>&1; then
      sudo "$SYSTEM_CPU_SMU_HELPER" disable-boot
    else
      echo "Error: disable the OpenRC bc250-smu-oc service before uninstalling." >&2
      return 1
    fi
  elif [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    systemctl disable --now bc250-smu-oc.service || true
    systemctl reset-failed bc250-smu-oc.service >/dev/null 2>&1 || true
    systemctl daemon-reload || true
  elif command -v sudo >/dev/null 2>&1; then
    sudo systemctl disable --now bc250-smu-oc.service || true
    sudo systemctl reset-failed bc250-smu-oc.service >/dev/null 2>&1 || true
    sudo systemctl daemon-reload || true
  else
    echo "Error: persistent CPU service depends on the installed CPU helper; disable it before uninstalling." >&2
    return 1
  fi
}

remove_path() {
  local path="$1"
  if [[ -e "$path" || -L "$path" ]]; then
    echo "Removing: $path"
    if [[ "$DRY_RUN" -eq 0 ]]; then
      if ! rm -rf -- "$path"; then
        if [[ "${EUID:-$(id -u)}" -ne 0 ]] && command -v sudo >/dev/null 2>&1; then
          echo "Protected files found inside $path; requesting administrator permission..."
          sudo rm -rf -- "$path"
        else
          echo "Error: could not completely remove $path" >&2
          return 1
        fi
      fi
    fi
  fi
}

remove_managed_privileged_file() {
  local source="$1"
  local target="$2"
  [[ -e "$target" || -L "$target" ]] || return 0
  # A local uninstall must not turn a stale/custom prefix into authority to
  # remove a global root file. The installed application still contains the
  # exact source that install-local.sh copied, so use it as a conservative
  # provenance check before requesting elevation for removal.
  if [[ ! -f "$source" ]] || ! cmp -s -- "$source" "$target"; then
    echo "Warning: keeping unverified privileged file: $target" >&2
    echo "         It does not match this installed Control Center build." >&2
    return 0
  fi
  remove_path "$target"
}

remove_managed_cyan_dropin() {
  local target="$SYSTEM_CYAN_OVERLAY_DROPIN"
  [[ -e "$target" || -L "$target" ]] || return 0
  local expected_preflight="ExecStartPre=$SYSTEM_CYAN_OVERLAY_PREFLIGHT"
  if [[ -L "$target" ]] || ! grep -Fqx '# Managed by BC250 Control Center: prevent a stale Cyan fix-freq hwmon bind from racing service restart.' "$target" 2>/dev/null || ! grep -Fqx "$expected_preflight" "$target" 2>/dev/null; then
    echo "Warning: keeping unverified Cyan systemd drop-in: $target" >&2
    return 0
  fi
  remove_path "$target"
  remove_empty_dir "$(dirname -- "$target")"
}

remove_empty_dir() {
  local path="$1"
  if [[ -d "$path" ]]; then
    if [[ "$DRY_RUN" -eq 0 ]]; then
      rmdir --ignore-fail-on-non-empty "$path" 2>/dev/null || true
    else
      echo "Would remove empty dir if unused: $path"
    fi
  fi
}

try_disable_user_daemon() {
  if [[ ! -d /run/systemd/system ]]; then
    return 0
  fi
  local expected_user_systemd_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
  if [[ "$SYSTEMD_USER_DIR" != "$expected_user_systemd_dir" ]]; then
    return 0
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "Would try: systemctl --user disable --now bc250-control-centerd.service"
    return 0
  fi
  if [[ "${EUID:-$(id -u)}" -ne 0 ]] && command -v systemctl >/dev/null 2>&1; then
    systemctl --user disable --now bc250-control-centerd.service >/dev/null 2>&1 || true
    systemctl --user daemon-reload >/dev/null 2>&1 || true
  fi
}

reload_systemd_after_overlay_removal() {
  # Removing the Control Center-owned Cyan drop-in without a daemon reload can
  # leave systemd's in-memory service definition pointing at a helper we have
  # just removed. Never call systemctl on OpenRC merely because it is present.
  [[ -d /run/systemd/system ]] || return 0
  command -v systemctl >/dev/null 2>&1 || return 0
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "Would reload systemd after removing the BC250 Cyan overlay drop-in"
    return 0
  fi
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    systemctl daemon-reload
  elif command -v sudo >/dev/null 2>&1; then
    sudo systemctl daemon-reload
  else
    echo "Error: systemd must be reloaded after removing the BC250 Cyan overlay drop-in." >&2
    return 1
  fi
}

cat <<INFO
== BC250 Control Center local uninstall ==
Prefix: $PREFIX

Files installed by install-local.sh will be removed from:
- $APP_DIR
- $BIN_DIR/bc250-control-center
- $BIN_DIR/bc250-control-center-cli
- $BIN_DIR/bc250-control-centerd
- $DESKTOP_DIR/io.github.movacx.bc250-control-center.desktop
- $METAINFO_DIR/io.github.movacx.bc250-control-center.metainfo.xml
- $SYSTEMD_USER_DIR/bc250-control-centerd.service
- $ICON_DIR/*/apps/bc250-control-center.png
- $DOC_DIR
INFO

if [[ "$PURGE_USER_DATA" -eq 1 ]]; then
  cat <<INFO

User data purge enabled. It will also remove:
- $HOME/.config/bc250-control-center
- $HOME/.local/share/bc250-control-center
INFO
fi

if [[ "$YES" -ne 1 ]]; then
  read -r -p "Continue? Type YES to uninstall: " confirm
  if [[ "$confirm" != "YES" ]]; then
    echo "Cancelled."
    exit 0
  fi
fi

try_disable_user_daemon
if [[ "$KEEP_PRIVILEGED" -eq 0 ]]; then
  disable_managed_cpu_service
fi

remove_path "$BIN_DIR/bc250-control-center"
remove_path "$BIN_DIR/bc250-control-center-cli"
remove_path "$BIN_DIR/bc250-control-centerd"
remove_path "$DESKTOP_DIR/io.github.movacx.bc250-control-center.desktop"
remove_path "$METAINFO_DIR/io.github.movacx.bc250-control-center.metainfo.xml"
remove_path "$SYSTEMD_USER_DIR/bc250-control-centerd.service"
if [[ "$KEEP_PRIVILEGED" -eq 0 ]]; then
if [[ -e /var/lib/bc250-control-center/system-setup/acpi.json || -e /etc/systemd/system/bc250-memory-setup.service || -e /var/lib/bc250-control-center-swap/swapfile || -e /etc/systemd/zram-generator.conf.d/90-bc250.conf ]]; then
  echo "Keeping the optional memory/ACPI helper for restoration. Restore these settings in Control Center before removing that helper."
else
  remove_managed_privileged_file "$APP_DIR/privileged/helpers/bc250-system-setup-helper" "/usr/libexec/bc250-control-center/bc250-system-setup-helper"
  for setup_module in system_setup_common.py system_setup_memory.py system_setup_acpi.py acpi_payload.py; do
    remove_managed_privileged_file "$APP_DIR/privileged/lib/$setup_module" "/usr/libexec/bc250-control-center/lib/$setup_module"
  done
fi
remove_managed_privileged_file "$APP_DIR/privileged/helpers/bc250-fan-pwm-helper" "$SYSTEM_PRIV_HELPER"
remove_managed_privileged_file "$APP_DIR/privileged/helpers/bc250-steamos-game-helper" "$SYSTEM_STEAMOS_GAME_HELPER"
remove_managed_privileged_file "$APP_DIR/privileged/helpers/bc250-cu-helper" "$SYSTEM_CU_HELPER"
remove_managed_privileged_file "$APP_DIR/privileged/helpers/bc250-governor-config-helper" "$SYSTEM_GOVERNOR_CONFIG_HELPER"
remove_managed_privileged_file "$APP_DIR/privileged/helpers/bc250-core-unlock-helper" "$SYSTEM_CORE_UNLOCK_HELPER"
remove_managed_privileged_file "$APP_DIR/privileged/helpers/bc250-cpu-smu-helper" "$SYSTEM_CPU_SMU_HELPER"
remove_managed_privileged_file "$APP_DIR/privileged/helpers/bc250-openrc-service-helper" "$SYSTEM_OPENRC_SERVICE_HELPER"
remove_managed_privileged_file "$APP_DIR/scripts/bc250-gpu-voltage-lab.sh" "$SYSTEM_GPU_LAB_SCRIPT"
remove_managed_privileged_file "$APP_DIR/scripts/prepare-steamos-telemetry-oc-overlay.py" "$SYSTEM_STEAMOS_AMDGPU_OVERLAY"
remove_managed_privileged_file "$APP_DIR/privileged/helpers/bc250-cyan-overlay-preflight" "$SYSTEM_CYAN_OVERLAY_PREFLIGHT"
remove_managed_cyan_dropin
# This directory is generated only from the pinned SteamOS toolkit by this
# build. It remains protected unless --keep-privileged was requested.
if [[ -e "$SYSTEM_STEAMOS_AMDGPU_BACKEND_DIR" || -L "$SYSTEM_STEAMOS_AMDGPU_BACKEND_DIR" ]]; then
  remove_path "$SYSTEM_STEAMOS_AMDGPU_BACKEND_DIR"
fi
remove_managed_privileged_file "$APP_DIR/privileged/lib/bc250_smu_oc_vendor.zip" "$SYSTEM_CPU_SMU_VENDOR"
remove_managed_privileged_file "$APP_DIR/privileged/lib/governor_toml.py" "$SYSTEM_GOVERNOR_TOML_IMPLEMENTATION"
remove_managed_privileged_file "$APP_DIR/privileged/policies/io.github.movacx.bc250-control-center.policy" "$SYSTEM_POLKIT_ACTION"
remove_empty_dir "/usr/libexec/bc250-control-center"
reload_systemd_after_overlay_removal
fi
if [[ "$SYSTEMD_USER_DIR" != "$PREFIX/lib/systemd/user" ]]; then
  remove_path "$PREFIX/lib/systemd/user/bc250-control-centerd.service"
fi
remove_path "$DOC_DIR"
remove_path "$APP_DIR"

for size in 32 48 64 128 256 512 1024; do
  remove_path "$ICON_DIR/${size}x${size}/apps/bc250-control-center.png"
  remove_empty_dir "$ICON_DIR/${size}x${size}/apps"
  remove_empty_dir "$ICON_DIR/${size}x${size}"
done
remove_path "$ICON_DIR/scalable/apps/bc250-control-center.svg"
remove_empty_dir "$ICON_DIR/scalable/apps"
remove_empty_dir "$ICON_DIR/scalable"

if [[ "$PURGE_USER_DATA" -eq 1 ]]; then
  remove_path "$HOME/.config/bc250-control-center"
  remove_path "$HOME/.local/share/bc250-control-center"
fi

runtime_prefix=0
case "$PREFIX" in
  /usr|/usr/local|"$HOME/.local") runtime_prefix=1 ;;
esac
if [[ "$DRY_RUN" -eq 0 && "$runtime_prefix" -eq 1 ]]; then
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
  fi
  if command -v gtk-update-icon-cache >/dev/null 2>&1 && [[ -d "$ICON_DIR" ]]; then
    gtk-update-icon-cache -q -t "$ICON_DIR" >/dev/null 2>&1 || true
  fi
fi

cat <<INFO

Uninstall complete.
INFO

if [[ -d /run/systemd/system ]]; then
  cat <<INFO

If you enabled the optional daemon from another user session, you can also run:
  systemctl --user disable --now bc250-control-centerd.service

If an older/manual bc250-smu-oc.service still exists and does not use this build's managed helper,
disable it separately when appropriate:
  sudo systemctl disable --now bc250-smu-oc.service
INFO
else
  cat <<INFO

OpenRC note: Control Center does not install a user daemon on this init system.
INFO
fi
