#!/usr/bin/env bash
# Rebuilds frontends/web/dist from the React sources in frontends/web/app.
# Only developers need Node; the built dist/ is committed, so installs and packages never do.
set -euo pipefail
cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../frontends/web/app"
[[ -d node_modules ]] || npm ci --no-audit --no-fund
npm run build
