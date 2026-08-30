#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=steamos-root.sh
source "$SCRIPT_DIR/steamos-root.sh"

cleanup_cyan_root() {
  local status=$?
  trap - EXIT
  if bc250_steamos_restore_root "$status"; then exit 0; else exit $?; fi
}
trap cleanup_cyan_root EXIT

# Install the reviewed, checksummed Cyan SMU release as a reversible init-service
# override whenever Control Center prepares Cyan. Compatibility switches are
# user-controlled: updates validate but never overwrite gpu.set-method,
# gpu-usage.method, gpu-usage.fix-metrics, or gpu-usage.fix-freq.

SOURCE_DIR="${1:-}"
SERVICE="cyan-skillfish-governor-smu.service"
CONFIG="/etc/cyan-skillfish-governor-smu/config.toml"
MANAGED_BINARY="/usr/local/bin/cyan-skillfish-governor-smu"
DROPIN_DIR="/etc/systemd/system/${SERVICE}.d"
DROPIN="${DROPIN_DIR}/90-bc250-control-center-upstream.conf"
OPENRC_SERVICE="/etc/init.d/cyan-skillfish-governor-smu"
STATE_DIR="/var/lib/bc250-control-center/cyan-governor"
FALLBACK_UNIT="/usr/local/lib/systemd/system/${SERVICE}"
FALLBACK_UNIT_MARKER="${STATE_DIR}/managed-fallback-unit"
DBUS_POLICY="/etc/dbus-1/system.d/com.cyanskillfish.Governor.conf"
PERFORMANCE_MODE="/usr/local/bin/cyan-skillfish-performance-mode"
REPOSITORY="https://github.com/filippor/cyan-skillfish-governor"
MARKER="GPU frequency fix enabled"
REVIEWED_RELEASE_TAG="v0.4.12"
REVIEWED_COMMIT="964524d74ba6b69364be39f0e8fa484eb915779e"
REVIEWED_ARCHIVE_SHA256="43cf992d4a2078bb4d208c6bf411293c8ba127f5170f4e59cb09e8cc25ec0821"
BC250CC_RUNTIME_REVISION="bc250cc.2"
BC250CC_PATCHER="$SCRIPT_DIR/patch-cyan-bc250cc-runtime.py"
BC250CC_RUNTIME_MARKER="BC250CC_RUNTIME_PATCH=${BC250CC_RUNTIME_REVISION}"

info() { printf '[INFO] %s\n' "$*"; }
error() { printf '[ERROR] %s\n' "$*" >&2; }
have() { command -v "$1" >/dev/null 2>&1; }
is_openrc() {
  [[ -f /run/openrc/softlevel ]] && have openrc-run && have rc-service && have rc-update
}

as_root() {
  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    "$@"
  elif have sudo; then
    sudo "$@"
  elif have pkexec; then
    pkexec "$@"
  else
    die "Administrator authentication is required for: $*"
  fi
}

die() {
  error "$*"
  exit 61
}

supports_frequency_fix() {
  local binary="$1"
  [[ -f "$binary" ]] && LC_ALL=C grep -aFq "$MARKER" "$binary"
}

validate_compatibility_switches() {
  python3 - "$CONFIG" <<'PY'
import sys, tomllib
with open(sys.argv[1], "rb") as handle:
    config = tomllib.load(handle)
usage = config.get("gpu-usage", config.get("gpu_usage"))
gpu = config.get("gpu")
if not isinstance(usage, dict) or not isinstance(gpu, dict):
    raise SystemExit("Cyan config requires [gpu-usage] and [gpu] sections")
if not isinstance(usage.get("fix-metrics"), bool):
    raise SystemExit("gpu-usage.fix-metrics must be true or false")
frequency_fix = usage.get("fix-freq", usage.get("fix_freq"))
if not isinstance(frequency_fix, bool):
    raise SystemExit("gpu-usage.fix-freq must be true or false")
if usage.get("method", "busy-flag") not in {"busy-flag", "process", "kernel"}:
    raise SystemExit("gpu-usage.method must be busy-flag, process or kernel")
if gpu.get("set-method", "smu") not in {"smu", "kernel"}:
    raise SystemExit("gpu.set-method must be smu or kernel")
PY
}

require_source_checkout() {
  [[ -d "$SOURCE_DIR/.git" ]] || die "Cyan source directory is missing or not a Git checkout: $SOURCE_DIR"
  [[ -f "$SOURCE_DIR/src/gpu_frequency_fix.rs" ]] ||
    die "The official Cyan checkout does not contain src/gpu_frequency_fix.rs"
  LC_ALL=C grep -Fq 'GPU frequency fix enabled' "$SOURCE_DIR/src/main.rs" ||
    die "The checked-out SMU branch does not contain the GPU frequency-reporting fix"
  local head dirty
  head="$(git -C "$SOURCE_DIR" rev-parse HEAD 2>/dev/null || true)"
  [[ "$head" == "$REVIEWED_COMMIT" ]] ||
    die "Cyan checkout is not the reviewed commit $REVIEWED_COMMIT (found ${head:-unknown})"
  # The reviewed commit is only meaningful if Cargo sees that exact tree.
  # checkout --force resets tracked files, but Git deliberately leaves
  # untracked files behind; an old .cargo/config.toml or build helper could
  # otherwise influence the privileged runtime build without changing HEAD.
  dirty="$(git -C "$SOURCE_DIR" status --porcelain --untracked-files=all 2>/dev/null || true)"
  [[ -z "$dirty" ]] ||
    die "Cyan checkout contains local/untracked files before the reviewed patch; clean the source tree and retry"
}

prepare_native_build_tools() {
  # Native builds link against the target distro's libc, not Fedora's libc.
  # Never replace a user's Rust toolchain if it already exists.  Ubuntu 24.04
  # (and therefore Mint 22.x) ships Rust 1.75, while the reviewed Cyan source
  # requires Rust 1.88 or newer.  In that case rustup provides a user-scoped,
  # pinned toolchain; do not change the system Rust package or rustup's global
  # default toolchain.
  local rust_packages=()
  if ! have cargo || ! have rustc; then
    case "$target_family" in
      arch|cachyos|manjaro|steamos) rust_packages=(rust) ;;
      fedora) rust_packages=(cargo rust) ;;
      *) rust_packages=(cargo rustc) ;;
    esac
  fi
  if ! have cc || ! have pkg-config || ! pkg-config --exists libdrm libdrm_amdgpu || ((${#rust_packages[@]})); then
    case "$target_family" in
      arch|cachyos|manjaro)
        as_root pacman -Syu --needed --noconfirm base-devel libdrm "${rust_packages[@]}" ;;
      steamos)
        as_root pacman -S --needed --noconfirm base-devel libdrm "${rust_packages[@]}" ;;
      debian|ubuntu)
        as_root apt-get update
        as_root apt-get install -y build-essential pkg-config libdrm-dev "${rust_packages[@]}" ;;
      fedora)
        as_root dnf install -y gcc pkgconf-pkg-config libdrm-devel "${rust_packages[@]}" ;;
      *) die "No reviewed native Cyan build route for $target_family" ;;
    esac
  fi
  have cargo && have rustc || die "Cyan requires Cargo and Rust 1.88 or newer"
  if cyan_rust_is_supported; then
    return 0
  fi
  case "$target_family" in
    debian|ubuntu)
      info "The distribution Rust toolchain is too old; installing the pinned user Rust 1.88.0 toolchain"
      as_root apt-get update
      as_root apt-get install -y rustup
      have rustup || die "rustup is required to install the user Rust 1.88.0 toolchain"
      rustup toolchain install 1.88.0 --profile minimal ||
        die "Could not install the user Rust 1.88.0 toolchain; verify network access and retry"
      export PATH="${CARGO_HOME:-$HOME/.cargo}/bin:$PATH"
      # Select this toolchain only for the current preparation process.  This
      # works even when the user has never configured a rustup default, while
      # preserving any default toolchain they already use elsewhere.
      export RUSTUP_TOOLCHAIN=1.88.0
      ;;
    *)
      die "Cyan requires Rust >= 1.88, but $(rustc --version) is installed. Update the user toolchain and retry; the existing governor was not replaced."
      ;;
  esac
  cyan_rust_is_supported ||
    die "Rust 1.88.0 was not selected after installation; the existing governor was not replaced."
}

cyan_rust_is_supported() {
  have rustc || return 1
  python3 - "$(rustc --version)" <<'PY'
import re, sys
match = re.match(r"rustc (\d+)\.(\d+)\.(\d+)", sys.argv[1])
if not match or tuple(map(int, match.groups())) < (1, 88, 0):
    raise SystemExit(1)
PY
}

build_bc250cc_runtime() (
  local workdir source_copy output_dir image binary version binary_sha patcher_sha
  [[ -x "$BC250CC_PATCHER" ]] || die "BC250CC Cyan patch helper is missing: $BC250CC_PATCHER"
  [[ ${EUID:-$(id -u)} -ne 0 ]] || die "Run preparation as your desktop user; only installation uses administrator privileges"
  if [[ "$target_family" == "bazzite" ]]; then
    have podman || die "podman is required to build the reviewed BC250CC Cyan runtime on Bazzite"
  else
    prepare_native_build_tools
  fi
  have python3 || die "python3 is required to apply the reviewed Cyan runtime patch"
  have git || die "git is required to materialize the reviewed Cyan source tree"
  have tar || die "tar is required to materialize the reviewed Cyan source tree"

  # Never patch the user's checked-out third-party source in place. Build from
  # an exact git-archive copy of the reviewed commit so repeated Prepare runs
  # stay idempotent and the source checkout remains clean/auditable.
  workdir="$(mktemp -d /tmp/bc250-cyan-build.XXXXXX)"
  trap 'rm -rf -- "$workdir"' EXIT
  source_copy="$workdir/source"
  output_dir="$workdir/output"
  mkdir -p "$source_copy" "$output_dir"
  git -C "$SOURCE_DIR" archive --format=tar "$REVIEWED_COMMIT" | tar -xf - -C "$source_copy" ||
    die "The reviewed Cyan source tree could not be materialized"

  info "Applying BC250 Control Center Cyan runtime patch ${BC250CC_RUNTIME_REVISION} to an isolated source copy"
  python3 "$BC250CC_PATCHER" "$source_copy" ||
    die "The reviewed Cyan runtime patch could not be applied"
  LC_ALL=C grep -Fq "$BC250CC_RUNTIME_MARKER" "$source_copy/src/governor.rs" ||
    die "The Cyan governor source does not contain the expected BC250CC runtime marker"
  LC_ALL=C grep -Fq "$BC250CC_RUNTIME_MARKER" "$source_copy/src/gpu.rs" ||
    die "The Cyan GPU source does not contain the expected BC250CC runtime marker"

  # The container writes Cargo output as its own uid mapping. Only the output
  # directory needs broad write permission; the patched source stays read-only.
  if [[ "$target_family" == "bazzite" ]]; then
    chmod 0777 "$output_dir"
    image="registry.fedoraproject.org/fedora:44"
    info "Building Cyan ${REVIEWED_RELEASE_TAG}-${BC250CC_RUNTIME_REVISION} in an isolated Fedora container"
    podman run --rm \
    -v "$source_copy:/src:ro,Z" \
    -v "$output_dir:/out:Z" \
    -w /src \
    -e "CARGO_TARGET_DIR=/out" \
    -e "CYAN_SKILLFISH_GOVERNOR_VERSION=${REVIEWED_RELEASE_TAG}-${BC250CC_RUNTIME_REVISION}" \
    "$image" bash -lc \
    'dnf install -y cargo rust gcc libdrm-devel pkgconf-pkg-config git && cargo build --locked --release' ||
      die "The reviewed BC250CC Cyan runtime build failed"
  else
    info "Building patched Cyan against the native $target_family runtime"
    (
      cd "$source_copy"
      CARGO_TARGET_DIR="$output_dir" \
      CYAN_SKILLFISH_GOVERNOR_VERSION="${REVIEWED_RELEASE_TAG}-${BC250CC_RUNTIME_REVISION}" \
        cargo build --locked --release
    ) || die "The reviewed native Cyan build failed; the existing governor was not replaced"
  fi

  binary="$output_dir/release/cyan-skillfish-governor-smu"
  [[ -x "$binary" ]] || die "The BC250CC Cyan build did not produce a governor binary"
  supports_frequency_fix "$binary" ||
    die "The BC250CC Cyan binary lost the upstream GPU frequency-reporting fix"
  version="$($binary --version 2>&1 | head -n 1)"
  [[ "$version" == *"${BC250CC_RUNTIME_REVISION}"* ]] ||
    die "The BC250CC Cyan binary does not expose its runtime revision: $version"

  as_root install -D -m 0755 "$binary" "$MANAGED_BINARY"
  as_root install -d -m 0755 "$STATE_DIR"
  printf '%s\n' "$BC250CC_RUNTIME_REVISION" >"$workdir/runtime-revision"
  printf '%s\n' "$REVIEWED_COMMIT" >"$workdir/upstream-commit"
  patcher_sha="$(sha256sum "$BC250CC_PATCHER" | awk '{print $1}')"
  printf '%s\n' "$patcher_sha" >"$workdir/patcher-sha256"
  binary_sha="$(sha256sum "$binary" | awk '{print $1}')"
  printf '%s\n' "$binary_sha" >"$workdir/binary-sha256"
  as_root install -m 0644 "$workdir/runtime-revision" "$STATE_DIR/runtime-revision"
  as_root install -m 0644 "$workdir/upstream-commit" "$STATE_DIR/upstream-commit"
  as_root install -m 0644 "$workdir/patcher-sha256" "$STATE_DIR/patcher-sha256"
  as_root install -m 0644 "$workdir/binary-sha256" "$STATE_DIR/binary-sha256"
  info "BC250CC Cyan runtime ${BC250CC_RUNTIME_REVISION} built and staged"
)
ensure_base_installation() (
  local binary="$1" workdir load_state
  [[ -x "$binary" ]] || die "The Cyan governor binary is unavailable: $binary"
  [[ -f "$SOURCE_DIR/default-config.toml" ]] ||
    die "The official Cyan checkout does not contain default-config.toml"
  [[ -f "$SOURCE_DIR/com.cyanskillfish.Governor.conf" ]] ||
    die "The official Cyan checkout does not contain its D-Bus policy"
  workdir="$(mktemp -d /tmp/bc250-cyan-base.XXXXXX)"
  trap 'rm -rf -- "$workdir"' EXIT

  # Never replace a user's governor configuration.  A default is installed
  # only when the package/archive left no configuration at all.
  if [[ ! -f "$CONFIG" ]]; then
    info "Installing the missing official Cyan default configuration"
    as_root install -D -m 0644 "$SOURCE_DIR/default-config.toml" "$CONFIG"
  fi
  if [[ ! -f "$DBUS_POLICY" ]]; then
    info "Installing the missing official Cyan D-Bus policy"
    as_root install -D -m 0644 "$SOURCE_DIR/com.cyanskillfish.Governor.conf" "$DBUS_POLICY"
  fi
  # D-Bus does not necessarily rescan policy files immediately when a new
  # policy is dropped into /etc/dbus-1/system.d.  A fresh SteamOS install can
  # therefore start Cyan successfully while the bus still rejects ownership of
  # com.cyanskillfish.Governor.  Upstream's own installer explicitly reloads
  # the system-bus configuration after installing this policy, so mirror that
  # contract here before the service can be enabled from the GUI.
  grep -Fq '<allow own="com.cyanskillfish.Governor"/>' "$DBUS_POLICY" ||
    die "The installed Cyan D-Bus policy does not authorize com.cyanskillfish.Governor"
  if have busctl; then
    info "Reloading the system D-Bus policy for Cyan"
    as_root busctl --system call org.freedesktop.DBus /org/freedesktop/DBus       org.freedesktop.DBus ReloadConfig >/dev/null
  else
    die "busctl is required to reload the Cyan D-Bus policy"
  fi
  if [[ ! -x "$PERFORMANCE_MODE" && -f "$SOURCE_DIR/scripts/cyan-skillfish-performance-mode" ]]; then
    as_root install -D -m 0755 "$SOURCE_DIR/scripts/cyan-skillfish-performance-mode" "$PERFORMANCE_MODE"
  fi

  if is_openrc; then
    if [[ ! -f "$OPENRC_SERVICE" ]]; then
      info "Installing the BC250 OpenRC Cyan service"
      printf '%s\n' \
        '#!/sbin/openrc-run' \
        '# Managed by BC250 Control Center (OpenRC)' \
        'description="Cyan Skillfish GPU Governor"' \
        "command=$binary" \
        "command_args=$CONFIG" \
        'command_background=yes' \
        'pidfile=/run/cyan-skillfish-governor-smu.pid' \
        '' \
        'depend() {' \
        '  need dbus' \
        '  after localmount' \
        '}' >"$workdir/openrc-service"
      as_root install -D -m 0755 "$workdir/openrc-service" "$OPENRC_SERVICE"
    fi
    # Preparation installs a reviewed binary/configuration, but it must not
    # silently make an optional governor persistent.  GPU control activates
    # it through the protected OpenRC service helper after the user requests
    # that action explicitly.
    return 0
  fi

  load_state="$(systemctl show "$SERVICE" -p LoadState --value 2>/dev/null || true)"
  if [[ "$load_state" == "masked" ]]; then
    info "Removing the stale Cyan service mask; the service remains disabled"
    as_root systemctl unmask "$SERVICE"
    as_root systemctl daemon-reload
    load_state="$(systemctl show "$SERVICE" -p LoadState --value 2>/dev/null || true)"
  fi
  if [[ "$load_state" == "not-found" || -z "$load_state" ]]; then
    info "Installing the missing official Cyan systemd service"
    printf '%s\n' \
      '[Unit]' \
      'Description=Cyan Skillfish GPU Governor' \
      'Conflicts=cyan-skillfish-governor.service cyan-skillfish-governor-tt.service oberon-governor.service' \
      '' \
      '[Service]' \
      "ExecStart=$binary $CONFIG" \
      'ManagedOOMPreference=avoid' \
      'OOMScoreAdjust=-1000' \
      'Restart=on-failure' \
      'RestartSec=5' \
      '' \
      '[Install]' \
      'WantedBy=default.target' >"$workdir/service"
    as_root install -D -m 0644 "$workdir/service" "$FALLBACK_UNIT"
    printf '%s\n' "$FALLBACK_UNIT" >"$workdir/managed-fallback-unit"
    as_root install -D -m 0644 "$workdir/managed-fallback-unit" "$FALLBACK_UNIT_MARKER"
    as_root systemctl daemon-reload
  fi

  systemctl cat "$SERVICE" >/dev/null 2>&1 ||
    die "The Cyan systemd service is still unavailable after repair"
)

install_release() (
  local release_tag="$1"
  local archive_name base_url workdir extracted binary version actual_sha256
  archive_name="cyan-skillfish-governor-smu-${release_tag}-x86_64-linux.tar.gz"
  base_url="$REPOSITORY/releases/download/${release_tag}"
  workdir="$(mktemp -d /tmp/bc250-cyan-release.XXXXXX)"
  trap 'rm -rf -- "$workdir"' EXIT

  info "Downloading official Cyan SMU ${release_tag} release"
  curl --fail --location --retry 3 --output "$workdir/$archive_name" \
    "$base_url/$archive_name"
  actual_sha256="$(sha256sum "$workdir/$archive_name" | awk '{print $1}')"
  [[ "$actual_sha256" == "$REVIEWED_ARCHIVE_SHA256" ]] ||
    die "The reviewed Cyan release digest did not match; nothing was installed"

  mkdir -p "$workdir/extracted"
  tar -xzf "$workdir/$archive_name" -C "$workdir/extracted"
  mapfile -t binaries < <(find "$workdir/extracted" -type f \
    -name cyan-skillfish-governor-smu -print)
  [[ ${#binaries[@]} -eq 1 ]] ||
    die "The Cyan release archive did not contain exactly one governor binary"
  binary="${binaries[0]}"
  supports_frequency_fix "$binary" ||
    die "The reviewed Cyan release does not contain the required GPU frequency-reporting fix"
  version="$($binary --version 2>&1)"
  [[ "$version" == *"${release_tag}"* ]] ||
    die "The downloaded binary version does not match ${release_tag}: ${version}"

  local config_before=""
  if [[ -f "$CONFIG" ]]; then
    config_before="$(sha256sum "$CONFIG" | awk '{print $1}')"
  fi

  as_root install -D -m 0755 "$binary" "$MANAGED_BINARY"
  as_root install -d -m 0755 "$STATE_DIR"
  if ! is_openrc; then
    as_root install -d -m 0755 "$DROPIN_DIR"
    printf '%s\n' \
      '# Managed by BC250 Control Center. The distro package and TOML are preserved.' \
      '[Service]' \
      'ExecStart=' \
      "ExecStart=$MANAGED_BINARY $CONFIG" >"$workdir/override.conf"
    as_root install -m 0644 "$workdir/override.conf" "$DROPIN"
  fi
  printf '%s\n' "$release_tag" >"$workdir/release"
  printf '%s\n' "$REPOSITORY/tree/smu" >"$workdir/source"
  as_root install -m 0644 "$workdir/release" "$STATE_DIR/release"
  as_root install -m 0644 "$workdir/source" "$STATE_DIR/source"
  ensure_base_installation "$MANAGED_BINARY"
  if ! is_openrc; then as_root systemctl daemon-reload; fi

  if [[ -n "$config_before" ]]; then
    [[ "$(sha256sum "$CONFIG" | awk '{print $1}')" == "$config_before" ]] ||
      die "The governor TOML changed during the binary update"
  fi
  supports_frequency_fix "$MANAGED_BINARY" ||
    die "The installed Cyan binary failed the frequency-fix capability check"
  info "Cyan ${release_tag} staged; the existing TOML and service enable state were preserved"
)

[[ "$(uname -m)" == "x86_64" ]] || die "The official Cyan release is available only for x86_64"
have curl || die "curl is required to obtain the reviewed Cyan release"
have sha256sum || die "sha256sum is required to verify the upstream release"
have tar || die "tar is required to unpack the upstream release"
require_source_checkout
if have steamos-readonly; then
  bc250_steamos_unlock_root
fi

logical_cpus="$(getconf _NPROCESSORS_ONLN 2>/dev/null || printf '0')"
[[ "$logical_cpus" =~ ^[0-9]+$ ]] || logical_cpus=0
info "${logical_cpus} logical CPUs detected; preserving the selected Cyan compatibility switches"

if [[ -n "${BC250_CYAN_RELEASE_TAG:-}" && "$BC250_CYAN_RELEASE_TAG" != "$REVIEWED_RELEASE_TAG" ]]; then
  die "BC250_CYAN_RELEASE_TAG must match the reviewed Cyan release $REVIEWED_RELEASE_TAG"
fi
release_tag="$REVIEWED_RELEASE_TAG"
info "Using Control Center reviewed Cyan release $release_tag"
target_family="${BC250_CYAN_TARGET_FAMILY:-unknown}"
case "$target_family" in
  bazzite|arch|cachyos|manjaro|debian|ubuntu|fedora|steamos) patched_runtime=1 ;;
  *) patched_runtime=0 ;;
esac
if [[ "$patched_runtime" -eq 1 ]]; then
  runtime_ready=0
  current_patcher_sha="$(sha256sum "$BC250CC_PATCHER" | awk '{print $1}')"
  managed_version="$($MANAGED_BINARY --version 2>/dev/null | head -n 1 || true)"
  if supports_frequency_fix "$MANAGED_BINARY" && \
     [[ "$managed_version" == *"${BC250CC_RUNTIME_REVISION}"* ]] && \
     [[ -r "$STATE_DIR/runtime-revision" ]] && \
     [[ "$(<"$STATE_DIR/runtime-revision")" == "$BC250CC_RUNTIME_REVISION" ]] && \
     [[ -r "$STATE_DIR/upstream-commit" ]] && \
     [[ "$(<"$STATE_DIR/upstream-commit")" == "$REVIEWED_COMMIT" ]] && \
     [[ -r "$STATE_DIR/patcher-sha256" ]] && \
     [[ "$current_patcher_sha" == "$(<"$STATE_DIR/patcher-sha256")" ]] && \
     [[ -r "$STATE_DIR/binary-sha256" ]] && \
     [[ "$(sha256sum "$MANAGED_BINARY" | awk '{print $1}')" == "$(<"$STATE_DIR/binary-sha256")" ]]; then
    runtime_ready=1
  fi
  if [[ "$runtime_ready" -eq 1 ]]; then
    info "BC250CC Cyan runtime ${BC250CC_RUNTIME_REVISION} is already staged; no rebuild needed"
  else
    build_bc250cc_runtime
  fi
  # Install/preserve config, D-Bus policy and service binding exactly as the
  # upstream release path does, but use the locally reviewed patched binary.
  ensure_base_installation "$MANAGED_BINARY"
  if ! is_openrc; then
    as_root install -d -m 0755 "$DROPIN_DIR"
    override_tmp="$(mktemp /tmp/bc250-cyan-override.XXXXXX)"
    printf '%s\n' \
      '# Managed by BC250 Control Center. The distro package and TOML are preserved.' \
      '[Service]' \
      'ExecStart=' \
      "ExecStart=$MANAGED_BINARY $CONFIG" >"$override_tmp"
    if ! as_root install -m 0644 "$override_tmp" "$DROPIN"; then
      rm -f -- "$override_tmp"
      die "The Cyan systemd override could not be installed"
    fi
    rm -f -- "$override_tmp"
    as_root systemctl daemon-reload
  fi
else
  if supports_frequency_fix "$MANAGED_BINARY" && \
     [[ -r "$STATE_DIR/release" ]] && \
     [[ "$(<"$STATE_DIR/release")" == "$release_tag" ]] && \
     { is_openrc || [[ -r "$DROPIN" ]]; }; then
    info "Cyan ${release_tag} frequency fix is already staged; no files changed"
  else
    install_release "$release_tag"
  fi
  ensure_base_installation "$MANAGED_BINARY"
fi
validate_compatibility_switches

printf 'BC250_CYAN_RELEASE=%s\n' "$release_tag"
printf 'BC250_CYAN_BINARY=%s\n' "$MANAGED_BINARY"
printf 'BC250_CYAN_RUNTIME_REVISION=%s\n' "$(if [[ "$patched_runtime" -eq 1 ]]; then printf '%s' "$BC250CC_RUNTIME_REVISION"; else printf '%s' upstream; fi)"
