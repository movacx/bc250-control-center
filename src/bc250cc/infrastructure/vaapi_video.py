"""Hardware video for the BC-250: simpmix's VA-API driver, built and checked.

The BC-250 has no working video block (VCN), so radeonsi's VA-API driver
fails to start and every program falls back to software video.
simpmix/bc250-encoding-decoding-fix is a VA-API driver of its own: H.264
encodes on the GPU's compute units, HEVC mostly on the CPU, and both decode
on the CPU, behind the standard VA-API interface (Sunshine, OBS, Steam
Remote Play, ffmpeg, browsers).

Upstream is GPL-3.0-only, so none of its code is in this application. This
module builds its source at one reviewed commit, the way
keyboardspecialist/bc250-steamos (public domain) does on SteamOS:

* The archive is downloaded and checked against the pinned SHA-256.
* It is built in a Fedora container (Podman), the same on every
  distribution, without libx264: that keeps the driver free of a distro's
  x264 ABI (upstream's own release binary only loads on Ubuntu 24.04). Its
  HEVC path then uses the driver's own encoder. The result needs glibc 2.38.
* Before anything is switched on, the built driver must start through libva
  and offer H.264 and HEVC encode and decode (scripts/system/bc250-vaapi-probe.py).
* It is installed to /var/lib/bc250-control-center/vaapi, which every
  supported system keeps across updates, and switched on by two files that
  name it: /etc/environment.d (desktop and Game Mode sessions) and a late
  /etc/profile.d script (SteamOS's own libva.sh sets radeonsi). On SteamOS
  both are listed in /etc/atomic-update.conf.d.

A 32-bit companion can be added where there is a 32-bit userland (SteamOS, and
Arch with multilib): Steam's streaming client for Remote Play is a 32-bit
program and falls back to software video without it. It is built in the same
container, installed beside the 64-bit driver in ``dri32`` and found through
the same search path, where libva skips the file of the wrong class. SteamOS
needs the signed lib32 packages for it, which an update removes: the card says
so and adds the driver again without rebuilding it.

Flatpak apps (GPU Screen Recorder, OBS, Steam) run in a sandbox that cannot
open that folder and carries only radeonsi, so they list H.264 as "not
available on your system". A per-user Flatpak override (read-only access to
the folder, plus the two libva variables) lets them use it; it is applied with
the install and can be added or removed on its own
(scripts/system/bc250-vaapi-flatpak.py).

What upstream's installers also do is left out on purpose: the boot unit
that remounts /usr every boot and replaces radeonsi's driver file (it hung a
board's boot once, by its own account), the DKMS audio module (the BC-250
kernels already carry the audio fix) and OpenMP variables for every program
(the driver sets its own when it loads).
"""

from __future__ import annotations

import os
import platform
import shlex
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import Mapping

from . import container_network
from .accessories._shared import download_and_verify
from .steamos_readonly import (
    STEAMOS_PACMAN_INSTALL,
    STEAMOS_PASSWORD_GUARD,
    STEAMOS_VAR_SPACE_GUARD,
)

UPSTREAM = "https://github.com/simpmix/bc250-encoding-decoding-fix"
VERSION = "0.5.2"
REVIEWED_COMMIT = "b8de980fa58806ba34f3cdc91192584fe9e433d5"
ARCHIVE_SHA256 = "5de910533c508f5625dd4138f459db9165713896ce9dca823c8d09b4781ae598"
ARCHIVE_URL = f"https://codeload.github.com/simpmix/bc250-encoding-decoding-fix/tar.gz/{REVIEWED_COMMIT}"
BUILD_IMAGE = "registry.fedoraproject.org/fedora:44"
BUILD_PACKAGES = "gcc gcc-c++ cmake make pkgconf libva-devel libdrm-devel vulkan-loader-devel glslang"

RUNTIME = Path("/var/lib/bc250-control-center/vaapi")
DRIVER = RUNTIME / "bc250_drv_video.so"
#: A program that clears LIBVA_DRIVER_NAME lets libva choose the driver for the
#: GPU, which for AMD is radeonsi, and libva then looks for this file name and
#: never for ours. GPU Screen Recorder does exactly that, so it listed H.264 as
#: not available with the driver installed. The alias is a link beside the
#: driver, so the shaders it finds next to itself are the same ones.
ALIAS = RUNTIME / "radeonsi_drv_video.so"
MANIFEST = RUNTIME / "VERSION"
ENV_FILE = Path("/etc/environment.d/90-bc250-control-center-vaapi.conf")
PROFILE_FILE = Path("/etc/profile.d/zz-bc250-control-center-vaapi.sh")
KEEP_FILE = Path("/etc/atomic-update.conf.d/bc250-control-center-vaapi.conf")
MARKER = "# Managed by BC250 Control Center: VA-API video driver"
#: The freshly built copy, inside the install workflow's private stage.
BUILT = '"$bc250_stage/out"'
PROBE = Path(__file__).resolve().parents[3] / "scripts" / "system" / "bc250-vaapi-probe.py"
FLATPAK_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "system" / "bc250-vaapi-flatpak.py"
PROBE32_SOURCE = Path(__file__).resolve().parents[3] / "scripts" / "system" / "bc250-vaapi-probe.c"
#: Where a 32-bit userland exists to load a 32-bit driver: Valve's image, and Arch with [multilib].
MULTILIB_FAMILIES = frozenset({"steamos", "arch", "manjaro", "cachyos"})
LIB32_PACKAGES = (
    "lib32-glibc", "lib32-gcc-libs", "lib32-libva", "lib32-libdrm",
    "lib32-vulkan-icd-loader", "lib32-vulkan-radeon",
)
#: What the 32-bit driver loads at run time; a SteamOS update removes them with the rest of /usr.
LIB32_FILES = tuple(Path("/usr/lib32") / name for name in (
    "libc.so.6", "libgomp.so.1", "libva.so.2", "libva-drm.so.2", "libdrm.so.2", "libvulkan.so.1",
))
BUILD_PACKAGES32 = (
    f"{BUILD_PACKAGES} glibc-devel.i686 libgcc.i686 libstdc++-devel.i686 libva-devel.i686 "
    "libdrm-devel.i686 vulkan-loader-devel.i686 libgomp.i686 libatomic libatomic.i686 binutils"
)
#: Disk the lib32 packages and the second driver take on SteamOS's small /var and /usr.
VAR_SPACE_MB = 60
#: Where the distributions keep their own VA-API drivers, after ours, so a
#: program that asks for radeonsi by name still finds it.
SYSTEM_DRIVER_DIRS = (
    "/usr/lib64/dri", "/usr/lib/x86_64-linux-gnu/dri", "/usr/lib/dri",
    "/usr/lib32/dri", "/usr/lib/i386-linux-gnu/dri",
)

#: The same driver switched on by another installer: upstream's own scripts
#: and boot unit, or keyboardspecialist's SteamOS toolkit. Never both.
FOREIGN_FILES = (
    Path("/etc/environment.d/99-bc250.conf"),
    Path("/etc/profile.d/bc250.sh"),
    Path("/etc/environment.d/90-bc250-video-codec.conf"),
    Path("/etc/profile.d/zz-bc250-video-codec.sh"),
    Path("/etc/systemd/system/bc250-vaapi-boot-redirect.service"),
    Path("/etc/bc250-vaapi-redirect-apply.sh"),
)
#: linux-cachyos-rc-bc250's experimental hardware video block brings radeonsi
#: back; this driver would then hide the real one.
HARDWARE_VCN_ARGUMENT = "amdgpu.bc250_vcn=1"
MUTABLE_FAMILIES = {"arch", "manjaro", "cachyos", "fedora", "debian", "ubuntu"}
IMAGE_FAMILIES = {"bazzite", "steamos"}
PODMAN_PACKAGES = {
    "arch": "sudo pacman -S --needed --noconfirm podman",
    "manjaro": "sudo pacman -S --needed --noconfirm podman",
    "cachyos": "sudo pacman -S --needed --noconfirm podman",
    "fedora": "sudo dnf install -y podman",
    "debian": "sudo apt-get install -y podman",
    "ubuntu": "sudo apt-get install -y podman",
}
MIN_GLIBC = (2, 38)
ACTIONS = frozenset({"install", "install32", "test", "uninstall", "flatpak", "flatpak-remove"})


def driver32_dir() -> Path:
    return RUNTIME / "dri32"


def driver32() -> Path:
    return driver32_dir() / "bc250_drv_video.so"


def vaapi_supported32(family: str) -> tuple[bool, str]:
    """Whether a 32-bit companion can be offered here, and why not."""
    if str(family or "").strip().lower() not in MULTILIB_FAMILIES:
        return False, "The 32-bit driver is offered on SteamOS, Arch, CachyOS and Manjaro."
    return True, ""


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _glibc() -> tuple[int, int] | None:
    try:
        text = os.confstr("CS_GNU_LIBC_VERSION") or ""
    except (ValueError, OSError):
        return None
    try:
        major, minor = text.split()[-1].split(".")[:2]
        return int(major), int(minor)
    except (IndexError, ValueError):
        return None


def _bc250(root: Path = Path("/sys/bus/pci/devices")) -> bool:
    for device in root.glob("*"):
        if _read(device / "vendor").strip() == "0x1002" and _read(device / "device").strip() == "0x13fe":
            return True
    return False


def vaapi_supported(
    *, family: str, machine: str | None = None, glibc: tuple[int, int] | None = None,
    bc250: bool | None = None,
) -> tuple[bool, str]:
    """Whether this system can build and run the driver, and why not."""
    family = str(family or "").strip().lower()
    machine = machine or platform.machine()
    glibc = glibc if glibc is not None else _glibc()
    if not (bc250 if bc250 is not None else _bc250()):
        return False, "AMD BC-250 hardware was not detected."
    if machine != "x86_64":
        return False, "The driver is built for x86_64."
    if family not in MUTABLE_FAMILIES | IMAGE_FAMILIES:
        return False, "Offered on SteamOS, Bazzite, Arch, CachyOS, Manjaro, Fedora, Debian and Ubuntu."
    if glibc is not None and glibc < MIN_GLIBC:
        return False, "The driver needs glibc 2.38 or newer; this system is older."
    return True, ""


def _state32(family: str, ours: bool, lib32_files: Iterable[Path] | None) -> dict:
    """The 32-bit companion: ``unsupported``, ``not-installed``, ``installed`` or ``needs-libs``."""
    ok, reason = vaapi_supported32(family)
    if not ok:
        return {"state": "unsupported", "reason": reason, "installed": False, "libs": False}
    files = LIB32_FILES if lib32_files is None else tuple(lib32_files)
    libs = all(Path(path).exists() for path in files)
    installed = driver32().is_file()
    if not ours:
        state = "not-installed"
    elif installed and libs:
        state = "installed"
    elif installed:
        state = "needs-libs"
    else:
        state = "not-installed"
    return {"state": state, "reason": "", "installed": installed, "libs": libs}


def vaapi_state(
    *, family: str, environ: Mapping[str, str] | None = None, cmdline: str | None = None,
    supported: tuple[bool, str] | None = None, lib32_files: Iterable[Path] | None = None,
) -> dict:
    """Read-only: what is installed, switched on, and live in this session."""
    environ = os.environ if environ is None else environ
    cmdline = _read(Path("/proc/cmdline")) if cmdline is None else cmdline
    ok, reason = supported if supported is not None else vaapi_supported(family=family)
    env_text = _read(ENV_FILE)
    ours = MARKER in env_text
    installed_version = ""
    for line in _read(MANIFEST).splitlines():
        if line.startswith("VERSION="):
            installed_version = line.partition("=")[2].strip()
    driver = DRIVER.is_file()
    foreign = [str(path) for path in FOREIGN_FILES if path.exists()]
    hardware_vcn = HARDWARE_VCN_ARGUMENT in cmdline.split()
    session = str(environ.get("LIBVA_DRIVER_NAME") or "") == "bc250"
    if foreign and not ours:
        state = "managed-elsewhere"
    elif hardware_vcn and not ours:
        state = "hardware-vcn"
    elif not ours:
        state = "not-installed"
    elif not driver:
        state = "invalid"
    elif installed_version and installed_version != VERSION:
        state = "outdated"
    elif session:
        state = "active"
    else:
        state = "relogin-required"
    return {
        "supported": ok,
        "blocked_reason": reason,
        "installed": ours,
        "version": installed_version,
        "expected_version": VERSION,
        "state": state,
        "foreign": foreign,
        "hardware_vcn": hardware_vcn,
        "session_active": session,
        "flatpak": flatpak_state(),
        "alias": ALIAS.exists(),
        "driver32": _state32(family, ours, lib32_files),
    }


def _header(title: str) -> list[str]:
    return [
        "set -Eeuo pipefail",
        "export LC_ALL=C LANG=C",
        'echo; echo "=========================================================================="',
        f"echo {shlex.quote(f'  BC-250 hardware video · VA-API · {title}')}",
        f"echo {shlex.quote(f'  simpmix/bc250-encoding-decoding-fix v{VERSION} (GPL-3.0) · built from source')}",
        'echo "=========================================================================="; echo',
    ]


def _probe(directory: str) -> str:
    """Start the driver in ``directory`` through libva; fail unless it offers both codecs."""
    probe = shlex.quote(str(PROBE))
    return (
        f"LIBVA_DRIVER_NAME=bc250 LIBVA_DRIVERS_PATH={directory} python3 -I {probe} 2>/dev/null"
    )


def libva_driver_path(include32: bool | None = None) -> str:
    """Our folder first, then the distribution's, so a program asking for radeonsi still finds it.

    The 32-bit folder follows ours when there is one (``include32`` names it,
    or by default the file on disk does): libva tries each folder in turn and
    skips a driver of the wrong class, so each process gets its own.
    """
    if include32 is None:
        include32 = driver32().is_file()
    ours = (str(RUNTIME), str(driver32_dir())) if include32 else (str(RUNTIME),)
    return ":".join((*ours, *SYSTEM_DRIVER_DIRS))


def flatpak_override_file() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "flatpak" / "overrides" / "global"


def flatpak_state(*, override_text: str | None = None, available: bool | None = None) -> dict:
    """Whether Flatpak is here and its apps can reach the driver (read-only)."""
    if available is None:
        available = shutil.which("flatpak") is not None
    text = _read(flatpak_override_file()) if override_text is None else override_text
    keys = {}
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
        elif "=" in line:
            key, _separator, value = line.partition("=")
            keys[(section, key.strip())] = value.strip()
    filesystems = [item for item in keys.get(("Context", "filesystems"), "").split(";") if item]
    applied = (
        f"{RUNTIME}:ro" in filesystems
        and keys.get(("Environment", "LIBVA_DRIVER_NAME")) == "bc250"
        and keys.get(("Environment", "LIBVA_DRIVERS_PATH")) == libva_driver_path()
    )
    return {"available": bool(available), "applied": applied}


def _flatpak_script(action: str, include32: bool | None = None) -> str:
    return (
        f"python3 -I {shlex.quote(str(FLATPAK_SCRIPT))} {action} "
        f"{shlex.quote(str(RUNTIME))} {shlex.quote(libva_driver_path(include32))}"
    )


def _flatpak_lines(include32: bool | None = None) -> list[str]:
    """Switch Flatpak apps on, when Flatpak is installed; it needs no root."""
    return [
        "if command -v flatpak >/dev/null 2>&1; then",
        f"  {_flatpak_script('enable', include32)}",
        "  echo '     Restart GPU Screen Recorder, OBS or Steam if they were open: Flatpak apps read this at start.'",
        "else",
        "  echo '[INFO] Flatpak is not installed: nothing to allow.'",
        "fi",
    ]


def _environment_lines(steamos: bool, include32: bool | None = None) -> list[str]:
    path = libva_driver_path(include32)
    env_text = f"{MARKER}\nLIBVA_DRIVER_NAME=bc250\nLIBVA_DRIVERS_PATH={path}\n"
    profile_text = (
        f"{MARKER}\n# Loaded last: SteamOS's own libva.sh sets radeonsi.\n"
        f"export LIBVA_DRIVER_NAME=bc250\nexport LIBVA_DRIVERS_PATH={path}\n"
    )
    lines = []
    for target, text in ((ENV_FILE, env_text), (PROFILE_FILE, profile_text)):
        lines += [
            f"sudo install -d -m 0755 {shlex.quote(str(target.parent))}",
            f"printf '%s' {shlex.quote(text)} | sudo tee {shlex.quote(str(target))} >/dev/null",
            f"sudo chmod 0644 {shlex.quote(str(target))}",
        ]
    if steamos:
        keep = f"{MARKER}\n{ENV_FILE}\n{PROFILE_FILE}\n"
        lines += [
            f"sudo install -d -m 0755 {shlex.quote(str(KEEP_FILE.parent))}",
            f"printf '%s' {shlex.quote(keep)} | sudo tee {shlex.quote(str(KEEP_FILE))} >/dev/null",
            f"sudo chmod 0644 {shlex.quote(str(KEEP_FILE))}",
        ]
    return lines


def _foreign_guard() -> list[str]:
    files = " ".join(shlex.quote(str(path)) for path in FOREIGN_FILES)
    return [
        f"for bc250_file in {files}; do",
        '  if [ -e "$bc250_file" ]; then',
        '    echo "ERROR: $bc250_file already switches this driver on (another installer)."',
        "    echo 'Remove that installation first; two copies would fight over LIBVA_DRIVER_NAME.'",
        "    exit 65",
        "  fi",
        "done",
    ]


def _owned_guard(path: Path) -> str:
    quoted = shlex.quote(str(path))
    return (
        f"if [ -e {quoted} ] && ! grep -qxF {shlex.quote(MARKER)} {quoted}; then "
        f"echo 'ERROR: {path} belongs to another tool; it was left untouched.'; exit 65; fi"
    )


def _install(family: str) -> str:
    steamos = family == "steamos"
    podman_install = PODMAN_PACKAGES.get(family, "")
    get_podman = (
        f"command -v podman >/dev/null 2>&1 || {{ echo '[INFO] Installing Podman to build the driver in a container...'; {podman_install}; }}"
        if podman_install
        else "command -v podman >/dev/null 2>&1 || { echo 'ERROR: Podman is required to build the driver and is missing.'; exit 69; }"
    )
    cache = '"${XDG_CACHE_HOME:-$HOME/.cache}/bc250-control-center/vaapi"'
    build = (
        f"dnf -y -q install {BUILD_PACKAGES} >/tmp/dnf.log 2>&1 || {{ tail -20 /tmp/dnf.log; exit 31; }}; "
        "cmake -S /src/approach1-compute-encoder -B /tmp/build -DCMAKE_BUILD_TYPE=Release "
        "-DBUILD_TESTS=OFF -DBC250_WITH_X264=OFF >/tmp/cmake.log 2>&1 || { tail -30 /tmp/cmake.log; exit 31; }; "
        'cmake --build /tmp/build -j"$(nproc)" >/tmp/build.log 2>&1 || { grep -E "error" /tmp/build.log | head -20; exit 31; }; '
        "cp /tmp/build/bc250_drv_video.so /tmp/build/*.spv /out/ && cp /src/LICENSE /out/LICENSE"
    )
    runtime = shlex.quote(str(RUNTIME))
    return "\n".join((
        *_header("install"),
        *_foreign_guard(),
        f"if grep -qw {shlex.quote(HARDWARE_VCN_ARGUMENT)} /proc/cmdline; then",
        "  echo 'ERROR: the kernel'\"'\"'s hardware video block is on (amdgpu.bc250_vcn=1); radeonsi drives it.'",
        "  exit 65",
        "fi",
        _owned_guard(ENV_FILE),
        _owned_guard(PROFILE_FILE),
        *((STEAMOS_PASSWORD_GUARD, "bc250_require_password", STEAMOS_VAR_SPACE_GUARD, "bc250_require_var_space 40")
          if steamos else ()),
        "command -v python3 >/dev/null 2>&1 || { echo 'ERROR: python3 is required to check the driver.'; exit 69; }",
        'echo "[INFO] Your password is asked once now; the install at the end reuses it."',
        "sudo -v",
        "( while sleep 50; do sudo -n -v 2>/dev/null || exit 0; done ) &",
        "bc250_sudo_keepalive=$!",
        get_podman,
        *download_and_verify(ARCHIVE_URL, "source.tar.gz", ARCHIVE_SHA256),
        "trap 'kill \"$bc250_sudo_keepalive\" 2>/dev/null || true; rm -rf -- \"$bc250_stage\"' EXIT",
        'mkdir -p "$bc250_stage/src" "$bc250_stage/out"',
        'tar -xzf "$bc250_stage/source.tar.gz" -C "$bc250_stage/src" --strip-components=1',
        'test -f "$bc250_stage/src/approach1-compute-encoder/CMakeLists.txt" || '
        "{ echo 'ERROR: the source archive does not have the expected layout.'; exit 29; }",
        f"mkdir -p {cache}",
        'echo "== Building in a Fedora container (a few minutes; nothing is installed yet) =="',
        "bc250_podman=podman; podman info >/dev/null 2>&1 || bc250_podman='sudo podman'",
        *container_network.setup_lines('"$bc250_podman"'),
        f'$bc250_podman run --rm $bc250_net --pull=missing -v "$bc250_stage/src":/src:ro,Z -v "$bc250_stage/out":/out:Z '
        f"{BUILD_IMAGE} bash -c {shlex.quote(build)}",
        'test -s "$bc250_stage/out/bc250_drv_video.so" || { echo "ERROR: the build produced no driver."; exit 31; }',
        'echo "== Checking the new driver before switching it on =="',
        f'if ! bc250_probe="$({_probe(BUILT)})"; then',
        '  echo "$bc250_probe"',
        "  echo 'ERROR: the built driver did not start or lacks H.264/HEVC. Nothing was installed.'",
        "  exit 32",
        "fi",
        'echo "$bc250_probe"',
        'echo "== Installing =="',
        f"sudo rm -rf {runtime}.new",
        f"sudo install -d -m 0755 {runtime}.new",
        f'sudo install -m 0644 "$bc250_stage/out/"* {runtime}.new/',
        f"sudo ln -sf {shlex.quote(DRIVER.name)} {runtime}.new/{shlex.quote(ALIAS.name)}",
        f"printf 'VERSION={VERSION}\\nCOMMIT={REVIEWED_COMMIT}\\nSOURCE={UPSTREAM}\\n' | sudo tee {runtime}.new/VERSION >/dev/null",
        f"if [ -f {shlex.quote(str(driver32()))} ]; then echo '[INFO] The 32-bit companion goes with this update: add it again from the card.'; fi",
        f"sudo rm -rf {runtime}.old; if [ -d {runtime} ]; then sudo mv {runtime} {runtime}.old; fi",
        f"sudo mv {runtime}.new {runtime}; sudo rm -rf {runtime}.old",
        # SELinux (Fedora, Bazzite): a library under /var/lib is var_lib_t.
        f"if command -v selinuxenabled >/dev/null 2>&1 && selinuxenabled; then sudo chcon -R -t lib_t {runtime} 2>/dev/null || true; fi",
        *_environment_lines(steamos, include32=False),
        *_flatpak_lines(include32=False),
        f'echo "[OK] Installed v{VERSION}. Log out and back in (or restart) so programs use it."',
        "echo '     Streaming while you play: choose H.264. HEVC encodes mostly on the CPU.'",
    ))


def _install32(family: str) -> str:
    """Add, or repair, the 32-bit companion of the installed 64-bit driver."""
    steamos = family == "steamos"
    packages = " ".join(LIB32_PACKAGES)
    runtime = shlex.quote(str(RUNTIME))
    target = shlex.quote(str(driver32_dir()))
    present = " && ".join(f"[ -e {shlex.quote(str(path))} ]" for path in LIB32_FILES)
    if steamos:
        libs = [
            f"bc250_pacman_install --needed --noconfirm {packages}",
            # SteamOS can keep a package's record after an update removed its files.
            f"if ! ( {present} ); then bc250_pacman_install --noconfirm {packages}; fi",
        ]
    else:
        libs = [
            "if ! pacman-conf --repo-list 2>/dev/null | grep -qx multilib; then",
            "  echo 'ERROR: the [multilib] repository is off. Uncomment [multilib] and its Include line in /etc/pacman.conf,'",
            "  echo '       run sudo pacman -Sy, and try again.'; exit 65",
            "fi",
            f"sudo pacman -S --needed --noconfirm {packages}",
        ]
    cache = '"${XDG_CACHE_HOME:-$HOME/.cache}/bc250-control-center/vaapi"'
    build = (
        f"dnf -y -q install {BUILD_PACKAGES32} >/tmp/dnf.log 2>&1 || {{ tail -20 /tmp/dnf.log; exit 31; }}; "
        "cmake -S /src/approach1-compute-encoder -B /tmp/build -DCMAKE_BUILD_TYPE=Release "
        "-DBUILD_TESTS=OFF -DBC250_WITH_X264=OFF -DBUILD_32BIT=ON >/tmp/cmake.log 2>&1 || { tail -30 /tmp/cmake.log; exit 31; }; "
        'cmake --build /tmp/build -j"$(nproc)" --target bc250_drv_video >/tmp/build.log 2>&1 || { grep -E "error" /tmp/build.log | head -20; exit 31; }; '
        "cp /tmp/build/bc250_drv_video.so /out/; "
        "readelf -h /out/bc250_drv_video.so | grep -q 'Class: *ELF32' || { echo 'ERROR: the build is not a 32-bit driver.'; exit 31; }; "
        "if readelf -d /out/bc250_drv_video.so | grep -q TEXTREL; then echo 'ERROR: the driver has text relocations and would not load under SELinux.'; exit 31; fi; "
        'bc250_glibc="$(objdump -T /out/bc250_drv_video.so | grep -o "GLIBC_[0-9.]*" | sort -uV | tail -n 1)"; '
        f'echo "glibc needed: $bc250_glibc (the oldest SteamOS ships is newer than {MIN_GLIBC[0]}.{MIN_GLIBC[1]})"; '
        "export PKG_CONFIG_LIBDIR=/usr/lib/pkgconfig:/usr/share/pkgconfig; "
        "gcc -m32 -O2 -Wl,-z,text /probe.c -o /out/bc250-vaapi-probe32 $(pkg-config --cflags --libs libva-drm)"
    )
    return "\n".join((
        *_header("add the 32-bit driver"),
        _owned_guard(ENV_FILE),
        _owned_guard(PROFILE_FILE),
        f"test -f {shlex.quote(str(DRIVER))} || {{ echo 'ERROR: install the 64-bit driver first.'; exit 29; }}",
        "command -v python3 >/dev/null 2>&1 || { echo 'ERROR: python3 is required to check the driver.'; exit 69; }",
        *((STEAMOS_PASSWORD_GUARD, "bc250_require_password", STEAMOS_VAR_SPACE_GUARD,
           f"bc250_require_var_space {VAR_SPACE_MB}", STEAMOS_PACMAN_INSTALL) if steamos else ()),
        'echo "[INFO] Your password is asked once now; the install at the end reuses it."',
        "sudo -v",
        "( while sleep 50; do sudo -n -v 2>/dev/null || exit 0; done ) &",
        "bc250_sudo_keepalive=$!",
        'echo "== 32-bit libraries (signed packages) =="',
        *libs,
        f"if ! ( {present} ); then echo 'ERROR: the 32-bit libraries are still missing after the install.'; exit 33; fi",
        # A driver that is already here only needed its libraries back (a SteamOS update removes them).
        f"if [ -f {shlex.quote(str(driver32()))} ] && ! ldd {shlex.quote(str(driver32()))} 2>&1 | grep -q 'not found'; then",
        "  kill \"$bc250_sudo_keepalive\" 2>/dev/null || true",
        '  echo "[OK] The 32-bit driver was already here; its libraries are back."',
        "  exit 0",
        "fi",
        "command -v podman >/dev/null 2>&1 || { echo 'ERROR: Podman is required to build the 32-bit driver and is missing.'; exit 69; }"
        if steamos else
        f"command -v podman >/dev/null 2>&1 || {{ echo '[INFO] Installing Podman to build the driver in a container...'; {PODMAN_PACKAGES.get(family, '')}; }}",
        *download_and_verify(ARCHIVE_URL, "source.tar.gz", ARCHIVE_SHA256),
        "trap 'kill \"$bc250_sudo_keepalive\" 2>/dev/null || true; rm -rf -- \"$bc250_stage\"' EXIT",
        'mkdir -p "$bc250_stage/src" "$bc250_stage/out"',
        'tar -xzf "$bc250_stage/source.tar.gz" -C "$bc250_stage/src" --strip-components=1',
        'test -f "$bc250_stage/src/approach1-compute-encoder/CMakeLists.txt" || '
        "{ echo 'ERROR: the source archive does not have the expected layout.'; exit 29; }",
        f"mkdir -p {cache}",
        'echo "== Building the 32-bit driver in a Fedora container (a few minutes; nothing is installed yet) =="',
        "bc250_podman=podman; podman info >/dev/null 2>&1 || bc250_podman='sudo podman'",
        *container_network.setup_lines('"$bc250_podman"'),
        f'$bc250_podman run --rm $bc250_net --pull=missing -v "$bc250_stage/src":/src:ro,Z -v "$bc250_stage/out":/out:Z '
        f"-v {shlex.quote(str(PROBE32_SOURCE))}:/probe.c:ro,Z {BUILD_IMAGE} bash -c {shlex.quote(build)}",
        'test -s "$bc250_stage/out/bc250_drv_video.so" || { echo "ERROR: the build produced no driver."; exit 31; }',
        'echo "== Checking the 32-bit driver before switching it on =="',
        # The render node comes from the 64-bit check; the 32-bit program is the one the driver is for.
        f'bc250_probe="$({_probe(runtime)})" || {{ echo "$bc250_probe"; echo "ERROR: the 64-bit driver does not start; fix it first."; exit 32; }}',
        'bc250_node="$(python3 -I -c \'import json,sys; print(json.loads(sys.argv[1])["node"])\' "$bc250_probe")"',
        f'cp {runtime}/*.spv "$bc250_stage/out/"',
        'if ! bc250_probe32="$(LIBVA_DRIVER_NAME=bc250 LIBVA_DRIVERS_PATH="$bc250_stage/out" "$bc250_stage/out/bc250-vaapi-probe32" "$bc250_node" 2>&1)"; then',
        '  echo "$bc250_probe32"',
        "  echo 'ERROR: the 32-bit driver did not start or lacks H.264/HEVC. Nothing was installed.'",
        "  exit 32",
        "fi",
        'echo "$bc250_probe32"',
        'echo "== Installing =="',
        f"sudo rm -rf {target}.new",
        f"sudo install -d -m 0755 {target}.new",
        f'sudo install -m 0755 "$bc250_stage/out/bc250_drv_video.so" {target}.new/',
        f"sudo ln -sf {shlex.quote(DRIVER.name)} {target}.new/{shlex.quote(ALIAS.name)}",
        # The shaders sit beside the 64-bit driver; this folder points at them.
        f'for bc250_spv in {runtime}/*.spv; do sudo ln -sf "../$(basename "$bc250_spv")" {target}.new/; done',
        f"sudo rm -rf {target}; sudo mv {target}.new {target}",
        *_environment_lines(steamos, include32=True),
        *_flatpak_lines(include32=True),
        'echo "[OK] The 32-bit driver is installed. Log out and back in (or restart) so Steam picks it up."',
        "echo '     Steam Remote Play and Steam Link then encode with it. A SteamOS update removes the 32-bit libraries:'",
        "echo '     the card offers Repair 32-bit driver when that happens.'",
    ))


def _test() -> str:
    runtime = shlex.quote(str(RUNTIME))
    sample = "testsrc2=size=1920x1080:rate=60"
    return "\n".join((
        *_header("test"),
        f"test -f {shlex.quote(str(DRIVER))} || {{ echo 'ERROR: the driver is not installed.'; exit 29; }}",
        f"if ! bc250_probe=\"$({_probe(runtime)})\"; then echo \"$bc250_probe\"; echo 'ERROR: the installed driver did not start.'; exit 32; fi",
        'echo "$bc250_probe"',
        'echo "This session: LIBVA_DRIVER_NAME=${LIBVA_DRIVER_NAME:-not set}"',
        # Programs that clear the variable (GPU Screen Recorder) can only find the alias.
        f"if env -u LIBVA_DRIVER_NAME LIBVA_DRIVERS_PATH={runtime} python3 -I {shlex.quote(str(PROBE))} >/dev/null 2>&1; then",
        "  echo 'Programs that choose the driver themselves (GPU Screen Recorder): ready.'",
        "else",
        "  echo '[WARN] Programs that clear LIBVA_DRIVER_NAME (GPU Screen Recorder) cannot find the driver yet. Use Allow Flatpak apps, or Update.'",
        "fi",
        f"if [ -f {shlex.quote(str(driver32()))} ]; then",
        f"  if ldd {shlex.quote(str(driver32()))} 2>&1 | grep -q 'not found'; then",
        "    echo '[WARN] The 32-bit driver is here but its 32-bit libraries are missing (a SteamOS update removes them). Use Repair 32-bit driver.'",
        "  else",
        "    echo '32-bit driver (Steam Remote Play): ready.'",
        "  fi",
        "fi",
        "if command -v flatpak >/dev/null 2>&1; then",
        f"  if python3 -I {shlex.quote(str(FLATPAK_SCRIPT))} status {runtime} {shlex.quote(libva_driver_path())} | grep -q '\"filesystem\": true.*\"driver_name\": true.*\"driver_path\": true'; then",
        "    echo 'Flatpak apps (GPU Screen Recorder, OBS, Steam): allowed.'",
        "  else",
        "    echo '[WARN] Flatpak apps cannot use the driver yet: they list H.264 as not available. Use Allow Flatpak apps.'",
        "  fi",
        "fi",
        "if ! command -v ffmpeg >/dev/null 2>&1; then echo '[INFO] ffmpeg is not installed: the encode test is skipped.'; exit 0; fi",
        'bc250_node="$(python3 -I -c \'import json,sys; print(json.loads(sys.argv[1])["node"])\' "$bc250_probe")"',
        'bc250_test="$(mktemp -d /tmp/bc250-vaapi-test.XXXXXX)"; trap \'rm -rf -- "$bc250_test"\' EXIT',
        f"export LIBVA_DRIVER_NAME=bc250 LIBVA_DRIVERS_PATH={runtime}",
        "for bc250_codec in h264_vaapi hevc_vaapi; do",
        '  echo "== Encoding 1080p60 with $bc250_codec (300 frames) =="',
        f'  ffmpeg -hide_banner -loglevel error -stats -vaapi_device "$bc250_node" -f lavfi -i {sample} '
        "-vf 'format=nv12,hwupload' -c:v \"$bc250_codec\" -b:v 15M -frames:v 300 -y \"$bc250_test/$bc250_codec.mp4\" 2>&1 | tr '\\r' '\\n' | tail -1",
        # Fedora's ffmpeg-free has no HEVC decoder: the decode then stopped
        # with "Error opening output files" and failed the whole test.
        '  bc250_decoder="${bc250_codec%_vaapi}"',
        '  if ! ffmpeg -hide_banner -decoders 2>/dev/null | grep -qE "^ *V[^ ]* +${bc250_decoder}( |$)"; then',
        '    echo "[INFO] This ffmpeg has no ${bc250_decoder} decoder (Fedora\'s ffmpeg-free leaves HEVC out): the decode test is skipped. Encoding works."',
        "    continue",
        "  fi",
        '  echo "== Decoding it =="',
        '  ffmpeg -hide_banner -loglevel error -stats -hwaccel vaapi -hwaccel_device "$bc250_node" '
        "-i \"$bc250_test/$bc250_codec.mp4\" -f null - 2>&1 | tr '\\r' '\\n' | tail -1",
        "done",
        "echo '[OK] fps above 60 keeps up with a 1080p60 stream.'",
    ))


def _alias_lines() -> list[str]:
    """Add the radeonsi alias to a driver installed without it (needs root, once)."""
    runtime = shlex.quote(str(RUNTIME))
    alias = shlex.quote(str(ALIAS))
    return [
        f"if [ ! -e {alias} ]; then",
        "  echo '[INFO] Adding the radeonsi alias: GPU Screen Recorder clears LIBVA_DRIVER_NAME, so it looks for the driver named after the GPU.'",
        "  sudo -v",
        f"  sudo ln -sf {shlex.quote(DRIVER.name)} {alias}",
        f"  if command -v selinuxenabled >/dev/null 2>&1 && selinuxenabled; then sudo chcon -R -t lib_t {runtime} 2>/dev/null || true; fi",
        "fi",
    ]


def _flatpak_workflow(action: str) -> str:
    """Allow, or stop allowing, Flatpak apps to use the installed driver."""
    enabling = action == "flatpak"
    return "\n".join((
        *_header("Flatpak apps" if enabling else "Flatpak apps · remove"),
        *((
            f"test -f {shlex.quote(str(DRIVER))} || {{ echo 'ERROR: install the driver first.'; exit 29; }}",
        ) if enabling else ()),
        "command -v flatpak >/dev/null 2>&1 || { echo 'ERROR: Flatpak is not installed.'; exit 69; }",
        "command -v python3 >/dev/null 2>&1 || { echo 'ERROR: python3 is required.'; exit 69; }",
        *(_alias_lines() if enabling else ()),
        _flatpak_script("enable" if enabling else "disable"),
        *(("echo '     Restart GPU Screen Recorder, OBS or Steam if they were open: Flatpak apps read this at start.'",)
          if enabling else ()),
    ))


def _uninstall(family: str) -> str:
    steamos = family == "steamos"
    files = [ENV_FILE, PROFILE_FILE, *((KEEP_FILE,) if steamos else ())]
    return "\n".join((
        *_header("remove"),
        *(_owned_guard(path) for path in files),
        *((STEAMOS_PASSWORD_GUARD, "bc250_require_password") if steamos else ()),
        "sudo -v",
        *(f"sudo rm -f {shlex.quote(str(path))}" for path in files),
        f"sudo rm -rf {shlex.quote(str(RUNTIME))}",
        f"command -v flatpak >/dev/null 2>&1 && {_flatpak_script('disable')} || true",
        "echo '[OK] The driver was removed. Log out and back in so programs stop asking for it.'",
    ))


def build_vaapi_command(action: str, *, family: str) -> str:
    """One closed workflow per action, for the embedded terminal."""
    action = str(action or "").strip().lower()
    family = str(family or "").strip().lower()
    if action not in ACTIONS:
        raise ValueError(f"Unsupported VA-API action: {action or '--'}")
    if action == "install":
        return _install(family)
    if action == "install32":
        ok, reason = vaapi_supported32(family)
        if not ok:
            raise ValueError(reason)
        return _install32(family)
    if action == "test":
        return _test()
    if action in {"flatpak", "flatpak-remove"}:
        return _flatpak_workflow(action)
    return _uninstall(family)
