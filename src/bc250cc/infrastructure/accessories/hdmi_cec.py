"""TV control over HDMI-CEC through Valve's cecd.

The BC-250 has no CEC line of its own. A DisplayPort-to-HDMI adapter that
tunnels CEC over the DisplayPort AUX channel (Club3D CAC-1080 and CAC-1085,
or any Parade PS176/PS186 design) gives the kernel a /dev/cecN, through
CONFIG_DRM_DISPLAY_DP_AUX_CEC, which the SteamOS, Arch, Fedora and Debian
kernels enable.

cecd is the daemon SteamOS runs for it: it wakes the TV when the console
wakes, puts it to sleep on suspend, turns the TV remote into an input device
and exposes all of it over D-Bus (com.steampowered.CecDaemon1). It is
Valve's linux-cec (LGPL-2.1-or-later; its linux-cec-sys crate BSD-3-Clause),
the same one keyboardspecialist/bc250-steamos's bc250-cec.sh builds on.

SteamOS ships cecd: only a configuration fragment is written (the BC-250's
name on the TV), and Steam's own CEC settings keep deciding when the TV
follows the console. Elsewhere cecd is built here from one reviewed commit,
with the distribution's Rust toolchain (Bazzite: in a Fedora container of
the same release), and runs from the user's tools folder as a user service,
like the upstream unit; the only system files are the two uaccess udev
rules upstream installs, so the logged-in user can reach /dev/cecN and
/dev/uinput.
"""

from __future__ import annotations

import gzip
import os
import shlex
import shutil
from pathlib import Path

from ..steamos_readonly import STEAMOS_PASSWORD_GUARD
from ._shared import UNIT_DIRECTORY, command_output, shell_header, user_service_state

REPOSITORY = "https://gitlab.steamos.cloud/holo/linux-cec"
VERSION = "0.3.0"
REVIEWED_REVISION = "2b7a801a682eb3e728cdb6de85712e78738f5576"
MARKER = "# Managed by BC250 Control Center: HDMI-CEC"
BUS_NAME = "com.steampowered.CecDaemon1"
DAEMON_PATH = "/com/steampowered/CecDaemon1/Daemon"
FOLDER = "cecd"
VERSION_MARKER = ".bc250-version"
SERVICE = "bc250-cecd.service"
SYSTEM_SERVICE = "cecd.service"
SYSTEM_BINARY = Path("/usr/bin/cecd")
UDEV_RULE = Path("/etc/udev/rules.d/60-bc250-control-center-cec.rules")
CONFIG_NAME = "50-bc250-control-center.toml"
CEC_CLASS = Path("/sys/class/cec")
KERNEL_OPTIONS = ("CONFIG_DRM_DISPLAY_DP_AUX_CEC=y", "CONFIG_DRM_DP_CEC=y")
#: The Rust toolchain, pkg-config, libudev headers and git, per distribution.
BUILD_PACKAGES = {
    "arch": "sudo pacman -S --needed --noconfirm rust pkgconf git",
    "manjaro": "sudo pacman -S --needed --noconfirm rust pkgconf git",
    "cachyos": "sudo pacman -S --needed --noconfirm rust pkgconf git",
    "fedora": "sudo dnf install -y cargo rust pkgconf-pkg-config systemd-devel git",
    "debian": "sudo apt-get update && sudo apt-get install -y --no-install-recommends cargo rustc pkg-config libudev-dev git",
    "ubuntu": "sudo apt-get update && sudo apt-get install -y --no-install-recommends cargo rustc pkg-config libudev-dev git",
}
FAMILIES = frozenset(BUILD_PACKAGES) | {"bazzite", "steamos"}
MIN_RUST = "1.85.0"

UDEV_TEXT = f"""{MARKER}
# From linux-cec (60-cec-uaccess.rules, 60-cecd-uinput.rules): the logged-in
# user may open CEC adapters and create the remote control's input device.
SUBSYSTEM=="cec", TAG+="uaccess"
SUBSYSTEM=="misc", KERNEL=="uinput", TAG+="uaccess"
"""


def config_text(*, follow_console: bool) -> str:
    """The BC-250's name on the TV; elsewhere also the TV following the console.

    SteamOS's own CEC settings write wake_tv and suspend_tv in a later
    fragment, so there only the name is set and the owner keeps deciding.
    """
    lines = [MARKER, 'osd_name = "BC-250"']
    if follow_console:
        lines += ["wake_tv = true", "suspend_tv = true"]
    return "\n".join(lines) + "\n"


def unit_text(folder: Path) -> str:
    return f"""[Unit]
Description=HDMI-CEC daemon (cecd, BC250 Control Center)
Documentation={REPOSITORY}
ConditionPathExists={folder}/cecd

[Service]
Type=notify
BusName={BUS_NAME}
Environment=RUST_LOG=info
ExecStart={folder}/cecd -e
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=5

[Install]
WantedBy=graphical-session.target
"""


DBUS_SERVICE_TEXT = f"""[D-BUS Service]
Name={BUS_NAME}
Exec=/bin/false
SystemdService={SERVICE}
"""


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config"))


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local/share"))


def config_path() -> Path:
    return _config_home() / "cecd" / "config.d" / CONFIG_NAME


def dbus_service_path() -> Path:
    return _data_home() / "dbus-1" / "services" / f"{BUS_NAME}.service"


def adapters(root: Path = CEC_CLASS) -> list[str]:
    try:
        return sorted(path.name for path in root.iterdir() if path.name.startswith("cec"))
    except OSError:
        return []


def kernel_support(config_gz: Path = Path("/proc/config.gz")) -> bool | None:
    """True or False when the running kernel's configuration says; None when unreadable."""
    try:
        text = gzip.decompress(config_gz.read_bytes()).decode(errors="replace")
    except (OSError, ValueError, EOFError):
        text = _read(Path("/boot") / f"config-{os.uname().release}")
    if not text:
        return None
    lines = set(text.splitlines())
    return any(option in lines for option in KERNEL_OPTIONS)


def system_cecd() -> bool:
    """cecd from the system image or a distribution package, not built here."""
    return SYSTEM_BINARY.is_file()


def supported(family: str, *, kernel: bool | None = None) -> tuple[bool, str]:
    family = str(family or "").strip().lower()
    if family not in FAMILIES:
        return False, "Offered on SteamOS, Bazzite, Arch, CachyOS, Manjaro, Fedora, Debian and Ubuntu."
    kernel = kernel_support() if kernel is None else kernel
    if kernel is False:
        return False, "The running kernel was built without CEC over DisplayPort (CONFIG_DRM_DISPLAY_DP_AUX_CEC)."
    return True, ""


def inventory(family: str, tool_dir: Path) -> dict:
    family = str(family or "").strip().lower()
    ok, reason = supported(family)
    base = {
        "supported": ok, "reason": reason, "version": VERSION,
        "device": bool(adapters()), "adapters": adapters(),
        "mode": "system" if family == "steamos" or system_cecd() else "bundled",
    }
    if not ok:
        return {**base, "state": "unsupported"}
    configured = MARKER in _read(config_path())
    if base["mode"] == "system":
        if not configured:
            return {**base, "state": "not-installed"}
        active = command_output(["systemctl", "--user", "is-active", SYSTEM_SERVICE]) == "active"
        return {**base, "state": "active" if active else "installed"}
    folder = Path(tool_dir) / FOLDER
    installed_version = _read(folder / VERSION_MARKER).strip()
    service = user_service_state(SERVICE)
    if not installed_version or not (folder / "cecd").is_file():
        state = "not-installed"
    elif installed_version != VERSION:
        state = "update-available"
    elif service == "active":
        state = "active"
    else:
        state = "installed"
    return {**base, "state": state, "service": service, "installed_version": installed_version}


def _config_lines(*, follow_console: bool) -> list[str]:
    return [
        'bc250_cec_conf="${XDG_CONFIG_HOME:-$HOME/.config}/cecd/config.d"',
        'mkdir -p "$bc250_cec_conf"',
        f'if [ -e "$bc250_cec_conf/{CONFIG_NAME}" ] && ! grep -qxF {shlex.quote(MARKER)} "$bc250_cec_conf/{CONFIG_NAME}"; then',
        f"  echo 'ERROR: {CONFIG_NAME} was changed by hand; it was left untouched.'; exit 65",
        "fi",
        f"printf '%s' {shlex.quote(config_text(follow_console=follow_console))} > \"$bc250_cec_conf/{CONFIG_NAME}\"",
    ]


def _build_lines(family: str) -> list[str]:
    """Fetch the reviewed commit and build cecd and cectool in "$bc250_stage"."""
    fetch = [
        'git -C "$bc250_stage/src" init -q',
        f'git -C "$bc250_stage/src" fetch -q --depth 1 {shlex.quote(REPOSITORY + ".git")} {REVIEWED_REVISION}',
        'git -C "$bc250_stage/src" checkout -q FETCH_HEAD',
        f'[ "$(git -C "$bc250_stage/src" rev-parse HEAD)" = {REVIEWED_REVISION} ] '
        "|| { echo 'ERROR: the fetched source is not the reviewed commit.'; exit 29; }",
    ]
    # cectool (linux-cec's default feature) comes along for diagnosis.
    cargo = "cargo build --release --locked -p cecd -p linux-cec"
    if family == "bazzite":
        # No compiler on the image: build in a Fedora container of the same
        # release, so the binary links against the same glibc and libudev.
        build = (
            "dnf -y -q install cargo rust pkgconf-pkg-config systemd-devel >/tmp/dnf.log 2>&1 "
            "|| { tail -20 /tmp/dnf.log; exit 31; }; "
            f"cd /src && {cargo} && cp target/release/cecd target/release/cectool /out/"
        )
        return [
            "command -v podman >/dev/null 2>&1 || { echo 'ERROR: Podman is required to build cecd and is missing.'; exit 69; }",
            "command -v git >/dev/null 2>&1 || { echo 'ERROR: git is required.'; exit 69; }",
            *fetch,
            'bc250_fedora="$(. /etc/os-release; printf %s "${VERSION_ID:-latest}")"',
            'echo "== Building cecd in a Fedora $bc250_fedora container (a few minutes; nothing is installed yet) =="',
            'mkdir -p "$bc250_stage/out"',
            "bc250_podman=podman; podman info >/dev/null 2>&1 || bc250_podman='sudo podman'",
            '$bc250_podman run --rm --pull=missing -v "$bc250_stage/src":/src:Z -v "$bc250_stage/out":/out:Z '
            f'"registry.fedoraproject.org/fedora:$bc250_fedora" bash -c {shlex.quote(build)}',
        ]
    return [
        "if ! command -v cargo >/dev/null 2>&1 || ! command -v pkg-config >/dev/null 2>&1 || ! command -v git >/dev/null 2>&1; then",
        "  echo '== Installing the Rust toolchain to build cecd =='",
        f"  {BUILD_PACKAGES[family]}",
        "fi",
        # The locked dependencies (clap 4.6, toml 1.1) need Rust 1.85.
        "bc250_rust=\"$(rustc --version 2>/dev/null | awk '{print $2}')\"",
        f'if [ "$(printf \'%s\\n%s\\n\' {MIN_RUST} "${{bc250_rust:-0}}" | sort -V | head -n 1)" != {MIN_RUST} ]; then',
        f"  echo \"ERROR: cecd needs Rust {MIN_RUST} or newer; this system has ${{bc250_rust:-none}}. Install a newer toolchain (for example with rustup) and try again.\"",
        "  exit 69",
        "fi",
        *fetch,
        'echo "== Building cecd (a few minutes; nothing is installed yet) =="',
        f'(cd "$bc250_stage/src" && {cargo})',
        'mkdir -p "$bc250_stage/out"',
        'cp "$bc250_stage/src/target/release/cecd" "$bc250_stage/src/target/release/cectool" "$bc250_stage/out/"',
    ]


def install_command(family: str, tool_dir: Path) -> str:
    family = str(family or "").strip().lower()
    ok, reason = supported(family)
    if not ok:
        raise RuntimeError(reason)
    commands = shell_header("TV control · HDMI-CEC (cecd)")
    if family == "steamos" or system_cecd():
        unit = SYSTEM_SERVICE
        commands += [
            *_config_lines(follow_console=family != "steamos"),
            f"systemctl --user reload-or-restart {unit} 2>/dev/null || systemctl --user start {unit} 2>/dev/null || true",
            "echo 'OK: the TV lists this console as BC-250. Its CEC behaviour follows the Steam settings.'"
            if family == "steamos"
            else "echo 'OK: the TV follows this computer: on when it wakes, asleep when it suspends.'",
        ]
        return "\n".join(commands)
    folder = Path(tool_dir) / FOLDER
    target = shlex.quote(str(folder))
    commands += [
        "for bc250_command in sudo systemctl udevadm; do",
        '  command -v "$bc250_command" >/dev/null 2>&1 || { echo "ERROR: $bc250_command is required."; exit 69; }',
        "done",
        f"if [ -e {shlex.quote(str(UDEV_RULE))} ] && ! grep -qxF {shlex.quote(MARKER)} {shlex.quote(str(UDEV_RULE))}; then",
        f"  echo 'ERROR: {UDEV_RULE} belongs to another tool; it was left untouched.'; exit 65",
        "fi",
        'echo "[INFO] Your password is asked once now; the install at the end reuses it."',
        "sudo -v",
        'bc250_stage="$(mktemp -d /tmp/bc250-cecd.XXXXXX)"',
        "trap 'rm -rf -- \"$bc250_stage\"' EXIT",
        'mkdir -p "$bc250_stage/src"',
        *_build_lines(family),
        'test -x "$bc250_stage/out/cecd" || { echo "ERROR: the build produced no cecd."; exit 31; }',
        'echo "== Installing =="',
        f"systemctl --user stop {SERVICE} 2>/dev/null || true",
        f"mkdir -p {target}",
        f'install -m 0755 "$bc250_stage/out/cecd" "$bc250_stage/out/cectool" {target}/',
        f'install -m 0644 "$bc250_stage/src/cecd/LICENSE" {target}/LICENSE',
        f'install -m 0644 "$bc250_stage/src/linux-cec-sys/LICENSE" {target}/LICENSE.linux-cec-sys',
        f"printf '%s\\n' {VERSION} > {target}/{VERSION_MARKER}",
        (
            "sudo sh -c "
            + shlex.quote(
                f"set -eu; umask 022; mkdir -p {shlex.quote(str(UDEV_RULE.parent))}; "
                f"printf '%s' \"$1\" > {shlex.quote(str(UDEV_RULE))}; "
                "udevadm control --reload-rules; "
                "udevadm trigger --subsystem-match=cec || true; "
                "udevadm trigger --subsystem-match=misc --sysname-match=uinput || true"
            )
            + f" bc250-cec {shlex.quote(UDEV_TEXT)}"
        ),
        f'mkdir -p "{UNIT_DIRECTORY}"',
        f"printf '%s' {shlex.quote(unit_text(folder))} > \"{UNIT_DIRECTORY}/{SERVICE}\"",
        'bc250_dbus="${XDG_DATA_HOME:-$HOME/.local/share}/dbus-1/services"',
        'mkdir -p "$bc250_dbus"',
        f"printf '%s' {shlex.quote(DBUS_SERVICE_TEXT)} > \"$bc250_dbus/{BUS_NAME}.service\"",
        *_config_lines(follow_console=True),
        "systemctl --user daemon-reload",
        f"systemctl --user enable {SERVICE}",
        f"systemctl --user restart {SERVICE} || true",
        f"if [ -z \"$(ls {shlex.quote(str(CEC_CLASS))} 2>/dev/null)\" ]; then",
        "  echo '[INFO] No CEC adapter is connected now; cecd picks it up when a CEC-capable DisplayPort-to-HDMI adapter is plugged in.'",
        "fi",
        f"echo 'OK: cecd {VERSION} is running. The TV follows this computer: on when it wakes, asleep when it suspends.'",
    ]
    return "\n".join(commands)


def remove_command(family: str, tool_dir: Path) -> str:
    family = str(family or "").strip().lower()
    commands = shell_header("TV control · remove HDMI-CEC setup")
    commands += [
        'bc250_cec_conf="${XDG_CONFIG_HOME:-$HOME/.config}/cecd/config.d/' + CONFIG_NAME + '"',
        f'if [ -e "$bc250_cec_conf" ] && grep -qxF {shlex.quote(MARKER)} "$bc250_cec_conf"; then rm -f "$bc250_cec_conf"; fi',
    ]
    if family == "steamos" or system_cecd():
        commands += [
            f"systemctl --user reload-or-restart {SYSTEM_SERVICE} 2>/dev/null || true",
            "echo 'OK: the CEC settings Control Center added are removed.'",
        ]
        return "\n".join(commands)
    folder = shlex.quote(str(Path(tool_dir) / FOLDER))
    rule = shlex.quote(str(UDEV_RULE))
    commands += [
        f"systemctl --user disable --now {SERVICE} 2>/dev/null || true",
        f'rm -f "{UNIT_DIRECTORY}/{SERVICE}"',
        f'rm -f "${{XDG_DATA_HOME:-$HOME/.local/share}}/dbus-1/services/{BUS_NAME}.service"',
        "systemctl --user daemon-reload",
        f"rm -rf -- {folder}",
        "sudo sh -c "
        + shlex.quote(
            f"if [ -e {rule} ] && grep -qxF {shlex.quote(MARKER)} {rule}; then rm -f {rule}; fi; "
            "udevadm control --reload-rules"
        ),
        "echo 'OK: cecd and its settings are removed.'",
    ]
    return "\n".join(commands)


def test_command(family: str, tool_dir: Path) -> str:
    """Ask cecd to wake the TV and switch it to this input."""
    commands = shell_header("TV control · test")
    commands += [
        f"bc250_adapters=\"$(ls {shlex.quote(str(CEC_CLASS))} 2>/dev/null || true)\"",
        'if [ -z "$bc250_adapters" ]; then',
        "  echo 'ERROR: no CEC adapter is connected. CEC needs a DisplayPort-to-HDMI adapter that tunnels it (Club3D CAC-1080/CAC-1085, Parade PS176/PS186).'",
        "  exit 1",
        "fi",
        'echo "[INFO] CEC adapters: $bc250_adapters"',
        "command -v busctl >/dev/null 2>&1 || { echo 'ERROR: busctl (systemd) is required.'; exit 69; }",
        f"if ! busctl --user --timeout=5 call {BUS_NAME} {DAEMON_PATH} org.freedesktop.DBus.Peer Ping >/dev/null 2>&1; then",
        "  echo 'ERROR: cecd is not running. Install TV control first, or start it: systemctl --user start "
        + (SYSTEM_SERVICE if family == "steamos" or system_cecd() else SERVICE) + "'",
        "  exit 1",
        "fi",
        f"busctl --user --timeout=10 call {BUS_NAME} {DAEMON_PATH} {BUS_NAME}.Daemon1 Wake",
        "echo 'OK: the TV was asked to turn on and switch to this input. If nothing happened, the TV or the adapter does not pass CEC.'",
    ]
    return "\n".join(commands)
