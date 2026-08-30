#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
PYTHON_BIN="${BC250_QA_PYTHON:-python3}"

if ! "$PYTHON_BIN" -c 'import pytest, pytestqt' >/dev/null 2>&1; then
    printf '%s\n' "ERROR: pytest and pytest-qt are required (install requirements-dev.txt)." >&2
    exit 2
fi

for scale in 1.0 1.25 1.5 2.0; do
    printf '== BC250 UI scale matrix: %s ==\n' "$scale"
    QT_QPA_PLATFORM=offscreen \
    QT_SCALE_FACTOR="$scale" \
    PYTHONPATH="$PROJECT_ROOT" \
        "$PYTHON_BIN" -m pytest \
        -q -o addopts='' \
        "$PROJECT_ROOT/tests/desktop/dashboard/test_control_page_responsive_matrix.py"
done

printf '%s\n' "OK: multilingual UI layout passed at every audited scale."
