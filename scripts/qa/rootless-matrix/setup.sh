#!/bin/bash
# setup.sh -- one-time preparation of the rootless distribution matrix:
# downloads the distribution rootfs images (about 700 MB) from
# images.linuxcontainers.org, installs python/grub/grubby/sudo in them and
# builds the fake BC-250 hardware tree. Needs bubblewrap, curl, tar, xz and
# newuidmap (for enter-user.sh). Everything lives in $BC250_QA
# (default ~/.cache/bc250-qa); nothing outside it is touched and no root is used.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); QA=${BC250_QA:-$HOME/.cache/bc250-qa}
mkdir -p "$QA/rootfs" "$QA/hw" "$QA/out"; cp "$here/enter.sh" "$QA/enter.sh"
base=https://images.linuxcontainers.org
index=$(curl -fsS "$base/meta/1.0/index-system")
fetch() { # distro release
  local path; path=$(awk -F';' -v d="$1" -v r="$2" '$1==d && $2==r && $3=="amd64" && $4=="default" {print $6}' <<<"$index")
  [ -n "$path" ] || { echo "no image for $1 $2" >&2; exit 1; }
  local name="$1-$2"
  if [ ! -d "$QA/rootfs/$name" ]; then
    curl -fL -o "$QA/rootfs/$name.tar.xz" "$base${path}rootfs.tar.xz"
    mkdir -p "$QA/rootfs/$name"; tar -xf "$QA/rootfs/$name.tar.xz" -C "$QA/rootfs/$name" --no-same-owner --exclude='./dev/*'
    chmod -R u+rwX "$QA/rootfs/$name"; rm -f "$QA/rootfs/$name.tar.xz"
    rm -f "$QA/rootfs/$name/etc/resolv.conf"; cp -L /etc/resolv.conf "$QA/rootfs/$name/etc/resolv.conf"
  fi
}
fetch fedora 44; fetch debian trixie; fetch ubuntu noble; fetch archlinux current; fetch mint zena

# Fake hardware: a BC-250 on the PCI bus, an amdgpu card, TTM and a /dev/port.
cd "$QA/hw"
mkdir -p sys/bus/pci/devices/0000:00:01.0 sys/class/drm/card1/device sys/module/ttm/parameters sys/module/amdgpu/parameters proc
echo 0x1002 > sys/bus/pci/devices/0000:00:01.0/vendor; echo 0x13fe > sys/bus/pci/devices/0000:00:01.0/device
echo 0x1002 > sys/class/drm/card1/device/vendor; echo 7970897920 > sys/class/drm/card1/device/mem_info_gtt_total
echo 536870912 > sys/class/drm/card1/device/mem_info_vram_total; echo 100000000 > sys/class/drm/card1/device/mem_info_vram_used
echo 1946020 > sys/module/ttm/parameters/pages_limit; echo 0 > sys/module/amdgpu/parameters/bc250_cc_write_mode
echo "BOOT_IMAGE=/boot/vmlinuz-linux root=UUID=aaaa-bbbb rw quiet" > proc/cmdline
printf 'MemTotal:       15500000 kB\nMemAvailable:   12000000 kB\n' > proc/meminfo
python3 -c "open('devport','wb').write(bytes(0x80))"

E="$QA/enter.sh"
"$E" archlinux-current --persist -- bash -c 'pacman-key --init >/dev/null 2>&1; pacman-key --populate archlinux >/dev/null 2>&1; pacman -Sy --noconfirm --needed --disable-sandbox python grub sudo diffutils rpm-tools dpkg zstd binutils'
for d in debian-trixie ubuntu-noble; do
  "$E" $d --persist -- bash -c 'apt-get -o APT::Sandbox::User=root update -qq; DEBIAN_FRONTEND=noninteractive apt-get -o APT::Sandbox::User=root install -y -qq --no-install-recommends python3 python3-venv python3-pip grub-common sudo diffutils'
done
"$E" mint-zena --persist -- bash -c 'apt-get -o APT::Sandbox::User=root update -qq; DEBIAN_FRONTEND=noninteractive apt-get -o APT::Sandbox::User=root install -y -qq --no-install-recommends python3 grub-common sudo diffutils'
chmod -R u+w "$QA/rootfs/fedora-44"
"$E" fedora-44 --persist -- bash -c 'dnf -y --setopt=install_weak_deps=False --setopt=tsflags=nocontexts,nocaps install python3 grubby sudo diffutils'
echo "ready: $QA"
