#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../common/common.sh"
: "${BC250_NCT6687_SOURCE_DIR:=$BC250_TOOLS_DIR/nct6687d}"
echo "== SteamOS: preparing nct6687 PWM support for the active Neptune kernel ==";
echo "Source: https://github.com/Fred78290/nct6687d";
if command -v steamos-readonly >/dev/null 2>&1; then
  sudo steamos-readonly disable || true;
fi;
sudo pacman-key --init 2>/dev/null || true;
sudo pacman-key --populate holo 2>/dev/null || true;
sudo pacman-key --populate archlinux 2>/dev/null || true;
sudo pacman -Syy --noconfirm || true;
sudo pacman -S --needed --noconfirm lm_sensors git base-devel fakeroot debugedit gcc make pkgconf pahole dkms curl zstd tar || true;

kver="$(uname -r)"
base_kver="$(printf '%s
' "$kver" | sed 's/-g[0-9a-fA-F].*$//')"
echo "Running kernel: $kver"
echo "Base kernel: $base_kver"

find_build_dir() {
  for d in     "/usr/lib/modules/$kver/build"     "/lib/modules/$kver/build"     "/usr/lib/modules/$base_kver/build"     "/lib/modules/$base_kver/build"; do
    [ -d "$d" ] && [ -f "$d/Makefile" ] && printf '%s
' "$d" && return 0
  done
  {
    find /usr/lib/modules /lib/modules -maxdepth 3 -type d -path '*/build' 2>/dev/null
    find /usr/src -maxdepth 5 -type d 2>/dev/null
  } | while IFS= read -r d; do
    [ -f "$d/Makefile" ] && printf '%s
' "$d"
  done | grep -E 'neptune|valve|linux' | sort -V | tail -n 1
}

build_dir="$(find_build_dir | head -n 1)"
if [ -z "$build_dir" ]; then
  echo "WARN: kernel build tree for $kver is missing. Trying SteamOS/Neptune headers."
  kernel_pkg="$(pacman -Qoq "/usr/lib/modules/$kver" 2>/dev/null | head -n 1 || true)"
  if [ -n "$kernel_pkg" ]; then
    echo "Detected kernel package: $kernel_pkg -> ${kernel_pkg}-headers"
    sudo pacman -S --needed --noconfirm "${kernel_pkg}-headers" 2>/dev/null || true
  fi
  case "$kver" in
    *neptune-616*) sudo pacman -S --needed --noconfirm linux-neptune-616-headers 2>/dev/null || true ;;
    *neptune-61*) sudo pacman -S --needed --noconfirm linux-neptune-61-headers 2>/dev/null || true ;;
    *neptune*) sudo pacman -S --needed --noconfirm linux-neptune-headers 2>/dev/null || true ;;
    *) sudo pacman -S --needed --noconfirm linux-headers 2>/dev/null || true ;;
  esac
  build_dir="$(find_build_dir | head -n 1)"
fi

steam_headers_pkg_name() {
  rel="$1"
  case "$rel" in *-neptune-*-g*) ;; *) return 1 ;; esac
  sha="${rel##*-g}"
  rest="${rel%-g$sha}"
  flavor="${rest##*-neptune-}"
  mid="${rest%-neptune-$flavor}"
  pkgrel="${mid##*-}"
  kver_pkg="${mid%-$pkgrel}"
  pkgver="$(printf '%s
' "$kver_pkg" | tr '-' '.')"
  printf 'linux-neptune-%s-headers-%s-%s-x86_64.pkg.tar.zst
' "$flavor" "$pkgver" "$pkgrel"
}

fetch_headers_pkg() {
  hdrpkg="$1"
  dest="$2"
  mirror="https://steamdeck-packages.steamos.cloud/archlinux-mirror"
  repos="$(sed -n 's/^\[\(.*\)\]$/\1/p' /etc/pacman.conf 2>/dev/null | grep '^jupiter-' || true) jupiter-rel jupiter-main jupiter-3.8 jupiter-3.7 jupiter-3.6 jupiter-beta jupiter-beta-staging holo-main"
  for repo in $repos; do
    echo "Trying headers package from $repo: $hdrpkg"
    if curl -fsSL -o "$dest" "$mirror/$repo/os/x86_64/$hdrpkg" 2>/dev/null; then
      echo "OK: downloaded $hdrpkg from $repo"
      return 0
    fi
    rm -f "$dest"
  done
  return 1
}

if [ -z "$build_dir" ]; then
  hdrpkg="$(steam_headers_pkg_name "$kver" || true)"
  if [ -n "$hdrpkg" ]; then
    tmp_headers="$(mktemp -d)"
    if fetch_headers_pkg "$hdrpkg" "$tmp_headers/$hdrpkg"; then
      echo "== Extracting SteamOS headers fallback =="
      sudo tar --zstd -xf "$tmp_headers/$hdrpkg" -C /
    fi
    rm -rf "$tmp_headers"
    build_dir="$(find_build_dir | head -n 1)"
  fi
fi

if [ -z "$build_dir" ]; then
  echo "ERROR: no kernel build directory found for $kver."
  echo "Run: find /usr/lib/modules /lib/modules -maxdepth 3 -path '*/build' -print"
  echo "Then send the output together with: uname -r"
  exit 1
fi

echo "Using kernel build directory: $build_dir"
echo "== Preparing Fred78290/nct6687d source =="
mkdir -p "$(dirname "${BC250_NCT6687_SOURCE_DIR}")"
if [ -d "${BC250_NCT6687_SOURCE_DIR}"/.git ]; then
  git -C "${BC250_NCT6687_SOURCE_DIR}" pull --ff-only || true
elif [ -f "${BC250_NCT6687_SOURCE_DIR}"/Makefile ]; then
  echo "OK: existing nct6687d source tree found."
else
  if [ -d "${BC250_NCT6687_SOURCE_DIR}" ]; then
    incomplete=""${BC250_NCT6687_SOURCE_DIR}".incomplete-$(date +%Y%m%d-%H%M%S)"
    echo "WARN: incomplete nct6687d source found; preserving it at $incomplete"
    mv "${BC250_NCT6687_SOURCE_DIR}" "$incomplete"
  fi
  git clone --depth 1 https://github.com/Fred78290/nct6687d "${BC250_NCT6687_SOURCE_DIR}"
fi
if [ ! -f "${BC250_NCT6687_SOURCE_DIR}"/Makefile ] || [ ! -f "${BC250_NCT6687_SOURCE_DIR}"/nct6687.c ]; then
  echo "ERROR: nct6687d source is incomplete."
  exit 1
fi

echo "== Building nct6687 for SteamOS kernel =="
build_work=""${BC250_NCT6687_SOURCE_DIR}"/bc250-build-$kver"
rm -rf "$build_work"
mkdir -p "$build_work"
cp "${BC250_NCT6687_SOURCE_DIR}"/nct6687.c "$build_work/"
printf 'obj-m += nct6687.o
' > "$build_work/Makefile"
build_flags=""
if grep -qs 'CONFIG_CC_IS_CLANG=y' "$build_dir/.config" 2>/dev/null; then
  build_flags="LLVM=1"
  echo "Kernel was built with clang; building external module with LLVM=1."
fi
if make -C "$build_dir" M="$build_work" $build_flags modules; then
  ko_path="$build_work/nct6687.ko"
else
  echo "WARN: direct kernel build failed; trying upstream Makefile fallback."
  (cd "${BC250_NCT6687_SOURCE_DIR}" && make clean) || true
  if (cd "${BC250_NCT6687_SOURCE_DIR}" && make kver="$kver" build); then
    ko_path=""${BC250_NCT6687_SOURCE_DIR}"/$kver/nct6687.ko"
  elif [ "$base_kver" != "$kver" ] && (cd "${BC250_NCT6687_SOURCE_DIR}" && make kver="$base_kver" build); then
    ko_path=""${BC250_NCT6687_SOURCE_DIR}"/$base_kver/nct6687.ko"
  elif (cd "${BC250_NCT6687_SOURCE_DIR}" && make build); then
    ko_path="$(find "${BC250_NCT6687_SOURCE_DIR}" -name nct6687.ko -type f | head -n 1)"
  else
    echo "ERROR: nct6687 build failed. Check compiler and kernel header output above."
    exit 1
  fi
fi
if [ -z "${ko_path:-}" ] || [ ! -f "$ko_path" ]; then
  echo "ERROR: nct6687.ko was not produced."
  exit 1
fi

echo "== Installing kernel-matched module =="
sudo install -Dm644 "$ko_path" /var/lib/nct6687/nct6687.ko
sudo chmod 0644 /var/lib/nct6687/nct6687.ko
sudo chcon -t modules_object_t /var/lib/nct6687/nct6687.ko 2>/dev/null || true
sudo restorecon -v /var/lib/nct6687/nct6687.ko 2>/dev/null || true
kernel_module_root="/usr/lib/modules/$kver"
if [ ! -d "$kernel_module_root" ] && [ -d "/lib/modules/$kver" ]; then
  kernel_module_root="/lib/modules/$kver"
fi
kernel_module_path="$kernel_module_root/kernel/drivers/hwmon/nct6687.ko"
if [ -d "$kernel_module_root" ]; then
  sudo install -Dm644 "$ko_path" "$kernel_module_path"
  sudo chmod 0644 "$kernel_module_path"
  sudo chcon -t modules_object_t "$kernel_module_path" 2>/dev/null || true
  sudo restorecon -v "$kernel_module_path" 2>/dev/null || true
  echo "OK: nct6687 installed at $kernel_module_path"
else
  echo "WARN: kernel module root was not found; /var/lib/nct6687 fallback will be used."
fi
sudo depmod -a "$kver" 2>/dev/null || true

echo "== Configuring module preference =="
echo 'blacklist nct6683' | sudo tee /etc/modprobe.d/nct6683.conf >/dev/null
echo 'options nct6687 force=true' | sudo tee /etc/modprobe.d/nct6687.conf >/dev/null
printf 'blacklist nct6683\noptions nct6687 force=true\n' | sudo tee /etc/modprobe.d/sensors.conf >/dev/null
echo 'nct6687' | sudo tee /etc/modules-load.d/nct6687.conf >/dev/null
echo 'nct6687' | sudo tee /etc/modules-load.d/99-sensors.conf >/dev/null
sudo modprobe -r nct6683 2>/dev/null || true
sudo modprobe -r nct6687 2>/dev/null || true
load_err="$(mktemp -t bc250-nct6687-load-now.XXXXXX)"
trap 'rm -f "$load_err"' EXIT
: > "$load_err"
if sudo modprobe nct6687 force=true 2>"$load_err" || sudo modprobe nct6687 2>>"$load_err"; then
  echo "OK: nct6687 loaded with modprobe."
else
  echo "WARN: modprobe failed; trying /var/lib fallback."
  cat "$load_err" || true
  sudo insmod /var/lib/nct6687/nct6687.ko force=1 2>>"$load_err" || sudo insmod /var/lib/nct6687/nct6687.ko 2>>"$load_err" || true
fi
if command -v udevadm >/dev/null 2>&1; then
  sudo udevadm trigger --subsystem-match=hwmon 2>/dev/null || true
  sudo udevadm settle --timeout=15 2>/dev/null || true
fi
bc250_nct6687_ready() {
  for n in /sys/class/hwmon/hwmon*/name; do
    [ -r "$n" ] || continue
    name="$(cat "$n" 2>/dev/null || true)"
    case "$name" in nct668*|nct67*|nct*) dir="${n%/name}"; ls "$dir"/fan*_input "$dir"/pwm* >/dev/null 2>&1 && return 0 ;; esac
  done
  sensors 2>/dev/null | awk '/nct6686-isa/{seen=1} seen && /(Fan|fan|pwm)[ #0-9]*:/ {ok=1} END{exit ok?0:1}'
}
if ! lsmod | grep -q '^nct6687 ' || ! bc250_nct6687_ready; then
  echo "ERROR: nct6687 loaded check failed or fan/PWM hwmon is not ready."
  cat "$load_err" || true
  journalctl -u nct6687-load.service -b --no-pager | tail -120 2>/dev/null || true
  exit 1
fi
sensors | sed -n '/nct6686/,+45p' || true
echo "OK: SteamOS nct6687 PWM module is ready and the NCT fan/PWM hwmon is visible."
