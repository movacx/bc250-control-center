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

import getpass as getpass  # compatibility for existing report integrations
import glob
import os
import re
import shutil
import socket as socket  # compatibility for existing report integrations
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from pathlib import Path

from bc250cc.infrastructure import system_diagnostics as diag

#: Each section of the system state, before the whole is split into parts.
SECTION_LIMIT = 12000
#: The full hardware diagnosis: the same sections as the report, more room.
FULL_SECTION_LIMIT = 8000
FULL_LOG_LIMIT = 16000
FULL_TOTAL_LIMIT = 90000

# The rules that take the person out of a text live in privacy.py; these names
# stay importable from here, where reports have always found them.
from bc250cc.infrastructure.privacy import (  # noqa: E402,F401
    _GENERIC_HOSTS,
    _GENERIC_USERS,
    redact_machine,
)

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
    if not current and diag._READONLY_KERNEL_LOGS.get() is not None:
        current = "(kernel log is not readable without administrator authorization)"
    current_lines = current.splitlines()
    return "\n".join((
        f"[this boot, last {min(120, len(current_lines))} of {len(current_lines)} lines]",
        *current_lines[-120:],
        "[previous boot, last 40 lines]",
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
    # Files of ours in places others write too: who wrote them, not what they say
    # (R-6d0f3190: "it was not written by BC250 Control Center").
    for path in sorted(glob.glob("/usr/local/bin/bc250*")):
        facts = diag._run(["stat", "-c", "%A %U %s bytes %y", path])
        owned = "ours" if "Managed by BC250 Control Center" in diag._read(path, 2000) else "no mark of ours"
        lines.append(f"{path}: {facts or '?'} · {owned}")
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


def _recent_actions() -> str:
    """The last workflows, successes too: what was done, when, how it ended."""
    import json
    from datetime import datetime

    rows = []
    for path in sorted(diag.workflow_log_directory().glob("workflow-*.log"), key=_mtime, reverse=True)[:25]:
        text = diag._read(path, 400_000)
        found = re.findall(r"^BC250_CONTEXT (\{.*\})$", text, re.M)
        try:
            context = json.loads(found[-1]) if found else {}
        except ValueError:
            context = {}
        status = re.findall(r"^BC250_WORKFLOW exit_status=(\d+) duration_seconds=(\d+)", text, re.M)
        ended = datetime.fromtimestamp(_mtime(path)).astimezone().isoformat(timespec="seconds")
        name = str(context.get("action") or path.name)
        outcome = str(context.get("outcome") or ("ended" if status else "still running or interrupted"))
        detail = f" · exit {status[-1][0]} after {status[-1][1]} s" if status else ""
        rows.append(f"{ended} · {name} · {outcome}{detail}")
    return "\n".join(rows) or "(no workflow has been run from the app yet)"


def _running_now() -> str:
    """Who holds a lock: the package manager or a SteamOS toolkit action."""
    lines = []
    try:
        from .pacman_lock import lock_state

        state = lock_state()
        if state.get("state") in {"in-use", "stale"}:
            lines.append("pacman lock: " + str(state.get("state")) + " " + ", ".join(state.get("holders") or ()))
    except Exception as error:  # noqa: BLE001 - a report section never fails the report
        lines.append(f"pacman lock: not read ({type(error).__name__})")
    try:
        from . import steamos_real_toolkit, steamos_root_guard

        session = steamos_root_guard.read_session(steamos_real_toolkit.STATE_ROOT)
        if session:
            running = "running" if steamos_root_guard.session_running(session) else "ended without closing"
            lines.append(f"Real Toolkit: {session.get('action')} · {running} · started {session.get('started')}")
    except Exception as error:  # noqa: BLE001
        lines.append(f"Real Toolkit: not read ({type(error).__name__})")
    names = "pacman|paru|yay|dnf|apt-get|rpm-ostree|dkms|ninja|make|cargo"
    running = diag._run(["pgrep", "-x", "-l", names])
    if running:
        lines.append("[processes]\n" + running)
    return "\n".join(lines) or "(nothing)"


def _toolchain() -> str:
    """The programs a build uses: a broken compiler looks like the fault of what it builds."""
    lines = []
    for command in (["gcc", "--version"], ["ld", "--version"], ["ld.lld", "--version"], ["clang", "--version"],
                    ["python3", "--version"], ["ldd", "--version"], ["dkms", "--version"]):
        if shutil.which(command[0]):
            lines.append(f"{command[0]}: " + (diag._run(command, merge=True).splitlines() or ["?"])[0])
    found = sorted({*glob.glob("/usr/lib/libgcc_s.so*"), *glob.glob("/usr/lib64/libgcc_s.so*"),
                    *glob.glob("/usr/lib/x86_64-linux-gnu/libgcc_s.so*")})
    lines.append("libgcc_s: " + (", ".join(found) or "missing"))
    try:
        from .kernel_headers import headers_state

        state = headers_state()
        lines.append("kernel headers: " + " · ".join(f"{key}={value}" for key, value in state.items() if value))
    except Exception as error:  # noqa: BLE001
        lines.append(f"kernel headers: not read ({type(error).__name__})")
    return "\n".join(lines)


def _upstream_logs() -> str:
    """The logs the other projects' installers keep, condensed."""
    from bc250cc.infrastructure.problem_report import clean_log, condense_log

    paths = [Path.home() / ".cache/directmesh-build/build.log", Path.home() / ".cache/directmesh-build/setup.log",
             Path.home() / ".local/share/HelixSR/last-failed-build.log"]
    try:
        from .steamos_real_toolkit import STATE_ROOT

        paths += sorted((STATE_ROOT / "last-failure").glob("*.log"), key=_mtime, reverse=True)[:2]
    except OSError:
        pass
    blocks = []
    for path in paths:
        text = diag._read(path, 2_000_000)
        if text.strip():
            blocks.append(f"[{path.name}]\n" + condense_log(clean_log(diag._ANSI.sub("", text)), 5_000))
    return "\n\n".join(blocks) or "(none)"


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


def _core_unlock() -> str:
    """How the 8-core unlock is kept now (R-886467f7: lost after a restart).

    Observed only: topology, shim files and boot entry. Nothing needs sudo,
    nothing is changed; what cannot be read is said to be unavailable.
    """
    try:
        from .core_unlock_persistence import detect_core_unlock_persistence

        cores = set()
        for topology in Path("/sys/devices/system/cpu").glob("cpu[0-9]*/topology"):
            try:
                cores.add(((topology / "physical_package_id").read_text().strip(),
                           (topology / "core_id").read_text().strip()))
            except OSError:
                continue
        logical = os.cpu_count() or 0
        state = detect_core_unlock_persistence(physical_cores=len(cores), logical_cpus=logical)
    except Exception as error:  # noqa: BLE001 - a report section never fails the report
        return f"(not available: {error})"
    lines = [f"physical cores: {len(cores)}", f"logical CPUs: {logical}"]
    lines += [f"{key}: {value}" for key, value in state.items()]
    # The mask is readable only as root: what the tools already said about it.
    from .core_unlock_attempts import recent_attempts
    from .core_unlock_persistence import BOOT_SERVICE_STATE, BOOT_SERVICE_UNIT

    started = re.findall(r"^ExecStart=.*$", diag._read(BOOT_SERVICE_UNIT, 6000), re.M)
    if started:
        lines.append("boot service: " + started[0])
    record = diag._read(BOOT_SERVICE_STATE, 4000).strip()
    if record:
        lines.append("boot service record: " + " ".join(record.split()))
    tried = recent_attempts()
    if tried:
        lines.append("[attempts from this app]\n" + "\n".join(tried))
    return "\n".join(lines)


STATE_SECTIONS = (
    ("Boot and deployments", _boot),
    ("Core unlock", _core_unlock),
    ("GPU device", _gpu_device),
    ("Kernel log (unfiltered)", _kernel_log_full),
    ("BC-250 services and their journals", _service_journals),
    ("Configuration files", _configuration),
    ("Storage", _storage_detail),
    ("Control Center files and tools", _application_files),
    ("Packages", _packages_full),
    ("Recent actions", _recent_actions),
    ("Running now", _running_now),
    ("Build tools", _toolchain),
    ("Logs of other installers", _upstream_logs),
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
        futures = [pool.submit(copy_context().run, one, item) for item in sections]
        parts = [future.result() for future in futures]
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


#: Sections that say nothing about a failure of that area. Everything not
#: named stays, and an area not listed here keeps every section.
_FAN_AND_SENSORS = {"Kernel log: fan chip and sensors", "Sensors (hwmon)", "sensors"}
AREA_WITHOUT: dict[str, frozenset[str]] = {
    "upscaling": frozenset(_FAN_AND_SENSORS | {
        "Core unlock", "Black box", "Previous boot", "Kernel log (unfiltered)",
        "BC-250 services and their journals", "Configuration files",
    }),
    "packages": frozenset(_FAN_AND_SENSORS | {"Core unlock", "Black box", "Previous boot", "Graphics stack"}),
    "fans": frozenset({"Graphics stack", "Build tools", "Logs of other installers", "Core unlock"}),
    "compute-units": frozenset(_FAN_AND_SENSORS | {"Build tools", "Logs of other installers"}),
}
#: Only codes that name one subject. GENERAL, WORKFLOW, PROTOCOL, GPU and the
#: rest can be anything, and their reports keep everything.
_AREA_OF_CODE = {
    "UPSCALE": "upscaling", "PROTON": "upscaling", "PKG": "packages", "NET": "packages",
    "FAN": "fans", "CU": "compute-units", "UMR": "compute-units",
}


def report_area(code: str, words: str = "") -> str:
    """The area a report is about, or "" when that is not certain.

    Someone who wrote something may be describing another problem than the
    error on screen, so their report is never shortened.
    """
    if str(words or "").strip():
        return ""
    parts = str(code or "").split("-")
    return _AREA_OF_CODE.get(parts[1], "") if len(parts) == 3 and parts[0] == "BC250" else ""


def for_area(attachments, area: str) -> list[tuple[str, str]]:
    without = AREA_WITHOUT.get(area, frozenset())
    return [(name, text) for name, text in attachments if name not in without]


def collect_readonly_attachments() -> list[tuple[str, str]]:
    """The desktop diagnosis without any interactive privilege escalation.

    The cache is local to this collection and propagated to its reader threads;
    it cannot change a simultaneous desktop collection's permission policy.
    """
    logs = {boot: diag._kernel_text(boot, allow_privileged=False) for boot in ("0", "-1")}
    token = diag._READONLY_KERNEL_LOGS.set(logs)
    try:
        return collect_attachments()
    finally:
        diag._READONLY_KERNEL_LOGS.reset(token)
