#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
#
# BC-250 async compute for Arch-family systems (Arch, CachyOS, Manjaro...):
# RADV with the GFX1013 compute-queue patch, built from source and installed
# as a second Vulkan driver beside the system Mesa -- the approach of
# tri3gubki-ops/bc250-async-compute-bazzite, whose patches and tests this
# builds from a reviewed commit.
#
# Why no kernel module here: that release runs the patched RADV on Bazzite's
# OGC 7.2 kernel with a stock amdgpu. The amdgpu of linux 7.2 is the same on
# CachyOS and on OGC (gmc_v10_0.c, gfx_v10_0.c, amdgpu_amdkfd.c, the VM, ring
# and CS code are byte-identical in 7.2.7), so kernel 7.2 or newer is
# required and nothing else. Older kernels keep DryhoppedIPA's kernel-side
# fix (bc250-gfx1013-source.sh): the patched RADV on them can hang the GPU.
#
# Nothing replaces the system Mesa. The driver lives in
# /opt/bc250cc-radv/<mesa version>; a user environment generator offers it to
# desktop sessions only while it is switched on, the running kernel is 7.2 or
# newer and amdgpu is loaded. "bc250.async=0" on the kernel command line
# (press e in the boot menu) keeps it out of that boot's sessions.
#
# usage:
#   bc250-async-compute-radv.sh deps                 install build tools (sudo)
#   bc250-async-compute-radv.sh build --source DIR   build as the user
#   sudo bc250-async-compute-radv.sh install --stage DIR
#   sudo bc250-async-compute-radv.sh enable|disable|uninstall
#   bc250-async-compute-radv.sh status

set -Eeuo pipefail

MESA_VERSION=26.2.3
# From Mesa's release notes and Arch's own mesa PKGBUILD; both list this sum.
MESA_SHA256=1628058a8d2c0615975de5a15ab7bbb9638c50000b5bed9456ff423ea034a81f
MESA_URL="https://archive.mesa3d.org/mesa-${MESA_VERSION}.tar.xz"
PATCHES=(0001-radv-ac-gfx1013-expose-ace-compute-queue.patch 0002-radv-ac-optional-bc250-ip-debug-print.patch)
MARKER="# Managed by BC250 Control Center: RADV async compute"
PREFIX_ROOT=/opt/bc250cc-radv
LIB_DIR=/usr/lib/bc250cc-radv
CONF_DIR=/etc/bc250cc-radv
HELPER=/usr/local/bin/bc250cc-async-compute
GENERATOR=/usr/lib/systemd/user-environment-generators/61-bc250cc-radv
MIN_MAJOR=7
MIN_MINOR=2
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
        arch|cachyos|endeavouros|manjaro|garuda|artix) echo arch ;;
        *) case "$like" in *" arch "*) echo arch ;; *) echo other ;; esac ;;
    esac
}

kernel_supported() {
    local release="${1%%-*}" major minor
    major="${release%%.*}"; minor="${release#*.}"; minor="${minor%%.*}"
    [[ $major =~ ^[0-9]+$ && $minor =~ ^[0-9]+$ ]] || return 1
    (( major > MIN_MAJOR || (major == MIN_MAJOR && minor >= MIN_MINOR) ))
}

check_host() {
    case "$(family)" in
        bazzite) die "Bazzite keeps its own reviewed async-compute release; this build is not for it." ;;
        steamos) die "SteamOS uses its own reviewed toolkit; this build is not for it." ;;
        fedora) die "Fedora is covered by the upstream Bazzite/Fedora release and DryhoppedIPA's installer." ;;
        other) die "this build covers Arch-family distributions (Arch, CachyOS, Manjaro, EndeavourOS)." ;;
    esac
    [[ -e /run/ostree-booted ]] && die "image-based systems are not covered by this build."
    [[ "$(uname -m)" == x86_64 ]] || die "x86_64 only."
    local found=0 device
    for device in /sys/bus/pci/devices/*; do
        [[ -r $device/vendor && -r $device/device ]] || continue
        [[ $(<"$device/vendor") == 0x1002 && $(<"$device/device") == 0x13fe ]] && { found=1; break; }
    done
    [[ $found -eq 1 ]] || die "AMD BC-250 (PCI 1002:13fe) was not found."
    case "$KVER" in
        *bc250*) die "this BC-250 kernel ($KVER) ships its own matching Mesa route; use that instead." ;;
    esac
    kernel_supported "$KVER" || die "kernel $KVER is older than ${MIN_MAJOR}.${MIN_MINOR}. On it the patched RADV needs DryhoppedIPA's kernel-side fix; use the GFX1013 source build instead, or update the kernel."
}

# ---------------------------------------------------------------- deps (user)
deps() {
    check_host
    local -a wanted=(base-devel curl patch git meson ninja python-mako python-yaml python-packaging
        glslang libdrm wayland wayland-protocols libxcb libx11 libxrandr libxshmfence
        expat zlib zstd spirv-tools vulkan-headers vulkan-icd-loader shaderc vulkan-tools pciutils)
    # pacman -T honours "provides": CachyOS ships zlib-ng-compat for zlib, and
    # naming zlib outright made pacman try to replace it.
    local -a missing=()
    mapfile -t missing < <(pacman -T "${wanted[@]}" || true)
    if ((${#missing[@]})); then
        say "installing ${missing[*]}"
        sudo pacman -S --needed --noconfirm "${missing[@]}"
    fi
    say "build tools ready"
}

fetch() {
    local url=$1 destination=$2
    [[ -s $destination ]] && return 0
    printf '   downloading %s\n' "${url##*/}"
    COLUMNS=60 curl -fL --retry 3 --connect-timeout 20 --progress-bar -o "$destination.part" "$url"
    mv -- "$destination.part" "$destination"
}

# --------------------------------------------------------------- build (user)
build() {
    local source="" stage=""
    while (($#)); do
        case $1 in
            --source) source=$2; shift 2 ;;
            --stage) stage=$2; shift 2 ;;
            *) die "unknown build option $1" ;;
        esac
    done
    [[ ${EUID} -ne 0 ]] || die "build as your own user, not as root."
    check_host
    local patch
    for patch in "${PATCHES[@]}"; do
        [[ -f $source/patches/$patch ]] || die "upstream checkout is incomplete: $source/patches/$patch"
    done
    [[ -f $source/test/bc250-ace-test.c && -f $source/test/bc250-ace-soak.c && -f $source/test/ace.comp ]] \
        || die "upstream checkout has no test sources: $source/test"
    stage="${stage:-${XDG_CACHE_HOME:-$HOME/.cache}/bc250-control-center/radv-async/stage}"
    local work="$stage/work" prefix="$PREFIX_ROOT/$MESA_VERSION"
    if [[ -r $stage/build.env ]] && grep -qx "VERSION=$MESA_VERSION" "$stage/build.env" \
        && [[ -f $stage/root$prefix/lib/libvulkan_radeon.so && -x $stage/tests/bc250-ace-test ]]; then
        # Kept: when only the privileged install failed, running again goes
        # straight to installing. The driver does not depend on the kernel.
        say "already built: $stage"
        return 0
    fi
    mkdir -p "$work"

    say "RADV $MESA_VERSION with the GFX1013 compute-queue patch"
    local tarball="$work/mesa-$MESA_VERSION.tar.xz"
    fetch "$MESA_URL" "$tarball"
    printf '%s  %s\n' "$MESA_SHA256" "$tarball" | sha256sum -c - >/dev/null || {
        rm -f -- "$tarball"
        die "mesa-$MESA_VERSION.tar.xz failed its checksum"
    }
    local tree="$work/mesa-$MESA_VERSION"
    rm -rf -- "$tree" "$work/build"
    tar -C "$work" -xf "$tarball"
    for patch in "${PATCHES[@]}"; do
        patch -p1 -s --dry-run -d "$tree" < "$source/patches/$patch" \
            || die "$patch does not apply to mesa-$MESA_VERSION"
        patch -p1 -s -d "$tree" < "$source/patches/$patch"
        printf '   applied %s\n' "$patch"
    done
    # The same configuration as the Bazzite release: Vulkan RADV only, ACO
    # instead of LLVM, and a prefix that must equal the final path, because
    # Mesa writes it into the ICD manifest and the drirc directory.
    meson setup "$work/build" "$tree" --prefix="$prefix" --libdir=lib --buildtype=release \
        -Dvulkan-drivers=amd -Dgallium-drivers= -Dplatforms=wayland,x11 \
        -Dglx=disabled -Degl=disabled -Dgbm=disabled -Dopengl=false \
        -Dgles1=disabled -Dgles2=disabled -Dllvm=disabled \
        -Dvideo-codecs= -Dvulkan-layers= -Dtools= \
        > "$work/setup.log" 2>&1 || { tail -40 "$work/setup.log"; die "Mesa configuration failed; log: $work/setup.log"; }
    say "building RADV (10-20 minutes on a BC-250)"
    ninja -C "$work/build" > "$work/build.log" 2>&1 || { tail -40 "$work/build.log"; die "Mesa build failed; log: $work/build.log"; }
    rm -rf -- "$stage/root"
    DESTDIR="$stage/root" ninja -C "$work/build" install > "$work/install.log" 2>&1 \
        || { tail -20 "$work/install.log"; die "Mesa staging failed; log: $work/install.log"; }
    local library="$stage/root$prefix/lib/libvulkan_radeon.so"
    local manifest="$stage/root$prefix/share/vulkan/icd.d/radeon_icd.x86_64.json"
    [[ -f $library ]] || die "the build has no libvulkan_radeon.so"
    grep -Fq "\"$prefix/lib/libvulkan_radeon.so\"" "$manifest" || die "the ICD manifest does not point at $prefix"

    say "verification tests (upstream bc250-ace-test and bc250-ace-soak)"
    local tests="$work/tests"
    rm -rf -- "$tests" "$stage/tests"
    cp -a "$source/test" "$tests"
    glslc -O --target-env=vulkan1.1 -fshader-stage=compute "$tests/ace.comp" -o "$tests/ace.spv"
    python3 - "$tests/ace.spv" "$tests/ace_comp_spv.h" <<'PY'
import sys
data = open(sys.argv[1], "rb").read()
assert len(data) % 4 == 0
words = ", ".join("0x%08x" % int.from_bytes(data[i:i + 4], "little") for i in range(0, len(data), 4))
open(sys.argv[2], "w").write(
    "/* generated from ace.comp by glslc -- do not edit */\n"
    "#include <stdint.h>\n"
    "static const uint32_t ace_comp_spv[] = {%s};\n" % words)
PY
    mkdir -p "$stage/tests"
    gcc -O2 -Wall -o "$stage/tests/bc250-ace-test" "$tests/bc250-ace-test.c" -lvulkan
    gcc -O2 -Wall -o "$stage/tests/bc250-ace-soak" "$tests/bc250-ace-soak.c" -lvulkan
    printf 'VERSION=%s\nUPSTREAM=%s\n' "$MESA_VERSION" "$(git -C "$source" rev-parse HEAD 2>/dev/null || echo unknown)" > "$stage/build.env"
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
    local version upstream prefix
    version="$(sed -n 's/^VERSION=\([0-9A-Za-z._-]*\)$/\1/p' "$stage/build.env")"
    upstream="$(sed -n 's/^UPSTREAM=\([0-9a-f]*\)$/\1/p' "$stage/build.env")"
    [[ $version == "$MESA_VERSION" ]] || die "the staged build is not RADV $MESA_VERSION; build again"
    prefix="$PREFIX_ROOT/$version"
    [[ -f $stage/root$prefix/lib/libvulkan_radeon.so ]] || die "the staged driver is incomplete"
    local missing
    missing="$(ldd "$stage/root$prefix/lib/libvulkan_radeon.so" 2>/dev/null | awk '/not found/ {print $1}' | tr '\n' ' ')"
    [[ -z $missing ]] || die "the driver cannot resolve: $missing"

    say "installing RADV $version under $prefix (the system Mesa is not touched)"
    rm -rf -- "$prefix.new"
    mkdir -p "$PREFIX_ROOT"
    cp -a "$stage/root$prefix" "$prefix.new"
    # Mesa reads game profiles from its own prefix; point it at the system's
    # so they follow every Mesa update instead of freezing at build time.
    rm -rf -- "$prefix.new/share/drirc.d"
    if [[ -d /usr/share/drirc.d ]]; then
        ln -sfn /usr/share/drirc.d "$prefix.new/share/drirc.d"
    fi
    install -d -m 0755 "$prefix.new/etc"
    ln -sfn /etc/drirc "$prefix.new/etc/drirc"
    rm -rf -- "$prefix"
    mv -- "$prefix.new" "$prefix"
    local old
    for old in "$PREFIX_ROOT"/*/; do
        old="$(basename "$old")"
        [[ $old == "$version" ]] || rm -rf -- "${PREFIX_ROOT:?}/$old"
    done
    install -D -m 0755 "$stage/tests/bc250-ace-test" "$LIB_DIR/bc250-ace-test"
    install -D -m 0755 "$stage/tests/bc250-ace-soak" "$LIB_DIR/bc250-ace-soak"

    write_managed "$HELPER" 0755 <<'TOOL'
#!/usr/bin/env bash
# Managed by BC250 Control Center: RADV async compute
# Checks the install, runs the verification tests, and starts a single game
# with the patched RADV while the system-wide switch is off.
set -uo pipefail
CONF=/etc/bc250cc-radv
# shellcheck disable=SC1091
. "$CONF/active.env" 2>/dev/null || { echo "BC-250 async compute is not installed." >&2; exit 1; }
PREFIX="/opt/bc250cc-radv/${VERSION:-}"
ICD64="$PREFIX/share/vulkan/icd.d/radeon_icd.x86_64.json"
SYSTEM_ICD64=/usr/share/vulkan/icd.d/radeon_icd.x86_64.json
extras() {
    local other
    # 32-bit games and Proton's helpers keep the system RADV, and llvmpipe
    # stays listed: VK_DRIVER_FILES replaces the loader's whole search.
    for other in /usr/share/vulkan/icd.d/radeon_icd.i686.json /usr/share/vulkan/icd.d/lvp_icd.x86_64.json; do
        [ -r "$other" ] && printf ':%s' "$other"
    done
}
driver_files() { printf '%s%s' "$ICD64" "$(extras)"; }
system_files() { printf '%s%s' "$SYSTEM_ICD64" "$(extras)"; }
ace_families() {
    local count=0 flags
    while IFS= read -r flags; do
        case "$flags" in *QUEUE_COMPUTE_BIT*) case "$flags" in *QUEUE_GRAPHICS_BIT*) ;; *) count=$((count + 1)) ;; esac ;; esac
    done < <(env -u VK_ICD_FILENAMES "VK_DRIVER_FILES=$1" vulkaninfo 2>/dev/null | grep -E 'queueFlags' | sed 's/.*= //')
    printf '%d' "$count"
}
case "${1:-status}" in
    status)
        echo "BC-250 async compute (RADV ${VERSION:-?}, built from tri3gubki-ops' patches)"
        echo "  kernel       : $(uname -r)"
        echo "  system Mesa  : $(pacman -Q vulkan-radeon 2>/dev/null | awk '{print $2}')"
        if [ -f "$PREFIX/lib/libvulkan_radeon.so" ]; then echo "  driver       : $PREFIX"; else echo "  driver       : MISSING at $PREFIX"; exit 1; fi
        missing=$(ldd "$PREFIX/lib/libvulkan_radeon.so" 2>/dev/null | awk '/not found/ {print $1}' | tr '\n' ' ')
        [ -z "$missing" ] && echo "  libraries    : all resolve" || echo "  libraries    : UNRESOLVED $missing"
        echo "  dedicated compute (ACE) queue families:"
        echo "    system driver : $(ace_families "$(system_files)")"
        echo "    this driver   : $(ace_families "$(driver_files)")"
        if [ -f "$CONF/enabled" ]; then echo "  system-wide  : on (every new session uses it)"; else echo "  system-wide  : off (use: bc250cc-async-compute run %command%)"; fi
        case ":${VK_DRIVER_FILES:-}:" in *":$ICD64:"*) echo "  this session : uses the patched RADV" ;; *) echo "  this session : system driver (log out and back in after switching on)" ;; esac
        ;;
    env) printf 'VK_DRIVER_FILES=%s\n' "$(driver_files)" ;;
    steam) echo "bc250cc-async-compute run %command%" ;;
    run)
        shift
        [ "$#" -gt 0 ] || { echo "usage: bc250cc-async-compute run <command...>" >&2; exit 2; }
        files="$(driver_files)"
        exec env VK_DRIVER_FILES="$files" VK_ICD_FILENAMES="$files" "$@"
        ;;
    test) VK_DRIVER_FILES="$(driver_files)" exec /usr/lib/bc250cc-radv/bc250-ace-test ;;
    soak)
        echo "Sustained GPU work for ${2:-300} seconds; the desktop may feel slower meanwhile."
        VK_DRIVER_FILES="$(driver_files)" exec /usr/lib/bc250cc-radv/bc250-ace-soak "${2:-300}"
        ;;
    *) echo "usage: bc250cc-async-compute status|env|steam|run <command...>|test|soak [seconds]" >&2; exit 2 ;;
esac
TOOL

    write_managed "$GENERATOR" 0755 <<GEN
#!/bin/sh
$MARKER
# Offer the patched RADV to desktop sessions only while it is switched on, the
# running kernel is ${MIN_MAJOR}.${MIN_MINOR} or newer and amdgpu is loaded.
# BC250CC_TEST_ROOT and BC250CC_TEST_KERNEL exist only for the test suite.
R="\${BC250CC_TEST_ROOT:-}"
[ -f "\$R$CONF_DIR/enabled" ] || exit 0
grep -qw 'bc250.async=0' "\$R/proc/cmdline" 2>/dev/null && exit 0
[ -d "\$R/sys/module/amdgpu" ] || exit 0
# DryhoppedIPA's kernel-side fix brings its own RADV while its module is loaded.
[ "\$(cat "\$R/run/bc250cc-gfx1013/loaded" 2>/dev/null)" = patched ] && exit 0
release="\${BC250CC_TEST_KERNEL:-\$(uname -r)}"
major=\${release%%.*}; rest=\${release#*.}; minor=\${rest%%[!0-9]*}
case "\$major:\$minor" in *[!0-9:]*|:*|*:) exit 0 ;; esac
[ "\$major" -gt $MIN_MAJOR ] || { [ "\$major" -eq $MIN_MAJOR ] && [ "\$minor" -ge $MIN_MINOR ]; } || exit 0
. "\$R$CONF_DIR/active.env" 2>/dev/null || exit 0
case "\${VERSION:-}" in *[!0-9A-Za-z._-]*|'') exit 0 ;; esac
icd="$PREFIX_ROOT/\$VERSION/share/vulkan/icd.d/radeon_icd.x86_64.json"
[ -r "\$R\$icd" ] || exit 0
files="\$icd"
for other in /usr/share/vulkan/icd.d/radeon_icd.i686.json /usr/share/vulkan/icd.d/lvp_icd.x86_64.json; do
    [ -r "\$R\$other" ] && files="\$files:\$other"
done
echo "VK_DRIVER_FILES=\$files"
echo "VK_ICD_FILENAMES=\$files"
GEN

    install -d -m 0755 "$CONF_DIR"
    printf '%s\nVERSION=%s\nUPSTREAM=%s\n' "$MARKER" "$version" "${upstream:-unknown}" > "$CONF_DIR/active.env"
    : > "$CONF_DIR/enabled"
    say "installed and switched on. Log out and back in; games need no launch options."
    echo "Check it with: bc250cc-async-compute status"
    echo "If the desktop does not come back after logging in, press e at the boot menu and add: bc250.async=0"
    echo "BC250_RELOGIN_REQUIRED=1"
}

enable_driver() {
    require_root
    [[ -f $CONF_DIR/active.env ]] || die "async compute is not installed"
    : > "$CONF_DIR/enabled"
    say "switched on; log out and back in to use it"
    echo "BC250_RELOGIN_REQUIRED=1"
}

disable_driver() {
    require_root
    rm -f -- "$CONF_DIR/enabled"
    say "switched off; sessions started from now on use the system driver"
    echo "BC250_RELOGIN_REQUIRED=1"
}

remove_managed() {
    local target=$1
    [[ -e $target ]] || return 0
    grep -Fq "$MARKER" "$target" || die "refusing to remove $target: it was not written by BC250 Control Center"
    rm -f -- "$target"
}

uninstall_release() {
    require_root
    remove_managed "$GENERATOR"
    remove_managed "$HELPER"
    rm -rf -- "$LIB_DIR" "$PREFIX_ROOT" "$CONF_DIR"
    say "removed. Sessions started from now on use the system driver."
    echo "BC250_RELOGIN_REQUIRED=1"
}

status() {
    local version=""
    [[ -r $CONF_DIR/active.env ]] && version="$(sed -n 's/^VERSION=//p' "$CONF_DIR/active.env")"
    echo "kernel=$KVER"
    echo "family=$(family)"
    echo "kernel_supported=$(kernel_supported "$KVER" && echo yes || echo no)"
    echo "installed=$([[ -n $version ]] && echo yes || echo no)"
    echo "version=$version"
    echo "enabled=$([[ -f $CONF_DIR/enabled ]] && echo yes || echo no)"
    case ":${VK_DRIVER_FILES:-}:" in
        *":$PREFIX_ROOT/"*) echo "session=patched" ;;
        *) echo "session=system" ;;
    esac
    if [[ -x $HELPER ]]; then
        echo
        "$HELPER" status || true
    fi
}

case ${1:-} in
    deps) shift; deps "$@" ;;
    build) shift; build "$@" ;;
    install) shift; install_release "$@" ;;
    enable) enable_driver ;;
    disable) disable_driver ;;
    uninstall) uninstall_release ;;
    status) status ;;
    *) sed -n '2,29p' "$0" >&2; exit 64 ;;
esac
