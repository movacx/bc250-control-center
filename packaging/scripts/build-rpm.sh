#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="${VERSION:-0.1.0}"
NAME="bc250-control-center"
TOPDIR="$ROOT/build/rpm"
SRC_DIR="$TOPDIR/${NAME}-${VERSION}"
OUT_DIR="$ROOT/packaging/rpm/out"
PACKAGE_DIR="$ROOT/packaging/packages/fedora"

if ! command -v rpmbuild >/dev/null 2>&1; then
  echo "ERROR: falta rpmbuild." >&2
  echo "Fedora/Bazzite: instala rpm-build con:" >&2
  echo "  sudo dnf install rpm-build" >&2
  echo "  # o en Bazzite: sudo rpm-ostree install rpm-build && systemctl reboot" >&2
  exit 1
fi

rm -rf "$TOPDIR"
mkdir -p "$SRC_DIR" "$TOPDIR/SOURCES" "$TOPDIR/SPECS" "$TOPDIR/BUILD" "$TOPDIR/RPMS" "$TOPDIR/SRPMS" "$TOPDIR/rpmdb" "$OUT_DIR" "$PACKAGE_DIR"

rsync -a \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude 'build' \
  --exclude '*.pkg.tar.*' \
  --exclude '*.rpm' \
  --exclude 'packaging/arch/local/src' \
  --exclude 'packaging/arch/local/pkg' \
  --exclude 'packaging/local/src' \
  --exclude 'packaging/local/pkg' \
  --exclude 'packaging/tar-local/out' \
  --exclude 'packaging/rpm/out' \
  --exclude 'packaging/packages/arch' \
  --exclude 'packaging/packages/fedora' \
  --exclude 'packaging/packages/bazzite' \
  --exclude 'packaging/arch/local/*.pkg.tar.*' \
  --exclude 'packaging/arch/local/*.tar.gz' \
  "$ROOT/" "$SRC_DIR/"

tar -C "$TOPDIR" -czf "$TOPDIR/SOURCES/${NAME}-${VERSION}.tar.gz" "${NAME}-${VERSION}"
cp "$ROOT/packaging/rpm/${NAME}.spec" "$TOPDIR/SPECS/"

rpmbuild \
  --define "_topdir $TOPDIR" \
  --define "_dbpath $TOPDIR/rpmdb" \
  -ba "$TOPDIR/SPECS/${NAME}.spec"
cp -f "$TOPDIR/RPMS/noarch/"*.rpm "$OUT_DIR/"
cp -f "$TOPDIR/SRPMS/"*.rpm "$OUT_DIR/" 2>/dev/null || true
rm -f "$PACKAGE_DIR"/*.rpm
cp -f "$TOPDIR/RPMS/noarch/"*.rpm "$PACKAGE_DIR/"

echo "RPM generado en: $OUT_DIR"
ls -lh "$OUT_DIR"
echo "Fedora package copied to: $PACKAGE_DIR"
ls -lh "$PACKAGE_DIR"
