#!/usr/bin/env bash
set -Eeuo pipefail

BC250_DRY_RUN="${BC250_DRY_RUN:-0}"
BC250_TOOLS_DIR="${BC250_TOOLS_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/bc250-control-center/ResourceTools}"

bold() { printf '\n== %s ==\n' "$*"; }
info() { printf '[INFO] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*" >&2; }
error() { printf '[ERROR] %s\n' "$*" >&2; }
have() { command -v "$1" >/dev/null 2>&1; }

# The package family and the active init manager are independent.  Artix and
# Devuan, for example, use Arch/Debian packages but must never take a
# systemd-only verification path merely because systemctl is installed.
bc250_openrc_active() {
  [[ -f /run/openrc/softlevel ]] \
    && have openrc-run \
    && have rc-service \
    && have rc-update
}

# Stable, machine-readable events coexist with the human log.  GUI and CLI
# clients can consume these without scraping package-manager prose.
result_event() {
  local status="$1" component="$2" code="${3:-0}" message="${4:-}"
  printf 'BC250_RESULT status=%q component=%q code=%q message=%q\n' \
    "$status" "$component" "$code" "$message"
}

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

clone_or_update_commit() {
  local url="$1"
  local destination="$2"
  local revision="$3"
  [[ "$revision" =~ ^[0-9a-f]{40}$ ]] || {
    error "Reviewed source revision must be a full 40-character commit"
    return 22
  }
  mkdir -p "$(dirname "$destination")"
  if [[ -d "$destination/.git" ]]; then
    run git -C "$destination" remote set-url origin "$url"
  else
    if [[ -e "$destination" ]]; then
      local backup="${destination}.incomplete-$(date +%Y%m%d-%H%M%S)"
      warn "Preserving incomplete directory at $backup"
      mv "$destination" "$backup"
    fi
    run git clone --no-checkout "$url" "$destination"
  fi
  run git -C "$destination" fetch --depth 1 origin "$revision"
  run git -C "$destination" checkout --detach FETCH_HEAD
  [[ "$(git -C "$destination" rev-parse HEAD)" == "$revision" ]] || {
    error "Reviewed source revision could not be checked out"
    return 22
  }
}

bc250_stage_reviewed_git_tree() {
  # A checked-out repository under ResourceTools belongs to the desktop user.
  # Do not build a kernel module from that mutable worktree or reset it with a
  # detached checkout. Fetch the reviewed object directly, then build from a
  # fresh archive whose contents are exactly that commit.
  local url="$1"
  local destination="$2"
  local revision="$3"
  local output_variable="$4"
  local stage
  [[ "$revision" =~ ^[0-9a-f]{40}$ ]] || {
    error "Reviewed source revision must be a full 40-character commit"
    return 22
  }
  [[ "$output_variable" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]] || {
    error "Reviewed source staging needs a safe output variable name"
    return 22
  }
  mkdir -p "$(dirname "$destination")"
  if [[ ! -d "$destination/.git" ]]; then
    if [[ -e "$destination" ]]; then
      local backup="${destination}.incomplete-$(date +%Y%m%d-%H%M%S)"
      warn "Preserving non-Git source directory at $backup"
      mv "$destination" "$backup"
    fi
    run git clone --no-checkout "$url" "$destination" || return $?
  fi
  # Fetch from the declared URL without changing the user's origin or working
  # tree.  A user can retain local branches/edits for investigation.
  run git -C "$destination" fetch --no-tags --depth 1 "$url" "$revision" || return $?
  git -C "$destination" cat-file -e "${revision}^{commit}" 2>/dev/null || {
    error "Reviewed source commit is unavailable after fetch"
    return 22
  }
  stage="$(mktemp -d "${TMPDIR:-/tmp}/bc250-reviewed-source.XXXXXX")" || {
    error "Could not create a private reviewed-source staging directory"
    return 22
  }
  if ! git -C "$destination" archive --format=tar "$revision" | tar -xf - -C "$stage"; then
    rm -rf -- "$stage"
    error "Could not archive the reviewed source commit"
    return 22
  fi
  printf -v "$output_variable" '%s' "$stage"
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
  BC250_MODE="apply"
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
      --mode)
        [[ $# -ge 2 ]] || { error "--mode requires a value"; return 2; }
        case "$2" in
          apply|check|plan) BC250_MODE="$2" ;;
          *) error "Unsupported operation mode: $2"; return 2 ;;
        esac
        shift 2
        ;;
      *)
        error "Unknown argument: $1"
        return 2
        ;;
    esac
  done
  case "$BC250_COMPONENT" in
    all|runtime|governor|stress|sensors|umr) ;;
    *) error "Unsupported component: $BC250_COMPONENT"; return 2 ;;
  esac
}

component_action() {
  local component="$1" apply_function="$2" check_function="$3" plan_function="$4"
  component_is "$component" || return 0
  BC250_ACTIVE_COMPONENT="$component"
  case "$BC250_MODE" in
    apply) "$apply_function" ;;
    check) "$check_function" ;;
    plan) "$plan_function" ;;
  esac
  result_event "ok" "$component" 0 "$BC250_MODE completed"
  BC250_ACTIVE_COMPONENT=""
}

plan_packages() {
  local component="$1" manager="$2"
  shift 2
  printf 'PLAN component=%s manager=%s packages=' "$component" "$manager"
  printf '%q ' "$@"
  printf '\n'
}

finish_operation() {
  local label="$1"
  case "$BC250_MODE" in
    plan) bold "$label dependency plan completed (no changes made)" ;;
    check) bold "$label dependency verification completed (no changes made)" ;;
    apply) bold "$label dependency preparation completed" ;;
  esac
}

component_is() {
  [[ "$BC250_COMPONENT" == "all" || "$BC250_COMPONENT" == "$1" ]]
}

print_credits() {
  bold "Third-party credits"
  echo "Explicit workflows and credited references use their official upstream projects. Availability depends on the distribution and the workflow's safety checks."
  echo "- cyan-skillfish-governor (SMU): https://github.com/filippor/cyan-skillfish-governor/tree/smu"
  echo "- Oberon Governor (supported alternative): https://gitlab.com/mothenjoyer69/oberon-governor"
  echo "- bc250_smu_oc: https://github.com/bc250-collective/bc250_smu_oc"
  echo "- bc250-cu-live-manager (explicit CU workflow; upstream license under review): https://github.com/WinnieLV/bc250-cu-live-manager"
  echo "- SteamOS CU backend (explicit workflow; upstream license under review): https://github.com/F5GO/bc250-cu-live-manager-SteamOS"
  echo "- bc250-core-unlock (official repository cloned and launched by the GUI): https://github.com/rw-r-r-0644/bc250-core-unlock"
  echo "- GFX1013 kernel/Mesa stack (exact reviewed Fedora 43 workflow): https://github.com/DryhoppedIPA/bc250-gfx1013-fix"
  echo "- BC250 FSR4 V3 (per-user/per-game Arch/CachyOS workflow): https://github.com/dmorazasanchez/bc250-fsr4"
  echo "- SteamOS AMDGPU/RADV workflow: https://github.com/keyboardspecialist/bc250-steamos"
  echo "- BC250 ACPI compatibility workflow: https://github.com/e-tho/bc250-acpi-fix"
  echo "- SteamOS ASIC fallback reference: https://github.com/rpf16rj/bc250-steamos-real-toolkit"
  echo "- Bazzite BC-250 patched image reference: https://github.com/62fixolab/Latest-Bazzite-AMD-BC-250-Patched-Images"
  echo "- CachyOS BC-250 kernel (explicit opt-in repository): https://github.com/MastaG/linux-cachyos-bc250"
  echo "- nct6687d (kernel-module workflow): https://github.com/Fred78290/nct6687d"
}

on_error() {
  local status=$?
  trap - ERR
  result_event "error" "${BC250_ACTIVE_COMPONENT:-system}" "$status" "${BC250_MODE:-operation} failed"
  error "Operation failed at line ${BASH_LINENO[0]} with exit code $status"
  exit "$status"
}
trap on_error ERR
