"""Send a problem report or an idea to the maintainer's Google Form.

The form lives at ``FORM_URL`` and the app fills in the same questions,
without a browser. Google Forms has no API for answering a form, so this does
what the browser does: it reads the live form, checks that every question this
module answers is still there with the same choices, and posts the answers to
``formResponse``. When the form was edited and a question is gone, nothing is
sent: the caller opens the form in the browser instead (``prefill_url``) and
the person loses nothing they wrote.

Nothing here sends by itself. Every submission is one press of a Send button,
and only to ``docs.google.com``.
"""

from __future__ import annotations

import html
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from bc250cc.shared.error_origins import redact

FORM_ID = "1FAIpQLSe3M1stf3bpCoorb4hCWFX9YC_TZ_Gv6WHWQDRe1AV5rJT6rA"
FORM_URL = f"https://docs.google.com/forms/d/e/{FORM_ID}/viewform"
RESPONSE_URL = f"https://docs.google.com/forms/d/e/{FORM_ID}/formResponse"
TIMEOUT_S = 15
MAX_PAGE_BYTES = 2 * 1024 * 1024
#: Long answers are cut here: a report is read by a person, not archived.
MAX_LONG_TEXT = 20000
MAX_SHORT_TEXT = 500
#: The hardware diagnosis is long by nature: kernel log, sensors, services.
MAX_HARDWARE_TEXT = 32000
#: One report at a time, and not twice in a row by a double press.
MIN_SECONDS_BETWEEN = 30
#: Google rejects a response body over about 32 KB with "413 Payload Too
#: Large" (measured: 32 481 bytes stored, 32 656 refused). The answers are cut
#: to fit under this, URL-encoded, before sending.
MAX_POST_BYTES = 30000
OTHER = "__other_option__"

KIND_PROBLEM = "Report a problem"
KIND_IDEA = "Just a suggestion or idea"

# Question ids of the live form (entry.<id>), with the exact choice labels.
ENTRY_KIND = 580341729
ENTRY_SUMMARY = 62514469
ENTRY_DIAGNOSTICS = 1414055199
ENTRY_AREA = 1970910545
ENTRY_SEEN = 1804847651
ENTRY_CODE = 1005448092
ENTRY_FREQUENCY = 1992030782
ENTRY_WORKED_BEFORE = 424248790
ENTRY_STEPS = 1223347216
ENTRY_DISTRIBUTION = 158368381
ENTRY_VERSION = 868843241
ENTRY_INSTALL = 806698536
ENTRY_BIOS = 36849397
ENTRY_CORES = 2065940039
ENTRY_CUS = 568185977
ENTRY_OTHER_TOOLS = 435678328
ENTRY_TERMINAL = 1794625694
ENTRY_MEDIA = 923724431
ENTRY_CONTACT = 591697048
ENTRY_IDEAS = 1853494275
# The "Automatic report" page: filled by the app, never typed.
ENTRY_REFERENCE = 1776658400
ENTRY_WHERE = 411722285
ENTRY_RAW = 1408768783
ENTRY_SPECS = 1028547932
ENTRY_RECENT = 309991622
ENTRY_DETAILS = 552182803
ENTRY_HARDWARE = 897848333

AREAS = (
    "Dashboard / Prepare dependencies",
    "CPU (frequencies, profiles, core unlock)",
    "GPU governor (Cyan)",
    "Compute Units (40CU)",
    "Fans",
    "Telemetry and sensors",
    "FSR4 / OptiScaler",
    "Firmware (BIOS flashing)",
    "Drivers and case accessories",
    "App install or update",
    "Decky plugin (Game Mode)",
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
DISTRIBUTIONS = ("Bazzite", "CachyOS", "SteamOS", "Arch Linux", "Fedora", "Ubuntu", "Debian")
INSTALLS = (
    "Package from GitHub Releases (.pkg.tar.zst, .rpm, .deb)",
    "install-local.sh script",
    "Running from the source code (run.sh)",
    "Only the Decky plugin",
    "Not sure",
)
BIOSES = ("MeiMeiDXE v3", "Another modded BIOS", "Stock BIOS", "Not sure")
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

#: Questions with fixed choices; anything else typed goes into "Other".
CHOICES = {
    ENTRY_AREA: AREAS,
    ENTRY_SEEN: SEEN,
    ENTRY_DISTRIBUTION: DISTRIBUTIONS,
    ENTRY_OTHER_TOOLS: OTHER_TOOLS,
}

#: The pages each kind walks through when the live form cannot say (page 0
#: asks the kind). ``parse_form`` reads the real route from the form itself.
PAGES_PROBLEM = "0,1,2,3,4,5"
PAGES_IDEA = "0,5"

_LOAD_DATA = re.compile(r"FB_PUBLIC_LOAD_DATA_\s*=\s*(.*?);\s*</script>", re.S)
_FBZX = re.compile(r'name="fbzx"\s+value="([^"]+)"')
#: The page Google shows once a response is stored.
_CONFIRMATION = re.compile(r"freebirdFormviewerViewResponseConfirmationMessage|vHW8K", re.I)

_sent_lock = threading.Lock()
_last_sent = 0.0


#: The form's own confirmation message (Settings > Presentation), and
#: Google's default one for a form without it. Either sentence only appears
#: once the response is stored, and Google now also carries the form data on
#: that page, so the sentence must win over it.
CONFIRMATION_TEXTS = (
    "thanks, received. i read every one of them",
    "your response has been recorded",
)


_SCRIPT = re.compile(r"<script\b.*?</script>", re.S | re.I)


def confirmed(answer: str) -> bool:
    """Google's "response recorded" page, not the form drawn again."""
    # The form data inside the page's scripts already holds the confirmation
    # message, so only the text the page shows counts.
    shown = html.unescape(_SCRIPT.sub(" ", answer)).lower()
    if any(text in shown for text in CONFIRMATION_TEXTS):
        return True
    if _LOAD_DATA.search(answer):
        return False
    return bool(_CONFIRMATION.search(answer))


class FeedbackError(RuntimeError):
    """The report was not sent; ``fallback`` says the browser should take over."""

    def __init__(self, message: str, *, fallback: bool = True):
        super().__init__(message)
        self.fallback = fallback


@dataclass
class FeedbackReport:
    kind: str = KIND_PROBLEM
    summary: str = ""
    diagnostics: str = ""
    area: str = ""
    seen: list[str] = field(default_factory=list)
    code: str = ""
    frequency: str = ""
    worked_before: str = ""
    steps: str = ""
    distribution: str = ""
    version: str = ""
    install: str = ""
    bios: str = ""
    cores: str = ""
    cus: str = ""
    other_tools: list[str] = field(default_factory=list)
    terminal: str = ""
    media: str = ""
    # Filled by the app ("Automatic report"): never typed by the owner.
    reference: str = ""
    where: str = ""
    raw: str = ""
    specs: str = ""
    recent_errors: str = ""
    details: str = ""
    hardware: str = ""
    contact: str = ""
    ideas: str = ""

    @property
    def is_problem(self) -> bool:
        return self.kind == KIND_PROBLEM

    def missing(self) -> str:
        """The one required answer still empty, or an empty string."""
        if self.is_problem and not self.summary.strip():
            return "What went wrong?"
        if not self.is_problem and not self.ideas.strip():
            return "Suggestions and ideas"
        return ""


@dataclass(frozen=True)
class FormShape:
    """What the live form asks: choices per question, and its session token."""

    questions: dict[int, tuple[frozenset[str], bool]]
    token: str = ""
    #: ``pageHistory`` for a problem and for an idea, read from the form's
    #: sections and from where the "idea" answer jumps to.
    problem_pages: str = PAGES_PROBLEM
    idea_pages: str = PAGES_IDEA


def _clip(text: str, limit: int) -> str:
    text = str(text or "").strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _clip_tail(text: str, limit: int) -> str:
    """The end of a traceback is where it failed: keep that end."""
    text = str(text or "").strip()
    return text if len(text) <= limit else "..." + text[-(limit - 3):]


def parse_form(page_text: str) -> FormShape:
    match = _LOAD_DATA.search(page_text)
    if match is None:
        raise FeedbackError("The report form could not be read.")
    try:
        data = json.loads(match.group(1))
        items = data[1][1] or []
    except (ValueError, IndexError, TypeError) as error:
        raise FeedbackError("The report form could not be read.") from error
    questions: dict[int, tuple[frozenset[str], bool]] = {}
    page = 0
    section_pages: dict[int, int] = {}
    idea_jump = None
    for item in items:
        if not isinstance(item, list) or len(item) < 4:
            continue
        if item[3] == 8:  # a page break starts the next section
            page += 1
            if isinstance(item[0], int):
                section_pages[item[0]] = page
            continue
        if len(item) < 5 or not item[4]:
            continue
        for question in item[4]:
            if question and question[0] == ENTRY_KIND:
                for choice in question[1] or []:
                    if choice and choice[0] == KIND_IDEA and len(choice) > 2 and isinstance(choice[2], int):
                        idea_jump = choice[2]
            if not question or not isinstance(question[0], int):
                continue
            raw = question[1] if len(question) > 1 and question[1] else []
            labels = frozenset(str(choice[0]) for choice in raw if choice and choice[0])
            # A choice whose fifth field is 1 is the form's "Other: ___".
            has_other = any(len(choice) > 4 and choice[4] == 1 for choice in raw if choice)
            questions[question[0]] = (labels, has_other)
    token = _FBZX.search(page_text)
    problem_pages = ",".join(str(number) for number in range(page + 1))
    idea_from = section_pages.get(idea_jump, page) if idea_jump is not None else page
    idea_pages = ",".join(str(number) for number in [0, *range(idea_from, page + 1)])
    return FormShape(
        questions=questions,
        token=html.unescape(token.group(1)) if token else "",
        problem_pages=problem_pages if page else PAGES_PROBLEM,
        idea_pages=idea_pages if page else PAGES_IDEA,
    )


def _pairs(report: FeedbackReport) -> list[tuple[int, object]]:
    """Every answer this report gives, as (question id, text or list)."""
    pairs: list[tuple[int, object]] = [(ENTRY_KIND, report.kind)]
    if report.is_problem:
        pairs += [
            (ENTRY_SUMMARY, _clip(report.summary, MAX_SHORT_TEXT)),
            (ENTRY_DIAGNOSTICS, _clip(report.diagnostics, MAX_LONG_TEXT)),
            (ENTRY_AREA, report.area),
            (ENTRY_SEEN, list(report.seen)),
            (ENTRY_CODE, _clip(report.code, MAX_SHORT_TEXT)),
            (ENTRY_FREQUENCY, report.frequency),
            (ENTRY_WORKED_BEFORE, report.worked_before),
            (ENTRY_STEPS, _clip(report.steps, MAX_LONG_TEXT)),
            (ENTRY_DISTRIBUTION, report.distribution),
            (ENTRY_VERSION, _clip(report.version, MAX_SHORT_TEXT)),
            (ENTRY_INSTALL, report.install),
            (ENTRY_BIOS, report.bios),
            (ENTRY_CORES, report.cores),
            (ENTRY_CUS, report.cus),
            (ENTRY_OTHER_TOOLS, list(report.other_tools)),
            (ENTRY_TERMINAL, _clip(report.terminal, MAX_LONG_TEXT)),
            (ENTRY_MEDIA, _clip(report.media, MAX_SHORT_TEXT)),
            (ENTRY_REFERENCE, _clip(report.reference, MAX_SHORT_TEXT)),
            (ENTRY_WHERE, _clip(report.where, MAX_LONG_TEXT)),
            (ENTRY_RAW, _clip_tail(report.raw, MAX_LONG_TEXT)),
            (ENTRY_SPECS, _clip(report.specs, MAX_LONG_TEXT)),
            (ENTRY_RECENT, _clip(report.recent_errors, MAX_LONG_TEXT)),
            (ENTRY_DETAILS, _clip(report.details, MAX_LONG_TEXT)),
            (ENTRY_HARDWARE, _clip(report.hardware, MAX_HARDWARE_TEXT)),
        ]
    pairs += [
        (ENTRY_CONTACT, _clip(report.contact, MAX_SHORT_TEXT)),
        (ENTRY_IDEAS, _clip(report.ideas, MAX_LONG_TEXT)),
    ]
    # Nothing leaves the machine with the user's home folder (and name) in it.
    return [
        (entry, value if isinstance(value, list) else redact(value))
        for entry, value in pairs if value
    ]


def form_fields(report: FeedbackReport, shape: FormShape) -> list[tuple[str, str]]:
    """The POST body, checked against the live form.

    A question the form no longer has stops the send: answering into a
    renamed form would store the words under the wrong question. A choice
    the form no longer offers goes into its "Other" box when it has one.
    """
    fields: list[tuple[str, str]] = []
    for entry, value in _pairs(report):
        if entry not in shape.questions:
            raise FeedbackError("The report form changed since this version of the app.")
        labels, has_other = shape.questions[entry]
        values = value if isinstance(value, list) else [value]
        others = []
        for item in values:
            text = str(item)
            if not labels or text in labels:
                fields.append((f"entry.{entry}", text))
            elif has_other:
                others.append(text)
            else:
                raise FeedbackError("The report form changed since this version of the app.")
        if others:
            fields += [(f"entry.{entry}", OTHER), (f"entry.{entry}.other_option_response", ", ".join(others))]
    pages = shape.problem_pages if report.is_problem else shape.idea_pages
    fields += [("fvv", "1"), ("pageHistory", pages)]
    if shape.token:
        fields += [("fbzx", shape.token), ("partialResponse", json.dumps([None, None, shape.token], separators=(",", ":")))]
    return fields


#: Answers too long for a URL: the browser fallback copies them instead.
_LONG_ANSWERS = frozenset({
    ENTRY_DIAGNOSTICS, ENTRY_STEPS, ENTRY_TERMINAL, ENTRY_IDEAS,
    ENTRY_WHERE, ENTRY_RAW, ENTRY_SPECS, ENTRY_RECENT, ENTRY_DETAILS, ENTRY_HARDWARE,
})


def prefill_url(report: FeedbackReport) -> str:
    """The form in the browser with the short answers already chosen.

    Long texts stay out: a URL has a length limit, and the dialog copies them
    to the clipboard for pasting.
    """
    query = [("usp", "pp_url")]
    for entry, value in _pairs(report):
        if entry in _LONG_ANSWERS:
            continue
        choices = CHOICES.get(entry)
        for item in value if isinstance(value, list) else [value]:
            if choices is not None and item not in choices:
                query += [(f"entry.{entry}", OTHER), (f"entry.{entry}.other_option_response", str(item))]
            else:
                query.append((f"entry.{entry}", str(item)))
    return f"{FORM_URL}?{urllib.parse.urlencode(query)}"


def _open(request: urllib.request.Request) -> str:
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310 - fixed https host
            if response.status != 200:
                raise FeedbackError("Google Forms answered with an error.")
            return response.read(MAX_PAGE_BYTES).decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        raise FeedbackError("Google Forms answered with an error.") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise FeedbackError("Google Forms could not be reached. Check the internet connection.") from error


def _request(url: str, data: bytes | None = None) -> urllib.request.Request:
    request = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    request.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) BC250-Control-Center")
    request.add_header("Accept-Language", "en")
    if data:
        request.add_header("Content-Type", "application/x-www-form-urlencoded;charset=utf-8")
    return request


#: Long answers in the order they give up room when the body is too big: the
#: first one is cut first. What the owner typed comes last.
_SHRINK_ORDER = (
    ("recent_errors", False), ("terminal", True), ("details", False), ("specs", False),
    ("hardware", False), ("raw", True), ("where", False), ("steps", False),
    ("diagnostics", False), ("ideas", False),
)
CUT_NOTE = "\n… (cut to fit the form; the full text is in Open in browser)"


def _body(report: FeedbackReport, shape: FormShape) -> bytes:
    return urllib.parse.urlencode(form_fields(report, shape)).encode("utf-8")


def fit_report(report: FeedbackReport, shape: FormShape, limit: int = MAX_POST_BYTES) -> FeedbackReport:
    """The same report, its least important long answers cut until it fits."""
    for name, keep_end in _SHRINK_ORDER:
        while len(_body(report, shape)) > limit:
            text = str(getattr(report, name) or "")
            if text.endswith(CUT_NOTE):
                text = text[: -len(CUT_NOTE)]
            elif text.startswith("…"):
                text = text[1:]
            if len(text) <= 200:
                break
            excess = len(_body(report, shape)) - limit
            # Encoded text is up to ~3x longer than the text: cut by bytes over,
            # at least a quarter, so a few rounds settle it.
            keep = max(200, len(text) - max(excess, len(text) // 4))
            cut = ("…" + text[-keep:]) if keep_end else (text[:keep].rstrip() + CUT_NOTE)
            report = replace(report, **{name: cut})
        if len(_body(report, shape)) <= limit:
            return report
    return report


def submit(
    report: FeedbackReport,
    *,
    fetch: Callable[[urllib.request.Request], str] = _open,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Send the report, or raise ``FeedbackError`` saying why it was not sent."""
    global _last_sent
    missing = report.missing()
    if missing:
        raise FeedbackError("A required answer is empty.", fallback=False)
    with _sent_lock:
        if _last_sent and clock() - _last_sent < MIN_SECONDS_BETWEEN:
            raise FeedbackError("A report was sent a moment ago. Wait a few seconds.", fallback=False)
        shape = parse_form(fetch(_request(f"{FORM_URL}?hl=en")))
        body = _body(fit_report(report, shape), shape)
        answer = fetch(_request(f"{RESPONSE_URL}?hl=en", body))
        # Google answers 200 for a rejected response too, with the form drawn
        # again; only the confirmation page, without the form in it, means
        # the answers were stored.
        if not confirmed(answer):
            raise FeedbackError("Google Forms did not confirm the report.")
        _last_sent = clock()


# --- Answers the app already knows -------------------------------------------------


def suggested_distribution(os_release: dict[str, str]) -> str:
    ids = " ".join((os_release.get("ID", ""), os_release.get("ID_LIKE", ""), os_release.get("NAME", ""))).lower()
    for label, needle in (
        ("Bazzite", "bazzite"), ("CachyOS", "cachyos"), ("SteamOS", "steamos"),
        ("Fedora", "fedora"), ("Ubuntu", "ubuntu"), ("Debian", "debian"),
    ):
        if needle in ids:
            return label
    if os_release.get("ID", "").lower() == "arch":
        return "Arch Linux"
    return os_release.get("PRETTY_NAME") or os_release.get("NAME") or ""


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
_AREA_WORDS = (
    (("HELIXSR", "FSR4", "OPTISCALER", "UPSCAL"), "FSR4 / OptiScaler"),
    (("CYAN", "GPU"), "GPU governor (Cyan)"),
    (("COMPUTE UNIT", "40CU", " CU"), "Compute Units (40CU)"),
    (("CPU", "CORE UNLOCK", "SMU"), "CPU (frequencies, profiles, core unlock)"),
    (("FAN",), "Fans"),
    (("FIRMWARE", "BIOS", "FLASH"), "Firmware (BIOS flashing)"),
    (("DRIVER", "ACCESSOR", "LCD", "RGB"), "Drivers and case accessories"),
    (("UPDATE", "INSTALL"), "App install or update"),
    (("DECKY",), "Decky plugin (Game Mode)"),
    (("TELEMETRY", "SENSOR", "GDDR6", "TEMPERATURE"), "Telemetry and sensors"),
    (("DEPENDENC", "PREPAR", "DASHBOARD"), "Dashboard / Prepare dependencies"),
)


#: Origin sections (``error_origins``) and the form's answer for each.
AREA_BY_SECTION = {
    "UPS": "FSR4 / OptiScaler",
    "GPU": "GPU governor (Cyan)",
    "CU": "Compute Units (40CU)",
    "CPU": "CPU (frequencies, profiles, core unlock)",
    "FAN": "Fans",
    "FW": "Firmware (BIOS flashing)",
    "DRV": "Drivers and case accessories",
    "UPD": "App install or update",
    "DECKY": "Decky plugin (Game Mode)",
    "TEL": "Telemetry and sensors",
    "MEM": "Telemetry and sensors",
    "DASH": "Dashboard / Prepare dependencies",
    "PREP": "Dashboard / Prepare dependencies",
}


def suggested_area(context: str) -> str:
    text = f" {context.upper()} "
    for words, area in _AREA_WORDS:
        if any(word in text for word in words):
            return area
    return ""


def suggested_cores(physical_cores: int) -> str:
    # Eight cores came from the BIOS or from Control Center; only the owner knows.
    return CORES[0] if physical_cores == 6 else ""
