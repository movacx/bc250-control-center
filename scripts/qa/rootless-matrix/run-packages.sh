#!/bin/bash
# run-packages.sh -- build the four release packages (in an Arch rootfs) and
# install/remove each one with its own package manager. Rootless.
here=$(cd "$(dirname "$0")" && pwd); QA=${BC250_QA:-$HOME/.cache/bc250-qa}; out=$QA/out; rc=0
if [ "$1" != "--no-build" ]; then
  "$QA/enter.sh" archlinux-current --bind "$out" /out -- bash -c 'pacman -S --noconfirm --needed --disable-sandbox rpm-tools dpkg zstd binutils >/dev/null 2>&1; cd /src && bash packaging/scripts/build-release.sh /out >/tmp/build.log 2>&1 && echo "  PASS  build-release.sh built the four packages" || { echo "  FAIL  build-release.sh"; tail -n 20 /tmp/build.log; exit 1; }' || exit 1
fi
run() { shift; local fam=$1 rootfs=$2 kind=$3; echo "=== packages: $fam on $rootfs ($kind)"; shift 3
  args=(); [ -n "${OSREL:-}" ] && args=(--os-release "$here/os-release/$OSREL")
  "$QA/enter.sh" "$rootfs" "${args[@]}" --bind "$out" /out -- bash /src/scripts/qa/rootless-matrix/pkg_scenario.sh "$fam" "$kind" || rc=1; }
OSREL= run x deb debian-trixie debian-grub
OSREL=linuxmint run x deb ubuntu-noble mint-grub
OSREL= run x deb ubuntu-noble ubuntu-grub
OSREL= run x arch archlinux-current arch-grub-new
OSREL=cachyos run x arch archlinux-current cachyos-limine
OSREL=nobara run x rpm fedora-44 nobara-grubby
OSREL= run x rpm fedora-44 fedora-grubby
OSREL=bazzite run x rpm fedora-44 bazzite
exit $rc
