"""Send a problem report or an idea to the maintainer's report service.

The service (``integrations/report-endpoint``, a Cloudflare Worker) takes the
whole report in one request: a gzip-compressed JSON document whose layout is
``SCHEMA``. Every part has one place, so nothing is sent twice:

- ``problem``: what the owner wrote (summary, steps, what was expected).
- ``error``: the error window or failed workflow the report came from.
- ``system``: what the app detected; ``owner`` only what the owner answered.
- ``history``: earlier errors, one line each; the current one is in ``error``.
- ``attachments``: the diagnosis, one entry per section.

When the service cannot be reached the report is not lost: it is written to
``saved_directory()`` and the dialog says where.

Nothing here sends by itself: every report is one press of a Send button.
"""

from __future__ import annotations

import gzip
import json
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from bc250cc.infrastructure.report_attachments import redact_machine
from bc250cc.shared.paths import state_root

#: The maintainer's report service.
REPORT_ENDPOINT = "https://bc250-reports.report-endpoint.workers.dev/v1/reports"
SCHEMA = 2
TIMEOUT_S = 25
#: A field the owner types on one line.
MAX_SHORT_TEXT = 500
#: Anything longer: a workflow log, a traceback, an attachment section.
MAX_LONG_TEXT = 200_000
#: One report at a time, and not twice in a row by a double press.
MIN_SECONDS_BETWEEN = 30

KIND_PROBLEM = "problem"
KIND_IDEA = "idea"

#: The choice that opens a box to type the answer.
OTHER = "Other (not listed)"

#: The parts of the app, one per section of ``error_origins`` that a person
#: would recognise (``AREA_BY_SECTION``).
AREAS = (
    "Dashboard / Prepare dependencies",
    "CPU (frequencies, profiles, core unlock)",
    "Compute Units (40CU)",
    "GPU governor (Cyan)",
    "Upscaling (FSR4, HelixSR, OptiScaler)",
    "Memory (VRAM, TTM, swap)",
    "Kernel, Mesa and distribution support",
    "Fans",
    "Telemetry, sensors and performance",
    "Processes",
    "Firmware (BIOS flashing)",
    "Drivers, accessories and TV control",
    "Settings and profiles",
    "Diagnostics and problem reports",
    "Built-in terminal",
    "App install or update",
    "Decky plugin (Game Mode)",
    "First-run guide",
    "Languages and translations",
    OTHER,
)
SEEN = (
    "An error window with a code (BC250-...)",
    "An error in the terminal",
    "The app does not open or closes by itself",
    "A button does nothing",
    "Wrong readings (temperature, voltage, clocks, usage)",
    "A setting is lost after a restart",
    "Games run worse than before",
    "The system does not boot or shows a black screen",
    "Text in the wrong language or untranslated",
)
FREQUENCIES = ("Every time", "Sometimes", "Only once so far")
WORKED_BEFORE = (
    "Yes, in an older version of the app",
    "Yes, before a system update",
    "No, it never worked",
    "Not sure",
)
DISTRIBUTIONS = (
    "Bazzite", "CachyOS", "SteamOS", "Arch Linux", "Manjaro", "EndeavourOS",
    "Fedora", "Nobara", "Ubuntu", "Debian", OTHER,
)
INSTALLS = (
    "Package from GitHub Releases (.pkg.tar.zst, .rpm, .deb)",
    "install-local.sh script",
    "Running from the source code (run.sh)",
    "Only the Decky plugin",
    "Not sure",
)
BIOSES = ("MeiMeiDXE v3", "Chipset Menu", "Stock BIOS", "Another modded BIOS", "Not sure", OTHER)
CORES = (
    "6 cores (stock)",
    "8 cores, unlocked in the BIOS",
    "8 cores, unlocked with Control Center",
    "Not sure",
)
CUS = ("24 CU (stock)", "40 CU unlocked", "Not sure")
OTHER_TOOLS = (
    "Another setup script or kit for the BC-250",
    "A GPU governor installed by hand",
    "A custom kernel installed by hand",
    "BC250-Telemetry",
    "None, only Control Center",
)

_sent_lock = threading.Lock()
_last_sent = 0.0


class ReportError(RuntimeError):
    """The report was not sent; ``saved`` is where a copy was kept, if any."""

    def __init__(self, message: str, *, saved: Path | None = None):
        super().__init__(message)
        self.saved = saved


@dataclass
class ErrorEvidence:
    """The error the report is about, as the app recorded it."""

    code: str = ""
    title: str = ""
    #: The catalog's explanation of ``code``.
    what: str = ""
    cause: str = ""
    fix: str = ""
    reference: str = ""
    #: "Origin: …" and "Raised in: …" lines from ``error_origins``.
    where: str = ""
    raw: str = ""

    def is_empty(self) -> bool:
        return not any((self.code, self.title, self.where, self.raw))


@dataclass
class Report:
    kind: str = KIND_PROBLEM
    id: str = field(default_factory=lambda: new_report_id())
    # What the owner wrote.
    summary: str = ""
    area: str = ""
    seen: list[str] = field(default_factory=list)
    frequency: str = ""
    worked_before: str = ""
    steps: str = ""
    expected: str = ""
    media: str = ""
    contact: str = ""
    #: An idea, or anything else added to a problem.
    notes: str = ""
    # What the owner answered about the system (the app's own reading is in
    # ``system``).
    distribution: str = ""
    install: str = ""
    bios: str = ""
    cores: str = ""
    cus: str = ""
    other_tools: list[str] = field(default_factory=list)
    # Filled by the app.
    version: str = ""
    opened_from: str = ""
    language: str = ""
    error: ErrorEvidence = field(default_factory=ErrorEvidence)
    #: The failed workflow's title and its whole log.
    workflow_title: str = ""
    workflow_log: str = ""
    #: Detected facts, in display order: {"Operating system": "Fedora Linux 44", …}.
    system: dict[str, str] = field(default_factory=dict)
    #: ``/etc/os-release`` keys that tell distributions apart.
    os_release: dict[str, str] = field(default_factory=dict)
    #: The BIOS as read: version, date, variant and how it was told.
    firmware: dict[str, str] = field(default_factory=dict)
    #: Earlier errors: {"at", "code", "source", "title", "detail"}.
    history: list[dict[str, str]] = field(default_factory=list)
    #: (section title, text) of the diagnosis.
    attachments: list[tuple[str, str]] = field(default_factory=list)

    @property
    def is_problem(self) -> bool:
        return self.kind == KIND_PROBLEM

    def missing(self) -> str:
        """The one required answer still empty, or an empty string."""
        if self.is_problem and not self.summary.strip():
            return "What went wrong?"
        if not self.is_problem and not self.notes.strip():
            return "Suggestions and ideas"
        return ""


def new_report_id() -> str:
    return "R-" + secrets.token_hex(4)


def _short(text: object) -> str:
    text = str(text or "").strip()
    return text if len(text) <= MAX_SHORT_TEXT else text[: MAX_SHORT_TEXT - 1] + "…"


def _long(text: object, *, keep_end: bool = False) -> str:
    """Bounded; a log or a traceback keeps its end, where it failed."""
    text = str(text or "").strip()
    if len(text) <= MAX_LONG_TEXT:
        return text
    return "…" + text[-(MAX_LONG_TEXT - 1):] if keep_end else text[: MAX_LONG_TEXT - 1] + "…"


def _clean(value):
    """Redacted, with empty parts dropped: the document carries no blanks."""
    if isinstance(value, dict):
        cleaned = {key: _clean(item) for key, item in value.items()}
        return {key: item for key, item in cleaned.items() if item not in ("", [], {}, None)}
    if isinstance(value, list):
        return [item for item in (_clean(item) for item in value) if item not in ("", [], {}, None)]
    if isinstance(value, str):
        return redact_machine(value)
    return value


def payload(report: Report, *, now: datetime | None = None) -> dict:
    """The document the service stores, redacted and without empty parts."""
    sent_at = (now or datetime.now().astimezone()).isoformat(timespec="seconds")
    document: dict = {
        "schema": SCHEMA,
        "id": report.id,
        "kind": report.kind,
        "sent_at": sent_at,
        "summary": _short(report.summary if report.is_problem else report.notes.splitlines()[0] if report.notes.strip() else ""),
        "app": {
            "version": _short(report.version),
            "opened_from": _short(report.opened_from),
            "language": _short(report.language),
        },
    }
    # Typed by the owner so the answer reaches them: never redacted. A handle
    # equal to the Linux account name arrived as "@<user>".
    contact = _short(report.contact)
    if not report.is_problem:
        document["idea"] = _long(report.notes)
        return _with_contact(_clean(document), contact)
    document["problem"] = {
        "area": _short(report.area),
        "seen": [_short(item) for item in report.seen],
        "frequency": _short(report.frequency),
        "worked_before": _short(report.worked_before),
        "steps": _long(report.steps),
        "expected": _long(report.expected),
        "media": _short(report.media),
        "notes": _long(report.notes),
    }
    error = report.error
    document["error"] = {
        "code": _short(error.code),
        "title": _short(error.title),
        "what": _short(error.what),
        "cause": _short(error.cause),
        "fix": _short(error.fix),
        "reference": _short(error.reference),
        "where": _long(error.where),
        "raw": _long(error.raw, keep_end=True),
    }
    document["workflow"] = {
        "title": _short(report.workflow_title),
        "log": _long(report.workflow_log, keep_end=True),
    }
    document["system"] = {_short(key): _short(value) for key, value in report.system.items()}
    document["os_release"] = {key: _short(value) for key, value in report.os_release.items()}
    document["firmware"] = {key: _short(value) for key, value in report.firmware.items()}
    document["owner"] = {
        "distribution": _short(report.distribution),
        "install": _short(report.install),
        "bios": _short(report.bios),
        "cores": _short(report.cores),
        "cus": _short(report.cus),
        "other_tools": [_short(item) for item in report.other_tools],
    }
    document["history"] = [
        {key: _short(entry.get(key, "")) for key in ("at", "code", "source", "title", "detail")}
        for entry in report.history
    ]
    document["attachments"] = [
        {"name": _short(name), "text": _long(text, keep_end=name.lower().startswith(("last workflow", "kernel log")))}
        for name, text in report.attachments
    ]
    return _with_contact(_clean(document), contact)


def _with_contact(document: dict, contact: str) -> dict:
    if contact:
        document["contact"] = contact
    return document


def post_report(document: dict, *, url: str = REPORT_ENDPOINT, timeout: float = TIMEOUT_S) -> None:
    """Store ``document`` in the service, or raise ``ReportError`` saying why."""
    body = gzip.compress(json.dumps(document, ensure_ascii=False).encode("utf-8"))
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("User-Agent", "BC250-Control-Center")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https host
            answer = json.loads(response.read(65536).decode("utf-8", "replace"))
    except urllib.error.HTTPError as error:
        if error.code == 429:
            raise ReportError("The report service is busy. Wait a minute and send it again.") from error
        raise ReportError("The report service refused the report.") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise ReportError("The report service could not be reached. Check the internet connection.") from error
    except ValueError as error:
        raise ReportError("The report service gave an unreadable answer.") from error
    if not (isinstance(answer, dict) and answer.get("ok") and answer.get("id") == document.get("id")):
        raise ReportError("The report service did not confirm the report.")


def saved_directory() -> Path:
    return state_root() / "bc250-control-center" / "reports"


def save_copy(document: dict, directory: Path | None = None) -> Path | None:
    """Keep an unsent report on disk; None when even that fails."""
    folder = directory or saved_directory()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{document.get('id') or new_report_id()}.json"
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
    except OSError:
        return None


def submit(
    report: Report,
    *,
    post: Callable[[dict], None] = post_report,
    save: Callable[[dict], Path | None] = save_copy,
    clock: Callable[[], float] = time.monotonic,
) -> str:
    """Send the report and return its ID, or raise ``ReportError``.

    A report the service did not take is saved on disk first, so the error
    can say where it is.
    """
    global _last_sent
    if report.missing():
        raise ReportError("A required answer is empty.")
    document = payload(report)
    with _sent_lock:
        if _last_sent and clock() - _last_sent < MIN_SECONDS_BETWEEN:
            raise ReportError("A report was sent a moment ago. Wait a few seconds.")
        try:
            post(document)
        except ReportError as error:
            raise ReportError(str(error), saved=save(document)) from error
        _last_sent = clock()
    return report.id


# --- Answers the app already knows -------------------------------------------------


_DISTRIBUTION_IDS = (
    ("Bazzite", "bazzite"), ("Nobara", "nobara"), ("CachyOS", "cachyos"), ("SteamOS", "steamos"),
    ("Manjaro", "manjaro"), ("EndeavourOS", "endeavouros"), ("Fedora", "fedora"),
    ("Ubuntu", "ubuntu"), ("Debian", "debian"),
)


def suggested_distribution(os_release: dict[str, str]) -> str:
    """The listed choice for this system, or its own name for "Other"."""
    own = " ".join((os_release.get("ID", ""), os_release.get("NAME", ""), os_release.get("VARIANT_ID", ""))).lower()
    for label, needle in _DISTRIBUTION_IDS:
        if needle in own:
            return label
    if os_release.get("ID", "").lower() == "arch":
        return "Arch Linux"
    # A derivative names its parent only in ID_LIKE: its own name is the answer.
    return os_release.get("PRETTY_NAME") or os_release.get("NAME") or ""


#: ``firmware.board.InstalledBios.variant`` and the form's answer for it.
_BIOS_BY_VARIANT = {"MeiMeiDXE v3": "MeiMeiDXE v3", "Chipset Menu": "Chipset Menu", "ASRock": "Stock BIOS"}


def suggested_bios(variant: str) -> str:
    return _BIOS_BY_VARIANT.get(variant, "")


def suggested_install(installation: str) -> str:
    """Map the Diagnostics "Installation" row to the form's choice."""
    text = installation.lower()
    if text.startswith(("package", "aur")):
        return INSTALLS[0]
    if text.startswith("install-local"):
        return INSTALLS[1]
    if text.startswith(("source", "script")):
        return INSTALLS[2]
    return ""


#: Words in an error window's context and the part of the app they belong to.
#: The first match wins: the narrower parts come before the ones they live in
#: (HelixSR is reached from the GPU governor page, but it is upscaling).
_AREA_WORDS = (
    (("HELIXSR", "FSR4", "OPTISCALER", "UPSCAL"), "Upscaling (FSR4, HelixSR, OptiScaler)"),
    (("COMPUTE UNIT", "40CU", " CU "), "Compute Units (40CU)"),
    (("CYAN", "OBERON", "GOVERNOR", "GPU"), "GPU governor (Cyan)"),
    (("CORE UNLOCK", "CPU", "SMU"), "CPU (frequencies, profiles, core unlock)"),
    # Not "memory": the GDDR6 memory temperature is a sensor reading.
    (("VRAM", "TTM", "SWAP", "ZRAM", "ZSWAP"), "Memory (VRAM, TTM, swap)"),
    (("KERNEL", "MESA", "RADV", "VAAPI", "GFX1013"), "Kernel, Mesa and distribution support"),
    (("FAN", "PWM", "NCT6687"), "Fans"),
    (("FIRMWARE", "BIOS", "FLASH"), "Firmware (BIOS flashing)"),
    (("HDMI", "CEC", " TV ", "DRIVER", "ACCESSOR", "LCD", "RGB", "PRINT", "CORSAIR", "OPENLINKHUB", "THERMALRIGHT", "TRCC"),
     "Drivers, accessories and TV control"),
    (("TELEMETRY", "SENSOR", "GDDR6", "TEMPERATURE", "PERFORMANCE", "BENCHMARK", "STRESS"), "Telemetry, sensors and performance"),
    (("PROCESS",), "Processes"),
    (("PROFILE", "SETTING", "PREFERENCE"), "Settings and profiles"),
    (("REPORT", "DIAGNOSTIC"), "Diagnostics and problem reports"),
    (("UPDATE", "INSTALL"), "App install or update"),
    (("DECKY", "QUICK ACCESS", "GAME MODE"), "Decky plugin (Game Mode)"),
    (("DEPENDENC", "PREPAR", "DASHBOARD"), "Dashboard / Prepare dependencies"),
)


#: Sections of ``error_origins`` and the part of the app each is. System
#: access, the interface and the core are everywhere: they name no part.
AREA_BY_SECTION = {
    "DASH": "Dashboard / Prepare dependencies",
    "PREP": "Dashboard / Prepare dependencies",
    "CPU": "CPU (frequencies, profiles, core unlock)",
    "CU": "Compute Units (40CU)",
    "GPU": "GPU governor (Cyan)",
    "UPS": "Upscaling (FSR4, HelixSR, OptiScaler)",
    "MEM": "Memory (VRAM, TTM, swap)",
    "DIST": "Kernel, Mesa and distribution support",
    "FAN": "Fans",
    "TEL": "Telemetry, sensors and performance",
    "PROC": "Processes",
    "FW": "Firmware (BIOS flashing)",
    "DRV": "Drivers, accessories and TV control",
    "SET": "Settings and profiles",
    "DIAG": "Diagnostics and problem reports",
    "CON": "Built-in terminal",
    "UPD": "App install or update",
    "DECKY": "Decky plugin (Game Mode)",
    "ONB": "First-run guide",
    "I18N": "Languages and translations",
}
#: Sections every part goes through: where the error was raised says more.
GENERIC_SECTIONS = frozenset({"SYS", "UI", "CORE"})


def area_section(raised, shown) -> str:
    """The section a report is about: where it failed, unless that is code
    every part shares; then where it was shown."""
    for place in (raised, shown):
        section = getattr(place, "section", "") or ""
        if section and section not in GENERIC_SECTIONS:
            return section
    return ""


def suggested_area(context: str) -> str:
    text = f" {context.upper()} "
    for words, area in _AREA_WORDS:
        if any(word in text for word in words):
            return area
    return ""


def suggested_cores(physical_cores: int) -> str:
    # Eight cores came from the BIOS or from Control Center; only the owner knows.
    return CORES[0] if physical_cores == 6 else ""


_HISTORY_DETAIL = 300


def history_items(entries, *, exclude_raw: str = "", exclude_title: str = "", limit: int = 10) -> list[dict[str, str]]:
    """Earlier errors, newest first, one short line of detail each.

    The error the report is about is left out (it is in ``error`` whole), and
    so is a repeat of the line just above it.
    """
    items: list[dict[str, str]] = []
    previous = None
    for entry in entries:
        raw = str(getattr(entry, "raw", "") or "")
        title = str(getattr(entry, "title", "") or "")
        if (exclude_raw and raw and raw.strip() == exclude_raw.strip()) or (exclude_title and title == exclude_title):
            continue
        detail = " ".join(str(getattr(entry, "detail", "") or "").split())
        key = (getattr(entry, "code", ""), title, detail)
        if key == previous:
            continue
        previous = key
        items.append({
            "at": datetime.fromtimestamp(float(getattr(entry, "at", 0) or 0)).astimezone().isoformat(timespec="seconds"),
            "code": str(getattr(entry, "code", "") or ""),
            "source": str(getattr(entry, "source", "") or ""),
            "title": title,
            "detail": detail if len(detail) <= _HISTORY_DETAIL else detail[: _HISTORY_DETAIL - 1] + "…",
        })
        if len(items) >= limit:
            break
    return items


#: os-release keys worth sending: they tell a distribution and its edition
#: apart (its name is already in ``system``).
OS_RELEASE_KEYS = ("ID", "ID_LIKE", "VERSION_ID", "VARIANT", "VARIANT_ID", "BUILD_ID", "IMAGE_VERSION")


def os_release_subset(values: dict[str, str]) -> dict[str, str]:
    return {key: values[key] for key in OS_RELEASE_KEYS if values.get(key)}


_LOG_SYNC = re.compile(r"\x1b?\]777;[^\x07\n]*\x07?")
#: The credits every workflow prints first (common.sh): the same in every log.
CREDITS = re.compile(r"^(?:== )?Third-party credits(?: ==)?\n(?:Explicit workflows[^\n]*\n)?(?:- [^\n]*\n?)*", re.M)


def clean_log(text: str) -> str:
    """A workflow log as read: no terminal control strings, no credits."""
    return CREDITS.sub("", _LOG_SYNC.sub("", str(text or "")))
