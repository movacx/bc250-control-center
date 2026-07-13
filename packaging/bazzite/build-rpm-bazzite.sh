#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="${VERSION:-0.1.0}"
NAME="bc250-control-center"
TOPDIR="$ROOT/build/bazzite-rpm"
SRC_DIR="$TOPDIR/${NAME}-${VERSION}"
OUT_DIR="$ROOT/packaging/bazzite/out"
PACKAGE_DIR="$ROOT/packaging/packages/bazzite"
SPEC="$ROOT/packaging/rpm/${NAME}.spec"

if ! command -v rpmbuild >/dev/null 2>&1; then
  echo "ERROR: rpmbuild is not installed."
  echo "Bazzite/Fedora Atomic:"
  echo "  sudo rpm-ostree install rpm-build rpmdevtools rsync"
  echo "  systemctl reboot"
  exit 1
fi

if ! command -v rsync >/dev/null 2>&1; then
  echo "ERROR: rsync is not installed."
  echo "Bazzite/Fedora Atomic:"
  echo "  sudo rpm-ostree install rsync"
  echo "  systemctl reboot"
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
  --exclude 'packaging/arch/local/*.pkg.tar.*' \
  --exclude 'packaging/arch/local/*.tar.gz' \
  --exclude 'packaging/rpm/out' \
  --exclude 'packaging/bazzite/out' \
  --exclude 'packaging/packages/arch' \
  --exclude 'packaging/packages/fedora' \
  --exclude 'packaging/packages/bazzite' \
  --exclude 'packaging/tar-local/out' \
  "$ROOT/" "$SRC_DIR/"

tar -C "$TOPDIR" -czf "$TOPDIR/SOURCES/${NAME}-${VERSION}.tar.gz" "${NAME}-${VERSION}"
cp "$SPEC" "$TOPDIR/SPECS/"

rpmbuild \
  --define "_topdir $TOPDIR" \
  --define "_dbpath $TOPDIR/rpmdb" \
  -ba "$TOPDIR/SPECS/${NAME}.spec"

cp -f "$TOPDIR/RPMS/noarch/"*.rpm "$OUT_DIR/"
cp -f "$TOPDIR/SRPMS/"*.rpm "$OUT_DIR/" 2>/dev/null || true
rm -f "$PACKAGE_DIR"/*.rpm
cp -f "$TOPDIR/RPMS/noarch/"*.rpm "$PACKAGE_DIR/"

echo "Bazzite RPM output: $OUT_DIR"
ls -lh "$OUT_DIR"
echo "Bazzite package copied to: $PACKAGE_DIR"
ls -lh "$PACKAGE_DIR"
