#!/bin/sh
# runs as root inside container: bootstrap, then run inner as tester
echo "### BOOTSTRAP $(. /etc/os-release; echo $PRETTY_NAME)"
need="bash sudo python3 diffutils findutils"
if command -v apt-get >/dev/null; then
  # End-of-life releases (bullseye, buster, Ubuntu 18.04) only live on the archive mirrors.
  . /etc/os-release; case "${VERSION_CODENAME:-}" in bullseye|buster) sed -i "s#deb.debian.org#archive.debian.org#; s#security.debian.org[^ ]*#archive.debian.org/debian-security#; /-updates/d" /etc/apt/sources.list /etc/apt/sources.list.d/* 2>/dev/null; echo "Acquire::Check-Valid-Until false;" >/etc/apt/apt.conf.d/99eol;; esac
  export DEBIAN_FRONTEND=noninteractive; for i in 1 2 3; do apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq --fix-missing bash sudo python3 diffutils findutils >/tmp/boot.log 2>&1 && break; done
elif command -v pacman >/dev/null; then
  pacman -Sy --noconfirm --needed bash sudo python diffutils findutils >/tmp/boot.log 2>&1
elif command -v dnf >/dev/null; then
  dnf install -y shadow-utils bash sudo python3 diffutils findutils >/tmp/boot.log 2>&1
elif command -v microdnf >/dev/null; then
  microdnf install -y shadow-utils bash sudo python3 diffutils findutils >/tmp/boot.log 2>&1
elif command -v yum >/dev/null; then
  yum install -y shadow-utils bash sudo python3 diffutils findutils >/tmp/boot.log 2>&1
elif command -v apk >/dev/null; then
  apk add --no-progress bash sudo python3 diffutils findutils >/tmp/boot.log 2>&1
elif command -v zypper >/dev/null; then
  zypper -n install bash sudo python3 diffutils findutils >/tmp/boot.log 2>&1
elif command -v xbps-install >/dev/null; then
  xbps-install -Sy shadow util-linux bash sudo python3 diffutils findutils >/tmp/boot.log 2>&1
elif command -v urpmi >/dev/null; then
  urpmi --auto bash sudo python3 diffutils findutils >/tmp/boot.log 2>&1
elif command -v tdnf >/dev/null; then
  tdnf install -y shadow-utils bash sudo python3 diffutils findutils shadow >/tmp/boot.log 2>&1
elif command -v emerge >/dev/null; then
  echo "gentoo: no emerge bootstrap (slow), using stage3 content" >/tmp/boot.log
fi

if [ "$PHASE" = pytest ] || [ "$PHASE" = detail ]; then
  if command -v apt-get >/dev/null; then apt-get install -y -qq python3-venv python3-pip libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3 libglib2.0-0 >/tmp/boot2.log 2>&1
  elif command -v pacman >/dev/null; then pacman -Syu --noconfirm --needed python-pip libglvnd libxkbcommon fontconfig dbus >/tmp/boot2.log 2>&1
  elif command -v dnf >/dev/null; then dnf install -y python3-pip mesa-libEGL mesa-libGL libxkbcommon fontconfig dbus-libs >/tmp/boot2.log 2>&1
  elif command -v apk >/dev/null; then apk add --no-progress py3-pip py3-virtualenv >/tmp/boot2.log 2>&1
  fi
  echo "boot2_rc=$?"; tail -2 /tmp/boot2.log
fi
echo "boot_rc=$? ; bash=$(command -v bash) sudo=$(command -v sudo) python3=$(command -v python3)"
tail -3 /tmp/boot.log
useradd -m tester 2>/dev/null || adduser -D tester 2>/dev/null
mkdir -p /etc/sudoers.d; echo 'tester ALL=(ALL) NOPASSWD:ALL' >/etc/sudoers.d/t; chmod 440 /etc/sudoers.d/t
mkdir -p /work; chown tester /work
cp /qa/inner.sh /tmp/inner.sh; chmod 755 /tmp/inner.sh
if command -v sudo >/dev/null && sudo -n -u tester true >/dev/null 2>&1; then exec sudo -u tester -H env PHASE="$PHASE" bash /tmp/inner.sh
else exec su tester -s /bin/bash -c "PHASE=$PHASE bash /tmp/inner.sh"; fi
