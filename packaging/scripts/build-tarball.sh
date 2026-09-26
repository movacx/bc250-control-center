#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
OUTPUT_DIR="${1:-$ROOT_DIR/dist}"
VERSION="$(tr -d '[:space:]' < "$ROOT_DIR/VERSION")"
if [[ -n "${BC250_VERSION:-}" && "$BC250_VERSION" != "$VERSION" ]]; then
  echo "BC250_VERSION must match the release VERSION file ($VERSION)." >&2
  exit 64
fi
SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(stat -c %Y "$ROOT_DIR/packaging/common/io.github.movacx.bc250-control-center.metainfo.xml")}"
RELEASE_SOURCE_EXCLUDES=(--exclude 'archive' --exclude 'tests')

[[ "$VERSION" =~ ^[0-9]+([.][0-9A-Za-z]+)*(-[0-9A-Za-z.]+)?$ ]] || { echo "Invalid release version: $VERSION" >&2; exit 64; }
mkdir -p -- "$OUTPUT_DIR"
bash "$ROOT_DIR/scripts/qa/validate-install-source.sh" "$ROOT_DIR"
target="$OUTPUT_DIR/bc250-control-center-$VERSION.tar.gz"
temporary="$target.tmp.$$"
trap 'rm -f -- "$temporary"' EXIT
# --format=gnu: openSUSE builds GNU tar with posix (pax) as its default,
# and pax headers record atime and ctime, so two builds of the same tree
# differed byte for byte there and nowhere else. --mode: a file left 0600 in
# the builder's tree must not ship unreadable to everyone but root.
tar --create --file - --format=gnu \
  --sort=name --mtime="@$SOURCE_DATE_EPOCH" --owner=0 --group=0 --numeric-owner \
  --mode='u+rwX,go+rX,go-w' \
  "${RELEASE_SOURCE_EXCLUDES[@]}" \
  --exclude '.git' --exclude '.pytest_cache' --exclude '__pycache__' \
  --exclude '*.pyc' --exclude '*.pyo' --exclude './dist' --exclude 'node_modules' \
  --transform "s,^,bc250-control-center-$VERSION/," \
  -C "$ROOT_DIR" \
  VERSION README.md LICENSE SECURITY.md pyproject.toml run.sh docs/THIRD_PARTY_NOTICES.md \
  assets integrations src frontends privileged scripts packaging \
  | gzip -n -9 > "$temporary"
mv -- "$temporary" "$target"
trap - EXIT
target_name="${target##*/}"
(
  cd -- "$OUTPUT_DIR"
  sha256sum "$target_name" > "$target_name.sha256"
)
echo "$target"
