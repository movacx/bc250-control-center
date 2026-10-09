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
from pathlib import Path
from typing import Mapping

from .accessories._shared import download_and_verify
from .steamos_readonly import STEAMOS_PASSWORD_GUARD

UPSTREAM = "https://github.com/simpmix/bc250-encoding-decoding-fix"
VERSION = "0.5.2"
REVIEWED_COMMIT = "b8de980fa58806ba34f3cdc91192584fe9e433d5"
ARCHIVE_SHA256 = "5de910533c508f5625dd4138f459db9165713896ce9dca823c8d09b4781ae598"
ARCHIVE_URL = f"https://codeload.github.com/simpmix/bc250-encoding-decoding-fix/tar.gz/{REVIEWED_COMMIT}"
BUILD_IMAGE = "registry.fedoraproject.org/fedora:44"
BUILD_PACKAGES = "gcc gcc-c++ cmake make pkgconf libva-devel libdrm-devel vulkan-loader-devel glslang"

RUNTIME = Path("/var/lib/bc250-control-center/vaapi")
DRIVER = RUNTIME / "bc250_drv_video.so"
MANIFEST = RUNTIME / "VERSION"
ENV_FILE = Path("/etc/environment.d/90-bc250-control-center-vaapi.conf")
PROFILE_FILE = Path("/etc/profile.d/zz-bc250-control-center-vaapi.sh")
KEEP_FILE = Path("/etc/atomic-update.conf.d/bc250-control-center-vaapi.conf")
MARKER = "# Managed by BC250 Control Center: VA-API video driver"
#: The freshly built copy, inside the install workflow's private stage.
BUILT = '"$bc250_stage/out"'
PROBE = Path(__file__).resolve().parents[3] / "scripts" / "system" / "bc250-vaapi-probe.py"
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
ACTIONS = frozenset({"install", "test", "uninstall"})


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


def vaapi_state(
    *, family: str, environ: Mapping[str, str] | None = None, cmdline: str | None = None,
    supported: tuple[bool, str] | None = None,
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


def _environment_lines(steamos: bool) -> list[str]:
    path = ":".join((str(RUNTIME), *SYSTEM_DRIVER_DIRS))
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
        *((STEAMOS_PASSWORD_GUARD, "bc250_require_password") if steamos else ()),
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
        f'$bc250_podman run --rm --pull=missing -v "$bc250_stage/src":/src:ro,Z -v "$bc250_stage/out":/out:Z '
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
        f"printf 'VERSION={VERSION}\\nCOMMIT={REVIEWED_COMMIT}\\nSOURCE={UPSTREAM}\\n' | sudo tee {runtime}.new/VERSION >/dev/null",
        f"sudo rm -rf {runtime}.old; if [ -d {runtime} ]; then sudo mv {runtime} {runtime}.old; fi",
        f"sudo mv {runtime}.new {runtime}; sudo rm -rf {runtime}.old",
        # SELinux (Fedora, Bazzite): a library under /var/lib is var_lib_t.
        f"if command -v selinuxenabled >/dev/null 2>&1 && selinuxenabled; then sudo chcon -R -t lib_t {runtime} 2>/dev/null || true; fi",
        *_environment_lines(steamos),
        f'echo "[OK] Installed v{VERSION}. Log out and back in (or restart) so programs use it."',
        "echo '     Streaming while you play: choose H.264. HEVC encodes mostly on the CPU.'",
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
        "if ! command -v ffmpeg >/dev/null 2>&1; then echo '[INFO] ffmpeg is not installed: the encode test is skipped.'; exit 0; fi",
        'bc250_node="$(python3 -I -c \'import json,sys; print(json.loads(sys.argv[1])["node"])\' "$bc250_probe")"',
        'bc250_test="$(mktemp -d /tmp/bc250-vaapi-test.XXXXXX)"; trap \'rm -rf -- "$bc250_test"\' EXIT',
        f"export LIBVA_DRIVER_NAME=bc250 LIBVA_DRIVERS_PATH={runtime}",
        "for bc250_codec in h264_vaapi hevc_vaapi; do",
        '  echo "== Encoding 1080p60 with $bc250_codec (300 frames) =="',
        f'  ffmpeg -hide_banner -loglevel error -stats -vaapi_device "$bc250_node" -f lavfi -i {sample} '
        "-vf 'format=nv12,hwupload' -c:v \"$bc250_codec\" -b:v 15M -frames:v 300 -y \"$bc250_test/$bc250_codec.mp4\" 2>&1 | tr '\\r' '\\n' | tail -1",
        '  echo "== Decoding it =="',
        '  ffmpeg -hide_banner -loglevel error -stats -hwaccel vaapi -hwaccel_device "$bc250_node" '
        "-i \"$bc250_test/$bc250_codec.mp4\" -f null - 2>&1 | tr '\\r' '\\n' | tail -1",
        "done",
        "echo '[OK] fps above 60 keeps up with a 1080p60 stream.'",
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
    if action == "test":
        return _test()
    return _uninstall(family)
