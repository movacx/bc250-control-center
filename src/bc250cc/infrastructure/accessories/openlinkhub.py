"""Corsair hubs, AIOs, fans and RGB through OpenLinkHub.

Corsair controls its hubs only from iCUE on Windows. OpenLinkHub replaces it
on Linux: a small service that owns the USB devices and serves a control panel
at http://127.0.0.1:27003. NexGen3D's Steam Machine PRO case wires its fans and
lighting to a Corsair Commander Duo, which is what brought it here.

The upstream release ships three ways in. Its .rpm installs into /opt and
creates a system user from inside the package scripts, which rpm-ostree does
not handle well, so every distribution takes the user-space archive instead:
the program in the user's tools folder, a user service, and the upstream udev
rule with its group. That route writes only to /etc and the home folder, so
it works the same on Arch, Fedora, Debian, Bazzite and SteamOS.

The steps follow upstream's install-user-space.sh, except that script also
runs ``chmod -x /etc/udev/rules.d/`` (it meant the rule file), which is not
repeated here.
"""

from __future__ import annotations

import grp
import os
import platform
import shlex
from pathlib import Path

from ._shared import (
    UNIT_DIRECTORY,
    download_and_verify,
    present_usb_vendor,
    shell_header,
    user_service_state,
    user_unit_path,
)

REPOSITORY = "https://github.com/jurkovic-nikola/OpenLinkHub"
VERSION = "0.9.2"
#: The tag's commit, for the external tools manifest.
REVIEWED_REVISION = "e3909fd3aba71fe2b9192af6f76c6fb9614c89f5"
ARCHIVE = "OpenLinkHub_0.9.2_amd64.tar.gz"
ARCHIVE_SHA256 = "e1a2211f01ab6229709a4cd7994b74e5f067af7bb11ef4cd2beaf69bc2244c0c"
PANEL_URL = "http://127.0.0.1:27003"
CORSAIR_VENDOR = "1b1c"
GROUP = "openlinkhub"
RULE_PATH = "/etc/udev/rules.d/99-openlinkhub.rules"
FOLDER = "OpenLinkHub"
VERSION_MARKER = ".bc250-version"

SERVICE = "bc250-openlinkhub.service"
#: Where the other install routes put it. Two copies would fight over the
#: devices and the port, so their presence stops this one.
FOREIGN_INSTALLS = (
    Path("/usr/lib/systemd/system/OpenLinkHub.service"),
    Path("/etc/systemd/system/OpenLinkHub.service"),
    Path("/opt/OpenLinkHub/OpenLinkHub"),
)
FOREIGN_USER_UNIT = "OpenLinkHub.service"


def unit_text(folder: Path) -> str:
    return f"""[Unit]
Description=Corsair devices through OpenLinkHub (BC250 Control Center)
Documentation={REPOSITORY}
ConditionPathExists={folder}/OpenLinkHub
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
WorkingDirectory={folder}
ExecStart={folder}/OpenLinkHub
ExecReload=/bin/kill -s HUP $MAINPID
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
"""


def supported() -> bool:
    return platform.machine() == "x86_64"


def _managed_elsewhere() -> bool:
    return any(path.exists() for path in FOREIGN_INSTALLS) or user_unit_path(FOREIGN_USER_UNIT).is_file()


def _in_group_now() -> bool:
    """Whether this session already carries the group the udev rule grants."""
    try:
        gid = grp.getgrnam(GROUP).gr_gid
    except KeyError:
        return False
    return gid in os.getgroups()


def inventory(tool_dir: Path) -> dict:
    folder = Path(tool_dir) / FOLDER
    base = {
        "supported": supported(),
        "version": VERSION,
        "device": present_usb_vendor(CORSAIR_VENDOR),
        "panel_url": PANEL_URL,
    }
    if not base["supported"]:
        return {**base, "state": "unsupported", "service": "missing", "installed_version": ""}
    service = user_service_state(SERVICE)
    try:
        installed_version = (folder / VERSION_MARKER).read_text(encoding="utf-8").strip()
    except OSError:
        installed_version = ""
    if not installed_version and _managed_elsewhere():
        state = "managed-elsewhere"
    elif not installed_version or not (folder / "OpenLinkHub").is_file():
        state = "not-installed"
    elif installed_version != VERSION:
        state = "update-available"
    elif not _in_group_now():
        # The rule is in place, but this login predates the group.
        state = "relogin-required"
    elif service == "active":
        state = "active"
    else:
        state = "installed"
    return {**base, "state": state, "service": service, "installed_version": installed_version}


def install_command(tool_dir: Path) -> str:
    if not supported():
        raise RuntimeError("OpenLinkHub is published for x86_64 only.")
    if _managed_elsewhere() and not (Path(tool_dir) / FOLDER / VERSION_MARKER).is_file():
        raise RuntimeError(
            "OpenLinkHub is already installed another way on this system. Remove that copy first; two would fight over the same devices."
        )
    folder = Path(tool_dir) / FOLDER
    target = shlex.quote(str(folder))
    url = f"{REPOSITORY}/releases/download/{VERSION}/{ARCHIVE}"
    commands = shell_header(f"Corsair devices · OpenLinkHub {VERSION}")
    commands += [
        "for bc250_command in tar sudo systemctl getent udevadm; do",
        '  command -v "$bc250_command" >/dev/null 2>&1 || { echo "ERROR: $bc250_command is required."; exit 69; }',
        "done",
    ]
    commands += download_and_verify(url, ARCHIVE, ARCHIVE_SHA256)
    commands += [
        f'tar -xzf "$bc250_stage/{ARCHIVE}" -C "$bc250_stage"',
        'test -x "$bc250_stage/OpenLinkHub/OpenLinkHub" && test -f "$bc250_stage/OpenLinkHub/99-openlinkhub.rules" '
        '|| { echo "ERROR: the archive is not the expected OpenLinkHub release."; exit 29; }',
        f"systemctl --user stop {SERVICE} 2>/dev/null || true",
        # Copied over the previous copy, as upstream's upgrade does: the
        # program and its web files are replaced, profiles the owner created
        # in its database folder stay.
        f"mkdir -p {target}",
        f'cp -a "$bc250_stage/OpenLinkHub/." {target}/',
        f"printf '%s\\n' {VERSION} > {target}/{VERSION_MARKER}",
        # The rule grants the devices to a group rather than a user, so the
        # service can run as the desktop user.
        f"sed 's/OWNER=\"{GROUP}\"/GROUP=\"{GROUP}\"/g' {target}/99-openlinkhub.rules > \"$bc250_stage/rules\"",
        'bc250_user="$(id -un)"',
        f'bc250_new_member=0; id -nG "$bc250_user" | grep -qw {GROUP} || bc250_new_member=1',
        (
            "sudo sh -c '"
            f"getent group {GROUP} >/dev/null || groupadd -r {GROUP}; "
            f"usermod -aG {GROUP} \"$1\"; "
            f"install -m 0644 \"$2\" {RULE_PATH}; "
            "udevadm control --reload-rules; "
            f"udevadm trigger --subsystem-match=usb --attr-match=idVendor={CORSAIR_VENDOR}"
            "' bc250-openlinkhub \"$bc250_user\" \"$bc250_stage/rules\""
        ),
        f'mkdir -p "{UNIT_DIRECTORY}"',
        # Another toolkit run with sudo can leave the user's unit folder, or
        # an old copy of this unit, owned by root: the write then failed with
        # "Permission denied". Both belong to the desktop user.
        f'if [ ! -w "{UNIT_DIRECTORY}" ]; then sudo chown "$bc250_user": "{UNIT_DIRECTORY}"; fi',
        f'if [ -e "{UNIT_DIRECTORY}/{SERVICE}" ] && [ ! -w "{UNIT_DIRECTORY}/{SERVICE}" ]; then '
        f'sudo rm -f "{UNIT_DIRECTORY}/{SERVICE}"; fi',
        f"printf '%s' {shlex.quote(unit_text(folder))} > \"{UNIT_DIRECTORY}/{SERVICE}\"",
        "systemctl --user daemon-reload",
        f"systemctl --user enable {SERVICE}",
        f"systemctl --user restart {SERVICE} || true",
        'if [ "$bc250_new_member" = 1 ]; then',
        "  echo 'BC250_RELOGIN_REQUIRED=1'",
        "  echo 'OK: OpenLinkHub installed. Log out and back in (or restart) once, so this account can reach the Corsair devices.'",
        "else",
        f"  echo 'OK: OpenLinkHub {VERSION} is running. Its panel is at {PANEL_URL}'",
        "fi",
    ]
    return "\n".join(commands)


def remove_command(tool_dir: Path) -> str:
    folder = shlex.quote(str(Path(tool_dir) / FOLDER))
    commands = shell_header("Corsair devices · remove OpenLinkHub")
    commands += [
        f"systemctl --user disable --now {SERVICE} 2>/dev/null || true",
        f'rm -f "{UNIT_DIRECTORY}/{SERVICE}"',
        "systemctl --user daemon-reload",
        f"rm -rf -- {folder}",
        f"sudo sh -c 'rm -f {RULE_PATH}; udevadm control --reload-rules'",
        # The group stays: removing it could strip access other tools set up.
        "echo 'OK: OpenLinkHub removed.'",
    ]
    return "\n".join(commands)
