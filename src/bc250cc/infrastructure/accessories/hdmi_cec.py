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
follows the console. Elsewhere cecd is built here from one reviewed commit
and runs from the user's tools folder as a user service, like the upstream
unit; the only system files are the two uaccess udev rules upstream
installs, so the logged-in user can reach /dev/cecN and /dev/uinput.

cecd wakes the TV when the console resumes from suspend and nothing more: not
at a cold boot, not at power-off. Two optional pieces cover that, ported from
keyboardspecialist/bc250-steamos (public domain): a user service that wakes the
TV once per session start, and a system unit that puts it in standby on a real
power-off (not a reboot, not a suspend). Both are polite: when another device
holds the input of a TV that is on, they leave it alone.

The locked dependencies need Rust 1.87 (zbus 5.18). Arch, CachyOS, Manjaro
and Fedora ship a newer one and build natively. Where the distribution's
Rust is older (Debian 13 and Ubuntu 25.10 carry 1.85, Ubuntu 24.04 1.75) and
on Bazzite, which has no compiler, cecd is built in the official Rust image
on Debian 12, whose binary needs only glibc 2.34 and libudev; it was checked
to run on Debian 13 and on Ubuntu 24.04, 25.10 and 26.04.
"""

from __future__ import annotations

import gzip
import os
import shlex
from pathlib import Path

from .. import container_network
from ..steamos_readonly import STEAMOS_PASSWORD_GUARD
from ._shared import (
    UNIT_DIRECTORY,
    command_output,
    shell_header,
    user_service_state,
    user_unit_path,
)

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
WAKE_SERVICE = "bc250-control-center-cec-wake.service"
WAKE_HELPER = ".local/bin/bc250-control-center-cec-wake"
POWEROFF_SERVICE = "bc250-control-center-cec-poweroff.service"
POWEROFF_UNIT = Path("/etc/systemd/system") / POWEROFF_SERVICE
POWEROFF_WANTS = Path("/etc/systemd/system/multi-user.target.wants") / POWEROFF_SERVICE
POWEROFF_HELPER = Path("/var/lib/bc250-control-center/cec/poweroff-standby")
POWEROFF_KEEP = Path("/etc/atomic-update.conf.d/bc250-control-center-cec.conf")
#: The same two pieces from keyboardspecialist/bc250-steamos; never both.
FOREIGN_WAKE = "bc250-cec-boot-wake.service"
FOREIGN_POWEROFF = Path("/etc/systemd/system/bc250-cec-poweroff-standby.service")
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
#: zbus 5.18 in the reviewed Cargo.lock declares rust-version 1.87.
MIN_RUST = "1.87.0"
#: The official Rust image, on Debian 12: its binaries need glibc 2.34.
BUILD_IMAGE = "docker.io/library/rust:1.90-slim-bookworm"
PODMAN_PACKAGES = {
    "arch": "sudo pacman -S --needed --noconfirm podman",
    "manjaro": "sudo pacman -S --needed --noconfirm podman",
    "cachyos": "sudo pacman -S --needed --noconfirm podman",
    "fedora": "sudo dnf install -y podman",
    "debian": "sudo apt-get update && sudo apt-get install -y podman",
    "ubuntu": "sudo apt-get update && sudo apt-get install -y podman",
}

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
        "automation": automation_state(),
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


def automation_state() -> dict:
    """The TV waking at session start and standing by at power-off: ``absent``, ``installed`` or ``foreign``."""
    wake = "absent"
    if user_unit_path(FOREIGN_WAKE).is_file() and not user_unit_path(WAKE_SERVICE).is_file():
        wake = "foreign"
    elif MARKER in _read(user_unit_path(WAKE_SERVICE)):
        wake = "installed"
    poweroff = "absent"
    if FOREIGN_POWEROFF.is_file() and not POWEROFF_UNIT.is_file():
        poweroff = "foreign"
    elif MARKER in _read(POWEROFF_UNIT):
        poweroff = "installed"
    return {"wake": wake, "poweroff": poweroff}


def _config_lines(*, follow_console: bool) -> list[str]:
    return [
        'bc250_cec_conf="${XDG_CONFIG_HOME:-$HOME/.config}/cecd/config.d"',
        'mkdir -p "$bc250_cec_conf"',
        f'if [ -e "$bc250_cec_conf/{CONFIG_NAME}" ] && ! grep -qxF {shlex.quote(MARKER)} "$bc250_cec_conf/{CONFIG_NAME}"; then',
        f"  echo 'ERROR: {CONFIG_NAME} was changed by hand; it was left untouched.'; exit 65",
        "fi",
        f"printf '%s' {shlex.quote(config_text(follow_console=follow_console))} > \"$bc250_cec_conf/{CONFIG_NAME}\"",
    ]


def _fetch_lines(directory: str) -> list[str]:
    return [
        f'git -C {directory} init -q',
        f'git -C {directory} fetch -q --depth 1 {shlex.quote(REPOSITORY + ".git")} {REVIEWED_REVISION}',
        f'git -C {directory} checkout -q FETCH_HEAD',
        f'[ "$(git -C {directory} rev-parse HEAD)" = {REVIEWED_REVISION} ] '
        "|| { echo 'ERROR: the fetched source is not the reviewed commit.'; exit 29; }",
    ]


#: cectool (linux-cec's default feature) comes along for diagnosis.
CARGO = "cargo build --release --locked -p cecd -p linux-cec"
#: What either route leaves in "$bc250_stage/out".
_COLLECT = (
    "cp target/release/cecd target/release/cectool {out}/ && "
    "cp cecd/LICENSE {out}/LICENSE && cp linux-cec-sys/LICENSE {out}/LICENSE.linux-cec-sys"
)


def _container_lines(family: str) -> list[str]:
    """Build in the official Rust image; the source is fetched inside it too."""
    build = " && ".join((
        "apt-get update -qq >/tmp/apt.log 2>&1",
        "apt-get install -y -qq --no-install-recommends pkg-config libudev-dev git ca-certificates >>/tmp/apt.log 2>&1",
    )) + " || { tail -20 /tmp/apt.log; exit 31; }; " + "; ".join((
        "set -e",
        "mkdir -p /tmp/src",
        *_fetch_lines("/tmp/src"),
        f"cd /tmp/src && {CARGO}",
        _COLLECT.format(out="/out"),
    ))
    get_podman = PODMAN_PACKAGES.get(family, "")
    return [
        "if ! command -v podman >/dev/null 2>&1; then",
        *(
            ["  echo '== Installing Podman to build cecd in a container =='", f"  {get_podman}"]
            if get_podman
            else ["  echo 'ERROR: Podman is required to build cecd and is missing.'", "  exit 69"]
        ),
        "fi",
        f'echo "== Building cecd in {BUILD_IMAGE} (a few minutes, about 1 GB downloaded the first time; nothing is installed yet) =="',
        'mkdir -p "$bc250_stage/out"',
        "bc250_podman=podman; podman info >/dev/null 2>&1 || bc250_podman='sudo podman'",
        *container_network.setup_lines('"$bc250_podman"'),
        f'$bc250_podman run --rm $bc250_net --pull=missing -v "$bc250_stage/out":/out:Z {BUILD_IMAGE} bash -c {shlex.quote(build)}',
    ]


def _rust_check() -> str:
    """Sets bc250_rust_ok=1 when the rustc on PATH is new enough."""
    return (
        # "|| true": under pipefail a missing rustc would otherwise end the script.
        "bc250_rust=\"$(rustc --version 2>/dev/null | awk '{print $2}' || true)\"; bc250_rust_ok=0; "
        f'if [ -n "$bc250_rust" ] && [ "$(printf \'%s\\n%s\\n\' {MIN_RUST} "$bc250_rust" | sort -V | head -n 1)" = {MIN_RUST} ]; '
        "then bc250_rust_ok=1; fi"
    )


def _build_lines(family: str) -> list[str]:
    """Build cecd and cectool into "$bc250_stage/out", natively when possible."""
    if family == "bazzite":
        # No compiler on the image.
        return _container_lines(family)
    native = [
        *_fetch_lines('"$bc250_stage/src"'),
        'echo "== Building cecd (a few minutes; nothing is installed yet) =="',
        f'(cd "$bc250_stage/src" && {CARGO} && {_COLLECT.format(out=chr(34) + "$bc250_stage/out" + chr(34))})',
    ]
    lines = [
        # A toolchain installed with rustup counts as well.
        'export PATH="$HOME/.cargo/bin:$PATH"',
        'mkdir -p "$bc250_stage/src" "$bc250_stage/out"',
        _rust_check(),
    ]
    if family in {"debian", "ubuntu"}:
        # The distribution's own Rust is only taken when it is new enough;
        # otherwise the container route, not a toolchain that cannot build it.
        lines += [
            'if [ "$bc250_rust_ok" = 1 ]; then',
            "  sudo apt-get update && sudo apt-get install -y --no-install-recommends pkg-config libudev-dev git",
            "else",
            '  bc250_candidate="$(apt-cache policy rustc 2>/dev/null | sed -n \'s/^ *Candidate: //p\' || true)"',
            f'  if [ -n "$bc250_candidate" ] && [ "$bc250_candidate" != "(none)" ] && [ "$(printf \'%s\\n%s\\n\' {MIN_RUST} "$bc250_candidate" | sort -V | head -n 1)" = {MIN_RUST} ]; then',
            f"    {BUILD_PACKAGES[family]}",
            f"    {_rust_check()}",
            "  fi",
            "fi",
        ]
    else:
        lines += [
            "if ! command -v cargo >/dev/null 2>&1 || ! command -v pkg-config >/dev/null 2>&1 || ! command -v git >/dev/null 2>&1; then",
            "  echo '== Installing the Rust toolchain to build cecd =='",
            f"  {BUILD_PACKAGES[family]}",
            f"  {_rust_check()}",
            "fi",
        ]
    lines += [
        'if [ "$bc250_rust_ok" = 1 ]; then',
        *("  " + line for line in native),
        "else",
        f'  echo "[INFO] This system\'s Rust (${{bc250_rust:-none}}) is older than the {MIN_RUST} cecd needs; building in a container instead."',
        *("  " + line for line in _container_lines(family)),
        "fi",
    ]
    return lines


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
        *_build_lines(family),
        'test -x "$bc250_stage/out/cecd" || { echo "ERROR: the build produced no cecd."; exit 31; }',
        'echo "== Installing =="',
        f"systemctl --user stop {SERVICE} 2>/dev/null || true",
        f"mkdir -p {target}",
        f'install -m 0755 "$bc250_stage/out/cecd" "$bc250_stage/out/cectool" {target}/',
        f'install -m 0644 "$bc250_stage/out/LICENSE" "$bc250_stage/out/LICENSE.linux-cec-sys" {target}/',
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


# --------------------------------------------------------------- automation

#: The device object cecd exports for the first adapter (/dev/cec0).
DEVICE_PATH_SHELL = '/com/steampowered/CecDaemon1/Devices/Cec$bc250_n'


def wake_helper_text(mode: str) -> str:
    """The script the user service runs once at session start."""
    return f"""#!/bin/bash
{MARKER}
# Wakes the TV at session start. Regenerated by Control Center; do not edit.
MODE={mode}
n=$(ls /sys/class/cec 2>/dev/null | sed -n 's/^cec//p' | head -n 1)
bc250_n=${{n:-0}}
D=(busctl --user --timeout=5 call {BUS_NAME} {DEVICE_PATH_SHELL} {BUS_NAME}.CecDevice1)
# The TV's power state (<Give Device Power Status> 0x8f, reply 0x90), retried
# while the adapter settles after boot.
st=""
for i in 1 2 3 4 5; do
    out=$("${{D[@]}}" SendReceiveRawMessage ayyyq 1 143 0 144 1500 2>/dev/null) && {{ st=${{out##* }}; break; }}
    sleep 2
done
if [ -z "$st" ]; then
    echo "TV power probe got no reply; trying the wake anyway" | systemd-cat -t bc250-cec-wake -p warning
fi
# Polite: a TV that is on, with another device holding the input, is left alone.
if [ "$MODE" = polite ] && {{ [ "$st" = 0 ] || [ "$st" = 2 ]; }}; then
    if "${{D[@]}}" SendReceiveRawMessage ayyyq 1 133 15 130 2000 >/dev/null 2>&1; then
        exit 0
    fi
fi
# Wake powers the TV on and switches its input; Wake alone does not broadcast
# the active-source claim, so it is sent too.
"${{D[@]}}" Wake || true
"${{D[@]}}" SetActiveSource i -- -1 || true
exit 0
"""


def wake_unit_text(helper: str, cecd_unit: str) -> str:
    return f"""{MARKER}
[Unit]
Description=BC-250: wake the TV at session start
After={cecd_unit}
Wants={cecd_unit}

[Service]
Type=oneshot
ExecStart={helper}

[Install]
WantedBy=graphical-session.target
"""


def poweroff_helper_text() -> str:
    return f"""#!/bin/bash
{MARKER}
# TV standby on a real power-off. Regenerated by Control Center; do not edit.
# Real power-off or halt only: a reboot and a suspend leave the TV alone.
systemctl list-jobs | grep -qE '(poweroff|halt)\\.target.*start' || exit 0
dev=$(ls -d /dev/cec* 2>/dev/null | head -n 1)
[ -n "$dev" ] || exit 0
command -v cec-ctl >/dev/null 2>&1 || exit 0
# Polite: when another device holds the input, someone is still watching.
own=$(cec-ctl -d "$dev" 2>/dev/null | sed -n 's/.*Physical Address *: *//p' | head -n 1)
act=$(cec-ctl -s -d "$dev" --request-active-source 2>/dev/null | sed -n 's/.*phys-addr: *\\([0-9a-f.]*\\).*/\\1/p' | head -n 1)
if [ -n "$act" ] && [ "$act" != "$own" ]; then
    exit 0
fi
# Logical address 0 is the TV.
cec-ctl -s -d "$dev" --to 0 --standby || true
exit 0
"""


def poweroff_unit_text() -> str:
    return f"""{MARKER}
[Unit]
Description=BC-250: TV standby on power-off
After=local-fs.target
RequiresMountsFor={POWEROFF_HELPER.parent}

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/true
ExecStop={POWEROFF_HELPER}
TimeoutStopSec=10

[Install]
WantedBy=multi-user.target
"""


def _cecd_unit(family: str) -> str:
    return SYSTEM_SERVICE if family == "steamos" or system_cecd() else SERVICE


def wake_install_command(family: str, mode: str = "polite") -> str:
    family = str(family or "").strip().lower()
    if mode not in {"polite", "grab"}:
        raise ValueError(f"Unsupported wake mode: {mode or '--'}")
    helper = f"$HOME/{WAKE_HELPER}"
    unit = f"{UNIT_DIRECTORY}/{WAKE_SERVICE}"
    commands = shell_header("TV control · wake the TV at start")
    commands += [
        f'if [ -e "{UNIT_DIRECTORY}/{FOREIGN_WAKE}" ]; then',
        f"  echo 'ERROR: {FOREIGN_WAKE} (another toolkit) already wakes the TV. Remove it first.'; exit 65",
        "fi",
        f'if [ -e "{unit}" ] && ! grep -qxF {shlex.quote(MARKER)} "{unit}"; then',
        f"  echo 'ERROR: {WAKE_SERVICE} was changed by hand; it was left untouched.'; exit 65",
        "fi",
        f'mkdir -p "$(dirname "{helper}")" "{UNIT_DIRECTORY}"',
        f"printf '%s' {shlex.quote(wake_helper_text(mode))} > \"{helper}\"",
        f'chmod 0755 "{helper}"',
        f"printf '%s' {shlex.quote(wake_unit_text('%h/' + WAKE_HELPER, _cecd_unit(family)))} > \"{unit}\"",
        "systemctl --user daemon-reload",
        f"systemctl --user enable {WAKE_SERVICE}",
        "echo "
        + shlex.quote(
            "OK: the TV wakes when this session starts."
            + (" If another device is already showing on a TV that is on, the input is left alone."
               if mode == "polite" else " It always switches to the BC-250.")
        ),
    ]
    return "\n".join(commands)


def wake_remove_command() -> str:
    helper = f"$HOME/{WAKE_HELPER}"
    unit = f"{UNIT_DIRECTORY}/{WAKE_SERVICE}"
    commands = shell_header("TV control · stop waking the TV at start")
    commands += [
        f'if [ -e "{unit}" ] && ! grep -qxF {shlex.quote(MARKER)} "{unit}"; then',
        f"  echo 'ERROR: {WAKE_SERVICE} belongs to another tool; it was left untouched.'; exit 65",
        "fi",
        f"systemctl --user disable {WAKE_SERVICE} 2>/dev/null || true",
        f'rm -f "{unit}" "{helper}"',
        "systemctl --user daemon-reload",
        "echo 'OK: the TV is no longer woken when the session starts.'",
    ]
    return "\n".join(commands)


def poweroff_install_command(family: str) -> str:
    family = str(family or "").strip().lower()
    steamos = family == "steamos"
    helper = shlex.quote(str(POWEROFF_HELPER))
    unit = shlex.quote(str(POWEROFF_UNIT))
    commands = shell_header("TV control · standby at power-off")
    commands += [
        f"if [ -e {shlex.quote(str(FOREIGN_POWEROFF))} ]; then",
        f"  echo 'ERROR: {FOREIGN_POWEROFF} (another toolkit) already does this. Remove it first.'; exit 65",
        "fi",
        f"if [ -e {unit} ] && ! grep -qxF {shlex.quote(MARKER)} {unit}; then",
        f"  echo 'ERROR: {POWEROFF_UNIT} belongs to another tool; it was left untouched.'; exit 65",
        "fi",
        "command -v cec-ctl >/dev/null 2>&1 || { echo 'ERROR: cec-ctl (v4l-utils) is needed to talk to the TV at shutdown.'; exit 69; }",
        *((STEAMOS_PASSWORD_GUARD, "bc250_require_password") if steamos else ()),
        "sudo -v",
        f"sudo install -d -m 0755 {shlex.quote(str(POWEROFF_HELPER.parent))}",
        f"printf '%s' {shlex.quote(poweroff_helper_text())} | sudo tee {helper} >/dev/null",
        f"sudo chmod 0755 {helper}",
        f"printf '%s' {shlex.quote(poweroff_unit_text())} | sudo tee {unit} >/dev/null",
        f"sudo chmod 0644 {unit}",
        *((
            f"sudo install -d -m 0755 {shlex.quote(str(POWEROFF_KEEP.parent))}",
            f"printf '%s' {shlex.quote(f'{MARKER}{chr(10)}{POWEROFF_UNIT}{chr(10)}{POWEROFF_WANTS}{chr(10)}')} "
            f"| sudo tee {shlex.quote(str(POWEROFF_KEEP))} >/dev/null",
        ) if steamos else ()),
        "sudo systemctl daemon-reload",
        f"sudo systemctl enable --now {POWEROFF_SERVICE}",
        "echo 'OK: the TV goes to standby when this computer powers off (not on a reboot or a suspend),'",
        "echo '    unless another device holds its input.'",
    ]
    return "\n".join(commands)


def poweroff_remove_command(family: str) -> str:
    steamos = str(family or "").strip().lower() == "steamos"
    helper = shlex.quote(str(POWEROFF_HELPER))
    unit = shlex.quote(str(POWEROFF_UNIT))
    commands = shell_header("TV control · no standby at power-off")
    commands += [
        f"if [ -e {unit} ] && ! grep -qxF {shlex.quote(MARKER)} {unit}; then",
        f"  echo 'ERROR: {POWEROFF_UNIT} belongs to another tool; it was left untouched.'; exit 65",
        "fi",
        *((STEAMOS_PASSWORD_GUARD, "bc250_require_password") if steamos else ()),
        "sudo -v",
        f"sudo systemctl disable --now {POWEROFF_SERVICE} 2>/dev/null || true",
        f"sudo rm -f {unit} {helper} {shlex.quote(str(POWEROFF_WANTS))}"
        + (f" {shlex.quote(str(POWEROFF_KEEP))}" if steamos else ""),
        "sudo systemctl daemon-reload",
        "echo 'OK: the TV is no longer put in standby at power-off.'",
    ]
    return "\n".join(commands)
