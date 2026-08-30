#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
export PYTHONPATH="$APP_ROOT/src:$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m bc250cc.platform.packages.strategies.cli "$@"
