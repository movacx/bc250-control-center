#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
#
# BC-250 GFX1013 compute-queue fix (DryhoppedIPA/bc250-gfx1013-fix, V33),
# built from source on the running kernel -- for the distributions upstream's
# installer does not cover. Fedora keeps upstream's own installer; Bazzite and
# SteamOS have their own reviewed backends and are refused here.
#
# The two halves go together, exactly as upstream requires:
#   kernel  amdgpu.ko built from the kernel.org source of the running kernel's
#           version with the V33 patches, against the distribution's headers;
#   Mesa    RADV from the pinned mesa-26.2.0-rc3 tarball with patch 0001,
#           installed privately under /opt/bc250cc-gfx1013/<version>.
#
# Nothing replaces the distribution's amdgpu or Mesa. Instead:
#   * the stock module is left in place and autoloading of amdgpu is held back
#     (modprobe blacklist), so a small boot service decides which module to
#     load once the root file system is writable;
#   * that service records an attempt before loading the patched module, and a
#     timer clears it three minutes into a healthy boot. A boot that never got
#     that far falls back to the stock module next time and switches the fix
#     off by itself;
#   * "bc250.gfx1013=0" on the kernel command line (press e in the boot menu)
#     forces the stock module for that boot;
#   * the private RADV is offered to desktop sessions only while the patched
#     module is the one actually loaded, checked by its srcversion.
#
# usage:
#   bc250-gfx1013-source.sh deps                 install build tools (sudo)
#   bc250-gfx1013-source.sh build --source DIR   build both halves as the user
#   sudo bc250-gfx1013-source.sh install --stage DIR
#   sudo bc250-gfx1013-source.sh enable|disable|uninstall
#   bc250-gfx1013-source.sh status

set -Eeuo pipefail

MESA_VERSION=26.2.0-rc3
MESA_SHA256=f733c005660d342a51c6727d1ad481f43d05b4c601ac72247fa641e1d73a8ad1
MESA_URL="https://archive.mesa3d.org/mesa-${MESA_VERSION}.tar.xz"
MARKER="# Managed by BC250 Control Center: GFX1013 compute-queue fix"
LIB_DIR=/usr/lib/bc250cc-gfx1013
OPT_DIR=/opt/bc250cc-gfx1013
CONF_DIR=/etc/bc250cc-gfx1013
STATE_DIR=/var/lib/bc250cc-gfx1013
RUN_DIR=/run/bc250cc-gfx1013
MODPROBE_CONF=/etc/modprobe.d/bc250cc-gfx1013.conf
LOAD_UNIT=/etc/systemd/system/bc250cc-gfx1013-load.service
CONFIRM_UNIT=/etc/systemd/system/bc250cc-gfx1013-confirm.service
CONFIRM_TIMER=/etc/systemd/system/bc250cc-gfx1013-confirm.timer
GENERATOR=/usr/lib/systemd/user-environment-generators/60-bc250cc-gfx1013
KVER="$(uname -r)"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
say() { printf '== %s\n' "$*"; }

require_root() { [[ ${EUID} -eq 0 ]] || die "this step needs root; run it with sudo"; }

os_field() {
    local field=$1
    [[ -r /etc/os-release ]] || return 0
    # shellcheck disable=SC1091
    ( . /etc/os-release; printf '%s' "${!field:-}" )
}

family() {
    local id like
    id="$(os_field ID)"; like=" $(os_field ID_LIKE) "
    case "$id" in
        bazzite) echo bazzite ;;
        steamos) echo steamos ;;
        fedora) echo fedora ;;
        arch|cachyos|endeavouros|manjaro|garuda) echo arch ;;
        debian|ubuntu|linuxmint|pop|zorin|elementary) echo debian ;;
        opensuse-tumbleweed|opensuse-slowroll|opensuse*) echo suse ;;
        *)
            case "$like" in
                *" arch "*) echo arch ;;
                *" debian "*|*" ubuntu "*) echo debian ;;
                *" suse "*) echo suse ;;
                *" fedora "*) echo fedora ;;
                *) echo unknown ;;
            esac ;;
    esac
}

check_host() {
    local fam
    fam="$(family)"
    case "$fam" in
        bazzite) die "Bazzite has its own reviewed async-compute release; this build is not for it." ;;
        steamos) die "SteamOS uses its own reviewed toolkit; this build is not for it." ;;
        fedora) die "Fedora uses DryhoppedIPA's own installer; use that workflow instead." ;;
        unknown) die "this distribution is not recognised; apply the patches by hand (upstream README, option 2)." ;;
    esac
    [[ -e /run/ostree-booted ]] && die "image-based (rpm-ostree) systems cannot take an out-of-tree amdgpu this way."
    [[ "$(uname -m)" == x86_64 ]] || die "x86_64 only."
    local found=0 device
    for device in /sys/bus/pci/devices/*; do
        [[ -r $device/vendor && -r $device/device ]] || continue
        [[ $(<"$device/vendor") == 0x1002 && $(<"$device/device") == 0x13fe ]] && { found=1; break; }
    done
    [[ $found -eq 1 ]] || die "AMD BC-250 (PCI 1002:13fe) was not found."
    case "$KVER" in
        *bc250*) die "this kernel ($KVER) already carries a BC-250 build of amdgpu; the fix is part of it." ;;
    esac
    # The V33 patches apply from linux 6.14 on (checked 6.14 to 7.2); on 6.12
    # (Debian 13), 6.8 (Ubuntu 24.04) or older they do not. Say so before any
    # package is installed or anything is downloaded.
    local release="${KVER%%-*}" kmajor kminor
    kmajor="${release%%.*}"; kminor="${release#*.}"; kminor="${kminor%%.*}"
    if [[ $kmajor =~ ^[0-9]+$ && $kminor =~ ^[0-9]+$ ]] && (( kmajor < 6 || (kmajor == 6 && kminor < 14) )); then
        die "kernel $KVER is older than 6.14; the V33 patches need linux 6.14 or newer. Install a newer kernel (for example a backports or HWE kernel) and retry."
    fi
    if [[ -r /sys/kernel/security/lockdown ]] && grep -q '\[integrity\]\|\[confidentiality\]' /sys/kernel/security/lockdown; then
        die "kernel lockdown is active (usually Secure Boot): an unsigned amdgpu would be refused."
    fi
}

# ---------------------------------------------------------------- deps (user)
deps() {
    check_host
    local fam kernel_pkg
    fam="$(family)"
    case "$fam" in
        arch)
            kernel_pkg="$(pacman -Qqo "/usr/lib/modules/$KVER/vmlinuz" 2>/dev/null || true)"
            [[ -n $kernel_pkg ]] || die "cannot tell which package owns kernel $KVER."
            local -a wanted=(base-devel bc cpio xz curl patch \
                meson ninja python-mako python-yaml python-packaging glslang \
                libdrm wayland wayland-protocols libxcb libx11 libxrandr libxshmfence \
                expat zlib zstd spirv-tools clang lld llvm "${kernel_pkg}-headers")
            # Ask pacman which of these are really missing. It honours
            # "provides": CachyOS ships zlib-ng-compat, which provides zlib,
            # and naming zlib outright made pacman try to replace it and stop
            # on the conflict.
            local -a missing=()
            mapfile -t missing < <(pacman -T "${wanted[@]}" || true)
            if ((${#missing[@]})); then
                say "installing ${missing[*]}"
                sudo pacman -S --needed --noconfirm "${missing[@]}"
            fi
            ;;
        debian)
            sudo apt-get update
            sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y build-essential bc cpio \
                xz-utils curl patch meson ninja-build python3-mako python3-yaml python3-packaging \
                glslang-tools libdrm-dev libwayland-dev wayland-protocols libxcb-dri3-dev \
                libxcb-present-dev libxcb-randr0-dev libxcb-shm0-dev libxcb-sync-dev \
                libx11-xcb-dev libx11-dev libxrandr-dev libxshmfence-dev libexpat1-dev \
                zlib1g-dev libzstd-dev spirv-tools libelf-dev clang lld llvm \
                "linux-headers-$KVER"
            ;;
        suse)
            sudo zypper --non-interactive install --no-recommends -t pattern devel_basis
            sudo zypper --non-interactive install --no-recommends bc cpio xz curl patch meson \
                ninja python3-Mako python3-PyYAML python3-packaging glslang-devel libdrm-devel \
                wayland-devel wayland-protocols-devel libxcb-devel libX11-devel libXrandr-devel \
                libxshmfence-devel libexpat-devel zlib-devel libzstd-devel spirv-tools \
                libelf-devel clang lld llvm kernel-default-devel
            ;;
    esac
    [[ -d /usr/lib/modules/$KVER/build ]] || die "kernel headers for $KVER were not installed; reboot into the newest kernel and retry."
    say "build tools ready"
}

fetch() {
    local url=$1 destination=$2
    [[ -s $destination ]] && return 0
    printf '   downloading %s\n' "${url##*/}"
    # curl sizes its bar from COLUMNS, which is fixed when the terminal opens
    # and wider than the panel once it is resized; a short bar always fits.
    COLUMNS=60 curl -fL --retry 3 --connect-timeout 20 --progress-bar -o "$destination.part" "$url"
    mv -- "$destination.part" "$destination"
}

# --------------------------------------------------------------- build (user)
build() {
    local source="" stage="" kernel_only=0
    while (($#)); do
        case $1 in
            --source) source=$2; shift 2 ;;
            --stage) stage=$2; shift 2 ;;
            --kernel-only) kernel_only=1; shift ;;
            *) die "unknown build option $1" ;;
        esac
    done
    [[ ${EUID} -ne 0 ]] || die "build as your own user, not as root."
    check_host
    [[ -f $source/patches/mesa/series && -d $source/patches/kernel/v33 ]] || die "upstream checkout is incomplete: $source"
    local version base major headers work
    version="$(tr -d '[:space:]' < "$source/VERSION")"
    [[ $version =~ ^[0-9A-Za-z._-]+$ ]] || die "invalid upstream version"
    # Debian names its kernels 6.16.12+deb13-amd64: the kernel.org release is
    # what comes before both the "-" and the "+".
    base="${KVER%%-*}"; base="${base%%+*}"; major="${base%%.*}"
    [[ $base =~ ^[0-9]+\.[0-9]+(\.[0-9]+)?$ ]] || die "cannot derive a kernel.org version from $KVER"
    # kernel.org names the first release of a series 7.2, not 7.2.0.
    [[ $base =~ ^[0-9]+\.[0-9]+\.0$ ]] && base="${base%.0}"
    headers="/usr/lib/modules/$KVER/build"
    [[ -f $headers/Makefile && -f $headers/.config ]] || die "kernel headers for $KVER are missing; run the dependency step first."
    stage="${stage:-${XDG_CACHE_HOME:-$HOME/.cache}/bc250-control-center/gfx1013/$version}"
    work="$stage/work"
    # A finished build for this kernel and upstream version is kept: when only
    # the privileged install failed (a password prompt that timed out after
    # the long build), running again goes straight to installing.
    if [[ -r $stage/build.env && -f $stage/modules/$KVER/amdgpu.ko ]] \
        && grep -qx "VERSION=$version" "$stage/build.env" \
        && grep -qx "KVER=$KVER" "$stage/build.env" \
        && { [[ $kernel_only -eq 1 ]] || { ! grep -qx 'KERNEL_ONLY=1' "$stage/build.env" \
            && [[ -f $stage/mesa-root$OPT_DIR/$version/lib/libvulkan_radeon.so ]]; }; }; then
        say "already built for $KVER: $stage"
        return 0
    fi
    mkdir -p "$work"

    say "kernel half: linux-$base amdgpu with V33 for $KVER"
    local tarball="$work/linux-$base.tar.xz" sums="$work/sha256sums-v$major.asc"
    fetch "https://cdn.kernel.org/pub/linux/kernel/v${major}.x/linux-$base.tar.xz" "$tarball"
    rm -f -- "$sums"
    fetch "https://cdn.kernel.org/pub/linux/kernel/v${major}.x/sha256sums.asc" "$sums"
    local expected
    expected="$(awk -v name="linux-$base.tar.xz" '$2 == name {print $1}' "$sums")"
    [[ ${#expected} -eq 64 ]] || die "kernel.org lists no checksum for linux-$base.tar.xz"
    printf '%s  %s\n' "$expected" "$tarball" | sha256sum -c - >/dev/null || die "linux-$base.tar.xz failed its kernel.org checksum"
    local tree="$work/linux-$base"
    rm -rf -- "$tree"
    tar -C "$work" -xf "$tarball" --wildcards "linux-$base/drivers/gpu/drm/amd"
    local patch_file
    for patch_file in "$source"/patches/kernel/v33/*.patch; do
        patch -p1 -s --dry-run -d "$tree" < "$patch_file" \
            || die "$(basename "$patch_file") does not apply to linux-$base; this kernel is not supported yet."
        patch -p1 -s -d "$tree" < "$patch_file"
        printf '   applied %s\n' "$(basename "$patch_file")"
    done
    # amdgpu_trace.h names its directory relative to the kernel tree, which an
    # out-of-tree build does not have. "." resolves through the module's own
    # include path. (An absolute path does not work: the directory name
    # "linux-X.Y" contains the predefined macro "linux", which the
    # preprocessor turns into "1".) Same repair as the Fedora workflow.
    local trace="$tree/drivers/gpu/drm/amd/amdgpu/amdgpu_trace.h"
    if grep -Fqx '#define TRACE_INCLUDE_PATH ../../drivers/gpu/drm/amd/amdgpu' "$trace"; then
        sed -i 's|^#define TRACE_INCLUDE_PATH \.\./\.\./drivers/gpu/drm/amd/amdgpu$|#define TRACE_INCLUDE_PATH .|' "$trace"
    elif ! grep -Fqx '#define TRACE_INCLUDE_PATH .' "$trace"; then
        die "unexpected amdgpu trace include layout in linux-$base"
    fi
    local -a make_args=()
    grep -q '^CONFIG_CC_IS_CLANG=y' "$headers/.config" && make_args+=(LLVM=1 LLVM_IAS=1)
    say "building amdgpu (several minutes)"
    make -C "$headers" "M=$tree/drivers/gpu/drm/amd/amdgpu" "${make_args[@]}" -j"$(nproc)" modules \
        > "$work/kernel-build.log" 2>&1 || { tail -40 "$work/kernel-build.log"; die "amdgpu build failed; full log: $work/kernel-build.log"; }
    local module="$tree/drivers/gpu/drm/amd/amdgpu/amdgpu.ko"
    [[ -f $module ]] || die "amdgpu.ko was not produced"
    [[ "$(modinfo -F vermagic "$module")" == "$KVER "* ]] || die "the built module does not match kernel $KVER"
    install -D -m 0644 "$module" "$stage/modules/$KVER/amdgpu.ko"
    # Debug information makes the module ~700 MB; the distribution's own is
    # stripped too. srcversion survives stripping, so the boot check still works.
    local strip_tool=strip
    [[ ${#make_args[@]} -gt 0 ]] && command -v llvm-strip >/dev/null 2>&1 && strip_tool=llvm-strip
    "$strip_tool" --strip-debug "$stage/modules/$KVER/amdgpu.ko"
    if [[ $kernel_only -eq 1 ]]; then
        # After a kernel update only the module has to follow; the private
        # RADV does not depend on the kernel version.
        printf 'VERSION=%s\nKVER=%s\nKERNEL_ONLY=1\n' "$version" "$KVER" > "$stage/build.env"
        say "kernel module rebuilt for $KVER: $stage"
        return 0
    fi

    say "Mesa half: RADV $MESA_VERSION with the compute-queue patch"
    local mesa_tar="$work/mesa-$MESA_VERSION.tar.xz"
    fetch "$MESA_URL" "$mesa_tar"
    printf '%s  %s\n' "$MESA_SHA256" "$mesa_tar" | sha256sum -c - >/dev/null || die "the Mesa tarball failed its checksum"
    local mesa_src="$work/mesa-$MESA_VERSION"
    rm -rf -- "$mesa_src" "$work/mesa-build"
    tar -C "$work" -xf "$mesa_tar"
    local name
    while IFS= read -r name; do
        [[ -z $name || $name == \#* ]] && continue
        patch -p1 -s -d "$mesa_src" < "$source/patches/mesa/$name"
        printf '   applied %s\n' "$name"
    done < "$source/patches/mesa/series"
    local prefix="$OPT_DIR/$version"
    meson setup "$work/mesa-build" "$mesa_src" \
        -Dvulkan-drivers=amd -Dgallium-drivers= -Dplatforms=x11,wayland \
        -Dglx=disabled -Dllvm=disabled -Dvideo-codecs= \
        -Dprefix="$prefix" -Dlibdir=lib -Dbuildtype=release \
        > "$work/mesa-setup.log" 2>&1 || { tail -30 "$work/mesa-setup.log"; die "Mesa configuration failed; log: $work/mesa-setup.log"; }
    ninja -C "$work/mesa-build" > "$work/mesa-build.log" 2>&1 || { tail -40 "$work/mesa-build.log"; die "Mesa build failed; log: $work/mesa-build.log"; }
    rm -rf -- "$stage/mesa-root"
    DESTDIR="$stage/mesa-root" ninja -C "$work/mesa-build" install >> "$work/mesa-build.log" 2>&1
    [[ -f $stage/mesa-root$prefix/lib/libvulkan_radeon.so ]] || die "the Mesa install is missing libvulkan_radeon.so"
    printf 'VERSION=%s\nKVER=%s\n' "$version" "$KVER" > "$stage/build.env"
    say "build complete: $stage"
}

# ------------------------------------------------------------- install (root)
write_managed() {
    local target=$1 mode=$2
    if [[ -e $target ]] && ! grep -Fq "$MARKER" "$target"; then
        die "refusing to replace $target: it was not written by BC250 Control Center"
    fi
    install -D -m "$mode" /dev/stdin "$target"
}

regenerate_initramfs() {
    say "regenerating the initramfs so amdgpu waits for the boot service"
    if command -v mkinitcpio >/dev/null 2>&1; then
        mkinitcpio -P
    elif command -v dracut >/dev/null 2>&1; then
        dracut --regenerate-all --force
    elif command -v update-initramfs >/dev/null 2>&1; then
        update-initramfs -u -k all
    else
        die "no supported initramfs tool (mkinitcpio, dracut, update-initramfs) was found"
    fi
}

install_release() {
    require_root
    local stage=""
    while (($#)); do
        case $1 in
            --stage) stage=$2; shift 2 ;;
            *) die "unknown install option $1" ;;
        esac
    done
    check_host
    [[ -r $stage/build.env ]] || die "no build found in $stage; run the build step first"
    local VERSION="" BUILT_KVER=""
    VERSION="$(sed -n 's/^VERSION=\([0-9A-Za-z._-]*\)$/\1/p' "$stage/build.env")"
    BUILT_KVER="$(sed -n 's/^KVER=\(.*\)$/\1/p' "$stage/build.env")"
    [[ -n $VERSION ]] || die "the build record is invalid"
    [[ $BUILT_KVER == "$KVER" ]] || die "the build is for kernel $BUILT_KVER but $KVER is running; build again"
    local module="$stage/modules/$KVER/amdgpu.ko"
    [[ "$(modinfo -F vermagic "$module")" == "$KVER "* ]] || die "the staged module does not match kernel $KVER"
    local prefix="$OPT_DIR/$VERSION" kernel_only=0
    grep -qx 'KERNEL_ONLY=1' "$stage/build.env" && kernel_only=1
    if [[ $kernel_only -eq 1 ]]; then
        [[ -f $prefix/lib/libvulkan_radeon.so ]] || die "a kernel-only rebuild needs the private RADV installed already"
    else
        [[ -f $stage/mesa-root$prefix/lib/libvulkan_radeon.so ]] || die "the staged Mesa is incomplete"
    fi

    say "installing the patched amdgpu for $KVER (the stock module is not touched)"
    install -D -m 0644 "$module" "$LIB_DIR/$KVER/amdgpu.ko"
    modinfo -F srcversion "$module" > "$LIB_DIR/$KVER/srcversion"
    # Modules built for kernels that are no longer installed only take room.
    local stale
    for stale in "$LIB_DIR"/*/; do
        stale="$(basename "$stale")"
        [[ -d /usr/lib/modules/$stale || $stale == "$KVER" ]] || rm -rf -- "${LIB_DIR:?}/$stale"
    done
    if [[ $kernel_only -eq 0 ]]; then
        say "installing the private RADV under $prefix"
        rm -rf -- "$prefix.new"
        mkdir -p "$OPT_DIR"
        cp -a "$stage/mesa-root$prefix" "$prefix.new"
        rm -rf -- "$prefix"
        mv -- "$prefix.new" "$prefix"
    fi

    write_managed "$LIB_DIR/bc250cc-gfx1013-load" 0755 <<'LOADER'
#!/bin/sh
# Managed by BC250 Control Center: GFX1013 compute-queue fix
# Decides, once the root file system is writable, whether this boot loads the
# patched amdgpu or the stock one, and keeps a record a failed boot can undo.
# BC250CC_TEST_ROOT exists only for the test suite; systemd never sets it.
set -u
R="${BC250CC_TEST_ROOT:-}"
PATH="${R:+$R/bin:}/usr/sbin:/usr/bin:/sbin:/bin"
LIB="$R/usr/lib/bc250cc-gfx1013"; CONF="$R/etc/bc250cc-gfx1013"
STATE="$R/var/lib/bc250cc-gfx1013"; RUN="$R/run/bc250cc-gfx1013"
KVER="$(uname -r)"; MODULE="$LIB/$KVER/amdgpu.ko"
mkdir -p "$RUN" "$STATE"
note() { printf '%s\n' "$1" > "$RUN/reason"; }
stock() {
    note "$1"; printf 'stock\n' > "$RUN/loaded"
    modprobe amdgpu
    exit 0
}
confirm() {
    [ "$(cat "$RUN/loaded" 2>/dev/null)" = patched ] || exit 0
    rm -f "$STATE/attempt"
    date -u +%Y-%m-%dT%H:%M:%SZ > "$STATE/last-good"
    exit 0
}
[ "${1:-load}" = confirm ] && confirm
if grep -q '^amdgpu ' "$R/proc/modules"; then
    printf 'early\n' > "$RUN/loaded"
    note "amdgpu was loaded before the boot service (initramfs or a MODULES entry); the fix could not be used"
    exit 0
fi
grep -qw 'bc250.gfx1013=0' "$R/proc/cmdline" && stock "switched off for this boot from the boot menu (bc250.gfx1013=0)"
[ -f "$CONF/enabled" ] || stock "installed but switched off"
[ -r "$MODULE" ] || stock "no patched module for kernel $KVER; build the fix again for this kernel"
if [ -e "$STATE/attempt" ]; then
    rm -f "$CONF/enabled"
    mv -f "$STATE/attempt" "$STATE/last-fallback"
    stock "the last boot with the fix did not finish; the fix was switched off"
fi
: > "$STATE/attempt"
sync
for dependency in $(modinfo -F depends "$MODULE" | tr ',' ' '); do
    modprobe "$dependency" || true
done
# insmod does not read modprobe.d or the kernel command line the way modprobe
# does: collect amdgpu options from both. Upstream's patched boot runs without
# the hardware scheduler (sched_policy=2) unless the user said otherwise.
params="$(modprobe -c 2>/dev/null | awk '$1 == "options" && $2 == "amdgpu" { for (i = 3; i <= NF; i++) print $i }' | tr '\n' ' ')"
for word in $(cat "$R/proc/cmdline"); do
    case "$word" in amdgpu.*=*) params="$params ${word#amdgpu.}" ;; esac
done
case " $params " in *" sched_policy="*) ;; *) params="$params sched_policy=2" ;; esac
# shellcheck disable=SC2086
if insmod "$MODULE" $params; then
    expected="$(cat "$LIB/$KVER/srcversion" 2>/dev/null)"
    actual="$(cat "$R/sys/module/amdgpu/srcversion" 2>/dev/null)"
    if [ -n "$expected" ] && [ -n "$actual" ] && [ "$expected" != "$actual" ]; then
        rm -f "$STATE/attempt"
        printf 'stock\n' > "$RUN/loaded"
        note "the loaded amdgpu is not the patched build"
        exit 0
    fi
    printf 'patched\n' > "$RUN/loaded"
    printf '%s\n' "$expected" > "$RUN/srcversion"
    note "patched amdgpu active"
    exit 0
fi
rm -f "$STATE/attempt"
stock "the patched module refused to load; the stock amdgpu is in use"
LOADER

    write_managed "$MODPROBE_CONF" 0644 <<CONF
$MARKER
# amdgpu is loaded by bc250cc-gfx1013-load.service once the root file system is
# writable, so a boot with the patched module can be recorded and undone.
# Removing the fix removes this file; "bc250.gfx1013=0" at the boot menu
# selects the stock module for one boot.
blacklist amdgpu
CONF

    write_managed "$LOAD_UNIT" 0644 <<UNIT
$MARKER
[Unit]
Description=BC-250 GFX1013 fix: load the matching amdgpu driver
DefaultDependencies=no
After=local-fs.target systemd-remount-fs.service systemd-udevd.service
Wants=systemd-udevd.service
Before=display-manager.service systemd-user-sessions.service plymouth-quit.service plymouth-quit-wait.service
ConditionPathExists=$LIB_DIR/bc250cc-gfx1013-load

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=$LIB_DIR/bc250cc-gfx1013-load load
TimeoutStartSec=120

[Install]
WantedBy=sysinit.target
UNIT

    write_managed "$CONFIRM_UNIT" 0644 <<UNIT
$MARKER
[Unit]
Description=BC-250 GFX1013 fix: mark this boot as healthy

[Service]
Type=oneshot
ExecStart=$LIB_DIR/bc250cc-gfx1013-load confirm
UNIT

    write_managed "$CONFIRM_TIMER" 0644 <<UNIT
$MARKER
[Unit]
Description=BC-250 GFX1013 fix: mark the boot healthy after three minutes

[Timer]
OnBootSec=3min
AccuracySec=10s

[Install]
WantedBy=timers.target
UNIT

    write_managed "$GENERATOR" 0755 <<GEN
#!/bin/sh
$MARKER
# Offer the private RADV only while the patched amdgpu is the loaded one:
# upstream warns that this Mesa on a stock kernel can hang the GPU.
[ "\$(cat $RUN_DIR/loaded 2>/dev/null)" = patched ] || exit 0
[ "\$(cat $RUN_DIR/srcversion 2>/dev/null)" = "\$(cat /sys/module/amdgpu/srcversion 2>/dev/null)" ] || exit 0
. $CONF_DIR/active.env 2>/dev/null || exit 0
case "\${VERSION:-}" in *[!0-9A-Za-z._-]*|'') exit 0 ;; esac
icd="$OPT_DIR/\$VERSION/share/vulkan/icd.d/radeon_icd.x86_64.json"
[ -r "\$icd" ] || exit 0
files="\$icd"
# 32-bit games keep the system RADV: the private build is 64-bit only.
for other in /usr/share/vulkan/icd.d/radeon_icd.i686.json /usr/share/vulkan/icd.d/radeon_icd.i386.json; do
    [ -r "\$other" ] && files="\$files:\$other"
done
echo "VK_DRIVER_FILES=\$files"
echo "VK_ICD_FILENAMES=\$files"
GEN

    install -d -m 0755 "$CONF_DIR" "$STATE_DIR"
    printf '%s\nVERSION=%s\nKVER=%s\n' "$MARKER" "$VERSION" "$KVER" > "$CONF_DIR/active.env"
    : > "$CONF_DIR/enabled"
    rm -f -- "$STATE_DIR/attempt"
    regenerate_initramfs
    systemctl daemon-reload
    systemctl enable bc250cc-gfx1013-load.service bc250cc-gfx1013-confirm.timer
    say "installed. Reboot to use the fix."
    echo "If the machine does not reach the desktop, the next boot uses the stock driver and switches the fix off by itself."
    echo "To skip it for one boot, press e at the boot menu and add: bc250.gfx1013=0"
    echo "BC250_REBOOT_REQUIRED=1"
}

enable_fix() {
    require_root
    [[ -f $CONF_DIR/active.env ]] || die "the fix is not installed"
    install -d -m 0755 "$CONF_DIR"
    : > "$CONF_DIR/enabled"
    rm -f -- "$STATE_DIR/attempt"
    say "switched on; it takes effect at the next boot"
    echo "BC250_REBOOT_REQUIRED=1"
}

disable_fix() {
    require_root
    rm -f -- "$CONF_DIR/enabled" "$STATE_DIR/attempt"
    say "switched off; the stock amdgpu and system Mesa are used from the next boot"
    echo "BC250_REBOOT_REQUIRED=1"
}

remove_managed() {
    local target=$1
    [[ -e $target ]] || return 0
    grep -Fq "$MARKER" "$target" || die "refusing to remove $target: it was not written by BC250 Control Center"
    rm -f -- "$target"
}

uninstall_release() {
    require_root
    systemctl disable bc250cc-gfx1013-load.service bc250cc-gfx1013-confirm.timer 2>/dev/null || true
    remove_managed "$LOAD_UNIT"
    remove_managed "$CONFIRM_UNIT"
    remove_managed "$CONFIRM_TIMER"
    remove_managed "$GENERATOR"
    remove_managed "$MODPROBE_CONF"
    remove_managed "$LIB_DIR/bc250cc-gfx1013-load"
    rm -rf -- "$LIB_DIR" "$OPT_DIR" "$CONF_DIR" "$STATE_DIR"
    systemctl daemon-reload
    regenerate_initramfs
    say "removed. The stock amdgpu and system Mesa are used from the next boot."
    echo "BC250_REBOOT_REQUIRED=1"
}

status() {
    echo "kernel=$KVER"
    echo "family=$(family)"
    echo "installed=$([[ -f $CONF_DIR/active.env ]] && echo yes || echo no)"
    echo "enabled=$([[ -f $CONF_DIR/enabled ]] && echo yes || echo no)"
    echo "module_for_kernel=$([[ -r $LIB_DIR/$KVER/amdgpu.ko ]] && echo yes || echo no)"
    echo "loaded=$(cat "$RUN_DIR/loaded" 2>/dev/null || echo unknown)"
    echo "reason=$(cat "$RUN_DIR/reason" 2>/dev/null || true)"
    echo "last_fallback=$([[ -e $STATE_DIR/last-fallback ]] && echo yes || echo no)"
    echo "last_good=$(cat "$STATE_DIR/last-good" 2>/dev/null || true)"
}

case ${1:-} in
    deps) shift; deps "$@" ;;
    build) shift; build "$@" ;;
    install) shift; install_release "$@" ;;
    enable) enable_fix ;;
    disable) disable_fix ;;
    uninstall) uninstall_release ;;
    status) status ;;
    *) sed -n '2,40p' "$0" >&2; exit 64 ;;
esac
