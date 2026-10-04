"""Installing the BC250-Telemetry daemon so the Power delivery band has data.

Control Center only *reads* ``/run/apu_telemetry.json``; the file is written by
``apu-telemetry.service`` from onlinermm/BC250-Telemetry, which used to be a
manual install. This module builds the closed, reviewed workflow that installs
just that daemon.

What it deliberately leaves out of upstream's ``install.sh``: the web server
(it listens on the network), the Nuvoton fan-module setup (Control Center has
its own fan workflow), and the GDDR6 collector (Control Center has its own
memory reader). The daemon is compiled from a pinned commit on the machine and
runs as root; it reads the PMIC over I2C, with one write, the standard PMBus
PAGE selector that picks the CPU or GPU rail before each read.

A unit this module did not install, for example one from upstream's own
installer, is never replaced or removed: only a unit carrying MARKER is ours.

On rpm-ostree images (Bazzite, Silverblue, Kinoite...) only ``/usr`` is
read-only: ``/etc`` is writable and ``/usr/local`` points at ``/var/usrlocal``,
so the unit and the binary land in places that survive image updates, and
SELinux labels them ``systemd_unit_file_t`` and ``bin_t`` like on Fedora.

SteamOS replaces its root filesystem on every update, ``/usr/local`` included,
but its default keep list (``/usr/lib/rauc/atomic-update-keep.conf``) already
carries ``/etc/systemd/system/*.service`` and ``*.wants/**`` across, and ``/var``
is its own partition. So the unit goes where it does elsewhere and the binary
to ``/var/lib/bc250-control-center``; nothing needs the read-only root unlocked.
The image ships ``g++`` without the C headers, so the daemon is built static
inside a pinned compiler container with the Podman SteamOS already includes,
and keeps working whatever the next update does to the libraries.

It is not offered on the BC-250 kernel (linux-cachyos-bc250): that kernel has
its own driver for the same regulator, which claims the PMIC's address on every
BC-250, so the daemon would be refused the bus. The dashboard reads the rails
from that driver's hwmon device there (see ``vrm_telemetry_reader``).
"""

from __future__ import annotations

import shlex
from pathlib import Path

from .source_checkout import clone_or_update_commit
from .steamos_readonly import STEAMOS_PASSWORD_GUARD
from .vrm_telemetry_reader import KERNEL_VRM_MODULE, kernel_vrm_driver_present

APU_TELEMETRY_UPSTREAM = "https://github.com/onlinermm/BC250-Telemetry"
#: Main at review time: the daemon reads sysfs and I2C, writes only the PMBus
#: PAGE selector and files under /run, and runs no commands and opens no sockets.
APU_TELEMETRY_REVIEWED_COMMIT = "71ad42184012367ab43eac177942a8d8d9ef73c4"
APU_TELEMETRY_DIRECTORY = "bc250-telemetry"

UNIT_PATH = Path("/etc/systemd/system/apu-telemetry.service")
BINARY_PATH = Path("/usr/local/bin/apu_telemetry")
STEAMOS_BINARY_PATH = Path("/var/lib/bc250-control-center/apu-telemetry/apu_telemetry")
#: gcc:14-bookworm at review time; pinned so every SteamOS build uses the same
#: compiler and static libc.
STEAMOS_BUILD_IMAGE = (
    "docker.io/library/gcc@sha256:a689e29bc3adf4663ef9a141d23081252764d1319c63f591a027bd6fd676f4c1"
)
SNAPSHOT_PATH = Path("/run/apu_telemetry.json")
MARKER = "# Managed by BC250 Control Center: apu-telemetry"
ACTIONS = frozenset({"install", "uninstall", "status"})

#: Families that keep their own route: there is no systemd unit to install.
_BLOCKED_FAMILIES = {
    "alpine": "BC250-Telemetry needs systemd, which Alpine does not use.",
}
#: Image-based families with a persistent place for the unit and the binary.
_IMAGE_FAMILIES = frozenset({"bazzite", "steamos"})


def _is_steamos(family: str) -> bool:
    return str(family or "").strip().lower() == "steamos"


def binary_path_for(family: str) -> Path:
    """Where the daemon is installed: SteamOS keeps /var, not /usr/local."""
    return STEAMOS_BINARY_PATH if _is_steamos(family) else BINARY_PATH


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def apu_telemetry_supported(
    *,
    family: str,
    distro_id: str = "",
    immutable: bool = False,
    kernel_module: Path = KERNEL_VRM_MODULE,
) -> tuple[bool, str]:
    """Whether this host may use the install workflow, and why not when not."""
    family = str(family or "").strip().lower()
    distro_id = str(distro_id or "").strip().lower()
    for name in (family, distro_id):
        if name in _BLOCKED_FAMILIES:
            return False, _BLOCKED_FAMILIES[name]
    # rpm-ostree images and SteamOS keep the unit and the binary across
    # updates (see the module docstring); any other image-based system is
    # still left to its own route.
    if immutable and family not in _IMAGE_FAMILIES:
        return False, "Image-based systems are not covered by this installer."
    if kernel_vrm_driver_present(kernel_module):
        return False, (
            "This kernel already reads the VRM itself (bc250_vrm, see: sensors bc250_vrm-*), "
            "and its driver keeps the service from opening the bus, so it is not needed."
        )
    return True, ""


def apu_telemetry_state(
    *,
    family: str,
    distro_id: str = "",
    immutable: bool = False,
    unit: Path = UNIT_PATH,
    binary: Path | None = None,
    snapshot: Path = SNAPSHOT_PATH,
    kernel_module: Path = KERNEL_VRM_MODULE,
) -> dict:
    """Read-only: what the installed files say. Never raises."""
    supported, blocked_reason = apu_telemetry_supported(
        family=family, distro_id=distro_id, immutable=immutable, kernel_module=kernel_module
    )
    if binary is None:
        binary = binary_path_for(family)
    unit_text = _read(unit)
    installed = bool(unit_text)
    managed = MARKER in unit_text
    if not installed:
        state = "not-installed"
    elif not managed:
        state = "external"
    elif not binary.is_file():
        state = "invalid"
    elif snapshot.exists():
        state = "publishing"
    else:
        state = "installed"
    return {
        "supported": supported,
        "blocked_reason": blocked_reason,
        "installed": installed,
        "managed": managed,
        "binary_present": binary.is_file(),
        "publishing": snapshot.exists(),
        "state": state,
    }


def _header() -> str:
    return "\n".join((
        "set -Eeuo pipefail",
        'echo; echo "=========================================================================="',
        'echo "  BC250-Telemetry · power delivery daemon (apu-telemetry.service)"',
        f'echo "  onlinermm/BC250-Telemetry · pinned {APU_TELEMETRY_REVIEWED_COMMIT[:12]} · needs the I2C mod"',
        'echo "=========================================================================="; echo',
    ))


def _host_build(quoted_checkout: str) -> tuple[str, ...]:
    return (
        "command -v g++ >/dev/null 2>&1 || { echo 'ERROR: g++ is required to build the daemon. "
        "Install the compiler (Arch: base-devel · Debian/Ubuntu: build-essential · Fedora: gcc-c++ · "
        "Bazzite/Fedora Atomic: rpm-ostree install gcc-c++, then reboot) and retry.'; exit 29; }",
    ), (
        # Static when the distribution ships libc.a; Fedora and its images do
        # not, so the static attempt stays quiet and the dynamic build reports.
        f'g++ -std=c++17 -O2 -static -o "$bc250_stage/apu_telemetry" {quoted_checkout}/bc250_telemetry.cpp 2>/dev/null || '
        f'g++ -std=c++17 -O2 -o "$bc250_stage/apu_telemetry" {quoted_checkout}/bc250_telemetry.cpp || '
        "{ echo 'ERROR: the daemon did not build; nothing was installed.'; exit 30; }",
    )


def _container_build(quoted_checkout: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    image = shlex.quote(STEAMOS_BUILD_IMAGE)
    return (
        "command -v podman >/dev/null 2>&1 || { echo 'ERROR: Podman is required to build the daemon on SteamOS.'; exit 29; }",
        "podman info >/dev/null 2>&1 || { echo 'ERROR: rootless Podman is not ready for the current user.'; exit 29; }",
    ), (
        f'podman run --rm --network=none --userns=keep-id -v {quoted_checkout}:/src:ro '
        f'-v "$bc250_stage":/out {image} '
        "g++ -std=c++17 -O2 -static -o /out/apu_telemetry /src/bc250_telemetry.cpp || "
        "{ echo 'ERROR: the daemon did not build; nothing was installed.'; exit 30; }",
        # The image is ~1.4 GB; drop it unless it was here before the pull.
        f'[ "$bc250_had_image" = 1 ] || podman rmi {image} >/dev/null 2>&1 || true',
    )


def _pull_build_image() -> tuple[str, ...]:
    image = shlex.quote(STEAMOS_BUILD_IMAGE)
    return (
        f"bc250_had_image=0; podman image exists {image} && bc250_had_image=1",
        f'[ "$bc250_had_image" = 1 ] || podman pull {image} || '
        "{ echo 'ERROR: the compiler image could not be downloaded; nothing was installed.'; exit 30; }",
    )


def _install(checkout: Path, family: str = "") -> str:
    steamos = _is_steamos(family)
    binary_path = binary_path_for(family)
    quoted_checkout = shlex.quote(str(checkout))
    unit = shlex.quote(str(UNIT_PATH))
    binary = shlex.quote(str(binary_path))
    marker = shlex.quote(MARKER)
    snapshot = shlex.quote(str(SNAPSHOT_PATH))
    stage = '"${XDG_CACHE_HOME:-$HOME/.cache}/bc250-control-center/apu-telemetry/stage"'
    build_checks, build_steps = _container_build(quoted_checkout) if steamos else _host_build(quoted_checkout)
    # The deck account has no password until its owner sets one.
    password_guard = (STEAMOS_PASSWORD_GUARD, "bc250_require_password") if steamos else ()
    verify = (
        f'test "$(git -C {quoted_checkout} rev-parse HEAD)" = {APU_TELEMETRY_REVIEWED_COMMIT} || '
        "{ echo 'ERROR: the reviewed upstream revision was not checked out.'; exit 29; }"
    )
    return "\n".join((
        _header(),
        # A unit from upstream's own installer is the user's: leave it alone.
        f"if [ -e {unit} ] && ! grep -qxF {marker} {unit}; then",
        "  echo '[INFO] apu-telemetry.service was installed by BC250-Telemetry itself; it is left untouched.'",
        f"  systemctl is-active apu-telemetry.service || true; ls -l {snapshot} 2>/dev/null || true",
        "  exit 0",
        "fi",
        "command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ] || "
        "{ echo 'ERROR: BC250-Telemetry needs systemd, which is not running here.'; exit 29; }",
        "command -v git >/dev/null 2>&1 || { echo 'ERROR: git is required to fetch the reviewed source.'; exit 29; }",
        *build_checks,
        *password_guard,
        'echo "[INFO] Your password is asked once now; the install at the end reuses it."',
        "sudo -v",
        "( while sleep 50; do sudo -n -v 2>/dev/null || exit 0; done ) &",
        "bc250_sudo_keepalive=$!",
        "trap 'kill \"$bc250_sudo_keepalive\" 2>/dev/null || true' EXIT",
        clone_or_update_commit(APU_TELEMETRY_UPSTREAM, checkout, APU_TELEMETRY_REVIEWED_COMMIT),
        verify,
        f"bc250_stage={stage}",
        'rm -rf "$bc250_stage"; mkdir -p "$bc250_stage"',
        *(_pull_build_image() if steamos else ()),
        'echo "== Building the daemon =="',
        *build_steps,
        'test -x "$bc250_stage/apu_telemetry" || { echo "ERROR: the built daemon is missing."; exit 30; }',
        # Our marker first, then upstream's unit with its binary path filled in.
        f'{{ printf \'%s\\n\' {marker}; sed "s|TELEMETRY_BIN_PATH|{binary_path}|g" {quoted_checkout}/apu-telemetry.service; }} '
        '> "$bc250_stage/apu-telemetry.service"',
        f'grep -qF {binary} "$bc250_stage/apu-telemetry.service" || '
        "{ echo 'ERROR: the service unit could not be prepared.'; exit 30; }",
        'echo "== Installing =="',
        # The PMIC is reached through /dev/i2c-*; load the driver for this boot
        # when the kernel has not exposed any bus yet.
        "ls /dev/i2c-* >/dev/null 2>&1 || sudo modprobe i2c-dev 2>/dev/null || true",
        f'sudo install -d -m 0755 {shlex.quote(str(binary_path.parent))}',
        # Swap under a new name: a running daemon's binary cannot be overwritten.
        f'sudo install -m 0755 "$bc250_stage/apu_telemetry" {binary}.new',
        f"sudo mv -f {binary}.new {binary}",
        f'sudo install -m 0644 "$bc250_stage/apu-telemetry.service" {unit}',
        f"command -v restorecon >/dev/null 2>&1 && sudo restorecon {binary} {unit} || true",
        "sudo systemctl daemon-reload",
        "sudo systemctl enable apu-telemetry.service",
        "sudo systemctl restart apu-telemetry.service",
        'echo "== Waiting for the first snapshot =="',
        f'bc250_wait=0; while [ ! -e {snapshot} ] && [ "$bc250_wait" -lt 30 ]; do sleep 0.5; bc250_wait=$((bc250_wait + 1)); done',
        f'if [ -e {snapshot} ]; then echo "[OK] The daemon is publishing {SNAPSHOT_PATH}."; '
        "else echo '[WARN] The service started but has not published yet.'; "
        "echo '       Without the physical I2C mod it finds no PMIC and keeps retrying.'; "
        "sudo journalctl -u apu-telemetry.service -n 12 --no-pager || true; fi",
    ))


def _uninstall(family: str = "") -> str:
    steamos = _is_steamos(family)
    unit = shlex.quote(str(UNIT_PATH))
    binary = shlex.quote(str(binary_path_for(family)))
    marker = shlex.quote(MARKER)
    return "\n".join((
        _header(),
        f"if [ ! -e {unit} ]; then echo '[INFO] apu-telemetry.service is not installed.'; exit 0; fi",
        f"grep -qxF {marker} {unit} || "
        "{ echo '[INFO] That service was not installed by Control Center; it is left untouched.'; exit 0; }",
        *((STEAMOS_PASSWORD_GUARD, "bc250_require_password") if steamos else ()),
        "sudo -v",
        "sudo systemctl disable --now apu-telemetry.service || true",
        f"sudo rm -f {unit} {binary}",
        "sudo systemctl daemon-reload",
        f"sudo rm -f {shlex.quote(str(SNAPSHOT_PATH))}",
        "echo '[OK] BC250-Telemetry was removed.'",
    ))


def _status(family: str = "") -> str:
    return "\n".join((
        _header(),
        f"ls -l {shlex.quote(str(UNIT_PATH))} {shlex.quote(str(binary_path_for(family)))} 2>&1 || true",
        "systemctl is-enabled apu-telemetry.service 2>&1 || true",
        "systemctl is-active apu-telemetry.service 2>&1 || true",
        f"ls -l {shlex.quote(str(SNAPSHOT_PATH))} 2>&1 || true",
        "journalctl -u apu-telemetry.service -n 12 --no-pager 2>&1 || true",
    ))


def build_apu_telemetry_command(action: str, checkout: str | Path, *, family: str = "") -> str:
    """One closed shell workflow per action, for the embedded terminal."""
    action = str(action or "").strip().lower()
    if action not in ACTIONS:
        raise ValueError(f"Unsupported BC250-Telemetry action: {action or '--'}")
    if action == "install":
        return _install(Path(checkout), family)
    if action == "uninstall":
        return _uninstall(family)
    return _status(family)

