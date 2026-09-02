#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
OUTPUT_DIR="${1:-$ROOT_DIR/dist}"
VERSION="$(tr -d '[:space:]' < "$ROOT_DIR/VERSION")"
PKG_RELEASE="${BC250_PKG_RELEASE:-1}"
if [[ -n "${BC250_VERSION:-}" && "$BC250_VERSION" != "$VERSION" ]]; then
  echo "BC250_VERSION must match the release VERSION file ($VERSION)." >&2
  exit 64
fi
SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(stat -c %Y "$ROOT_DIR/packaging/common/io.github.movacx.bc250-control-center.metainfo.xml")}"
RELEASE_SOURCE_EXCLUDES=(--exclude 'archive' --exclude 'tests')
: "${RELEASE_SOURCE_EXCLUDES[*]}"

command -v zstd >/dev/null || { echo "zstd is required" >&2; exit 69; }
[[ "$VERSION" =~ ^[0-9]+([.][0-9A-Za-z]+)*$ ]] || { echo "Invalid release version: $VERSION" >&2; exit 64; }
[[ "$PKG_RELEASE" =~ ^[1-9][0-9]*$ ]] || { echo "BC250_PKG_RELEASE must be a positive integer." >&2; exit 64; }
mkdir -p -- "$OUTPUT_DIR"
work="$(mktemp -d /tmp/bc250-arch-package.XXXXXX)"
trap 'rm -rf -- "$work"' EXIT
bash "$SCRIPT_DIR/stage-package-root.sh" "$work/root"
install -m644 "$ROOT_DIR/packaging/common/bc250-control-center.install" "$work/root/.INSTALL"
installed_size="$(du -sk "$work/root" | awk '{print $1 * 1024}')"
cat > "$work/root/.PKGINFO" <<EOF
pkgname = bc250-control-center
pkgbase = bc250-control-center
pkgver = $VERSION-$PKG_RELEASE
pkgdesc = BC-250 monitoring, tuning and recovery control center
url = https://github.com/movacx/bc250-control-center
builddate = $SOURCE_DATE_EPOCH
packager = BC250 Control Center local reproducible builder
size = $installed_size
arch = any
license = MIT
depend = python
depend = bash
depend = python-pyqt6
depend = python-psutil
depend = qt6-svg
depend = polkit
depend = jq
provides = bc250-control-center
conflict = bc250-control-center-git
replaces = bc250-control-center-git
optdepend = git: download reviewed upstream BC-250 tools
optdepend = lm_sensors: additional hardware sensor discovery
optdepend = pciutils: PCI and amdgpu diagnostics
optdepend = stress: CPU tuning stability checks
optdepend = vulkan-tools: Vulkan capability diagnostics
EOF
target="$OUTPUT_DIR/bc250-control-center-$VERSION-$PKG_RELEASE-any.pkg.tar.zst"
temporary="$target.tmp.$$"
# Pacman looks up .PKGINFO by its exact archive-root name. Archiving `.` would
# prefix every member with `./` (including `./.PKGINFO`), which libalpm treats
# as missing metadata and reports as an invalid or corrupted package. List the
# package metadata and payload explicitly so their archive paths are canonical.
tar --create --file - --sort=name --mtime="@$SOURCE_DATE_EPOCH" \
  --owner=0 --group=0 --numeric-owner -C "$work/root" \
  .PKGINFO .INSTALL usr \
  | zstd -q -19 -T0 -o "$temporary"

# Never publish an artifact whose compression stream or mandatory Arch
# metadata cannot be read. The portable checks run on every build host;
# libalpm performs an additional authoritative query on Arch-family systems.
zstd -q --test "$temporary"
if ! zstd -q -d -c "$temporary" | tar -tf - .PKGINFO >/dev/null; then
  echo "Generated package is missing readable .PKGINFO metadata." >&2
  exit 70
fi
if command -v pacman >/dev/null && ! pacman -Qip "$temporary" >/dev/null; then
  echo "Pacman rejected the generated package as invalid or corrupted." >&2
  exit 70
fi
mv -- "$temporary" "$target"
target_name="${target##*/}"
(
  cd -- "$OUTPUT_DIR"
  sha256sum "$target_name" > "$target_name.sha256"
)
echo "$target"
