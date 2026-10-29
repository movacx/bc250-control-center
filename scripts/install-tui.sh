#!/usr/bin/env bash
# Install only the terminal interface: the same application tree, launchers
# and privileged helpers as install-local.sh, without PyQt6, a desktop entry or
# icons. Without root it installs to ~/.local, which is also what keeps it
# working on Bazzite and SteamOS, whose / is read-only.
#
#   scripts/install-tui.sh               install or update (safe to run again)
#   scripts/install-tui.sh --uninstall   remove it (the uninstaller's options follow)
set -euo pipefail
ROOT_DIR="$(dirname "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")")"
if [[ "${1:-}" == "--uninstall" ]]; then
  exec bash "$ROOT_DIR/scripts/uninstall-local.sh" "${@:2}"
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--uninstall [uninstaller options]]" >&2
  exit 64
fi
BC250_INSTALL_PROFILE=tui exec bash "$ROOT_DIR/scripts/install-local.sh"
