#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../common/common.sh"
: "${BC250_NCT6687_SOURCE_DIR:=$BC250_TOOLS_DIR/nct6687d}"

bold "SteamOS: preparing nct6687 PWM support for the active Neptune kernel"
echo "Source: https://github.com/Fred78290/nct6687d"
if have steamos-readonly; then
  as_root steamos-readonly disable || true
fi
as_root pacman-key --init 2>/dev/null || true
as_root pacman-key --populate holo 2>/dev/null || true
as_root pacman-key --populate archlinux 2>/dev/null || true
as_root pacman -Syy --noconfirm || true
as_root pacman -S --needed --noconfirm lm_sensors git base-devel fakeroot debugedit gcc make pkgconf pahole dkms curl zstd tar kmod || true

KERNEL_RELEASE="$(bc250_running_kernel_release)"
MODULE_ROOT="/usr/lib/modules/$KERNEL_RELEASE"
[[ -d "$MODULE_ROOT" ]] || MODULE_ROOT="/lib/modules/$KERNEL_RELEASE"
info "Running SteamOS kernel: $KERNEL_RELEASE"
bc250_kernel_headers_preflight "$KERNEL_RELEASE" || true

kernel_package=""
if [[ -r "$MODULE_ROOT/pkgbase" ]]; then
  IFS= read -r kernel_package < "$MODULE_ROOT/pkgbase" || true
fi
if [[ -z "$kernel_package" && -d "$MODULE_ROOT" ]]; then
  kernel_package="$(pacman -Qoq "$MODULE_ROOT" 2>/dev/null | head -n 1 || true)"
fi
if ! bc250_find_matching_kernel_build_dir "$KERNEL_RELEASE" && [[ -n "$kernel_package" ]]; then
  info "Detected active SteamOS kernel package: $kernel_package"
  info "Trying exact headers package: ${kernel_package}-headers"
  as_root pacman -S --needed --noconfirm "${kernel_package}-headers" 2>/dev/null || true
fi
if ! bc250_find_matching_kernel_build_dir "$KERNEL_RELEASE"; then
  case "$KERNEL_RELEASE" in
    *neptune-616*) as_root pacman -S --needed --noconfirm linux-neptune-616-headers 2>/dev/null || true ;;
    *neptune-61*) as_root pacman -S --needed --noconfirm linux-neptune-61-headers 2>/dev/null || true ;;
    *neptune*) as_root pacman -S --needed --noconfirm linux-neptune-headers 2>/dev/null || true ;;
    *) as_root pacman -S --needed --noconfirm linux-headers 2>/dev/null || true ;;
  esac
fi

steam_headers_pkg_name() {
  local release="$1" sha rest flavor mid pkgrel kernel_version package_version
  case "$release" in *-neptune-*-g*) ;; *) return 1 ;; esac
  sha="${release##*-g}"
  rest="${release%-g$sha}"
  flavor="${rest##*-neptune-}"
  mid="${rest%-neptune-$flavor}"
  pkgrel="${mid##*-}"
  kernel_version="${mid%-$pkgrel}"
  package_version="$(printf '%s\n' "$kernel_version" | tr '-' '.')"
  printf 'linux-neptune-%s-headers-%s-%s-x86_64.pkg.tar.zst\n' "$flavor" "$package_version" "$pkgrel"
}

fetch_headers_pkg() {
  local package_name="$1" destination="$2" repository
  local mirror="https://steamdeck-packages.steamos.cloud/archlinux-mirror"
  local repositories
  repositories="$(sed -n 's/^\[\(.*\)\]$/\1/p' /etc/pacman.conf 2>/dev/null | grep '^jupiter-' || true) jupiter-rel jupiter-main jupiter-3.8 jupiter-3.7 jupiter-3.6 jupiter-beta jupiter-beta-staging holo-main"
  for repository in $repositories; do
    info "Trying exact SteamOS headers from $repository: $package_name"
    if curl -fsSL -o "$destination" "$mirror/$repository/os/x86_64/$package_name" 2>/dev/null; then
      info "Downloaded $package_name from $repository"
      return 0
    fi
    rm -f "$destination"
  done
  return 1
}

if ! bc250_find_matching_kernel_build_dir "$KERNEL_RELEASE"; then
  headers_package="$(steam_headers_pkg_name "$KERNEL_RELEASE" || true)"
  if [[ -n "$headers_package" ]]; then
    temporary_headers="$(mktemp -d)"
    if fetch_headers_pkg "$headers_package" "$temporary_headers/$headers_package"; then
      bold "Extracting exact SteamOS headers fallback"
      as_root tar --zstd -xf "$temporary_headers/$headers_package" -C /
    fi
    rm -rf "$temporary_headers"
  fi
fi

if ! bc250_require_matching_kernel_headers "$KERNEL_RELEASE"; then
  error "SteamOS repair failed safely: only headers for another kernel were found or the exact Neptune headers are unavailable."
  error "Update SteamOS, reboot so uname -r changes to the installed kernel, then run Prepare PWM driver again."
  error "Diagnostic commands: uname -r; find /usr/lib/modules /lib/modules /usr/src -path '*/build/Makefile' -o -path '*/include/config/kernel.release'"
  exit 21
fi
BUILD_DIR="$BC250_KERNEL_BUILD_DIR"
info "Using verified kernel build directory: $BUILD_DIR"

bold "Preparing Fred78290/nct6687d source"
mkdir -p "$(dirname "$BC250_NCT6687_SOURCE_DIR")"
if [[ -d "$BC250_NCT6687_SOURCE_DIR/.git" ]]; then
  git -C "$BC250_NCT6687_SOURCE_DIR" pull --ff-only || true
elif [[ -f "$BC250_NCT6687_SOURCE_DIR/Makefile" ]]; then
  info "Existing nct6687d source tree found"
else
  if [[ -d "$BC250_NCT6687_SOURCE_DIR" ]]; then
    incomplete="${BC250_NCT6687_SOURCE_DIR}.incomplete-$(date +%Y%m%d-%H%M%S)"
    warn "Incomplete nct6687d source found; preserving it at $incomplete"
    mv "$BC250_NCT6687_SOURCE_DIR" "$incomplete"
  fi
  git clone --depth 1 https://github.com/Fred78290/nct6687d "$BC250_NCT6687_SOURCE_DIR"
fi
if [[ ! -f "$BC250_NCT6687_SOURCE_DIR/Makefile" || ! -f "$BC250_NCT6687_SOURCE_DIR/nct6687.c" ]]; then
  error "nct6687d source is incomplete"
  exit 22
fi

bold "Building nct6687 for the exact SteamOS kernel"
BUILD_WORK="$BC250_NCT6687_SOURCE_DIR/bc250-build-$KERNEL_RELEASE"
rm -rf "$BUILD_WORK"
mkdir -p "$BUILD_WORK"
cp "$BC250_NCT6687_SOURCE_DIR/nct6687.c" "$BUILD_WORK/"
printf 'obj-m += nct6687.o\n' > "$BUILD_WORK/Makefile"
build_flags=()
if grep -qs 'CONFIG_CC_IS_CLANG=y' "$BUILD_DIR/.config" 2>/dev/null; then
  build_flags=(LLVM=1)
  info "Kernel was built with clang; building the external module with LLVM=1"
fi
if make -C "$BUILD_DIR" M="$BUILD_WORK" "${build_flags[@]}" modules; then
  MODULE_PATH="$BUILD_WORK/nct6687.ko"
else
  warn "Direct verified-tree build failed; trying the upstream Makefile for the same exact kernel release only"
  (cd "$BC250_NCT6687_SOURCE_DIR" && make clean) || true
  if (cd "$BC250_NCT6687_SOURCE_DIR" && make kver="$KERNEL_RELEASE" build); then
    MODULE_PATH="$BC250_NCT6687_SOURCE_DIR/$KERNEL_RELEASE/nct6687.ko"
  else
    error "nct6687 build failed. Compiler and exact-header diagnostics are shown above."
    exit 22
  fi
fi
[[ -f "${MODULE_PATH:-}" ]] || { error "nct6687.ko was not produced"; exit 22; }
bc250_verify_module_vermagic "$MODULE_PATH" "$KERNEL_RELEASE"

bold "Installing kernel-matched module"
as_root install -Dm644 "$MODULE_PATH" /var/lib/nct6687/nct6687.ko
as_root chmod 0644 /var/lib/nct6687/nct6687.ko
as_root chcon -t modules_object_t /var/lib/nct6687/nct6687.ko 2>/dev/null || true
as_root restorecon -v /var/lib/nct6687/nct6687.ko 2>/dev/null || true
kernel_module_root="/usr/lib/modules/$KERNEL_RELEASE"
[[ -d "$kernel_module_root" ]] || kernel_module_root="/lib/modules/$KERNEL_RELEASE"
kernel_module_path="$kernel_module_root/kernel/drivers/hwmon/nct6687.ko"
if [[ -d "$kernel_module_root" ]]; then
  as_root install -Dm644 "$MODULE_PATH" "$kernel_module_path"
  as_root chmod 0644 "$kernel_module_path"
  as_root chcon -t modules_object_t "$kernel_module_path" 2>/dev/null || true
  as_root restorecon -v "$kernel_module_path" 2>/dev/null || true
  info "nct6687 installed at $kernel_module_path"
else
  warn "Kernel module root was not found; /var/lib/nct6687 fallback will be used"
fi
as_root depmod -a "$KERNEL_RELEASE" 2>/dev/null || true

bold "Configuring module preference"
echo 'blacklist nct6683' | as_root tee /etc/modprobe.d/nct6683.conf >/dev/null
echo 'options nct6687 force=true' | as_root tee /etc/modprobe.d/nct6687.conf >/dev/null
printf 'blacklist nct6683\noptions nct6687 force=true\n' | as_root tee /etc/modprobe.d/sensors.conf >/dev/null
echo 'nct6687' | as_root tee /etc/modules-load.d/nct6687.conf >/dev/null
echo 'nct6687' | as_root tee /etc/modules-load.d/99-sensors.conf >/dev/null
as_root modprobe -r nct6683 2>/dev/null || true
as_root modprobe -r nct6687 2>/dev/null || true
load_error="$(mktemp -t bc250-nct6687-load-now.XXXXXX)"
trap 'rm -f "$load_error"' EXIT
: > "$load_error"
if as_root modprobe nct6687 force=true 2>"$load_error" || as_root modprobe nct6687 2>>"$load_error"; then
  info "nct6687 loaded with modprobe"
else
  warn "modprobe failed; trying the verified /var/lib module fallback"
  cat "$load_error" || true
  as_root insmod /var/lib/nct6687/nct6687.ko force=1 2>>"$load_error" || as_root insmod /var/lib/nct6687/nct6687.ko 2>>"$load_error" || true
fi
if have udevadm; then
  as_root udevadm trigger --subsystem-match=hwmon 2>/dev/null || true
  as_root udevadm settle --timeout=15 2>/dev/null || true
fi
bc250_nct6687_ready() {
  local node name directory
  for node in /sys/class/hwmon/hwmon*/name; do
    [[ -r "$node" ]] || continue
    name="$(cat "$node" 2>/dev/null || true)"
    case "$name" in
      nct668*|nct67*|nct*)
        directory="${node%/name}"
        ls "$directory"/fan*_input "$directory"/pwm* >/dev/null 2>&1 && return 0
        ;;
    esac
  done
  sensors 2>/dev/null | awk '/nct6686-isa/{seen=1} seen && /(Fan|fan|pwm)[ #0-9]*:/ {ok=1} END{exit ok?0:1}'
}
if ! lsmod | grep -q '^nct6687 ' || ! bc250_nct6687_ready; then
  error "nct6687 load verification failed or the fan/PWM hwmon is not ready"
  cat "$load_error" || true
  journalctl -u nct6687-load.service -b --no-pager | tail -120 2>/dev/null || true
  exit 22
fi
sensors | sed -n '/nct6686/,+45p' || true
info "SteamOS nct6687 PWM module is ready and the NCT fan/PWM hwmon is visible"
