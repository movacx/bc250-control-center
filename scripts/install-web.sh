#!/usr/bin/env bash
if LC_ALL=C grep -q "$(printf '\r')" "$0"; then echo "Error: CRLF checkout detected. Convert shell scripts to LF and rerun with bash." >&2; exit 65; fi # POSIX bootstrap.
# Install only the web interface: the same application tree, launchers and
# protected helpers as install-tui.sh, without PyQt6, polkit or a desktop, and
# leave it running for the home network. A phone or another computer is enough
# to use it; the board needs no screen.
if [ -z "${BASH_VERSION:-}" ]; then
  command -v bash >/dev/null 2>&1 || { echo "Error: install bash, then run: bash $0" >&2; exit 69; }
  exec bash "$0" "$@"
fi
set -euo pipefail
ROOT_DIR="$(dirname "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")")"
START=1
MODE=install
case "${1:-}" in
  -h|--help)
    cat <<'HELP'
Usage: bash scripts/install-web.sh [--check | --no-start | --uninstall [options] | --help]

Installs or updates the web interface; safe to run again.
It needs Python 3.11+ with psutil, and offers to install what is missing with
your distribution's package manager. The web server itself is prepared in a
private environment of your user; nothing is installed with the system's pip,
and neither Qt, polkit nor a display is needed.

  --check, --dry-run   say what is missing and what would be done, change nothing
  --no-start           install without starting web access
  --uninstall          remove it (the uninstaller's options follow)

Afterwards:
  bc250-control-center web setup    start it and show the address, key and QR
  bc250-control-center web status   show them again
  bc250-control-center web stop     stop it

PREFIX selects the destination (default: ~/.local, or /usr/local for root).
HELP
    exit 0 ;;
  --uninstall)
    exec bash "$ROOT_DIR/scripts/uninstall-local.sh" "${@:2}" ;;
  --dry-run|--check) MODE=check ;;
  --no-start) START=0 ;;
  "") ;;
  *) echo "Usage: $0 [--help | --check | --no-start | --uninstall [options]]" >&2; exit 64 ;;
esac
[[ $# -le 1 ]] || { echo "Error: unexpected arguments." >&2; exit 64; }
if [[ ! -s "$ROOT_DIR/frontends/web/dist/webApp.js" ]]; then
  echo "Error: this copy has no built web interface. Use a release, or run scripts/development/build-web.sh first." >&2
  exit 2
fi
if [[ "$MODE" == check ]]; then
  exec bash "$ROOT_DIR/scripts/install-tui.sh" --check
fi
bash "$ROOT_DIR/scripts/install-tui.sh"
if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
  echo "Web access runs as your ordinary user. As that user: bc250-control-center web setup"
  exit 0
fi
PREFIX="${PREFIX:-$HOME/.local}"
if [[ "$START" == 1 ]]; then
  exec "$PREFIX/bin/bc250-control-center" web setup
fi
echo "Web interface: $PREFIX/bin/bc250-control-center web setup"
