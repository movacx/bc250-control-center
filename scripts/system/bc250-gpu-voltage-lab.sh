#!/usr/bin/env bash
set -euo pipefail

CONFIG="${BC250_GPU_CONFIG:-/etc/cyan-skillfish-governor-smu/config.toml}"
SERVICE="cyan-skillfish-governor-smu.service"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
CURVE_EDITOR="${BC250_GOVERNOR_TOML_EDITOR:-${SCRIPT_DIR}/../../Repository/governor_toml.py}"

usage() {
  cat <<'EOF'
BC250 GPU Voltage Lab

Usage:
  bc250-gpu-voltage-lab.sh status
  bc250-gpu-voltage-lab.sh preview <nivel>
  bc250-gpu-voltage-lab.sh apply <nivel>
  bc250-gpu-voltage-lab.sh apply-custom 500=700 1850=970 2000=1000 ...
  bc250-gpu-voltage-lab.sh menu

Levels:
  0 = governor default values
  1..6 = default +10..60 mV at every point from 2000 MHz

Level 0 restores all 17 original voltages, including commented points.
EOF
}

python_status() {
  python3 "$CURVE_EDITOR" status "$CONFIG"
}

python_preview() {
  local level="$1"
  python3 "$CURVE_EDITOR" preview-voltage-level "$level"
}


busctl_uint() {
  busctl --system get-property com.cyanskillfish.Governor "$1" com.cyanskillfish.Governor.Range "$2" 2>/dev/null | awk '{print $2}'
}

capture_current_range() {
  RANGE_MIN="$(busctl_uint /com/cyanskillfish/Governor/Range/Current Min || true)"
  RANGE_MAX="$(busctl_uint /com/cyanskillfish/Governor/Range/Current Max || true)"
  if [[ ! "$RANGE_MIN" =~ ^[0-9]+$ || ! "$RANGE_MAX" =~ ^[0-9]+$ ]]; then
    RANGE_MIN=""
    RANGE_MAX=""
  fi
}

require_current_range() {
  if ! systemctl is-active --quiet "$SERVICE"; then
    echo "ERROR: the governor must be active before changing the voltage curve." >&2
    return 1
  fi
  capture_current_range
  if [[ -z "${RANGE_MIN:-}" || -z "${RANGE_MAX:-}" ]]; then
    echo "ERROR: the current D-Bus range could not be read; the curve was not changed." >&2
    return 1
  fi
  echo "Protected range before the change: ${RANGE_MIN}-${RANGE_MAX} MHz"
}

restore_current_range() {
  if [[ -z "${RANGE_MIN:-}" || -z "${RANGE_MAX:-}" ]]; then
    echo "ERROR: the previous range is unavailable; safe restoration cannot be verified." >&2
    return 1
  fi
  echo "Restoring the previous D-Bus range: ${RANGE_MIN}-${RANGE_MAX} MHz"
  for _ in $(seq 1 60); do
    local allowed_min allowed_max target_min target_max
    allowed_min="$(busctl_uint /com/cyanskillfish/Governor/Range/Allowed Min || true)"
    allowed_max="$(busctl_uint /com/cyanskillfish/Governor/Range/Allowed Max || true)"
    if [[ "$allowed_min" =~ ^[0-9]+$ && "$allowed_max" =~ ^[0-9]+$ ]]; then
      target_min="$RANGE_MIN"
      target_max="$RANGE_MAX"
      (( target_min < allowed_min )) && target_min="$allowed_min"
      (( target_min > allowed_max )) && target_min="$allowed_max"
      (( target_max < allowed_min )) && target_max="$allowed_min"
      (( target_max > allowed_max )) && target_max="$allowed_max"
      (( target_min > target_max )) && target_min="$target_max"
    else
      sleep 0.5
      continue
    fi
    if busctl --system call com.cyanskillfish.Governor /com/cyanskillfish/Governor com.cyanskillfish.Governor.PerformanceMode SetRange uu "$target_min" "$target_max" >/dev/null 2>&1; then
      local current_min current_max
      current_min="$(busctl_uint /com/cyanskillfish/Governor/Range/Current Min || true)"
      current_max="$(busctl_uint /com/cyanskillfish/Governor/Range/Current Max || true)"
      if [[ "$current_min" == "$target_min" && "$current_max" == "$target_max" ]]; then
        if [[ "$target_min" != "$RANGE_MIN" || "$target_max" != "$RANGE_MAX" ]]; then
          echo "WARNING: the previous range exceeds the active points and was limited safely."
        fi
        echo "OK: range restored and verified at ${target_min}-${target_max} MHz"
        return 0
      fi
    fi
    sleep 0.5
  done
  echo "ERROR: the previous D-Bus range could not be restored. Do not start a GPU workload." >&2
  return 1
}

wait_for_governor_dbus() {
  # SteamOS can need several Cyan retry cycles before its amdgpu hwmon target
  # becomes mountable for fix-freq.  The preflight intentionally waits only a
  # short time now, so this is the single authoritative readiness deadline.
  # Keep it configurable for diagnostics, but never below 30 seconds.
  local attempts="${BC250_CYAN_DBUS_WAIT_ATTEMPTS:-240}"
  [[ "$attempts" =~ ^[0-9]+$ ]] || attempts=240
  (( attempts < 60 )) && attempts=60
  for _ in $(seq 1 "$attempts"); do
    if systemctl is-active --quiet "$SERVICE"; then
      local allowed_min allowed_max
      allowed_min="$(busctl_uint /com/cyanskillfish/Governor/Range/Allowed Min || true)"
      allowed_max="$(busctl_uint /com/cyanskillfish/Governor/Range/Allowed Max || true)"
      if [[ "$allowed_min" =~ ^[0-9]+$ && "$allowed_max" =~ ^[0-9]+$ ]]; then
        return 0
      fi
    fi
    sleep 0.5
  done
  echo "ERROR: Cyan did not publish its D-Bus interface after restarting." >&2
  systemctl status "$SERVICE" --no-pager || true
  return 1
}

restart_governor_preserving_range() {
  # A stop/start sequence gives SteamOS' dynamic hwmon links time to settle.
  # The installed BC250 preflight cleans only Cyan's stale bind target before
  # start.  ``systemctl restart`` previously raced that target and made a
  # valid voltage-curve edit look like a D-Bus failure.
  if ! systemctl stop "$SERVICE"; then
    echo "ERROR: Cyan could not be stopped cleanly." >&2
    return 1
  fi
  for _ in $(seq 1 20); do
    if ! systemctl is-active --quiet "$SERVICE"; then
      break
    fi
    sleep 0.25
  done
  sleep 1
  systemctl reset-failed "$SERVICE" || true
  if ! systemctl start "$SERVICE"; then
    echo "ERROR: Cyan could not be started after updating the curve." >&2
    return 1
  fi
  if ! wait_for_governor_dbus; then
    return 1
  fi
  if ! restore_current_range; then
    return 1
  fi
  systemctl status "$SERVICE" --no-pager || true
}

rollback_curve_after_failed_restart() {
  local backup="$1"
  echo "ERROR: Cyan did not recover its D-Bus range; restoring the previous curve." >&2
  cp -af "$backup" "$CONFIG"
  # Use the exact same stop/start path as the forward transaction.  A raw
  # restart can race the SteamOS hwmon link and make rollback less reliable
  # than the operation it is meant to recover.
  if restart_governor_preserving_range; then
    echo "OK: the previous curve was restored after the failure." >&2
  else
    echo "ERROR: Cyan could not be verified after restoring the curve. Do not start a GPU workload." >&2
  fi
}

apply_level() {
  local level="$1"
  if [[ ! "$level" =~ ^[0-6]$ ]]; then
    echo "ERROR: invalid level. Use an integer from 0 through 6." >&2
    exit 1
  fi
  if [[ $EUID -ne 0 ]]; then
    exec sudo "$0" apply "$level"
  fi
  if [[ ! -f "$CONFIG" ]]; then
    echo "ERROR: $CONFIG does not exist" >&2
    exit 1
  fi
  require_current_range
  local backup="${CONFIG}.backup.bcc-voltage-lab-$(date +%Y%m%d-%H%M%S)"
  cp -a "$CONFIG" "$backup"
  echo "Backup created: $backup"
  if ! python3 "$CURVE_EDITOR" apply-voltage-level "$CONFIG" "$level"; then
    echo "ERROR: the curve was not changed." >&2
    return 1
  fi
  if ! restart_governor_preserving_range; then
    rollback_curve_after_failed_restart "$backup"
    return 1
  fi
  echo
  echo "Test guidance: do not jump directly to 2200 MHz. Test one frequency at a time with a short workload."
}


apply_custom() {
  if [[ $# -lt 1 ]]; then
    echo "ERROR: provide values such as 500=700 1850=970 2000=1000" >&2
    exit 1
  fi
  if [[ $EUID -ne 0 ]]; then
    exec sudo "$0" apply-custom "$@"
  fi
  if [[ ! -f "$CONFIG" ]]; then
    echo "ERROR: $CONFIG does not exist" >&2
    exit 1
  fi
  require_current_range
  local backup="${CONFIG}.backup.bcc-voltage-custom-$(date +%Y%m%d-%H%M%S)"
  cp -a "$CONFIG" "$backup"
  echo "Backup created: $backup"
  if ! python3 "$CURVE_EDITOR" apply-custom-voltage "$CONFIG" "$@"; then
    echo "ERROR: the curve was not changed." >&2
    return 1
  fi
  if ! restart_governor_preserving_range; then
    rollback_curve_after_failed_restart "$backup"
    return 1
  fi
  echo
  echo "Custom curve applied. Editor limit: 600-1210 mV."
}

menu() {
  while true; do
    clear || true
    echo "== BC250 GPU Voltage Lab =="
    echo
    python_status || true
    echo
    echo "Choose a level to apply:"
    echo "  0) restore the complete original curve"
    echo "  1-6) add +10 through +60 mV over defaults"
    echo "  p) preview a level"
    echo "  q) quit"
    echo
    read -r -p "Option: " opt
    case "$opt" in
      0|1|2|3|4|5|6)
        echo
        python_preview "$opt"
        echo
        read -r -p "Apply level $opt and restart the governor? Type YES: " ok
        if [[ "$ok" == "YES" || "$ok" == "SI" ]]; then
          "$0" apply "$opt"
          read -r -p "Press Enter to continue..." _
        fi
        ;;
      p|P)
        read -r -p "Level 0 through 6: " lvl
        python_preview "$lvl" || true
        read -r -p "Press Enter to continue..." _
        ;;
      q|Q) exit 0 ;;
    esac
  done
}

cmd="${1:-menu}"
case "$cmd" in
  status) python_status ;;
  preview) python_preview "${2:-}" ;;
  apply) apply_level "${2:-}" ;;
  apply-custom) shift; apply_custom "$@" ;;
  menu) menu ;;
  -h|--help|help) usage ;;
  *) usage; exit 1 ;;
esac
