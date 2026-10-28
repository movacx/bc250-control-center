"""The diagnosis a problem report carries, one attachment per section.

The hardware diagnosis (``system_diagnostics``) and the system state read
here (the unfiltered kernel log, why a service exits, what fills SteamOS's
/var, the config a governor started from, the last workflow logs) are joined
into one list. A section both could read is taken once, from the one that
reads more of it.

Read-only and without privileges, like ``system_diagnostics``: nothing here
writes, asks for a password or reads a file outside the system and this
application's own folders. Personal data stays out: home folders become ``~``
(``redact``), and the machine's name and network addresses are removed
(``redact_machine``).
"""

from __future__ import annotations

import getpass
import glob
import os
import re
import shutil
import socket
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from bc250cc.infrastructure import system_diagnostics as diag
from bc250cc.shared.error_origins import redact

#: Each section of the system state, before the whole is split into parts.
SECTION_LIMIT = 12000
#: The full hardware diagnosis: the same sections as the report, more room.
FULL_SECTION_LIMIT = 8000
FULL_LOG_LIMIT = 16000
FULL_TOTAL_LIMIT = 90000

#: Default host names: replacing them would also erase the distribution's
#: name everywhere it is written ("Bazzite", "steamdeck"), and they say
#: nothing about the person.
_GENERIC_HOSTS = frozenset({
    "localhost", "bazzite", "steamdeck", "fedora", "cachyos", "cachyos-x8664",
    "archlinux", "ubuntu", "debian", "manjaro", "bc250", "bc-250", "linux",
})
_OCTET = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
#: Not glued to a hyphen, letter, colon or dot: a package version such as
#: "2.4.11.1-1" or "1:2.0.0.1" is four numbers too, and was sent as "<ip>-1".
_IPV4 = re.compile(rf"(?<![\w.:-])(?!127\.0\.0\.1\b)(?:{_OCTET}\.){{3}}{_OCTET}(?![\w.-])")
#: Account names that say nothing about the person and are also words of
#: this app's own paths: with the account "bc250", every "bc250" of a report
#: (bc250-control-center, /tmp/bc250-helixsr) became "<user>".
_GENERIC_USERS = frozenset({
    "root", "deck", "bazzite", "bc250", "bc-250", "steam", "user", "gamer", "admin", "linux",
    "guest", "player", "ubuntu", "fedora", "arch", "cachyos", "manjaro", "debian",
})
_MAC = re.compile(r"\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b", re.I)


def redact_machine(text: object) -> str:
    """``redact`` plus the machine's name and its network addresses."""
    text = redact(text)
    host = socket.gethostname().strip()
    names = {host, host.split(".", 1)[0]}
    for name in sorted(names, key=len, reverse=True):
        if len(name) >= 3 and name.lower() not in _GENERIC_HOSTS:
            text = re.sub(rf"(?<![\w.-]){re.escape(name)}(?![\w-])", "<host>", text)
    # The account name also shows outside the home folder (/var/tmp/pamac-
    # build-<name>, "[sudo] password for <name>").
    try:
        user = getpass.getuser().strip()
    except Exception:  # noqa: BLE001 - no name to remove
        user = ""
    if len(user) >= 3 and user.lower() not in _GENERIC_USERS:
        text = re.sub(rf"(?<![\w]){re.escape(user)}(?![\w])", "<user>", text)
    text = _IPV4.sub("<ip>", text)
    return _MAC.sub("<mac>", text)


# --- Sections ---------------------------------------------------------------


def _boot() -> str:
    lines = [
        "cmdline: " + (diag._read("/proc/cmdline").strip() or "?"),
        "uname: " + (diag._run(["uname", "-a"]) or "?"),
        "[os-release]\n" + diag._read("/etc/os-release").strip(),
    ]
    if shutil.which("rpm-ostree"):
        # Every deployment: a pending one explains "installed but missing".
        lines.append("[rpm-ostree status]\n" + diag._run(["rpm-ostree", "status"], timeout=8))
    if shutil.which("steamos-readonly"):
        lines.append("steamos-readonly: " + diag._run(["steamos-readonly", "status"], merge=True))
    return "\n".join(lines)


def _gpu_device() -> str:
    lines = []
    if shutil.which("lspci"):
        lines.append(diag._run(["lspci", "-nnk", "-d", "1002:"]) or "lspci: no AMD device")
    cards = sorted(path for path in glob.glob("/sys/class/drm/card[0-9]*/device") if "-" not in Path(path).parent.name)
    for card in cards:
        vendor = diag._read(f"{card}/vendor").strip()
        device = diag._read(f"{card}/device").strip()
        driver = os.path.basename(os.path.realpath(f"{card}/driver")) if os.path.exists(f"{card}/driver") else "none"
        lines.append(f"{card}: vendor {vendor or '?'} device {device or '?'} driver {driver}")
    if not cards:
        lines.append("no DRM card: the GPU driver did not start this boot")
    if shutil.which("vainfo"):
        lines.append("[vainfo]\n" + diag._run(["vainfo", "--display", "drm"], merge=True))
    return "\n".join(lines)


def _kernel_log_full() -> str:
    current, _source = diag._kernel_cached("0")
    previous, _ = diag._kernel_cached("-1")
    current_lines = current.splitlines()
    return "\n".join((
        f"[this boot, last {min(250, len(current_lines))} of {len(current_lines)} lines]",
        *current_lines[-250:],
        "[previous boot, last 60 lines]",
        *previous.splitlines()[-60:],
    ))


def _service_journals() -> str:
    if not shutil.which("systemctl"):
        return "(no systemd)"
    lines = []
    for unit in (*diag._UNITS, "bc250-fan-pwm-restore.service"):
        state = diag._run(["systemctl", "show", unit, "-p", "LoadState,ActiveState,SubState,NRestarts,ExecMainStatus", "--value"])
        if not state or state.splitlines()[0] == "not-found":
            continue
        lines.append(f"== {unit}: " + " · ".join(state.splitlines()))
        journal = diag._run(["journalctl", "-u", unit, "-b", "--no-pager", "-n", "60", "-o", "short-monotonic"])
        if journal and "No entries" not in journal:
            lines.append(journal)
    return "\n".join(lines) or "(no BC-250 services)"


def _configuration() -> str:
    lines = []
    for path in (
        "/etc/cyan-skillfish-governor-smu/config.toml",
        "/etc/oberon-config.yaml",
        *sorted(glob.glob("/etc/modprobe.d/*")),
        *sorted(glob.glob("/etc/modules-load.d/*")),
        *sorted(glob.glob("/etc/systemd/system/cyan-skillfish-governor-smu.service.d/*")),
    ):
        text = diag._read(path, 6000)
        if text.strip():
            lines.append(f"[{path}]\n{text.strip()}")
    pacman = diag._read("/etc/pacman.conf", 20000)
    if pacman:
        # Only the repositories: a BC-250 one set up by hand made a workflow
        # refuse to continue, and the report could not say how it was set.
        repos = re.findall(r"^\[(?!options\])[^\]]+\][^\[]*", pacman, re.M)
        lines.append("[pacman.conf repositories]\n" + "\n".join(
            "\n".join(line for line in block.splitlines() if line.strip() and not line.lstrip().startswith("#"))
            for block in repos
        ))
    return "\n".join(lines) or "(no configuration found)"


def _storage_detail() -> str:
    lines = [diag._run(["df", "-hT", "-x", "tmpfs", "-x", "devtmpfs", "-x", "squashfs", "-x", "overlay"])]
    # What fills /var: SteamOS keeps it small and a full /var broke installs.
    usage = diag._run(["du", "-xh", "-d", "3", "/var"], timeout=8)
    if usage:
        rows = sorted(usage.splitlines(), key=_size_key, reverse=True)[:25]
        lines.append("[largest under /var]\n" + "\n".join(rows))
    return "\n".join(filter(None, lines))


def _size_key(row: str) -> float:
    size = row.split("\t", 1)[0].strip()
    match = re.fullmatch(r"([\d.,]+)([KMGT]?)", size)
    if not match:
        return 0.0
    number = float(match.group(1).replace(",", "."))
    return number * {"": 1, "K": 1e3, "M": 1e6, "G": 1e9, "T": 1e12}[match.group(2)]


def _application_files() -> str:
    lines = []
    for folder in ("/var/lib/bc250-control-center", "/usr/libexec/bc250-control-center"):
        if os.path.isdir(folder):
            lines.append(f"[{folder}]\n" + diag._run(["ls", "-laR", folder])[:4000])
    tools = Path.home() / ".local/share/bc250-control-center/ResourceTools"
    if tools.is_dir():
        for checkout in sorted(tools.iterdir()):
            if (checkout / ".git").exists():
                head = diag._run(["git", "-C", str(checkout), "log", "-1", "--format=%h %cs %s"])
                lock = " · index.lock present" if (checkout / ".git/index.lock").exists() else ""
                lines.append(f"{checkout.name}: {head or '?'}{lock}")
    helixsr = Path.home() / ".local/share/HelixSR"
    if helixsr.is_dir():
        lines.append("[HelixSR]\n" + diag._run(["ls", "-la", str(helixsr)]))
    return "\n".join(lines) or "(no application files)"


def _workflow_logs() -> str:
    """The last three workflow logs, their ends: the step that failed."""
    logs = sorted(diag.workflow_log_directory().glob("workflow-*.log"), key=_mtime, reverse=True)[:3]
    blocks = []
    for path in logs:
        from bc250cc.infrastructure.problem_report import clean_log

        tail = clean_log(diag._ANSI.sub("", diag._read(path, 400_000))).splitlines()[-150:]
        blocks.append(f"[{path.name}]\n" + "\n".join(tail))
    return "\n\n".join(blocks) or "(no workflow has been run from the app yet)"


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _packages_full() -> str:
    text = diag._packages()
    if shutil.which("flatpak"):
        text += "\n[flatpak]\n" + diag._run(["flatpak", "list", "--columns=application,version"])
    return text


#: Lines of the application's own log a report carries: the end, where the
#: failure is.
APP_LOG_LINES = 400


def _application_log() -> str:
    from bc250cc.shared.logging_config import log_path

    path = log_path()
    text = diag._read(f"{path}.1", 200_000) + diag._read(path, 400_000)
    lines = text.splitlines()[-APP_LOG_LINES:]
    return "\n".join(lines) or "(the application has not logged anything yet)"


def _settings() -> str:
    """The app's own settings: fan curve, governor, alerts, daemon intervals,
    interface. Nothing personal is kept there; the report redacts it anyway."""
    import json

    config = Path.home() / ".config/bc250-control-center"
    blocks = []
    raw = diag._read(config / "config.json", 40_000)
    if raw.strip():
        try:
            raw = json.dumps(json.loads(raw), indent=1, sort_keys=True)
        except ValueError:
            pass
        blocks.append(f"[config.json]\n{raw.strip()}")
    ui = diag._read(config / "ui.conf", 20_000)
    if ui.strip():
        blocks.append(f"[ui.conf]\n{ui.strip()}")
    return "\n\n".join(blocks) or "(no settings saved yet)"


def _helper_logs() -> str:
    """What the protected helpers refused, in their own words (SteamOS)."""
    from bc250cc.shared.paths import state_root

    folder = state_root() / "bc250-control-center"
    blocks = []
    for path in sorted(folder.glob("*-helper.log")):
        tail = diag._read(path, 200_000).splitlines()[-80:]
        if tail:
            blocks.append(f"[{path.name}]\n" + "\n".join(tail))
    return "\n\n".join(blocks) or "(no helper log)"


STATE_SECTIONS = (
    ("Boot and deployments", _boot),
    ("GPU device", _gpu_device),
    ("Kernel log (unfiltered)", _kernel_log_full),
    ("BC-250 services and their journals", _service_journals),
    ("Configuration files", _configuration),
    ("Storage", _storage_detail),
    ("Control Center files and tools", _application_files),
    ("Packages", _packages_full),
    ("Last workflow logs", _workflow_logs),
    ("Application log", _application_log),
    ("Control Center settings", _settings),
    ("Helper logs", _helper_logs),
)


def collect_system_state(sections=STATE_SECTIONS) -> str:
    def one(item):
        title, read = item
        try:
            body = str(read() or "").strip() or "—"
        except Exception as error:  # noqa: BLE001 - one unreadable section must not hide the rest
            body = f"(could not be read: {type(error).__name__})"
        if len(body) > SECTION_LIMIT:
            body = body[:SECTION_LIMIT // 3] + "\n… (cut) …\n" + body[-(SECTION_LIMIT * 2 // 3):]
        return f"== {title} ==\n{body}"

    with ThreadPoolExecutor(max_workers=4) as pool:
        parts = list(pool.map(one, sections))
    return redact_machine("\n\n".join(parts))


#: Hardware sections the system state reads more fully.
_COVERED_BY_STATE = {"Last workflow log", "Packages", "Storage", "Control Center files"}
_HEADING = re.compile(r"== (.+?) ==")


def split_sections(text: str, titles) -> list[tuple[str, str]]:
    """(title, body) of every ``== title ==`` section of a diagnosis.

    Only the diagnosis's own titles start a section: a workflow log inside
    one prints ``== Staging protected SteamOS AMDGPU backend ==`` too, and
    was cut into sections of its own (a SteamOS report kept 34 characters of
    "Last workflow logs").
    """
    known = {str(title) for title in titles}
    sections: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        match = _HEADING.fullmatch(line)
        if match and match.group(1).strip() in known:
            sections.append((match.group(1).strip(), []))
        elif sections:
            sections[-1][1].append(line)
    return [(title, "\n".join(body).strip() or "—") for title, body in sections]


def collect_attachments() -> list[tuple[str, str]]:
    """(section title, text) of every part of the diagnosis, each once."""
    hardware = [item for item in diag.SECTIONS if item[0] not in _COVERED_BY_STATE]
    full = diag.collect_diagnostics(
        hardware, section_limit=FULL_SECTION_LIMIT, log_limit=FULL_LOG_LIMIT, total_limit=FULL_TOTAL_LIMIT,
    )
    sections = (
        split_sections(redact_machine(full), (title for title, _read in hardware))
        + split_sections(collect_system_state(), (title for title, _read in STATE_SECTIONS))
    )
    seen: set[str] = set()
    unique = []
    for title, body in sections:
        if title.lower() in seen:
            continue
        seen.add(title.lower())
        unique.append((title, body))
    return unique
