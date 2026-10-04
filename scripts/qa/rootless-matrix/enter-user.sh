#!/bin/bash
# enter-user.sh <rootfs> [--os-release FILE] --root "cmd" --user "cmd"
# Like enter.sh, but with a second, unprivileged user (uid 1000, "deck") and a
# working sudo, for the installers that refuse to run as root. Rootless: a user
# namespace mapping uid 0 to you and uid 1000 to your subordinate range.
QA=${BC250_QA:-$HOME/.cache/bc250-qa}; base=$QA/rootfs/$1; shift
osr=""; rootcmd=":"; usercmd=":"; cmdline="$(cat $QA/hw/proc/cmdline)"; devport="$QA/hw/devport"
while [ $# -gt 0 ]; do case "$1" in
  --os-release) osr="$2"; shift 2;; --root) rootcmd="$2"; shift 2;; --user) usercmd="$2"; shift 2;;
  --devport) devport="$2"; shift 2;; *) echo bad arg $1; exit 2;; esac; done
root=$(mktemp -d $QA/run.XXXXXX); rmdir $root; cp -a --reflink=always $base $root
map=(--user --map-users=0:$(id -u):1 --map-users=1:100000:65535 --map-groups=0:$(id -g):1 --map-groups=1:100000:65535)
cleanup() { unshare "${map[@]}" rm -rf "$root" 2>/dev/null; rm -rf "$root" 2>/dev/null; }
trap cleanup EXIT
[ -n "$osr" ] && { rm -f "$root/etc/os-release"; cp "$osr" "$root/etc/os-release"; }
cmdfile=$(mktemp); echo "$cmdline" > "$cmdfile"
export QA root rootcmd usercmd devport cmdfile
unshare "${map[@]}" --mount --pid --fork --kill-child bash -c '
set -e
mount --make-rprivate /
mount --bind "$root" "$root"
mount -t proc proc "$root/proc"
mount -t tmpfs tmpfs "$root/dev"; mount -t tmpfs tmpfs "$root/run"; mount -t tmpfs tmpfs "$root/tmp"; chmod 1777 "$root/tmp"
for n in null zero random urandom full tty; do touch "$root/dev/$n"; mount --bind /dev/$n "$root/dev/$n"; done
ln -s /proc/self/fd "$root/dev/fd"; ln -s /proc/self/fd/0 "$root/dev/stdin"; ln -s /proc/self/fd/1 "$root/dev/stdout"; ln -s /proc/self/fd/2 "$root/dev/stderr"
touch "$root/dev/port"; mount --bind "$devport" "$root/dev/port"
mount --bind "$QA/hw/sys" "$root/sys"
mount --bind "$cmdfile" "$root/proc/cmdline"; mount --bind "$QA/hw/proc/meminfo" "$root/proc/meminfo"
mkdir -p "$root/src"; mount --bind /home/deck/Documentos/GitHub/bc250-control-center "$root/src"
grep -q "^deck:" "$root/etc/passwd" || { echo "deck:x:1000:1000:deck:/home/deck:/bin/bash" >> "$root/etc/passwd"; echo "deck:x:1000:" >> "$root/etc/group"; }
mkdir -p "$root/home/deck"; chown 1000:1000 "$root/home/deck"
mkdir -p "$root/etc/sudoers.d"; echo "deck ALL=(ALL) NOPASSWD: ALL" > "$root/etc/sudoers.d/deck"; chmod 440 "$root/etc/sudoers.d/deck"
for s in "$root/usr/bin/sudo" "$root/usr/sbin/sudo"; do [ -f "$s" ] && chmod 4111 "$s"; done
printf "auth sufficient pam_permit.so\naccount sufficient pam_permit.so\nsession sufficient pam_permit.so\n" > "$root/etc/pam.d/sudo"
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
chroot "$root" /bin/bash -c "cd /src; $rootcmd" || exit $?
if [ "$usercmd" != ":" ]; then
  # The kernel denies writes to host device nodes whose owner is not mapped
  # into the namespace; an ordinary unprivileged user gets a plain file as /dev/null.
  umount "$root/dev/null"; : > "$root/dev/null"; chmod 666 "$root/dev/null"
  chroot "$root" setpriv --reuid=1000 --regid=1000 --clear-groups env HOME=/home/deck USER=deck PATH=/usr/sbin:/usr/bin:/sbin:/bin /bin/bash -c "cd /src; $usercmd"
fi'
