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
tar --create --file - --format=gnu --sort=name --mtime="@$SOURCE_DATE_EPOCH" \
  --owner=0 --group=0 --numeric-owner -C "$work/payload" . \
  | gzip -n -9 > "$work/top/SOURCES/bc250-control-center-root.tar.gz"
# The %files list used to be written by hand, and it had already drifted:
# a systemd drop-in added to the payload failed the build with "installed
# (but unpackaged) file(s) found". Derive it from what is actually staged so
# a new file can never fail the build again.
#
# Only the directories that belong entirely to this package are listed as
# directories; everything else goes in file by file, because owning
# /usr/bin or /usr/lib/systemd/system would claim directories that belong to
# other packages.
owned_directories=(
  /usr/libexec/bc250-control-center
  /usr/share/bc250-control-center
  /usr/share/doc/bc250-control-center
)
files_list="$work/files.list"
: > "$files_list"
for directory in "${owned_directories[@]}"; do
  [[ -d "$work/payload$directory" ]] && printf '%s\n' "$directory" >> "$files_list"
done
owned_pattern="$(IFS='|'; printf '%s' "${owned_directories[*]}")"
(cd "$work/payload" && find . \( -type f -o -type l \) -printf '/%P\n') \
  | grep -vE "^($owned_pattern)/" \
  | LC_ALL=C sort >> "$files_list"
[[ -s "$files_list" ]] || { echo "The staged payload is empty." >&2; exit 70; }

cat > "$work/top/SPECS/bc250-control-center.spec" <<EOF
Name:           bc250-control-center
Version:        $RPM_VERSION
Release:        $RPM_RELEASE%{?dist}
Summary:        BC-250 monitoring, tuning and recovery control center
License:        MIT
URL:            https://github.com/movacx/bc250-control-center
Source0:        bc250-control-center-root.tar.gz
BuildArch:      noarch
Requires:       python3 >= 3.11, python3-psutil, python3-pip >= 22.3, python3-pyqt6, qt6-qtsvg, openssl, ca-certificates, polkit, jq, diffutils
Suggests:       git, lm_sensors, pciutils, stress, vulkan-tools

%description
Desktop and headless management for AMD BC-250 systems.

%prep

%build

%install
mkdir -p %{buildroot}
tar -xzf %{SOURCE0} -C %{buildroot}

%files
$(cat "$files_list")

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
# RPM 6 (Arch's rpm-tools, and the release workflow's Arch container) writes
# the v6 package format by default, whose payload is rpm's own cpio variant
# (magic 07070X, rpmlib(LargeFiles)). dnf and rpm install it, but rpm-ostree
# unpacks a local package with libarchive, which only reads standard cpio:
# on Bazzite and every Fedora Atomic "rpm-ostree install" stopped with
# "Reading rpm2cpio: Unrecognized archive format". The v4 format keeps the
# standard payload every published RPM had; rpm 4.x ignores this macro.
SOURCE_DATE_EPOCH="$SOURCE_DATE_EPOCH" rpmbuild -bb \
  --define "_rpmformat 4" \
  --define "_topdir $work/top" \
  --define "_buildhost bc250-control-center.invalid" \
  --define "_build_id_links none" \
  --define "_source_date_epoch_from_changelog 1" \
  --define "clamp_mtime_to_source_date_epoch 1" \
  --define "use_source_date_epoch_as_buildtime 1" \
  "$work/top/SPECS/bc250-control-center.spec"
# The file is named after the release alone (1.20.0, not 1.20.0-1); the
# package revision stays inside the metadata, where the package manager needs it.
built_rpm="$(find "$work/top/RPMS" -type f -name '*.noarch.rpm' -print -quit)"
[[ -n "$built_rpm" ]] || { echo "rpmbuild produced no noarch package." >&2; exit 70; }
if rpm -qp --dbpath "$work/rpmdb" --requires "$built_rpm" 2>/dev/null | grep -q '^rpmlib(LargeFiles)'; then
  echo "rpmbuild wrote a payload rpm-ostree cannot unpack (rpmlib(LargeFiles)); Bazzite could not install it." >&2
  exit 70
fi
target="$OUTPUT_DIR/bc250-control-center-$VERSION.noarch.rpm"
cp -f -- "$built_rpm" "$target"
(
  cd -- "$OUTPUT_DIR"
  sha256sum "${target##*/}" > "${target##*/}.sha256"
)
printf '%s\n' "$target"
