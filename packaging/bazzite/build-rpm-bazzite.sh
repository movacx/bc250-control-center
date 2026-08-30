#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
RELEASE_SOURCE_EXCLUDES=(--exclude 'archive' --exclude 'tests')
: "${RELEASE_SOURCE_EXCLUDES[*]}"

# Bazzite consumes the same noarch RPM payload as Fedora. The Bazzite image
# carries the beta tester package from the previous local build, so this wrapper
# uses release -6 by default. The generic Fedora builder remains at its
# normal release -1; callers may still override this explicitly.
export BC250_RPM_RELEASE="${BC250_RPM_RELEASE:-6}"
exec "$ROOT_DIR/packaging/scripts/build-rpm.sh" "${1:-$ROOT_DIR/dist/bazzite}"
