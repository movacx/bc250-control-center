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

install -dm755 "$APP_DIR" "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR" "$METAINFO_DIR" "$SYSTEMD_USER_DIR" "$DOC_DIR"
rm -rf "$APP_DIR/mvc"
cp -a "$ROOT_DIR/mvc" "$APP_DIR/"
install -Dm644 "$ROOT_DIR/README.md" "$DOC_DIR/README.md"
install -Dm644 "$ROOT_DIR/LICENSE" "$DOC_DIR/LICENSE"
install -Dm755 "$ROOT_DIR/scripts/bc250-control-center" "$BIN_DIR/bc250-control-center"
install -Dm755 "$ROOT_DIR/scripts/bc250-control-centerd" "$BIN_DIR/bc250-control-centerd"
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

echo "Installed in $PREFIX"
echo "GUI: $BIN_DIR/bc250-control-center"
echo "Optional daemon: systemctl --user enable --now bc250-control-centerd.service"
echo "If the daemon was just installed, run: systemctl --user daemon-reload"
echo "Uninstall: PREFIX=\"$PREFIX\" $APP_DIR/scripts/uninstall-local.sh"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "Note: $BIN_DIR is not in PATH. Use the full GUI command above or add it to your shell PATH." ;;
esac
