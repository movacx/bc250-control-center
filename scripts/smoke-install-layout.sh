#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_PATH")")"
SMOKE_ROOT="$(mktemp -d /tmp/bc250-install-layout.XXXXXX)"
SMOKE_PREFIX="$SMOKE_ROOT/prefix"

cleanup() {
  case "$SMOKE_ROOT" in
    /tmp/bc250-install-layout.*) rm -rf -- "$SMOKE_ROOT" ;;
    *) echo "ERROR: refusing to clean unexpected smoke root: $SMOKE_ROOT" >&2 ;;
  esac
}
trap cleanup EXIT

echo "== BC250 isolated installation-layout smoke test =="
PREFIX="$SMOKE_PREFIX" BC250_SKIP_PRIVILEGED_HELPER=1 BC250_SKIP_DEPENDENCY_INSTALL=1 \
  bash "$PROJECT_ROOT/scripts/install-local.sh"

required=(
  bin/bc250-control-center
  bin/bc250-control-center-cli
  bin/bc250-control-centerd
  share/bc250-control-center/frontends/desktop/main.py
  share/bc250-control-center/frontends/cli.py
  share/bc250-control-center/src/bc250cc/__init__.py
  share/bc250-control-center/frontends/desktop/features/gpu/presenter.py
  share/bc250-control-center/frontends/quick_access/backend/mapper.py
  share/bc250-control-center/privileged/helpers/README.md
  share/bc250-control-center/VERSION
  share/bc250-control-center/scripts/uninstall-local.sh
  share/bc250-control-center/scripts/update-local.sh
  share/bc250-control-center/scripts/install-decky-quick-access.sh
  share/bc250-control-center/integrations/decky/bc250-quick-access/plugin.json
  share/bc250-control-center/integrations/decky/bc250-quick-access/package.json
  share/bc250-control-center/integrations/decky/bc250-quick-access/main.py
  share/bc250-control-center/integrations/decky/bc250-quick-access/dist/index.js
  share/bc250-control-center/integrations/decky/bc250-quick-access/bc250cc/domain/gpu/profiles.py
  share/applications/io.github.movacx.bc250-control-center.desktop
  share/metainfo/io.github.movacx.bc250-control-center.metainfo.xml
  lib/systemd/user/bc250-control-centerd.service
  share/doc/bc250-control-center/README.md
)
for relative in "${required[@]}"; do
  [[ -f "$SMOKE_PREFIX/$relative" ]] || {
    echo "ERROR: isolated install is missing $relative" >&2
    exit 20
  }
done
if [[ -e "$SMOKE_PREFIX/share/bc250-control-center/integrations/decky/bc250-quick-access/node_modules" ]]; then
  echo "ERROR: isolated install copied Decky development dependencies" >&2
  exit 24
fi
for size in 32 48 64 128 256 512 1024; do
  [[ -f "$SMOKE_PREFIX/share/icons/hicolor/${size}x${size}/apps/bc250-control-center.png" ]] || {
    echo "ERROR: isolated install is missing ${size}x${size} icon" >&2
    exit 21
  }
done

expected_version="$(tr -d '[:space:]' < "$PROJECT_ROOT/VERSION")"
installed_version="$(tr -d '[:space:]' < "$SMOKE_PREFIX/share/bc250-control-center/VERSION")"
[[ "$installed_version" == "$expected_version" ]] || {
  echo "ERROR: installed VERSION does not match source VERSION" >&2
  exit 23
}
"$SMOKE_PREFIX/bin/bc250-control-center-cli" --version | grep -F "$expected_version" >/dev/null

grep -Fqx "Exec=$SMOKE_PREFIX/bin/bc250-control-center" \
  "$SMOKE_PREFIX/share/applications/io.github.movacx.bc250-control-center.desktop"
grep -Fqx "ExecStart=$SMOKE_PREFIX/bin/bc250-control-centerd" \
  "$SMOKE_PREFIX/lib/systemd/user/bc250-control-centerd.service"

cli_json="$($SMOKE_PREFIX/bin/bc250-control-center-cli --json system)"
python3 - "$cli_json" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
required = {"distro_id", "family", "pretty_name", "immutable"}
missing = sorted(required - set(payload))
if missing:
    raise SystemExit(f"installed CLI system report is incomplete: {', '.join(missing)}")
PY

PREFIX="$SMOKE_PREFIX" bash \
  "$SMOKE_PREFIX/share/bc250-control-center/scripts/uninstall-local.sh" \
  --yes --keep-privileged

leftover="$(find "$SMOKE_PREFIX" -type f -print -quit 2>/dev/null || true)"
if [[ -n "$leftover" ]]; then
  echo "ERROR: isolated uninstall left a managed file: $leftover" >&2
  exit 22
fi

echo "OK: isolated install, installed CLI execution and uninstall layout passed."
