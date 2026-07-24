#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

if [[ -z "${PREFIX:-}" ]]; then
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    PREFIX="/usr/local"
  else
    PREFIX="$HOME/.local"
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
SYSTEM_POLKIT_ACTION="/usr/share/polkit-1/actions/io.github.fabianbeita.bc250-control-center.policy"

is_steamos_install_local() {
  local text=""
  if [[ -r /etc/os-release ]]; then
    text="$(cat /etc/os-release)"
  elif [[ -r /usr/lib/os-release ]]; then
    text="$(cat /usr/lib/os-release)"
  fi
  printf '%s' "$text" | tr '[:upper:]' '[:lower:]' | grep -Eq 'steamos|steamdeck|holo'
}

prepare_steamos_pacman_install_local() {
  if ! is_steamos_install_local || ! command -v pacman >/dev/null 2>&1; then
    return 0
  fi
  echo "SteamOS detected: preparing writable pacman/keyring layer for GUI dependencies..."
  if command -v steamos-readonly >/dev/null 2>&1; then
    sudo steamos-readonly disable || true
  fi
  sudo timedatectl set-ntp true || true
  sudo pacman-key --init || true
  sudo pacman-key --populate holo || true
  sudo pacman-key --populate archlinux || true
  sudo pacman-key --populate || true
  sudo rm -f /var/cache/pacman/pkg/python-pyqt6-*.pkg.tar.zst /var/cache/pacman/pkg/python-pyqt6-sip-*.pkg.tar.zst 2>/dev/null || true
  sudo pacman -Syy --noconfirm || true
}

if [[ "${EUID:-$(id -u)}" -ne 0 && "$PREFIX" == "$HOME/.local" ]]; then
  SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
fi

if [[ ! -d "$ROOT_DIR/mvc" || ! -d "$ROOT_DIR/scripts" || ! -d "$ROOT_DIR/packaging" ]]; then
  echo "Error: no se encontro la raiz del proyecto BC250 Control Center." >&2
  echo "Script: $SCRIPT_PATH" >&2
  echo "Raiz detectada: $ROOT_DIR" >&2
  echo "Ejecuta el instalador desde el repo/tarball original o revisa que existan mvc/, scripts/ y packaging/." >&2
  exit 1
fi

missing_python_deps=0
missing_python_deps_command=""
missing_python_deps_reboot_notice=0
if ! command -v python3 >/dev/null 2>&1; then
  echo "Warning: python3 is not installed or is not in PATH." >&2
  missing_python_deps=1
elif ! python3 - <<'PY' >/dev/null 2>&1
from PyQt6.QtWidgets import QApplication
import psutil
PY
then
  echo "Warning: Python GUI dependencies are missing. The app will install, but it will not open until they are installed." >&2
  if [[ -e /run/ostree-booted ]] && command -v rpm-ostree >/dev/null 2>&1; then
    missing_python_deps_command="rpm-ostree install --idempotent python3-pyqt6 python3-psutil"
    missing_python_deps_reboot_notice=1
    echo "Bazzite/Fedora Atomic: sudo $missing_python_deps_command" >&2
  elif command -v dnf >/dev/null 2>&1; then
    missing_python_deps_command="dnf install -y python3-pyqt6 python3-psutil"
    echo "Fedora/Nobara: sudo $missing_python_deps_command" >&2
  elif command -v pacman >/dev/null 2>&1; then
    missing_python_deps_command="pacman -S --needed python-pyqt6 python-psutil"
    echo "Arch/CachyOS: sudo $missing_python_deps_command" >&2
  elif command -v apt >/dev/null 2>&1; then
    missing_python_deps_command="apt install -y python3 python-is-python3 python3-pyqt6 python3-psutil"
    echo "Debian/Ubuntu: sudo $missing_python_deps_command" >&2
  fi
  missing_python_deps=1
fi

if [[ -n "$missing_python_deps_command" ]]; then
  prepare_steamos_pacman_install_local
  echo "Installing missing Python GUI dependencies..."
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    $missing_python_deps_command
  elif command -v sudo >/dev/null 2>&1; then
    sudo $missing_python_deps_command
  else
    echo "Warning: sudo is not available. Install manually: $missing_python_deps_command" >&2
  fi
fi

install -dm755 "$APP_DIR" "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR" "$METAINFO_DIR" "$SYSTEMD_USER_DIR" "$DOC_DIR"
rm -rf "$APP_DIR/mvc"
cp -a "$ROOT_DIR/mvc" "$APP_DIR/"
install -Dm644 "$ROOT_DIR/README.md" "$DOC_DIR/README.md"
install -Dm644 "$ROOT_DIR/LICENSE" "$DOC_DIR/LICENSE"
install -Dm755 "$ROOT_DIR/scripts/bc250-control-center" "$BIN_DIR/bc250-control-center"
install -Dm755 "$ROOT_DIR/scripts/bc250-control-centerd" "$BIN_DIR/bc250-control-centerd"
install_privileged_pwm_components() {
  local helper_source="$ROOT_DIR/mvc/Resources/privileged/bc250-fan-pwm-helper"
  local policy_source="$ROOT_DIR/packaging/common/polkit/io.github.fabianbeita.bc250-control-center.policy"
  local -a elevate=()

  if [[ "${BC250_SKIP_PRIVILEGED_HELPER:-0}" == "1" ]]; then
    echo "Skipping privileged PWM helper because BC250_SKIP_PRIVILEGED_HELPER=1."
    return 0
  fi

  if [[ -e /run/ostree-booted ]]; then
    echo "Warning: immutable rpm-ostree system detected; install the RPM with rpm-ostree for the hardened PWM helper." >&2
    return 0
  fi

  if is_steamos_install_local; then
    prepare_steamos_pacman_install_local
  fi

  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    if ! command -v sudo >/dev/null 2>&1; then
      echo "Warning: sudo is unavailable; the hardened PWM helper and Polkit action were not installed." >&2
      return 0
    fi
    elevate=(sudo)
  fi

  echo "Installing root-owned PWM helper and Polkit action..."
  "${elevate[@]}" install -Dm755 "$helper_source" "$SYSTEM_PRIV_HELPER"
  "${elevate[@]}" install -Dm644 "$policy_source" "$SYSTEM_POLKIT_ACTION"
}

install_privileged_pwm_components
install -Dm755 "$ROOT_DIR/scripts/uninstall-local.sh" "$APP_DIR/scripts/uninstall-local.sh"
rm -f "$ICON_DIR/scalable/apps/bc250-control-center.svg"
for size in 32 48 64 128 256 512 1024; do
  install -Dm644 "$ROOT_DIR/mvc/Resources/icons/bc250-control-center-${size}.png" "$ICON_DIR/${size}x${size}/apps/bc250-control-center.png"
done
desktop_file="$DESKTOP_DIR/io.github.fabianbeita.bc250-control-center.desktop"
install -Dm644 "$ROOT_DIR/packaging/common/desktop/io.github.fabianbeita.bc250-control-center.desktop" "$desktop_file"
sed -i "s|^Exec=.*|Exec=$BIN_DIR/bc250-control-center|" "$desktop_file"
install -Dm644 "$ROOT_DIR/packaging/common/metainfo/io.github.fabianbeita.bc250-control-center.metainfo.xml" "$METAINFO_DIR/io.github.fabianbeita.bc250-control-center.metainfo.xml"
install -Dm644 "$ROOT_DIR/packaging/common/systemd-user/bc250-control-centerd.service" "$SYSTEMD_USER_DIR/bc250-control-centerd.service"
sed -i "s|^ExecStart=.*|ExecStart=$BIN_DIR/bc250-control-centerd|" "$SYSTEMD_USER_DIR/bc250-control-centerd.service"
if [[ "$SYSTEMD_USER_DIR" != "$PREFIX/lib/systemd/user" ]]; then
  rm -f "$PREFIX/lib/systemd/user/bc250-control-centerd.service"
fi
if [[ "${EUID:-$(id -u)}" -ne 0 ]] && command -v systemctl >/dev/null 2>&1; then
  systemctl --user daemon-reload >/dev/null 2>&1 || true
fi

echo "Installed in $PREFIX"
echo "GUI: $BIN_DIR/bc250-control-center"
echo "Optional daemon: systemctl --user enable --now bc250-control-centerd.service"
if [[ -x "$SYSTEM_PRIV_HELPER" ]]; then
  echo "PWM helper: $SYSTEM_PRIV_HELPER"
else
  echo "PWM helper: not installed; use a native package or rerun with sudo access for hardened PWM control."
fi
echo "Daemon reload: attempted automatically when possible"
echo "If systemd still does not find the daemon, run: systemctl --user daemon-reload"
echo "Uninstall: PREFIX=\"$PREFIX\" $APP_DIR/scripts/uninstall-local.sh"
if [[ "$missing_python_deps" -eq 1 ]]; then
  echo "Important: install the Python GUI dependencies above before opening the app."
  if [[ "$missing_python_deps_reboot_notice" -eq 1 ]]; then
    echo "Bazzite/Fedora Atomic note: reboot after rpm-ostree installs new packages, then open the app again."
  fi
fi
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "Note: $BIN_DIR is not in PATH. Use the full GUI command above or add it to your shell PATH." ;;
esac
