#!/usr/bin/env bash
if LC_ALL=C grep -q "$(printf '\r')" "$0"; then echo "Error: CRLF checkout detected. Convert shell scripts to LF and rerun with bash." >&2; exit 65; fi # POSIX bootstrap.
# Install only the terminal interface: the same application tree, launchers
# and protected helpers as install-local.sh, without PyQt6, polkit, a desktop
# entry or icons. Without root it installs to ~/.local, which is also what
# keeps it working on Bazzite and SteamOS, whose / is read-only.
if [ -z "${BASH_VERSION:-}" ]; then
  command -v bash >/dev/null 2>&1 || { echo "Error: install bash, then run: bash $0" >&2; exit 69; }
  exec bash "$0" "$@"
fi
set -euo pipefail
ROOT_DIR="$(dirname "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")")"
if LC_ALL=C grep -q "$(printf '\r')" "$ROOT_DIR/scripts/install-local.sh"; then
  echo "Error: CRLF checkout detected. Convert shell scripts to LF and rerun with bash." >&2
  exit 65
fi
case "${1:-}" in
  -h|--help)
    cat <<'HELP'
Usage: bash scripts/install-tui.sh [--check | --uninstall [options] | --help]

Installs or updates the terminal interface; safe to run again.
It needs Python 3.11+ with curses and psutil, and offers to install what is
missing with your distribution's package manager. Nothing is installed with
pip, and neither Qt, polkit nor a display is needed.

  --check, --dry-run   say what is missing and what would be done, change nothing
  --uninstall          remove it (the uninstaller's options follow)

PREFIX selects the destination (default: ~/.local, or /usr/local for root).
On Batocera use PREFIX=/userdata/system/.local, which survives a reboot.
Exit codes: 0 done, 2 something is missing, 6 the files belong to a package,
64 wrong usage, 65 Windows line endings, 69 no bash.
HELP
    exit 0 ;;
  --uninstall)
    exec bash "$ROOT_DIR/scripts/uninstall-local.sh" "${@:2}" ;;
  --dry-run|--check)
    [[ $# -eq 1 ]] || { echo "Error: unexpected arguments." >&2; exit 64; }
    export BC250_TUI_CHECK=1 ;;
  "") ;;
  *) echo "Usage: $0 [--help | --dry-run | --check | --uninstall [options]]" >&2; exit 64 ;;
esac
BC250_INSTALL_PROFILE=tui exec bash "$ROOT_DIR/scripts/install-local.sh"
