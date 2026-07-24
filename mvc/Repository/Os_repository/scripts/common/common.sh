#!/usr/bin/env bash
set -Eeuo pipefail

BC250_DRY_RUN="${BC250_DRY_RUN:-0}"
BC250_TOOLS_DIR="${BC250_TOOLS_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/bc250-control-center/ResourceTools}"

bold() { printf '\n== %s ==\n' "$*"; }
info() { printf '[INFO] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*" >&2; }
error() { printf '[ERROR] %s\n' "$*" >&2; }
have() { command -v "$1" >/dev/null 2>&1; }

run() {
  printf '[INFO]'
  printf ' %q' "$@"
  printf '\n'
  if [[ "$BC250_DRY_RUN" == "1" ]]; then
    return 0
  fi
  "$@"
}

run_optional() {
  if ! run "$@"; then
    warn "Optional command failed: $*"
    return 0
  fi
}

as_root() {
  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    run "$@"
  elif have sudo; then
    run sudo "$@"
  else
    error "sudo is required for: $*"
    return 1
  fi
}

require_user_build() {
  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    error "AUR/makepkg builds must run as a regular user, not root. Start BC250 Control Center from your desktop session."
    return 1
  fi
}

clone_or_update() {
  local url="$1"
  local destination="$2"
  mkdir -p "$(dirname "$destination")"
  if [[ -d "$destination/.git" ]]; then
    run git -C "$destination" pull --ff-only
  else
    if [[ -e "$destination" ]]; then
      local backup="${destination}.incomplete-$(date +%Y%m%d-%H%M%S)"
      warn "Preserving incomplete directory at $backup"
      mv "$destination" "$backup"
    fi
    run git clone --depth 1 "$url" "$destination"
  fi
}

verify_command() {
  local command_name="$1"
  if have "$command_name"; then
    info "$command_name -> $(command -v "$command_name")"
    return 0
  fi
  error "$command_name is still not available in PATH"
  return 1
}

parse_component() {
  BC250_COMPONENT="all"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --component)
        [[ $# -ge 2 ]] || { error "--component requires a value"; return 2; }
        BC250_COMPONENT="$2"
        shift 2
        ;;
      --runtime)
        shift
        ;;
      *)
        error "Unknown argument: $1"
        return 2
        ;;
    esac
  done
}

component_is() {
  [[ "$BC250_COMPONENT" == "all" || "$BC250_COMPONENT" == "$1" ]]
}

print_credits() {
  bold "Third-party credits"
  echo "BC250 Control Center integrates community tools from their official upstream projects."
  echo "- cyan-skillfish-governor (SMU): https://github.com/filippor/cyan-skillfish-governor/tree/smu"
  echo "- bc250_smu_oc: https://github.com/bc250-collective/bc250_smu_oc"
  echo "- bc250-cu-live-manager: https://github.com/WinnieLV/bc250-cu-live-manager"
  echo "- SteamOS CU backend: https://github.com/F5GO/bc250-cu-live-manager-SteamOS"
  echo "- nct6687d: https://github.com/Fred78290/nct6687d"
}

on_error() {
  local status=$?
  error "Operation failed at line ${BASH_LINENO[0]} with exit code $status"
  exit "$status"
}
trap on_error ERR
