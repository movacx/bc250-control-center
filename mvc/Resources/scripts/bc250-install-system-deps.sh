#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m mvc.Repository.Os_repository.cli "$@"
