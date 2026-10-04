#!/bin/bash
# enter.sh <rootfs> [--os-release FILE] [--cmdline STR] [--bind SRC DST]... -- cmd...
# Every run works on a throw-away reflink clone of the rootfs (instant on btrfs).
QA=${BC250_QA:-$HOME/.cache/bc250-qa}; base=$QA/rootfs/$1; shift
osr=""; cmdline="$(cat $QA/hw/proc/cmdline)"; extra=(); persist=""
while [ "$1" != "--" ]; do
  case "$1" in
    --os-release) osr="$2"; shift 2;;
    --cmdline) cmdline="$2"; shift 2;;
    --bind) extra+=(--bind "$2" "$3"); shift 3;;
    --persist) persist=1; shift;;
    *) echo bad arg $1; exit 2;;
  esac
done; shift
if [ -n "$persist" ]; then root=$base; else
  root=$(mktemp -d $QA/run.XXXXXX); rmdir $root; cp -a --reflink=always $base $root
  trap 'chmod -R u+w "$root" 2>/dev/null; rm -rf "$root"' EXIT
fi
tmp=$(mktemp -d); echo "$cmdline" > $tmp/cmdline
[ -n "$osr" ] && { rm -f "$root/etc/os-release"; cp "$osr" "$root/etc/os-release"; }
bwrap --unshare-user --uid 0 --gid 0 --unshare-pid --unshare-ipc --unshare-uts \
  --bind "$root" / --proc /proc --dev /dev --tmpfs /run --tmpfs /tmp \
  --bind $QA/hw/sys /sys --ro-bind $tmp/cmdline /proc/cmdline --ro-bind $QA/hw/proc/meminfo /proc/meminfo \
  --bind $QA/hw/devport /dev/port \
  --ro-bind /home/deck/Documentos/GitHub/bc250-control-center /src \
  --setenv HOME /root --setenv PATH /usr/sbin:/usr/bin:/sbin:/bin --chdir /src "${extra[@]}" "$@"
rc=$?; rm -rf $tmp; exit $rc
