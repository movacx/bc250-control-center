#!/usr/bin/env bash
# Installs system dependencies for BC250 Control Center by distribution.
# Called by the GUI through "Prepare dependencies".

set -u
export LC_ALL=C
export LANG=C

MODE="runtime"
YES=0
for arg in "$@"; do
  case "$arg" in
    --yes|-y) YES=1 ;;
    --runtime|--all) MODE="runtime" ;;
    --help|-h)
      cat <<HELP
Usage: $0 [--runtime] [--yes]

Installs base/hardware dependencies for BC250 Control Center:
- PyQt6/psutil/lm_sensors/stress/git/pciutils/libdrm/mesa/vulkan tools
- cyan-skillfish-governor-smu when the distribution has a known install flow

HELP
      exit 0
      ;;
  esac
done

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
info() { printf '[INFO] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*"; }
err()  { printf '[ERR ] %s\n' "$*" >&2; }
have() { command -v "$1" >/dev/null 2>&1; }

os_id=""
os_like=""
os_name=""
variant_id=""
if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  os_id="${ID:-}"
  os_like="${ID_LIKE:-}"
  os_name="${NAME:-}"
  variant_id="${VARIANT_ID:-}"
elif [ -r /usr/lib/os-release ]; then
  # shellcheck disable=SC1091
  . /usr/lib/os-release
  os_id="${ID:-}"
  os_like="${ID_LIKE:-}"
  os_name="${NAME:-}"
  variant_id="${VARIANT_ID:-}"
fi

lower_os="$(printf '%s %s %s %s' "$os_id" "$os_like" "$os_name" "$variant_id" | tr '[:upper:]' '[:lower:]')"
in_container=0
[ -f /.dockerenv ] && in_container=1
[ -f /run/.containerenv ] && in_container=1
[ -n "${container:-}" ] && in_container=1

is_ostree=0
if have rpm-ostree && printf '%s' "$lower_os" | grep -Eq 'bazzite|silverblue|kinoite|ublue|atomic'; then
  is_ostree=1
fi

is_steamos=0
if printf '%s' "$lower_os" | grep -Eq 'steamos|steamdeck|holo'; then
  is_steamos=1
fi

SUDO="sudo"
[ "$(id -u)" = "0" ] && SUDO=""

run_cmd() {
  info "$*"
  "$@"
}

pacman_install() {
  local pkgs=(python python-pyqt6 python-psutil lm_sensors stress git pciutils libdrm vulkan-tools mesa-utils)
  run_cmd $SUDO pacman -S --needed --noconfirm "${pkgs[@]}"
}

dnf_install() {
  local pkgs=(python3 python3-pyqt6 python3-psutil lm_sensors stress git pciutils libdrm vulkan-tools)
  run_cmd $SUDO dnf install -y "${pkgs[@]}"
}

apt_install() {
  local pkgs=(python3 python-is-python3 python3-pyqt6 python3-psutil lm-sensors stress git pciutils libdrm2 libdrm-amdgpu1 mesa-utils vulkan-tools curl ca-certificates dbus dbus-user-session build-essential dkms dh-dkms "linux-headers-$(uname -r)")
  run_cmd $SUDO apt update
  run_cmd $SUDO apt install -y "${pkgs[@]}" || {
    warn "Some Debian/Ubuntu packages failed. Retrying core runtime packages without kernel headers/DKMS."
    run_cmd $SUDO apt install -y python3 python-is-python3 python3-pyqt6 python3-psutil lm-sensors stress git pciutils libdrm2 libdrm-amdgpu1 mesa-utils vulkan-tools curl ca-certificates dbus dbus-user-session build-essential || true
  }
  if ! have pkexec; then
    warn "pkexec was not found. Trying common Polkit packages."
    run_cmd $SUDO apt install -y policykit-1 || run_cmd $SUDO apt install -y polkitd pkexec || true
  fi
}

ostree_install() {
  local pkgs=(python3 python3-pyqt6 python3-psutil lm_sensors stress git pciutils libdrm vulkan-tools)
  run_cmd $SUDO rpm-ostree install --idempotent "${pkgs[@]}"
  warn "rpm-ostree usually requires a reboot before new layered packages are usable."
}

print_credits() {
  bold "== Third-party credits =="
  echo "BC250 Control Center integrates community tools. These projects remain property of their respective authors."
  echo "Tools are cloned/installed from official upstream repositories or distro packages when requested."
  echo "If your terminal/browser has trouble opening multiple links, use: Information > Official repositories."
  echo "- cyan-skillfish-governor-smu / cyan-skillfish-governor: https://github.com/filippor/cyan-skillfish-governor/tree/smu"
  echo "- bc250_smu_oc by bc250-collective: https://github.com/bc250-collective/bc250_smu_oc"
  echo "- bc250-cu-live-manager by WinnieLV: https://github.com/WinnieLV/bc250-cu-live-manager"
  echo "- bc250-40cu-unlock reference by duggasco: https://github.com/duggasco/bc250-40cu-unlock"
  echo
}

steamos_prepare_pacman() {
  if [ "$is_steamos" != 1 ]; then
    return 0
  fi
  bold "== Preparing SteamOS writable pacman/keyring layer =="
  warn "SteamOS is immutable. The app will unlock the current system layer to install BC250 build dependencies."
  if have steamos-readonly; then
    run_cmd $SUDO steamos-readonly disable || warn "Could not disable SteamOS read-only mode. Continue only if pacman can write."
  fi
  run_cmd $SUDO timedatectl set-ntp true || true
  run_cmd $SUDO pacman-key --init || true
  run_cmd $SUDO pacman-key --populate holo || true
  run_cmd $SUDO pacman-key --populate archlinux || true
  run_cmd $SUDO pacman-key --populate || true
  run_cmd $SUDO pacman -Syy --noconfirm || true
}

steamos_install_base() {
  local pkgs=(python python-pyqt6 python-psutil lm_sensors stress git pciutils libdrm vulkan-tools mesa-utils base-devel fakeroot debugedit rust gcc make pkgconf)
  steamos_prepare_pacman
  bold "== Installing SteamOS base/build dependencies with pacman =="
  run_cmd $SUDO pacman -S --needed --noconfirm "${pkgs[@]}"
}

steamos_install_yay() {
  if have yay; then
    info "yay already exists."
    return 0
  fi
  if have paru; then
    info "paru already exists; yay is not required."
    return 0
  fi
  if ! have makepkg || ! have git; then
    warn "makepkg/git are missing; installing base-devel/git before yay-bin."
    run_cmd $SUDO pacman -S --needed --noconfirm base-devel git fakeroot debugedit
  fi
  bold "== Installing yay-bin for SteamOS AUR packages =="
  local dir="${XDG_CACHE_HOME:-$HOME/.cache}/bc250-control-center/aur/yay-bin"
  mkdir -p "$(dirname "$dir")"
  if [ -d "$dir/.git" ]; then
    git -C "$dir" pull --ff-only || true
  else
    rm -rf "$dir"
    git clone https://aur.archlinux.org/yay-bin.git "$dir"
  fi
  (cd "$dir" && makepkg -si --noconfirm)
}

install_governor_steamos() {
  if have cyan-skillfish-governor-smu; then
    info "cyan-skillfish-governor-smu already exists."
    return 0
  fi
  steamos_install_yay
  if have yay; then
    run_cmd yay -S --needed --noconfirm cyan-skillfish-governor-smu
    return $?
  fi
  if have paru; then
    run_cmd paru -S --needed --noconfirm cyan-skillfish-governor-smu
    return $?
  fi
  warn "SteamOS AUR helper is still missing; falling back to makepkg."
  install_governor_arch
}

install_governor_arch() {
  if have cyan-skillfish-governor-smu; then
    info "cyan-skillfish-governor-smu already exists."
    return 0
  fi
  if have yay; then
    run_cmd yay -S --needed --noconfirm cyan-skillfish-governor-smu
    return $?
  fi
  if have paru; then
    run_cmd paru -S --needed --noconfirm cyan-skillfish-governor-smu
    return $?
  fi
  if have makepkg && have git; then
    local dir="${XDG_DATA_HOME:-$HOME/.local/share}/bc250-control-center/tools/aur-cyan-skillfish-governor-smu"
    mkdir -p "$(dirname "$dir")"
    if [ -d "$dir/.git" ]; then
      git -C "$dir" pull --ff-only || true
    else
      git clone https://aur.archlinux.org/cyan-skillfish-governor-smu.git "$dir"
    fi
    (cd "$dir" && makepkg -si --noconfirm)
    return $?
  fi
  warn "Could not find yay/paru/makepkg to install cyan-skillfish-governor-smu."
  return 0
}

install_governor_fedora() {
  if have cyan-skillfish-governor-smu; then
    info "cyan-skillfish-governor-smu already exists."
    return 0
  fi
  if [ "$is_ostree" = 1 ]; then
    if have dnf; then
      run_cmd $SUDO dnf -y copr enable filippor/bazzite || true
    else
      warn "dnf was not found to enable COPR filippor/bazzite; if the repo is already enabled, rpm-ostree may continue."
    fi
    run_cmd $SUDO rpm-ostree install --idempotent cyan-skillfish-governor-smu
    warn "Reboot Bazzite/Fedora Atomic before enabling the service."
    return 0
  fi
  if have dnf; then
    run_cmd $SUDO dnf -y copr enable filippor/bazzite || true
    run_cmd $SUDO dnf install -y cyan-skillfish-governor-smu
    return $?
  fi
  return 0
}

install_governor_debian() {
  if have cyan-skillfish-governor-smu; then
    info "cyan-skillfish-governor-smu already exists."
    return 0
  fi

  local version="${BC250_GOVERNOR_SMU_VERSION:-0.4.11}"
  local tmpdir
  tmpdir="$(mktemp -d)"
  local deb="cyan-skillfish-governor-smu_${version}-1_amd64.deb"
  local deb_url="https://github.com/filippor/cyan-skillfish-governor/releases/download/v${version}/${deb}"
  local tar="cyan-skillfish-governor-smu-v${version}-x86_64-linux.tar.gz"
  local tar_url="https://github.com/filippor/cyan-skillfish-governor/releases/download/v${version}/${tar}"

  bold "== Preparing Debian/Ubuntu governor from upstream SMU release =="
  warn "Debian Stable is best-effort for BC-250. If kernel/Mesa support is too old, the app may still need a newer kernel stack."
  warn "Debian BC-250 docs may require kernel parameter amdgpu.sg_display=0; this script does not edit bootloader settings automatically."
  if ! have curl; then
    run_cmd $SUDO apt install -y curl ca-certificates || true
  fi

  if have curl && curl -L --fail -o "$tmpdir/$deb" "$deb_url"; then
    info "Installing $deb from filippor/cyan-skillfish-governor SMU release."
    run_cmd $SUDO apt install -y "$tmpdir/$deb" || {
      run_cmd $SUDO dpkg -i "$tmpdir/$deb" || true
      run_cmd $SUDO apt -f install -y || true
    }
  elif have curl && curl -L --fail -o "$tmpdir/$tar" "$tar_url"; then
    warn "Debian .deb download failed; trying upstream tarball installer."
    (cd "$tmpdir" && tar -xf "$tar" && cd "cyan-skillfish-governor-smu-v${version}-x86_64-linux" && run_cmd $SUDO ./scripts/install.sh) || true
  else
    warn "Could not download cyan-skillfish-governor-smu release assets."
    warn "Manual source: https://github.com/filippor/cyan-skillfish-governor/tree/smu"
  fi

  run_cmd $SUDO systemctl daemon-reload || true
  if have cyan-skillfish-governor-smu; then
    info "cyan-skillfish-governor-smu installed. Use the app button to enable/start the service."
  else
    warn "cyan-skillfish-governor-smu is still not available. Check the terminal output above."
  fi
}

container_notice() {
  if [ "$in_container" != 1 ]; then
    return 0
  fi
  warn "A container/Distrobox environment was detected."
  warn "GUI dependencies can be installed here, but governor/UMR/systemctl/rpm-ostree must be installed on the HOST."
  if have distrobox-host-exec; then
    warn "distrobox-host-exec exists. On Bazzite, run on the host:"
    warn "  distrobox-host-exec rpm-ostree install --idempotent stress git pciutils libdrm vulkan-tools"
  fi
}

bold "== BC250 Control Center: system dependencies =="
info "Detected OS: ${os_name:-unknown} (${os_id:-?}) like=${os_like:-?} variant=${variant_id:-?}"
print_credits
container_notice

if [ "$is_steamos" = 1 ] && have pacman; then
  steamos_install_base
  bold "== Preparing SteamOS/AUR governor =="
  install_governor_steamos
elif have pacman; then
  bold "== Installing base dependencies with pacman =="
  pacman_install
  bold "== Preparing Arch/AUR governor =="
  install_governor_arch
elif [ "$is_ostree" = 1 ]; then
  bold "== Installing base dependencies with rpm-ostree =="
  ostree_install
  bold "== Preparing Bazzite/Fedora Atomic governor =="
  install_governor_fedora
elif have dnf; then
  bold "== Installing base dependencies with dnf =="
  dnf_install
  bold "== Preparing Fedora/Nobara governor =="
  install_governor_fedora
elif have apt; then
  bold "== Installing base dependencies with apt =="
  apt_install
  install_governor_debian
else
  err "No supported package manager found: pacman, dnf, rpm-ostree or apt."
  exit 1
fi

bold "== Quick verification =="
for cmd in python3 python stress git lspci sensors; do
  if have "$cmd"; then
    printf 'OK: %s -> %s\n' "$cmd" "$(command -v "$cmd")"
  else
    printf 'MISSING: %s\n' "$cmd"
  fi
done

if have cyan-skillfish-governor-smu; then
  printf 'OK: cyan-skillfish-governor-smu -> %s\n' "$(command -v cyan-skillfish-governor-smu)"
else
  warn "cyan-skillfish-governor-smu is still not in PATH. Bazzite/rpm-ostree may require reboot; Debian/Ubuntu may need manual review if the upstream .deb failed."
fi

bold "== System dependency phase finished =="
