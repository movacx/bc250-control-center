#!/bin/sh
# Package-manager operations are confined to a disposable rootless container.
set -eu
[ "${BC250_TUI_QA_CONTAINER:-}" = 1 ] || { echo 'Container-only bootstrap' >&2; exit 64; }
name=${1:?distribution required}
case "$name" in
  arch|cachyos|manjaro|artix)
    pacman -Syu --noconfirm --needed python python-psutil python-pytest python-pytest-cov git sudo polkit ncurses
    ;;
  alpine)
    apk add --no-progress bash openrc python3 py3-psutil py3-pytest py3-pytest-cov git sudo polkit ncurses-terminfo-base util-linux
    ;;
  gentoo)
    python3 -m venv /qa-venv
    /qa-venv/bin/python -m pip install psutil pytest pytest-cov
    ;;
  bazzite)
    python3 -m venv --system-site-packages /qa-venv
    /qa-venv/bin/python -m pip install pytest pytest-cov
    ;;
  debian|devuan|kali|parrot|kubuntu|xubuntu|lubuntu)
    apt-get update
    packages='python3 python3-psutil python3-pytest python3-pytest-cov python3-pip python3-venv git sudo pkexec ncurses-term'
    case "$name" in kubuntu|xubuntu|lubuntu) packages="$packages $name-desktop";; esac
    # All tokens above are repository-owned fixed package names.
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends $packages
    ;;
  *) echo 'Unknown test profile' >&2; exit 64;;
esac
python3 -c 'import curses; print("CURSES_OK")'
