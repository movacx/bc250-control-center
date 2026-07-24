#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NAME="bc250-control-center"
VERSION="${VERSION:-0.1.0}"
RELEASE="${RELEASE:-64}"
PKG_VERSION="${VERSION}-${RELEASE}"
BUILD_DIR="$ROOT/build/deb"
PKG_DIR="$BUILD_DIR/${NAME}_${PKG_VERSION}_all"
OUT_DIR="$ROOT/packaging/debian/out"
PACKAGE_DIR="$ROOT/packaging/packages/debian"

rm -rf "$BUILD_DIR"
mkdir -p "$PKG_DIR/DEBIAN" "$OUT_DIR" "$PACKAGE_DIR"
mkdir -p "$PKG_DIR/usr/share/$NAME" \
         "$PKG_DIR/usr/bin" \
         "$PKG_DIR/usr/share/doc/$NAME" \
         "$PKG_DIR/usr/share/applications" \
         "$PKG_DIR/usr/share/metainfo" \
         "$PKG_DIR/usr/share/polkit-1/actions" \
         "$PKG_DIR/usr/lib/systemd/user" \
         "$PKG_DIR/usr/libexec/bc250-control-center"

cp -a "$ROOT/mvc" "$PKG_DIR/usr/share/$NAME/"
find "$PKG_DIR/usr/share/$NAME/mvc" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "$PKG_DIR/usr/share/$NAME/mvc" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
install -Dm755 "$ROOT/scripts/bc250-control-center" "$PKG_DIR/usr/bin/bc250-control-center"
install -Dm755 "$ROOT/scripts/bc250-control-centerd" "$PKG_DIR/usr/bin/bc250-control-centerd"
install -Dm755 "$ROOT/mvc/Resources/privileged/bc250-fan-pwm-helper" \
  "$PKG_DIR/usr/libexec/bc250-control-center/bc250-fan-pwm-helper"
install -Dm644 "$ROOT/packaging/common/polkit/io.github.fabianbeita.bc250-control-center.policy" \
  "$PKG_DIR/usr/share/polkit-1/actions/io.github.fabianbeita.bc250-control-center.policy"
install -Dm644 "$ROOT/README.md" "$PKG_DIR/usr/share/doc/$NAME/README.md"
install -Dm644 "$ROOT/LICENSE" "$PKG_DIR/usr/share/doc/$NAME/LICENSE"

if [[ -d "$ROOT/docs" ]]; then
  while IFS= read -r -d '' doc_file; do
    install -Dm644 "$doc_file" "$PKG_DIR/usr/share/doc/$NAME/$(basename "$doc_file")"
  done < <(find "$ROOT/docs" -maxdepth 1 -type f \( -name '*.md' -o -name '*.txt' \) -print0)
fi

for size in 32 48 64 128 256 512 1024; do
  install -Dm644 "$ROOT/mvc/Resources/icons/bc250-control-center-${size}.png" \
    "$PKG_DIR/usr/share/icons/hicolor/${size}x${size}/apps/bc250-control-center.png"
done

install -Dm644 "$ROOT/packaging/common/desktop/io.github.fabianbeita.bc250-control-center.desktop" \
  "$PKG_DIR/usr/share/applications/io.github.fabianbeita.bc250-control-center.desktop"
install -Dm644 "$ROOT/packaging/common/metainfo/io.github.fabianbeita.bc250-control-center.metainfo.xml" \
  "$PKG_DIR/usr/share/metainfo/io.github.fabianbeita.bc250-control-center.metainfo.xml"
install -Dm644 "$ROOT/packaging/common/systemd-user/bc250-control-centerd.service" \
  "$PKG_DIR/usr/lib/systemd/user/bc250-control-centerd.service"

cat > "$PKG_DIR/DEBIAN/control" <<CONTROL
Package: $NAME
Version: $PKG_VERSION
Section: utils
Priority: optional
Architecture: all
Maintainer: Fabian Beita <fabianbeita@users.noreply.github.com>
Depends: python3, python3-pyqt6, python3-psutil
Recommends: lm-sensors, stress, git, pciutils, mesa-utils, vulkan-tools, curl, ca-certificates, dbus, dbus-user-session, polkitd | policykit-1, build-essential, dkms
Homepage: https://github.com/movacx/bc250-control-center
Description: Graphical control center for AMD BC-250 community tools
 BC250 Control Center provides a PyQt6 interface for monitoring and managing
 community tools used with the AMD BC-250 board. It includes process and
 performance views, GPU governor helpers, CPU OC helpers, 40CU actions and an
 experimental fan PWM panel.
CONTROL

cat > "$PKG_DIR/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi
exit 0
POSTINST

cat > "$PKG_DIR/DEBIAN/postrm" <<'POSTRM'
#!/bin/sh
set -e
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi
exit 0
POSTRM

# Shared build directories can inherit setgid. Debian control directories must not.
find "$PKG_DIR" -type d -exec chmod a-s,u=rwx,go=rx {} +
find "$PKG_DIR" -type f -exec chmod a-s,u=rw,go=r {} +
find "$PKG_DIR/usr/share/$NAME/mvc" -type f -name '*.sh' -exec chmod 0755 {} +
chmod 0755 "$PKG_DIR/usr/bin/bc250-control-center" \
           "$PKG_DIR/usr/bin/bc250-control-centerd" \
           "$PKG_DIR/usr/libexec/bc250-control-center/bc250-fan-pwm-helper" \
           "$PKG_DIR/DEBIAN/postinst" \
           "$PKG_DIR/DEBIAN/postrm"

deb_file="$OUT_DIR/${NAME}_${PKG_VERSION}_all.deb"
if command -v dpkg-deb >/dev/null 2>&1; then
  dpkg-deb --build --root-owner-group "$PKG_DIR" "$deb_file"
else
  if ! command -v ar >/dev/null 2>&1; then
    echo "ERROR: dpkg-deb and ar are missing. Install dpkg-dev or binutils first." >&2
    exit 1
  fi
  manual_dir="$BUILD_DIR/manual-deb"
  rm -rf "$manual_dir"
  mkdir -p "$manual_dir"
  printf '2.0\n' > "$manual_dir/debian-binary"
  (
    cd "$PKG_DIR/DEBIAN"
    tar --owner=0 --group=0 --numeric-owner -czf "$manual_dir/control.tar.gz" .
  )
  (
    cd "$PKG_DIR"
    tar --owner=0 --group=0 --numeric-owner --exclude='./DEBIAN' -czf "$manual_dir/data.tar.gz" .
  )
  rm -f "$deb_file"
  (
    cd "$manual_dir"
    ar rcs "$deb_file" debian-binary control.tar.gz data.tar.gz
  )
fi
rm -f "$PACKAGE_DIR"/*.deb
cp -f "$deb_file" "$PACKAGE_DIR/"

echo "Built: $deb_file"
echo "Copied: $PACKAGE_DIR/$(basename "$deb_file")"
