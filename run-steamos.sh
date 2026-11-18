#!/usr/bin/env bash
# Open the real desktop shell with SteamOS menus and Game Mode layout.
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$PROJECT_ROOT/src:$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec python3 "$PROJECT_ROOT/scripts/development/preview-steamos.py" "$@"
