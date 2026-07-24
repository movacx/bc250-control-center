#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="${VERSION:-0.1.0}"
NAME="bc250-control-center"
BUILD_DIR="$ROOT/build/tarball"
SRC_DIR="$BUILD_DIR/${NAME}-${VERSION}"
OUT_DIR="$ROOT/packaging/tar-local/out"

rm -rf "$BUILD_DIR"
mkdir -p "$SRC_DIR" "$OUT_DIR"

rsync -a \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude '.pytest_cache' \
  --exclude '*.pyc' \
  --exclude 'build' \
  --exclude '*.pkg.tar.*' \
  --exclude '*.rpm' \
  --exclude '*.deb' \
  --exclude 'packaging/arch/local/src' \
  --exclude 'packaging/arch/local/pkg' \
  --exclude 'packaging/arch/local/*.tar.gz' \
  --exclude 'packaging/arch/local/*.pkg.tar.*' \
  --exclude 'packaging/rpm/out' \
  --exclude 'packaging/debian/out' \
  --exclude 'packaging/bazzite/out' \
  --exclude 'packaging/packages' \
  --exclude 'packaging/tar-local/out' \
  --exclude 'packaging/local/src' \
  --exclude 'packaging/local/pkg' \
  "$ROOT/" "$SRC_DIR/"

tar -C "$BUILD_DIR" -czf "$OUT_DIR/${NAME}-${VERSION}.tar.gz" "${NAME}-${VERSION}"
echo "Tarball generado en: $OUT_DIR/${NAME}-${VERSION}.tar.gz"
ls -lh "$OUT_DIR/${NAME}-${VERSION}.tar.gz"
