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


bc250_running_kernel_release() {
  printf '%s\n' "${BC250_KERNEL_RELEASE_OVERRIDE:-$(uname -r)}"
}

bc250_kernel_build_candidates() {
  local running="${1:-$(bc250_running_kernel_release)}"
  local candidate root
  if [[ -n "${BC250_KERNEL_BUILD_CANDIDATES:-}" ]]; then
    while IFS= read -r candidate || [[ -n "$candidate" ]]; do
      [[ -n "$candidate" ]] && printf '%s\n' "$candidate"
    done < <(printf '%s' "$BC250_KERNEL_BUILD_CANDIDATES" | tr ':' '\n')
    return 0
  fi

  printf '%s\n' \
    "/usr/lib/modules/$running/build" \
    "/lib/modules/$running/build" \
    "/usr/src/kernels/$running" \
    "/usr/src/linux-headers-$running"

  # Search additional installed trees only for diagnosis or when their embedded
  # kernel.release proves that they match the running kernel. A random tree is
  # never accepted merely because it contains a Makefile.
  for root in /usr/lib/modules /lib/modules /usr/src/kernels /usr/src; do
    [[ -d "$root" ]] || continue
    if [[ "$root" == /usr/src/kernels ]]; then
      find "$root" -mindepth 1 -maxdepth 1 -type d -print 2>/dev/null || true
    elif [[ "$root" == /usr/src ]]; then
      find "$root" -mindepth 1 -maxdepth 1 -type d -name 'linux-headers-*' -print 2>/dev/null || true
    else
      find "$root" -mindepth 2 -maxdepth 2 -type d -name build -print 2>/dev/null || true
    fi
  done
}

bc250_kernel_release_from_tree() {
  local tree="$1"
  local release=""
  if [[ -r "$tree/include/config/kernel.release" ]]; then
    IFS= read -r release < "$tree/include/config/kernel.release" || true
  elif [[ -r "$tree/include/generated/utsrelease.h" ]]; then
    release="$(sed -n 's/^#define[[:space:]]\+UTS_RELEASE[[:space:]]\+"\([^"]*\)".*/\1/p' "$tree/include/generated/utsrelease.h" | head -n 1)"
  elif [[ -r "$tree/include/linux/utsrelease.h" ]]; then
    release="$(sed -n 's/^#define[[:space:]]\+UTS_RELEASE[[:space:]]\+"\([^"]*\)".*/\1/p' "$tree/include/linux/utsrelease.h" | head -n 1)"
  fi
  printf '%s\n' "$release"
}

bc250_kernel_tree_matches() {
  local tree="$1"
  local running="${2:-$(bc250_running_kernel_release)}"
  local declared=""
  [[ -f "$tree/Makefile" ]] || return 1
  declared="$(bc250_kernel_release_from_tree "$tree")"
  if [[ -n "$declared" ]]; then
    [[ "$declared" == "$running" ]]
    return
  fi
  case "$tree" in
    "/usr/lib/modules/$running/build"|"/lib/modules/$running/build"|"/usr/src/kernels/$running"|"/usr/src/linux-headers-$running") return 0 ;;
    *) return 1 ;;
  esac
}

bc250_find_matching_kernel_build_dir() {
  local running="${1:-$(bc250_running_kernel_release)}"
  local candidate canonical
  declare -A seen=()
  BC250_KERNEL_BUILD_DIR=""
  BC250_KERNEL_HEADER_RELEASE=""
  while IFS= read -r candidate; do
    [[ -n "$candidate" ]] || continue
    canonical="$(readlink -f "$candidate" 2>/dev/null || printf '%s' "$candidate")"
    [[ -n "${seen[$canonical]:-}" ]] && continue
    seen[$canonical]=1
    if bc250_kernel_tree_matches "$candidate" "$running"; then
      BC250_KERNEL_BUILD_DIR="$candidate"
      BC250_KERNEL_HEADER_RELEASE="$(bc250_kernel_release_from_tree "$candidate")"
      [[ -n "$BC250_KERNEL_HEADER_RELEASE" ]] || BC250_KERNEL_HEADER_RELEASE="$running"
      return 0
    fi
  done < <(bc250_kernel_build_candidates "$running")
  return 1
}

bc250_kernel_headers_preflight() {
  local running="${1:-$(bc250_running_kernel_release)}"
  local candidate canonical declared shown=0
  declare -A seen=()
  bold "Kernel/header compatibility check"
  info "Running kernel: $running"
  if bc250_find_matching_kernel_build_dir "$running"; then
    info "Matching headers: $BC250_KERNEL_BUILD_DIR"
    info "Header kernel release: $BC250_KERNEL_HEADER_RELEASE"
    return 0
  fi

  warn "No kernel build tree matching the running kernel was found."
  warn "Headers for another installed kernel cannot safely build the PWM module for $running."
  while IFS= read -r candidate; do
    [[ -f "$candidate/Makefile" ]] || continue
    canonical="$(readlink -f "$candidate" 2>/dev/null || printf '%s' "$candidate")"
    [[ -n "${seen[$canonical]:-}" ]] && continue
    seen[$canonical]=1
    declared="$(bc250_kernel_release_from_tree "$candidate")"
    [[ -n "$declared" ]] || declared="unknown"
    warn "Found header tree: $candidate (kernel release: $declared)"
    shown=$((shown + 1))
    [[ $shown -ge 12 ]] && break
  done < <(bc250_kernel_build_candidates "$running")
  if [[ $shown -eq 0 ]]; then
    warn "No usable kernel header trees were found on this system."
  fi
  return 1
}

bc250_require_matching_kernel_headers() {
  local running="${1:-$(bc250_running_kernel_release)}"
  if bc250_find_matching_kernel_build_dir "$running"; then
    info "Verified matching kernel headers: $BC250_KERNEL_BUILD_DIR"
    return 0
  fi
  bc250_kernel_headers_preflight "$running" || true
  error "PWM installation stopped before compilation because kernel and headers do not match."
  error "Install headers for exactly: $running"
  error "If package repositories only provide headers for a newer kernel, update the system, reboot into that kernel, and run Prepare PWM driver again."
  return 21
}

bc250_verify_module_vermagic() {
  local module_path="$1"
  local running="${2:-$(bc250_running_kernel_release)}"
  local vermagic module_release
  if [[ "$BC250_DRY_RUN" == "1" ]]; then
    info "Dry-run: skipping module vermagic verification for $module_path"
    return 0
  fi
  [[ -f "$module_path" ]] || { error "Module file is missing: $module_path"; return 22; }
  have modinfo || { warn "modinfo is unavailable; module vermagic could not be checked"; return 0; }
  vermagic="$(modinfo -F vermagic "$module_path" 2>/dev/null || true)"
  module_release="${vermagic%% *}"
  if [[ -z "$module_release" ]]; then
    error "Could not read vermagic from $module_path"
    return 22
  fi
  if [[ "$module_release" != "$running" ]]; then
    error "Module/kernel mismatch: nct6687 was built for $module_release but the running kernel is $running"
    error "The incompatible module will not be installed or loaded."
    return 22
  fi
  info "Verified module vermagic: $module_release"
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
  echo "- bc250-40cu-unlock (documentation reference only): https://github.com/duggasco/bc250-40cu-unlock"
  echo "- bc250-core-unlock (official repository cloned and launched by the GUI): https://github.com/rw-r-r-0644/bc250-core-unlock"
  echo "- nct6687d: https://github.com/Fred78290/nct6687d"
}

on_error() {
  local status=$?
  error "Operation failed at line ${BASH_LINENO[0]} with exit code $status"
  exit "$status"
}
trap on_error ERR
