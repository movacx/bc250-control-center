#!/usr/bin/env bash
# Shared SteamOS root-filesystem guard.
#
# Operations that need to write /usr or install host packages may temporarily
# disable SteamOS read-only protection.  This helper records whether Control
# Center changed the state and restores it on completion.  A root filesystem
# that was already writable is deliberately left writable.

BC250_STEAMOS_READONLY_RESTORE_NEEDED="${BC250_STEAMOS_READONLY_RESTORE_NEEDED:-0}"

bc250_steamos_root_command() {
  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    printf '[ERROR] sudo is required to change SteamOS read-only state.\n' >&2
    return 1
  fi
}

bc250_steamos_readonly_state() {
  local output
  if ! command -v steamos-readonly >/dev/null 2>&1; then
    printf 'unavailable\n'
    return 0
  fi
  output="$(steamos-readonly status 2>&1 || true)"
  if printf '%s\n' "$output" | grep -Eqi '(^|[^[:alpha:]])disabled([^[:alpha:]]|$)'; then
    printf 'disabled\n'
  elif printf '%s\n' "$output" | grep -Eqi '(^|[^[:alpha:]])enabled([^[:alpha:]]|$)'; then
    printf 'enabled\n'
  else
    printf 'unknown\n'
  fi
}

bc250_steamos_verify_usr_writable() {
  local test_dir="${BC250_STEAMOS_WRITABLE_TEST_DIR:-/usr}"
  local token="${test_dir%/}/.bc250-control-center-rw-test.$$"
  local diagnostic_file diagnostic=""
  diagnostic_file="$(mktemp "${TMPDIR:-/tmp}/bc250-steamos-rw.XXXXXX")" || {
    printf '[ERROR] Could not create a temporary diagnostic file for the SteamOS write check.\n' >&2
    return 1
  }
  if bc250_steamos_root_command sh -c 'token="$1"; : > "$token" && rm -f -- "$token"' sh "$token" 2>"$diagnostic_file"; then
    rm -f -- "$diagnostic_file"
    return 0
  fi
  diagnostic="$(cat "$diagnostic_file" 2>/dev/null || true)"
  rm -f -- "$diagnostic_file"
  if printf '%s\n' "$diagnostic" | grep -Eqi 'terminal is required|password is required|no askpass program'; then
    printf '[ERROR] SteamOS write verification needs interactive sudo authorization.\n' >&2
    printf '[ERROR] Run this installer from a terminal, or authorize its Polkit prompt, then retry.\n' >&2
    return 77
  fi
  printf '[ERROR] SteamOS reports a writable root, but /usr is still read-only.\n' >&2
  printf '[ERROR] A systemd-sysext or another immutable layer may be active; disable it or reboot, then retry.\n' >&2
  return 1
}

bc250_steamos_unlock_root() {
  local state
  command -v steamos-readonly >/dev/null 2>&1 || return 0
  state="$(bc250_steamos_readonly_state)"
  case "$state" in
    enabled)
      printf '[INFO] Temporarily disabling SteamOS read-only protection.\n'
      bc250_steamos_root_command steamos-readonly disable
      BC250_STEAMOS_READONLY_RESTORE_NEEDED=1
      ;;
    disabled)
      printf '[INFO] SteamOS root was already writable; its existing state will be preserved.\n'
      ;;
    *)
      printf '[ERROR] Could not determine the SteamOS read-only state; refusing host filesystem changes.\n' >&2
      return 70
      ;;
  esac
  bc250_steamos_verify_usr_writable
}

bc250_steamos_restore_root() {
  local status="${1:-0}" restore_status=0
  if [[ "$BC250_STEAMOS_READONLY_RESTORE_NEEDED" == "1" ]] && command -v steamos-readonly >/dev/null 2>&1; then
    printf '[INFO] Restoring SteamOS read-only protection.\n'
    if ! bc250_steamos_root_command steamos-readonly enable; then
      printf '[ERROR] Failed to restore SteamOS read-only protection. Run: sudo steamos-readonly enable\n' >&2
      restore_status=71
    fi
    BC250_STEAMOS_READONLY_RESTORE_NEEDED=0
  fi
  if [[ "$status" -ne 0 ]]; then
    return "$status"
  fi
  return "$restore_status"
}
