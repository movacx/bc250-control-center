#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
if [[ -z "${PREFIX:-}" ]]; then
  if [[ "$SCRIPT_PATH" == */share/bc250-control-center/scripts/uninstall-local.sh ]]; then
    PREFIX="${SCRIPT_PATH%/share/bc250-control-center/scripts/uninstall-local.sh}"
  else
    PREFIX="/usr/local"
  fi
fi

APP_DIR="$PREFIX/share/bc250-control-center"
BIN_DIR="$PREFIX/bin"
DESKTOP_DIR="$PREFIX/share/applications"
ICON_DIR="$PREFIX/share/icons/hicolor"
METAINFO_DIR="$PREFIX/share/metainfo"
SYSTEMD_USER_DIR="$PREFIX/lib/systemd/user"
DOC_DIR="$PREFIX/share/doc/bc250-control-center"

YES=0
DRY_RUN=0
PURGE_USER_DATA=0

usage() {
  cat <<USAGE
BC250 Control Center local uninstaller

Usage:
  PREFIX="\$HOME/.local" ./scripts/uninstall-local.sh [options]
  sudo ./scripts/uninstall-local.sh [options]

Options:
  -y, --yes             Do not ask for confirmation.
  --dry-run             Show what would be removed, but do not delete anything.
  --purge-user-data     Also remove ~/.config and ~/.local/share data created by the app.
  -h, --help            Show this help.

This removes only files installed by scripts/install-local.sh.
It does not uninstall system dependencies, AUR/RPM packages, cyan-skillfish-governor,
UMR, or persistent CPU OC services created manually from inside the app.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -y|--yes) YES=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --purge-user-data) PURGE_USER_DATA=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

remove_path() {
  local path="$1"
  if [[ -e "$path" || -L "$path" ]]; then
    echo "Removing: $path"
    if [[ "$DRY_RUN" -eq 0 ]]; then
      rm -rf -- "$path"
    fi
  fi
}

remove_empty_dir() {
  local path="$1"
  if [[ -d "$path" ]]; then
    if [[ "$DRY_RUN" -eq 0 ]]; then
      rmdir --ignore-fail-on-non-empty "$path" 2>/dev/null || true
    else
      echo "Would remove empty dir if unused: $path"
    fi
  fi
}

try_disable_user_daemon() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "Would try: systemctl --user disable --now bc250-control-centerd.service"
    return 0
  fi
  if [[ "${EUID:-$(id -u)}" -ne 0 ]] && command -v systemctl >/dev/null 2>&1; then
    systemctl --user disable --now bc250-control-centerd.service >/dev/null 2>&1 || true
    systemctl --user daemon-reload >/dev/null 2>&1 || true
  fi
}

cat <<INFO
== BC250 Control Center local uninstall ==
Prefix: $PREFIX

Files installed by install-local.sh will be removed from:
- $APP_DIR
- $BIN_DIR/bc250-control-center
- $BIN_DIR/bc250-control-centerd
- $DESKTOP_DIR/io.github.fabianbeita.bc250-control-center.desktop
- $METAINFO_DIR/io.github.fabianbeita.bc250-control-center.metainfo.xml
- $SYSTEMD_USER_DIR/bc250-control-centerd.service
- $ICON_DIR/*/apps/bc250-control-center.png
- $DOC_DIR
INFO

if [[ "$PURGE_USER_DATA" -eq 1 ]]; then
  cat <<INFO

User data purge enabled. It will also remove:
- $HOME/.config/bc250-control-center
- $HOME/.local/share/bc250-control-center
INFO
fi

if [[ "$YES" -ne 1 ]]; then
  read -r -p "Continue? Type YES to uninstall: " confirm
  if [[ "$confirm" != "YES" ]]; then
    echo "Cancelled."
    exit 0
  fi
fi

try_disable_user_daemon

remove_path "$BIN_DIR/bc250-control-center"
remove_path "$BIN_DIR/bc250-control-centerd"
remove_path "$DESKTOP_DIR/io.github.fabianbeita.bc250-control-center.desktop"
remove_path "$METAINFO_DIR/io.github.fabianbeita.bc250-control-center.metainfo.xml"
remove_path "$SYSTEMD_USER_DIR/bc250-control-centerd.service"
remove_path "$DOC_DIR"
remove_path "$APP_DIR"

for size in 32 48 64 128 256 512 1024; do
  remove_path "$ICON_DIR/${size}x${size}/apps/bc250-control-center.png"
  remove_empty_dir "$ICON_DIR/${size}x${size}/apps"
  remove_empty_dir "$ICON_DIR/${size}x${size}"
done
remove_path "$ICON_DIR/scalable/apps/bc250-control-center.svg"
remove_empty_dir "$ICON_DIR/scalable/apps"
remove_empty_dir "$ICON_DIR/scalable"

if [[ "$PURGE_USER_DATA" -eq 1 ]]; then
  remove_path "$HOME/.config/bc250-control-center"
  remove_path "$HOME/.local/share/bc250-control-center"
fi

if [[ "$DRY_RUN" -eq 0 ]]; then
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
  fi
  if command -v gtk-update-icon-cache >/dev/null 2>&1 && [[ -d "$ICON_DIR" ]]; then
    gtk-update-icon-cache -q -t "$ICON_DIR" >/dev/null 2>&1 || true
  fi
fi

cat <<INFO

Uninstall complete.

If you enabled the optional daemon from another user session, you can also run:
  systemctl --user disable --now bc250-control-centerd.service

If you enabled persistent CPU OC from inside the app, that is separate from install-local.sh.
Disable it from the app or run:
  sudo systemctl disable --now bc250-smu-oc.service
INFO
