#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
else
    echo "BC250 Control Center requires Python 3, but no Python interpreter was found." >&2
    exit 127
fi

# Say what is missing, and how to get it.
#
# This used to exec straight into Python, so a host without PyQt6 met a raw
# ImportError naming a module rather than a package — and had to work out for
# itself that Bazzite spells it "python3-pyqt6" and installs it through
# rpm-ostree. install-local.sh has always known those commands; this is the
# same knowledge at the one other place the application is started from.
if ! "$PYTHON_BIN" - <<'DEPENDENCY_PROBE' >/dev/null 2>&1
from PyQt6.QtGui import QImageReader
from PyQt6.QtWidgets import QApplication  # noqa: F401
import psutil  # noqa: F401

formats = {bytes(fmt).decode("ascii", "ignore").lower() for fmt in QImageReader.supportedImageFormats()}
assert "svg" in formats, "Qt SVG image plugin is missing"
DEPENDENCY_PROBE
then
    echo "BC250 Control Center needs PyQt6, its Qt SVG plugin and psutil." >&2
    if [[ -e /run/ostree-booted ]] && command -v rpm-ostree >/dev/null 2>&1; then
        echo "Install them with:" >&2
        echo "  sudo rpm-ostree install --idempotent python3-pyqt6 qt6-qtsvg python3-psutil" >&2
        echo "Then reboot: an image-based system applies this on the next boot." >&2
    elif command -v dnf >/dev/null 2>&1; then
        echo "Install them with:" >&2
        echo "  sudo dnf install -y python3-pyqt6 qt6-qtsvg python3-psutil" >&2
    elif command -v apt-get >/dev/null 2>&1; then
        echo "Install them with:" >&2
        echo "  sudo apt-get install -y python3-pyqt6 libqt6svg6 python3-psutil" >&2
    elif command -v pacman >/dev/null 2>&1; then
        echo "Install them with:" >&2
        echo "  sudo pacman -S --needed python-pyqt6 qt6-svg python-psutil" >&2
    elif command -v apk >/dev/null 2>&1; then
        echo "Install them with:" >&2
        echo "  sudo apk add py3-qt6 qt6-qtsvg py3-psutil" >&2
    elif command -v emerge >/dev/null 2>&1; then
        echo "Install them with:" >&2
        echo "  sudo emerge dev-python/PyQt6 dev-python/psutil" >&2
    else
        echo "Install the PyQt6, Qt SVG and psutil packages for your distribution." >&2
    fi
    exit 127
fi

exec "$PYTHON_BIN" -m frontends.desktop.main "$@"