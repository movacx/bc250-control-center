#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=steamos-root.sh
source "$SCRIPT_DIR/steamos-root.sh"

[[ $# -gt 0 ]] || { echo "usage: $0 COMMAND [ARG ...]" >&2; exit 64; }

cleanup() {
  local status=$?
  trap - EXIT
  if bc250_steamos_restore_root "$status"; then
    exit 0
  else
    exit $?
  fi
}
trap cleanup EXIT

bc250_steamos_unlock_root
"$@"
