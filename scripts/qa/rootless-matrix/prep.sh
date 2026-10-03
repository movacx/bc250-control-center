#!/bin/bash
# Runs inside the throw-away container, as the fake root: lays out the boot
# configuration of one distribution family. prep.sh <kind>
set -euo pipefail
kind=$1; here=/src/scripts/qa/rootless-matrix
mkdir -p /run/systemd/system /boot/grub /etc/default /var/lib
install -m755 "$here/stubs/systemctl" /usr/bin/systemctl
install -m755 "$here/stubs/limine-mkinitcpio" /usr/bin/limine-mkinitcpio
for dir in /usr/bin /usr/sbin; do [ -d $dir ] && [ ! -L $dir ] && install -m755 "$here/stubs/grub-probe" $dir/grub-probe; done
debian_grub() {
  : > /boot/grub/grub.cfg
  cat > /etc/default/grub <<'EOG'
# If you change this file, run 'update-grub' afterwards to update
GRUB_DEFAULT=0
GRUB_TIMEOUT=5
GRUB_DISTRIBUTOR=`( . /etc/os-release; echo ${NAME:-Debian} ) 2>/dev/null`
GRUB_CMDLINE_LINUX_DEFAULT="quiet"
GRUB_CMDLINE_LINUX=""
EOG
  touch /boot/vmlinuz-6.1.0-1-amd64 /boot/initrd.img-6.1.0-1-amd64
}
arch_grub() {
  : > /boot/grub/grub.cfg
  [ -f /etc/default/grub ] || cp /etc/default/grub.pacnew /etc/default/grub
  touch /boot/vmlinuz-linux /boot/initramfs-linux.img
}
case "$kind" in
  debian-grub|ubuntu-grub|mint-grub|py310-refused) debian_grub;;
  arch-grub-new) arch_grub;;
  arch-grub-old)
    arch_grub
    # grub 2.12 and earlier: grub-mkconfig reads /etc/default/grub only.
    sed -i '/default\/grub\.d/,/^done$/d' /usr/bin/grub-mkconfig
    if grep -q 'default/grub.d' /usr/bin/grub-mkconfig; then echo "prep: could not strip grub.d from grub-mkconfig" >&2; exit 1; fi;;
  cachyos-limine)
    cat > /etc/default/limine <<'EOG'
TARGET_OS_NAME="CachyOS"
ESP_PATH="/boot"
KERNEL_CMDLINE[default]="quiet nowatchdog splash rw"
EOG
    ;;
  fedora-grubby|nobara-grubby|bazzite)
    mkdir -p /boot/loader/entries /boot/grub2 /etc/default
    touch /boot/vmlinuz-6.1.0-1.fc44.x86_64 /boot/initramfs-6.1.0-1.fc44.x86_64.img
    cat > /boot/loader/entries/0123456789abcdef-6.1.0-1.fc44.x86_64.conf <<'EOG'
title Fedora Linux (6.1.0-1.fc44.x86_64)
version 6.1.0-1.fc44.x86_64
linux /vmlinuz-6.1.0-1.fc44.x86_64
initrd /initramfs-6.1.0-1.fc44.x86_64.img
options root=UUID=aaaa-bbbb ro rhgb quiet
grub_users $grub_users
grub_arg --unrestricted
grub_class fedora
EOG
    printf 'GRUB_DEFAULT=saved\nGRUB_ENABLE_BLSCFG=true\nGRUB_CMDLINE_LINUX="rhgb quiet"\n' > /etc/default/grub
    printf '# GRUB Environment Block\nsaved_entry=0123456789abcdef-6.1.0-1.fc44.x86_64\n' > /boot/grub2/grubenv
    ln -sf ../boot/grub2/grubenv /etc/grub2.cfg || true
    ;;
  steamos) :;;
  *) echo "unknown kind $kind" >&2; exit 2;;
esac
[ "$kind" = bazzite ] && { install -m755 "$here/stubs/rpm-ostree" /usr/bin/rpm-ostree; mkdir -p /run; : > /run/ostree-booted; }
exit 0
