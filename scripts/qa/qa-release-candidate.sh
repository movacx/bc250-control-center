#!/usr/bin/env bash
# Read-only release-candidate verification.  It never installs packages,
# contacts hardware, or turns an evidence gate into a public-release claim.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
PYTHON_BIN="${BC250_QA_PYTHON:-python3}"
DECKY_DIR="$PROJECT_ROOT/integrations/decky/bc250-quick-access"
REPORT_FILE="$(mktemp "${TMPDIR:-/tmp}/bc250-release-gates.XXXXXX.json")"

cleanup() {
    rm -f -- "$REPORT_FILE"
}
trap cleanup EXIT

require() {
    command -v "$1" >/dev/null 2>&1 || {
        printf 'ERROR: required command is unavailable: %s\n' "$1" >&2
        exit 2
    }
}

require "$PYTHON_BIN"
require npm
"$PYTHON_BIN" -c 'import bandit, pytest, pytestqt, ruff' >/dev/null 2>&1 || {
    printf '%s\n' 'ERROR: pytest, pytest-qt, Ruff and Bandit are required (install requirements-dev.txt).' >&2
    exit 2
}

printf '%s\n' '== BC250 release-candidate: Python lint and security gate =='
(
    cd "$PROJECT_ROOT"
    "$PYTHON_BIN" -m ruff check src frontends privileged scripts tests
    # B608 is an SQL-string heuristic; this project intentionally builds one
    # fixed CachyOS shell workflow and contains no SQL at that location.
    "$PYTHON_BIN" -m bandit -q -r src frontends privileged scripts -x '*/__pycache__/*' -ll -s B608
)

printf '%s\n' '== BC250 release-candidate: full Python regression =='
(
    cd "$PROJECT_ROOT"
    QT_QPA_PLATFORM=offscreen "$PYTHON_BIN" -m pytest -q -o addopts=''
)

printf '%s\n' '== BC250 release-candidate: install-source validation =='
(
    cd "$PROJECT_ROOT"
    bash scripts/qa/validate-install-source.sh .
)

printf '%s\n' '== BC250 release-candidate: Decky TypeScript and bundle =='
(
    cd "$DECKY_DIR"
    npx tsc --noEmit
    npm run build
)

printf '%s\n' '== BC250 release-candidate: desktop scale matrix =='
(
    cd "$PROJECT_ROOT"
    BC250_QA_PYTHON="$PYTHON_BIN" bash scripts/qa/qa-ui-scale-matrix.sh
)

printf '%s\n' '== BC250 release-candidate: release gate contract =='
(
    cd "$PROJECT_ROOT"
    PYTHONPATH="$PROJECT_ROOT/src:$PROJECT_ROOT" "$PYTHON_BIN" -m frontends.cli --json release-gates > "$REPORT_FILE"
)
"$PYTHON_BIN" - "$REPORT_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    report = json.load(stream)

assert report["schema"] == 2
assert report["static_contracts_ready"] is True
assert report["public_release_ready"] is False
assert report["qualification_evidence_can_self_certify"] is False
assert not report["manifest_issues"]
print("OK: static contracts are ready; physical qualification remains mandatory.")
PY

printf '%s\n' 'OK: release-candidate static verification completed. No hardware action was executed.'
