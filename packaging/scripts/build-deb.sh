#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
OUTPUT_DIR="${1:-$ROOT_DIR/dist}"
VERSION="$(tr -d '[:space:]' < "$ROOT_DIR/VERSION")"
DEB_RELEASE="${BC250_DEB_RELEASE:-1}"
RELEASE_SOURCE_EXCLUDES=(--exclude 'archive' --exclude 'tests')
: "${RELEASE_SOURCE_EXCLUDES[*]}"
if [[ -n "${BC250_VERSION:-}" && "$BC250_VERSION" != "$VERSION" ]]; then
  echo "BC250_VERSION must match the release VERSION file ($VERSION)." >&2
  exit 64
fi
[[ "$VERSION" =~ ^[0-9]+([.][0-9A-Za-z]+)*(-[0-9A-Za-z.]+)?$ ]] || {
  echo "Invalid release version: $VERSION" >&2
  exit 64
}
[[ "$DEB_RELEASE" =~ ^[1-9][0-9]*$ ]] || {
  echo "BC250_DEB_RELEASE must be a positive integer." >&2
  exit 64
}
command -v dpkg-deb >/dev/null || { echo "dpkg-deb is required" >&2; exit 69; }

mkdir -p -- "$OUTPUT_DIR"
work="$(mktemp -d /tmp/bc250-deb-package.XXXXXX)"
trap 'rm -rf -- "$work"' EXIT
bash "$SCRIPT_DIR/stage-package-root.sh" "$work/root"
rm -rf -- "$work/root/usr/share/libalpm"
install -d -m755 "$work/root/DEBIAN"
cat > "$work/root/DEBIAN/control" <<EOF
Package: bc250-control-center
Version: $VERSION-$DEB_RELEASE
Section: utils
Priority: optional
Architecture: all
Maintainer: BC250 Control Center contributors <noreply@example.invalid>
Depends: python3, python3-pyqt6, python3-psutil, libqt6svg6, pkexec | policykit-1, jq
Suggests: git, lm-sensors, pciutils, stress, vulkan-tools
Description: BC-250 monitoring, tuning and recovery control center
 Desktop and headless management for AMD BC-250 systems.
EOF
cat > "$work/root/DEBIAN/preinst" <<'EOF'
#!/bin/sh
set -e
exit 0
EOF
cat > "$work/root/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
# dpkg preserves the mode of some already-existing directories during a
# reinstall/upgrade. Repair this privileged trust boundary explicitly so an
# old 0775 directory cannot make the CU helpers reject one another.
install -d -o 0 -g 0 -m 0755 \
  /usr/libexec/bc250-control-center \
  /usr/libexec/bc250-control-center/lib
/usr/libexec/bc250-control-center/bc250-package-maintenance post-install
EOF
cat > "$work/root/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = remove ] || [ "$1" = deconfigure ]; then
  /usr/libexec/bc250-control-center/bc250-package-maintenance pre-remove
fi
EOF
chmod 0755 "$work/root/DEBIAN/preinst" "$work/root/DEBIAN/postinst" "$work/root/DEBIAN/prerm"

target="$OUTPUT_DIR/bc250-control-center_${VERSION}-${DEB_RELEASE}_all.deb"
temporary="$target.tmp.$$"
SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(stat -c %Y "$ROOT_DIR/packaging/common/io.github.movacx.bc250-control-center.metainfo.xml")}" \
  dpkg-deb --root-owner-group --build "$work/root" "$temporary"
mv -- "$temporary" "$target"
target_name="${target##*/}"
(
  cd -- "$OUTPUT_DIR"
  sha256sum "$target_name" > "$target_name.sha256"
)
echo "$target"
