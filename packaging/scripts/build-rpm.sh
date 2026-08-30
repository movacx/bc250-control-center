#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
OUTPUT_DIR="${1:-$ROOT_DIR/dist}"
VERSION="$(tr -d '[:space:]' < "$ROOT_DIR/VERSION")"
# RPM permits a tilde for pre-release ordering, but an unescaped tilde in
# Bash's parameter-expansion replacement is expanded to $HOME. Keep it literal.
RPM_VERSION="${VERSION/-/\~}"
RPM_RELEASE="${BC250_RPM_RELEASE:-1}"
if [[ -n "${BC250_VERSION:-}" && "$BC250_VERSION" != "$VERSION" ]]; then
  echo "BC250_VERSION must match the release VERSION file ($VERSION)." >&2
  exit 64
fi
SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(stat -c %Y "$ROOT_DIR/packaging/common/io.github.movacx.bc250-control-center.metainfo.xml")}"
RELEASE_SOURCE_EXCLUDES=(--exclude 'archive' --exclude 'tests')
: "${RELEASE_SOURCE_EXCLUDES[*]}"

command -v rpmbuild >/dev/null || { echo "rpmbuild is required" >&2; exit 69; }
[[ "$VERSION" =~ ^[0-9]+([.][0-9A-Za-z]+)*(-[0-9A-Za-z.]+)?$ ]] || { echo "Invalid release version: $VERSION" >&2; exit 64; }
[[ "$RPM_RELEASE" =~ ^[1-9][0-9]*$ ]] || { echo "BC250_RPM_RELEASE must be a positive integer." >&2; exit 64; }
mkdir -p -- "$OUTPUT_DIR"
work="$(mktemp -d /tmp/bc250-rpm-package.XXXXXX)"
trap 'rm -rf -- "$work"' EXIT
mkdir -p "$work/top"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
bash "$SCRIPT_DIR/stage-package-root.sh" "$work/payload"
# libalpm hooks are meaningful only to pacman.  Shipping one in an RPM leaves
# an inert Arch-specific file on Fedora/Bazzite and makes package ownership
# needlessly broader.
rm -rf -- "$work/payload/usr/share/libalpm"
tar --create --file - --sort=name --mtime="@$SOURCE_DATE_EPOCH" \
  --owner=0 --group=0 --numeric-owner -C "$work/payload" . \
  | gzip -n -9 > "$work/top/SOURCES/bc250-control-center-root.tar.gz"
cat > "$work/top/SPECS/bc250-control-center.spec" <<EOF
Name:           bc250-control-center
Version:        $RPM_VERSION
Release:        $RPM_RELEASE%{?dist}
Summary:        BC-250 monitoring, tuning and recovery control center
License:        MIT
URL:            https://github.com/movacx/bc250-control-center
Source0:        bc250-control-center-root.tar.gz
BuildArch:      noarch
Requires:       python3, python3-psutil, python3-pyqt6, qt6-qtsvg, polkit, jq
Suggests:       git, lm_sensors, pciutils, stress, vulkan-tools

%description
Desktop and headless management for AMD BC-250 systems.

%prep

%build

%install
mkdir -p %{buildroot}
tar -xzf %{SOURCE0} -C %{buildroot}

%files
/usr/bin/bc250-control-center
/usr/bin/bc250-control-center-cli
/usr/bin/bc250-control-center-decky-install
/usr/bin/bc250-control-centerd
/usr/lib/systemd/user/bc250-control-centerd.service
/usr/libexec/bc250-control-center
/usr/share/applications/io.github.movacx.bc250-control-center.desktop
/usr/share/bc250-control-center
/usr/share/doc/bc250-control-center
/usr/share/icons/hicolor/*/apps/bc250-control-center.png
/usr/share/metainfo/io.github.movacx.bc250-control-center.metainfo.xml
/usr/share/pixmaps/bc250-control-center.png
/usr/share/polkit-1/actions/io.github.movacx.bc250-control-center.policy

%preun
if [ "\$1" -eq 0 ]; then
  /usr/libexec/bc250-control-center/bc250-package-maintenance pre-remove || exit 1
fi

%post
/usr/libexec/bc250-control-center/bc250-package-maintenance post-install

%changelog
* Thu Aug 13 2026 BC250 Control Center <noreply@example.invalid> - $RPM_VERSION-$RPM_RELEASE
- Reproducible local package build.
EOF
SOURCE_DATE_EPOCH="$SOURCE_DATE_EPOCH" rpmbuild -bb \
  --define "_topdir $work/top" \
  --define "_buildhost bc250-control-center.invalid" \
  --define "_build_id_links none" \
  --define "_source_date_epoch_from_changelog 1" \
  --define "clamp_mtime_to_source_date_epoch 1" \
  --define "use_source_date_epoch_as_buildtime 1" \
  "$work/top/SPECS/bc250-control-center.spec"
find "$work/top/RPMS" -type f -name '*.rpm' -exec cp -f -- {} "$OUTPUT_DIR/" \;
for rpm in "$OUTPUT_DIR"/*.rpm; do sha256sum "$rpm" > "$rpm.sha256"; done
printf '%s\n' "$OUTPUT_DIR"/*.rpm
