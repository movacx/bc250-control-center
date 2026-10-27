"""The full system state a problem report carries after its own answer.

Google Forms refuses a response body over about 32 KB, so the report itself
keeps a bounded diagnosis. What did not fit, and what the first week of
reports showed was missing (the end of a long workflow, the unfiltered kernel
log, why a service exits, what fills SteamOS's /var, the config a governor
started from), goes in "attachments": further responses of the same form,
tied to the report by its Report ID.

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
_IPV4 = re.compile(r"\b(?!127\.0\.0\.1\b)(?:\d{1,3}\.){3}\d{1,3}\b")
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
    if len(user) >= 3 and user not in {"root", "deck", "bazzite"}:
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
        tail = diag._ANSI.sub("", diag._read(path, 400_000)).splitlines()[-150:]
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


def collect_attachments() -> list[tuple[str, str]]:
    """(name, text) of every attachment the app gathers by itself."""
    full = diag.collect_diagnostics(
        section_limit=FULL_SECTION_LIMIT, log_limit=FULL_LOG_LIMIT, total_limit=FULL_TOTAL_LIMIT,
        fresh=False,
    )
    return [
        ("Hardware diagnosis (full)", redact_machine(full)),
        ("System state", collect_system_state()),
    ]
