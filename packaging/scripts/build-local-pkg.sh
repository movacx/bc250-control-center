#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD_DIR="$ROOT/build/local-pkg"
SRC_DIR="$BUILD_DIR/bc250-control-center-local"
PKG_DIR="$ROOT/packaging/arch/local"
OUT_DIR="$ROOT/packaging/packages/arch"

rm -rf "$BUILD_DIR" "$PKG_DIR/src" "$PKG_DIR/pkg"
mkdir -p "$SRC_DIR" "$PKG_DIR" "$OUT_DIR"

rsync -a \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude 'build' \
  --exclude '*.pkg.tar.*' \
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

tar -C "$BUILD_DIR" -czf "$PKG_DIR/bc250-control-center-local.tar.gz" bc250-control-center-local
cd "$PKG_DIR"
makepkg -f "$@"
rm -f "$OUT_DIR"/*.pkg.tar.*
cp -f "$PKG_DIR"/*.pkg.tar.* "$OUT_DIR"/
echo "Arch package copied to: $OUT_DIR"
ls -lh "$OUT_DIR"
