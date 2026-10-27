"""Where a failure happened: a stable code for every function of the app.

``error_catalog`` says *what* went wrong (``BC250-UPSCALE-001``: the upscaler
could not be changed). This module says *where*: every function in the
desktop app and the backend has an origin code such as ``GPU-0142``, kept in
``error_origins.json`` so it never changes once given. An error window shows
two of them, the screen action the owner pressed and the line that raised, so
a report names the exact function without anyone reading a traceback.

The catalog is generated, not written by hand::

    python -m bc250cc.shared.error_origins

adds the functions that are new, keeps every code already given (a function
that moved or was renamed gets a new one; the old code is retired, never
reused) and a test fails while it is out of date.
"""

from __future__ import annotations

import ast
import json
import re
import sys
import traceback
from dataclasses import dataclass
from fnmatch import fnmatch
from functools import lru_cache
from pathlib import Path
from types import FrameType, TracebackType

CATALOG_PATH = Path(__file__).with_name("error_origins.json")
#: The trees whose functions get a code, relative to the repository root.
SOURCE_TREES = ("frontends/desktop", "src/bc250cc")
#: Generated translation tables: data, not code anyone calls.
SKIPPED = ("frontends/desktop/i18n/*catalog.py",)

#: Sections in match order: the first pattern that fits a module wins.
#: Patterns match the module's key (``bc250cc/...`` or ``frontends/desktop/...``).
SECTIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("DIAG", "Diagnostics and reports", (
        "*/diagnostic_*", "*/error_*", "*/failure_text.py", "*/feedback_*", "*/system_snapshot.py",
        "*/shared/errors.py",
    )),
    ("CON", "Built-in terminal", ("*/console/*",)),
    ("UPS", "Upscaling (FSR4, HelixSR)", (
        "*/helixsr*", "*/bc250_fsr4*", "*/opticlient*", "*/bc250_opticlient*", "*/steam_launch_options*",
        "*/upscaler_*", "*/preparation_pages.py", "*/preparation_render.py",
    )),
    ("DECKY", "Decky plugin (Game Mode)", ("*/decky_*", "*/quick_access*", "*/external_tools/*")),
    ("UPD", "App install and update", (
        "*/update_dialog.py", "*/self_update.py", "*/release_check.py", "*/install_source.py",
        "*/source_checkout.py", "*/repository_provenance.py",
    )),
    ("CU", "Compute Units (40CU)", ("*compute_units*", "*/cu_*", "*/gfx1013*", "*/steamos_cu_shell.py")),
    ("CPU", "CPU", ("*cpu*", "*/core_unlock*", "*/core_monitor.py")),
    ("GPU", "GPU governor", (
        "*gpu*", "*/governor_*", "*/cyan_*", "*/oberon*", "*/voltage*", "*/range_policy.py", "*/safe_points.py",
        "*/steamos_amdgpu*",
    )),
    ("FAN", "Fans", ("*fan*",)),
    ("FW", "Firmware", ("*firmware*", "*/boot_logo*", "*/usb*", "*/lzma1.py", "*/udisks.py")),
    ("DRV", "Drivers and case accessories", (
        "*/drivers*", "*/accessories/*", "*/tv_control.py", "*/hdmi*", "*/openlinkhub*", "*/thermalright*",
    )),
    ("TEL", "Telemetry and sensors", (
        "*telemetry*", "*/sensor*", "*/gddr6*", "*/vrm_*", "*/performance*", "*/realtime_*", "*/chart_*", "*/i2c_guide*",
        "*/dashboard_instruments.py",
    )),
    ("MEM", "Memory", ("*/memory*",)),
    ("PROC", "Processes", ("*/process*", "*/proceso.py")),
    ("DASH", "Dashboard", ("*/dashboard*", "*/attention.py", "*/alert*", "*/health/*")),
    ("PREP", "Prepare BC250 system", (
        "*/dependencias_*", "*/preparation*", "*/system_setup*", "*/component_engine.py", "*/tool_inventory.py",
        "*/toolkit_conflicts.py", "*/additional_settings.py", "*/init_services.py",
    )),
    ("DIST", "Distribution support", (
        "*/bazzite_*", "*/steamos_*", "*/cachyos_*", "*/debian_*", "*/fedora_*", "*/mesa_*", "*/radv_*",
        "*/vaapi_*", "*/container_network.py", "*/platform/*",
    )),
    ("SET", "Settings", ("*/settings*", "*/preferences.py", "*/persistence/*", "*/configuracion_*", "*/recovery*")),
    ("SYS", "System access", (
        "*/terminal_*", "*/privilege*", "*/polkit_*", "*/session_privilege*", "*/daemon*", "*/sistema_*",
        "*/system_service.py", "*/protected_file_health.py", "*/headless_dispatch.py", "*/script_presentation.py",
        "*/historial_*", "*/hardware_identity.py",
    )),
    ("ONB", "First-run guide", ("*/onboarding/*",)),
    ("I18N", "Languages", ("*/i18n/*",)),
    ("UI", "Interface", ("frontends/desktop/*",)),
    ("CORE", "Core", ("bc250cc/*",)),
)
SECTION_NAMES = {code: name for code, name, _patterns in SECTIONS}


@dataclass(frozen=True)
class Origin:
    """One function the failure passed through."""

    code: str
    section: str
    module: str
    function: str
    line: int = 0

    @property
    def section_name(self) -> str:
        return SECTION_NAMES.get(self.section, "Interface")

    @property
    def place(self) -> str:
        """``gpu_governor.py:812 · GpuGovernorPage._install``."""
        line = f":{self.line}" if self.line else ""
        return f"{Path(self.module).name}{line} · {self.function}"


def module_key(path: str | Path) -> str:
    """``.../src/bc250cc/x.py`` → ``bc250cc/x.py``; empty when not ours.

    Keys start at the package so an installed copy (``~/.local/share/...``)
    and a source checkout name a module the same way.
    """
    text = str(path).replace("\\", "/")
    for marker in ("/frontends/desktop/", "/bc250cc/"):
        index = text.rfind(marker)
        if index >= 0:
            return text[index + 1:]
    for marker in ("frontends/desktop/", "bc250cc/"):
        if text.startswith(marker):
            return text
    return ""


def section_of(key: str) -> str:
    for code, _name, patterns in SECTIONS:
        if any(fnmatch(key, pattern) for pattern in patterns):
            return code
    return "CORE"


def outer_function(qualname: str) -> str:
    """``Page.run.<locals>.failed`` → ``Page.run``: the catalogued function."""
    return qualname.split(".<locals>.", 1)[0]


@lru_cache(maxsize=1)
def _catalog() -> dict[str, dict[str, str]]:
    try:
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        return {module: dict(functions) for module, functions in data.get("modules", {}).items()}
    except (OSError, ValueError, AttributeError):
        return {}


def origin_for(key: str, qualname: str, line: int = 0) -> Origin:
    code = _catalog().get(key, {}).get(outer_function(qualname))
    # A function newer than the catalog still reports its section and name.
    section = _number(code)[0] if code else section_of(key)
    return Origin(code=code or f"{section}-0000", section=section, module=key, function=qualname, line=line)


def _frame_origin(code_object, filename: str, line: int) -> Origin | None:
    key = module_key(filename)
    if not key:
        return None
    qualname = getattr(code_object, "co_qualname", None) or code_object.co_name
    return origin_for(key, qualname, line)


def raise_site(error: BaseException | None = None, tb: TracebackType | None = None) -> Origin | None:
    """The innermost function of ours the exception passed through."""
    tb = tb or (error.__traceback__ if error is not None else None)
    found = None
    while tb is not None:
        frame = tb.tb_frame
        origin = _frame_origin(frame.f_code, frame.f_code.co_filename, tb.tb_lineno)
        if origin is not None:
            found = origin
        tb = tb.tb_next
    return found


#: Functions that only draw an error window; the origin is whoever called them.
_PRESENTERS = frozenset({
    "_show_info", "_show_error", "_show_safety_alert", "_fail", "_show_failure", "_error_dialog",
    "_present_error", "_report_error", "show_error",
})
_PRESENTER_MODULES = (
    "frontends/desktop/components/widgets.py",
    "frontends/desktop/components/dialogs.py",
    "frontends/desktop/components/page_widgets.py",
    "frontends/desktop/core/diagnostic_history.py",
    "frontends/desktop/core/error_diagnostics.py",
    "frontends/desktop/i18n/",
    "bc250cc/shared/error_origins.py",
)


def caller_origin(frame: FrameType | None = None) -> Origin | None:
    """The screen action that is showing the error: the first frame of ours
    above the window code and the small helpers that only draw it."""
    frame = frame or sys._getframe(1)
    fallback = None
    while frame is not None:
        key = module_key(frame.f_code.co_filename)
        if key and not key.startswith(_PRESENTER_MODULES):
            origin = _frame_origin(frame.f_code, frame.f_code.co_filename, frame.f_lineno)
            if origin is not None:
                if frame.f_code.co_name not in _PRESENTERS:
                    return origin
                fallback = fallback or origin
        frame = frame.f_back
    return fallback


_PATH = re.compile(r'File "([^"]+)"')
#: A home folder in any form a path can take; the name in it is the user's.
_HOME_PATH = re.compile(
    r"(?:/var)?/home/[^/\s'\"]+|/Users/[^/\s'\"]+|/root(?=/|\b)"
    # Removable drives and second disks mount under the user's name too
    # (SteamOS: /run/media/deck/<card>), and Steam libraries live there.
    r"|/run/media/[^/\s'\"]+|/media/[^/\s'\"]+"
)


def redact(text: object) -> str:
    """Text fit to leave the machine: every home folder becomes ``~``.

    Exception messages, install paths and command lines name files under the
    user's home, and the folder carries the user's name. The running user's
    home is replaced exactly; any other home path by pattern.
    """
    text = str(text or "")
    # The pattern first: on Bazzite the home is /home/<name> but paths read
    # /var/home/<name>, and replacing the exact home first left "/var~".
    text = _HOME_PATH.sub("~", text)
    home = str(Path.home())
    if home and home not in ("/", "/root"):
        text = text.replace(home, "~")
    return text


def _short_path(match: re.Match) -> str:
    path = match.group(1)
    key = module_key(path)
    if key:
        return f'File "{key}"'
    home = str(Path.home())
    # A report leaves the machine: the home folder carries the user's name.
    if home and home != "/" and path.startswith(home):
        path = "~" + path[len(home):]
    return f'File "{path}"'


def format_raw(error: BaseException, *, limit: int = 12) -> str:
    """The exception as Python printed it: type, message and the last frames.

    Paths of ours start at the package and the home folder reads ``~``.
    """
    lines = traceback.format_exception(type(error), error, error.__traceback__, limit=-limit)
    return redact(_PATH.sub(_short_path, "".join(lines).strip()))


# --- The catalog generator ---------------------------------------------------------


def _functions(source: str) -> list[str]:
    """Every function's qualified name, nested functions excluded."""
    names: list[str] = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.")
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.append(f"{prefix}{child.name}")

    visit(ast.parse(source), "")
    return names


def scan(root: Path) -> dict[str, list[str]]:
    modules: dict[str, list[str]] = {}
    for tree in SOURCE_TREES:
        for path in sorted((root / tree).rglob("*.py")):
            key = module_key(path.relative_to(root))
            if not key or "__pycache__" in path.parts or any(fnmatch(str(path.relative_to(root)), s) for s in SKIPPED):
                continue
            functions = _functions(path.read_text(encoding="utf-8"))
            if functions:
                modules[key] = list(dict.fromkeys(functions))
    return modules


def _number(code: str) -> tuple[str, int]:
    section, _, number = str(code).rpartition("-")
    return section, int(number) if number.isdigit() else 0


def build_catalog(root: Path, previous: dict | None = None) -> dict:
    """Keep every code already given, whole; number new functions after the highest.

    Codes are stored whole (``UPS-0181``): a module that later moves to another
    section keeps the codes it had, and only its new functions take the new
    prefix. A code that disappears is retired and never handed out again.
    """
    previous = previous or {}
    old_modules: dict[str, dict[str, str]] = previous.get("modules", {})
    retired: set[str] = set(previous.get("retired", []))
    highest: dict[str, int] = {code: 0 for code in SECTION_NAMES}
    for code in [*retired, *(c for functions in old_modules.values() for c in functions.values())]:
        section, number = _number(code)
        highest[section] = max(highest.get(section, 0), number)

    modules: dict[str, dict[str, str]] = {}
    for key, functions in scan(root).items():
        section = section_of(key)
        known = old_modules.get(key, {})
        entry: dict[str, str] = {}
        for name in functions:
            if name in known:
                entry[name] = known[name]
            else:
                highest[section] = highest.get(section, 0) + 1
                entry[name] = f"{section}-{highest[section]:04d}"
        modules[key] = entry

    alive = {code for functions in modules.values() for code in functions.values()}
    for functions in old_modules.values():
        retired |= {code for code in functions.values() if code not in alive}
    return {
        "version": 2,
        "note": "Generated by `python -m bc250cc.shared.error_origins`. Codes are never reused.",
        "sections": {code: name for code, name, _p in SECTIONS},
        "modules": dict(sorted(modules.items())),
        "retired": sorted(retired),
    }


def write_catalog(root: Path, path: Path = CATALOG_PATH) -> dict:
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}
    catalog = build_catalog(root, previous)
    path.write_text(json.dumps(catalog, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    _catalog.cache_clear()
    return catalog


if __name__ == "__main__":  # pragma: no cover - maintenance entry point
    repository = Path(__file__).resolve().parents[3]
    result = write_catalog(repository)
    total = sum(len(functions) for functions in result["modules"].values())
    print(f"{total} functions in {len(result['modules'])} modules -> {CATALOG_PATH}")
